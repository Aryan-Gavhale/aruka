"""Starting content, rate card and clause library.

Run with `python app.py seed`. Every insert is keyed on a slug or code and skipped
when it already exists, so seeding twice is safe and a later release can add rows
without touching what the owner has edited. `--force` only affects settings, which
it resets to defaults.

The prices here are the ones the studio actually opens with: a static site with a
year of hosting, a domain and enquiry capture at 4,999, and each tier above it
priced from the same rate card the calculator reads.
"""

from __future__ import annotations

from core import db, settings

# ── packages ────────────────────────────────────────────────────────────────
PACKAGES = [
    {
        "slug": "starter", "name": "Starter", "category": "website",
        "tagline": "A real website, live in a fortnight, with the enquiries coming to you",
        "price": 4999, "internal_cost": 1400, "pages_included": 5,
        "delivery_days": 14, "support_months": 1,
        "recurring_yearly": 3499, "recurring_label": "Hosting, domain and SSL after year one",
        "best_for": "A new brand that needs to exist properly online this month.",
        "is_featured": 0, "sort_order": 0,
        "features": "\n".join([
            "Up to 5 pages, written to your content",
            "Mobile-first design from your brand colours",
            "Domain for one year (.in or .com)",
            "Hosting and SSL for one year",
            "Enquiry form with every submission stored and emailed to you",
            "WhatsApp button wired to your number",
            "Google Analytics and Search Console set up",
            "Basic on-page SEO: titles, descriptions, sitemap",
            "Google Business Profile tidied up",
            "One round of revisions before launch",
            "30 days of support after go-live",
        ]),
        "excluded": "\n".join([
            "Logo design or brand identity",
            "Copywriting beyond light editing of what you send",
            "Stock photography licences",
            "Payments, logins or anything a visitor signs into",
            "Ongoing content updates after the first 30 days",
        ]),
    },
    {
        "slug": "growth", "name": "Growth", "category": "website",
        "tagline": "More pages, better SEO, and a blog you can actually update",
        "price": 12999, "internal_cost": 4200, "pages_included": 12,
        "delivery_days": 21, "support_months": 3,
        "recurring_yearly": 5999, "recurring_label": "Hosting, domain, SSL and backups after year one",
        "best_for": "A business that already has customers and wants to be found by more.",
        "is_featured": 1, "sort_order": 1,
        "features": "\n".join([
            "Everything in Starter",
            "Up to 12 pages plus a blog or insights section",
            "Admin panel so you can publish without us",
            "Keyword research on ten terms, mapped to pages",
            "Schema markup for your business, services and FAQs",
            "Speed pass: images optimised, Core Web Vitals green on mobile",
            "Lead capture with source tracking, so you know what worked",
            "Two rounds of revisions",
            "90 days of support after go-live",
        ]),
        "excluded": "\n".join([
            "Paid advertising management or ad spend",
            "Ecommerce checkout",
            "Custom application logic",
            "Content writing for the blog",
        ]),
    },
    {
        "slug": "business", "name": "Business", "category": "website",
        "tagline": "Commerce, integrations and the automation behind them",
        "price": 29999, "internal_cost": 11000, "pages_included": 25,
        "delivery_days": 35, "support_months": 6,
        "recurring_yearly": 11999, "recurring_label": "Managed hosting, backups and monitoring",
        "best_for": "A business selling or booking online, or wiring the site into its tools.",
        "is_featured": 0, "sort_order": 2,
        "features": "\n".join([
            "Everything in Growth",
            "Up to 25 pages, or a catalogue of up to 100 products",
            "Payments through Razorpay or Stripe, with GST-ready invoices",
            "Bookings or enquiry routing into your CRM or spreadsheet",
            "Two automations - lead alerts, WhatsApp confirmations or a daily digest",
            "Staging site, so changes are seen before they go live",
            "Monthly performance and traffic report",
            "Six months of support after go-live",
        ]),
        "excluded": "\n".join([
            "Payment gateway fees and transaction charges",
            "Third-party subscription costs, billed at actuals",
            "Product photography and cataloguing",
            "Warehouse, ERP or accounting integration beyond one endpoint",
        ]),
    },
    {
        "slug": "saas", "name": "SaaS build", "category": "custom",
        "tagline": "A product, not a brochure: accounts, data, dashboards, billing",
        "price": 89999, "internal_cost": 34000, "pages_included": 0,
        "delivery_days": 60, "support_months": 6, "is_from_price": 1,
        "recurring_yearly": 23999, "recurring_label": "Managed infrastructure and monitoring",
        "best_for": "An idea that has customers waiting and needs to be built properly once.",
        "is_featured": 0, "sort_order": 3,
        "features": "\n".join([
            "Discovery: user journeys, data model and a scope we both sign",
            "Accounts, roles and permissions",
            "The core workflow your product exists to do",
            "Admin panel for your own team",
            "Reporting and exports",
            "Subscription billing where the model needs it",
            "Deployment, backups, monitoring and error alerts",
            "Handover documentation and a walkthrough recording",
            "Six months of support after launch",
        ]),
        "excluded": "\n".join([
            "Mobile apps on the App Store or Play Store",
            "Cloud infrastructure costs, billed at actuals",
            "Third-party API and licence fees",
            "Ongoing feature development, which is quoted separately",
        ]),
    },
    {
        "slug": "seo-retainer", "name": "SEO retainer", "category": "growth",
        "tagline": "Ranking is a habit, not a project",
        "price": 14999, "internal_cost": 5200, "pages_included": 0,
        "delivery_days": 30, "support_months": 1,
        "best_for": "A site that exists and now needs to be found.",
        "sort_order": 4,
        "features": "\n".join([
            "Monthly technical audit and fixes",
            "Keyword tracking on twenty terms",
            "Two optimised pages or articles a month",
            "Internal linking and content refresh",
            "Local SEO and Google Business Profile upkeep",
            "Backlink outreach, quality over quantity",
            "Monthly report with what moved and what is next",
        ]),
        "excluded": "\n".join([
            "Paid ads",
            "Guaranteed positions, which nobody can honestly promise",
            "Content in languages other than English",
        ]),
    },
    {
        "slug": "ai-automation", "name": "AI automation", "category": "ai",
        "tagline": "Take the repetitive part out of the week",
        "price": 24999, "internal_cost": 9000, "pages_included": 0,
        "delivery_days": 21, "support_months": 3, "is_from_price": 1,
        "best_for": "A team retyping the same things between tools.",
        "sort_order": 5,
        "features": "\n".join([
            "Process mapping of what is actually being done by hand",
            "Up to three automations built and monitored",
            "A support or sales assistant trained on your own documents",
            "WhatsApp, email or Slack notifications where they belong",
            "Dashboards for whatever you have been counting manually",
            "Runbook so your team can operate it without us",
            "90 days of tuning after go-live",
        ]),
        "excluded": "\n".join([
            "Model API usage costs, billed at actuals",
            "Data cleanup of legacy records",
            "Anything requiring a licence you do not hold",
        ]),
    },
]

# ── add-ons ─────────────────────────────────────────────────────────────────
ADDONS = [
    {"slug": "extra-page", "name": "Extra page", "category": "build", "unit": "page",
     "unit_price": 900, "internal_cost": 300, "is_quantity": 1, "max_qty": 40,
     "help": "Beyond what the package includes."},
    {"slug": "landing-page", "name": "Campaign landing page", "category": "build",
     "unit": "page", "unit_price": 3500, "internal_cost": 1100, "is_quantity": 1, "max_qty": 10,
     "help": "A single-purpose page built to convert one ad or campaign."},
    {"slug": "multilingual", "name": "Second language", "category": "build",
     "unit": "language", "unit_price": 6500, "internal_cost": 2400, "is_quantity": 1,
     "max_qty": 4, "help": "Full translation of the site, with hreflang set up correctly."},
    {"slug": "cms-training", "name": "Admin training session", "category": "build",
     "unit": "session", "unit_price": 2500, "internal_cost": 600,
     "help": "An hour on a call, recorded, so your team can publish without us."},

    {"slug": "ecommerce", "name": "Online store", "category": "commerce",
     "unit": "store", "unit_price": 18000, "internal_cost": 6800,
     "help": "Catalogue, cart, checkout and order emails."},
    {"slug": "payment-gateway", "name": "Payment gateway", "category": "commerce",
     "unit": "gateway", "unit_price": 6000, "internal_cost": 1800,
     "help": "Razorpay, Stripe or PayU wired in, tested end to end with a live rupee."},
    {"slug": "bookings", "name": "Bookings or appointments", "category": "commerce",
     "unit": "module", "unit_price": 12000, "internal_cost": 4200,
     "help": "Slots, confirmations and reminders."},
    {"slug": "membership", "name": "Logins and members area", "category": "commerce",
     "unit": "module", "unit_price": 16000, "internal_cost": 6000,
     "help": "Accounts, gated content and password resets."},

    {"slug": "logo", "name": "Logo and brand mark", "category": "brand",
     "unit": "identity", "unit_price": 8000, "internal_cost": 2800,
     "help": "Three directions, one taken to final files."},
    {"slug": "brand-kit", "name": "Brand kit", "category": "brand",
     "unit": "kit", "unit_price": 12000, "internal_cost": 4000,
     "help": "Colour, type, spacing and usage rules, as a document your team can follow."},
    {"slug": "copywriting", "name": "Copywriting", "category": "brand",
     "unit": "page", "unit_price": 1800, "internal_cost": 700, "is_quantity": 1, "max_qty": 25,
     "help": "We write the page rather than editing what you send."},
    {"slug": "photography", "name": "Photo shoot", "category": "brand",
     "unit": "half day", "unit_price": 9000, "internal_cost": 5000,
     "help": "Product or premises, edited and web-ready."},

    {"slug": "seo-setup", "name": "SEO foundation", "category": "growth",
     "unit": "site", "unit_price": 6500, "internal_cost": 2200,
     "help": "Keyword mapping, schema, sitemap and a technical pass."},
    {"slug": "blog-article", "name": "Blog article", "category": "growth",
     "unit": "article", "unit_price": 2500, "internal_cost": 900, "is_quantity": 1,
     "max_qty": 20, "help": "Researched, 900 to 1,200 words, optimised for one keyword."},
    {"slug": "gmb", "name": "Google Business Profile", "category": "growth",
     "unit": "profile", "unit_price": 3000, "internal_cost": 900,
     "help": "Claimed, filled in properly, categories and photos, review link ready."},
    {"slug": "analytics-dash", "name": "Analytics dashboard", "category": "growth",
     "unit": "dashboard", "unit_price": 5500, "internal_cost": 1800,
     "help": "The numbers you care about on one screen, instead of four tools."},

    {"slug": "chatbot", "name": "Support assistant", "category": "ai",
     "unit": "assistant", "unit_price": 15000, "internal_cost": 5500,
     "help": "Answers from your own documents, with a handover to a human."},
    {"slug": "automation-flow", "name": "Automation", "category": "ai",
     "unit": "flow", "unit_price": 7000, "internal_cost": 2400, "is_quantity": 1, "max_qty": 10,
     "help": "One workflow between two tools, monitored and alerting on failure."},
    {"slug": "whatsapp-api", "name": "WhatsApp Business API", "category": "ai",
     "unit": "setup", "unit_price": 9000, "internal_cost": 3200,
     "help": "Verified number, approved templates and delivery reporting."},
    {"slug": "crm-integration", "name": "CRM integration", "category": "ai",
     "unit": "integration", "unit_price": 8500, "internal_cost": 3000,
     "help": "Leads into the system you already use, without retyping."},

    {"slug": "domain", "name": "Domain", "category": "infra", "unit": "year",
     "unit_price": 1200, "internal_cost": 800, "is_recurring": 1, "recurring_period": "yearly",
     "help": "Registered in your name, not ours."},
    {"slug": "hosting", "name": "Hosting and SSL", "category": "infra", "unit": "year",
     "unit_price": 3499, "internal_cost": 1400, "is_recurring": 1, "recurring_period": "yearly",
     "help": "Managed, with SSL and daily backups."},
    {"slug": "email-hosting", "name": "Business email", "category": "infra",
     "unit": "mailbox/year", "unit_price": 1800, "internal_cost": 1300, "is_recurring": 1,
     "recurring_period": "yearly", "is_quantity": 1, "max_qty": 25,
     "help": "you@yourbrand.com, on Google or Zoho."},
    {"slug": "cdn", "name": "CDN and WAF", "category": "infra", "unit": "year",
     "unit_price": 4800, "internal_cost": 2400, "is_recurring": 1, "recurring_period": "yearly",
     "help": "Faster abroad, and a firewall in front of the site."},

    {"slug": "care-basic", "name": "Care plan, essential", "category": "care",
     "unit": "year", "unit_price": 7999, "internal_cost": 2600, "is_recurring": 1,
     "recurring_period": "yearly",
     "help": "Updates, backups, uptime monitoring and two hours of changes a month."},
    {"slug": "care-plus", "name": "Care plan, priority", "category": "care",
     "unit": "year", "unit_price": 17999, "internal_cost": 6200, "is_recurring": 1,
     "recurring_period": "yearly",
     "help": "Everything in essential, a four-hour response promise and six hours a month."},
    {"slug": "support-hours", "name": "Prepaid support hours", "category": "care",
     "unit": "hour", "unit_price": 1200, "internal_cost": 400, "is_quantity": 1, "max_qty": 100,
     "help": "Used against anything out of scope. Unused hours roll over one quarter."},
    {"slug": "amc", "name": "Annual maintenance contract", "category": "care",
     "unit": "year", "unit_price": 24999, "internal_cost": 9000, "is_recurring": 1,
     "recurring_period": "yearly",
     "help": "For applications rather than sites: environment, releases and on-call."},
]

# ── pricing rules ───────────────────────────────────────────────────────────
RULES = [
    {"code": "rush", "label": "Rush delivery", "kind": "surcharge_pct", "value": 25,
     "applies_to": "build",
     "help": "Applied when the client wants it faster than the standard timeline. It is not "
             "a penalty; it is the cost of pushing other work aside."},
    {"code": "complexity", "label": "Complexity multiplier", "kind": "multiplier", "value": 1,
     "applies_to": "build",
     "help": "Set per quote. 1.0 is a normal build, 1.5 is an unusual one. Use it instead of "
             "quietly padding the line items."},
    {"code": "extra_page", "label": "Extra page beyond the package", "kind": "per_unit",
     "value": 900, "applies_to": "pages",
     "help": "Charged per page over the package's included count."},
    {"code": "annual_prepay", "label": "Annual prepayment discount", "kind": "discount_pct",
     "value": 10, "applies_to": "recurring",
     "help": "For paying a year of hosting or care up front."},
    {"code": "referral", "label": "Referral discount", "kind": "discount_pct", "value": 5,
     "applies_to": "build",
     "help": "For a client who came through an existing client's referral code."},
]

# ── lead sources ────────────────────────────────────────────────────────────
SOURCES = [
    {"slug": "referral", "name": "Referral", "sort_order": 0},
    {"slug": "word-of-mouth", "name": "Word of mouth", "sort_order": 1},
    {"slug": "google", "name": "Google search", "sort_order": 2},
    {"slug": "instagram", "name": "Instagram", "sort_order": 3},
    {"slug": "linkedin", "name": "LinkedIn", "sort_order": 4},
    {"slug": "whatsapp", "name": "WhatsApp forward", "sort_order": 5},
    {"slug": "google-ads", "name": "Google Ads", "is_paid": 1, "cost_monthly": 0,
     "sort_order": 6},
    {"slug": "meta-ads", "name": "Meta Ads", "is_paid": 1, "cost_monthly": 0, "sort_order": 7},
    {"slug": "directory", "name": "Directory listing", "sort_order": 8},
    {"slug": "repeat", "name": "Existing client", "sort_order": 9},
    {"slug": "cold-outreach", "name": "Our outreach", "sort_order": 10},
    {"slug": "walk-in", "name": "Walk-in or event", "sort_order": 11},
]

# ── expense categories ──────────────────────────────────────────────────────
EXPENSE_CATEGORIES = [
    {"slug": "hosting", "name": "Hosting and domains", "kind": "cogs", "sort_order": 0},
    {"slug": "software", "name": "Software and subscriptions", "kind": "tool", "sort_order": 1},
    {"slug": "contractor", "name": "Contractors and freelancers", "kind": "cogs",
     "sort_order": 2},
    {"slug": "licence", "name": "Licences and stock assets", "kind": "cogs", "sort_order": 3},
    {"slug": "advertising", "name": "Advertising", "kind": "marketing", "sort_order": 4},
    {"slug": "referral", "name": "Referral payouts", "kind": "marketing", "sort_order": 5},
    {"slug": "equipment", "name": "Equipment", "kind": "capex", "sort_order": 6},
    {"slug": "internet", "name": "Internet and phone", "kind": "operating", "sort_order": 7},
    {"slug": "rent", "name": "Rent and utilities", "kind": "operating", "sort_order": 8},
    {"slug": "professional", "name": "Accounting and legal", "kind": "operating",
     "sort_order": 9},
    {"slug": "tax", "name": "Tax and statutory", "kind": "tax", "sort_order": 10},
    {"slug": "travel", "name": "Travel", "kind": "operating", "sort_order": 11},
    {"slug": "other", "name": "Everything else", "kind": "operating", "sort_order": 12},
]

# ── SLA policies ────────────────────────────────────────────────────────────
SLA = [
    {"priority": "p1", "label": "P1 - down", "response_hours": 4, "resolve_hours": 12,
     "sort_order": 0,
     "description": "The site or application is unreachable, or money cannot be taken. "
                    "Nothing else matters until this is fixed."},
    {"priority": "p2", "label": "P2 - broken", "response_hours": 12, "resolve_hours": 48,
     "sort_order": 1,
     "description": "Something important does not work - a form, a page, a login - but the "
                    "business can still operate around it."},
    {"priority": "p3", "label": "P3 - normal", "response_hours": 24, "resolve_hours": 120,
     "sort_order": 2,
     "description": "A change, a question or a cosmetic fault. This is where most requests "
                    "belong, and saying so is what protects the P1 promise."},
    {"priority": "p4", "label": "P4 - whenever", "response_hours": 72, "resolve_hours": 240,
     "sort_order": 3,
     "description": "A nice-to-have, batched with other work."},
]


# ── the insert machinery ────────────────────────────────────────────────────
def _fill(table: str, rows: list[dict], key: str | tuple[str, ...]) -> int:
    """Insert each row unless one matching on the key columns is already there.

    Columns the table does not have are dropped rather than raising, so a seed list
    written against a later schema still loads what it can on an older database.
    """
    keys = (key,) if isinstance(key, str) else key
    where = " AND ".join(f"{k} = ?" for k in keys)
    columns = set(db.table_columns(table))
    added = 0
    for row in rows:
        if db.one(f"SELECT 1 FROM {table} WHERE {where}",
                  tuple(row.get(k) for k in keys)):
            continue
        db.insert(table, {k: v for k, v in row.items() if k in columns})
        added += 1
    return added


def _fill_clauses() -> int:
    """Clauses are keyed on code and version, so an unseen code lands at version 1.

    An existing code is left entirely alone even if this file's wording has since
    changed - the owner may have edited it, and silently replacing a clause that a
    signed proposal points at is the one thing this must never do.
    """
    from db import seed_clauses

    added = 0
    for clause in seed_clauses.CLAUSES:
        if db.one("SELECT 1 FROM clause_library WHERE code = ?", (clause["code"],)):
            continue
        db.insert("clause_library", clause | {"version": 1})
        added += 1
    return added


def _fill_posts() -> int:
    """Insights are seeded published and dated, spaced a week apart going backwards.

    An unpublished draft nobody notices is worse than a starter article the owner
    rewrites, and a blank insights page on a live site looks abandoned.
    """
    from datetime import date, timedelta

    from db import seed_content

    added = 0
    today = date.today()
    for index, post in enumerate(seed_content.POSTS):
        if db.one("SELECT 1 FROM posts WHERE slug = ?", (post["slug"],)):
            continue
        published = (today - timedelta(days=7 * index)).isoformat() + " 09:00:00"
        db.insert("posts", post | {"is_published": 1, "published_at": published,
                                   "sort_order": index})
        added += 1
    return added


def _fill_templates() -> int:
    from db import seed_content

    rows = [t | {"channel": "whatsapp"} for t in seed_content.WHATSAPP_TEMPLATES]
    rows += [t | {"channel": "email"} for t in seed_content.EMAIL_TEMPLATES]
    return _fill("message_templates", rows, "code")


def run(force: bool = False, quiet: bool = False) -> dict:
    """Load everything, and report what was actually added.

    Safe to run repeatedly: only rows whose key is missing are inserted. `force`
    additionally resets settings to their defaults, which is the one thing a
    re-seed will overwrite - and it is the only reason to pass it.
    """
    from db import seed_clauses, seed_content

    if force:
        settings.reset_defaults()

    counts = {
        "packages": _fill("packages", PACKAGES, "slug"),
        "add-ons": _fill("addons", ADDONS, "slug"),
        "pricing rules": _fill("pricing_rules", RULES, "code"),
        "lead sources": _fill("lead_sources", SOURCES, "slug"),
        "expense categories": _fill("expense_categories", EXPENSE_CATEGORIES, "slug"),
        "SLA policies": _fill("sla_policies", SLA, "priority"),
        "clauses": _fill_clauses(),
        "legal pages": _fill("legal_pages", seed_clauses.LEGAL_PAGES, "slug"),
        "pages": _fill("pages", seed_content.PAGES, "slug"),
        "services": _fill("services", seed_content.SERVICES, "slug"),
        "case studies": _fill("case_studies", seed_content.CASE_STUDIES, "slug"),
        "testimonials": _fill("testimonials", seed_content.TESTIMONIALS, "author"),
        "FAQs": _fill("faqs", seed_content.FAQS, "question"),
        "insights": _fill_posts(),
        "stats": _fill("stats", seed_content.STATS, "label"),
        "tech items": _fill("tech_items", seed_content.TECH, "label"),
        "nav items": _fill("nav_items", seed_content.NAV, ("location", "label")),
        "message templates": _fill_templates(),
    }

    if not quiet:
        added = {name: n for name, n in counts.items() if n}
        if added:
            for name, n in added.items():
                print(f"  + {n} {name}")
        else:
            print("  nothing to add - everything is already seeded")
        if force:
            print("  ! settings reset to defaults")
    return counts
