"""Typed key/value settings, cached for the life of a request.

Every value is stored as JSON so a setting can be a string, a number, a list of
payment methods or a whole nested block. DEFAULTS below is the single source of
truth for what Aruka expects to find, and the onboarding wizard writes over the
handful an owner must personalise before anything leaves the building.
"""

from __future__ import annotations

import json

from flask import g

from core import db

DEFAULTS: dict = {
    # ── brand ───────────────────────────────────────────────────────────────
    "brand.name": "Aruka",
    "brand.legal_name": "Aruka Digital",
    "brand.tagline": "Digital presence, built properly",
    "brand.promise": "Websites, software and automation for brands that are done waiting.",
    "brand.short": "Aruka",
    "brand.logo_media_id": None,
    "brand.signature_media_id": None,
    "brand.city": "Pune",
    "brand.state": "Maharashtra",
    "brand.established": "2024",
    "brand.founder": "",
    "brand.about": (
        "Aruka is a small studio that gives brands a digital presence they can "
        "actually run. We build the site, wire the automation behind it, and stay "
        "on for the part everyone else calls out of scope."
    ),

    # ── contact ─────────────────────────────────────────────────────────────
    "contact.phone": "+91 90000 00000",
    "contact.phone_display": "+91 90000 00000",
    "contact.whatsapp": "919000000000",
    "contact.email": "hello@aruka.studio",
    "contact.support_email": "support@aruka.studio",
    "contact.address": "Pune, Maharashtra, India",
    "contact.map_url": "",
    "contact.hours_note": "Monday to Saturday, 10am to 7pm IST.",

    # ── socials ─────────────────────────────────────────────────────────────
    "social.instagram": "",
    "social.linkedin": "",
    "social.x": "",
    "social.github": "",
    "social.youtube": "",
    "social.google_review_url": "",

    # ── theme ───────────────────────────────────────────────────────────────
    # Warm paper, near-black ink, one rust accent, and a serif that carries the
    # headlines. The primary is ink rather than a colour on purpose: a saturated
    # brand hue on every button is what makes a site look generated, and it leaves
    # nothing louder for the accent to be.
    "theme.primary": "#17140F",
    "theme.primary_dark": "#000000",
    "theme.accent": "#B8431C",
    "theme.warm": "#A6741A",
    "theme.ink": "#17140F",
    "theme.ink_soft": "#2C2720",
    "theme.muted": "#6B6459",
    "theme.surface": "#FFFFFF",
    "theme.canvas": "#F5F2EB",
    "theme.line": "#E1DBCE",
    # Six, not eighteen. A large radius on every corner reads as a template.
    "theme.radius": "6",
    "theme.font_display": "Instrument Serif",
    "theme.font_body": "Inter",
    "theme.font_url": (
        "https://fonts.googleapis.com/css2?"
        "family=Instrument+Serif:ital@0;1&"
        "family=Inter:wght@300..700&display=swap"
    ),
    "theme.animations": True,

    # ── seo ─────────────────────────────────────────────────────────────────
    "seo.title_suffix": "Aruka",
    "seo.default_description": (
        "Aruka builds websites, SaaS products, AI automations and SEO for Indian "
        "brands. Fixed scope, written quotes, and support that answers."
    ),
    "seo.og_media_id": None,
    "seo.indexable": True,
    "seo.ga4_id": "",
    "seo.search_console_tag": "",

    # ── whatsapp ────────────────────────────────────────────────────────────
    # provider: click_to_chat is the day-one path and needs no account at all;
    # cloud_api is written and tested but stays off until a verified Business
    # number and approved templates exist.
    "whatsapp.provider": "click_to_chat",
    "whatsapp.default_country_code": "91",
    "whatsapp.cloud_phone_number_id": "",
    "whatsapp.cloud_token": "",
    "whatsapp.cloud_waba_id": "",
    "whatsapp.cloud_verify_token": "",
    "whatsapp.cloud_app_secret": "",
    "whatsapp.cloud_api_version": "v21.0",
    "whatsapp.bulk_throttle_seconds": 4,
    "whatsapp.bulk_daily_cap": 200,
    "whatsapp.signature": "\n\n- {{ brand }}",

    # ── email ───────────────────────────────────────────────────────────────
    "email.enabled": False,
    "email.from_name": "Aruka",
    "email.reply_to": "",
    "email.notify_on_lead": True,
    "email.notify_on_ticket": True,
    "email.signature": "Aruka | aruka.studio",

    # ── tax and invoicing ───────────────────────────────────────────────────
    # gst.mode: bill_of_supply until registration comes through, then tax_invoice.
    "gst.mode": "bill_of_supply",
    "gst.gstin": "",
    "gst.state_code": "27",
    "gst.default_rate": 18,
    "gst.default_sac": "998314",
    "gst.composition": False,
    "gst.reverse_charge_note": "Tax is not payable under reverse charge.",
    "tax.pan": "",
    "tax.tds_note": (
        "Where the client is required to deduct tax at source under section 194J "
        "or 194C of the Income-tax Act 1961, the deduction shall be made at the "
        "prescribed rate and Form 16A furnished within the statutory timeline."
    ),

    "invoice.prefix": "ARK",
    "invoice.terms_days": 7,
    "invoice.late_fee_pct_month": 1.5,
    "invoice.footer_note": (
        "Thank you for working with Aruka. Please quote the invoice number with "
        "your transfer so it can be matched on the same day."
    ),
    "invoice.upi_id": "",
    "invoice.upi_qr_media_id": None,
    "invoice.bank_name": "",
    "invoice.bank_account_name": "",
    "invoice.bank_account_no": "",
    "invoice.bank_ifsc": "",
    "invoice.bank_branch": "",
    "invoice.payment_methods": ["UPI", "Bank transfer (NEFT/IMPS)", "Cheque", "Cash"],

    # ── documents ───────────────────────────────────────────────────────────
    "doc.jurisdiction_city": "Pune",
    "doc.jurisdiction_state": "Maharashtra",
    "doc.arbitration_seat": "Pune",
    "doc.arbitration_language": "English",
    "doc.validity_days": 15,
    "doc.share_expiry_days": 30,
    "doc.signatory_name": "",
    "doc.signatory_title": "Founder",
    "doc.milestone_split": [
        {"label": "On acceptance", "pct": 40},
        {"label": "On staging approval", "pct": 40},
        {"label": "On go-live", "pct": 20},
    ],
    "doc.assumptions": [
        "Content, logo files and access credentials are supplied by the client before the build starts.",
        "One consolidated round of feedback is provided per milestone.",
        "Third-party licence and subscription costs are billed at actuals.",
        "Timelines pause while we are waiting on the client.",
    ],

    # ── pricing ─────────────────────────────────────────────────────────────
    "pricing.currency": "INR",
    "pricing.rounding": 100,
    "pricing.rush_pct": 25,
    "pricing.annual_prepay_discount_pct": 10,
    "pricing.referral_discount_pct": 5,
    "pricing.extra_page_rate": 900,
    "pricing.show_public_calculator": True,
    "pricing.public_note": (
        "This is a real estimate from the same rate card we quote from. The written "
        "proposal confirms it, and nothing is charged until you accept."
    ),

    # ── tickets ─────────────────────────────────────────────────────────────
    "sla.p1_response_hours": 4,
    "sla.p2_response_hours": 12,
    "sla.p3_response_hours": 24,
    "sla.p4_response_hours": 72,
    "sla.p1_resolve_hours": 12,
    "sla.p2_resolve_hours": 48,
    "sla.p3_resolve_hours": 120,
    "sla.p4_resolve_hours": 240,
    "sla.at_risk_pct": 75,
    "sla.business_hours_only": False,
    "ticket.default_rate_per_hour": 1200,
    "ticket.intro": (
        "Tell us what broke, when it started and what you were doing at the time. "
        "Screenshots help more than anything else."
    ),

    # ── portal ──────────────────────────────────────────────────────────────
    "portal.enabled": True,
    "portal.code_ttl_minutes": 20,
    "portal.session_days": 14,
    "portal.welcome": (
        "Everything Aruka is building for you, in one place: progress, invoices, "
        "documents and support."
    ),

    # ── crm ─────────────────────────────────────────────────────────────────
    "crm.stage_probability": {
        "new": 5, "contacted": 15, "qualified": 35, "quoted": 55,
        "negotiation": 75, "won": 100, "lost": 0, "dormant": 2,
    },
    "crm.followup_days": 2,
    "crm.dormant_after_days": 30,
    "crm.lead_success_title": "Thank you, that is with us",
    "crm.lead_success_body": (
        "We reply to every enquiry within one working day, usually much sooner. "
        "Keep the reference below - quote it if you message us first."
    ),
    "crm.budget_bands": [
        "Under \u20b910,000", "\u20b910,000 - \u20b930,000", "\u20b930,000 - \u20b975,000",
        "\u20b975,000 - \u20b92,00,000", "Above \u20b92,00,000", "Not sure yet",
    ],
    "crm.lost_reasons": [
        "Price", "Timeline", "Went with another agency", "Built in-house",
        "Project shelved", "No response", "Not a fit",
    ],
    "crm.referral_payout_pct": 5,

    # ── analytics ───────────────────────────────────────────────────────────
    # Your own cost per hour, used for the effective-rate column on a project.
    # Rent, tools and your own time divided by the hours you actually sell.
    "analytics.cost_per_hour": 400,
    "analytics.monthly_revenue_target": 100000,
    "analytics.working_days_per_month": 22,

    # ── ops ─────────────────────────────────────────────────────────────────
    "ops.onboarded": False,
    "ops.expiry_warn_days": 30,
    "ops.renewal_notice_days": 21,
    "ops.digest_enabled": True,
    "ops.vault_enabled": True,
}


def _cache() -> dict:
    if not hasattr(g, "_settings_cache"):
        rows = db.query("SELECT key, value FROM settings")
        store = {}
        for row in rows:
            try:
                store[row["key"]] = json.loads(row["value"]) if row["value"] is not None else None
            except (ValueError, TypeError):
                store[row["key"]] = row["value"]
        g._settings_cache = store
    return g._settings_cache


def get(key: str, default=None):
    store = _cache()
    if key in store:
        return store[key]
    if key in DEFAULTS:
        return DEFAULTS[key]
    return default


def set(key: str, value) -> None:  # noqa: A001 - deliberate settings API
    payload = json.dumps(value)
    db.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
        (key, payload),
    )
    _cache()[key] = value


def set_many(items: dict) -> None:
    for key, value in items.items():
        set(key, value)


def all_settings() -> dict:
    merged = dict(DEFAULTS)
    merged.update(_cache())
    return merged


def group(prefix: str) -> dict:
    """All settings under a prefix, with the prefix stripped from the keys."""
    out = {}
    for key, value in all_settings().items():
        if key.startswith(prefix + "."):
            out[key[len(prefix) + 1:]] = value
    return out


def ensure_defaults() -> None:
    """Write any missing default into the table so the admin can see every knob."""
    existing = {r["key"] for r in db.query("SELECT key FROM settings")}
    for key, value in DEFAULTS.items():
        if key not in existing:
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
    if hasattr(g, "_settings_cache"):
        del g._settings_cache


def reset_defaults() -> None:
    """Put every setting back to the value shipped in DEFAULTS.

    Only `seed --force` calls this. It is destructive of configuration - brand,
    contact details, WhatsApp credentials, tax mode - so nothing else should.
    """
    for key, value in DEFAULTS.items():
        db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = datetime('now')",
            (key, json.dumps(value)),
        )
    if hasattr(g, "_settings_cache"):
        del g._settings_cache


def gst_on() -> bool:
    """One place asks the question, so switching modes is genuinely one field."""
    return get("gst.mode") == "tax_invoice"


def onboarded() -> bool:
    return bool(get("ops.onboarded", False))
