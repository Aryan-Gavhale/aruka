"""WhatsApp: template library, composer, message log, bulk queue and opt-outs.

Routes hang off the shared admin blueprint so `crud.register` keeps producing
`admin.*` endpoints and the nav stays one namespace.
"""

from __future__ import annotations

import secrets

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from blueprints.admin import bp
from core import audit, crud, db, settings
from core.auth import require_role, verify_csrf
from core.crud import Field, Resource
from core.leads import STAGE_LABELS
from core.util import parse_int, template_vars, wa_number
from services import whatsapp

SEND_LIMIT_PER_RUN = 40


def _template_code(data: dict, existing) -> None:
    """Give a hand-made template a stable code without asking for one.

    Seeded templates are looked up by code from the send helpers, so the column has
    to be filled and unique - but a code is a machine detail and no one should have
    to invent one while writing a message.
    """
    if existing and existing["code"]:
        return
    from core.util import slugify
    base = slugify(data.get("name") or "template") or "template"
    code = base
    while db.one("SELECT 1 FROM message_templates WHERE code = ?", (code,)):
        code = f"{base}-{secrets.token_hex(2)}"
    data["code"] = code

VARIABLE_HELP = (
    "Placeholders: {{ name }}, {{ full_name }}, {{ company }}, {{ brand }}, {{ service }}, "
    "{{ ref }}, {{ project }}, {{ invoice_no }}, {{ amount }}, {{ balance }}, {{ due_date }}, "
    "{{ upi }}, {{ document_no }}, {{ link }}, {{ ticket_ref }}, {{ subject }}, {{ status }}, "
    "{{ phone }}, {{ email }}, {{ site }}, {{ support_link }}, {{ sender }}. "
    "A placeholder with no value stays visible, so a half-filled message is obvious "
    "before you send it rather than after."
)


# ── template library ────────────────────────────────────────────────────────
WA_TEMPLATES = Resource(
    key="wa_templates", table="message_templates",
    label="WhatsApp template", label_plural="WhatsApp templates",
    area="messages", row_label="name", icon="whatsapp", sortable=True, activatable=True,
    searchable=("name", "body"),
    base_where="channel = 'whatsapp'",
    defaults={"channel": "whatsapp"},
    before_save=_template_code,
    intro="The messages you send again and again. Everything here is editable, and the "
          "composer fills the placeholders from whichever lead, invoice or ticket you "
          "opened it from.",
    list_columns=[("name", "Template"), ("category", "Category"), ("body", "Message")],
    fields=[
        Field("name", "Name", "text", required=True, span=7,
              help="Only you see this. Something like 'First reply - website enquiry'."),
        Field("category", "Category", "select", span=5,
              options=list(whatsapp.TEMPLATE_CATEGORIES.items()), default="followup"),
        Field("body", "Message", "textarea", rows=9, required=True, span=12, help=VARIABLE_HELP),
        Field("cloud_head", "Cloud API", "heading",
              help="Only relevant once you switch the provider to the Meta Cloud API."),
        Field("cloud_template_name", "Approved template name", "text", span=6,
              help="Meta only allows a free-form message inside 24 hours of the contact's "
                   "last reply. Outside that window it has to be a template they approved, "
                   "and this is its name on their side."),
        Field("is_active", "Active", "bool", span=6, default=1),
    ],
)

EMAIL_TEMPLATES = Resource(
    key="email_templates", table="message_templates",
    label="Email template", label_plural="Email templates",
    area="messages", row_label="name", icon="mail", sortable=True, activatable=True,
    searchable=("name", "subject", "body"),
    base_where="channel = 'email'",
    defaults={"channel": "email"},
    before_save=_template_code,
    intro="Used by the SMTP sender for enquiry acknowledgements, invoices, ticket replies "
          "and the portal login code.",
    list_columns=[("name", "Template"), ("category", "Category"), ("subject", "Subject")],
    fields=[
        Field("name", "Name", "text", required=True, span=7),
        Field("category", "Category", "select", span=5,
              options=list(whatsapp.TEMPLATE_CATEGORIES.items()), default="followup"),
        Field("subject", "Subject", "text", required=True, span=12),
        Field("body", "Body", "textarea", rows=12, required=True, span=12, help=VARIABLE_HELP),
        Field("is_active", "Active", "bool", span=6, default=1),
    ],
)

OPTOUTS = Resource(
    key="optouts", table="optouts", label="Opt-out", label_plural="Opt-outs",
    area="messages", row_label="name", icon="shield", order_by="created_at DESC",
    searchable=("name", "number", "email", "reason"),
    intro="Anyone here is skipped by the bulk queue, and the composer warns before it "
          "lets you message them.",
    list_columns=[("name", "Name"), ("number", "Number"), ("channel", "Channel"),
                  ("reason", "Reason")],
    fields=[
        Field("name", "Name", "text", span=6),
        Field("channel", "Channel", "select", span=6, default="whatsapp",
              options=[("whatsapp", "WhatsApp"), ("email", "Email"), ("all", "Everything")]),
        Field("number", "WhatsApp number", "tel", span=6,
              help="Digits with the country code, the form the log shows."),
        Field("email", "Email", "email", span=6),
        Field("reason", "Reason", "textarea", rows=2, span=12),
    ],
)

for resource in (WA_TEMPLATES, EMAIL_TEMPLATES, OPTOUTS):
    crud.register(bp, resource)


# ── target resolution ───────────────────────────────────────────────────────
TARGET_TABLES = {"lead": "leads", "client": "clients", "invoice": "invoices",
                 "ticket": "tickets", "document": "documents"}

BACK_ROUTES = {
    "lead": ("admin.lead_detail", "lead_id"),
    "client": ("admin.client_detail", "client_id"),
    "invoice": ("admin.invoice_detail", "invoice_id"),
    "ticket": ("admin.ticket_detail", "ticket_id"),
    "document": ("admin.document_detail", "document_id"),
}


def _target(kind: str, target_id: int):
    table = TARGET_TABLES.get(kind)
    if not table:
        abort(404)
    row = db.one(f"SELECT * FROM {table} WHERE id = ?", (target_id,))
    if not row:
        abort(404)
    return row


def _resolve(kind: str, row):
    """Variable values, destination number and the log's foreign keys, for one target."""
    lead = client = invoice = ticket = document = project = None
    number = name = ""

    if kind == "lead":
        lead = row
        number, name = row["whatsapp"] or row["phone"], row["name"]
    elif kind == "client":
        client = row
        number, name = row["whatsapp"] or row["phone"], row["contact_name"] or row["name"]
    elif kind == "invoice":
        invoice = row
        client = db.one("SELECT * FROM clients WHERE id = ?", (row["client_id"],))
        if row["project_id"]:
            project = db.one("SELECT * FROM projects WHERE id = ?", (row["project_id"],))
        if client:
            number = client["whatsapp"] or client["phone"]
            name = client["contact_name"] or client["name"]
    elif kind == "ticket":
        ticket = row
        client = db.one("SELECT * FROM clients WHERE id = ?", (row["client_id"],)) \
            if row["client_id"] else None
        number = (client["whatsapp"] or client["phone"]) if client else row["contact_phone"]
        name = row["contact_name"] or (client["contact_name"] if client else "")
    elif kind == "document":
        document = row
        if row["lead_id"]:
            lead = db.one("SELECT * FROM leads WHERE id = ?", (row["lead_id"],))
        if row["client_id"]:
            client = db.one("SELECT * FROM clients WHERE id = ?", (row["client_id"],))
        source = client or lead
        if source is not None:
            number = source["whatsapp"] or source["phone"]
            name = (source["contact_name"] if client is not None else source["name"])

    values = whatsapp.context_for(lead=lead, client=client, invoice=invoice, ticket=ticket,
                                  document=document, project=project)
    links = {}
    for row_obj, column in ((lead, "lead_id"), (client, "client_id"), (invoice, "invoice_id"),
                            (ticket, "ticket_id"), (document, "document_id")):
        if row_obj is not None:
            links[column] = row_obj["id"]
    return values, number or "", name or "", links


def _back(kind: str, target_id) -> str:
    endpoint, arg = BACK_ROUTES.get(kind, ("admin.wa_log", None))
    try:
        return url_for(endpoint, **({arg: target_id} if arg else {}))
    except Exception:  # noqa: BLE001 - target module may not be reachable yet
        return url_for("admin.wa_log")


def _back_from_row(row) -> str:
    for kind, column in (("lead", "lead_id"), ("invoice", "invoice_id"), ("ticket", "ticket_id"),
                         ("document", "document_id"), ("client", "client_id")):
        if row[column]:
            return _back(kind, row[column])
    return url_for("admin.wa_log")


def _suggested_category(kind: str, row) -> str:
    if kind == "invoice":
        return "payment"
    if kind == "ticket":
        return "ticket"
    if kind == "document":
        return "quote"
    if kind == "lead":
        return "first_touch" if row["stage"] == "new" else "followup"
    return "greeting"


def _opted_out(number: str) -> bool:
    digits = wa_number(number, settings.get("whatsapp.default_country_code") or "91")
    if not digits:
        return False
    return bool(db.scalar(
        "SELECT 1 FROM optouts WHERE channel IN ('whatsapp', 'all') AND number != '' "
        "AND REPLACE(REPLACE(REPLACE(number, ' ', ''), '+', ''), '-', '') = ?", (digits,)))


# ── composer ────────────────────────────────────────────────────────────────
@bp.route("/whatsapp/send/<kind>/<int:target_id>", methods=["GET", "POST"])
@require_role("messages")
def wa_compose(kind, target_id):
    row = _target(kind, target_id)
    values, number, name, links = _resolve(kind, row)
    blocked = _opted_out(number)

    if request.method == "POST":
        verify_csrf()
        body = (request.form.get("body") or "").strip()
        number = (request.form.get("number") or number).strip()
        template_id = parse_int(request.form.get("template_id"), 0)
        template_row = db.one("SELECT * FROM message_templates WHERE id = ?",
                              (template_id,)) if template_id else None

        if not body:
            flash("Nothing to send - the message is empty.", "error")
        elif blocked and not request.form.get("override_optout"):
            flash("This number has opted out of WhatsApp. Tick the override box only if they "
                  "have since asked you to message them.", "error")
        else:
            result = whatsapp.send(body=body, number=number, to_name=name,
                                   template=template_row, **links)
            if not result.ok:
                flash(result.error or "The message could not be sent.", "error")
            elif result.link:
                # Click-to-chat needs a browser to open the link, so the send finishes
                # on the handoff page rather than here.
                return redirect(url_for("admin.wa_handoff", message_id=result.message_id))
            else:
                flash("Sent through the WhatsApp Cloud API.", "ok")
                return redirect(_back(kind, target_id))
        return redirect(request.url)

    templates = db.query(
        "SELECT * FROM message_templates WHERE channel = 'whatsapp' AND is_active = 1 "
        "ORDER BY category, sort_order, name")
    history = []
    if links:
        clause = " OR ".join(f"{column} = ?" for column in links)
        history = db.query(
            f"SELECT * FROM messages WHERE channel = 'whatsapp' AND ({clause}) "
            "ORDER BY id DESC LIMIT 20", tuple(links.values()))

    return render_template(
        "admin/wa_compose.html", title="Send WhatsApp", kind=kind, row=row, number=number,
        name=name, values=values, templates=templates, history=history, blocked=blocked,
        suggested=_suggested_category(kind, row), provider=whatsapp.provider(),
        categories=whatsapp.TEMPLATE_CATEGORIES, labels=whatsapp.STATUS_LABELS,
        back=_back(kind, target_id), nav_active="admin.wa_log")


@bp.route("/whatsapp/preview", methods=["POST"])
@require_role("messages")
def wa_preview():
    """Live preview behind the composer's template picker."""
    verify_csrf()
    payload = request.get_json(silent=True) or {}
    row = db.one("SELECT * FROM message_templates WHERE id = ?",
                 (parse_int(payload.get("template_id"), 0),))
    if not row:
        return jsonify({"ok": False, "body": ""})
    values = payload.get("values") or {}
    return jsonify({
        "ok": True,
        "body": whatsapp.render(row, values),
        "missing": [name for name in template_vars(row["body"]) if not values.get(name)],
    })


@bp.route("/whatsapp/handoff/<int:message_id>")
@require_role("messages")
def wa_handoff(message_id):
    """Click-to-chat's second half.

    WhatsApp tells us nothing once the tab opens, so the owner says what happened.
    Better a log that admits it does not know than one that claims a delivery.
    """
    from urllib.parse import quote

    row = db.one("SELECT * FROM messages WHERE id = ?", (message_id,))
    if not row:
        abort(404)
    digits = wa_number(row["to_number"], settings.get("whatsapp.default_country_code") or "91")
    return render_template("admin/wa_handoff.html", title="Open WhatsApp", row=row,
                           link=f"https://wa.me/{digits}?text={quote(row['body'])}",
                           back=_back_from_row(row), nav_active="admin.wa_log")


@bp.route("/whatsapp/confirm/<int:message_id>", methods=["POST"])
@require_role("messages")
def wa_confirm(message_id):
    verify_csrf()
    row = db.one("SELECT * FROM messages WHERE id = ?", (message_id,))
    if not row:
        abort(404)
    sent = request.form.get("outcome") == "sent"
    db.update("messages", message_id, {
        "status": "sent" if sent else "failed",
        "error": "" if sent else "Not sent - reported by you on the handoff screen.",
        "sent_at": db.scalar("SELECT datetime('now')") if sent else None,
    })
    flash("Logged as sent." if sent else "Logged as not sent.", "ok")
    return redirect(request.form.get("next") or url_for("admin.wa_log"))


# ── message log ─────────────────────────────────────────────────────────────
@bp.route("/whatsapp/log")
@require_role("messages")
def wa_log():
    channel = request.args.get("channel") or "whatsapp"
    status = request.args.get("status") or ""
    direction = request.args.get("direction") or ""
    query = (request.args.get("q") or "").strip()

    where = ["m.channel = ?"]
    params: list = [channel]
    if status:
        where.append("m.status = ?")
        params.append(status)
    if direction:
        where.append("m.direction = ?")
        params.append(direction)
    if query:
        where.append("(m.to_name LIKE ? OR m.to_number LIKE ? OR m.body LIKE ?)")
        params += [f"%{query}%"] * 3

    rows = db.query(
        f"""SELECT m.*, t.name AS template_name, l.ref AS lead_ref, l.name AS lead_name,
                   c.name AS client_name, i.ref AS invoice_ref, k.ref AS ticket_ref
            FROM messages m
            LEFT JOIN message_templates t ON t.id = m.template_id
            LEFT JOIN leads l    ON l.id = m.lead_id
            LEFT JOIN clients c  ON c.id = m.client_id
            LEFT JOIN invoices i ON i.id = m.invoice_id
            LEFT JOIN tickets k  ON k.id = m.ticket_id
            WHERE {' AND '.join(where)}
            ORDER BY m.id DESC LIMIT 400""", tuple(params))

    counts = {r["status"]: r["n"] for r in db.query(
        "SELECT status, COUNT(*) AS n FROM messages WHERE channel = ? GROUP BY status",
        (channel,))}

    return render_template("admin/wa_log.html", title="Message log", rows=rows, counts=counts,
                           channel=channel, status=status, direction=direction, q=query,
                           labels=whatsapp.STATUS_LABELS, provider=whatsapp.provider(),
                           nav_active="admin.wa_log")


@bp.route("/whatsapp/log/<int:message_id>/delete", methods=["POST"])
@require_role("owner")
def wa_log_delete(message_id):
    verify_csrf()
    db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    audit.log("delete", "messages", message_id, "log entry")
    flash("Log entry removed.", "ok")
    return redirect(request.referrer or url_for("admin.wa_log"))


# ── bulk queue ──────────────────────────────────────────────────────────────
AUDIENCES = {
    "leads_stage": "Leads at one stage",
    "clients_active": "All active clients",
    "invoices_unpaid": "Clients with an unpaid invoice",
}


@bp.route("/whatsapp/bulk", methods=["GET", "POST"])
@require_role("owner")
def wa_bulk():
    """Queue a template against an audience.

    A queue and not a blast: click-to-chat cannot send by itself, and on the Cloud
    API a sudden burst to people who never opted in is the quickest way to lose the
    number. Rows are queued, then released in small runs.
    """
    if request.method == "POST":
        verify_csrf()
        template_row = db.one("SELECT * FROM message_templates WHERE id = ? AND channel = 'whatsapp'",
                              (parse_int(request.form.get("template_id"), 0),))
        if not template_row:
            flash("Pick a template first.", "error")
            return redirect(request.url)

        audience = request.form.get("audience") or "leads_stage"
        stage = request.form.get("stage") or "new"
        batch_id = secrets.token_hex(6)
        queued = skipped = 0
        for target in _audience(audience, stage):
            if not target["number"] or _opted_out(target["number"]):
                skipped += 1
                continue
            whatsapp.log_row(body=whatsapp.render(template_row, target["values"]),
                             to_number=target["number"], to_name=target["name"],
                             template_id=template_row["id"], batch_id=batch_id,
                             **target["links"])
            queued += 1

        audit.log("create", "messages", batch_id, f"bulk: {template_row['name']}",
                  after={"queued": queued, "skipped": skipped, "audience": audience})
        if not queued:
            flash("Nobody in that audience has a usable number.", "warn")
            return redirect(request.url)
        flash(f"Queued {queued}." + (f" Skipped {skipped} with no number or an opt-out."
                                     if skipped else ""), "ok")
        return redirect(url_for("admin.wa_batch", batch_id=batch_id))

    return render_template(
        "admin/wa_bulk.html", title="Bulk WhatsApp",
        templates=db.query("SELECT * FROM message_templates WHERE channel = 'whatsapp' "
                           "AND is_active = 1 ORDER BY category, sort_order, name"),
        # Stages are a constant in core.leads, not a table - a pipeline stage has
        # code hanging off it, so it is not something to let anyone rename freely.
        stages=[{"code": code, "name": label} for code, label in STAGE_LABELS.items()],
        audiences=AUDIENCES, provider=whatsapp.provider(),
        batches=db.query(
            """SELECT batch_id, COUNT(*) AS total,
                      SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN status IN ('sent','delivered','read') THEN 1 ELSE 0 END) AS done,
                      MIN(created_at) AS started
               FROM messages WHERE batch_id != '' GROUP BY batch_id
               ORDER BY started DESC LIMIT 20"""),
        nav_active="admin.wa_bulk")


def _audience(kind: str, stage: str) -> list[dict]:
    out: list[dict] = []
    if kind == "leads_stage":
        for row in db.query("SELECT * FROM leads WHERE stage = ? AND is_spam = 0 "
                            "ORDER BY id DESC LIMIT 300", (stage,)):
            out.append({"number": row["whatsapp"] or row["phone"], "name": row["name"],
                        "values": whatsapp.context_for(lead=row),
                        "links": {"lead_id": row["id"]}})
    elif kind == "clients_active":
        for row in db.query("SELECT * FROM clients WHERE is_active = 1 ORDER BY name"):
            out.append({"number": row["whatsapp"] or row["phone"],
                        "name": row["contact_name"] or row["name"],
                        "values": whatsapp.context_for(client=row),
                        "links": {"client_id": row["id"]}})
    elif kind == "invoices_unpaid":
        for row in db.query("SELECT * FROM invoices WHERE status IN "
                            "('sent', 'part_paid', 'overdue') ORDER BY due_on"):
            client = db.one("SELECT * FROM clients WHERE id = ?", (row["client_id"],))
            if not client:
                continue
            out.append({"number": client["whatsapp"] or client["phone"],
                        "name": client["contact_name"] or client["name"],
                        "values": whatsapp.context_for(client=client, invoice=row),
                        "links": {"client_id": client["id"], "invoice_id": row["id"]}})
    return out


@bp.route("/whatsapp/bulk/<batch_id>")
@require_role("owner")
def wa_batch(batch_id):
    rows = db.query("SELECT * FROM messages WHERE batch_id = ? ORDER BY id", (batch_id,))
    if not rows:
        abort(404)
    return render_template("admin/wa_batch.html", title=f"Batch {batch_id}", rows=rows,
                           batch_id=batch_id, limit=SEND_LIMIT_PER_RUN,
                           pending=[r for r in rows if r["status"] == "queued"],
                           provider=whatsapp.provider(), labels=whatsapp.STATUS_LABELS,
                           nav_active="admin.wa_bulk")


@bp.route("/whatsapp/bulk/<batch_id>/run", methods=["POST"])
@require_role("owner")
def wa_batch_run(batch_id):
    verify_csrf()
    if not whatsapp.cloud_api_on():
        flash("Click-to-chat cannot send on its own - open each queued message from the list "
              "below, or switch the provider to the Cloud API in Settings.", "warn")
        return redirect(url_for("admin.wa_batch", batch_id=batch_id))

    rows = db.query("SELECT * FROM messages WHERE batch_id = ? AND status = 'queued' "
                    "ORDER BY id LIMIT ?", (batch_id, SEND_LIMIT_PER_RUN))
    provider = whatsapp.CloudApiProvider()
    sent = failed = 0
    for row in rows:
        template_row = db.one("SELECT * FROM message_templates WHERE id = ?",
                              (row["template_id"],)) if row["template_id"] else None
        result = provider.send(number=row["to_number"], body=row["body"],
                              row_id=row["id"], template=template_row)
        sent, failed = sent + (1 if result.ok else 0), failed + (0 if result.ok else 1)
    flash(f"Sent {sent}." + (f" {failed} failed - the log has the reason." if failed else ""),
          "warn" if failed else "ok")
    return redirect(url_for("admin.wa_batch", batch_id=batch_id))


@bp.route("/whatsapp/bulk/<batch_id>/cancel", methods=["POST"])
@require_role("owner")
def wa_batch_cancel(batch_id):
    verify_csrf()
    db.execute("DELETE FROM messages WHERE batch_id = ? AND status = 'queued'", (batch_id,))
    flash("Remaining queued messages cancelled.", "ok")
    return redirect(url_for("admin.wa_bulk"))
