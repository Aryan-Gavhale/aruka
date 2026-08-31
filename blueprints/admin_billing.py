"""Money: clients, invoices, payments, receipts, credit notes and renewals."""

from __future__ import annotations

import io
import csv

from flask import (Response, abort, flash, redirect, render_template, request, url_for)

from blueprints.admin import bp
from core import audit, billing, crud, db, numbering, pricing, settings
from core.auth import require_role, verify_csrf
from core.crud import Field, Resource
from core.util import (csv_cell, fy_bounds, fy_label, fy_start_year, money, parse_float,
                       parse_int, slugify, today_iso)
from services import pdf


# ── clients ─────────────────────────────────────────────────────────────────
@bp.route("/clients")
@require_role("billing")
def clients_list():
    query = (request.args.get("q") or "").strip()
    show = request.args.get("show") or "active"

    where, params = ["1 = 1"], []
    if show == "active":
        where.append("c.is_active = 1")
    elif show == "owing":
        where.append("EXISTS (SELECT 1 FROM invoices i WHERE i.client_id = c.id "
                     "AND i.status IN ('sent', 'part_paid', 'overdue'))")
    if query:
        where.append("(c.name LIKE ? OR c.contact_name LIKE ? OR c.email LIKE ? "
                     "OR c.phone LIKE ? OR c.ref LIKE ?)")
        params += [f"%{query}%"] * 5

    rows = db.query(
        f"""SELECT c.*,
                   (SELECT COUNT(*) FROM projects p WHERE p.client_id = c.id) AS projects,
                   (SELECT COALESCE(SUM(i.balance), 0) FROM invoices i
                      WHERE i.client_id = c.id
                        AND i.status IN ('sent', 'part_paid', 'overdue')) AS owing,
                   (SELECT COALESCE(SUM(p2.amount + p2.tds_amount), 0) FROM payments p2
                      WHERE p2.client_id = c.id AND p2.voided_at IS NULL) AS collected,
                   (SELECT COUNT(*) FROM tickets t WHERE t.client_id = c.id
                        AND t.status NOT IN ('resolved', 'closed')) AS open_tickets
            FROM clients c
            WHERE {' AND '.join(where)}
            ORDER BY c.name""", tuple(params))

    return render_template("admin/clients_list.html", title="Clients", rows=rows, q=query,
                           show=show, nav_active="admin.clients_list")


@bp.route("/clients/new", methods=["GET", "POST"])
@require_role("billing")
def client_new():
    if request.method == "POST":
        verify_csrf()
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("A client needs a name.", "error")
        else:
            client_id = db.insert("clients", {
                **_read_client_form(request.form),
                "ref": numbering.take("client"),
            })
            audit.log("create", "clients", client_id, name)
            flash("Client added.", "ok")
            return redirect(url_for("admin.client_detail", client_id=client_id))
    return render_template("admin/client_form.html", title="New client", client=None,
                           states=INDIAN_STATES, nav_active="admin.clients_list")


INDIAN_STATES = [
    ("01", "Jammu and Kashmir"), ("02", "Himachal Pradesh"), ("03", "Punjab"),
    ("04", "Chandigarh"), ("05", "Uttarakhand"), ("06", "Haryana"), ("07", "Delhi"),
    ("08", "Rajasthan"), ("09", "Uttar Pradesh"), ("10", "Bihar"), ("11", "Sikkim"),
    ("12", "Arunachal Pradesh"), ("13", "Nagaland"), ("14", "Manipur"), ("15", "Mizoram"),
    ("16", "Tripura"), ("17", "Meghalaya"), ("18", "Assam"), ("19", "West Bengal"),
    ("20", "Jharkhand"), ("21", "Odisha"), ("22", "Chhattisgarh"), ("23", "Madhya Pradesh"),
    ("24", "Gujarat"), ("26", "Dadra and Nagar Haveli and Daman and Diu"),
    ("27", "Maharashtra"), ("29", "Karnataka"), ("30", "Goa"), ("31", "Lakshadweep"),
    ("32", "Kerala"), ("33", "Tamil Nadu"), ("34", "Puducherry"), ("35", "Andaman and Nicobar"),
    ("36", "Telangana"), ("37", "Andhra Pradesh"), ("38", "Ladakh"),
]

STATE_NAMES = dict(INDIAN_STATES)


def _read_client_form(form) -> dict:
    from core.util import clean_phone, wa_number

    state_code = (form.get("state_code") or "").strip()
    return {
        "name": (form.get("name") or "").strip()[:200],
        "legal_name": (form.get("legal_name") or "").strip()[:200],
        "gstin": (form.get("gstin") or "").strip().upper()[:20],
        "pan": (form.get("pan") or "").strip().upper()[:12],
        "contact_name": (form.get("contact_name") or "").strip()[:200],
        "email": (form.get("email") or "").strip()[:200],
        "phone": clean_phone(form.get("phone") or "")[:40],
        "whatsapp": wa_number(form.get("whatsapp") or form.get("phone") or ""),
        "billing_address": (form.get("billing_address") or "").strip()[:600],
        "city": (form.get("city") or "").strip()[:120],
        "state_code": state_code,
        "state": STATE_NAMES.get(state_code, (form.get("state") or "").strip())[:120],
        "pincode": (form.get("pincode") or "").strip()[:10],
        "website": (form.get("website") or "").strip()[:200],
        "sector": (form.get("sector") or "").strip()[:120],
        "notes": (form.get("notes") or "").strip()[:4000],
        "opt_out": 1 if form.get("opt_out") else 0,
        "is_active": 1 if form.get("is_active") else 0,
    }


@bp.route("/clients/<int:client_id>", methods=["GET", "POST"])
@require_role("billing")
def client_detail(client_id):
    client = db.one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if not client:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        data = _read_client_form(request.form)
        db.update("clients", client_id, {**data,
                                         "updated_at": db.scalar("SELECT datetime('now')")})
        audit.log("update", "clients", client_id, client["name"], before=client, after=data)
        flash("Client saved.", "ok")
        return redirect(url_for("admin.client_detail", client_id=client_id))

    return render_template(
        "admin/client_detail.html", title=client["name"], client=client,
        states=INDIAN_STATES, balance=billing.client_balance(client_id),
        projects=db.query("SELECT * FROM projects WHERE client_id = ? ORDER BY id DESC",
                          (client_id,)),
        invoices=db.query("SELECT * FROM invoices WHERE client_id = ? ORDER BY id DESC LIMIT 40",
                          (client_id,)),
        paymentz=db.query(
            "SELECT p.*, i.ref AS invoice_ref FROM payments p "
            "LEFT JOIN invoices i ON i.id = p.invoice_id "
            "WHERE p.client_id = ? ORDER BY p.paid_on DESC, p.id DESC LIMIT 30", (client_id,)),
        recurring=db.query(
            "SELECT * FROM recurring_items WHERE client_id = ? ORDER BY next_due_on", (client_id,)),
        assets=db.query("SELECT * FROM assets WHERE client_id = ? ORDER BY expires_on", (client_id,)),
        tickets_open=db.query(
            "SELECT * FROM tickets WHERE client_id = ? AND status NOT IN ('resolved', 'closed') "
            "ORDER BY id DESC", (client_id,)),
        contacts=db.query("SELECT * FROM contacts WHERE client_id = ? ORDER BY is_primary DESC, name",
                          (client_id,)),
        documents=db.query("SELECT * FROM documents WHERE client_id = ? ORDER BY id DESC LIMIT 20",
                           (client_id,)),
        supply=billing.supply_type_for(client), our_state=billing.our_state_code(),
        nav_active="admin.clients_list")


@bp.route("/clients/<int:client_id>/contacts", methods=["POST"])
@require_role("billing")
def client_contact_add(client_id):
    verify_csrf()
    from core.util import clean_phone, wa_number

    name = (request.form.get("name") or "").strip()
    if not name:
        flash("A contact needs a name.", "error")
        return redirect(url_for("admin.client_detail", client_id=client_id))
    db.insert("contacts", {
        "client_id": client_id,
        "name": name[:200],
        "role": (request.form.get("role") or "").strip()[:120],
        "email": (request.form.get("email") or "").strip()[:200],
        "phone": clean_phone(request.form.get("phone") or "")[:40],
        "whatsapp": wa_number(request.form.get("whatsapp") or request.form.get("phone") or ""),
        "is_primary": 1 if request.form.get("is_primary") else 0,
        "portal_access": 1 if request.form.get("portal_access") else 0,
    })
    flash("Contact added. They can sign in to the portal with that email.", "ok")
    return redirect(url_for("admin.client_detail", client_id=client_id))


@bp.route("/clients/<int:client_id>/contacts/<int:contact_id>/delete", methods=["POST"])
@require_role("billing")
def client_contact_delete(client_id, contact_id):
    verify_csrf()
    db.execute("DELETE FROM contacts WHERE id = ? AND client_id = ?", (contact_id, client_id))
    flash("Contact removed.", "ok")
    return redirect(url_for("admin.client_detail", client_id=client_id))


@bp.route("/clients/<int:client_id>/delete", methods=["POST"])
@require_role("owner")
def client_delete(client_id):
    verify_csrf()
    client = db.one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if not client:
        abort(404)
    issued = parse_int(db.scalar(
        "SELECT COUNT(*) FROM invoices WHERE client_id = ? AND status != 'draft'",
        (client_id,), 0))
    if issued:
        flash(f"This client has {issued} issued invoice(s). Deactivate them instead - "
              "deleting would remove numbered documents from the record.", "error")
        return redirect(url_for("admin.client_detail", client_id=client_id))
    db.delete("clients", client_id)
    audit.log("delete", "clients", client_id, client["name"], before=client)
    flash("Client deleted.", "ok")
    return redirect(url_for("admin.clients_list"))


# ── invoices ────────────────────────────────────────────────────────────────
@bp.route("/invoices")
@require_role("billing")
def invoices_list():
    status = request.args.get("status") or ""
    client_id = parse_int(request.args.get("client"), 0) or None
    fy = parse_int(request.args.get("fy"), 0) or None
    query = (request.args.get("q") or "").strip()

    where, params = ["1 = 1"], []
    if status == "open":
        where.append("i.status IN ('sent', 'part_paid', 'overdue')")
    elif status:
        where.append("i.status = ?")
        params.append(status)
    if client_id:
        where.append("i.client_id = ?")
        params.append(client_id)
    if fy:
        where.append("i.issued_on >= ? AND i.issued_on < ?")
        params += [f"{fy}-04-01", f"{fy + 1}-04-01"]
    if query:
        where.append("(i.ref LIKE ? OR c.name LIKE ? OR i.notes LIKE ?)")
        params += [f"%{query}%"] * 3

    rows = db.query(
        f"""SELECT i.*, c.name AS client_name, c.whatsapp AS client_whatsapp,
                   p.name AS project_name
            FROM invoices i JOIN clients c ON c.id = i.client_id
            LEFT JOIN projects p ON p.id = i.project_id
            WHERE {' AND '.join(where)}
            ORDER BY i.id DESC LIMIT 400""", tuple(params))

    totals = {
        "invoiced": sum(parse_float(r["total"]) for r in rows),
        "outstanding": sum(parse_float(r["balance"]) for r in rows),
        "collected": sum(parse_float(r["amount_paid"]) + parse_float(r["tds_amount"])
                         for r in rows),
    }

    return render_template(
        "admin/invoices_list.html", title="Invoices", rows=rows, status=status, q=query,
        client_id=client_id, fy=fy, totals=totals,
        years=list(range(fy_start_year() - 4, fy_start_year() + 1)),
        clients=db.query("SELECT id, name FROM clients ORDER BY name"),
        counts={r["status"]: r["n"] for r in db.query(
            "SELECT status, COUNT(*) AS n FROM invoices GROUP BY status")},
        nav_active="admin.invoices_list")


@bp.route("/invoices/new", methods=["GET", "POST"])
@require_role("billing")
def invoice_new():
    client_id = parse_int(request.args.get("client_id"), 0) or None
    quote_id = parse_int(request.args.get("quote_id"), 0) or None
    project_id = parse_int(request.args.get("project_id"), 0) or None

    if request.method == "POST":
        verify_csrf()
        client_id = parse_int(request.form.get("client_id"), 0) or None
        if not client_id:
            flash("Pick a client.", "error")
            return redirect(request.url)

        source_quote = parse_int(request.form.get("quote_id"), 0) or None
        try:
            if source_quote and request.form.get("from_quote"):
                invoice_id = billing.from_quote(
                    source_quote, client_id,
                    project_id=parse_int(request.form.get("project_id"), 0) or None,
                    share_pct=parse_float(request.form.get("share_pct"), 100))
            else:
                items = _read_line_items(request.form)
                if not items:
                    flash("An invoice needs at least one line.", "error")
                    return redirect(request.url)
                invoice_id = billing.create(
                    client_id,
                    kind=request.form.get("kind") or "invoice",
                    project_id=parse_int(request.form.get("project_id"), 0) or None,
                    quote_id=source_quote,
                    line_items=items,
                    notes=(request.form.get("notes") or "").strip(),
                    issued_on=(request.form.get("issued_on") or "").strip(),
                    terms_days=parse_int(request.form.get("terms_days"),
                                         parse_int(settings.get("invoice.terms_days"), 7)))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(request.url)

        flash("Draft raised. Check it, then issue it to take a number.", "ok")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))

    return render_template(
        "admin/invoice_form.html", title="New invoice",
        client=db.one("SELECT * FROM clients WHERE id = ?", (client_id,)) if client_id else None,
        quote=pricing.get_quote(quote_id) if quote_id else None,
        quote_lines=pricing.quote_lines(quote_id) if quote_id else [],
        project=db.one("SELECT * FROM projects WHERE id = ?", (project_id,)) if project_id else None,
        clients=db.query("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name"),
        projects=db.query("SELECT id, name, client_id FROM projects ORDER BY id DESC"),
        quotes=db.query("SELECT id, ref, title, total, client_id FROM quotes "
                        "WHERE status IN ('accepted', 'sent') ORDER BY id DESC LIMIT 50"),
        gst=settings.gst_on(), mode_label=billing.doc_mode_label(),
        default_sac=settings.get("gst.default_sac"),
        tax_rate=billing.default_tax_rate(), nav_active="admin.invoices_list")


def _read_line_items(form) -> list[dict]:
    """Read the repeated line inputs the invoice editor posts."""
    items = []
    for index in range(0, 40):
        label = (form.get(f"line_label_{index}") or "").strip()
        if not label:
            continue
        items.append({
            "label": label,
            "description": (form.get(f"line_description_{index}") or "").strip(),
            "hsn_sac": (form.get(f"line_hsn_{index}") or "").strip(),
            "qty": parse_float(form.get(f"line_qty_{index}"), 1),
            "unit": (form.get(f"line_unit_{index}") or "each").strip(),
            "unit_price": parse_float(form.get(f"line_price_{index}"), 0),
            "discount_pct": parse_float(form.get(f"line_discount_{index}"), 0),
            "tax_rate": parse_float(form.get(f"line_tax_{index}"), billing.default_tax_rate()),
        })
    return items


@bp.route("/invoices/<int:invoice_id>", methods=["GET", "POST"])
@require_role("billing")
def invoice_detail(invoice_id):
    invoice = billing.get(invoice_id)
    if not invoice:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        changes = {
            "notes": (request.form.get("notes") or "").strip(),
            "terms": (request.form.get("terms") or "").strip(),
            "due_on": (request.form.get("due_on") or "").strip() or None,
        }
        if invoice["status"] == "draft":
            changes["issued_on"] = (request.form.get("issued_on") or invoice["issued_on"])
        db.update("invoices", invoice_id, changes)
        billing.recalc(invoice_id)
        flash("Invoice saved.", "ok")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))

    client = db.one("SELECT * FROM clients WHERE id = ?", (invoice["client_id"],))
    stage = billing.dunning_stage_for(invoice) if invoice["status"] in billing.OPEN_STATUSES \
        else None
    return render_template(
        "admin/invoice_detail.html", title=invoice["ref"], invoice=invoice, client=client,
        lines=billing.lines(invoice_id),
        paymentz=billing.payments_for(invoice_id, include_void=True),
        credits=db.query("SELECT * FROM credit_notes WHERE invoice_id = ? ORDER BY id DESC",
                         (invoice_id,)),
        project=db.one("SELECT * FROM projects WHERE id = ?", (invoice["project_id"],))
        if invoice["project_id"] else None,
        methods=billing.PAYMENT_METHODS, dunning=stage, ladder=billing.DUNNING_LADDER,
        gst=invoice["doc_mode"] == "tax_invoice", tax_rate=billing.default_tax_rate(),
        nav_active="admin.invoices_list")


@bp.route("/invoices/<int:invoice_id>/lines", methods=["POST"])
@require_role("billing")
def invoice_line_add(invoice_id):
    verify_csrf()
    invoice = billing.get(invoice_id)
    if not invoice:
        abort(404)
    if invoice["status"] != "draft" and not request.form.get("force"):
        flash("This invoice has been issued. Add a line only if it has not left your hands - "
              "otherwise raise a credit note and a fresh invoice.", "error")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))

    label = (request.form.get("label") or "").strip()
    if not label:
        flash("A line needs a label.", "error")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))
    billing.add_line(invoice_id, {
        "label": label,
        "description": (request.form.get("description") or "").strip(),
        "hsn_sac": (request.form.get("hsn_sac") or "").strip(),
        "qty": parse_float(request.form.get("qty"), 1),
        "unit": (request.form.get("unit") or "each").strip(),
        "unit_price": parse_float(request.form.get("unit_price"), 0),
        "discount_pct": parse_float(request.form.get("discount_pct"), 0),
        "tax_rate": parse_float(request.form.get("tax_rate"), billing.default_tax_rate()),
    })
    billing.recalc(invoice_id)
    flash("Line added.", "ok")
    return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/lines/<int:line_id>/delete", methods=["POST"])
@require_role("billing")
def invoice_line_delete(invoice_id, line_id):
    verify_csrf()
    db.execute("DELETE FROM invoice_lines WHERE id = ? AND invoice_id = ?", (line_id, invoice_id))
    billing.recalc(invoice_id)
    flash("Line removed.", "ok")
    return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/issue", methods=["POST"])
@require_role("billing")
def invoice_issue(invoice_id):
    verify_csrf()
    try:
        ref = billing.issue(invoice_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))
    flash(f"Issued as {ref}. That number is now used and cannot be reused.", "ok")
    return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/cancel", methods=["POST"])
@require_role("money")
def invoice_cancel(invoice_id):
    verify_csrf()
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Say why. A cancelled invoice without a reason is a hole in your records.",
              "error")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))
    try:
        billing.cancel(invoice_id, reason)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))
    flash("Cancelled. The number stays used so the series has no gap.", "ok")
    return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/writeoff", methods=["POST"])
@require_role("money")
def invoice_writeoff(invoice_id):
    verify_csrf()
    amount = parse_float(request.form.get("amount"), 0)
    reason = (request.form.get("reason") or "").strip()
    if amount <= 0 or not reason:
        flash("A write-off needs both an amount and a reason.", "error")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))
    billing.write_off(invoice_id, amount, reason)
    flash(f"Wrote off {money(amount)}. It stays visible on the invoice as a record.", "ok")
    return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))


@bp.route("/invoices/<int:invoice_id>/credit", methods=["POST"])
@require_role("money")
def invoice_credit(invoice_id):
    verify_csrf()
    amount = parse_float(request.form.get("amount"), 0)
    reason = (request.form.get("reason") or "").strip()
    if amount <= 0 or not reason:
        flash("A credit note needs both an amount and a reason.", "error")
        return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))
    note_id = billing.credit_note(invoice_id, amount, reason)
    flash("Credit note raised.", "ok")
    return redirect(url_for("admin.credit_note_pdf", note_id=note_id))


@bp.route("/invoices/<int:invoice_id>/pdf")
@require_role("billing")
def invoice_pdf(invoice_id):
    invoice = billing.get(invoice_id)
    if not invoice:
        abort(404)
    payload = pdf.invoice_pdf(invoice)
    name = "%s-%s.pdf" % (slugify(settings.get("brand.name") or "aruka"), invoice["ref"])
    inline = request.args.get("download") != "1"
    return Response(payload, mimetype="application/pdf", headers={
        "Content-Disposition": "%s; filename=%s" % ("inline" if inline else "attachment", name),
        "Cache-Control": "no-store"})


@bp.route("/invoices/<int:invoice_id>/reminded", methods=["POST"])
@require_role("billing")
def invoice_reminded(invoice_id):
    verify_csrf()
    billing.mark_reminded(invoice_id, parse_int(request.form.get("stage"), 0))
    flash("Logged as reminded, so the dunning ladder moves on.", "ok")
    return redirect(request.referrer or url_for("admin.invoice_detail", invoice_id=invoice_id))


# ── payments and receipts ───────────────────────────────────────────────────
@bp.route("/payments")
@require_role("billing")
def payments_list():
    fy = parse_int(request.args.get("fy"), 0) or fy_start_year()
    rows = db.query(
        """SELECT p.*, c.name AS client_name, i.ref AS invoice_ref
           FROM payments p JOIN clients c ON c.id = p.client_id
           LEFT JOIN invoices i ON i.id = p.invoice_id
           WHERE p.paid_on >= ? AND p.paid_on < ?
           ORDER BY p.paid_on DESC, p.id DESC""",
        (f"{fy}-04-01", f"{fy + 1}-04-01"))
    live = [r for r in rows if not r["voided_at"]]
    return render_template(
        "admin/payments_list.html", title="Payments received", rows=rows,
        total=sum(parse_float(r["amount"]) for r in live),
        tds=sum(parse_float(r["tds_amount"]) for r in live),
        fy=fy_label(f"{fy}-04-01"), start_year=fy,
        years=list(range(fy_start_year() - 4, fy_start_year() + 1)),
        nav_active="admin.payments_list")


@bp.route("/payments/new", methods=["POST"])
@require_role("billing")
def payment_new():
    verify_csrf()
    invoice_id = parse_int(request.form.get("invoice_id"), 0) or None
    try:
        payment_id = billing.record_payment(
            invoice_id,
            parse_float(request.form.get("amount"), 0),
            method=request.form.get("method") or "UPI",
            reference=(request.form.get("reference") or "").strip(),
            paid_on=(request.form.get("paid_on") or today_iso()).strip(),
            notes=(request.form.get("notes") or "").strip(),
            tds_amount=parse_float(request.form.get("tds_amount"), 0),
            client_id=parse_int(request.form.get("client_id"), 0) or None,
            is_advance=bool(request.form.get("is_advance")))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("admin.invoices_list"))

    payment = db.one("SELECT * FROM payments WHERE id = ?", (payment_id,))
    flash(f"Recorded. Receipt {payment['ref']} is ready to send.", "ok")
    return redirect(url_for("admin.payment_detail", payment_id=payment_id))


@bp.route("/payments/<int:payment_id>")
@require_role("billing")
def payment_detail(payment_id):
    payment = db.one("SELECT * FROM payments WHERE id = ?", (payment_id,))
    if not payment:
        abort(404)
    return render_template(
        "admin/payment_detail.html", title=payment["ref"], payment=payment,
        client=db.one("SELECT * FROM clients WHERE id = ?", (payment["client_id"],)),
        invoice=billing.get(payment["invoice_id"]) if payment["invoice_id"] else None,
        nav_active="admin.payments_list")


@bp.route("/payments/<int:payment_id>/void", methods=["POST"])
@require_role("money")
def payment_void(payment_id):
    verify_csrf()
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Voiding money needs a reason on the record.", "error")
        return redirect(url_for("admin.payment_detail", payment_id=payment_id))
    billing.void_payment(payment_id, reason)
    flash("Voided. The receipt stays in the list, marked void.", "ok")
    return redirect(url_for("admin.payment_detail", payment_id=payment_id))


@bp.route("/payments/<int:payment_id>/pdf")
@require_role("billing")
def receipt_pdf(payment_id):
    payment = db.one("SELECT * FROM payments WHERE id = ?", (payment_id,))
    if not payment:
        abort(404)
    payload = pdf.receipt_pdf(payment)
    return Response(payload, mimetype="application/pdf", headers={
        "Content-Disposition": f"inline; filename=receipt-{payment['ref']}.pdf",
        "Cache-Control": "no-store"})


@bp.route("/credit-notes/<int:note_id>/pdf")
@require_role("billing")
def credit_note_pdf(note_id):
    note = db.one("SELECT * FROM credit_notes WHERE id = ?", (note_id,))
    if not note:
        abort(404)
    payload = pdf.credit_note_pdf(note)
    return Response(payload, mimetype="application/pdf", headers={
        "Content-Disposition": f"inline; filename=credit-note-{note['ref']}.pdf",
        "Cache-Control": "no-store"})


# ── receivables ─────────────────────────────────────────────────────────────
@bp.route("/receivables")
@require_role("billing")
def receivables():
    aging = billing.aging()
    return render_template(
        "admin/receivables.html", title="Receivables", aging=aging,
        reminders=billing.due_reminders(), ladder=billing.DUNNING_LADDER,
        nav_active="admin.receivables")


# ── recurring items and renewals ────────────────────────────────────────────
RECURRING = Resource(
    key="recurring", table="recurring_items", label="Recurring item",
    label_plural="Recurring and renewals", area="billing", row_label="label",
    activatable=True, order_by="next_due_on", searchable=("label", "notes"), icon="refresh",
    intro="Hosting, domains, care plans, SEO retainers - anything that comes round again. "
          "These drive the renewal invoices and the reminders, and they are what makes the "
          "MRR figure on the dashboard real rather than a guess.",
    list_columns=[("label", "Item"), ("kind", "Kind"), ("amount", "Amount"),
                  ("period", "Every"), ("next_due_on", "Next due")],
    fields=[
        Field("client_id", "Client", "select", required=True, span=6,
              options=lambda: [(r["id"], r["name"]) for r in db.query(
                  "SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name")]),
        Field("project_id", "Project", "select", span=6,
              options=lambda: [("", "Not tied to a project")] + [
                  (r["id"], f"{r['ref']} - {r['name']}") for r in db.query(
                      "SELECT id, ref, name FROM projects ORDER BY id DESC")]),
        Field("label", "What it is", "text", required=True, span=8,
              help="How it reads on the renewal invoice. For example: hosting and domain "
                   "for example.com."),
        Field("kind", "Kind", "select", span=4, default="hosting",
              options=lambda: list(billing.RECURRING_KINDS.items())),

        Field("money_head", "Money", "heading"),
        Field("amount", "Amount per period", "money", span=4, required=True),
        Field("internal_cost", "Your cost per period", "money", span=4, owner_only=True,
              help="What the registrar or host charges you. The difference is the real margin "
                   "on renewals, which is where quiet money lives."),
        Field("period", "Every", "select", span=4, default="yearly",
              options=[("monthly", "Month"), ("quarterly", "Quarter"),
                       ("half_yearly", "Six months"), ("yearly", "Year")]),

        Field("dates_head", "Dates", "heading"),
        Field("starts_on", "Started on", "date", span=4),
        Field("next_due_on", "Next due on", "date", span=4, required=True),
        Field("ends_on", "Stops after", "date", span=4,
              help="Leave blank to run indefinitely."),
        Field("auto_invoice", "Raise the invoice automatically", "bool", span=6,
              help="Off by default. A renewal invoice going out without you seeing it is how "
                   "a client gets billed for something they cancelled last month."),
        Field("is_active", "Active", "bool", span=6, default=1),
        Field("notes", "Notes", "textarea", rows=3, span=12),
    ],
)

crud.register(bp, RECURRING)


@bp.route("/renewals")
@require_role("billing")
def renewals():
    notice = parse_int(settings.get("ops.renewal_notice_days"), 21)
    return render_template(
        "admin/renewals.html", title="Renewals", notice=notice,
        due=billing.recurring_due(notice),
        later=db.query(
            "SELECT r.*, c.name AS client_name FROM recurring_items r "
            "JOIN clients c ON c.id = r.client_id WHERE r.is_active = 1 "
            "AND r.next_due_on > date('now', ?) ORDER BY r.next_due_on LIMIT 40",
            (f"+{notice} days",)),
        mrr=billing.mrr(), nav_active="admin.recurring_list")


@bp.route("/renewals/<int:recurring_id>/invoice", methods=["POST"])
@require_role("billing")
def renewal_invoice(recurring_id):
    verify_csrf()
    try:
        invoice_id = billing.invoice_recurring(recurring_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.renewals"))
    flash("Renewal invoice drafted and the next due date rolled forward.", "ok")
    return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))


# ── milestone billing ───────────────────────────────────────────────────────
@bp.route("/milestones/<int:milestone_id>/invoice", methods=["POST"])
@require_role("billing")
def milestone_invoice(milestone_id):
    verify_csrf()
    try:
        invoice_id = billing.invoice_milestone(milestone_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("admin.invoices_list"))
    flash("Invoice drafted for that milestone.", "ok")
    return redirect(url_for("admin.invoice_detail", invoice_id=invoice_id))


# ── export ──────────────────────────────────────────────────────────────────
@bp.route("/invoices/export")
@require_role("billing")
def invoices_export():
    fy = parse_int(request.args.get("fy"), 0) or fy_start_year()
    since, until = f"{fy}-04-01", f"{fy + 1}-04-01"
    rows = db.query(
        """SELECT i.*, c.name AS client_name, c.gstin AS client_gstin
           FROM invoices i JOIN clients c ON c.id = i.client_id
           WHERE i.status != 'draft' AND i.issued_on >= ? AND i.issued_on < ?
           ORDER BY i.issued_on, i.id""", (since, until))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(("Invoice", "Date", "Client", "GSTIN", "Place of supply", "Type",
                     "Taxable", "CGST", "SGST", "IGST", "Total", "Received", "TDS",
                     "Balance", "Status"))
    for row in rows:
        writer.writerow([
            csv_cell(row["ref"]), csv_cell(row["issued_on"]), csv_cell(row["client_name"]),
            csv_cell(row["client_gstin"]), csv_cell(row["place_of_supply"]),
            csv_cell("Inter-state" if row["supply_type"] == "inter" else "Intra-state"),
            row["taxable_value"], row["cgst"], row["sgst"], row["igst"], row["total"],
            row["amount_paid"], row["tds_amount"], row["balance"], csv_cell(row["status"]),
        ])
    audit.log("export", "invoices", "", f"FY {fy} - {len(rows)} invoices")
    return Response(buffer.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="aruka-invoices-fy{fy}.csv"'})
