"""Settings, the team and lead sources.

Settings are declared here as tabs of typed fields rather than being free-form
key/value editing, because a panel that lets you type "eighteen" into the GST rate
is not a settings screen, it is a trap.
"""

from __future__ import annotations

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from blueprints.admin import bp
from core import audit, auth, crud, db, settings
from core.auth import PERMISSIONS, ROLES, require_role, verify_csrf
from core.crud import Field, Resource
from core.util import (parse_bool, parse_float, parse_int, split_lines, valid_email,
                       wa_number)
from services import whatsapp

# (key, label, kind, help). kind drives both the input and how the value is parsed.
TABS: dict[str, tuple[str, str, list]] = {
    "brand": ("Brand", "Who you are, everywhere it appears.", [
        ("brand.name", "Studio name", "text", "Used in the nav, emails and every document."),
        ("brand.legal_name", "Legal or trading name", "text",
         "What goes on an invoice, if it differs from the trading name."),
        ("brand.short", "Short name", "text", "For tight spaces and page titles."),
        ("brand.tagline", "Tagline", "text", ""),
        ("brand.promise", "Promise", "textarea", "The sentence under the home page headline."),
        ("brand.about", "About", "textarea", "Used on the about page and in structured data."),
        ("brand.founder", "Founder name", "text", ""),
        ("brand.established", "Established", "text", ""),
        ("brand.city", "City", "text", ""),
        ("brand.state", "State", "text", ""),
        ("brand.logo_media_id", "Logo", "media", ""),
        ("brand.signature_media_id", "Signature image", "media",
         "A transparent PNG, placed above your name on documents."),
    ]),
    "contact": ("Contact", "How people reach you, and where enquiries land.", [
        ("contact.phone", "Phone", "tel", ""),
        ("contact.phone_display", "Phone as displayed", "text", ""),
        ("contact.whatsapp", "WhatsApp number", "tel",
         "Digits with country code, e.g. 919000000000. Every wa.me link is built from this."),
        ("contact.email", "Enquiry email", "email", ""),
        ("contact.support_email", "Support email", "email", ""),
        ("contact.address", "Address", "textarea", ""),
        ("contact.map_url", "Google Maps link", "url", ""),
        ("contact.hours_note", "Working hours", "text", ""),
        ("social.instagram", "Instagram", "url", ""),
        ("social.linkedin", "LinkedIn", "url", ""),
        ("social.x", "X", "url", ""),
        ("social.github", "GitHub", "url", ""),
        ("social.youtube", "YouTube", "url", ""),
        ("social.google_review_url", "Google review link", "url",
         "Where the review request sends people."),
    ]),
    "theme": ("Look", "Colours and type for the public site. Layout stays in code.", [
        ("theme.primary", "Primary", "colour", ""),
        ("theme.primary_dark", "Primary, darker", "colour", ""),
        ("theme.accent", "Accent", "colour", ""),
        ("theme.warm", "Warm accent", "colour", ""),
        ("theme.ink", "Ink", "colour", ""),
        ("theme.ink_soft", "Ink, softer", "colour", ""),
        ("theme.muted", "Muted text", "colour", ""),
        ("theme.surface", "Surface", "colour", ""),
        ("theme.canvas", "Page background", "colour", ""),
        ("theme.line", "Hairlines", "colour", ""),
        ("theme.radius", "Corner radius, px", "int", ""),
        ("theme.font_display", "Display font", "text", ""),
        ("theme.font_body", "Body font", "text", ""),
        ("theme.font_url", "Web font URL", "url",
         "Leave blank to fall back to system fonts and drop one network request."),
        ("theme.animations", "Animations on", "bool",
         "Off disables the reveals and parallax for everyone. A visitor's own "
         "reduced-motion setting is always honoured regardless of this."),
    ]),
    "seo": ("SEO", "What search engines and link previews are told.", [
        ("seo.title_suffix", "Title suffix", "text", "Appended after a pipe on every page."),
        ("seo.default_description", "Fallback description", "textarea",
         "Used when a page has none of its own."),
        ("seo.og_media_id", "Share image", "media", "1200x630 works everywhere."),
        ("seo.indexable", "Allow indexing", "bool",
         "Off sends noindex and a blocking robots.txt. Keep it off until launch."),
        ("seo.ga4_id", "GA4 measurement ID", "text", "G-XXXXXXX. Blank means no analytics."),
        ("seo.search_console_tag", "Search Console verification", "text",
         "Just the content value of the meta tag."),
    ]),
    "whatsapp": ("WhatsApp", "", [
        ("whatsapp.provider", "How messages go out", "select", ""),
        ("whatsapp.default_country_code", "Default country code", "text",
         "Applied to numbers saved without one."),
        ("whatsapp.signature", "Signature", "textarea",
         "Appended to every message. Placeholders work here too."),
        ("whatsapp.bulk_throttle_seconds", "Seconds between bulk sends", "int", ""),
        ("whatsapp.bulk_daily_cap", "Daily bulk cap", "int", ""),
        ("whatsapp.cloud_phone_number_id", "Cloud phone number ID", "text", ""),
        ("whatsapp.cloud_waba_id", "WhatsApp Business account ID", "text", ""),
        ("whatsapp.cloud_token", "Permanent access token", "secret", ""),
        ("whatsapp.cloud_verify_token", "Webhook verify token", "secret",
         "You invent this, then paste the same string into Meta's webhook setup."),
        ("whatsapp.cloud_app_secret", "App secret", "secret",
         "Used to check that an inbound webhook really came from Meta."),
        ("whatsapp.cloud_api_version", "Graph API version", "text", ""),
    ]),
    "email": ("Email", "Optional. Everything works without it, just more manually.", [
        ("email.enabled", "Send email", "bool", ""),
        ("email.from_name", "From name", "text", ""),
        ("email.reply_to", "Reply-to", "email", ""),
        ("email.notify_on_lead", "Tell me about new enquiries", "bool", ""),
        ("email.notify_on_ticket", "Tell me about new tickets", "bool", ""),
        ("email.signature", "Signature", "textarea", ""),
    ]),
    "tax": ("Tax and invoicing", "", [
        ("gst.mode", "Invoice mode", "select",
         "Bill of supply is correct while you are not GST registered. Switching to tax "
         "invoice turns on HSN/SAC, place of supply and the CGST/SGST/IGST split on every "
         "new document. Existing documents keep the mode they were issued under."),
        ("gst.gstin", "GSTIN", "text", ""),
        ("gst.state_code", "Your state code", "text",
         "First two digits of the GSTIN. Decides intra-state versus inter-state tax."),
        ("gst.default_rate", "Default GST rate, percent", "number", ""),
        ("gst.default_sac", "Default SAC code", "text", "998314 is IT design and development."),
        ("gst.composition", "Composition scheme", "bool",
         "Adds the mandatory composition declaration and stops tax being charged."),
        ("gst.reverse_charge_note", "Reverse charge note", "text", ""),
        ("tax.pan", "PAN", "text", ""),
        ("tax.tds_note", "TDS note", "textarea", ""),
        ("invoice.prefix", "Number prefix", "text",
         "Numbers read PREFIX/INV/2026-27/001. Changing this mid-year makes the series "
         "look discontinuous, so pick it once."),
        ("invoice.terms_days", "Payment terms, days", "int", ""),
        ("invoice.late_fee_pct_month", "Late fee, percent per month", "number", ""),
        ("invoice.footer_note", "Invoice footer", "textarea", ""),
        ("invoice.upi_id", "UPI ID", "text", ""),
        ("invoice.upi_qr_media_id", "UPI QR image", "media", ""),
        ("invoice.bank_name", "Bank", "text", ""),
        ("invoice.bank_account_name", "Account name", "text", ""),
        ("invoice.bank_account_no", "Account number", "text", ""),
        ("invoice.bank_ifsc", "IFSC", "text", ""),
        ("invoice.bank_branch", "Branch", "text", ""),
        ("invoice.payment_methods", "Payment methods", "lines",
         "One per line. These are the options on the payment form."),
    ]),
    "documents": ("Documents", "Defaults that go into every proposal and contract.", [
        ("doc.jurisdiction_city", "Jurisdiction city", "text", ""),
        ("doc.jurisdiction_state", "Jurisdiction state", "text", ""),
        ("doc.arbitration_seat", "Arbitration seat", "text", ""),
        ("doc.arbitration_language", "Arbitration language", "text", ""),
        ("doc.validity_days", "Quote validity, days", "int", ""),
        ("doc.share_expiry_days", "Share link expiry, days", "int", ""),
        ("doc.signatory_name", "Who signs", "text", ""),
        ("doc.signatory_title", "Their title", "text", ""),
        ("doc.assumptions", "Standard assumptions", "lines",
         "One per line. These appear in every proposal and are what you point at when "
         "scope starts drifting."),
    ]),
    "pricing": ("Pricing", "", [
        ("pricing.currency", "Currency", "text", ""),
        ("pricing.rounding", "Round totals to", "int",
         "100 gives prices ending in 00. Set to 1 for no rounding."),
        ("pricing.rush_pct", "Rush surcharge, percent", "number", ""),
        ("pricing.annual_prepay_discount_pct", "Annual prepay discount, percent", "number", ""),
        ("pricing.referral_discount_pct", "Referral discount, percent", "number", ""),
        ("pricing.extra_page_rate", "Per extra page", "money", ""),
        ("pricing.show_public_calculator", "Public calculator on", "bool",
         "The /pricing page. Off leaves the packages visible without the estimator."),
        ("pricing.public_note", "Note under the calculator", "textarea", ""),
    ]),
    "support": ("Support", "", [
        ("sla.p1_response_hours", "P1 respond within, hours", "number", ""),
        ("sla.p1_resolve_hours", "P1 resolve within, hours", "number", ""),
        ("sla.p2_response_hours", "P2 respond within, hours", "number", ""),
        ("sla.p2_resolve_hours", "P2 resolve within, hours", "number", ""),
        ("sla.p3_response_hours", "P3 respond within, hours", "number", ""),
        ("sla.p3_resolve_hours", "P3 resolve within, hours", "number", ""),
        ("sla.p4_response_hours", "P4 respond within, hours", "number", ""),
        ("sla.p4_resolve_hours", "P4 resolve within, hours", "number", ""),
        ("sla.at_risk_pct", "Flag at risk after, percent of budget", "number", ""),
        ("ticket.default_rate_per_hour", "Support rate per hour", "money", ""),
        ("ticket.intro", "What the public form asks for", "textarea", ""),
    ]),
    "portal": ("Client portal", "", [
        ("portal.enabled", "Portal on", "bool", ""),
        ("portal.code_ttl_minutes", "Login code valid for, minutes", "int", ""),
        ("portal.session_days", "Stay signed in for, days", "int", ""),
        ("portal.welcome", "Welcome line", "textarea", ""),
    ]),
    "crm": ("Leads", "", [
        ("crm.followup_days", "Default follow-up gap, days", "int", ""),
        ("crm.dormant_after_days", "Mark dormant after, days", "int",
         "A lead with no contact for this long is moved to dormant by the daily sweep."),
        ("crm.referral_payout_pct", "Referral payout, percent", "number", ""),
        ("crm.budget_bands", "Budget bands", "lines", "One per line, in the order shown."),
        ("crm.lost_reasons", "Lost reasons", "lines", "One per line."),
        ("crm.lead_success_title", "Thank-you heading", "text", ""),
        ("crm.lead_success_body", "Thank-you text", "textarea", ""),
    ]),
    "ops": ("Operations", "", [
        ("analytics.cost_per_hour", "Your cost per hour", "money",
         "Rent, tools and your own time divided by the hours you actually sell. Used for "
         "the effective-rate column on a project."),
        ("analytics.monthly_revenue_target", "Monthly revenue target", "money", ""),
        ("analytics.working_days_per_month", "Working days per month", "int", ""),
        ("ops.expiry_warn_days", "Warn about expiries, days ahead", "int", ""),
        ("ops.renewal_notice_days", "Renewal notice, days ahead", "int", ""),
        ("ops.digest_enabled", "Daily digest on", "bool", ""),
        ("ops.vault_enabled", "Credential vault on", "bool",
         "Off hides the secret fields. The assets list stays, because expiry dates are "
         "useful even when you keep passwords elsewhere."),
    ]),
}

SELECTS = {
    "gst.mode": [("bill_of_supply", "Bill of supply - not GST registered"),
                 ("tax_invoice", "Tax invoice - GST registered")],
    "whatsapp.provider": [("click_to_chat", "Click to chat - opens WhatsApp with the message ready"),
                          ("cloud_api", "Meta WhatsApp Cloud API - sends automatically")],
}


@bp.route("/settings", methods=["GET", "POST"])
@bp.route("/settings/<tab>", methods=["GET", "POST"])
@require_role("settings")
def settings_view(tab: str = "brand"):
    if tab not in TABS:
        abort(404)
    label, intro, spec = TABS[tab]

    if request.method == "POST":
        verify_csrf()
        changed = {}
        for key, _label, kind, _help in spec:
            if kind == "bool":
                value = parse_bool(request.form.get(key))
            else:
                raw = request.form.get(key)
                if raw is None:
                    continue
                value = _parse(kind, raw)
            if key == "contact.whatsapp":
                value = wa_number(str(value), settings.get("whatsapp.default_country_code") or "91")
            if settings.get(key) != value:
                changed[key] = value

        if "gst.mode" in changed:
            flash("Invoice mode changed. Documents already issued keep the mode they went out "
                  "under - only new ones follow the new setting.", "ok")
        if changed.get("whatsapp.provider") == "cloud_api" and not _cloud_ready():
            flash("Cloud API needs a phone number ID and a token before it can send. Saved, "
                  "but sends will fall back to click-to-chat until those are filled in.", "error")

        settings.set_many(changed)
        if changed:
            audit.log("update", "settings", tab, label,
                      after={k: ("hidden" if k.endswith(("token", "secret")) else v)
                             for k, v in changed.items()})
        flash(f"{label} saved." if changed else "Nothing changed.", "ok")
        return redirect(url_for("admin.settings_view", tab=tab))

    fields = []
    for key, field_label, kind, help_text in spec:
        fields.append({
            "key": key, "label": field_label, "kind": kind, "help": help_text,
            "value": settings.get(key),
            "text": _to_text(kind, settings.get(key)),
            "options": SELECTS.get(key, []),
        })

    return render_template(
        "admin/settings.html", title="Settings", tab=tab, tabs=TABS, fields=fields,
        intro=intro, tab_label=label,
        cloud_ready=_cloud_ready(), provider=whatsapp.provider_name(),
        gst_on=settings.gst_on(), nav_active="admin.settings_view")


def _parse(kind: str, raw: str):
    if kind == "int":
        return parse_int(raw, 0)
    if kind in ("number", "money"):
        return parse_float(raw, 0)
    if kind == "lines":
        return split_lines(raw)
    if kind == "media":
        return parse_int(raw, 0) or None
    return raw.strip()


def _to_text(kind: str, value) -> str:
    if kind == "lines":
        if isinstance(value, list):
            return "\n".join(str(v) for v in value)
        return str(value or "")
    if value is None:
        return ""
    return str(value)


def _cloud_ready() -> bool:
    return bool(settings.get("whatsapp.cloud_phone_number_id")
                and settings.get("whatsapp.cloud_token"))


# ── the team ────────────────────────────────────────────────────────────────
@bp.route("/users")
@require_role("users")
def users_list():
    return render_template(
        "admin/users.html", title="Team",
        rows=db.query("SELECT * FROM users ORDER BY role, name"),
        # The page shows what each role reaches, so it wants the permission map
        # rather than the bare list of role names.
        roles=PERMISSIONS, nav_active="admin.users_list")


@bp.route("/users/new", methods=["GET", "POST"])
@require_role("users")
def user_new():
    if request.method == "POST":
        verify_csrf()
        email = (request.form.get("email") or "").strip().lower()
        name = (request.form.get("name") or "").strip()
        password = request.form.get("password") or ""
        role = request.form.get("role") or "staff"

        error = ""
        if not valid_email(email):
            error = "That email does not look right."
        elif auth.find_user(email):
            error = "Someone already has that email."
        elif len(password) < 10:
            error = "Use at least 10 characters."
        elif role not in ROLES:
            error = "Unknown role."
        elif role == "owner":
            error = ("There is one owner, and it is you. Give them admin if they need "
                     "everything except the money and vault controls.")

        if error:
            flash(error, "error")
            return render_template("admin/user_form.html", title="New person", row=None,
                                   roles=ROLES, nav_active="admin.users_list")

        user_id = db.insert("users", {
            "email": email, "name": name or email.split("@")[0],
            "password_hash": auth.hash_password(password), "role": role,
            "phone": (request.form.get("phone") or "").strip(),
        })
        audit.log("create", "users", user_id, email, after={"role": role})
        flash(f"{name or email} can sign in now.", "ok")
        return redirect(url_for("admin.users_list"))

    return render_template("admin/user_form.html", title="New person", row=None,
                           roles=ROLES, nav_active="admin.users_list")


@bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@require_role("users")
def user_edit(user_id):
    row = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not row:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        changes = {
            "name": (request.form.get("name") or row["name"]).strip(),
            "phone": (request.form.get("phone") or "").strip(),
        }
        role = request.form.get("role")
        if row["role"] != "owner" and role in ROLES and role != "owner":
            changes["role"] = role
        password = request.form.get("password") or ""
        if password:
            if len(password) < 10:
                flash("Use at least 10 characters.", "error")
                return redirect(url_for("admin.user_edit", user_id=user_id))
            changes["password_hash"] = auth.hash_password(password)

        db.update("users", user_id, changes)
        audit.log("update", "users", user_id, row["email"],
                  after={k: v for k, v in changes.items() if k != "password_hash"})
        flash("Saved." + (" They will need the new password." if password else ""), "ok")
        return redirect(url_for("admin.users_list"))

    return render_template("admin/user_form.html", title=row["name"] or row["email"], row=row,
                           roles=ROLES, nav_active="admin.users_list")


@bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@require_role("users")
def user_toggle(user_id):
    verify_csrf()
    row = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not row:
        abort(404)
    if row["role"] == "owner":
        flash("The owner account cannot be switched off - you would lock yourself out.",
              "error")
        return redirect(url_for("admin.users_list"))
    new_value = 0 if row["is_active"] else 1
    db.update("users", user_id, {"is_active": new_value})
    audit.log("update", "users", user_id, row["email"], after={"is_active": new_value})
    flash("Access restored." if new_value else "Access revoked.", "ok")
    return redirect(url_for("admin.users_list"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@require_role("owner")
def user_delete(user_id):
    verify_csrf()
    row = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not row:
        abort(404)
    if row["role"] == "owner":
        flash("The owner account stays.", "error")
        return redirect(url_for("admin.users_list"))
    db.delete("users", user_id)
    audit.log("delete", "users", user_id, row["email"])
    flash("Removed. Anything they did stays in the activity log.", "ok")
    return redirect(url_for("admin.users_list"))


# ── lead sources ────────────────────────────────────────────────────────────
SOURCES = Resource(
    key="sources", table="lead_sources", label="Lead source", label_plural="Lead sources",
    area="settings", row_label="name", slug_from="name", sortable=True, activatable=True,
    icon="funnel",
    intro="Where enquiries come from. Recording the monthly cost is what turns the source "
          "report into a return-on-spend answer instead of a popularity contest.",
    list_columns=[("name", "Source"), ("cost_monthly", "Monthly cost"), ("is_paid", "Paid")],
    fields=[
        Field("name", "Name", "text", required=True, span=6),
        Field("slug", "Slug", "slug", span=6,
              help="Used in ?src= links, so a campaign can tag itself."),
        Field("is_paid", "This costs money", "bool", span=6),
        Field("cost_monthly", "Monthly cost", "money", span=6,
              help="Ad spend, listing fee or retainer. Divided across the leads it brought "
                   "to give a cost per lead and per client."),
        Field("notes", "Notes", "textarea", rows=2, span=12),
        Field("is_active", "Active", "bool", span=6, default=1),
    ],
)

crud.register(bp, SOURCES)


@bp.route("/settings/test-whatsapp", methods=["POST"])
@require_role("settings")
def settings_test_whatsapp():
    """Send one message to yourself to prove the Cloud API credentials work."""
    verify_csrf()
    number = wa_number(settings.get("contact.whatsapp") or "",
                       settings.get("whatsapp.default_country_code") or "91")
    if not number:
        return jsonify({"ok": False, "error": "Set your own WhatsApp number first."}), 400
    result = whatsapp.send_test(number)
    return jsonify(result), (200 if result.get("ok") else 400)
