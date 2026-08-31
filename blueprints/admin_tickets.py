"""The support desk: queue, thread, SLA clock, time logging and change requests."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

from blueprints.admin import bp
from core import audit, crud, db, settings, tickets
from core.auth import require_role, verify_csrf
from core.crud import Field, Resource
from core.util import fy_label, fy_start_year, parse_int


# ── SLA policies ────────────────────────────────────────────────────────────
SLA = Resource(
    key="sla", table="sla_policies", label="SLA policy", label_plural="SLA policies",
    area="tickets", row_label="label", activatable=True, sortable=True, icon="clock",
    deletable=False,
    intro="What you have promised, per priority. A ticket takes a copy of these hours the "
          "moment it is raised, so tightening a policy tomorrow never retroactively breaches "
          "tickets already in flight.",
    list_columns=[("label", "Priority"), ("response_hours", "Respond within"),
                  ("resolve_hours", "Resolve within")],
    fields=[
        Field("priority", "Priority code", "select", span=6, required=True,
              options=lambda: list(tickets.PRIORITY_LABELS.items())),
        Field("label", "Label", "text", span=6, required=True),
        Field("description", "What counts as this", "textarea", rows=3, span=12,
              help="Shown to you when you set a priority. Being specific here is what stops "
                   "everything becoming a P1."),
        Field("response_hours", "Respond within, hours", "number", step="0.5", span=6,
              required=True),
        Field("resolve_hours", "Resolve within, hours", "number", step="0.5", span=6,
              required=True),
        Field("is_active", "Active", "bool", span=6, default=1),
    ],
)

crud.register(bp, SLA)


# ── queue ───────────────────────────────────────────────────────────────────
@bp.route("/tickets")
@require_role("tickets")
def tickets_list():
    status = request.args.get("status") or "live"
    priority = request.args.get("priority") or ""
    category = request.args.get("category") or ""
    sla = request.args.get("sla") or ""
    client_id = parse_int(request.args.get("client"), 0) or None
    query = (request.args.get("q") or "").strip()

    rows = tickets.search(status=status, priority=priority, category=category,
                          client_id=client_id, q=query, sla=sla)
    decorated = [(row, tickets.sla_state(row)) for row in rows]

    counts = {r["status"]: r["n"] for r in db.query(
        "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status")}
    counts["live"] = sum(counts.get(s, 0) for s in tickets.LIVE_STATUSES)

    return render_template(
        "admin/tickets_list.html", title="Support", rows=decorated, status=status,
        priority=priority, category=category, sla=sla, client_id=client_id, q=query,
        counts=counts, categories=tickets.CATEGORIES, priorities=tickets.PRIORITY_LABELS,
        statuses=tickets.TICKET_STATUS_LABELS,
        clients=db.query("SELECT id, name FROM clients ORDER BY name"),
        flagged=len([1 for _r, s in decorated if s["state"] in ("breached", "at_risk")]),
        nav_active="admin.tickets_list")


@bp.route("/tickets/new", methods=["GET", "POST"])
@require_role("tickets")
def ticket_new():
    client_id = parse_int(request.args.get("client_id"), 0) or None

    if request.method == "POST":
        verify_csrf()
        subject = (request.form.get("subject") or "").strip()
        if not subject:
            flash("A ticket needs a subject.", "error")
            return redirect(request.url)
        ticket_id = tickets.create({
            "client_id": parse_int(request.form.get("client_id"), 0) or None,
            "project_id": parse_int(request.form.get("project_id"), 0) or None,
            "contact_name": (request.form.get("contact_name") or "").strip(),
            "contact_email": (request.form.get("contact_email") or "").strip(),
            "contact_phone": (request.form.get("contact_phone") or "").strip(),
            "subject": subject,
            "body": (request.form.get("body") or "").strip(),
            "category": request.form.get("category") or "other",
            "priority": request.form.get("priority") or "p3",
            "is_change_request": bool(request.form.get("is_change_request")),
        }, source="admin")
        flash("Ticket raised, and its SLA clock has started.", "ok")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))

    return render_template(
        "admin/ticket_form.html", title="New ticket",
        client=db.one("SELECT * FROM clients WHERE id = ?", (client_id,)) if client_id else None,
        clients=db.query("SELECT id, name, contact_name, email, phone FROM clients "
                         "WHERE is_active = 1 ORDER BY name"),
        projects=db.query("SELECT id, ref, name, client_id FROM projects ORDER BY id DESC"),
        categories=tickets.CATEGORIES, priorities=tickets.PRIORITY_LABELS,
        policies={p: tickets.policy(p) for p in tickets.PRIORITIES},
        nav_active="admin.tickets_list")


@bp.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
@require_role("tickets")
def ticket_detail(ticket_id):
    ticket = tickets.get(ticket_id)
    if not ticket:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        changes = {
            "subject": (request.form.get("subject") or ticket["subject"]).strip()[:300],
            "category": request.form.get("category") or ticket["category"],
            "assignee_user_id": parse_int(request.form.get("assignee_user_id"), 0) or None,
            "project_id": parse_int(request.form.get("project_id"), 0) or None,
            "rate_per_hour": request.form.get("rate_per_hour") or ticket["rate_per_hour"],
            "is_change_request": 1 if request.form.get("is_change_request") else 0,
        }
        priority = request.form.get("priority")
        if priority in tickets.PRIORITIES and priority != ticket["priority"]:
            changes["priority"] = priority
            # Re-stamp the deadlines from the new policy, measured from now rather
            # than from creation, so re-prioritising an old ticket does not instantly
            # breach it or hand it a deadline that has already passed.
            from datetime import datetime, timedelta
            policy = tickets.policy(priority)
            now = datetime.now()
            changes["response_due_at"] = (
                now + timedelta(hours=policy["response_hours"])).strftime("%Y-%m-%d %H:%M:%S")
            changes["resolve_due_at"] = (
                now + timedelta(hours=policy["resolve_hours"])).strftime("%Y-%m-%d %H:%M:%S")
            tickets.reply(ticket_id,
                          f"Priority changed from {ticket['priority'].upper()} to "
                          f"{priority.upper()}; the SLA clock was reset from now.",
                          is_internal=True)
        db.update("tickets", ticket_id, changes)
        audit.log("update", "tickets", ticket_id, ticket["subject"], after=changes)
        flash("Ticket updated.", "ok")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))

    minutes = tickets.logged_minutes(ticket_id)
    return render_template(
        "admin/ticket_detail.html", title=ticket["ref"], ticket=ticket,
        state=tickets.sla_state(ticket), thread=tickets.messages(ticket_id),
        logs=tickets.time_logs(ticket_id), minutes=minutes,
        billable=tickets.billable_amount(ticket_id),
        client=db.one("SELECT * FROM clients WHERE id = ?", (ticket["client_id"],))
        if ticket["client_id"] else None,
        project=db.one("SELECT * FROM projects WHERE id = ?", (ticket["project_id"],))
        if ticket["project_id"] else None,
        projects=db.query("SELECT id, ref, name, client_id FROM projects ORDER BY id DESC"),
        users=db.query("SELECT id, name FROM users WHERE is_active = 1 ORDER BY name"),
        categories=tickets.CATEGORIES, priorities=tickets.PRIORITY_LABELS,
        statuses=tickets.TICKET_STATUS_LABELS,
        quote=db.one("SELECT * FROM quotes WHERE id = ?", (ticket["quote_id"],))
        if ticket["quote_id"] else None,
        invoices=db.query("SELECT * FROM invoices WHERE ticket_id = ? ORDER BY id DESC",
                          (ticket_id,)),
        nav_active="admin.tickets_list")


@bp.route("/tickets/<int:ticket_id>/reply", methods=["POST"])
@require_role("tickets")
def ticket_reply(ticket_id):
    verify_csrf()
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Write something first.", "error")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))

    internal = bool(request.form.get("is_internal"))
    tickets.reply(ticket_id, body, is_internal=internal,
                  media_id=parse_int(request.form.get("media_id"), 0) or None)

    status = request.form.get("then_status")
    if status in tickets.TICKET_STATUSES:
        tickets.set_status(ticket_id, status)

    if internal:
        flash("Internal note saved. The client cannot see it.", "ok")
    else:
        flash("Reply saved on the thread. Send it to them from the buttons on the right.", "ok")
    return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))


@bp.route("/tickets/<int:ticket_id>/status", methods=["POST"])
@require_role("tickets")
def ticket_status(ticket_id):
    verify_csrf()
    status = request.form.get("status") or ""
    if status not in tickets.TICKET_STATUSES:
        abort(400, "Unknown status.")
    tickets.set_status(ticket_id, status, (request.form.get("note") or "").strip())
    flash(f"Moved to {tickets.TICKET_STATUS_LABELS[status].lower()}."
          + (" The resolve clock is paused while it is with them."
             if status == "waiting_client" else ""), "ok")
    return redirect(request.referrer or url_for("admin.ticket_detail", ticket_id=ticket_id))


@bp.route("/tickets/<int:ticket_id>/time", methods=["POST"])
@require_role("tickets")
def ticket_time(ticket_id):
    verify_csrf()
    minutes = parse_int(request.form.get("minutes"), 0)
    if minutes <= 0:
        flash("How many minutes?", "error")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))
    tickets.log_time(ticket_id, minutes, (request.form.get("note") or "").strip(),
                     billable=bool(request.form.get("is_billable")))
    flash(f"Logged {minutes} minutes.", "ok")
    return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))


@bp.route("/tickets/<int:ticket_id>/time/<int:log_id>/delete", methods=["POST"])
@require_role("tickets")
def ticket_time_delete(ticket_id, log_id):
    verify_csrf()
    db.execute("DELETE FROM ticket_time_logs WHERE id = ? AND ticket_id = ?", (log_id, ticket_id))
    flash("Time entry removed.", "ok")
    return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))


@bp.route("/tickets/<int:ticket_id>/change-request", methods=["POST"])
@require_role("tickets")
def ticket_change_request(ticket_id):
    verify_csrf()
    try:
        quote_id = tickets.to_change_request(ticket_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))
    flash("Priced as a change request from the time already logged. Adjust the line, then "
          "send it.", "ok")
    return redirect(url_for("admin.quote_detail", quote_id=quote_id))


@bp.route("/tickets/<int:ticket_id>/invoice", methods=["POST"])
@require_role("billing")
def ticket_invoice(ticket_id):
    """Bill the billable time logged on a ticket."""
    verify_csrf()
    from core import billing

    ticket = tickets.get(ticket_id)
    if not ticket:
        abort(404)
    if not ticket["client_id"]:
        flash("Attach this ticket to a client before billing it.", "error")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))

    amount = tickets.billable_amount(ticket_id)
    if amount <= 0:
        flash("No billable time is logged on this ticket. Tick 'billable' when you log it.",
              "error")
        return redirect(url_for("admin.ticket_detail", ticket_id=ticket_id))

    from core.util import parse_float
    minutes = parse_int(db.scalar(
        "SELECT COALESCE(SUM(minutes), 0) FROM ticket_time_logs "
        "WHERE ticket_id = ? AND is_billable = 1", (ticket_id,), 0))
    hours = round(minutes / 60.0, 2)
    invoice_id = billing.create(
        ticket["client_id"], project_id=ticket["project_id"], ticket_id=ticket_id,
        line_items=[{
            "label": f"Support - {ticket['subject']}"[:300],
            "description": f"Ticket {ticket['ref']}, {hours:g} billable hour(s).",
            "qty": hours, "unit": "hour",
            "unit_price": parse_float(ticket["rate_per_hour"], 1200),
            "tax_rate": billing.default_tax_rate(),
        }], notes=f"Billable support time on ticket {ticket['ref']}.")
    flash("Draft invoice raised for the billable time.", "ok")
    return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))


@bp.route("/tickets/<int:ticket_id>/delete", methods=["POST"])
@require_role("owner")
def ticket_delete(ticket_id):
    verify_csrf()
    ticket = tickets.get(ticket_id)
    if not ticket:
        abort(404)
    db.delete("tickets", ticket_id)
    audit.log("delete", "tickets", ticket_id, ticket["subject"], before=ticket)
    flash("Ticket deleted.", "ok")
    return redirect(url_for("admin.tickets_list"))


# ── SLA report ──────────────────────────────────────────────────────────────
@bp.route("/tickets/report")
@require_role("tickets")
def tickets_report():
    start_year = parse_int(request.args.get("fy"), 0) or fy_start_year()
    since, until = f"{start_year}-04-01", f"{start_year + 1}-04-01"
    return render_template(
        "admin/tickets_report.html", title="Support performance",
        stats=tickets.stats(since, until), flagged=tickets.at_risk(),
        priorities=tickets.PRIORITY_LABELS, categories=tickets.CATEGORIES,
        policies={p: tickets.policy(p) for p in tickets.PRIORITIES},
        at_risk_pct=settings.get("sla.at_risk_pct"),
        fy=fy_label(f"{start_year}-04-01"), start_year=start_year,
        years=list(range(fy_start_year() - 4, fy_start_year() + 1)),
        nav_active="admin.tickets_list")
