"""The client portal.

No client passwords. A contact types their email, gets a six-digit code, and that
code buys a session. Clients forget passwords, reuse them, and share them with
their nephew who "does computers" - a short-lived code avoids all three, and there
is nothing to leak if the database is stolen because only the hash is kept.

Everything here is scoped to one client id held in the session. Every query filters
on it explicitly rather than trusting an id in the URL.
"""

from __future__ import annotations

from functools import wraps

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from core import billing, db, documents, settings, tickets
from core.auth import verify_csrf
from core.util import client_ip, load_json, numeric_code, parse_int, valid_email

bp = Blueprint("portal", __name__, template_folder="../templates")

MAX_ATTEMPTS_PER_IP = 10
MAX_ATTEMPTS_PER_EMAIL = 5
ATTEMPT_WINDOW_MINUTES = 30


# ── session ─────────────────────────────────────────────────────────────────
def current_client():
    if "portal_client" not in g:
        g.portal_client = None
        client_id = session.get("portal_client_id")
        if client_id:
            g.portal_client = db.one(
                "SELECT * FROM clients WHERE id = ? AND is_active = 1", (client_id,))
            if not g.portal_client:
                session.pop("portal_client_id", None)
    return g.portal_client


def client_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not settings.get("portal.enabled"):
            abort(404)
        if not current_client():
            return redirect(url_for("portal.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@bp.context_processor
def _chrome():
    client = current_client()
    counts = {}
    if client:
        counts = {
            "invoices": parse_int(db.scalar(
                "SELECT COUNT(*) FROM invoices WHERE client_id = ? AND status IN "
                "('sent', 'part_paid', 'overdue')", (client["id"],), 0)),
            "documents": parse_int(db.scalar(
                "SELECT COUNT(*) FROM documents WHERE client_id = ? AND status IN "
                "('sent', 'viewed')", (client["id"],), 0)),
            "tickets": parse_int(db.scalar(
                "SELECT COUNT(*) FROM tickets WHERE client_id = ? AND status IN "
                "('open', 'in_progress', 'waiting_client')", (client["id"],), 0)),
        }
    from blueprints.public import wa_link
    return {"client": client, "portal_counts": counts,
            "welcome": settings.get("portal.welcome"),
            "support_email": settings.get("contact.support_email"),
            # The proposal macros are shared with the public share link, and that copy
            # offers WhatsApp before you sign. The portal copy has to offer the same.
            "wa_link": wa_link(),
            "brand_name": settings.get("brand.name")}


# ── sign in ─────────────────────────────────────────────────────────────────
@bp.route("/", methods=["GET"])
def index():
    if not settings.get("portal.enabled"):
        abort(404)
    if current_client():
        return redirect(url_for("portal.dashboard"))
    return redirect(url_for("portal.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not settings.get("portal.enabled"):
        abort(404)
    if current_client():
        return redirect(url_for("portal.dashboard"))

    if request.method == "POST":
        verify_csrf()
        email = (request.form.get("email") or "").strip().lower()

        allowed, message = _throttle(email)
        if not allowed:
            flash(message, "error")
            return redirect(url_for("portal.login"))
        if not valid_email(email):
            flash("That email address does not look right.", "error")
            return redirect(url_for("portal.login"))

        target = _find_contact(email)
        _record_attempt(email, bool(target))

        if target:
            _issue_code(target["client_id"], target.get("contact_id"), email)
        # The same wording either way: whether an address is a client of ours is
        # not something a stranger gets to enumerate.
        session["portal_email"] = email
        flash("If that address is on one of our accounts, a code is on its way to it.", "ok")
        return redirect(url_for("portal.verify"))

    return render_template("portal/login.html", title="Sign in",
                           ttl=parse_int(settings.get("portal.code_ttl_minutes"), 20))


def _find_contact(email: str):
    client = db.one("SELECT id FROM clients WHERE email = ? AND is_active = 1", (email,))
    if client:
        return {"client_id": client["id"], "contact_id": None}
    contact = db.one(
        "SELECT c.id, c.client_id FROM contacts c JOIN clients cl ON cl.id = c.client_id "
        "WHERE c.email = ? AND c.portal_access = 1 AND cl.is_active = 1", (email,))
    if contact:
        return {"client_id": contact["client_id"], "contact_id": contact["id"]}
    return None


def _issue_code(client_id, contact_id, email: str) -> str:
    from core.util import add_minutes
    from services import mailer

    code = numeric_code(6)
    ttl = parse_int(settings.get("portal.code_ttl_minutes"), 20)

    # Only one code is live per address, so an older email cannot still be used.
    db.execute("UPDATE client_logins SET used_at = datetime('now') "
               "WHERE email = ? AND used_at IS NULL", (email,))
    db.insert("client_logins", {
        "client_id": client_id,
        "contact_id": contact_id,
        "email": email,
        "code_hash": generate_password_hash(code, method="pbkdf2:sha256:100000"),
        "expires_at": add_minutes(ttl),
        "ip": client_ip(),
    })

    brand = settings.get("brand.name") or "Aruka"
    result = mailer.send(
        email, f"Your {brand} sign-in code: {code}",
        f"Your code is {code}.\n\nIt works once and expires in {ttl} minutes.\n"
        f"If you did not ask for it, ignore this - nothing has changed on your account.")
    if result.get("skipped"):
        # Email off is a valid setup. The owner reads the code out of the panel and
        # sends it over WhatsApp, which is how most of these calls actually go.
        from core import notify
        client = db.one("SELECT name FROM clients WHERE id = ?", (client_id,))
        notify.push(f"Portal code for {client['name'] if client else email}",
                    f"{email} asked to sign in. Their code is {code} and it expires in "
                    f"{ttl} minutes. Email is off, so send it to them yourself.",
                    kind="warn", url="/admin/settings/email")
    return code


@bp.route("/verify", methods=["GET", "POST"])
def verify():
    if not settings.get("portal.enabled"):
        abort(404)
    email = session.get("portal_email") or ""

    if request.method == "POST":
        verify_csrf()
        email = (request.form.get("email") or email).strip().lower()
        code = (request.form.get("code") or "").strip()

        allowed, message = _throttle(email)
        if not allowed:
            flash(message, "error")
            return redirect(url_for("portal.login"))

        row = db.one(
            "SELECT * FROM client_logins WHERE email = ? AND used_at IS NULL "
            "AND expires_at >= datetime('now') ORDER BY id DESC", (email,))
        if row and code and check_password_hash(row["code_hash"], code):
            db.update("client_logins", row["id"],
                      {"used_at": db.scalar("SELECT datetime('now')")})
            _record_attempt(email, True)
            session.pop("portal_email", None)
            session["portal_client_id"] = row["client_id"]
            session["portal_contact_id"] = row["contact_id"]
            session.permanent = True
            flash("Signed in.", "ok")
            target = request.form.get("next") or ""
            safe = target if target.startswith("/portal") else ""
            return redirect(safe or url_for("portal.dashboard"))

        _record_attempt(email, False)
        flash("That code is wrong or has expired. Ask for a fresh one.", "error")
        return redirect(url_for("portal.verify"))

    return render_template("portal/verify.html", title="Enter your code", email=email,
                           next_url=request.args.get("next", ""))


@bp.route("/logout", methods=["POST"])
def logout():
    verify_csrf()
    session.pop("portal_client_id", None)
    session.pop("portal_contact_id", None)
    flash("Signed out.", "ok")
    return redirect(url_for("portal.login"))


def _throttle(email: str) -> tuple[bool, str]:
    window = f"-{ATTEMPT_WINDOW_MINUTES} minutes"
    by_ip = parse_int(db.scalar(
        "SELECT COUNT(*) FROM portal_attempts WHERE ip = ? AND ok = 0 "
        "AND created_at >= datetime('now', ?)", (client_ip(), window), 0))
    if by_ip >= MAX_ATTEMPTS_PER_IP:
        return False, ("Too many attempts from this connection. Wait half an hour, or "
                       "message us and we will sort it out directly.")
    if email:
        by_email = parse_int(db.scalar(
            "SELECT COUNT(*) FROM portal_attempts WHERE email = ? AND ok = 0 "
            "AND created_at >= datetime('now', ?)", (email, window), 0))
        if by_email >= MAX_ATTEMPTS_PER_EMAIL:
            return False, "Too many attempts for that address. Try again in half an hour."
    return True, ""


def _record_attempt(email: str, ok: bool) -> None:
    db.insert("portal_attempts",
              {"ip": client_ip(), "email": (email or "")[:200], "ok": 1 if ok else 0})


# ── dashboard ───────────────────────────────────────────────────────────────
@bp.route("/home")
@client_required
def dashboard():
    client = current_client()
    projects = db.query(
        "SELECT * FROM projects WHERE client_id = ? AND status NOT IN ('cancelled') "
        "ORDER BY status, id DESC", (client["id"],))
    balance = billing.client_balance(client["id"])
    return render_template(
        "portal/dashboard.html", title="Your account", projects=projects, balance=balance,
        invoices=db.query(
            "SELECT * FROM invoices WHERE client_id = ? AND status != 'draft' "
            "ORDER BY id DESC LIMIT 5", (client["id"],)),
        documents_rows=db.query(
            "SELECT * FROM documents WHERE client_id = ? AND status IN "
            "('sent', 'viewed', 'accepted') ORDER BY id DESC LIMIT 5", (client["id"],)),
        tickets_rows=db.query(
            "SELECT * FROM tickets WHERE client_id = ? ORDER BY id DESC LIMIT 5",
            (client["id"],)),
        assets=db.query(
            "SELECT * FROM assets WHERE client_id = ? AND is_active = 1 "
            "AND expires_on IS NOT NULL ORDER BY expires_on LIMIT 6", (client["id"],)),
        upi=settings.get("invoice.upi_id"))


# ── projects ────────────────────────────────────────────────────────────────
@bp.route("/projects/<int:project_id>")
@client_required
def project(project_id):
    client = current_client()
    row = db.one("SELECT * FROM projects WHERE id = ? AND client_id = ?",
                 (project_id, client["id"]))
    if not row:
        abort(404)
    checklist = db.query(
        "SELECT * FROM launch_checklist WHERE project_id = ? ORDER BY sort_order, id",
        (project_id,))
    return render_template(
        "portal/project.html", title=row["name"], project=row,
        milestones=billing.milestones(project_id),
        checklist=checklist,
        done_steps=len([c for c in checklist if c["is_done"]]),
        invoices=db.query("SELECT * FROM invoices WHERE project_id = ? AND status != 'draft' "
                          "ORDER BY id DESC", (project_id,)),
        tickets_rows=db.query("SELECT * FROM tickets WHERE project_id = ? ORDER BY id DESC",
                              (project_id,)))


# ── money ───────────────────────────────────────────────────────────────────
@bp.route("/invoices")
@client_required
def invoices():
    client = current_client()
    return render_template(
        "portal/invoices.html", title="Invoices",
        rows=db.query("SELECT * FROM invoices WHERE client_id = ? AND status != 'draft' "
                      "ORDER BY id DESC", (client["id"],)),
        payments=db.query("SELECT * FROM payments WHERE client_id = ? AND voided_at IS NULL "
                          "ORDER BY paid_on DESC, id DESC", (client["id"],)),
        credit_notes=db.query("SELECT * FROM credit_notes WHERE client_id = ? ORDER BY id DESC",
                              (client["id"],)),
        balance=billing.client_balance(client["id"]),
        upi=settings.get("invoice.upi_id"),
        bank={"name": settings.get("invoice.bank_name"),
              "account_name": settings.get("invoice.bank_account_name"),
              "account_no": settings.get("invoice.bank_account_no"),
              "ifsc": settings.get("invoice.bank_ifsc")})


@bp.route("/invoices/<int:invoice_id>.pdf")
@client_required
def invoice_pdf(invoice_id):
    client = current_client()
    invoice = db.one("SELECT * FROM invoices WHERE id = ? AND client_id = ? AND status != 'draft'",
                     (invoice_id, client["id"]))
    if not invoice:
        abort(404)
    from services import pdf
    return Response(pdf.invoice_pdf(invoice), mimetype="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{invoice["ref"]}.pdf"',
        "Cache-Control": "no-store"})


@bp.route("/receipts/<int:payment_id>.pdf")
@client_required
def receipt_pdf(payment_id):
    client = current_client()
    payment = db.one("SELECT * FROM payments WHERE id = ? AND client_id = ? AND voided_at IS NULL",
                     (payment_id, client["id"]))
    if not payment:
        abort(404)
    from services import pdf
    return Response(pdf.receipt_pdf(payment), mimetype="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{payment["ref"]}.pdf"',
        "Cache-Control": "no-store"})


# ── documents ───────────────────────────────────────────────────────────────
@bp.route("/documents")
@client_required
def documents_list():
    client = current_client()
    return render_template(
        "portal/documents.html", title="Documents",
        rows=db.query("SELECT * FROM documents WHERE client_id = ? AND status != 'draft' "
                      "ORDER BY id DESC", (client["id"],)),
        shares={r["document_id"]: r["token"] for r in db.query(
            "SELECT document_id, token FROM document_shares WHERE revoked_at IS NULL")})


@bp.route("/documents/<int:document_id>", methods=["GET", "POST"])
@client_required
def document(document_id):
    client = current_client()
    row = db.one("SELECT * FROM documents WHERE id = ? AND client_id = ? AND status != 'draft'",
                 (document_id, client["id"]))
    if not row:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        name = (request.form.get("name") or "").strip()
        if len(name) < 2:
            flash("Type your full name to sign.", "error")
            return redirect(url_for("portal.document", document_id=document_id))
        note = (request.form.get("note") or "").strip()
        if request.form.get("action") == "accept":
            if not request.form.get("agree"):
                flash("Tick the box confirming you have read the terms.", "error")
                return redirect(url_for("portal.document", document_id=document_id))
            documents.accept(document_id, name=name, ip=client_ip(), note=note)
            flash("Accepted. Thank you - we will get moving.", "ok")
        else:
            documents.decline(document_id, name=name, note=note, ip=client_ip())
            flash("Recorded. Thank you for letting us know.", "ok")
        return redirect(url_for("portal.document", document_id=document_id))

    documents.record_view(document_id, None, client_ip(),
                          request.headers.get("User-Agent", ""))
    body = load_json(row["body_json"], {})
    from core import pricing
    return render_template(
        "portal/document.html", title=row["title"], document=row, body=body,
        clauses=[c for c in documents.clauses_for(row["kind"], active_only=False)
                 if c["id"] in set(body.get("clause_ids") or [])],
        quote=pricing.quote_summary(row["quote_id"]) if row["quote_id"] else None)


@bp.route("/documents/<int:document_id>.pdf")
@client_required
def document_pdf(document_id):
    client = current_client()
    row = db.one("SELECT * FROM documents WHERE id = ? AND client_id = ? AND status != 'draft'",
                 (document_id, client["id"]))
    if not row:
        abort(404)
    from services import pdf
    return Response(pdf.proposal_pdf(row), mimetype="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{row["ref"]}.pdf"',
        "Cache-Control": "no-store"})


# ── support ─────────────────────────────────────────────────────────────────
@bp.route("/tickets")
@client_required
def tickets_list():
    client = current_client()
    rows = db.query("SELECT * FROM tickets WHERE client_id = ? ORDER BY id DESC",
                    (client["id"],))
    return render_template(
        "portal/tickets.html", title="Support", rows=rows,
        statuses=tickets.TICKET_STATUS_LABELS, priorities=tickets.PRIORITY_LABELS,
        policies={p: tickets.policy(p) for p in tickets.PRIORITIES},
        categories=tickets.CATEGORIES)


@bp.route("/tickets/new", methods=["GET", "POST"])
@client_required
def ticket_new():
    client = current_client()

    if request.method == "POST":
        verify_csrf()
        subject = (request.form.get("subject") or "").strip()
        if not subject:
            flash("What is it about?", "error")
            return redirect(url_for("portal.ticket_new"))

        contact = db.one("SELECT * FROM contacts WHERE id = ?",
                         (session.get("portal_contact_id"),)) \
            if session.get("portal_contact_id") else None
        change_request = bool(request.form.get("is_change_request"))

        ticket_id = tickets.create({
            "client_id": client["id"],
            "project_id": parse_int(request.form.get("project_id"), 0) or None,
            "contact_name": (contact["name"] if contact else client["contact_name"]) or client["name"],
            "contact_email": (contact["email"] if contact else client["email"]) or "",
            "contact_phone": (contact["phone"] if contact else client["phone"]) or "",
            "subject": subject,
            "body": (request.form.get("body") or "").strip(),
            "category": request.form.get("category") or "other",
            "priority": request.form.get("priority") or "p3",
            "is_change_request": change_request,
            "ip": client_ip(),
        }, source="portal")

        ticket = tickets.get(ticket_id)
        from core import notify
        notify.push(f"{client['name']} raised {ticket['ref']}", subject,
                    kind="warn" if ticket["priority"] in ("p1", "p2") else "info",
                    url=f"/admin/tickets/{ticket_id}", entity="ticket", entity_id=ticket_id)
        flash(f"Logged as {ticket['ref']}. We aim to reply within "
              f"{tickets.policy(ticket['priority'])['response_hours']:.0f} hours.", "ok")
        return redirect(url_for("portal.ticket", ticket_id=ticket_id))

    return render_template(
        "portal/ticket_form.html", title="Raise a request",
        projects=db.query("SELECT id, ref, name FROM projects WHERE client_id = ? "
                          "AND status NOT IN ('cancelled', 'closed') ORDER BY id DESC",
                          (client["id"],)),
        categories=tickets.CATEGORIES, priorities=tickets.PRIORITY_LABELS,
        policies={p: tickets.policy(p) for p in tickets.PRIORITIES},
        intro=settings.get("ticket.intro"))


@bp.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
@client_required
def ticket(ticket_id):
    client = current_client()
    row = db.one("SELECT * FROM tickets WHERE id = ? AND client_id = ?",
                 (ticket_id, client["id"]))
    if not row:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Write something first.", "error")
            return redirect(url_for("portal.ticket", ticket_id=ticket_id))
        contact = db.one("SELECT * FROM contacts WHERE id = ?",
                         (session.get("portal_contact_id"),)) \
            if session.get("portal_contact_id") else None
        tickets.reply(ticket_id, body, author_kind="client",
                      author_name=(contact["name"] if contact else client["contact_name"])
                      or client["name"])
        from core import notify
        notify.push(f"Reply on {row['ref']}", body[:200], kind="info",
                    url=f"/admin/tickets/{ticket_id}", entity="ticket", entity_id=ticket_id)
        flash("Added. We will pick it up from there.", "ok")
        return redirect(url_for("portal.ticket", ticket_id=ticket_id))

    return render_template(
        "portal/ticket.html", title=row["ref"], ticket=row,
        thread=tickets.messages(ticket_id, include_internal=False),
        state=tickets.sla_state(row),
        statuses=tickets.TICKET_STATUS_LABELS, priorities=tickets.PRIORITY_LABELS,
        categories=tickets.CATEGORIES)


@bp.route("/tickets/<int:ticket_id>/close", methods=["POST"])
@client_required
def ticket_close(ticket_id):
    client = current_client()
    verify_csrf()
    row = db.one("SELECT * FROM tickets WHERE id = ? AND client_id = ?",
                 (ticket_id, client["id"]))
    if not row:
        abort(404)
    tickets.set_status(ticket_id, "closed", "Closed by the client from the portal.")
    flash("Closed. Thank you for confirming.", "ok")
    return redirect(url_for("portal.tickets_list"))
