"""Audit trail. Every admin write goes through here so the owner can see who
changed what, and what the value was before."""

from __future__ import annotations

from core import db
from core.auth import current_user
from core.util import client_ip, dump_json

SKIP_KEYS = {"password_hash", "csrf_token", "secret_ciphertext", "cloud_token", "smtp_password"}


def _clean(payload) -> str | None:
    if payload is None:
        return None
    if hasattr(payload, "keys"):
        data = {k: payload[k] for k in payload.keys() if k not in SKIP_KEYS}
    elif isinstance(payload, dict):
        data = {k: v for k, v in payload.items() if k not in SKIP_KEYS}
    else:
        data = {"value": str(payload)}
    return dump_json(data)


def log(action: str, entity: str, entity_id="", label: str = "", before=None, after=None,
        actor: str = "") -> None:
    user = current_user()
    try:
        ip = client_ip()
    except RuntimeError:  # outside a request
        ip = ""
    db.insert(
        "audit_log",
        {
            "user_id": user["id"] if user else None,
            "user_email": user["email"] if user else (actor or "system"),
            "action": action,
            "entity": entity,
            "entity_id": str(entity_id or ""),
            "label": label[:200],
            "before_json": _clean(before),
            "after_json": _clean(after),
            "ip": (ip or "")[:60],
        },
    )


def recent(limit: int = 30):
    return db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))


def for_entity(entity: str, entity_id, limit: int = 40):
    return db.query(
        "SELECT * FROM audit_log WHERE entity = ? AND entity_id = ? ORDER BY id DESC LIMIT ?",
        (entity, str(entity_id), limit),
    )
