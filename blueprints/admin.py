"""The admin panel shell: sign-in, dashboard, global search, notifications,
settings, the onboarding wizard, activity log and backup.

Every feature area lives in its own module and attaches to this blueprint, which
is imported at the bottom of the file so `bp` exists before they reach for it.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, send_file, session, url_for)

from core import audit, auth, billing, db, leads, notify, settings, tickets
from core.auth import login_required, require_role, verify_csrf
from core.util import (client_ip, fy_bounds, month_bounds, parse_bool, parse_float,
                       parse_int, valid_email)

bp = Blueprint("admin", __name__, template_folder="../templates")

# (group label, [(endpoint, label, icon, permission area)])
NAV_GROUPS = [
    ("Overview", [
        ("admin.dashboard", "Dashboard", "grid", None),
        ("admin.analytics", "Analytics", "chart", "analytics"),
    ]),
    ("Sell", [
        ("admin.leads_board", "Pipeline", "board", "leads"),
        ("admin.leads_list", "Leads", "funnel", "leads"),
        ("admin.quotes_list", "Quotes", "calc", "pricing"),
        ("admin.documents_list", "Documents", "doc", "documents"),
        ("admin.wa_log", "Messages", "chat", "messages"),
    ]),
    ("Deliver", [
        ("admin.clients_list", "Clients", "briefcase", "billing"),
        ("admin.projects_list", "Projects", "rocket", "projects"),
        ("admin.tickets_list", "Support", "life", "tickets"),
        ("admin.renewals", "Renewals", "calendar", "billing"),
        ("admin.vault", "Assets and vault", "key", "vault"),
    ]),
    ("Money", [
        ("admin.invoices_list", "Invoices", "wallet", "billing"),
        ("admin.payments_list", "Payments", "receipt", "billing"),
        ("admin.expenses_list", "Expenses", "coins", "analytics"),
        ("admin.recurring_list", "Recurring", "refresh", "billing"),
        ("admin.referrals", "Referrals", "gift", "billing"),
    ]),
    ("Rate card", [
        ("admin.packages_list", "Packages", "tag", "pricing"),
        ("admin.addons_list", "Add-ons", "plus", "pricing"),
        ("admin.pricing_rules_list", "Pricing rules", "sliders", "pricing"),
        ("admin.clauses_list", "Clause library", "shield", "documents"),
    ]),
    ("Website", [
        ("admin.pages_list", "Pages", "layout", "content"),
        ("admin.services_list", "Services", "spark", "content"),
        ("admin.work_list", "Case studies", "star", "content"),
        ("admin.testimonials_list", "Testimonials", "quote", "content"),
        ("admin.faqs_list", "FAQs", "help", "content"),
        ("admin.posts_list", "Insights", "note", "content"),
        ("admin.legal_list", "Legal pages", "shield", "content"),
        ("admin.nav_list", "Navigation", "list", "content"),
        ("admin.stats_list", "Stats and marquee", "trend", "content"),
        ("admin.media", "Media", "image", "media"),
        ("admin.seo", "SEO checklist", "globe", "content"),
    ]),
    ("Setup", [
        ("admin.settings_view", "Settings", "sliders", "settings"),
        ("admin.wa_templates_list", "WhatsApp templates", "chat", "messages"),
        ("admin.email_templates_list", "Email templates", "mail", "messages"),
        ("admin.sla_list", "SLA policies", "clock", "tickets"),
        ("admin.sources_list", "Lead sources", "funnel", "settings"),
        ("admin.categories_list", "Expense categories", "coins", "settings"),
        ("admin.subscriptions_list", "Our subscriptions", "refresh", "analytics"),
        ("admin.users_list", "Team", "users", "users"),
        ("admin.audit", "Activity log", "list", "audit"),
        ("admin.backup", "Backup and restore", "database", "settings"),
    ]),
]


@bp.context_processor
def _shell():
    """Everything the admin chrome needs, on every admin page."""
    user = auth.current_user()
    if not user:
        return {"admin_user": None, "nav_groups": [], "counts": {}, "onboarded": True}
    return {
        "admin_user": user,
        "nav_groups": NAV_GROUPS,
        "counts": _badge_counts(),
        "onboarded": settings.get("ops.onboarded", False),
    }


def _badge_counts() -> dict:
    due = leads.followups_due()
    late = leads.followups_overdue()
    live = tickets.search(status="live", limit=500)
    flagged = [t for t in live if tickets.sla_state(t)["state"] in ("at_risk", "breached")]
    overdue = parse_int(db.scalar(
        "SELECT COUNT(*) FROM invoices WHERE status = 'overdue'", (), 0))
    return {
        "followups": len(due),
        "followups_late": len(late),
        "tickets": len(live),
        "tickets_sla": len(flagged),
        "overdue": overdue,
        "notifications": notify.unread_count(),
    }


# ── sign in ─────────────────────────────────────────────────────────────────
@bp.route("/login", methods=["GET", "POST"])
def login():
    if auth.current_user():
        return redirect(url_for("admin.dashboard"))

    next_url = request.args.get("next") or request.form.get("next") or ""
    email = ""
    if request.method == "POST":
        verify_csrf()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        user, error = auth.attempt_login(email, password, client_ip())
        if error:
            flash(error, "error")
        else:
            audit.log("login", "users", user["id"], user["email"])
            # Only local paths, so a crafted ?next= cannot bounce a signed-in
            # owner onto someone else's site with a fresh session.
            target = next_url if next_url.startswith("/") and not next_url.startswith("//") else ""
            return redirect(target or url_for("admin.dashboard"))

    return render_template("admin/login.html", title="Sign in", next_url=next_url, email=email)


@bp.route("/logout", methods=["POST"])
def logout():
    verify_csrf()
    user = auth.current_user()
    if user:
        audit.log("logout", "users", user["id"], user["email"])
    auth.logout()
    flash("Signed out.", "ok")
    return redirect(url_for("admin.login"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = auth.current_user()
    if request.method == "POST":
        verify_csrf()
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""

        if not valid_email(email):
            flash("That email does not look right.", "error")
        elif email != user["email"] and auth.find_user(email):
            flash("Another account already uses that email.", "error")
        else:
            changes = {"name": name or user["name"], "email": email}
            if new:
                from werkzeug.security import check_password_hash
                if not check_password_hash(user["password_hash"], current):
                    flash("Your current password did not match.", "error")
                    return redirect(url_for("admin.account"))
                if len(new) < 10:
                    flash("Use at least 10 characters for the new password.", "error")
                    return redirect(url_for("admin.account"))
                changes["password_hash"] = auth.hash_password(new)
            db.update("users", user["id"], changes)
            audit.log("update", "users", user["id"], email, after={"name": changes["name"]})
            flash("Account updated." + (" Sign in again with the new password."
                                        if "password_hash" in changes else ""), "ok")
            if "password_hash" in changes:
                auth.logout()
                return redirect(url_for("admin.login"))
            return redirect(url_for("admin.account"))

    return render_template("admin/account.html", title="Your account", user=user)


# ── dashboard ───────────────────────────────────────────────────────────────
@bp.route("/")
@login_required
def dashboard():
    digest = notify.digest()
    fy_since, fy_until = fy_bounds()
    m_since, m_until = month_bounds()

    pipeline = leads.pipeline_forecast()
    collected_month = billing.collected_between(m_since, m_until)
    spent_month = billing.spent_between(m_since, m_until)
    collected_fy = billing.collected_between(fy_since, fy_until)
    spent_fy = billing.spent_between(fy_since, fy_until)

    active_projects = db.query(
        "SELECT p.*, c.name AS client_name FROM projects p JOIN clients c ON c.id = p.client_id "
        "WHERE p.status IN ('planned', 'active') ORDER BY p.target_on IS NULL, p.target_on LIMIT 8")

    return render_template(
        "admin/dashboard.html",
        title="Dashboard",
        digest=digest,
        pipeline=pipeline,
        collected_month=collected_month,
        spent_month=spent_month,
        net_month=collected_month - spent_month,
        collected_fy=collected_fy,
        spent_fy=spent_fy,
        mrr=digest["mrr"],
        active_projects=active_projects,
        recent_leads=leads.search(limit=6),
        activity=audit.recent(12),
        lead_stats=leads.headline(fy_since, fy_until),
        ticket_stats=tickets.stats(fy_since, fy_until),
    )


# ── notifications ───────────────────────────────────────────────────────────
@bp.route("/notifications", methods=["GET", "POST"])
@login_required
def notifications():
    if request.method == "POST":
        verify_csrf()
        action = request.form.get("action")
        if action == "read_all":
            notify.mark_read()
            flash("All notifications marked read.", "ok")
        elif action == "sweep":
            result = notify.sweep()
            flash(f"Digest run: {result['created']} new notification(s).", "ok")
        return redirect(url_for("admin.notifications"))

    return render_template("admin/notifications.html", title="Notifications",
                           rows=notify.recent(80), digest_text=notify.digest_text())


@bp.route("/notifications/<int:row_id>/read", methods=["POST"])
@login_required
def notification_read(row_id):
    verify_csrf()
    notify.mark_read(row_id)
    row = db.one("SELECT * FROM notifications WHERE id = ?", (row_id,))
    return redirect(row["url"] if row and row["url"] else url_for("admin.notifications"))


# ── global search ───────────────────────────────────────────────────────────
@bp.route("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    results = {"leads": [], "clients": [], "projects": [], "invoices": [],
               "tickets": [], "documents": [], "quotes": []}
    if len(q) >= 2:
        like = f"%{q}%"
        results["leads"] = db.query(
            "SELECT * FROM leads WHERE name LIKE ? OR company LIKE ? OR email LIKE ? "
            "OR phone LIKE ? OR ref LIKE ? ORDER BY id DESC LIMIT 12", [like] * 5)
        results["clients"] = db.query(
            "SELECT * FROM clients WHERE name LIKE ? OR contact_name LIKE ? OR email LIKE ? "
            "OR ref LIKE ? OR gstin LIKE ? ORDER BY id DESC LIMIT 12", [like] * 5)
        results["projects"] = db.query(
            "SELECT p.*, c.name AS client_name FROM projects p JOIN clients c ON c.id = p.client_id "
            "WHERE p.name LIKE ? OR p.ref LIKE ? ORDER BY p.id DESC LIMIT 12", [like] * 2)
        results["invoices"] = db.query(
            "SELECT i.*, c.name AS client_name FROM invoices i JOIN clients c ON c.id = i.client_id "
            "WHERE i.ref LIKE ? OR c.name LIKE ? ORDER BY i.id DESC LIMIT 12", [like] * 2)
        results["tickets"] = db.query(
            "SELECT t.*, c.name AS client_name FROM tickets t LEFT JOIN clients c ON c.id = t.client_id "
            "WHERE t.ref LIKE ? OR t.subject LIKE ? OR t.contact_email LIKE ? "
            "ORDER BY t.id DESC LIMIT 12", [like] * 3)
        results["documents"] = db.query(
            "SELECT * FROM documents WHERE ref LIKE ? OR title LIKE ? "
            "ORDER BY id DESC LIMIT 12", [like] * 2)
        results["quotes"] = db.query(
            "SELECT * FROM quotes WHERE ref LIKE ? OR title LIKE ? "
            "ORDER BY id DESC LIMIT 12", [like] * 2)
    total = sum(len(v) for v in results.values())
    return render_template("admin/search.html", title="Search", q=q, results=results, total=total)


# ── onboarding wizard ───────────────────────────────────────────────────────
WIZARD_STEPS = [
    ("brand", "Brand"),
    ("contact", "Contact"),
    ("money", "Getting paid"),
    ("legal", "Legal and tax"),
    ("pricing", "Your floor price"),
]

WIZARD_FIELDS = {
    "brand": [
        ("brand.name", "Studio name", "text", "The name on every document and invoice."),
        ("brand.legal_name", "Legal or trading name", "text",
         "As registered, if different. This is what appears on invoices."),
        ("brand.tagline", "Tagline", "text", "One line, used on the home page."),
        ("brand.promise", "Promise", "textarea", "The sentence under your headline."),
        ("brand.city", "City", "text", ""),
        ("brand.state", "State", "text", ""),
        ("brand.logo_media_id", "Logo", "media", "Upload it in Media first if you have not."),
    ],
    "contact": [
        ("contact.phone", "Phone", "tel", ""),
        ("contact.whatsapp", "WhatsApp number", "tel",
         "Digits with country code, for example 919000000000. Every WhatsApp link uses this."),
        ("contact.email", "Enquiry email", "email", ""),
        ("contact.support_email", "Support email", "email", ""),
        ("contact.address", "Address", "textarea", "Shown on invoices and in the footer."),
        ("contact.hours_note", "Working hours", "text", ""),
    ],
    "money": [
        ("invoice.prefix", "Invoice prefix", "text",
         "Three letters. Numbers read ARK/INV/2026-27/001."),
        ("invoice.upi_id", "UPI ID", "text", "Printed on every invoice PDF."),
        ("invoice.upi_qr_media_id", "UPI QR image", "media",
         "Upload the QR from your UPI app; it is embedded in the invoice."),
        ("invoice.bank_name", "Bank", "text", ""),
        ("invoice.bank_account_name", "Account name", "text", ""),
        ("invoice.bank_account_no", "Account number", "text", ""),
        ("invoice.bank_ifsc", "IFSC", "text", ""),
        ("invoice.terms_days", "Payment terms, days", "int", "Due date is this many days after issue."),
    ],
    "legal": [
        ("gst.mode", "Invoice mode", "select",
         "Bill of supply until your GST registration comes through. Switching to tax "
         "invoice turns on HSN/SAC, place of supply and the CGST/SGST/IGST split."),
        ("gst.gstin", "GSTIN", "text", "Leave blank if you are not registered."),
        ("gst.state_code", "Your state code", "text",
         "First two digits of your GSTIN. 27 is Maharashtra. Decides intra vs inter-state tax."),
        ("tax.pan", "PAN", "text", "Clients need this to deduct TDS correctly."),
        ("doc.jurisdiction_city", "Jurisdiction city", "text",
         "Courts of this city get exclusive jurisdiction in your contracts."),
        ("doc.arbitration_seat", "Arbitration seat", "text", ""),
        ("doc.signatory_name", "Who signs", "text", ""),
        ("doc.signatory_title", "Their title", "text", ""),
        ("brand.signature_media_id", "Signature image", "media",
         "A transparent PNG of your signature, placed on documents."),
    ],
    "pricing": [
        ("pricing.extra_page_rate", "Per extra page", "money", ""),
        ("pricing.rush_pct", "Rush surcharge, percent", "number", ""),
        ("pricing.annual_prepay_discount_pct", "Annual prepay discount, percent", "number", ""),
        ("pricing.referral_discount_pct", "Referral discount, percent", "number", ""),
        ("pricing.rounding", "Round totals to", "int", "100 gives prices ending in 00."),
        ("ticket.default_rate_per_hour", "Support rate per hour", "money",
         "Used when a ticket turns into a billable change request."),
    ],
}

SELECT_OPTIONS = {
    "gst.mode": [("bill_of_supply", "Bill of supply (not GST registered)"),
                 ("tax_invoice", "Tax invoice (GST registered)")],
}


@bp.route("/setup", methods=["GET", "POST"])
@bp.route("/setup/<step>", methods=["GET", "POST"])
@require_role("settings")
def onboarding(step: str = "brand"):
    keys = [k for k, _l in WIZARD_STEPS]
    if step not in keys:
        abort(404)
    index = keys.index(step)

    if request.method == "POST":
        verify_csrf()
        for key, _label, kind, _help in WIZARD_FIELDS[step]:
            raw = request.form.get(key)
            if raw is None:
                continue
            if kind in ("money", "number"):
                settings.set(key, parse_float(raw, 0))
            elif kind == "int":
                settings.set(key, parse_int(raw, 0))
            elif kind == "media":
                settings.set(key, parse_int(raw, 0) or None)
            else:
                settings.set(key, raw.strip())
        audit.log("update", "settings", step, f"setup step: {step}")

        if index + 1 < len(keys):
            return redirect(url_for("admin.onboarding", step=keys[index + 1]))
        settings.set("ops.onboarded", True)
        flash("Setup complete. Your details are now on every document and invoice.", "ok")
        return redirect(url_for("admin.dashboard"))

    fields = []
    for key, label, kind, help_text in WIZARD_FIELDS[step]:
        fields.append({"key": key, "label": label, "kind": kind, "help": help_text,
                       "value": settings.get(key), "options": SELECT_OPTIONS.get(key, [])})
    return render_template("admin/onboarding.html", title="Setup", step=step, index=index,
                           steps=WIZARD_STEPS, fields=fields,
                           next_label=(WIZARD_STEPS[index + 1][1] if index + 1 < len(WIZARD_STEPS) else ""))


# ── activity log ────────────────────────────────────────────────────────────
@bp.route("/audit", endpoint="audit")
@require_role("audit")
def audit_view():
    entity = (request.args.get("entity") or "").strip()
    action = (request.args.get("action") or "").strip()
    sql = "SELECT * FROM audit_log WHERE 1 = 1"
    args: list = []
    if entity:
        sql += " AND entity = ?"
        args.append(entity)
    if action:
        sql += " AND action = ?"
        args.append(action)
    sql += " ORDER BY id DESC LIMIT 300"
    rows = db.query(sql, args)
    entities = db.query("SELECT DISTINCT entity FROM audit_log ORDER BY entity")
    actions = db.query("SELECT DISTINCT action FROM audit_log ORDER BY action")
    return render_template("admin/audit.html", title="Activity log", rows=rows,
                           entities=entities, actions=actions, entity=entity, action=action)


# ── backup and restore ──────────────────────────────────────────────────────
@bp.route("/backup", methods=["GET", "POST"])
@require_role("settings")
def backup():
    from core import crypto  # noqa: F401 - imported so the key file exists before a backup

    if request.method == "POST":
        verify_csrf()
        action = request.form.get("action")
        if action == "restore":
            return _restore()
        return redirect(url_for("admin.backup"))

    counts = {}
    for table in ("leads", "clients", "projects", "quotes", "documents", "invoices",
                  "payments", "expenses", "tickets", "messages", "media"):
        counts[table] = parse_int(db.scalar(f"SELECT COUNT(*) FROM {table}", (), 0))
    return render_template("admin/backup.html", title="Backup and restore",
                           counts=counts, db_bytes=db.db_file_size(),
                           backups=_backup_files())


def _backup_dir() -> Path:
    path = Path(current_app.root_path) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _backup_files():
    out = []
    for path in sorted(_backup_dir().glob("aruka-backup-*.zip"), reverse=True):
        stat = path.stat()
        out.append({"name": path.name, "bytes": stat.st_size,
                    "when": datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y, %H:%M")})
    return out[:20]


@bp.route("/backup/download")
@require_role("settings")
def backup_download():
    """A zip of the database plus uploads, streamed rather than written to disk.

    sqlite3's own backup API is used instead of copying the file, because a plain
    copy of a WAL database while it is being written can land mid-transaction.
    """
    import sqlite3
    import tempfile

    keep = parse_bool(request.args.get("keep"))
    buffer = io.BytesIO()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "aruka.db"
        source = db.connect(db.db_file_path())
        target = sqlite3.connect(str(snapshot))
        with target:
            source.backup(target)
        target.close()
        source.close()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot, "db/aruka.db")
            uploads = Path(current_app.root_path) / current_app.config["UPLOAD_DIR"]
            if uploads.exists():
                for item in uploads.rglob("*"):
                    if item.is_file():
                        zf.write(item, f"uploads/{item.relative_to(uploads)}")
            zf.writestr("manifest.json", json.dumps({
                "app": "aruka",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "schema_version": db.scalar("SELECT value FROM meta WHERE key = 'schema_version'"),
                "counts": {t: parse_int(db.scalar(f"SELECT COUNT(*) FROM {t}", (), 0))
                           for t in ("leads", "clients", "invoices", "payments", "tickets")},
                "note": "Restore replaces the live database. The secret and vault keys are "
                        "NOT in this file - back up db/secret.key and db/vault.key separately, "
                        "or encrypted credentials will not decrypt after a restore.",
            }, indent=2))

    buffer.seek(0)
    name = f"aruka-backup-{stamp}.zip"
    if keep:
        (_backup_dir() / name).write_bytes(buffer.getvalue())
        buffer.seek(0)
    audit.log("export", "backup", "", name)
    return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=name)


def _restore():
    upload = request.files.get("archive")
    if not upload or not upload.filename.lower().endswith(".zip"):
        flash("Choose a .zip backup produced by this app.", "error")
        return redirect(url_for("admin.backup"))
    if (request.form.get("confirm") or "").strip().upper() != "REPLACE":
        flash("Type REPLACE to confirm - restoring overwrites everything currently here.", "error")
        return redirect(url_for("admin.backup"))

    try:
        payload = io.BytesIO(upload.read())
        with zipfile.ZipFile(payload) as zf:
            names = zf.namelist()
            if "db/aruka.db" not in names:
                flash("That zip has no db/aruka.db - it is not an Aruka backup.", "error")
                return redirect(url_for("admin.backup"))

            # Keep a copy of what is being replaced, so a restore of the wrong file
            # is recoverable rather than terminal.
            safety = _backup_dir() / f"pre-restore-{datetime.now():%Y%m%d-%H%M%S}.db"
            Path(db.db_file_path()).replace(safety)

            db.close_db()
            Path(db.db_file_path()).write_bytes(zf.read("db/aruka.db"))
            for suffix in ("-wal", "-shm"):
                stale = Path(str(db.db_file_path()) + suffix)
                stale.unlink(missing_ok=True)

            uploads = Path(current_app.root_path) / current_app.config["UPLOAD_DIR"]
            uploads.mkdir(parents=True, exist_ok=True)
            for name in names:
                if not name.startswith("uploads/") or name.endswith("/"):
                    continue
                relative = Path(name).relative_to("uploads")
                if ".." in relative.parts or relative.is_absolute():
                    continue          # zip-slip guard
                destination = uploads / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(zf.read(name))
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        flash(f"Restore failed: {exc}", "error")
        return redirect(url_for("admin.backup"))

    session.clear()
    flash("Restored. Sign in again - the accounts are the ones from the backup.", "ok")
    return redirect(url_for("admin.login"))


@bp.route("/backup/keep", methods=["POST"])
@require_role("settings")
def backup_keep():
    verify_csrf()
    return redirect(url_for("admin.backup_download", keep=1))


# Feature modules attach their routes to `bp`; imported last so `bp` exists.
from blueprints import (admin_analytics, admin_billing, admin_content,  # noqa: E402,F401
                        admin_documents, admin_leads, admin_media, admin_messages,
                        admin_pricing, admin_projects, admin_settings, admin_tickets)
