"""The public website.

Copy, services, work, insights and pricing all come out of the database so the
owner can rewrite the site without touching a template. Layout and animation stay
in code, which is the split that keeps a CMS from turning into a page builder
nobody can maintain.

Three routes take input from strangers - the enquiry form, the public calculator
and the support form - and all three go through the same gate: CSRF token, a
honeypot field, a minimum time-on-page, and a per-IP rate limit.
"""

from __future__ import annotations

import time

from flask import (Blueprint, Response, abort, current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from markupsafe import Markup

from core import db, documents, leads, notify, pricing, settings, tickets
from core.auth import csrf_token, verify_csrf
from core.util import (client_ip, load_json, parse_float, parse_int, today_iso,
                       valid_email, wa_number)

bp = Blueprint("public", __name__, template_folder="../templates")

# A human filling in a form takes longer than this. Anything faster is a script.
MIN_SECONDS_ON_FORM = 3.0
RATE_WINDOW_MINUTES = 60
RATE_MAX_PER_IP = 6


# ── shared chrome ───────────────────────────────────────────────────────────
@bp.context_processor
def _chrome():
    return chrome()


def chrome() -> dict:
    """Header, footer and the switches the layout reads.

    A plain function rather than only a context processor, because the 404 page is
    rendered by the app-level error handler with no blueprint attached, and a public
    page with no navigation is worse than no 404 page at all.
    """
    return {
        "nav_items": db.query(
            "SELECT * FROM nav_items WHERE location = 'header' AND is_active = 1 "
            "ORDER BY sort_order, id"),
        "footer_items": db.query(
            "SELECT * FROM nav_items WHERE location = 'footer' AND is_active = 1 "
            "ORDER BY sort_order, id"),
        "legal_links": db.query(
            "SELECT slug, title FROM legal_pages WHERE is_published = 1 ORDER BY sort_order, id"),
        "footer_services": db.query(
            "SELECT slug, name FROM services WHERE is_published = 1 ORDER BY sort_order LIMIT 6"),
        "marquee": db.query(
            "SELECT * FROM tech_items WHERE is_active = 1 ORDER BY sort_order, id"),
        "wa_link": wa_link(),
        "calculator_on": settings.get("pricing.show_public_calculator"),
        "indexable": settings.get("seo.indexable"),
        # A FAQ page block stores only the category it wants, so the template needs
        # a way to fetch the rows. Handing it a query is the alternative to making
        # every route that can render blocks pass every category's FAQs.
        "faqs_in": _faqs_in,
    }


def _faqs_in(category: str = "general", limit: int = 12):
    return db.query(
        "SELECT * FROM faqs WHERE is_published = 1 AND category = ? ORDER BY sort_order, id "
        "LIMIT ?", (category or "general", limit))


def wa_link(text: str = "") -> str:
    number = wa_number(settings.get("contact.whatsapp") or "",
                       settings.get("whatsapp.default_country_code") or "91")
    if not number:
        return ""
    from urllib.parse import quote
    message = text or f"Hi {settings.get('brand.name') or 'Aruka'}, I would like to talk about a project."
    return f"https://wa.me/{number}?text={quote(message)}"


def _page(slug: str):
    return db.one("SELECT * FROM pages WHERE slug = ? AND is_published = 1", (slug,))


def _blocks(page):
    if not page:
        return []
    rows = db.query(
        "SELECT * FROM page_blocks WHERE page_id = ? AND is_published = 1 "
        "ORDER BY sort_order, id", (page["id"],))
    return [{**dict(r), "data": load_json(r["data"], {})} for r in rows]


def _meta(page=None, *, title: str = "", description: str = "", media_id=None) -> dict:
    """One shape for every page's head, so no template invents its own."""
    suffix = settings.get("seo.title_suffix") or settings.get("brand.name") or "Aruka"
    base = (page["meta_title"] if page and page["meta_title"] else "") or title
    if page and not base:
        base = page["title"]
    description = ((page["meta_description"] if page and page["meta_description"] else "")
                   or description or settings.get("seo.default_description") or "")
    og = media_id or (page["og_media_id"] if page else None) or settings.get("seo.og_media_id")
    return {
        "title": f"{base} | {suffix}" if base and base != suffix else suffix,
        "description": description[:300],
        "og_media_id": og,
        "canonical": request.base_url,
    }


# ── home ────────────────────────────────────────────────────────────────────
@bp.route("/")
def home():
    page = _page("home")
    return render_template(
        "public/home.html", page=page, blocks=_blocks(page), meta=_meta(page),
        services=db.query("SELECT * FROM services WHERE is_published = 1 "
                          "ORDER BY is_featured DESC, sort_order LIMIT 6"),
        work=db.query("SELECT * FROM case_studies WHERE is_published = 1 "
                      "ORDER BY is_featured DESC, sort_order LIMIT 3"),
        testimonials=db.query("SELECT * FROM testimonials WHERE is_published = 1 "
                              "ORDER BY sort_order LIMIT 6"),
        stats=db.query("SELECT * FROM stats WHERE is_active = 1 ORDER BY sort_order"),
        packages=pricing.packages()[:3],
        faqs=db.query("SELECT * FROM faqs WHERE is_published = 1 AND category = 'general' "
                      "ORDER BY sort_order LIMIT 6"),
        posts=db.query("SELECT * FROM posts WHERE is_published = 1 "
                       "ORDER BY published_at DESC LIMIT 3"),
        rotating=[s["name"] for s in db.query(
            "SELECT name FROM services WHERE is_published = 1 ORDER BY sort_order LIMIT 5")],
        nav_here="home")


# ── services ────────────────────────────────────────────────────────────────
@bp.route("/services")
def services():
    page = _page("services")
    return render_template(
        "public/services.html", page=page, blocks=_blocks(page),
        meta=_meta(page, title="Services"),
        rows=db.query("SELECT * FROM services WHERE is_published = 1 ORDER BY sort_order"),
        packages=pricing.packages(),
        faqs=db.query("SELECT * FROM faqs WHERE is_published = 1 AND category IN "
                      "('general', 'services') ORDER BY sort_order"),
        nav_here="services")


@bp.route("/services/<slug>")
def service(slug):
    row = db.one("SELECT * FROM services WHERE slug = ? AND is_published = 1", (slug,))
    if not row:
        abort(404)
    return render_template(
        "public/service.html", row=row,
        meta=_meta(title=row["name"],
                   description=row["meta_description"] or row["summary"],
                   media_id=row["media_id"]),
        work=db.query("SELECT * FROM case_studies WHERE is_published = 1 "
                      "AND service_line = ? ORDER BY sort_order LIMIT 3", (row["name"],)),
        packages=[p for p in pricing.packages()
                  if not row["slug"] or p["category"] in (row["slug"], "website", "custom")][:3],
        others=db.query("SELECT slug, name, tagline, icon FROM services WHERE is_published = 1 "
                        "AND id != ? ORDER BY sort_order LIMIT 4", (row["id"],)),
        testimonials=db.query("SELECT * FROM testimonials WHERE is_published = 1 "
                              "ORDER BY sort_order LIMIT 3"),
        nav_here="services")


# ── work ────────────────────────────────────────────────────────────────────
@bp.route("/work")
def work():
    page = _page("work")
    sector = (request.args.get("sector") or "").strip()
    sql = "SELECT * FROM case_studies WHERE is_published = 1"
    args: list = []
    if sector:
        sql += " AND sector = ?"
        args.append(sector)
    return render_template(
        "public/work.html", page=page, blocks=_blocks(page),
        meta=_meta(page, title="Work"),
        rows=db.query(sql + " ORDER BY is_featured DESC, sort_order", args),
        sectors=db.query("SELECT DISTINCT sector FROM case_studies WHERE is_published = 1 "
                         "AND sector != '' ORDER BY sector"),
        sector=sector, nav_here="work")


@bp.route("/work/<slug>")
def case_study(slug):
    row = db.one("SELECT * FROM case_studies WHERE slug = ? AND is_published = 1", (slug,))
    if not row:
        abort(404)
    return render_template(
        "public/case_study.html", row=row,
        meta=_meta(title=row["title"],
                   description=row["meta_description"] or row["summary"],
                   media_id=row["media_id"]),
        testimonial=db.one("SELECT * FROM testimonials WHERE company = ? AND is_published = 1",
                           (row["client_name"],)),
        others=db.query("SELECT slug, title, client_name, summary, media_id FROM case_studies "
                        "WHERE is_published = 1 AND id != ? ORDER BY is_featured DESC, "
                        "sort_order LIMIT 3", (row["id"],)),
        nav_here="work")


# ── about ───────────────────────────────────────────────────────────────────
@bp.route("/about")
def about():
    page = _page("about")
    return render_template(
        "public/about.html", page=page, blocks=_blocks(page),
        meta=_meta(page, title="About"),
        stats=db.query("SELECT * FROM stats WHERE is_active = 1 ORDER BY sort_order"),
        testimonials=db.query("SELECT * FROM testimonials WHERE is_published = 1 "
                              "ORDER BY sort_order"),
        services=db.query("SELECT slug, name, tagline, icon FROM services "
                          "WHERE is_published = 1 ORDER BY sort_order"),
        nav_here="about")


# ── insights ────────────────────────────────────────────────────────────────
@bp.route("/insights")
def insights():
    page = _page("insights")
    tag = (request.args.get("tag") or "").strip()
    sql = "SELECT * FROM posts WHERE is_published = 1"
    args: list = []
    if tag:
        sql += " AND tags LIKE ?"
        args.append(f"%{tag}%")
    rows = db.query(sql + " ORDER BY published_at DESC, id DESC", args)

    tags = sorted({t.strip() for row in db.query(
        "SELECT tags FROM posts WHERE is_published = 1") for t in (row["tags"] or "").split(",")
        if t.strip()})

    return render_template(
        "public/insights.html", page=page, blocks=_blocks(page),
        meta=_meta(page, title="Insights"), rows=rows, tags=tags, tag=tag,
        nav_here="insights")


@bp.route("/insights/<slug>")
def post(slug):
    row = db.one("SELECT * FROM posts WHERE slug = ? AND is_published = 1", (slug,))
    if not row:
        abort(404)
    return render_template(
        "public/post.html", row=row,
        meta=_meta(title=row["title"],
                   description=row["meta_description"] or row["excerpt"],
                   media_id=row["media_id"]),
        more=db.query("SELECT slug, title, excerpt, published_at FROM posts "
                      "WHERE is_published = 1 AND id != ? ORDER BY published_at DESC LIMIT 3",
                      (row["id"],)),
        nav_here="insights")


# ── pricing and the public calculator ───────────────────────────────────────
@bp.route("/pricing", methods=["GET", "POST"])
def pricing_page():
    page = _page("pricing")
    if not settings.get("pricing.show_public_calculator"):
        return render_template(
            "public/pricing.html", page=page, blocks=_blocks(page),
            meta=_meta(page, title="Pricing"), packages=pricing.packages(),
            groups=[], priced=None, config={}, calculator=False,
            faqs=db.query("SELECT * FROM faqs WHERE is_published = 1 AND category IN "
                          "('pricing', 'general') ORDER BY sort_order"),
            nav_here="pricing")

    priced = None
    config: dict = {}
    if request.method == "POST":
        verify_csrf()
        config = pricing.parse_config(request.form)
        priced = pricing.quote(config)

        if request.form.get("email") or request.form.get("phone"):
            return _save_public_quote(config, priced)
        session["aruka_quote"] = {"config": config, "at": time.time()}

    return render_template(
        "public/pricing.html", page=page, blocks=_blocks(page),
        meta=_meta(page, title="Pricing"),
        packages=pricing.packages(), groups=pricing.addons_grouped(),
        priced=priced, config=config, calculator=True,
        note=settings.get("pricing.public_note"),
        rush_pct=settings.get("pricing.rush_pct"),
        extra_page_rate=settings.get("pricing.extra_page_rate"),
        budget_bands=settings.get("crm.budget_bands"),
        faqs=db.query("SELECT * FROM faqs WHERE is_published = 1 AND category IN "
                      "('pricing', 'general') ORDER BY sort_order"),
        form_opened_at=time.time(), nav_here="pricing")


def _save_public_quote(config: dict, priced: dict):
    """Someone put their details on an estimate: that is a lead plus a saved quote."""
    ok, message = _gate("quote")
    if not ok:
        flash(message, "error")
        return redirect(url_for("public.pricing_page"))

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    if not name or not (email or phone):
        flash("A name and either an email or a phone number, and it is on its way.", "error")
        return redirect(url_for("public.pricing_page"))

    # priced["package"] is a database row, not a dict, so it has no .get - and a
    # custom build has no package at all.
    package = priced.get("package") if priced else None
    package_name = package["name"] if package else ""

    lead_id = leads.create({
        "name": name,
        "company": (request.form.get("company") or "").strip(),
        "email": email,
        "phone": phone,
        "whatsapp": phone,
        "city": (request.form.get("city") or "").strip(),
        "message": config.get("note") or "Built an estimate on the pricing page.",
        "service_interest": package_name,
        "quote_value": priced["total"] if priced else 0,
        "referral_code": (request.form.get("referral_code") or "").strip().upper(),
        "utm_source": request.form.get("utm_source") or "",
        "utm_medium": request.form.get("utm_medium") or "",
        "utm_campaign": request.form.get("utm_campaign") or "",
        "landing_page": "/pricing",
        "referrer": request.referrer or "",
        "ip": client_ip(),
    }, source="calculator")

    quote_id = pricing.save_quote(
        config, priced, lead_id=lead_id, source="public",
        title=package_name or "Self-serve estimate")

    notify.push(f"Estimate built: {name}",
                f"{name} priced up {package_name or 'a custom build'} "
                f"at {priced['total']:.0f}.",
                kind="lead", url=f"/admin/leads/{lead_id}",
                entity="lead", entity_id=lead_id)

    lead = leads.get(lead_id)
    quote = db.one("SELECT * FROM quotes WHERE id = ?", (quote_id,))
    return render_template("public/thanks.html", lead=lead, quote=quote,
                           meta=_meta(title="Estimate saved"),
                           title=settings.get("crm.lead_success_title"),
                           body=settings.get("crm.lead_success_body"),
                           wa=wa_link(f"Hi, I just built an estimate on your site. "
                                       f"My reference is {lead['ref']}."),
                           nav_here="pricing")


@bp.route("/pricing/estimate", methods=["POST"])
def pricing_estimate():
    """Live re-price behind the calculator, so the total moves as boxes are ticked."""
    verify_csrf()
    config = pricing.parse_config(request.form)
    priced = pricing.quote(config)
    return jsonify({
        "ok": True,
        "total": priced["total"],
        "subtotal": priced["subtotal"],
        "surcharge": priced["surcharge_amount"],
        "discount": priced["discount_amount"],
        "tax": priced["tax_amount"],
        "tax_rate": priced["tax_rate"],
        "recurring_yearly": priced["recurring_yearly"],
        "delivery_days": priced.get("delivery_days"),
        "lines": [{"label": l["label"], "qty": l["qty"], "unit": l["unit"],
                   "amount": l["amount"], "is_recurring": l["is_recurring"]}
                  for l in priced["lines"]],
        "milestones": priced.get("milestones") or [],
    })


# ── contact and the enquiry form ────────────────────────────────────────────
@bp.route("/contact", methods=["GET", "POST"])
def contact():
    page = _page("contact")

    if request.method == "POST":
        verify_csrf()
        ok, message = _gate("enquiry")
        if not ok:
            flash(message, "error")
            return redirect(url_for("public.contact"))

        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()
        phone = (request.form.get("phone") or "").strip()

        errors = []
        if len(name) < 2:
            errors.append("Your name, so we know who we are replying to.")
        if not email and not phone:
            errors.append("An email or a phone number - either is fine.")
        if email and not valid_email(email):
            errors.append("That email address does not look right.")
        if errors:
            for problem in errors:
                flash(problem, "error")
            return redirect(url_for("public.contact"))

        lead_id = leads.create({
            "name": name,
            "company": (request.form.get("company") or "").strip(),
            "email": email,
            "phone": phone,
            "whatsapp": phone,
            "city": (request.form.get("city") or "").strip(),
            "service_interest": (request.form.get("service") or "").strip(),
            "budget_band": (request.form.get("budget") or "").strip(),
            "message": (request.form.get("message") or "").strip(),
            "referral_code": (request.form.get("referral_code") or "").strip().upper(),
            "utm_source": request.args.get("utm_source") or request.form.get("utm_source") or "",
            "utm_medium": request.args.get("utm_medium") or request.form.get("utm_medium") or "",
            "utm_campaign": request.args.get("utm_campaign") or request.form.get("utm_campaign") or "",
            "utm_term": request.form.get("utm_term") or "",
            "utm_content": request.form.get("utm_content") or "",
            "referrer": request.referrer or "",
            "landing_page": request.form.get("landing_page") or "/contact",
            "ip": client_ip(),
        }, source="web")

        notify.push(f"New enquiry: {name}",
                    (request.form.get("message") or "")[:200] or "No message left.",
                    kind="lead", url=f"/admin/leads/{lead_id}",
                    entity="lead", entity_id=lead_id)
        _notify_email_on_lead(lead_id)

        lead = leads.get(lead_id)
        return render_template(
            "public/thanks.html", lead=lead, quote=None, meta=_meta(title="Thank you"),
            title=settings.get("crm.lead_success_title"),
            body=settings.get("crm.lead_success_body"),
            wa=wa_link(f"Hi, I just sent an enquiry through your site. "
                        f"My reference is {lead['ref']}."),
            nav_here="contact")

    return render_template(
        "public/contact.html", page=page, blocks=_blocks(page),
        meta=_meta(page, title="Contact"),
        services=db.query("SELECT name FROM services WHERE is_published = 1 ORDER BY sort_order"),
        budget_bands=settings.get("crm.budget_bands"),
        faqs=db.query("SELECT * FROM faqs WHERE is_published = 1 AND category IN "
                      "('general', 'process') ORDER BY sort_order LIMIT 6"),
        form_opened_at=time.time(), nav_here="contact")


def _notify_email_on_lead(lead_id) -> None:
    if not settings.get("email.notify_on_lead"):
        return
    from services import mailer
    lead = leads.get(lead_id)
    to = settings.get("contact.email")
    if not (to and lead):
        return
    mailer.send(to, f"New enquiry: {lead['name']} ({lead['ref']})",
                f"{lead['name']}\n{lead['company'] or ''}\n{lead['email'] or ''} "
                f"{lead['phone'] or ''}\n\n{lead['message'] or ''}\n\n"
                f"Open it: /admin/leads/{lead_id}")


# ── support ─────────────────────────────────────────────────────────────────
@bp.route("/support", methods=["GET"])
def support():
    return render_template(
        "public/support.html", meta=_meta(title="Support"),
        intro=settings.get("ticket.intro"),
        categories=tickets.CATEGORIES, priorities=tickets.PRIORITY_LABELS,
        policies={p: tickets.policy(p) for p in tickets.PRIORITIES},
        faqs=db.query("SELECT * FROM faqs WHERE is_published = 1 AND category IN "
                      "('support', 'general') ORDER BY sort_order"),
        form_opened_at=time.time(), nav_here="support")


@bp.route("/support/new", methods=["GET", "POST"])
def support_new():
    if request.method == "GET":
        return redirect(url_for("public.support"))

    verify_csrf()
    ok, message = _gate("ticket")
    if not ok:
        flash(message, "error")
        return redirect(url_for("public.support"))

    subject = (request.form.get("subject") or "").strip()
    email = (request.form.get("contact_email") or "").strip()
    if not subject or not email:
        flash("A subject and an email address, so we can reply.", "error")
        return redirect(url_for("public.support"))
    if not valid_email(email):
        flash("That email address does not look right.", "error")
        return redirect(url_for("public.support"))

    # Match the reporter to a client by email so the ticket lands on the right
    # account without asking a stressed person to know their reference number.
    client = db.one("SELECT * FROM clients WHERE email = ? AND is_active = 1", (email,))
    if not client:
        contact_row = db.one("SELECT * FROM contacts WHERE email = ?", (email,))
        client = (db.one("SELECT * FROM clients WHERE id = ?", (contact_row["client_id"],))
                  if contact_row else None)

    ticket_id = tickets.create({
        "client_id": client["id"] if client else None,
        "contact_name": (request.form.get("contact_name") or "").strip(),
        "contact_email": email,
        "contact_phone": (request.form.get("contact_phone") or "").strip(),
        "subject": subject,
        "body": (request.form.get("body") or "").strip(),
        "category": request.form.get("category") or "other",
        "priority": request.form.get("priority") or "p3",
        "ip": client_ip(),
    }, source="web")

    ticket = tickets.get(ticket_id)
    state = tickets.sla_state(ticket)
    notify.push(f"Ticket {ticket['ref']}: {subject}",
                f"{ticket['contact_name'] or email} raised a "
                f"{ticket['priority'].upper()} ticket.",
                kind="warn" if ticket["priority"] in ("p1", "p2") else "info",
                url=f"/admin/tickets/{ticket_id}", entity="ticket", entity_id=ticket_id)

    if settings.get("email.notify_on_ticket"):
        from services import mailer
        to = settings.get("contact.support_email") or settings.get("contact.email")
        if to:
            mailer.send(to, f"[{ticket['priority'].upper()}] {ticket['ref']}: {subject}",
                        f"{ticket['contact_name']} <{email}>\n\n{ticket['body']}\n\n"
                        f"Open it: /admin/tickets/{ticket_id}")
        if email:
            mailer.send(email, f"We have your request - {ticket['ref']}",
                        f"Thank you, this is logged as {ticket['ref']}.\n\n"
                        f"We aim to reply within "
                        f"{state['policy']['response_hours']:.0f} hours. Quote the reference "
                        f"if you follow up.\n\n{settings.get('brand.name')}")

    return render_template(
        "public/support_done.html", ticket=ticket, state=state,
        meta=_meta(title=f"Ticket {ticket['ref']}"),
        wa=wa_link(f"Hi, I raised support ticket {ticket['ref']}."), nav_here="support")


@bp.route("/support/status", methods=["GET", "POST"])
def support_status():
    """Look a ticket up by reference and email. No account, no password."""
    ticket = None
    thread = []
    if request.method == "POST":
        verify_csrf()
        ref = (request.form.get("ref") or "").strip().upper()
        email = (request.form.get("email") or "").strip().lower()
        found = tickets.by_ref(ref)
        # Both halves must match, so a guessable reference on its own reveals nothing.
        if found and (found["contact_email"] or "").lower() == email:
            ticket = found
            thread = tickets.messages(found["id"], include_internal=False)
        else:
            flash("No ticket matches that reference and email together.", "error")

    return render_template(
        "public/support_status.html", meta=_meta(title="Check a ticket"),
        ticket=ticket, thread=thread,
        state=tickets.sla_state(ticket) if ticket else None,
        statuses=tickets.TICKET_STATUS_LABELS, nav_here="support")


@bp.route("/support/<ref>/reply", methods=["POST"])
def support_reply(ref):
    verify_csrf()
    ticket = tickets.by_ref(ref)
    email = (request.form.get("email") or "").strip().lower()
    body = (request.form.get("body") or "").strip()
    if not ticket or (ticket["contact_email"] or "").lower() != email:
        abort(404)
    if not body:
        flash("Write something first.", "error")
        return redirect(url_for("public.support_status"))

    tickets.reply(ticket["id"], body, author_kind="client",
                  author_name=ticket["contact_name"] or email)
    notify.push(f"Client replied on {ticket['ref']}", body[:200],
                kind="info", url=f"/admin/tickets/{ticket['id']}",
                entity="ticket", entity_id=ticket["id"])
    flash("Added to your ticket. We will pick it up from there.", "ok")
    return redirect(url_for("public.support_status"))


# ── legal ───────────────────────────────────────────────────────────────────
@bp.route("/legal/<slug>")
def legal(slug):
    row = db.one("SELECT * FROM legal_pages WHERE slug = ? AND is_published = 1", (slug,))
    if not row:
        abort(404)
    return render_template(
        "public/legal.html", row=row,
        meta=_meta(title=row["title"], description=row["intro"]),
        others=db.query("SELECT slug, title FROM legal_pages WHERE is_published = 1 "
                        "AND id != ? ORDER BY sort_order", (row["id"],)),
        nav_here="legal")


# ── shared documents ────────────────────────────────────────────────────────
@bp.route("/d/<token>")
def document_share(token):
    document, share_row = documents.open_share(token)
    if not document:
        reason = {
            "unknown": "That link does not match anything here.",
            "revoked": "That link was withdrawn. Ask us for a fresh one.",
            "expired": "That link has expired. Ask us for a fresh one.",
        }.get(share_row, "That link is not usable.")
        return render_template("public/share_gone.html", reason=reason,
                               meta=_meta(title="Link unavailable")), 404

    documents.record_view(document["id"], share_row["id"], client_ip(),
                          request.headers.get("User-Agent", ""))
    body = load_json(document["body_json"], {})
    return render_template(
        "public/document.html", document=document, share=share_row, body=body,
        clauses=[c for c in documents.clauses_for(document["kind"], active_only=False)
                 if c["id"] in set(body.get("clause_ids") or [])],
        quote=pricing.quote_summary(document["quote_id"]) if document["quote_id"] else None,
        meta=_meta(title=document["title"]),
        accepted=document["status"] == "accepted",
        declined=document["status"] == "declined",
        nav_here="document")


@bp.route("/d/<token>/pdf")
def document_share_pdf(token):
    document, _share = documents.open_share(token)
    if not document:
        abort(404)
    from core.util import slugify
    from services import pdf

    payload = pdf.proposal_pdf(document)
    name = f"{slugify(document['title'] or 'document')}-{document['ref']}.pdf"
    return Response(payload, mimetype="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "no-store"})


@bp.route("/d/<token>/respond", methods=["POST"])
def document_respond(token):
    verify_csrf()
    document, share_row = documents.open_share(token)
    if not document:
        abort(404)

    name = (request.form.get("name") or "").strip()
    if len(name) < 2:
        flash("Type your full name to sign.", "error")
        return redirect(url_for("public.document_share", token=token))

    action = request.form.get("action")
    note = (request.form.get("note") or "").strip()
    if action == "accept":
        if not request.form.get("agree"):
            flash("Tick the box confirming you have read the terms.", "error")
            return redirect(url_for("public.document_share", token=token))
        documents.accept(document["id"], name=name, ip=client_ip(), note=note)
        flash("Accepted. We have it, and a copy is on its way to you.", "ok")
    elif action == "decline":
        documents.decline(document["id"], name=name, note=note, ip=client_ip())
        flash("Recorded. Thank you for telling us either way.", "ok")
    else:
        abort(400)
    return redirect(url_for("public.document_share", token=token))


# ── generic database page, last so it never shadows a real route ────────────
@bp.route("/<slug>")
def page(slug):
    row = _page(slug)
    if not row:
        abort(404)
    return render_template(
        "public/page.html", page=row, blocks=_blocks(row), meta=_meta(row),
        nav_here=slug)


# ── robots and sitemap ──────────────────────────────────────────────────────
@bp.route("/robots.txt")
def robots():
    base = _base_url()
    if not settings.get("seo.indexable"):
        body = "User-agent: *\nDisallow: /\n"
    else:
        body = ("User-agent: *\n"
                "Allow: /\n"
                "Disallow: /admin\n"
                "Disallow: /portal\n"
                "Disallow: /d/\n"
                f"Sitemap: {base}/sitemap.xml\n")
    return Response(body, mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    base = _base_url()
    urls = [(f"{base}/", "1.0", "weekly")]

    for row in db.query("SELECT slug, updated_at FROM pages WHERE is_published = 1 "
                        "AND slug != 'home' ORDER BY sort_order"):
        urls.append((f"{base}/{row['slug']}", "0.7", "monthly"))
    for row in db.query("SELECT slug, updated_at FROM services WHERE is_published = 1"):
        urls.append((f"{base}/services/{row['slug']}", "0.9", "monthly"))
    for row in db.query("SELECT slug FROM case_studies WHERE is_published = 1"):
        urls.append((f"{base}/work/{row['slug']}", "0.8", "monthly"))
    for row in db.query("SELECT slug FROM posts WHERE is_published = 1"):
        urls.append((f"{base}/insights/{row['slug']}", "0.6", "monthly"))
    for row in db.query("SELECT slug FROM legal_pages WHERE is_published = 1"):
        urls.append((f"{base}/legal/{row['slug']}", "0.3", "yearly"))

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, priority, freq in urls:
        parts.append(f"  <url><loc>{loc}</loc><changefreq>{freq}</changefreq>"
                     f"<priority>{priority}</priority></url>")
    parts.append("</urlset>")
    return Response("\n".join(parts), mimetype="application/xml")


def _base_url() -> str:
    return (current_app.config.get("PUBLIC_BASE_URL") or request.host_url.rstrip("/"))


# ── the gate every public form goes through ─────────────────────────────────
def _gate(kind: str) -> tuple[bool, str]:
    """Honeypot, timing and per-IP rate limit, in that order.

    Each one on its own is weak; together they stop the volume of automated junk
    that a small site actually gets, without putting a captcha in front of a real
    customer.
    """
    if (request.form.get("website") or request.form.get("_hp") or "").strip():
        # A hidden field only a bot fills in. Answer as though it worked, so the
        # bot has no signal to adapt to.
        return False, "Thank you, that is with us."

    opened = parse_float(request.form.get("opened_at"), 0)
    if opened and (time.time() - opened) < MIN_SECONDS_ON_FORM:
        return False, "That went through faster than a form can be filled in. Try once more."

    ip = client_ip()
    recent = parse_int(db.scalar(
        "SELECT COUNT(*) FROM leads WHERE ip = ? "
        f"AND created_at >= datetime('now', '-{RATE_WINDOW_MINUTES} minutes')", (ip,), 0))
    recent += parse_int(db.scalar(
        "SELECT COUNT(*) FROM tickets WHERE ip = ? "
        f"AND created_at >= datetime('now', '-{RATE_WINDOW_MINUTES} minutes')", (ip,), 0))
    if recent >= RATE_MAX_PER_IP:
        return False, ("That is several submissions in the last hour. Message us on WhatsApp "
                       "instead and we will pick it up straight away.")
    return True, ""


@bp.app_template_filter("md_lite")
def md_lite(text: str):
    """The three pieces of Markdown the editors actually use, and nothing else.

    A full Markdown dependency for headings, bold and links is not worth the
    supply chain; anything richer belongs in a page block.
    """
    import html
    import re

    escaped = html.escape(str(text or ""))
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\[(.+?)\]\((https?://[^\s)]+|/[^\s)]*)\)",
                     r'<a href="\2">\1</a>', escaped)

    blocks = []
    for chunk in re.split(r"\n{2,}", escaped.strip()):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith(("- ", "* ")) for line in lines):
            items = "".join(f"<li>{line[2:].strip()}</li>" for line in lines)
            blocks.append(f"<ul>{items}</ul>")
        elif lines[0].startswith("### "):
            blocks.append(f"<h3>{lines[0][4:]}</h3>"
                          + ("<p>" + " ".join(lines[1:]) + "</p>" if len(lines) > 1 else ""))
        elif lines[0].startswith("## "):
            blocks.append(f"<h2>{lines[0][3:]}</h2>"
                          + ("<p>" + " ".join(lines[1:]) + "</p>" if len(lines) > 1 else ""))
        else:
            blocks.append("<p>" + "<br>".join(lines) + "</p>")
    # Safe to mark: the input was escaped before any tag was added.
    return Markup("".join(blocks))
