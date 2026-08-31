"""Leads and CRM: the kanban, the table, the lead record with its timeline,
follow-ups, CSV in and out, and the conversion report."""

from __future__ import annotations

import csv
import io

from flask import (Response, abort, flash, jsonify, redirect, render_template,
                   request, url_for)

from blueprints.admin import bp
from core import audit, db, leads, pricing, settings
from core.auth import require_role, verify_csrf
from core.util import (clean_phone, csv_cell, fy_label, fy_start_year, parse_float,
                       parse_int, valid_email, wa_number)


@bp.route("/leads/board")
@require_role("leads")
def leads_board():
    grouped = leads.board()
    probability = settings.get("crm.stage_probability") or {}
    columns = []
    for stage in leads.BOARD_STAGES:
        rows = grouped.get(stage, [])
        columns.append({
            "stage": stage,
            "label": leads.STAGE_LABELS[stage],
            "rows": rows,
            "value": sum(parse_float(r["quote_value"]) for r in rows),
            "probability": parse_int(probability.get(stage, 0)),
        })
    return render_template("admin/leads_board.html", title="Pipeline", columns=columns,
                           forecast=leads.pipeline_forecast(),
                           due=leads.followups_due(), overdue=leads.followups_overdue())


@bp.route("/leads")
@require_role("leads")
def leads_list():
    stage = (request.args.get("stage") or "").strip()
    followup = (request.args.get("followup") or "").strip()
    source_id = parse_int(request.args.get("source"), 0) or None
    q = (request.args.get("q") or "").strip()
    spam = request.args.get("spam") == "1"

    rows = leads.search(stage=stage, source_id=source_id, q=q, spam=spam, followup=followup)
    return render_template(
        "admin/leads_list.html", title="Leads", rows=rows, stage=stage, q=q,
        followup=followup, source_id=source_id, spam=spam,
        sources=db.query("SELECT * FROM lead_sources ORDER BY sort_order, name"),
        counts=_stage_counts(),
    )


def _stage_counts() -> dict:
    rows = db.query("SELECT stage, COUNT(*) AS n FROM leads WHERE is_spam = 0 GROUP BY stage")
    out = {r["stage"]: r["n"] for r in rows}
    out["all"] = sum(out.values())
    out["spam"] = parse_int(db.scalar("SELECT COUNT(*) FROM leads WHERE is_spam = 1", (), 0))
    return out


@bp.route("/leads/new", methods=["GET", "POST"])
@require_role("leads")
def lead_new():
    if request.method == "POST":
        verify_csrf()
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("A lead needs a name.", "error")
        else:
            lead_id = leads.create(_read_lead_form(request.form), source="admin")
            flash("Lead added.", "ok")
            return redirect(url_for("admin.lead_detail", lead_id=lead_id))
    return render_template("admin/lead_form.html", title="New lead", lead=None,
                           sources=db.query("SELECT * FROM lead_sources WHERE is_active = 1 ORDER BY sort_order"),
                           services=db.query("SELECT name FROM services WHERE is_published = 1 ORDER BY sort_order"),
                           nav_active="admin.leads_list")


def _read_lead_form(form) -> dict:
    return {
        "name": (form.get("name") or "").strip()[:200],
        "company": (form.get("company") or "").strip()[:200],
        "email": (form.get("email") or "").strip()[:200],
        "phone": clean_phone(form.get("phone") or "")[:40],
        "whatsapp": wa_number(form.get("whatsapp") or form.get("phone") or ""),
        "city": (form.get("city") or "").strip()[:120],
        "stage": form.get("stage") if form.get("stage") in leads.STAGES else "new",
        "source_id": parse_int(form.get("source_id"), 0) or None,
        "source_note": (form.get("source_note") or "").strip()[:200],
        "service_interest": (form.get("service_interest") or "").strip()[:200],
        "budget_band": (form.get("budget_band") or "").strip()[:120],
        "message": (form.get("message") or "").strip()[:4000],
        "quote_value": parse_float(form.get("quote_value"), 0),
        "next_followup_on": (form.get("next_followup_on") or "").strip() or None,
        "followup_note": (form.get("followup_note") or "").strip()[:300],
        "tags": (form.get("tags") or "").strip()[:200],
    }


@bp.route("/leads/<int:lead_id>", methods=["GET", "POST"])
@require_role("leads")
def lead_detail(lead_id):
    lead = leads.get(lead_id)
    if not lead:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        data = _read_lead_form(request.form)
        stage = data.pop("stage")
        db.update("leads", lead_id, {**data, "score": leads.score_of({**dict(lead), **data}),
                                     "updated_at": db.scalar("SELECT datetime('now')")})
        if stage != lead["stage"]:
            leads.set_stage(lead_id, stage, request.form.get("stage_note") or "")
        audit.log("update", "leads", lead_id, lead["name"], before=lead, after=data)
        flash("Lead saved.", "ok")
        return redirect(url_for("admin.lead_detail", lead_id=lead_id))

    quotes = db.query(
        "SELECT * FROM quotes WHERE lead_id = ? ORDER BY id DESC", (lead_id,))
    documents = db.query(
        "SELECT * FROM documents WHERE lead_id = ? ORDER BY id DESC", (lead_id,))
    messages = db.query(
        "SELECT m.*, t.name AS template_name FROM messages m "
        "LEFT JOIN message_templates t ON t.id = m.template_id "
        "WHERE m.lead_id = ? ORDER BY m.id DESC LIMIT 30", (lead_id,))

    return render_template(
        "admin/lead_detail.html", title=lead["name"], lead=lead,
        events=leads.timeline(lead_id), quotes=quotes, documents=documents,
        messages=messages,
        client=db.one("SELECT * FROM clients WHERE id = ?", (lead["client_id"],)) if lead["client_id"] else None,
        sources=db.query("SELECT * FROM lead_sources WHERE is_active = 1 ORDER BY sort_order"),
        services=db.query("SELECT name FROM services WHERE is_published = 1 ORDER BY sort_order"),
        templates=db.query(
            "SELECT * FROM message_templates WHERE is_active = 1 AND channel = 'whatsapp' "
            "ORDER BY category, sort_order"),
        probability=leads.probability(lead["stage"]),
        nav_active="admin.leads_list",
    )


@bp.route("/leads/<int:lead_id>/stage", methods=["POST"])
@require_role("leads")
def lead_stage(lead_id):
    verify_csrf()
    stage = request.form.get("stage") or ""
    if stage not in leads.STAGES:
        abort(400, "Unknown stage.")
    leads.set_stage(lead_id, stage, request.form.get("note") or "",
                    request.form.get("lost_reason") or "")
    flash(f"Moved to {leads.STAGE_LABELS[stage]}.", "ok")
    return redirect(request.referrer or url_for("admin.lead_detail", lead_id=lead_id))


@bp.route("/leads/move", methods=["POST"])
@require_role("leads")
def lead_move():
    """The kanban drop target."""
    verify_csrf()
    payload = request.get_json(silent=True, force=True) or {}
    lead_id = parse_int(payload.get("lead_id"), 0)
    stage = payload.get("stage")
    if not lead_id or stage not in leads.STAGES:
        return jsonify({"ok": False, "error": "Bad lead or stage."}), 400
    lead = leads.get(lead_id)
    if not lead:
        return jsonify({"ok": False, "error": "Lead not found."}), 404
    leads.set_stage(lead_id, stage, "Moved on the board.")
    return jsonify({"ok": True, "message": f"{lead['name']} moved to {leads.STAGE_LABELS[stage]}."})


@bp.route("/leads/<int:lead_id>/event", methods=["POST"])
@require_role("leads")
def lead_event(lead_id):
    verify_csrf()
    lead = leads.get(lead_id)
    if not lead:
        abort(404)
    kind = request.form.get("kind") or "note"
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Write something to record.", "error")
    else:
        bump = kind in ("call", "whatsapp", "email", "meeting")
        if bump:
            leads.touch(lead_id, kind, body)
        else:
            leads.add_event(lead_id, kind, body)
        flash("Recorded on the timeline.", "ok")
    return redirect(url_for("admin.lead_detail", lead_id=lead_id))


@bp.route("/leads/<int:lead_id>/snooze", methods=["POST"])
@require_role("leads")
def lead_snooze(lead_id):
    verify_csrf()
    days = parse_int(request.form.get("days"), 3)
    when = leads.snooze(lead_id, days, request.form.get("note") or "")
    flash(f"Follow-up moved to {when}.", "ok")
    return redirect(request.referrer or url_for("admin.lead_detail", lead_id=lead_id))


@bp.route("/leads/<int:lead_id>/spam", methods=["POST"])
@require_role("leads")
def lead_spam(lead_id):
    verify_csrf()
    spam = request.form.get("spam") != "0"
    leads.mark_spam(lead_id, spam)
    flash("Marked as spam." if spam else "Restored.", "ok")
    return redirect(url_for("admin.leads_list", spam="1" if not spam else None))


@bp.route("/leads/<int:lead_id>/delete", methods=["POST"])
@require_role("leads")
def lead_delete(lead_id):
    verify_csrf()
    lead = leads.get(lead_id)
    if not lead:
        abort(404)
    db.delete("leads", lead_id)
    audit.log("delete", "leads", lead_id, lead["name"], before=lead)
    flash("Lead deleted.", "ok")
    return redirect(url_for("admin.leads_list"))


@bp.route("/leads/<int:lead_id>/convert", methods=["GET", "POST"])
@require_role("leads")
def lead_convert(lead_id):
    lead = leads.get(lead_id)
    if not lead:
        abort(404)

    quotes = db.query(
        "SELECT * FROM quotes WHERE lead_id = ? ORDER BY id DESC", (lead_id,))

    if request.method == "POST":
        verify_csrf()
        quote_id = parse_int(request.form.get("quote_id"), 0) or None
        value = parse_float(request.form.get("value"), 0)
        if quote_id and not value:
            quote = pricing.get_quote(quote_id)
            value = parse_float(quote["total"]) if quote else 0
        try:
            client_id, project_id = leads.convert(
                lead_id,
                project_name=(request.form.get("project_name") or "").strip(),
                value=value,
                billing_type=request.form.get("billing_type") or "milestone",
                quote_id=quote_id,
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("admin.lead_convert", lead_id=lead_id))
        flash("Client and project created, with the payment schedule and launch checklist.", "ok")
        return redirect(url_for("admin.project_detail", project_id=project_id))

    return render_template("admin/lead_convert.html", title=f"Convert {lead['name']}",
                           lead=lead, quotes=quotes, nav_active="admin.leads_list")


# ── follow-up queue ─────────────────────────────────────────────────────────
@bp.route("/leads/followups")
@require_role("leads")
def followups():
    return render_template("admin/followups.html", title="Follow-ups",
                           overdue=leads.followups_overdue(),
                           due=[r for r in leads.followups_due()
                                if r["next_followup_on"] >= db.scalar("SELECT date('now')")],
                           quiet=leads.going_quiet(),
                           templates=db.query(
                               "SELECT * FROM message_templates WHERE is_active = 1 "
                               "AND channel = 'whatsapp' ORDER BY category, sort_order"),
                           nav_active="admin.leads_list")


@bp.route("/leads/sweep", methods=["POST"])
@require_role("leads")
def leads_sweep():
    verify_csrf()
    moved = leads.sweep_dormant()
    flash(f"{moved} quiet lead(s) moved to dormant." if moved
          else "Nothing was quiet enough to move.", "ok")
    return redirect(url_for("admin.followups"))


# ── conversion report ───────────────────────────────────────────────────────
@bp.route("/leads/conversion")
@require_role("leads")
def conversion():
    start_year = parse_int(request.args.get("fy"), 0) or fy_start_year()
    since, until = f"{start_year}-04-01", f"{start_year + 1}-04-01"
    funnel = leads.funnel(since, until)
    return render_template(
        "admin/conversion.html", title="Conversion", funnel=funnel,
        headline=leads.headline(since, until),
        by_source=leads.by_source(since, until),
        lost=leads.lost_reasons(since, until),
        forecast=leads.pipeline_forecast(),
        fy=fy_label(f"{start_year}-04-01"), start_year=start_year,
        years=list(range(fy_start_year() - 4, fy_start_year() + 1)),
        nav_active="admin.leads_list",
    )


# ── CSV ─────────────────────────────────────────────────────────────────────
CSV_COLUMNS = ("ref", "name", "company", "email", "phone", "whatsapp", "city", "stage",
               "source", "service_interest", "budget_band", "quote_value", "score",
               "next_followup_on", "lost_reason", "utm_source", "utm_medium",
               "utm_campaign", "created_at", "message")


@bp.route("/leads/export")
@require_role("leads")
def leads_export():
    rows = leads.search(stage=request.args.get("stage") or "", limit=10000)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow([
            csv_cell(row["ref"]), csv_cell(row["name"]), csv_cell(row["company"]),
            csv_cell(row["email"]), csv_cell(row["phone"]), csv_cell(row["whatsapp"]),
            csv_cell(row["city"]), csv_cell(row["stage"]), csv_cell(row["source_name"]),
            csv_cell(row["service_interest"]), csv_cell(row["budget_band"]),
            row["quote_value"], row["score"], csv_cell(row["next_followup_on"]),
            csv_cell(row["lost_reason"]), csv_cell(row["utm_source"]),
            csv_cell(row["utm_medium"]), csv_cell(row["utm_campaign"]),
            csv_cell(row["created_at"]), csv_cell(row["message"]),
        ])
    audit.log("export", "leads", "", f"{len(rows)} leads")
    return Response(
        buffer.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="aruka-leads.csv"'})


@bp.route("/leads/import", methods=["GET", "POST"])
@require_role("leads")
def leads_import():
    if request.method == "POST":
        verify_csrf()
        upload = request.files.get("file")
        if not upload or not upload.filename:
            flash("Choose a CSV file.", "error")
            return redirect(url_for("admin.leads_import"))
        try:
            text = upload.read().decode("utf-8-sig", errors="replace")
        except (UnicodeError, AttributeError):
            flash("That file is not readable text.", "error")
            return redirect(url_for("admin.leads_import"))

        reader = csv.DictReader(io.StringIO(text))
        added, skipped = 0, 0
        source_id = parse_int(request.form.get("source_id"), 0) or None
        for raw in reader:
            data = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            name = data.get("name") or data.get("full name") or data.get("contact")
            email = data.get("email") or ""
            phone = data.get("phone") or data.get("mobile") or data.get("number") or ""
            if not name or (not email and not phone):
                skipped += 1
                continue
            # A repeat of an existing email or number is an update to that lead, not a
            # second lead: duplicates are what make a CRM stop being trusted.
            existing = None
            if email and valid_email(email):
                existing = db.one("SELECT * FROM leads WHERE email = ?", (email.lower(),))
            if not existing and phone:
                existing = db.one("SELECT * FROM leads WHERE phone = ? OR whatsapp = ?",
                                  (clean_phone(phone), wa_number(phone)))
            if existing:
                skipped += 1
                continue
            leads.create({
                "name": name[:200],
                "company": (data.get("company") or "")[:200],
                "email": email[:200],
                "phone": clean_phone(phone)[:40],
                "whatsapp": wa_number(data.get("whatsapp") or phone),
                "city": (data.get("city") or "")[:120],
                "service_interest": (data.get("service") or data.get("service_interest") or "")[:200],
                "budget_band": (data.get("budget") or "")[:120],
                "message": (data.get("message") or data.get("notes") or "")[:4000],
                "quote_value": parse_float(data.get("value") or data.get("quote_value"), 0),
                "source_id": source_id,
                "source_note": "CSV import",
            }, source="csv")
            added += 1
        audit.log("import", "leads", "", f"{added} added, {skipped} skipped")
        flash(f"Imported {added} lead(s). Skipped {skipped} "
              "(missing a name and any way to reach them, or already on file).", "ok")
        return redirect(url_for("admin.leads_list"))

    return render_template("admin/leads_import.html", title="Import leads",
                           columns=CSV_COLUMNS,
                           sources=db.query("SELECT * FROM lead_sources WHERE is_active = 1 ORDER BY sort_order"),
                           nav_active="admin.leads_list")
