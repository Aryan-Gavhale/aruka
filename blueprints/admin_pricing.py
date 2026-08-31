"""The rate card and the quotes it produces.

Packages, add-ons and rules are plain CRUD, because the whole point is that a
price change is a form and not a deploy. The calculator itself lives in
core/pricing.py; this module is the screens around it.
"""

from __future__ import annotations

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from blueprints.admin import bp
from core import audit, crud, db, leads, pricing, settings
from core.auth import require_role, verify_csrf
from core.crud import Field, Resource
from core.util import parse_float, parse_int

QUOTE_STATUSES = {
    "draft": "Draft",
    "sent": "Sent",
    "accepted": "Accepted",
    "declined": "Declined",
    "expired": "Expired",
    "superseded": "Superseded",
}

PACKAGE_CATEGORIES = [
    ("website", "Website"),
    ("saas", "SaaS and product"),
    ("automation", "AI and automation"),
    ("growth", "SEO and growth"),
    ("care", "Care plan"),
]

RECURRING_PERIODS = [
    ("yearly", "Yearly"),
    ("half_yearly", "Every six months"),
    ("quarterly", "Quarterly"),
    ("monthly", "Monthly"),
]


# ── the rate card ───────────────────────────────────────────────────────────
PACKAGES = Resource(
    key="packages", table="packages", label="Package", label_plural="Packages",
    area="pricing", row_label="name", slug_from="name", activatable=True, sortable=True,
    searchable=("name", "tagline", "best_for"), icon="gift",
    intro="The starting points a client chooses between. The calculator adds pages and "
          "add-ons on top of whichever one they pick, so a package only has to describe "
          "the baseline honestly.",
    list_columns=[("name", "Package"), ("category", "Category"), ("price", "Price"),
                  ("pages_included", "Pages"), ("delivery_days", "Days"),
                  ("recurring_yearly", "Renewal")],
    fields=[
        Field("name", "Name", "text", required=True, span=6),
        Field("slug", "URL slug", "slug", span=6,
              help="Used in the public calculator link. Leave blank to generate it."),
        Field("tagline", "One-line pitch", "text", span=8,
              help="Shown on the card and carried onto the quote line."),
        Field("category", "Category", "select", options=PACKAGE_CATEGORIES,
              default="website", span=4),
        Field("best_for", "Best for", "text", span=12,
              help="Who should pick this. For example: a new business that needs to be "
                   "findable and reachable."),

        Field("money_head", "Money", "heading"),
        Field("price", "Price", "money", span=4, required=True),
        Field("is_from_price", "Show as a from-price", "bool", span=4,
              help="For work that always needs scoping, like SaaS. The public page shows "
                   "'from' in front of the number."),
        Field("internal_cost", "Your cost to deliver", "money", span=4, owner_only=True,
              help="Licences, stock imagery, a subcontractor, hosting for year one - "
                   "whatever this package actually costs you. Only you ever see it, and it "
                   "is what makes the margin column real."),
        Field("recurring_yearly", "Yearly renewal from year two", "money", span=6,
              help="Hosting, domain and care, billed annually after the first year."),
        Field("recurring_label", "Renewal line label", "text", span=6,
              placeholder="Hosting, domain and care"),

        Field("scope_head", "What it includes", "heading"),
        Field("pages_included", "Pages included", "int", span=4,
              help="Anything past this is charged at the per-extra-page rate."),
        Field("delivery_days", "Typical delivery days", "int", span=4, default=14),
        Field("support_months", "Free support months", "int", span=4, default=1),
        Field("features", "Included, one per line", "textarea", rows=8, span=6,
              help="These become the bullet list on the public card and the scope section "
                   "of the proposal PDF. Write them as promises you will keep."),
        Field("excluded", "Not included, one per line", "textarea", rows=8, span=6,
              help="The most valuable field on this form. Anything written here cannot "
                   "become an argument later."),

        Field("show_head", "Where it shows", "heading"),
        Field("is_featured", "Highlight on the pricing page", "bool", span=4),
        Field("is_active", "Available to quote", "bool", span=4, default=1),
    ],
)

ADDONS = Resource(
    key="addons", table="addons", label="Add-on", label_plural="Add-ons",
    area="pricing", row_label="name", slug_from="name", activatable=True, sortable=True,
    searchable=("name", "help"), icon="plus",
    intro="Everything a client can bolt on. Recurring add-ons never enter the one-time "
          "total - they land in the renewal figure and later become recurring invoices.",
    list_columns=[("name", "Add-on"), ("category", "Category"), ("unit_price", "Price"),
                  ("unit", "Per"), ("is_recurring", "Recurring")],
    fields=[
        Field("name", "Name", "text", required=True, span=6),
        Field("slug", "Slug", "slug", span=6),
        Field("category", "Category", "select",
              options=lambda: list(pricing.ADDON_CATEGORIES.items()),
              default="build", span=4),
        Field("unit", "Unit", "text", span=4, default="each",
              placeholder="each, page, language, month"),
        Field("help", "Explain it in a line", "text", span=4,
              help="Shown next to the checkbox on the public calculator."),

        Field("money_head", "Money", "heading"),
        Field("unit_price", "Price per unit", "money", span=6, required=True),
        Field("internal_cost", "Your cost per unit", "money", span=6, owner_only=True),

        Field("qty_head", "Quantity", "heading"),
        Field("is_quantity", "Client picks a quantity", "bool", span=4,
              help="Off means a simple yes-or-no tick."),
        Field("default_qty", "Default quantity", "int", span=4, default=1),
        Field("min_qty", "Minimum", "int", span=2, default=1),
        Field("max_qty", "Maximum", "int", span=2, default=50),

        Field("rec_head", "Recurring", "heading"),
        Field("is_recurring", "This renews", "bool", span=4,
              help="A renewing add-on is quoted as a running cost, not part of the "
                   "build price, so the one-time total stays honest."),
        Field("recurring_period", "How often", "select", options=RECURRING_PERIODS,
              default="yearly", span=4),
        Field("package_scope", "Only offer with these packages", "csv", span=4,
              help="Package slugs, comma separated. Blank means always offered."),
        Field("is_active", "Available", "bool", span=4, default=1),
    ],
)

RULES = Resource(
    key="pricing_rules", table="pricing_rules", label="Pricing rule",
    label_plural="Pricing rules", area="pricing", row_label="label",
    activatable=True, sortable=True, searchable=("code", "label", "help"), icon="sliders",
    deletable=False,
    intro="The percentages and rates the calculator applies. Deactivating a rule makes the "
          "engine fall back to the matching value in Settings, so the calculator never "
          "breaks because a row was switched off.",
    list_columns=[("label", "Rule"), ("code", "Code"), ("kind", "Kind"), ("value", "Value")],
    fields=[
        Field("code", "Code", "text", required=True, span=4,
              help="The engine looks rules up by code. rush, extra_page, annual_prepay and "
                   "referral are the ones it reads - renaming those turns the rule off."),
        Field("label", "Label", "text", required=True, span=8,
              help="What the client sees on the quote line."),
        Field("kind", "Kind", "select",
              options=lambda: list(pricing.RULE_KINDS.items()),
              default="surcharge_pct", span=6),
        Field("value", "Value", "number", step="0.01", span=6,
              help="A percentage for the percent kinds, a rupee amount for per-unit."),
        Field("applies_to", "Applies to", "select", span=6,
              options=[("build", "The build subtotal"), ("total", "Everything before tax")],
              default="total"),
        Field("help", "Note to yourself", "textarea", rows=2, span=12),
        Field("is_active", "Active", "bool", span=6, default=1),
    ],
)

for resource in (PACKAGES, ADDONS, RULES):
    crud.register(bp, resource)


# ── the calculator, admin side ──────────────────────────────────────────────
@bp.route("/quotes")
@require_role("pricing")
def quotes_list():
    status = request.args.get("status") or ""
    query = (request.args.get("q") or "").strip()

    where, params = ["1 = 1"], []
    if status:
        where.append("q.status = ?")
        params.append(status)
    if query:
        where.append("(q.ref LIKE ? OR q.title LIKE ? OR l.name LIKE ? OR c.name LIKE ?)")
        params += [f"%{query}%"] * 4

    rows = db.query(
        f"""SELECT q.*, l.name AS lead_name, l.ref AS lead_ref, c.name AS client_name,
                   p.name AS package_name
            FROM quotes q
            LEFT JOIN leads l    ON l.id = q.lead_id
            LEFT JOIN clients c  ON c.id = q.client_id
            LEFT JOIN packages p ON p.id = q.package_id
            WHERE {' AND '.join(where)}
            ORDER BY q.id DESC LIMIT 300""", tuple(params))

    return render_template(
        "admin/quotes_list.html", title="Quotes", rows=rows, status=status, q=query,
        statuses=QUOTE_STATUSES,
        counts={r["status"]: r["n"] for r in db.query(
            "SELECT status, COUNT(*) AS n FROM quotes GROUP BY status")},
        nav_active="admin.quotes_list")


@bp.route("/quotes/new", methods=["GET", "POST"])
@require_role("pricing")
def quote_new():
    lead_id = parse_int(request.args.get("lead_id"), 0) or None
    client_id = parse_int(request.args.get("client_id"), 0) or None
    lead = leads.get(lead_id) if lead_id else None
    client = db.one("SELECT * FROM clients WHERE id = ?", (client_id,)) if client_id else None

    if request.method == "POST":
        verify_csrf()
        lead_id = parse_int(request.form.get("lead_id"), 0) or None
        client_id = parse_int(request.form.get("client_id"), 0) or None
        config = pricing.parse_config(request.form)
        if not config["package_id"] and not config["addons"]:
            flash("Pick a package, or at least one add-on.", "error")
            return redirect(request.url)

        priced = pricing.quote(config)
        quote_id = pricing.save_quote(
            config, priced, lead_id=lead_id, client_id=client_id,
            title=(request.form.get("title") or "").strip(),
            notes=(request.form.get("notes") or "").strip(), source="admin")

        if lead_id:
            leads.add_event(lead_id, "quote",
                            f"Quote priced at {priced['total']:.0f}.",
                            {"quote_id": quote_id})
            lead_row = leads.get(lead_id)
            db.update("leads", lead_id, {"quote_value": priced["total"]})
            if lead_row and lead_row["stage"] in ("new", "contacted", "qualified"):
                leads.set_stage(lead_id, "quoted", "Quote prepared.")

        flash("Quote saved.", "ok")
        return redirect(url_for("admin.quote_detail", quote_id=quote_id))

    return render_template(
        "admin/quote_form.html", title="New quote", lead=lead, client=client,
        packages=pricing.packages(), addon_groups=pricing.addons_grouped(),
        rules={r["code"]: r for r in pricing.rules()},
        clients=db.query("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name"),
        preview_url=url_for("admin.quote_preview"), nav_active="admin.quotes_list")


@bp.route("/quotes/preview", methods=["POST"])
@require_role("pricing")
def quote_preview():
    """Live totals while the form is being filled, so the owner sees the margin
    before the client ever sees the price."""
    verify_csrf()
    payload = request.get_json(silent=True) or {}
    config = pricing.parse_config(payload)
    priced = pricing.quote(config)
    from core.auth import is_owner
    out = {
        "ok": True,
        "lines": [{"label": l["label"], "qty": l["qty"], "unit": l["unit"],
                   "amount": l["amount"], "recurring": bool(l["is_recurring"]),
                   "unit_price": l["unit_price"]}
                  for l in priced["lines"]],
        "subtotal": priced["subtotal"],
        "surcharge": priced["surcharge_amount"],
        "discount": priced["discount_amount"],
        "taxable": priced["taxable_value"],
        "tax": priced["tax_amount"],
        "tax_rate": priced["tax_rate"],
        "total": priced["total"],
        "recurring_yearly": priced["recurring_yearly"],
        "delivery_days": priced["delivery_days"],
        "milestones": priced["milestones"],
    }
    if is_owner():
        out.update({"internal_cost": priced["internal_cost"],
                    "margin": priced["margin"], "margin_pct": priced["margin_pct"]})
    return jsonify(out)


@bp.route("/quotes/<int:quote_id>", methods=["GET", "POST"])
@require_role("pricing")
def quote_detail(quote_id):
    quote = pricing.get_quote(quote_id)
    if not quote:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        changes = {
            "title": (request.form.get("title") or "").strip(),
            "notes": (request.form.get("notes") or "").strip(),
            "valid_until": (request.form.get("valid_until") or "").strip() or None,
        }
        status = request.form.get("status")
        if status in QUOTE_STATUSES:
            changes["status"] = status
            if status == "accepted" and not quote["accepted_at"]:
                changes["accepted_at"] = db.scalar("SELECT datetime('now')")
        db.update("quotes", quote_id, changes)
        audit.log("update", "quotes", quote_id, quote["ref"], before=quote, after=changes)
        flash("Quote updated.", "ok")
        return redirect(url_for("admin.quote_detail", quote_id=quote_id))

    summary = pricing.quote_summary(quote_id)
    return render_template(
        "admin/quote_detail.html", title=quote["ref"], quote=quote, summary=summary,
        statuses=QUOTE_STATUSES,
        lead=leads.get(quote["lead_id"]) if quote["lead_id"] else None,
        client=db.one("SELECT * FROM clients WHERE id = ?", (quote["client_id"],))
        if quote["client_id"] else None,
        documents=db.query("SELECT * FROM documents WHERE quote_id = ? ORDER BY id DESC",
                           (quote_id,)),
        nav_active="admin.quotes_list")


@bp.route("/quotes/<int:quote_id>/line/<int:line_id>", methods=["POST"])
@require_role("pricing")
def quote_line_edit(quote_id, line_id):
    """Override one line and re-total.

    Every real quote ends up with one number that has to be nudged. Overriding a
    line and re-deriving the header is the only way the two can never disagree.
    """
    verify_csrf()
    line = db.one("SELECT * FROM quote_lines WHERE id = ? AND quote_id = ?", (line_id, quote_id))
    if not line:
        abort(404)

    if request.form.get("remove"):
        db.execute("DELETE FROM quote_lines WHERE id = ?", (line_id,))
        pricing.recalc_quote(quote_id)
        flash("Line removed.", "ok")
        return redirect(url_for("admin.quote_detail", quote_id=quote_id))

    qty = parse_float(request.form.get("qty"), parse_float(line["qty"], 1)) or 1
    unit_price = parse_float(request.form.get("unit_price"), parse_float(line["unit_price"]))
    changes = {
        "label": (request.form.get("label") or line["label"]).strip(),
        "description": (request.form.get("description") or "").strip(),
        "qty": qty,
        "unit_price": unit_price,
        "amount": 0.0 if line["is_recurring"] else round(qty * unit_price, 2),
        "is_override": 1,
    }
    if request.form.get("internal_cost") is not None:
        changes["internal_cost"] = parse_float(request.form.get("internal_cost"),
                                               parse_float(line["internal_cost"]))
    db.update("quote_lines", line_id, changes)
    pricing.recalc_quote(quote_id)
    audit.log("update", "quote_lines", line_id, line["label"], before=line, after=changes)
    flash("Line updated and the quote re-totalled.", "ok")
    return redirect(url_for("admin.quote_detail", quote_id=quote_id))


@bp.route("/quotes/<int:quote_id>/line/add", methods=["POST"])
@require_role("pricing")
def quote_line_add(quote_id):
    verify_csrf()
    if not pricing.get_quote(quote_id):
        abort(404)
    label = (request.form.get("label") or "").strip()
    if not label:
        flash("A line needs a label.", "error")
        return redirect(url_for("admin.quote_detail", quote_id=quote_id))

    qty = parse_float(request.form.get("qty"), 1) or 1
    unit_price = parse_float(request.form.get("unit_price"), 0)
    recurring = bool(request.form.get("is_recurring"))
    db.insert("quote_lines", {
        "quote_id": quote_id,
        "kind": "recurring" if recurring else "addon",
        "label": label,
        "description": (request.form.get("description") or "").strip(),
        "qty": qty,
        "unit": (request.form.get("unit") or "each").strip(),
        "unit_price": unit_price,
        "amount": 0.0 if recurring else round(qty * unit_price, 2),
        "internal_cost": parse_float(request.form.get("internal_cost"), 0),
        "is_recurring": 1 if recurring else 0,
        "recurring_period": request.form.get("recurring_period") or "yearly",
        "is_override": 1,
        "sort_order": parse_int(db.scalar(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM quote_lines WHERE quote_id = ?",
            (quote_id,)), 99),
    })
    pricing.recalc_quote(quote_id)
    flash("Line added.", "ok")
    return redirect(url_for("admin.quote_detail", quote_id=quote_id))


@bp.route("/quotes/<int:quote_id>/duplicate", methods=["POST"])
@require_role("pricing")
def quote_duplicate(quote_id):
    """Copy a quote so a revised version can be sent without losing the first.

    The original is marked superseded rather than edited, because "you quoted me
    something different" needs an answer that is a record and not a memory.
    """
    verify_csrf()
    quote = pricing.get_quote(quote_id)
    if not quote:
        abort(404)
    from core import numbering
    from core.util import load_json

    with db.transaction():
        new_id = db.insert("quotes", {
            **{k: quote[k] for k in quote.keys()
               if k not in ("id", "ref", "created_at", "updated_at", "accepted_at")},
            "ref": numbering.take("quote"),
            "status": "draft",
        })
        for line in pricing.quote_lines(quote_id):
            db.insert("quote_lines", {
                **{k: line[k] for k in line.keys() if k not in ("id", "quote_id")},
                "quote_id": new_id,
            })
        if quote["status"] in ("sent", "draft"):
            db.update("quotes", quote_id, {"status": "superseded"})

    audit.log("create", "quotes", new_id, "copied from " + quote["ref"],
              after={"config": load_json(quote["config_json"], {})})
    flash(f"Copied to a new draft. {quote['ref']} is marked superseded.", "ok")
    return redirect(url_for("admin.quote_detail", quote_id=new_id))


@bp.route("/quotes/<int:quote_id>/delete", methods=["POST"])
@require_role("owner")
def quote_delete(quote_id):
    verify_csrf()
    quote = pricing.get_quote(quote_id)
    if not quote:
        abort(404)
    if db.scalar("SELECT COUNT(*) FROM documents WHERE quote_id = ?", (quote_id,)):
        flash("This quote is attached to a document. Mark it declined or superseded "
              "instead - deleting it would leave the PDF referring to nothing.", "error")
        return redirect(url_for("admin.quote_detail", quote_id=quote_id))
    db.delete("quotes", quote_id)
    audit.log("delete", "quotes", quote_id, quote["ref"], before=quote)
    flash("Quote deleted.", "ok")
    return redirect(url_for("admin.quotes_list"))


# ── the rate card at a glance ───────────────────────────────────────────────
@bp.route("/ratecard")
@require_role("pricing")
def ratecard():
    """One page that answers 'what do we charge' without opening four screens."""
    rows = pricing.packages(active_only=False)
    return render_template(
        "admin/ratecard.html", title="Rate card", packages=rows,
        addon_groups=pricing.addons_grouped(active_only=False),
        rules=pricing.rules(active_only=False),
        gst=settings.gst_on(),
        extra_page=pricing.rule_value(
            "extra_page", parse_float(settings.get("pricing.extra_page_rate"), 900)),
        milestone_plan=settings.get("doc.milestone_split") or [],
        nav_active="admin.packages_list")
