"""Money out and the numbers that come from it.

Expenses are ordinary CRUD; analytics is where the panel earns its keep. Every
chart is drawn as inline SVG from values computed here, which keeps the pages
dependency-free and means a printed page looks the same as the screen.

One rule runs through all of it: revenue means money actually collected, never
money invoiced. An unpaid invoice has never paid for anything, and a dashboard
that pretends otherwise is how agencies run out of cash while "doing well".
"""

from __future__ import annotations

import csv
import io
from datetime import date

from flask import Response, abort, flash, redirect, render_template, request, url_for

from blueprints.admin import bp
from core import billing, crud, db, leads, numbering, settings, tickets
from core.auth import require_role, verify_csrf
from core.crud import Field, Resource
from core.util import (add_days, add_months, fy_label, fy_months, fy_start_year,
                       month_bounds, parse_date, parse_float, parse_int, pct, today_iso)

EXPENSE_METHODS = ["UPI", "Bank transfer", "Card", "Cash", "Auto-debit"]
PERIODS = {"monthly": "Monthly", "quarterly": "Quarterly", "yearly": "Yearly",
           "one_off": "One-off"}


# ── expense categories ──────────────────────────────────────────────────────
CATEGORIES = Resource(
    key="categories", table="expense_categories", label="Expense category",
    label_plural="Expense categories", area="settings", row_label="name",
    slug_from="name", sortable=True, activatable=True, icon="coins",
    intro="Keep this list short. Categories exist to answer 'where did the money go' "
          "in one glance, and fifteen of them answer nothing.",
    list_columns=[("name", "Category"), ("kind", "Kind")],
    fields=[
        Field("name", "Name", "text", required=True, span=7),
        Field("kind", "Kind", "select", span=5, default="operating",
              options=[("operating", "Operating - keeps the studio running"),
                       ("cogs", "Direct cost - spent to deliver a specific job"),
                       ("tool", "Software and subscriptions"),
                       ("marketing", "Marketing and acquisition"),
                       ("tax", "Tax and statutory"),
                       ("capex", "Equipment")],
              help="Direct costs are subtracted from a project's revenue to get its margin. "
                   "Operating costs are not, because they exist whether that job does or not."),
        Field("is_active", "Active", "bool", span=6, default=1),
    ],
)


def _category_options(include_blank: bool = True):
    rows = db.query("SELECT id, name FROM expense_categories WHERE is_active = 1 "
                    "ORDER BY sort_order, name")
    options = [(r["id"], r["name"]) for r in rows]
    return ([("", "Uncategorised")] + options) if include_blank else options


def _expense_ref(data: dict, existing) -> None:
    """Give a new expense its FY-scoped number. Editing one never renumbers it."""
    if existing is None and not data.get("ref"):
        data["ref"] = numbering.take("expense", data.get("paid_on"))


EXPENSES = Resource(
    key="expenses", table="expenses", label="Expense", label_plural="Expenses",
    area="analytics", row_label="description", order_by="paid_on DESC, id DESC",
    searchable=("description", "vendor", "reference", "notes"), icon="coins",
    before_save=_expense_ref,
    intro="Everything that leaves. Tag a cost to a project when it was spent to deliver "
          "that project - that is what makes the per-project margin real rather than a guess.",
    list_columns=[("paid_on", "Paid"), ("description", "What"), ("vendor", "Vendor"),
                  ("amount", "Amount")],
    fields=[
        Field("description", "What it was", "text", required=True, span=8),
        Field("amount", "Amount", "money", required=True, span=4),
        Field("paid_on", "Paid on", "date", span=4, required=True),
        Field("category_id", "Category", "select", span=4, options=_category_options),
        Field("method", "Method", "select", span=4,
              options=[(m, m) for m in EXPENSE_METHODS], default="UPI"),
        Field("vendor", "Vendor", "text", span=6),
        Field("reference", "Reference", "text", span=6,
              help="UPI reference, cheque number, invoice number from them."),
        Field("tax_amount", "GST in this amount", "money", span=4,
              help="Only if you can claim it. Leave at zero while you are not registered."),
        Field("project_id", "Against project", "select", span=4,
              options=lambda: [("", "Not project-specific")] + [
                  (r["id"], f"{r['ref']} - {r['name']}") for r in db.query(
                      "SELECT id, ref, name FROM projects ORDER BY id DESC LIMIT 200")]),
        Field("client_id", "Against client", "select", span=4,
              options=lambda: [("", "Not client-specific")] + [
                  (r["id"], r["name"]) for r in db.query(
                      "SELECT id, name FROM clients ORDER BY name")]),
        Field("is_billable", "Rebill this to the client", "bool", span=4,
              help="Domain and licence costs you pass on. Flagged here so you can see what "
                   "you have absorbed by forgetting to bill it."),
        Field("is_recurring", "This repeats", "bool", span=4),
        Field("recurring_period", "How often", "select", span=4, default="monthly",
              options=list(PERIODS.items())),
        Field("next_due_on", "Next one due", "date", span=4),
        Field("receipt_media_id", "Receipt", "media", span=4),
        Field("notes", "Notes", "textarea", rows=2, span=12),
    ],
)

SUBSCRIPTIONS = Resource(
    key="subscriptions", table="subscriptions", label="Subscription",
    label_plural="Our subscriptions", area="analytics", row_label="name",
    order_by="is_active DESC, renews_on", searchable=("name", "vendor", "purpose"),
    activatable=True, icon="refresh",
    intro="What the studio itself costs to run every month. This is the number that "
          "decides your real floor price, and the one that quietly grows.",
    list_columns=[("name", "Tool"), ("amount", "Amount"), ("period", "Period"),
                  ("renews_on", "Renews")],
    fields=[
        Field("name", "Tool", "text", required=True, span=6),
        Field("vendor", "Vendor", "text", span=6),
        Field("amount", "Amount", "money", required=True, span=4),
        Field("period", "Billed", "select", span=4, default="monthly",
              options=[("monthly", "Monthly"), ("yearly", "Yearly"),
                       ("quarterly", "Quarterly")]),
        Field("renews_on", "Next renewal", "date", span=4),
        Field("purpose", "What you use it for", "text", span=8),
        Field("seats", "Seats", "number", span=4, default=1),
        Field("category_id", "Expense category", "select", span=4,
              options=_category_options),
        Field("started_on", "Started", "date", span=4),
        Field("cancelled_on", "Cancelled", "date", span=4),
        Field("is_essential", "Could not work without it", "bool", span=6, default=1,
              help="Untick the nice-to-haves. When cash is tight this column is the "
                   "shortlist."),
        Field("is_active", "Active", "bool", span=6, default=1),
        Field("notes", "Notes", "textarea", rows=2, span=12),
    ],
)

for resource in (CATEGORIES, EXPENSES, SUBSCRIPTIONS):
    crud.register(bp, resource)


@bp.route("/subscriptions/<int:row_id>/expense", methods=["POST"])
@require_role("analytics")
def subscription_expense(row_id):
    """Log this month's charge for a subscription as a real expense."""
    verify_csrf()
    sub = db.one("SELECT * FROM subscriptions WHERE id = ?", (row_id,))
    if not sub:
        abort(404)
    expense_id = db.insert("expenses", {
        "ref": numbering.take("expense"),
        "category_id": sub["category_id"],
        "vendor": sub["vendor"] or sub["name"],
        "description": f"{sub['name']} - {PERIODS.get(sub['period'], sub['period'])}",
        "amount": parse_float(sub["amount"]),
        "paid_on": sub["renews_on"] or today_iso(),
        "method": "Auto-debit",
        "is_recurring": 1,
        "recurring_period": sub["period"],
    })

    step = {"monthly": 30, "quarterly": 91, "yearly": 365}.get(sub["period"], 30)
    if sub["renews_on"]:
        from core.util import parse_date
        db.update("subscriptions", row_id,
                  {"renews_on": add_days(parse_date(sub["renews_on"]), step).isoformat()})
    flash("Logged as an expense and the renewal date rolled forward.", "ok")
    return redirect(url_for("admin.expenses_edit", row_id=expense_id))


# ── analytics ───────────────────────────────────────────────────────────────
@bp.route("/analytics")
@require_role("analytics")
def analytics():
    view = request.args.get("view") or "fy"
    start_year = parse_int(request.args.get("fy"), 0) or fy_start_year()
    fy_since, fy_until = f"{start_year}-04-01", f"{start_year + 1}-04-01"

    if view == "month":
        since, until = month_bounds()
        period_label = date.today().strftime("%B %Y")
    elif view == "quarter":
        since, until, period_label = _quarter_bounds(start_year,
                                                     parse_int(request.args.get("q"), 1))
    else:
        since, until = fy_since, fy_until
        period_label = fy_label(date(start_year, 4, 1))

    collected = billing.collected_between(since, until)
    invoiced = billing.invoiced_between(since, until)
    spent = billing.spent_between(since, until)

    months = _monthly_series(start_year)
    peak = max([max(m["collected"], m["spent"]) for m in months] or [1]) or 1

    return render_template(
        "admin/analytics.html", title="Analytics", view=view, period_label=period_label,
        start_year=start_year, years=list(range(fy_start_year() - 4, fy_start_year() + 1)),
        quarter=parse_int(request.args.get("q"), 1),
        collected=collected, invoiced=invoiced, spent=spent,
        net=collected - spent,
        margin_pct=pct(collected - spent, collected, 1),
        uncollected=invoiced - collected,
        receivables=billing.receivables(),
        aging=billing.aging(),
        months=months, peak=peak,
        mrr=billing.mrr(), arr=billing.mrr() * 12,
        subs_monthly=_subscription_monthly(),
        by_category=_spend_by_category(since, until),
        by_service=_revenue_by_service(since, until),
        by_client=_revenue_by_client(since, until),
        sources=leads.by_source(since, until),
        lost=leads.lost_reasons(since, until),
        funnel=leads.funnel(since, until),
        lead_stats=leads.headline(since, until),
        pipeline=leads.pipeline_forecast(),
        ticket_stats=tickets.stats(since, until),
        projects=_project_margins(),
        renewal_rate=_renewal_rate(),
        tax=_tax_summary(since, until),
        target=parse_float(settings.get("analytics.monthly_revenue_target"), 0),
        cost_per_hour=parse_float(settings.get("analytics.cost_per_hour"), 0),
        nav_active="admin.analytics")


def _quarter_bounds(start_year: int, quarter: int) -> tuple[str, str, str]:
    """Indian FY quarters: Q1 is April to June."""
    quarter = max(1, min(4, quarter))
    since = add_months(date(start_year, 4, 1), (quarter - 1) * 3)
    until = add_months(since, 3)
    return since.isoformat(), until.isoformat(), f"Q{quarter} {fy_label(since)}"


def _monthly_series(start_year: int) -> list[dict]:
    """Twelve rows of the financial year, in FY order rather than calendar order."""
    out = []
    for iso, label in fy_months(start_year):
        start = parse_date(iso)
        end = add_months(start, 1).isoformat()
        collected = billing.collected_between(iso, end)
        spent = billing.spent_between(iso, end)
        out.append({
            "label": label,
            "month": label.split(" ")[0],
            "collected": collected,
            "invoiced": billing.invoiced_between(iso, end),
            "spent": spent,
            "net": collected - spent,
            "is_future": start > date.today(),
        })
    return out


def _spend_by_category(since: str, until: str) -> list[dict]:
    rows = db.query(
        "SELECT COALESCE(ec.name, 'Uncategorised') AS name, COALESCE(ec.kind, 'operating') AS kind, "
        "SUM(e.amount) AS total, COUNT(*) AS n FROM expenses e "
        "LEFT JOIN expense_categories ec ON ec.id = e.category_id "
        "WHERE e.paid_on >= ? AND e.paid_on < ? GROUP BY e.category_id ORDER BY total DESC",
        (since, until))
    return [dict(r) for r in rows]


def _revenue_by_service(since: str, until: str) -> list[dict]:
    """Collected money attributed to the service line that earned it.

    Payments are joined back through the invoice to the project, because that is the
    only chain that knows which service line the money came from.
    """
    rows = db.query(
        "SELECT COALESCE(s.name, 'Unattributed') AS name, "
        "SUM(p.amount + p.tds_amount) AS total FROM payments p "
        "JOIN invoices i ON i.id = p.invoice_id "
        "LEFT JOIN projects pr ON pr.id = i.project_id "
        "LEFT JOIN services s ON s.id = pr.service_id "
        "WHERE p.voided_at IS NULL AND p.paid_on >= ? AND p.paid_on < ? "
        "GROUP BY s.id ORDER BY total DESC", (since, until))
    return [dict(r) for r in rows]


def _revenue_by_client(since: str, until: str) -> list[dict]:
    rows = db.query(
        "SELECT c.id, c.name, SUM(p.amount + p.tds_amount) AS total, COUNT(DISTINCT i.id) AS invoices "
        "FROM payments p JOIN clients c ON c.id = p.client_id "
        "LEFT JOIN invoices i ON i.id = p.invoice_id "
        "WHERE p.voided_at IS NULL AND p.paid_on >= ? AND p.paid_on < ? "
        "GROUP BY c.id ORDER BY total DESC LIMIT 12", (since, until))
    out = [dict(r) for r in rows]
    total = sum(parse_float(r["total"]) for r in out) or 1
    for row in out:
        row["share"] = pct(parse_float(row["total"]), total, 1)
    return out


def _project_margins() -> list[dict]:
    rows = db.query(
        "SELECT p.id, p.ref, p.name, p.status, c.name AS client_name FROM projects p "
        "JOIN clients c ON c.id = p.client_id "
        "WHERE p.status NOT IN ('cancelled') ORDER BY p.id DESC LIMIT 25")
    out = []
    for row in rows:
        pl = billing.project_pl(row["id"])
        out.append({**dict(row), **pl})
    return out


def _subscription_monthly() -> float:
    """Every live subscription normalised to a month."""
    divisor = {"monthly": 1.0, "quarterly": 3.0, "yearly": 12.0}
    total = 0.0
    for row in db.query("SELECT amount, period FROM subscriptions WHERE is_active = 1"):
        total += parse_float(row["amount"]) / divisor.get(row["period"], 1.0)
    return round(total, 2)


def _renewal_rate() -> dict:
    """Of the recurring items that came due, how many were actually renewed."""
    due = parse_int(db.scalar(
        "SELECT COUNT(*) FROM recurring_items WHERE next_due_on IS NOT NULL "
        "AND next_due_on < date('now')", (), 0))
    renewed = parse_int(db.scalar(
        "SELECT COUNT(*) FROM recurring_items WHERE last_invoiced_on IS NOT NULL "
        "AND is_active = 1", (), 0))
    lapsed = parse_int(db.scalar(
        "SELECT COUNT(*) FROM recurring_items WHERE is_active = 0", (), 0))
    total = renewed + lapsed
    return {"renewed": renewed, "lapsed": lapsed, "overdue": due,
            "rate": pct(renewed, total, 1) if total else 0.0}


def _tax_summary(since: str, until: str) -> dict:
    """What you will need at filing time, in the shape the forms ask for."""
    output_tax = parse_float(db.scalar(
        "SELECT COALESCE(SUM(tax_amount), 0) FROM invoices WHERE status != 'draft' "
        "AND cancelled_at IS NULL AND issued_on >= ? AND issued_on < ?", (since, until), 0))
    splits = db.one(
        "SELECT COALESCE(SUM(cgst), 0) AS cgst, COALESCE(SUM(sgst), 0) AS sgst, "
        "COALESCE(SUM(igst), 0) AS igst FROM invoices WHERE status != 'draft' "
        "AND cancelled_at IS NULL AND issued_on >= ? AND issued_on < ?", (since, until))
    input_tax = parse_float(db.scalar(
        "SELECT COALESCE(SUM(tax_amount), 0) FROM expenses WHERE paid_on >= ? AND paid_on < ?",
        (since, until), 0))
    tds = parse_float(db.scalar(
        "SELECT COALESCE(SUM(tds_amount), 0) FROM payments WHERE voided_at IS NULL "
        "AND paid_on >= ? AND paid_on < ?", (since, until), 0))
    taxable = parse_float(db.scalar(
        "SELECT COALESCE(SUM(taxable_value), 0) FROM invoices WHERE status != 'draft' "
        "AND cancelled_at IS NULL AND issued_on >= ? AND issued_on < ?", (since, until), 0))
    return {
        "mode": billing.doc_mode_label(),
        "taxable_value": taxable,
        "output_tax": output_tax,
        "cgst": parse_float(splits["cgst"] if splits else 0),
        "sgst": parse_float(splits["sgst"] if splits else 0),
        "igst": parse_float(splits["igst"] if splits else 0),
        "input_tax": input_tax,
        "net_payable": round(output_tax - input_tax, 2),
        "tds_deducted": tds,
    }


# ── project P&L detail ──────────────────────────────────────────────────────
@bp.route("/analytics/project/<int:project_id>")
@require_role("analytics")
def project_pl(project_id):
    project = db.one(
        "SELECT p.*, c.name AS client_name FROM projects p JOIN clients c ON c.id = p.client_id "
        "WHERE p.id = ?", (project_id,))
    if not project:
        abort(404)
    return render_template(
        "admin/project_pl.html", title=f"{project['name']} - P&L", project=project,
        pl=billing.project_pl(project_id),
        expenses=db.query(
            "SELECT e.*, ec.name AS category_name FROM expenses e "
            "LEFT JOIN expense_categories ec ON ec.id = e.category_id "
            "WHERE e.project_id = ? ORDER BY e.paid_on", (project_id,)),
        invoices=db.query("SELECT * FROM invoices WHERE project_id = ? ORDER BY id",
                          (project_id,)),
        time_logs=db.query(
            "SELECT tl.*, t.ref AS ticket_ref, t.subject FROM ticket_time_logs tl "
            "JOIN tickets t ON t.id = tl.ticket_id WHERE tl.project_id = ? ORDER BY tl.logged_on",
            (project_id,)),
        cost_per_hour=parse_float(settings.get("analytics.cost_per_hour"), 0),
        nav_active="admin.analytics")


# ── CSV exports ─────────────────────────────────────────────────────────────
EXPORTS = {
    "collected": ("Money collected", (
        "SELECT p.ref AS receipt, p.paid_on, c.name AS client, i.ref AS invoice, "
        "p.amount, p.tds_amount, p.method, p.reference, p.notes FROM payments p "
        "JOIN clients c ON c.id = p.client_id LEFT JOIN invoices i ON i.id = p.invoice_id "
        "WHERE p.voided_at IS NULL AND p.paid_on >= ? AND p.paid_on < ? ORDER BY p.paid_on")),
    "invoiced": ("Invoices raised", (
        "SELECT i.ref, i.issued_on, i.due_on, c.name AS client, i.subtotal, i.discount_amount, "
        "i.taxable_value, i.tax_amount, i.total, i.amount_paid, i.balance, i.status "
        "FROM invoices i JOIN clients c ON c.id = i.client_id "
        "WHERE i.status != 'draft' AND i.issued_on >= ? AND i.issued_on < ? ORDER BY i.issued_on")),
    "expenses": ("Expenses", (
        "SELECT e.ref, e.paid_on, e.description, e.vendor, ec.name AS category, e.amount, "
        "e.tax_amount, e.method, e.reference, p.ref AS project FROM expenses e "
        "LEFT JOIN expense_categories ec ON ec.id = e.category_id "
        "LEFT JOIN projects p ON p.id = e.project_id "
        "WHERE e.paid_on >= ? AND e.paid_on < ? ORDER BY e.paid_on")),
    # Every invoice still owed, oldest first, with its age - the list that gets
    # handed to whoever is chasing the money.
    "receivables": ("Outstanding invoices", (
        "SELECT i.ref, i.issued_on, i.due_on, c.name AS client, c.phone, c.email, "
        "i.total, i.amount_paid, i.balance, i.status, "
        "CAST(julianday('now') - julianday(COALESCE(i.due_on, i.issued_on)) AS INTEGER) "
        "AS days_overdue FROM invoices i JOIN clients c ON c.id = i.client_id "
        "WHERE i.balance > 0 AND i.status NOT IN ('draft', 'cancelled', 'written_off') "
        "AND i.issued_on >= ? AND i.issued_on < ? "
        "ORDER BY COALESCE(i.due_on, i.issued_on)")),
    "leads": ("Leads", (
        "SELECT l.ref, l.created_at, l.name, l.company, l.email, l.phone, l.city, l.stage, "
        "ls.name AS source, l.utm_source, l.utm_campaign, l.service_interest, l.budget_band, "
        "l.quote_value, l.score, l.lost_reason FROM leads l "
        "LEFT JOIN lead_sources ls ON ls.id = l.source_id "
        "WHERE l.created_at >= ? AND l.created_at < ? ORDER BY l.id")),
    "tickets": ("Tickets", (
        "SELECT t.ref, t.created_at, c.name AS client, t.subject, t.category, t.priority, "
        "t.status, t.first_response_at, t.resolved_at, t.reopened_count FROM tickets t "
        "LEFT JOIN clients c ON c.id = t.client_id "
        "WHERE t.created_at >= ? AND t.created_at < ? ORDER BY t.id")),
}


@bp.route("/analytics/export/<name>")
@require_role("analytics")
def analytics_export(name):
    if name not in EXPORTS:
        abort(404)
    label, sql = EXPORTS[name]
    start_year = parse_int(request.args.get("fy"), 0) or fy_start_year()
    since, until = f"{start_year}-04-01", f"{start_year + 1}-04-01"

    rows = db.query(sql, (since, until))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if rows:
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow([row[key] for key in row.keys()])
    else:
        writer.writerow([f"No {label.lower()} between {since} and {until}"])

    filename = f"aruka-{name}-{start_year}-{(start_year + 1) % 100}.csv"
    return Response(buffer.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
