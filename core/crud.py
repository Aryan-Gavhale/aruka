"""A small declarative admin: describe a table once, get list, form, save,
delete, active-toggle and drag-reorder routes with consistent behaviour.

Most admin screens in Aruka are one Resource() - services, case studies,
testimonials, FAQs, posts, packages, add-ons, pricing rules, message templates,
expense categories, SLA policies, clauses, users. That is what keeps the panel
uniform instead of twenty hand-written screens, and what makes "add a field"
one Field() line plus one column in schema.sql.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Callable, Iterable

from flask import (abort, flash, jsonify, redirect, render_template, request,
                   url_for)

from core import audit, db
from core.auth import require_role, verify_csrf
from core.util import (dump_json, load_json, parse_bool, parse_float,
                       parse_int, slugify, unique_slug)

KINDS_TEXT = {"text", "email", "tel", "url", "slug", "date", "time", "color", "hidden"}


@dataclass
class Field:
    name: str
    label: str
    kind: str = "text"
    help: str = ""
    required: bool = False
    options: Any = None                 # list[(value, label)] or callable
    default: Any = None
    placeholder: str = ""
    span: int = 12                      # 12-column form grid
    json: bool = False                  # stored inside the resource json column
    line_keys: tuple[str, ...] = ()     # for kind="lines": keys per pipe-separated row
    rows: int = 4
    step: str = "1"
    prefix: str = ""
    suffix: str = ""
    owner_only: bool = False            # internal cost / margin columns

    def choices(self) -> list[tuple[Any, str]]:
        if callable(self.options):
            return list(self.options())
        return list(self.options or [])


def coerce(f: Field, raw) -> Any:
    if f.kind in ("checkbox", "bool"):
        return 1 if parse_bool(raw) else 0
    if f.kind in ("number", "money", "float"):
        return parse_float(raw, None if raw in (None, "") else 0.0)
    if f.kind in ("int", "integer"):
        return parse_int(raw, None if raw in (None, "") else 0)
    if f.kind == "media":
        value = parse_int(raw, 0)
        return value or None
    if f.kind == "select":
        if raw in (None, ""):
            return None
        choices = f.choices()
        if choices and isinstance(choices[0][0], int):
            return parse_int(raw, None)
        return raw
    if f.kind == "lines":
        return parse_lines(raw, f.line_keys)
    if f.kind == "csv":
        return ", ".join(p.strip() for p in str(raw or "").split(",") if p.strip())
    return (raw or "").strip() if isinstance(raw, str) else raw


def parse_lines(raw, keys: Iterable[str]) -> list:
    keys = list(keys)
    out = []
    for line in str(raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if not keys:
            out.append(line)
            continue
        parts = [p.strip() for p in line.split("|")]
        item = {}
        for i, key in enumerate(keys):
            item[key] = parts[i] if i < len(parts) else ""
        out.append(item)
    return out


def lines_to_text(value, keys: Iterable[str]) -> str:
    keys = list(keys)
    if not value:
        return ""
    if isinstance(value, str):
        return value
    rows = []
    for item in value:
        if isinstance(item, dict):
            rows.append(" | ".join(str(item.get(k, "")) for k in keys))
        else:
            rows.append(str(item))
    return "\n".join(rows)


def form_value(f: Field, row) -> Any:
    """Value to pre-fill the form control with."""
    if row is None:
        raw = f.default
    elif f.json:
        raw = (row or {}).get(f.name, f.default)
    else:
        try:
            raw = row[f.name]
        except (KeyError, IndexError, TypeError):
            raw = f.default
    if f.kind == "lines":
        return lines_to_text(raw, f.line_keys)
    if raw is None:
        return ""
    return raw


# ── resources ───────────────────────────────────────────────────────────────
@dataclass
class Resource:
    key: str
    table: str
    label: str
    label_plural: str
    fields: list[Field]
    list_columns: list[tuple[str, str]] = dc_field(default_factory=list)
    list_sql: str | None = None
    order_by: str = "id DESC"
    sortable: bool = False
    publishable: bool = False
    activatable: bool = False
    searchable: tuple[str, ...] = ()
    base_where: str = ""                # a permanent filter, e.g. channel = 'whatsapp'
    defaults: dict = dc_field(default_factory=dict)  # forced on every insert
    area: str = "content"
    slug_from: str | None = None
    row_label: str = "name"
    json_column: str | None = None
    icon: str = "list"
    intro: str = ""
    before_save: Callable | None = None   # (data, existing) -> None; may mutate data
    on_saved: Callable | None = None
    deletable: bool = True

    # ── data access ────────────────────────────────────────────────────────
    def rows(self, search: str = "", extra_where: str = "", args: list | None = None):
        args = list(args or [])
        sql = self.list_sql or f"SELECT * FROM {self.table}"
        where = []
        if self.base_where:
            where.append(f"({self.base_where})")
        if search and self.searchable:
            ors = " OR ".join(f"{c} LIKE ?" for c in self.searchable)
            where.append(f"({ors})")
            args += [f"%{search}%"] * len(self.searchable)
        if extra_where:
            where.append(extra_where)
        if where:
            joiner = " AND " if " WHERE " in sql.upper() else " WHERE "
            sql += joiner + " AND ".join(where)
        order = "sort_order, id" if self.sortable else self.order_by
        sql += f" ORDER BY {order}"
        return db.query(sql, args)

    def row(self, row_id):
        sql = f"SELECT * FROM {self.table} WHERE id = ?"
        if self.base_where:
            sql += f" AND ({self.base_where})"
        return db.one(sql, (row_id,))

    def label_for(self, row) -> str:
        try:
            return str(row[self.row_label] or f"#{row['id']}")
        except (KeyError, IndexError, TypeError):
            return f"#{row['id']}"

    def toggle_column(self) -> str:
        return "is_published" if self.publishable else "is_active"

    def visible_fields(self, owner: bool) -> list[Field]:
        return [f for f in self.fields if owner or not f.owner_only]

    # ── writes ─────────────────────────────────────────────────────────────
    def read_form(self, form, existing=None) -> dict:
        direct: dict = {}
        blob: dict = load_json(existing[self.json_column], {}) if (existing and self.json_column) else {}

        for f in self.fields:
            if f.kind == "heading":
                continue
            present = f.name in form or f.kind in ("checkbox", "bool")
            if not present:
                continue
            value = coerce(f, form.get(f.name))
            if f.json:
                blob[f.name] = value
            else:
                direct[f.name] = value

        if self.slug_from:
            source = direct.get(self.slug_from) or (existing[self.slug_from] if existing else "")
            given = (form.get("slug") or "").strip()
            if given:
                direct["slug"] = slugify(given)
            elif not existing or not existing["slug"]:
                direct["slug"] = unique_slug(source, self._slug_taken)
            if "slug" in direct and existing and direct["slug"] != existing["slug"]:
                direct["slug"] = unique_slug(direct["slug"], lambda s: self._slug_taken(s, existing["id"]))

        if self.json_column:
            direct[self.json_column] = dump_json(blob)

        if existing is None:
            for key, value in self.defaults.items():
                direct.setdefault(key, value)

        if self.before_save:
            self.before_save(direct, existing)

        columns = set(db.table_columns(self.table))
        if "updated_at" in columns:
            direct["updated_at"] = db.scalar("SELECT datetime('now')")
        return {k: v for k, v in direct.items() if k in columns}

    def _slug_taken(self, slug: str, exclude_id=None) -> bool:
        sql = f"SELECT 1 FROM {self.table} WHERE slug = ?"
        args: list = [slug]
        if exclude_id:
            sql += " AND id != ?"
            args.append(exclude_id)
        return db.one(sql, args) is not None

    def validate(self, data: dict, form) -> list[str]:
        errors = []
        for f in self.fields:
            if not f.required:
                continue
            value = data.get(f.name) if not f.json else load_json(data.get(self.json_column, "{}")).get(f.name)
            if value in (None, "", []):
                errors.append(f"{f.label} is required.")
        return errors


def wants_json() -> bool:
    """True when the caller is our own fetch() rather than a form post."""
    return (request.headers.get("X-CSRF-Token")
            or request.headers.get("X-Requested-With") == "fetch"
            or request.accept_mimetypes.best == "application/json")


# ── route registration ──────────────────────────────────────────────────────
def register(bp, res: Resource) -> None:
    key = res.key

    @bp.route(f"/{key}", endpoint=f"{key}_list")
    @require_role(res.area)
    def _list(res=res):
        search = (request.args.get("q") or "").strip()
        rows = res.rows(search)
        return render_template(
            "admin/crud_list.html", res=res, rows=rows, search=search,
            title=res.label_plural,
        )

    @bp.route(f"/{key}/new", methods=["GET", "POST"], endpoint=f"{key}_new")
    @require_role(res.area)
    def _new(res=res):
        if request.method == "POST":
            verify_csrf()
            data = res.read_form(request.form)
            errors = res.validate(data, request.form)
            if errors:
                for message in errors:
                    flash(message, "error")
                return render_template(
                    "admin/crud_form.html", res=res, row=None, blob={},
                    title=f"New {res.label.lower()}",
                )
            if res.sortable and "sort_order" not in data:
                data["sort_order"] = db.next_sort_order(res.table)
            row_id = db.insert(res.table, data)
            audit.log("create", res.table, row_id, str(data.get(res.row_label, "")), after=data)
            if res.on_saved:
                res.on_saved(row_id, data, None)
            flash(f"{res.label} created.", "ok")
            return redirect(url_for(f"admin.{key}_edit", row_id=row_id))

        return render_template(
            "admin/crud_form.html", res=res, row=None, blob={},
            title=f"New {res.label.lower()}",
        )

    @bp.route(f"/{key}/<int:row_id>", methods=["GET", "POST"], endpoint=f"{key}_edit")
    @require_role(res.area)
    def _edit(row_id, res=res):
        row = res.row(row_id)
        if not row:
            abort(404)
        if request.method == "POST":
            verify_csrf()
            data = res.read_form(request.form, row)
            errors = res.validate(data, request.form)
            if errors:
                for message in errors:
                    flash(message, "error")
            else:
                db.update(res.table, row_id, data)
                audit.log("update", res.table, row_id, res.label_for(row), before=row, after=data)
                if res.on_saved:
                    res.on_saved(row_id, data, row)
                flash(f"{res.label} saved.", "ok")
                return redirect(url_for(f"admin.{key}_edit", row_id=row_id))
            row = res.row(row_id)

        blob = load_json(row[res.json_column], {}) if res.json_column else {}
        return render_template(
            "admin/crud_form.html", res=res, row=row, blob=blob,
            title=res.label_for(row),
        )

    @bp.route(f"/{key}/<int:row_id>/delete", methods=["POST"], endpoint=f"{key}_delete")
    @require_role(res.area)
    def _delete(row_id, res=res):
        verify_csrf()
        row = res.row(row_id)
        if not row:
            abort(404)
        if not res.deletable:
            flash(f"{res.label_plural} cannot be deleted, only deactivated.", "error")
            return redirect(url_for(f"admin.{key}_edit", row_id=row_id))
        db.delete(res.table, row_id)
        audit.log("delete", res.table, row_id, res.label_for(row), before=row)
        flash(f"{res.label} deleted.", "ok")
        return redirect(url_for(f"admin.{key}_list"))

    @bp.route(f"/{key}/<int:row_id>/toggle", methods=["POST"], endpoint=f"{key}_toggle")
    @require_role(res.area)
    def _toggle(row_id, res=res):
        verify_csrf()
        row = res.row(row_id)
        if not row:
            abort(404)
        column = res.toggle_column()
        new_value = 0 if row[column] else 1
        db.update(res.table, row_id, {column: new_value})
        audit.log("update", res.table, row_id, res.label_for(row),
                  before={column: row[column]}, after={column: new_value})
        if wants_json():
            return jsonify({"ok": True, "on": bool(new_value)})
        flash("Visibility updated." if res.publishable else "Status updated.", "ok")
        return redirect(request.referrer or url_for(f"admin.{key}_list"))

    @bp.route(f"/{key}/reorder", methods=["POST"], endpoint=f"{key}_reorder")
    @require_role(res.area)
    def _reorder(res=res):
        verify_csrf()
        payload = request.get_json(silent=True, force=True) or {}
        order = payload.get("order") or payload.get("ids") or []
        if not isinstance(order, list):
            return jsonify({"ok": False, "error": "Expected a list of row ids."}), 400
        try:
            ids = [int(row_id) for row_id in order]
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Row ids have to be numbers."}), 400
        with db.transaction():
            for index, row_id in enumerate(ids):
                db.update(res.table, row_id, {"sort_order": index})
        audit.log("update", res.table, "", f"reordered {len(ids)} rows")
        return jsonify({"ok": True, "count": len(ids)})
