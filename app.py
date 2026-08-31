"""Aruka - agency website plus a single-owner business panel.

    python app.py            run the dev server
    python app.py seed       apply the schema and load the starting rate card
    python app.py reset      delete the database, then seed
    python app.py user       add or update an admin account
    python app.py digest     print today's digest (what a cron would mail)

Lead to cash in one place: the public site captures the lead, the calculator
prices it, the document builder puts it in writing, billing collects it and the
analytics tab shows what was left after costs.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, render_template, request

from core import auth, db, media, settings, util

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = {
    "secret_key": "",           # blank means: generate one and keep it in db/secret.key
    "host": "127.0.0.1",
    "port": 8140,
    "debug": False,             # the Werkzeug debugger is a remote shell; opt in, never default
    "db_path": "db/aruka.db",
    "upload_dir": "static/uploads",
    "max_upload_mb": 16,
    "owner_email": "owner@aruka.local",
    "owner_password": "",       # blank means: generate one and print it once
    "owner_name": "Aruka Owner",
    "public_base_url": "",      # used in share links and PDFs; falls back to the request host
    "https_only": False,        # set true behind TLS so the session cookie is Secure
    "trusted_proxies": 0,       # hops of X-Forwarded-For we put there ourselves
    "vault_key": "",            # blank means: generate one and keep it in db/vault.key
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_tls": True,
    "verify_tls": True,
}


def _keyfile(name: str, label: str) -> str:
    """A per-installation key, generated on first boot and kept out of git.

    Held in a file rather than the database so sessions and the credential vault
    survive a reset, and generated rather than shipped so no two installations
    share a key that would let anyone forge an admin cookie.
    """
    path = ROOT / "db" / name
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(48)
    path.write_text(generated, encoding="utf-8")
    print(f"[config] generated a new {label} in {path.relative_to(ROOT)}")
    return generated


def load_config() -> dict:
    """Defaults, overridden by config.json, overridden by ARUKA_* in the env.

    config.example.json is deliberately not read: a placeholder secret key should
    never become the live one just because nobody copied the file.
    """
    data = dict(DEFAULT_CONFIG)
    path = ROOT / "config.json"
    if path.exists():
        try:
            data.update(json.loads(path.read_text(encoding="utf-8")))
        except ValueError as exc:
            print(f"[config] ignoring config.json: {exc}")
    for key in list(data):
        env = os.environ.get("ARUKA_" + key.upper())
        if env is not None:
            data[key] = env
    return {k: v for k, v in data.items() if not k.startswith("_")}


def create_app() -> Flask:
    cfg = load_config()
    app = Flask(__name__, static_folder="static", template_folder="templates")

    app.secret_key = str(cfg["secret_key"]) or _keyfile("secret.key", "secret key")
    https_only = util.parse_bool(cfg["https_only"])
    app.config.update(
        DB_PATH=cfg["db_path"],
        UPLOAD_DIR=cfg["upload_dir"],
        OWNER_EMAIL=cfg["owner_email"],
        OWNER_PASSWORD=cfg["owner_password"],
        OWNER_NAME=cfg["owner_name"],
        HOST=cfg["host"],
        PORT=int(cfg["port"]),
        PUBLIC_BASE_URL=str(cfg["public_base_url"] or "").rstrip("/"),
        TRUSTED_PROXIES=int(cfg["trusted_proxies"] or 0),
        HTTPS_ONLY=https_only,
        VAULT_KEY=str(cfg["vault_key"] or ""),
        SMTP_HOST=cfg["smtp_host"],
        SMTP_PORT=int(cfg["smtp_port"] or 587),
        SMTP_USER=cfg["smtp_user"],
        SMTP_PASSWORD=cfg["smtp_password"],
        SMTP_FROM=cfg["smtp_from"],
        SMTP_TLS=util.parse_bool(cfg["smtp_tls"]),
        VERIFY_TLS=util.parse_bool(cfg["verify_tls"]),
        MAX_CONTENT_LENGTH=int(cfg["max_upload_mb"]) * 1024 * 1024,
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=https_only,
        TEMPLATES_AUTO_RELOAD=bool(cfg["debug"]),
        JSON_SORT_KEYS=False,
    )

    if util.parse_bool(cfg["debug"]) and str(cfg["host"]) not in ("127.0.0.1", "localhost"):
        print(f"[config] refusing to expose the debugger on {cfg['host']}: debug forced off. "
              "The Werkzeug console executes code for anyone who can reach it.")
        cfg["debug"] = False

    db.init_app(app)
    with app.app_context():
        settings.ensure_defaults()
    auth.bootstrap_owner(app)

    register_jinja(app)
    register_blueprints(app)
    register_headers(app)
    register_errors(app)
    return app


# ── template helpers ────────────────────────────────────────────────────────
def register_jinja(app: Flask) -> None:
    from core import crud, pricing
    from core.tickets import PRIORITY_LABELS, TICKET_STATUS_LABELS
    from core.leads import STAGES, STAGE_LABELS
    from core.billing import INVOICE_STATUS_LABELS, RECURRING_KINDS
    from core.documents import BODY_LABELS
    from core.projects import HEALTH as PROJECT_HEALTH
    from core.projects import STATUSES as PROJECT_STATUSES

    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    app.add_template_filter(util.money, "money")
    app.add_template_filter(util.money2, "money2")
    app.add_template_filter(util.compact_money, "cmoney")
    app.add_template_filter(util.inr, "inr")
    app.add_template_filter(util.pretty_date, "date_fmt")
    app.add_template_filter(util.pretty_datetime, "datetime_fmt")
    app.add_template_filter(util.time_ago, "ago")
    app.add_template_filter(util.truncate, "shorten")
    app.add_template_filter(util.initials, "initials")
    app.add_template_filter(util.split_list, "as_list")
    app.add_template_filter(util.load_json, "from_json")
    app.add_template_filter(util.slugify, "slugify")
    app.add_template_filter(util.days_until, "days_until")
    app.add_template_filter(util.amount_in_words, "in_words")
    app.add_template_filter(util.wa_number, "wa")

    @app.template_filter("paragraphs")
    def paragraphs(value):
        blocks = [b.strip() for b in str(value or "").split("\n\n") if b.strip()]
        return [b.replace("\n", " ") for b in blocks]

    @app.template_filter("bullets")
    def bullets(value):
        """A textarea of one-per-line items, which is how every feature list is edited."""
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value if str(v).strip()]
        return [line.strip().lstrip("-\u2022 ").strip()
                for line in str(value or "").splitlines() if line.strip()]

    # Helpers go in globals rather than a context processor, because a macro
    # imported without "with context" cannot see context values, and every admin
    # form is built out of macros.
    app.jinja_env.globals.update(
        S=settings.get,
        settings_group=settings.group,
        gst_on=settings.gst_on,
        csrf_token=auth.csrf_token,
        current_user=auth.current_user,
        can=auth.can,
        is_owner=auth.is_owner,
        media_url=media.media_url,
        media_alt=media.media_alt,
        media_row=media.get,
        field_value=crud.form_value,
        ROLE_LABELS=auth.ROLE_LABELS,
        STAGES=STAGES,
        STAGE_LABELS=STAGE_LABELS,
        PRIORITY_LABELS=PRIORITY_LABELS,
        TICKET_STATUS_LABELS=TICKET_STATUS_LABELS,
        INVOICE_STATUS_LABELS=INVOICE_STATUS_LABELS,
        RECURRING_KINDS=RECURRING_KINDS,
        BODY_LABELS=BODY_LABELS,
        PROJECT_STATUSES=PROJECT_STATUSES,
        PROJECT_HEALTH=PROJECT_HEALTH,
        ADDON_CATEGORIES=pricing.ADDON_CATEGORIES,
    )

    @app.context_processor
    def inject():
        return {
            "brand": settings.group("brand"),
            "contact": settings.group("contact"),
            "theme": settings.group("theme"),
            "social": settings.group("social"),
            "brand_name": settings.get("brand.name"),
            # Every date input that should default to today reads this rather than
            # each route remembering to pass it.
            "today": util.today_iso(),
            "fy_now": util.fy_label(),
        }

    @app.before_request
    def _touch():
        g.request_path = request.path
        g.csp_nonce = secrets.token_urlsafe(16)

    app.jinja_env.globals["csp_nonce"] = lambda: getattr(g, "csp_nonce", "")


def register_headers(app: Flask) -> None:
    """Headers every response carries.

    Styles stay 'unsafe-inline' because the theme colours are database rows written
    into a <style> block; scripts do not, so the handful of inline blocks in the
    admin templates carry a per-request nonce instead.
    """
    def policy(nonce: str) -> str:
        return (
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self'"
        )

    @app.after_request
    def _headers(response):
        response.headers.setdefault("Content-Security-Policy",
                                    policy(getattr(g, "csp_nonce", "")))
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy",
                                    "geolocation=(), microphone=(), camera=()")
        if app.config.get("HTTPS_ONLY"):
            response.headers.setdefault("Strict-Transport-Security",
                                        "max-age=31536000; includeSubDomains")
        if request.path.startswith(("/admin", "/portal")):
            response.headers["Cache-Control"] = "no-store"
        return response


def register_blueprints(app: Flask) -> None:
    from blueprints.admin import bp as admin_bp
    from blueprints.portal import bp as portal_bp
    from blueprints.public import bp as public_bp
    from blueprints.webhooks import bp as webhooks_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(portal_bp, url_prefix="/portal")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(webhooks_bp)


def register_errors(app: Flask) -> None:
    def _admin_side() -> bool:
        return request.path.startswith(("/admin", "/portal"))

    @app.errorhandler(400)
    def bad_request(exc):
        return render_template("errors/error.html", code=400, title="That request looked wrong",
                               message=getattr(exc, "description", "")), 400

    @app.errorhandler(403)
    def forbidden(exc):
        return render_template("errors/error.html", code=403, title="Not your door",
                               message="Your account does not have access to that page."), 403

    @app.errorhandler(404)
    def not_found(exc):
        if _admin_side():
            return render_template("errors/error.html", code=404, title="Nothing here",
                                   message="That page does not exist."), 404
        from blueprints.public import chrome
        return render_template("errors/404.html", meta=None, nav_here=None, **chrome()), 404

    @app.errorhandler(413)
    def too_large(exc):
        limit = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return render_template("errors/error.html", code=413, title="That file is too big",
                               message=f"Uploads are capped at {limit} MB per file."), 413

    @app.errorhandler(429)
    def too_many(exc):
        return render_template("errors/error.html", code=429, title="Slow down a moment",
                               message=getattr(exc, "description", "Too many requests.")), 429

    @app.errorhandler(500)
    def server_error(exc):
        app.logger.exception("Unhandled error")
        return render_template("errors/error.html", code=500, title="Something broke",
                               message="The error has been logged. Try again."), 500


# ── CLI ─────────────────────────────────────────────────────────────────────
def _cli(argv: list[str]) -> int:
    command = argv[0] if argv else "serve"

    if command == "reset":
        cfg = load_config()
        target = ROOT / cfg["db_path"]
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(target) + suffix)
            if candidate.exists():
                candidate.unlink()
                print(f"[reset] removed {candidate.name}")
        command = "seed"

    if command == "seed":
        app = create_app()
        from db.seed import run as seed_run
        with app.app_context():
            seed_run(force="--force" in argv)
        return 0

    if command == "digest":
        app = create_app()
        from core import notify
        with app.app_context():
            print(notify.digest_text())
        return 0

    if command == "vaultkey":
        app = create_app()
        from core import crypto
        with app.app_context():
            already = crypto.available()
            crypto.encrypt("probe")          # generates the key file if there is none
            path = ROOT / "db" / "vault.key"
            if already:
                print(f"[vault] a key is already in place: {path}")
            else:
                print(f"[vault] wrote a new key to {path}")
            print("[vault] back this file up separately from the database, and never commit it. "
                  "Without it the stored credentials cannot be read - including by you.")
        return 0

    if command == "user":
        app = create_app()
        if len(argv) < 4:
            print("usage: python app.py user <email> <name> <password> [role]")
            return 1
        email, name, password = argv[1], argv[2], argv[3]
        role = argv[4] if len(argv) > 4 else "admin"
        with app.app_context():
            existing = auth.find_user(email)
            if existing:
                db.update("users", existing["id"],
                          {"password_hash": auth.hash_password(password), "role": role,
                           "name": name, "is_active": 1})
                print(f"[user] updated {email} ({role})")
            else:
                auth.create_user(email, name, password, role)
                print(f"[user] created {email} ({role})")
        return 0

    app = create_app()
    host, port = app.config["HOST"], app.config["PORT"]
    debug = load_config()["debug"]
    print(f"  Public site   http://{host}:{port}/")
    print(f"  Client portal http://{host}:{port}/portal")
    print(f"  Admin panel   http://{host}:{port}/admin")
    print(f"  First login   {app.config['OWNER_EMAIL']}")
    app.run(host=host, port=port, debug=debug, threaded=True,
            use_reloader=debug and "--no-reload" not in argv)
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
