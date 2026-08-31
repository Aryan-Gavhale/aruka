"""SQLite access layer.

One connection per request, stored on flask.g. Rows come back as sqlite3.Row so
templates can use both dict and attribute-ish access. The schema is applied on
boot with executescript(); every statement in schema.sql is idempotent, which
keeps "migrations" to appending new statements to that file.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g

SCHEMA_VERSION = 1


def _db_path() -> str:
    root = Path(current_app.root_path)
    configured = current_app.config.get("DB_PATH", "db/aruka.db")
    path = Path(configured)
    if not path.is_absolute():
        path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(_db_path())
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# ── queries ────────────────────────────────────────────────────────────────
def query(sql: str, args=(), one: bool = False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def one(sql: str, args=()):
    return query(sql, args, one=True)


def scalar(sql: str, args=(), default=None):
    row = one(sql, args)
    if row is None:
        return default
    value = row[0]
    return default if value is None else value


def execute(sql: str, args=()) -> int:
    cur = get_db().execute(sql, args)
    rowid = cur.lastrowid
    cur.close()
    return rowid


def executemany(sql: str, seq) -> None:
    cur = get_db().executemany(sql, seq)
    cur.close()


@contextmanager
def transaction():
    """Group writes that only make sense together.

    The connection runs in autocommit, so a payment and the invoice balance it
    settles would otherwise be two independent writes with a window between
    them. Re-entrant: an inner block joins the outer one rather than failing.
    """
    conn = get_db()
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def insert(table: str, data: dict) -> int:
    keys = list(data.keys())
    cols = ", ".join(keys)
    marks = ", ".join("?" for _ in keys)
    return execute(
        f"INSERT INTO {table} ({cols}) VALUES ({marks})",
        [data[k] for k in keys],
    )


def update(table: str, row_id, data: dict, key: str = "id") -> None:
    if not data:
        return
    keys = list(data.keys())
    sets = ", ".join(f"{k} = ?" for k in keys)
    execute(
        f"UPDATE {table} SET {sets} WHERE {key} = ?",
        [data[k] for k in keys] + [row_id],
    )


def delete(table: str, row_id, key: str = "id") -> None:
    execute(f"DELETE FROM {table} WHERE {key} = ?", (row_id,))


def next_sort_order(table: str, where: str = "", args=()) -> int:
    clause = f" WHERE {where}" if where else ""
    return int(scalar(f"SELECT COALESCE(MAX(sort_order), -1) + 1 FROM {table}{clause}", args, 0))


def table_columns(table: str) -> list[str]:
    return [r["name"] for r in query(f"PRAGMA table_info({table})")]


def table_exists(table: str) -> bool:
    return one("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)) is not None


# ── schema ─────────────────────────────────────────────────────────────────
def init_schema() -> None:
    schema_file = Path(current_app.root_path) / "db" / "schema.sql"
    sql = schema_file.read_text(encoding="utf-8")
    conn = get_db()
    conn.executescript(sql)
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(SCHEMA_VERSION),),
    )


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_schema()


def db_file_size() -> int:
    """Size of the SQLite file in bytes; 0 if it cannot be read."""
    try:
        return os.path.getsize(_db_path())
    except OSError:
        return 0


def db_file_path() -> str:
    return _db_path()
