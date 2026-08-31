"""Media library: upload, edit alt text, delete with a usage warning, and the
picker modal every media field opens."""

from __future__ import annotations

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from blueprints.admin import bp
from core import audit, db, media
from core.auth import require_role, verify_csrf
from core.crud import wants_json


@bp.route("/media", endpoint="media")
@require_role("media")
def media_library():
    search = (request.args.get("q") or "").strip()
    rows = media.library(search)
    return render_template("admin/media.html", title="Media", rows=rows, search=search)


@bp.route("/media/upload", methods=["POST"])
@require_role("media")
def media_upload():
    verify_csrf()
    files = request.files.getlist("files")
    saved, errors = [], []
    for item in files:
        if not item or not item.filename:
            continue
        try:
            saved.append(media.save_upload(item))
        except ValueError as exc:
            errors.append(str(exc))
    if saved:
        audit.log("create", "media", "", f"uploaded {len(saved)} file(s)")

    if wants_json():
        return jsonify({"ok": bool(saved), "saved": len(saved), "errors": errors})
    for message in errors:
        flash(message, "error")
    if saved:
        flash(f"Uploaded {len(saved)} file(s).", "ok")
    return redirect(url_for("admin.media"))


@bp.route("/media/<int:media_id>", methods=["POST"])
@require_role("media")
def media_edit(media_id):
    verify_csrf()
    row = media.get(media_id)
    if not row:
        abort(404)
    changes = {
        "alt": (request.form.get("alt") or "").strip()[:300],
        "title": (request.form.get("title") or "").strip()[:200],
        "credit": (request.form.get("credit") or "").strip()[:200],
    }
    db.update("media", media_id, changes)
    audit.log("update", "media", media_id, changes["alt"], before=row, after=changes)
    flash("Image details saved.", "ok")
    return redirect(url_for("admin.media"))


@bp.route("/media/<int:media_id>/delete", methods=["POST"])
@require_role("media")
def media_delete(media_id):
    verify_csrf()
    row = media.get(media_id)
    if not row:
        abort(404)
    used = media.usage(media_id)
    if used and not request.form.get("force"):
        flash("That image is still used in " + ", ".join(
            f"{u['kind']} “{u['label']}”" for u in used[:4]) +
            ". Delete it again to remove it anyway.", "error")
        return redirect(url_for("admin.media", used=media_id))
    media.delete_media(media_id)
    audit.log("delete", "media", media_id, row["alt"] or row["filename"] or "", before=row)
    flash("Image deleted.", "ok")
    return redirect(url_for("admin.media"))


@bp.route("/media/picker")
@require_role("media")
def media_picker():
    search = (request.args.get("q") or "").strip()
    rows = media.library(search, limit=120)
    return render_template("admin/_picker.html", rows=rows, search=search)
