"""Media library: uploads, Pillow variants and URL resolution.

Local uploads produce three files:
    <uuid>.<ext>       original, capped at 2400px on the long edge, EXIF dropped
    <uuid>_md.webp     1200px wide, what the page normally serves
    <uuid>_th.webp     480px wide, admin grids and thumbnails

Seed rows carry a `url` instead and are served straight from source.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import current_app, url_for
from PIL import Image, ImageOps

from core import db

ALLOWED = {"jpg", "jpeg", "png", "webp", "gif", "avif", "svg"}
RASTER = ALLOWED - {"svg"}
MAX_LONG_EDGE = 2400
MEDIUM_WIDTH = 1200
THUMB_WIDTH = 480


def upload_dir() -> Path:
    configured = current_app.config.get("UPLOAD_DIR", "static/uploads")
    path = Path(configured)
    if not path.is_absolute():
        path = Path(current_app.root_path) / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ext(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()


def allowed_file(filename: str) -> bool:
    return _ext(filename) in ALLOWED


def save_upload(file_storage, alt: str = "", title: str = "", credit: str = "") -> dict:
    """Store one uploaded file and return the created media row as a dict."""
    original_name = file_storage.filename or "upload"
    ext = _ext(original_name)
    if ext not in ALLOWED:
        raise ValueError(f"{original_name}: only {', '.join(sorted(ALLOWED))} files are accepted")

    stem = uuid.uuid4().hex[:16]
    folder = upload_dir()
    if ext in ("jpg", "jpeg"):
        ext = "jpg"

    target = folder / f"{stem}.{ext}"
    file_storage.save(target)

    if ext == "svg":
        # An SVG is a document, not a bitmap: it can carry script, so it is stored
        # but never inlined, and it gets no raster variants.
        text = target.read_text(encoding="utf-8", errors="ignore").lower()
        if "<script" in text or "javascript:" in text or "onload=" in text:
            target.unlink(missing_ok=True)
            raise ValueError(f"{original_name}: that SVG contains script and was rejected")
        media_id = db.insert("media", {
            "filename": target.name, "medium": None, "thumb": None, "url": None,
            "alt": alt or Path(original_name).stem.replace("-", " "),
            "title": title or Path(original_name).stem,
            "bytes": os.path.getsize(target), "mime": "image/svg+xml",
            "source": "upload", "credit": credit,
        })
        return dict(db.one("SELECT * FROM media WHERE id = ?", (media_id,)))

    # An allowed extension is not proof of an image. Anything Pillow cannot parse
    # is removed rather than left sitting in a web-served folder.
    try:
        with Image.open(target) as probe:
            probe.verify()
    except Exception as exc:  # noqa: BLE001 - any parse failure is a rejection
        target.unlink(missing_ok=True)
        raise ValueError(f"{original_name}: that is not a readable image ({exc})") from exc

    width = height = None
    medium_name = thumb_name = None

    try:
        with Image.open(target) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in ("P", "LA"):
                img = img.convert("RGBA")
            width, height = img.size

            if max(img.size) > MAX_LONG_EDGE:
                img.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.LANCZOS)
                width, height = img.size
                save_img = img.convert("RGB") if ext in ("jpg", "jpeg") else img
                save_img.save(target, quality=88)

            base = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img

            md = base.copy()
            md.thumbnail((MEDIUM_WIDTH, MEDIUM_WIDTH * 3), Image.LANCZOS)
            medium_name = f"{stem}_md.webp"
            md.convert("RGB").save(folder / medium_name, "WEBP", quality=82, method=5)

            th = base.copy()
            th.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 3), Image.LANCZOS)
            thumb_name = f"{stem}_th.webp"
            th.convert("RGB").save(folder / thumb_name, "WEBP", quality=78, method=5)
    except Exception as exc:  # noqa: BLE001 - a bad image should not 500 the upload
        current_app.logger.warning("Could not build variants for %s: %s", original_name, exc)

    media_id = db.insert(
        "media",
        {
            "filename": target.name,
            "medium": medium_name,
            "thumb": thumb_name,
            "url": None,
            "alt": alt or Path(original_name).stem.replace("-", " ").replace("_", " "),
            "title": title or Path(original_name).stem,
            "width": width,
            "height": height,
            "bytes": os.path.getsize(target),
            "mime": f"image/{'jpeg' if ext == 'jpg' else ext}",
            "source": "upload",
            "credit": credit,
        },
    )
    return dict(db.one("SELECT * FROM media WHERE id = ?", (media_id,)))


def add_remote(url: str, alt: str = "", title: str = "", credit: str = "",
               source: str = "remote") -> int:
    return db.insert(
        "media",
        {
            "filename": None, "medium": None, "thumb": None, "url": url,
            "alt": alt, "title": title or alt, "source": source, "credit": credit,
        },
    )


def get(media_id):
    if not media_id:
        return None
    return db.one("SELECT * FROM media WHERE id = ?", (media_id,))


def media_url(row, size: str = "medium", absolute: bool = False) -> str:
    """size: original | medium | thumb

    `absolute` matters for one thing only: og:image is fetched by a crawler that
    has no page to resolve a relative path against, so a share card silently
    breaks without it.
    """
    if row is None:
        return ""
    if isinstance(row, int):
        row = get(row)
        if row is None:
            return ""
    if row["url"]:
        return row["url"]
    if absolute:
        base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
        if not base:
            from flask import request
            base = request.url_root.rstrip("/") if request else ""
        return base + media_url(row, size)
    if size == "thumb":
        name = row["thumb"] or row["medium"] or row["filename"]
    elif size == "medium":
        name = row["medium"] or row["filename"]
    else:
        name = row["filename"] or row["medium"]
    if not name:
        return ""
    folder = current_app.config.get("UPLOAD_DIR", "static/uploads")
    rel = folder.split("static/", 1)[-1] if "static/" in folder else "uploads"
    return url_for("static", filename=f"{rel}/{name}")


def media_path(media_id) -> str:
    """Absolute path of the best local file, for ReportLab to embed."""
    row = get(media_id) if not hasattr(media_id, "keys") else media_id
    if row is None or row["url"]:
        return ""
    name = row["filename"] or row["medium"]
    if not name:
        return ""
    candidate = upload_dir() / name
    return str(candidate) if candidate.exists() else ""


def media_alt(media_id) -> str:
    row = get(media_id) if not hasattr(media_id, "keys") else media_id
    if row is None:
        return ""
    return row["alt"] or row["title"] or ""


def usage(media_id) -> list[dict]:
    """Where a media row is referenced, so delete can warn instead of breaking pages."""
    checks = [
        ("services", "media_id", "name", "Service"),
        ("case_studies", "media_id", "title", "Case study"),
        ("case_studies", "logo_media_id", "title", "Case study logo"),
        ("testimonials", "media_id", "author", "Testimonial"),
        ("posts", "media_id", "title", "Post"),
        ("pages", "og_media_id", "title", "Page social image"),
        ("clients", "logo_media_id", "name", "Client logo"),
        ("expenses", "receipt_media_id", "vendor", "Expense receipt"),
        ("ticket_messages", "media_id", "body", "Ticket attachment"),
    ]
    found = []
    for table, column, label_col, kind in checks:
        if not db.table_exists(table):
            continue
        rows = db.query(
            f"SELECT id, {label_col} AS label FROM {table} WHERE {column} = ?", (media_id,)
        )
        for row in rows:
            found.append({"kind": kind, "id": row["id"], "label": row["label"] or f"#{row['id']}"})

    for row in db.query("SELECT id, page_id, kind, data FROM page_blocks WHERE data LIKE ?",
                        (f'%"media_id": {media_id}%',)):
        found.append({"kind": "Page block", "id": row["id"], "label": row["kind"]})

    for key in ("brand.logo_media_id", "brand.signature_media_id", "seo.og_media_id",
                "invoice.upi_qr_media_id"):
        val = db.scalar("SELECT value FROM settings WHERE key = ?", (key,))
        if val and str(media_id) == str(val).strip('" '):
            found.append({"kind": "Setting", "id": key, "label": key})
    return found


def delete_media(media_id) -> None:
    row = get(media_id)
    if not row:
        return
    folder = upload_dir()
    for name in (row["filename"], row["medium"], row["thumb"]):
        if name:
            try:
                (folder / name).unlink(missing_ok=True)
            except OSError:
                pass
    db.delete("media", media_id)


def library(search: str = "", source: str = "", limit: int = 200):
    sql = "SELECT * FROM media WHERE 1 = 1"
    args: list = []
    if search:
        sql += " AND (alt LIKE ? OR title LIKE ? OR filename LIKE ?)"
        term = f"%{search}%"
        args += [term, term, term]
    if source:
        sql += " AND source = ?"
        args.append(source)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return db.query(sql, args)
