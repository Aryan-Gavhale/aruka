"""The price calculator.

Nothing here hard-codes a rupee figure. Packages, add-ons and the rules that
adjust them are rows the owner edits in the panel, so a rate change is a form,
not a deploy. The engine's job is only to turn a selection into an itemised,
explainable quote - and to carry the internal cost alongside the price so the
margin is visible before the number is sent.

    quote(config) -> {lines, subtotal, surcharge, discount, tax, total,
                      recurring_yearly, internal_cost, margin, milestones}
"""

from __future__ import annotations

from core import db, settings
from core.util import parse_float, parse_int, pct

ADDON_CATEGORIES = {
    "build": "Build and pages",
    "commerce": "Commerce and payments",
    "brand": "Brand and content",
    "growth": "Growth and SEO",
    "ai": "AI and automation",
    "infra": "Hosting and infrastructure",
    "care": "Care and support",
}

RULE_KINDS = {
    "surcharge_pct": "Surcharge, percent of build",
    "discount_pct": "Discount, percent of build",
    "per_unit": "Per unit charge",
    "multiplier": "Multiplier on build",
}


# ── catalogue ───────────────────────────────────────────────────────────────
def packages(active_only: bool = True):
    sql = "SELECT * FROM packages"
    if active_only:
        sql += " WHERE is_active = 1"
    return db.query(sql + " ORDER BY sort_order, price")


def package(package_id):
    if not package_id:
        return None
    return db.one("SELECT * FROM packages WHERE id = ?", (package_id,))


def package_by_slug(slug: str):
    return db.one("SELECT * FROM packages WHERE slug = ?", (slug,))


def addons(active_only: bool = True):
    sql = "SELECT * FROM addons"
    if active_only:
        sql += " WHERE is_active = 1"
    return db.query(sql + " ORDER BY sort_order, name")


def addons_grouped(active_only: bool = True):
    grouped: dict[str, list] = {}
    for row in addons(active_only):
        grouped.setdefault(row["category"], []).append(row)
    # Present in the declared order so the public form reads like a build-up
    # rather than an alphabetical dump.
    return [(key, label, grouped[key]) for key, label in ADDON_CATEGORIES.items() if key in grouped]


def addon(addon_id):
    if not addon_id:
        return None
    return db.one("SELECT * FROM addons WHERE id = ?", (addon_id,))


def rules(active_only: bool = True):
    sql = "SELECT * FROM pricing_rules"
    if active_only:
        sql += " WHERE is_active = 1"
    return db.query(sql + " ORDER BY sort_order, code")


def rule(code: str):
    return db.one("SELECT * FROM pricing_rules WHERE code = ? AND is_active = 1", (code,))


def rule_value(code: str, fallback: float = 0.0) -> float:
    row = rule(code)
    return parse_float(row["value"], fallback) if row else fallback


# ── the engine ──────────────────────────────────────────────────────────────
def parse_config(form) -> dict:
    """Read a calculator submission - the same shape from the public page and the
    admin form - into a plain config dict the engine can price and store."""
    picks = []
    for key in form.keys():
        if not key.startswith("addon_"):
            continue
        try:
            addon_id = int(key.split("_", 1)[1])
        except (ValueError, IndexError):
            continue
        raw = form.get(key)
        qty = parse_int(raw, 0)
        if raw in ("on", "1", "true", "yes"):
            qty = 1
        if qty > 0:
            picks.append({"addon_id": addon_id, "qty": qty})

    return {
        "package_id": parse_int(form.get("package_id"), 0) or None,
        "pages": parse_int(form.get("pages"), 0),
        "rush": bool(form.get("rush")),
        "complexity": parse_float(form.get("complexity"), 1.0) or 1.0,
        "annual_prepay": bool(form.get("annual_prepay")),
        "referral": bool(form.get("referral")),
        "addons": picks,
        "note": (form.get("note") or "").strip()[:2000],
    }


def _round(amount: float) -> float:
    step = parse_int(settings.get("pricing.rounding"), 100)
    if step <= 1:
        return round(amount, 2)
    return float(int(round(amount / step)) * step)


def quote(config: dict) -> dict:
    """Price a config. Pure: reads the catalogue, writes nothing."""
    lines: list[dict] = []
    pkg = package(config.get("package_id"))

    build_total = 0.0
    recurring_total = 0.0
    internal_cost = 0.0

    if pkg:
        lines.append({
            "kind": "package",
            "label": pkg["name"],
            "description": pkg["tagline"] or "",
            "qty": 1,
            "unit": "package",
            "unit_price": parse_float(pkg["price"]),
            "amount": parse_float(pkg["price"]),
            "internal_cost": parse_float(pkg["internal_cost"]),
            "is_recurring": 0,
            "recurring_period": "",
            "addon_id": None,
        })
        build_total += parse_float(pkg["price"])
        internal_cost += parse_float(pkg["internal_cost"])
        if parse_float(pkg["recurring_yearly"]):
            recurring_total += parse_float(pkg["recurring_yearly"])
            lines.append({
                "kind": "recurring",
                "label": pkg["recurring_label"] or f"{pkg['name']} renewal",
                "description": "From year two, billed annually.",
                "qty": 1, "unit": "year",
                "unit_price": parse_float(pkg["recurring_yearly"]),
                "amount": 0.0,   # a renewal is not part of the one-time total
                "internal_cost": 0.0,
                "is_recurring": 1, "recurring_period": "yearly", "addon_id": None,
            })

    # Pages beyond what the package includes, at the per-page rate.
    included = parse_int(pkg["pages_included"], 0) if pkg else 0
    wanted = parse_int(config.get("pages"), 0)
    extra_pages = max(0, wanted - included) if wanted else 0
    if extra_pages:
        rate = rule_value("extra_page", parse_float(settings.get("pricing.extra_page_rate"), 900))
        amount = rate * extra_pages
        lines.append({
            "kind": "pages",
            "label": f"{extra_pages} extra page{'s' if extra_pages > 1 else ''}",
            "description": f"Beyond the {included} included in {pkg['name']}." if pkg else "",
            "qty": extra_pages, "unit": "page",
            "unit_price": rate, "amount": amount,
            "internal_cost": amount * 0.35,
            "is_recurring": 0, "recurring_period": "", "addon_id": None,
        })
        build_total += amount
        internal_cost += amount * 0.35

    # Add-ons.
    for pick in config.get("addons") or []:
        row = addon(pick.get("addon_id"))
        if not row or not row["is_active"]:
            continue
        qty = max(parse_int(row["min_qty"], 1), parse_int(pick.get("qty"), 1))
        qty = min(qty, parse_int(row["max_qty"], 50) or 50)
        unit_price = parse_float(row["unit_price"])
        amount = unit_price * qty
        cost = parse_float(row["internal_cost"]) * qty
        recurring = bool(row["is_recurring"])
        lines.append({
            "kind": "recurring" if recurring else "addon",
            "label": row["name"],
            "description": row["help"] or "",
            "qty": qty, "unit": row["unit"] or "each",
            "unit_price": unit_price,
            "amount": 0.0 if recurring else amount,
            "internal_cost": 0.0 if recurring else cost,
            "is_recurring": 1 if recurring else 0,
            "recurring_period": row["recurring_period"] if recurring else "",
            "addon_id": row["id"],
        })
        if recurring:
            recurring_total += _to_yearly(amount, row["recurring_period"])
        else:
            build_total += amount
            internal_cost += cost

    # Complexity multiplier, applied to the build before surcharges so a complex
    # brief scales the work rather than the discount.
    complexity = parse_float(config.get("complexity"), 1.0) or 1.0
    complexity = min(max(complexity, 1.0), 3.0)
    complexity_amount = 0.0
    if complexity > 1.0:
        complexity_amount = build_total * (complexity - 1.0)
        lines.append({
            "kind": "adjustment",
            "label": f"Complexity ({complexity:g}x)",
            "description": "Integrations, custom logic or a design system beyond the package.",
            "qty": 1, "unit": "adjustment",
            "unit_price": complexity_amount, "amount": complexity_amount,
            "internal_cost": complexity_amount * 0.45,
            "is_recurring": 0, "recurring_period": "", "addon_id": None,
        })
        internal_cost += complexity_amount * 0.45

    subtotal = build_total + complexity_amount

    # Surcharges.
    surcharge = 0.0
    if config.get("rush"):
        rush_pct = rule_value("rush", parse_float(settings.get("pricing.rush_pct"), 25))
        surcharge = subtotal * rush_pct / 100.0
        lines.append({
            "kind": "adjustment",
            "label": f"Rush delivery (+{rush_pct:g}%)",
            "description": "Compressed timeline, reserved capacity.",
            "qty": 1, "unit": "adjustment",
            "unit_price": surcharge, "amount": surcharge,
            "internal_cost": surcharge * 0.5,
            "is_recurring": 0, "recurring_period": "", "addon_id": None,
        })
        internal_cost += surcharge * 0.5

    # Discounts.
    discount = 0.0
    base_for_discount = subtotal + surcharge
    if config.get("annual_prepay"):
        d = rule_value("annual_prepay",
                       parse_float(settings.get("pricing.annual_prepay_discount_pct"), 10))
        amount = base_for_discount * d / 100.0
        discount += amount
        lines.append({
            "kind": "discount",
            "label": f"Annual prepay ({d:g}% off)",
            "description": "Whole engagement settled up front.",
            "qty": 1, "unit": "discount",
            "unit_price": -amount, "amount": -amount, "internal_cost": 0.0,
            "is_recurring": 0, "recurring_period": "", "addon_id": None,
        })
    if config.get("referral"):
        d = rule_value("referral", parse_float(settings.get("pricing.referral_discount_pct"), 5))
        amount = base_for_discount * d / 100.0
        discount += amount
        lines.append({
            "kind": "discount",
            "label": f"Referral ({d:g}% off)",
            "description": "Introduced by an existing Aruka client.",
            "qty": 1, "unit": "discount",
            "unit_price": -amount, "amount": -amount, "internal_cost": 0.0,
            "is_recurring": 0, "recurring_period": "", "addon_id": None,
        })

    taxable = _round(max(0.0, subtotal + surcharge - discount))

    tax_rate = parse_float(settings.get("gst.default_rate"), 18) if settings.gst_on() else 0.0
    tax_amount = round(taxable * tax_rate / 100.0, 2)
    total = round(taxable + tax_amount, 2)

    margin = taxable - internal_cost

    return {
        "package": pkg,
        "lines": lines,
        "build_total": build_total,
        "complexity": complexity,
        "subtotal": round(subtotal, 2),
        "surcharge_amount": round(surcharge, 2),
        "discount_amount": round(discount, 2),
        "taxable_value": taxable,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "recurring_yearly": round(recurring_total, 2),
        "internal_cost": round(internal_cost, 2),
        "margin": round(margin, 2),
        "margin_pct": pct(margin, taxable, 1),
        "extra_pages": extra_pages,
        "milestones": milestone_split(taxable + tax_amount),
        "delivery_days": _delivery_days(pkg, extra_pages, bool(config.get("rush")), complexity),
    }


def _to_yearly(amount: float, period: str) -> float:
    period = (period or "yearly").lower()
    if period == "monthly":
        return amount * 12
    if period == "quarterly":
        return amount * 4
    if period == "half_yearly":
        return amount * 2
    return amount


def _delivery_days(pkg, extra_pages: int, rush: bool, complexity: float) -> int:
    base = parse_int(pkg["delivery_days"], 14) if pkg else 14
    days = base + extra_pages * 2
    days = int(round(days * max(1.0, complexity * 0.8)))
    if rush:
        days = max(4, int(round(days * 0.6)))
    return days


def milestone_split(total: float) -> list[dict]:
    """The payment schedule from Settings, with the rounding remainder pushed onto
    the last milestone so the parts always add back to the total."""
    plan = settings.get("doc.milestone_split") or []
    if not plan:
        return [{"label": "On acceptance", "pct": 100, "amount": round(total, 2)}]
    out, running = [], 0.0
    for index, row in enumerate(plan):
        share = parse_float(row.get("pct"), 0)
        if index == len(plan) - 1:
            amount = round(total - running, 2)
        else:
            amount = _round(total * share / 100.0)
            running += amount
        out.append({"label": row.get("label") or f"Milestone {index + 1}",
                    "pct": share, "amount": amount})
    return out


# ── persistence ─────────────────────────────────────────────────────────────
def save_quote(config: dict, priced: dict, *, lead_id=None, client_id=None,
               project_id=None, title: str = "", source: str = "admin",
               status: str = "draft", notes: str = "") -> int:
    """Write a priced config to quotes + quote_lines and return the quote id."""
    from core import numbering
    from core.util import add_days, dump_json
    from datetime import date

    valid_days = parse_int(settings.get("doc.validity_days"), 15)
    with db.transaction():
        quote_id = db.insert("quotes", {
            "ref": numbering.take("quote"),
            "lead_id": lead_id,
            "client_id": client_id,
            "project_id": project_id,
            "package_id": config.get("package_id"),
            "title": title or (priced["package"]["name"] if priced.get("package") else "Custom build"),
            "status": status,
            "source": source,
            "pages": parse_int(config.get("pages"), 0),
            "rush": 1 if config.get("rush") else 0,
            "complexity": priced["complexity"],
            "annual_prepay": 1 if config.get("annual_prepay") else 0,
            "referral": 1 if config.get("referral") else 0,
            "subtotal": priced["subtotal"],
            "surcharge_amount": priced["surcharge_amount"],
            "discount_amount": priced["discount_amount"],
            "taxable_value": priced["taxable_value"],
            "tax_amount": priced["tax_amount"],
            "total": priced["total"],
            "recurring_yearly": priced["recurring_yearly"],
            "internal_cost": priced["internal_cost"],
            "currency": settings.get("pricing.currency") or "INR",
            "valid_until": add_days(date.today(), valid_days).isoformat(),
            "notes": notes or config.get("note") or "",
            "config_json": dump_json(config),
        })
        for index, line in enumerate(priced["lines"]):
            db.insert("quote_lines", {
                "quote_id": quote_id,
                "kind": line["kind"],
                "label": line["label"],
                "description": line["description"],
                "qty": line["qty"],
                "unit": line["unit"],
                "unit_price": line["unit_price"],
                "amount": line["amount"],
                "internal_cost": line["internal_cost"],
                "is_recurring": line["is_recurring"],
                "recurring_period": line["recurring_period"],
                "addon_id": line["addon_id"],
                "sort_order": index,
            })
    return quote_id


def get_quote(quote_id):
    return db.one("SELECT * FROM quotes WHERE id = ?", (quote_id,))


def quote_lines(quote_id):
    return db.query(
        "SELECT * FROM quote_lines WHERE quote_id = ? ORDER BY sort_order, id", (quote_id,))


def recalc_quote(quote_id) -> None:
    """Re-total a quote from its lines. Called after any per-line override, so an
    edited line and the header can never disagree."""
    lines = quote_lines(quote_id)
    quote = get_quote(quote_id)
    if not quote:
        return
    one_time = sum(parse_float(l["amount"]) for l in lines if not l["is_recurring"])
    recurring = sum(_to_yearly(parse_float(l["unit_price"]) * parse_float(l["qty"]),
                               l["recurring_period"])
                    for l in lines if l["is_recurring"])
    cost = sum(parse_float(l["internal_cost"]) for l in lines)
    positives = sum(parse_float(l["amount"]) for l in lines
                    if not l["is_recurring"] and parse_float(l["amount"]) > 0)
    discounts = sum(-parse_float(l["amount"]) for l in lines
                    if not l["is_recurring"] and parse_float(l["amount"]) < 0)

    taxable = _round(max(0.0, one_time))
    tax_rate = parse_float(settings.get("gst.default_rate"), 18) if settings.gst_on() else 0.0
    tax_amount = round(taxable * tax_rate / 100.0, 2)

    db.update("quotes", quote_id, {
        "subtotal": round(positives, 2),
        "discount_amount": round(discounts, 2),
        "taxable_value": taxable,
        "tax_amount": tax_amount,
        "total": round(taxable + tax_amount, 2),
        "recurring_yearly": round(recurring, 2),
        "internal_cost": round(cost, 2),
        "updated_at": db.scalar("SELECT datetime('now')"),
    })


def quote_summary(quote_id) -> dict:
    """Everything a document or an invoice needs from a stored quote."""
    quote = get_quote(quote_id)
    if not quote:
        return {}
    lines = quote_lines(quote_id)
    taxable = parse_float(quote["taxable_value"])
    cost = parse_float(quote["internal_cost"])
    return {
        "quote": quote,
        "lines": lines,
        "one_time": [l for l in lines if not l["is_recurring"]],
        "recurring": [l for l in lines if l["is_recurring"]],
        "milestones": milestone_split(parse_float(quote["total"])),
        "margin": round(taxable - cost, 2),
        "margin_pct": pct(taxable - cost, taxable, 1),
    }
