"""The ledger: invoices, payments, receipts, credit notes, aging and renewals.

There is no payment gateway. Every rupee is recorded by hand with a method and a
reference, and the app issues the numbered receipt - which means the balance on an
invoice is only ever the sum of live payments against it, never a gateway's
opinion. `recalc(invoice_id)` is the single place that derives status and balance,
so no route has to remember the rules.

GST: `gst.mode` decides whether an invoice is a **bill of supply** (no tax, what an
unregistered supplier must issue) or a **tax invoice**. In tax-invoice mode the
place of supply against our own state code decides CGST+SGST for an intra-state
supply or IGST for inter-state, which is the split the return actually asks for.
"""

from __future__ import annotations

from datetime import date

from core import audit, db, numbering, settings
from core.util import (add_days, add_months, dump_json, gstin_state_code, money2,
                       parse_date, parse_float, parse_int, pct, today_iso)

INVOICE_STATUS_LABELS = {
    "draft": "Draft",
    "sent": "Sent",
    "part_paid": "Part paid",
    "paid": "Paid",
    "overdue": "Overdue",
    "written_off": "Written off",
    "cancelled": "Cancelled",
}
OPEN_STATUSES = ("sent", "part_paid", "overdue")

KIND_LABELS = {
    "invoice": "Tax invoice / Bill of supply",
    "proforma": "Proforma invoice",
}

PAYMENT_METHODS = ("UPI", "Bank transfer (NEFT/IMPS)", "Cheque", "Cash", "Card", "Other")

RECURRING_KINDS = {
    "hosting": "Hosting",
    "domain": "Domain",
    "amc": "Care plan (AMC)",
    "seo": "SEO retainer",
    "support": "Priority support",
    "licence": "Third-party licence",
    "other": "Other",
}

PERIOD_MONTHS = {"monthly": 1, "quarterly": 3, "half_yearly": 6, "yearly": 12}


# ── tax helpers ─────────────────────────────────────────────────────────────
def our_state_code() -> str:
    code = (settings.get("gst.state_code") or "").strip()
    if code:
        return code
    return gstin_state_code(settings.get("gst.gstin") or "")


def supply_type_for(client) -> str:
    """intra when the client sits in our state, inter otherwise.

    A client with no state recorded is treated as intra-state, because that is the
    conservative assumption for a local studio and it is visible on the invoice.
    """
    if not client:
        return "intra"
    theirs = (client["state_code"] or gstin_state_code(client["gstin"] or "")).strip()
    if not theirs:
        return "intra"
    return "intra" if theirs == our_state_code() else "inter"


def split_tax(taxable: float, rate: float, supply_type: str) -> dict:
    """CGST+SGST for intra-state, IGST for inter-state. Rate is the total rate."""
    total = round(taxable * rate / 100.0, 2)
    if rate <= 0:
        return {"cgst": 0.0, "sgst": 0.0, "igst": 0.0, "tax_amount": 0.0}
    if supply_type == "inter":
        return {"cgst": 0.0, "sgst": 0.0, "igst": total, "tax_amount": total}
    half = round(total / 2, 2)
    # Any half-paisa remainder goes to SGST so the two halves always add to total.
    return {"cgst": half, "sgst": round(total - half, 2), "igst": 0.0, "tax_amount": total}


def default_tax_rate() -> float:
    return parse_float(settings.get("gst.default_rate"), 18) if settings.gst_on() else 0.0


def doc_mode() -> str:
    return "tax_invoice" if settings.gst_on() else "bill_of_supply"


def doc_mode_label(mode: str = "") -> str:
    mode = mode or doc_mode()
    return "Tax invoice" if mode == "tax_invoice" else "Bill of supply"


# ── invoices ────────────────────────────────────────────────────────────────
def get(invoice_id):
    return db.one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))


def lines(invoice_id):
    return db.query(
        "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY sort_order, id", (invoice_id,))


def payments_for(invoice_id, include_void: bool = False):
    sql = "SELECT * FROM payments WHERE invoice_id = ?"
    if not include_void:
        sql += " AND voided_at IS NULL"
    return db.query(sql + " ORDER BY paid_on, id", (invoice_id,))


def create(client_id, *, kind: str = "invoice", project_id=None, quote_id=None,
           milestone_id=None, recurring_id=None, ticket_id=None,
           line_items: list[dict] | None = None, notes: str = "",
           issued_on: str = "", terms_days: int | None = None) -> int:
    """Raise an invoice in draft. Numbers are only consumed when it is issued, so a
    cancelled draft never leaves a hole in the series."""
    client = db.one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if not client:
        raise ValueError("client not found")

    issued = issued_on or today_iso()
    days = parse_int(settings.get("invoice.terms_days"), 7) if terms_days is None else terms_days
    supply = supply_type_for(client)

    with db.transaction():
        invoice_id = db.insert("invoices", {
            "ref": f"DRAFT-{db.scalar('SELECT COALESCE(MAX(id), 0) + 1 FROM invoices', (), 1)}",
            "kind": kind,
            "doc_mode": doc_mode(),
            "client_id": client_id,
            "project_id": project_id,
            "quote_id": quote_id,
            "milestone_id": milestone_id,
            "recurring_id": recurring_id,
            "ticket_id": ticket_id,
            "status": "draft",
            "place_of_supply": client["state"] or settings.get("brand.state") or "",
            "supply_type": supply,
            "issued_on": issued,
            "due_on": add_days(parse_date(issued) or date.today(), days).isoformat(),
            "notes": notes,
            "terms": settings.get("invoice.footer_note") or "",
        })
        for index, item in enumerate(line_items or []):
            add_line(invoice_id, item, index)
        recalc(invoice_id)
    audit.log("create", "invoices", invoice_id, f"{kind} for {client['name']}")
    return invoice_id


def add_line(invoice_id, item: dict, index: int | None = None) -> int:
    qty = parse_float(item.get("qty"), 1) or 1
    unit_price = parse_float(item.get("unit_price"), 0)
    discount_pct = parse_float(item.get("discount_pct"), 0)
    gross = qty * unit_price
    amount = round(gross - gross * discount_pct / 100.0, 2)
    return db.insert("invoice_lines", {
        "invoice_id": invoice_id,
        "label": (item.get("label") or "Item")[:300],
        "description": item.get("description") or "",
        "hsn_sac": item.get("hsn_sac") or (settings.get("gst.default_sac") if settings.gst_on() else ""),
        "qty": qty,
        "unit": item.get("unit") or "each",
        "unit_price": unit_price,
        "discount_pct": discount_pct,
        "amount": amount,
        "tax_rate": parse_float(item.get("tax_rate"), default_tax_rate()),
        "sort_order": index if index is not None else db.next_sort_order(
            "invoice_lines", "invoice_id = ?", (invoice_id,)),
    })


def from_quote(quote_id, client_id=None, *, project_id=None, milestone_id=None,
               share_pct: float = 100.0, label_prefix: str = "") -> int:
    """Turn quote lines into an invoice. `share_pct` bills one milestone's slice of
    the same lines rather than re-typing them."""
    from core import pricing

    quote = pricing.get_quote(quote_id)
    if not quote:
        raise ValueError("quote not found")
    client_id = client_id or quote["client_id"]
    if not client_id:
        raise ValueError("that quote has no client yet")

    share = max(0.0, min(100.0, parse_float(share_pct, 100)))
    items = []
    for line in pricing.quote_lines(quote_id):
        if line["is_recurring"] or parse_float(line["amount"]) == 0:
            continue
        amount = parse_float(line["amount"]) * share / 100.0
        items.append({
            "label": (label_prefix + line["label"]) if label_prefix else line["label"],
            "description": line["description"],
            "qty": 1,
            "unit": line["unit"],
            "unit_price": round(amount, 2),
            "tax_rate": default_tax_rate(),
        })
    if not items:
        raise ValueError("that quote has no billable lines")

    return create(client_id, project_id=project_id or quote["project_id"],
                  quote_id=quote_id, milestone_id=milestone_id, line_items=items,
                  notes=f"Against quote {quote['ref']}.")


def recalc(invoice_id) -> None:
    """Derive every total, the tax split, the balance and the status.

    The only place that decides whether an invoice is overdue, part paid or closed.
    """
    invoice = get(invoice_id)
    if not invoice:
        return
    rows = lines(invoice_id)
    subtotal = round(sum(parse_float(r["amount"]) for r in rows), 2)

    taxable = round(subtotal - parse_float(invoice["discount_amount"]), 2)
    rate = max([parse_float(r["tax_rate"]) for r in rows], default=0.0)
    if invoice["doc_mode"] != "tax_invoice":
        rate = 0.0
    tax = split_tax(taxable, rate, invoice["supply_type"] or "intra")

    gross = taxable + tax["tax_amount"]
    total = round(gross)
    round_off = round(total - gross, 2)

    paid = parse_float(db.scalar(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE invoice_id = ? AND voided_at IS NULL",
        (invoice_id,), 0))
    tds = parse_float(db.scalar(
        "SELECT COALESCE(SUM(tds_amount), 0) FROM payments WHERE invoice_id = ? AND voided_at IS NULL",
        (invoice_id,), 0))
    credited = parse_float(db.scalar(
        "SELECT COALESCE(SUM(amount), 0) FROM credit_notes WHERE invoice_id = ?", (invoice_id,), 0))
    written = parse_float(invoice["written_off"])

    balance = round(total - paid - tds - credited - written, 2)
    if abs(balance) < 1:      # a rupee of rounding is settled, not outstanding
        balance = 0.0

    status = invoice["status"]
    if invoice["cancelled_at"]:
        status = "cancelled"
    elif written and balance <= 0:
        status = "written_off"
    elif balance <= 0 and (paid or credited or tds):
        status = "paid"
    elif status != "draft":
        overdue = invoice["due_on"] and invoice["due_on"] < today_iso()
        if paid > 0:
            status = "overdue" if overdue else "part_paid"
        else:
            status = "overdue" if overdue else "sent"

    closed_at = invoice["closed_at"]
    if status in ("paid", "written_off") and not closed_at:
        closed_at = db.scalar("SELECT datetime('now')")
    elif status not in ("paid", "written_off"):
        closed_at = None

    db.update("invoices", invoice_id, {
        "subtotal": subtotal,
        "taxable_value": taxable,
        "cgst": tax["cgst"], "sgst": tax["sgst"], "igst": tax["igst"],
        "tax_amount": tax["tax_amount"],
        "round_off": round_off,
        "total": float(total),
        "amount_paid": paid,
        "tds_amount": tds,
        "balance": balance,
        "status": status,
        "closed_at": closed_at,
        "updated_at": db.scalar("SELECT datetime('now')"),
    })


def issue(invoice_id) -> str:
    """Move a draft to sent and consume its number from the FY series."""
    invoice = get(invoice_id)
    if not invoice:
        raise ValueError("invoice not found")
    if invoice["status"] != "draft":
        return invoice["ref"]
    if not lines(invoice_id):
        raise ValueError("an invoice needs at least one line before it is issued")

    series = "proforma" if invoice["kind"] == "proforma" else "invoice"
    ref = numbering.take(series, invoice["issued_on"])
    db.update("invoices", invoice_id, {
        "ref": ref,
        "status": "sent",
        "doc_mode": doc_mode(),
        "sent_at": db.scalar("SELECT datetime('now')"),
    })
    recalc(invoice_id)
    audit.log("update", "invoices", invoice_id, ref, after={"status": "sent", "ref": ref})
    _sync_milestone(invoice_id)
    return ref


def cancel(invoice_id, reason: str) -> None:
    """Cancelled, never deleted: the number stays used so the series has no gap."""
    invoice = get(invoice_id)
    if not invoice:
        return
    if payments_for(invoice_id):
        raise ValueError("payments exist against this invoice; void them first")
    db.update("invoices", invoice_id, {
        "cancelled_at": db.scalar("SELECT datetime('now')"),
        "cancel_reason": reason[:500] or "No reason given",
        "status": "cancelled",
        "balance": 0.0,
    })
    audit.log("update", "invoices", invoice_id, invoice["ref"],
              before={"status": invoice["status"]}, after={"status": "cancelled", "reason": reason})


def write_off(invoice_id, amount: float, reason: str) -> None:
    invoice = get(invoice_id)
    if not invoice:
        return
    db.update("invoices", invoice_id, {
        "written_off": round(parse_float(invoice["written_off"]) + parse_float(amount), 2),
        "notes": ((invoice["notes"] or "") + f"\nWritten off {parse_float(amount)}: {reason}").strip(),
    })
    recalc(invoice_id)
    audit.log("update", "invoices", invoice_id, invoice["ref"],
              after={"written_off": amount, "reason": reason})


# ── payments ────────────────────────────────────────────────────────────────
def record_payment(invoice_id, amount: float, *, method: str = "UPI", reference: str = "",
                   paid_on: str = "", notes: str = "", tds_amount: float = 0.0,
                   client_id=None, is_advance: bool = False) -> int:
    """Record money actually received and issue its receipt number.

    TDS is captured separately because a client who deducts it pays less than the
    invoice while still settling it in full - treating the shortfall as a balance
    would leave every corporate invoice looking unpaid forever.
    """
    invoice = get(invoice_id) if invoice_id else None
    if invoice and invoice["status"] == "cancelled":
        raise ValueError("that invoice is cancelled")
    client_id = client_id or (invoice["client_id"] if invoice else None)
    if not client_id:
        raise ValueError("a payment needs a client")
    if parse_float(amount) <= 0 and parse_float(tds_amount) <= 0:
        raise ValueError("a payment needs an amount")

    # Receipting more than is owed would leave a negative balance sitting on a closed
    # invoice, which reads as a refund nobody made. Money genuinely received ahead of
    # an invoice is an advance, taken without an invoice id.
    if invoice is not None and not is_advance:
        offered = round(parse_float(amount) + parse_float(tds_amount), 2)
        balance = parse_float(invoice["balance"])
        if offered > balance + 1:
            raise ValueError(
                f"That is more than the balance on {invoice['ref'] or 'this invoice'}. "
                f"{money2(balance)} is outstanding. Take the excess as an advance "
                f"receipt against the client instead.")

    when = paid_on or today_iso()
    with db.transaction():
        payment_id = db.insert("payments", {
            "ref": numbering.take("receipt", when),
            "invoice_id": invoice_id,
            "client_id": client_id,
            "amount": round(parse_float(amount), 2),
            "tds_amount": round(parse_float(tds_amount), 2),
            "method": method or "UPI",
            "reference": reference[:200],
            "paid_on": when,
            "is_advance": 1 if is_advance else 0,
            "notes": notes[:1000],
            "created_by": _actor(),
        })
        if invoice_id:
            recalc(invoice_id)
            _sync_milestone(invoice_id)
    audit.log("create", "payments", payment_id,
              f"{method} {parse_float(amount)}", after={"invoice_id": invoice_id})
    return payment_id


def void_payment(payment_id, reason: str) -> None:
    payment = db.one("SELECT * FROM payments WHERE id = ?", (payment_id,))
    if not payment or payment["voided_at"]:
        return
    with db.transaction():
        db.update("payments", payment_id, {
            "voided_at": db.scalar("SELECT datetime('now')"),
            "void_reason": reason[:500] or "No reason given",
        })
        if payment["invoice_id"]:
            recalc(payment["invoice_id"])
    audit.log("update", "payments", payment_id, payment["ref"],
              after={"voided": True, "reason": reason})


def credit_note(invoice_id, amount: float, reason: str, issued_on: str = "") -> int:
    invoice = get(invoice_id)
    if not invoice:
        raise ValueError("invoice not found")
    when = issued_on or today_iso()
    with db.transaction():
        note_id = db.insert("credit_notes", {
            "ref": numbering.take("credit_note", when),
            "invoice_id": invoice_id,
            "client_id": invoice["client_id"],
            "amount": round(parse_float(amount), 2),
            "reason": reason[:500],
            "issued_on": when,
        })
        recalc(invoice_id)
    audit.log("create", "credit_notes", note_id, reason)
    return note_id


def _actor() -> str:
    from core.auth import current_user
    user = current_user()
    return user["email"] if user else "system"


# ── milestones ──────────────────────────────────────────────────────────────
def seed_milestones(project_id) -> None:
    """Give a new project the configured payment schedule, priced off its value."""
    project = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        return
    if db.one("SELECT 1 FROM milestones WHERE project_id = ?", (project_id,)):
        return

    if project["billing_type"] == "retainer":
        db.insert("milestones", {
            "project_id": project_id, "label": "Monthly retainer",
            "description": "Billed monthly in advance.",
            "invoice_pct": 100, "amount": parse_float(project["retainer_amount"]),
            "sort_order": 0,
        })
        return

    from core import pricing
    value = parse_float(project["value"])
    for index, part in enumerate(pricing.milestone_split(value)):
        db.insert("milestones", {
            "project_id": project_id,
            "label": part["label"],
            "invoice_pct": part["pct"],
            "amount": part["amount"],
            "sort_order": index,
        })


def milestones(project_id):
    return db.query(
        "SELECT * FROM milestones WHERE project_id = ? ORDER BY sort_order, id", (project_id,))


def invoice_milestone(milestone_id) -> int:
    """Raise the invoice for one milestone, from the project's quote when there is
    one so the wording matches what the client accepted."""
    ms = db.one("SELECT * FROM milestones WHERE id = ?", (milestone_id,))
    if not ms:
        raise ValueError("milestone not found")
    if ms["invoice_id"]:
        return ms["invoice_id"]
    project = db.one("SELECT * FROM projects WHERE id = ?", (ms["project_id"],))
    if not project:
        raise ValueError("project not found")

    if project["quote_id"] and parse_float(ms["invoice_pct"]):
        invoice_id = from_quote(project["quote_id"], project["client_id"],
                                project_id=project["id"], milestone_id=milestone_id,
                                share_pct=parse_float(ms["invoice_pct"]),
                                label_prefix=f"{ms['label']} - ")
    else:
        invoice_id = create(project["client_id"], project_id=project["id"],
                            milestone_id=milestone_id, line_items=[{
                                "label": f"{project['name']} - {ms['label']}",
                                "description": ms["description"] or "",
                                "qty": 1, "unit_price": parse_float(ms["amount"]),
                                "tax_rate": default_tax_rate(),
                            }])
    db.update("milestones", milestone_id, {"invoice_id": invoice_id, "status": "invoiced"})
    return invoice_id


def _sync_milestone(invoice_id) -> None:
    invoice = get(invoice_id)
    if not invoice or not invoice["milestone_id"]:
        return
    status = "paid" if invoice["status"] == "paid" else "invoiced"
    changes = {"status": status}
    if status == "paid":
        changes["done_on"] = changes.get("done_on") or today_iso()
    db.update("milestones", invoice["milestone_id"], changes)


# ── aging and dunning ───────────────────────────────────────────────────────
def outstanding():
    return db.query(
        "SELECT i.*, c.name AS client_name, c.whatsapp AS client_whatsapp, "
        "c.email AS client_email FROM invoices i JOIN clients c ON c.id = i.client_id "
        "WHERE i.status IN ({}) ORDER BY i.due_on, i.id".format(",".join("?" * len(OPEN_STATUSES))),
        OPEN_STATUSES,
    )


AGING_BUCKETS = (("current", "Not yet due", -10_000, 0),
                 ("b30", "1 - 30 days", 1, 30),
                 ("b60", "31 - 60 days", 31, 60),
                 ("b90", "61 - 90 days", 61, 90),
                 ("b90plus", "Over 90 days", 91, 100_000))


def aging() -> dict:
    """Outstanding balance bucketed by how long it has been overdue."""
    rows = outstanding()
    buckets = {key: {"key": key, "label": label, "total": 0.0, "count": 0, "invoices": []}
               for key, label, _, _ in AGING_BUCKETS}
    today = date.today()
    for row in rows:
        due = parse_date(row["due_on"])
        overdue_days = (today - due).days if due else 0
        for key, _label, lo, hi in AGING_BUCKETS:
            if lo <= overdue_days <= hi:
                buckets[key]["total"] += parse_float(row["balance"])
                buckets[key]["count"] += 1
                buckets[key]["invoices"].append(row)
                break
    ordered = [buckets[key] for key, _l, _lo, _hi in AGING_BUCKETS]
    return {"buckets": ordered, "total": sum(b["total"] for b in ordered),
            "count": sum(b["count"] for b in ordered)}


DUNNING_LADDER = (
    (0, "invoice_sent", "Invoice sent"),
    (1, "payment_due", "Due today or just past"),
    (7, "payment_overdue_7", "A week late"),
    (21, "payment_overdue_21", "Three weeks late, work pauses"),
    (45, "payment_final_notice", "Final notice"),
)


def dunning_stage_for(invoice) -> tuple[int, str, str]:
    """Which reminder this invoice has earned, based on days overdue."""
    due = parse_date(invoice["due_on"])
    overdue = (date.today() - due).days if due else 0
    chosen = DUNNING_LADDER[0]
    for threshold, code, label in DUNNING_LADDER:
        if overdue >= threshold:
            chosen = (threshold, code, label)
    return chosen


def due_reminders():
    """Open invoices whose dunning step has moved on since the last reminder."""
    out = []
    for invoice in outstanding():
        threshold, code, label = dunning_stage_for(invoice)
        if threshold > parse_int(invoice["dunning_stage"], 0) or (
                threshold == 0 and not invoice["last_reminder_at"]):
            out.append({"invoice": invoice, "stage": threshold, "code": code, "label": label})
    return out


def mark_reminded(invoice_id, stage: int) -> None:
    db.update("invoices", invoice_id, {
        "dunning_stage": stage,
        "last_reminder_at": db.scalar("SELECT datetime('now')"),
    })


# ── recurring / renewals ────────────────────────────────────────────────────
def recurring_due(within_days: int = 0):
    horizon = add_days(date.today(), within_days).isoformat()
    return db.query(
        "SELECT r.*, c.name AS client_name, c.whatsapp AS client_whatsapp, "
        "c.email AS client_email, p.name AS project_name "
        "FROM recurring_items r JOIN clients c ON c.id = r.client_id "
        "LEFT JOIN projects p ON p.id = r.project_id "
        "WHERE r.is_active = 1 AND r.next_due_on IS NOT NULL AND r.next_due_on <= ? "
        "AND (r.ends_on IS NULL OR r.ends_on = '' OR r.ends_on >= date('now')) "
        "ORDER BY r.next_due_on", (horizon,))


def invoice_recurring(recurring_id) -> int:
    """Raise the renewal invoice and roll the item on to its next period."""
    item = db.one("SELECT * FROM recurring_items WHERE id = ?", (recurring_id,))
    if not item:
        raise ValueError("recurring item not found")

    period_label = {"monthly": "month", "quarterly": "quarter",
                    "half_yearly": "half year", "yearly": "year"}.get(item["period"], "period")
    invoice_id = create(item["client_id"], project_id=item["project_id"],
                        recurring_id=recurring_id, line_items=[{
                            "label": item["label"],
                            "description": f"{RECURRING_KINDS.get(item['kind'], item['kind'])}"
                                           f" renewal, one {period_label} from {item['next_due_on']}.",
                            "qty": 1, "unit": period_label,
                            "unit_price": parse_float(item["amount"]),
                            "tax_rate": default_tax_rate(),
                        }])

    months = PERIOD_MONTHS.get(item["period"], 12)
    base = parse_date(item["next_due_on"]) or date.today()
    db.update("recurring_items", recurring_id, {
        "last_invoiced_on": today_iso(),
        "next_due_on": add_months(base, months).isoformat(),
        "reminder_sent_at": None,
    })
    return invoice_id


def mrr() -> float:
    """Monthly recurring revenue: every live recurring item normalised to a month."""
    rows = db.query("SELECT amount, period FROM recurring_items WHERE is_active = 1 "
                    "AND (ends_on IS NULL OR ends_on = '' OR ends_on >= date('now'))")
    total = 0.0
    for row in rows:
        months = PERIOD_MONTHS.get(row["period"], 12)
        total += parse_float(row["amount"]) / months
    retainers = parse_float(db.scalar(
        "SELECT COALESCE(SUM(retainer_amount), 0) FROM projects "
        "WHERE billing_type = 'retainer' AND status IN ('active', 'planned')", (), 0))
    return round(total + retainers, 2)


def collected_between(since: str, until: str) -> float:
    return parse_float(db.scalar(
        "SELECT COALESCE(SUM(amount + tds_amount), 0) FROM payments "
        "WHERE voided_at IS NULL AND paid_on >= ? AND paid_on < ?", (since, until), 0))


def invoiced_between(since: str, until: str) -> float:
    return parse_float(db.scalar(
        "SELECT COALESCE(SUM(total), 0) FROM invoices WHERE status != 'draft' "
        "AND cancelled_at IS NULL AND issued_on >= ? AND issued_on < ?", (since, until), 0))


def spent_between(since: str, until: str) -> float:
    return parse_float(db.scalar(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE paid_on >= ? AND paid_on < ?",
        (since, until), 0))


def receivables() -> float:
    return parse_float(db.scalar(
        "SELECT COALESCE(SUM(balance), 0) FROM invoices WHERE status IN ({})".format(
            ",".join("?" * len(OPEN_STATUSES))), OPEN_STATUSES, 0))


def project_pl(project_id) -> dict:
    """Revenue against cost for one project, with the effective hourly rate.

    Revenue is money actually collected, not invoiced, because an unpaid invoice
    has never yet paid for anything.
    """
    project = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        return {}
    invoiced = parse_float(db.scalar(
        "SELECT COALESCE(SUM(total), 0) FROM invoices WHERE project_id = ? "
        "AND status != 'draft' AND cancelled_at IS NULL", (project_id,), 0))
    collected = parse_float(db.scalar(
        "SELECT COALESCE(SUM(p.amount + p.tds_amount), 0) FROM payments p "
        "JOIN invoices i ON i.id = p.invoice_id "
        "WHERE i.project_id = ? AND p.voided_at IS NULL", (project_id,), 0))
    direct = parse_float(db.scalar(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE project_id = ?", (project_id,), 0))
    estimated = parse_float(project["internal_cost"])
    hours = parse_float(db.scalar(
        "SELECT COALESCE(SUM(actual_hours), 0) FROM tasks WHERE project_id = ?", (project_id,), 0))
    ticket_minutes = parse_int(db.scalar(
        "SELECT COALESCE(SUM(minutes), 0) FROM ticket_time_logs WHERE project_id = ?",
        (project_id,), 0))
    hours += ticket_minutes / 60.0
    cost = direct + estimated
    margin = collected - cost
    return {
        "project": project,
        "invoiced": invoiced,
        "collected": collected,
        "outstanding": round(invoiced - collected, 2),
        "direct_cost": direct,
        "estimated_cost": estimated,
        "total_cost": round(cost, 2),
        "margin": round(margin, 2),
        "margin_pct": pct(margin, collected, 1),
        "hours": round(hours, 1),
        "hourly": round(collected / hours, 0) if hours else 0,
    }


def client_balance(client_id) -> dict:
    invoiced = parse_float(db.scalar(
        "SELECT COALESCE(SUM(total), 0) FROM invoices WHERE client_id = ? "
        "AND status != 'draft' AND cancelled_at IS NULL", (client_id,), 0))
    paid = parse_float(db.scalar(
        "SELECT COALESCE(SUM(amount + tds_amount), 0) FROM payments "
        "WHERE client_id = ? AND voided_at IS NULL", (client_id,), 0))
    balance = parse_float(db.scalar(
        "SELECT COALESCE(SUM(balance), 0) FROM invoices WHERE client_id = ? "
        "AND status IN ({})".format(",".join("?" * len(OPEN_STATUSES))),
        [client_id] + list(OPEN_STATUSES), 0))
    return {"invoiced": invoiced, "paid": paid, "balance": balance}
