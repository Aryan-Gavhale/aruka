"""Website content: pages, services, case studies, testimonials, FAQs, insights,
legal pages, navigation, stats and the tech marquee.

Every one of these is a `Resource`, so the list, form, save, delete, publish
toggle and drag-reorder all come from core/crud.py. What is unique to a type is
its field list, which is the only thing declared here.
"""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

from blueprints.admin import bp
from core import audit, crud, db
from core.auth import require_role, verify_csrf
from core.crud import Field, Resource
from core.util import dump_json, load_json, parse_int

BLOCK_KINDS = {
    "richtext": "Rich text",
    "cta": "Call to action",
    "stats": "Stat row",
    "steps": "Numbered steps",
    "logos": "Logo marquee",
    "faq": "FAQ block",
    "quote": "Pull quote",
}

SERVICE_ICONS = [
    ("spark", "Spark"), ("layout", "Layout"), ("rocket", "Rocket"), ("globe", "Globe"),
    ("chart", "Chart"), ("chat", "Chat"), ("shield", "Shield"), ("calc", "Calculator"),
    ("board", "Board"), ("trend", "Trend"), ("life", "Support"), ("key", "Key"),
]

SEO_FIELDS = [
    Field("seo_head", "Search and social", "heading",
          help="Left blank, the page falls back to the title and the site description."),
    Field("meta_title", "Meta title", "text", span=6,
          help="Under 60 characters reads fully in Google."),
    Field("seo_keyword", "Target keyword", "text", span=6,
          help="Used by the SEO checklist to score the page."),
    Field("meta_description", "Meta description", "textarea", rows=2, span=12,
          help="Around 155 characters."),
]


PAGES = Resource(
    key="pages", table="pages", label="Page", label_plural="Pages",
    area="content", row_label="title", slug_from="title", publishable=True,
    sortable=True, searchable=("title", "slug"), icon="layout", deletable=True,
    intro="These rows hold the copy and search metadata for each fixed page. "
          "Layout and animation live in the templates.",
    list_columns=[("title", "Page"), ("nav_label", "Nav label"), ("heading", "Heading")],
    fields=[
        Field("title", "Page title", "text", required=True, span=6),
        Field("slug", "URL slug", "slug", span=6, help="Leave blank to generate it from the title."),
        Field("nav_label", "Navigation label", "text", span=4),
        Field("kicker", "Kicker", "text", span=8, help="The small line above the heading."),
        Field("heading", "Heading", "text", span=12),
        Field("intro", "Intro paragraph", "textarea", rows=3, span=12),
        *SEO_FIELDS,
        Field("og_media_id", "Social share image", "media", span=6),
        Field("is_published", "Published", "bool", span=6),
    ],
)

SERVICES = Resource(
    key="services", table="services", label="Service", label_plural="Services",
    area="content", row_label="name", slug_from="name", publishable=True,
    sortable=True, searchable=("name", "tagline", "summary"), icon="spark",
    intro="What you sell. Each row gets its own page, appears in the services grid, "
          "and can be attached to a case study.",
    list_columns=[("name", "Service"), ("tagline", "Tagline"), ("price_from", "From"),
                  ("is_featured", "Home")],
    fields=[
        Field("name", "Name", "text", required=True, span=6),
        Field("slug", "URL slug", "slug", span=6),
        Field("tagline", "Tagline", "text", span=8, help="One line, shown on the card."),
        Field("icon", "Icon", "select", options=SERVICE_ICONS, span=4),
        Field("summary", "Summary", "textarea", rows=3, span=12,
              help="Two or three sentences for the grid and the page intro."),
        Field("body", "Full description", "textarea", rows=8, span=12,
              help="Blank lines separate paragraphs."),
        Field("what_head", "Commercials", "heading"),
        Field("price_from", "Starting price", "money", span=4),
        Field("timeline", "Typical timeline", "text", span=4, help="For example: 2 to 3 weeks."),
        Field("ideal_for", "Ideal for", "text", span=4),
        Field("features", "What is included", "textarea", rows=6, span=6,
              help="One per line."),
        Field("deliverables", "What you get handed", "textarea", rows=6, span=6,
              help="One per line."),
        *SEO_FIELDS,
        Field("media_id", "Image", "media", span=6),
        Field("flags_head", "Visibility", "heading"),
        Field("is_featured", "Show on the home page", "bool", span=6),
        Field("is_published", "Published", "bool", span=6),
    ],
)

WORK = Resource(
    key="work", table="case_studies", label="Case study", label_plural="Case studies",
    area="content", row_label="title", slug_from="title", publishable=True,
    sortable=True, searchable=("title", "client_name", "summary"), icon="star",
    intro="Proof. A case study with a number in the outcome does more selling than any "
          "amount of copy.",
    list_columns=[("title", "Case study"), ("client_name", "Client"),
                  ("service_line", "Service"), ("is_featured", "Home")],
    fields=[
        Field("title", "Title", "text", required=True, span=8),
        Field("slug", "URL slug", "slug", span=4),
        Field("client_name", "Client name", "text", span=4),
        Field("sector", "Sector", "text", span=4),
        Field("service_line", "Service line", "text", span=4,
              help="Free text so it can name what you actually did."),
        Field("summary", "Summary", "textarea", rows=3, span=12),
        Field("story_head", "The story", "heading",
              help="Challenge, approach, outcome. Keep the outcome measurable."),
        Field("challenge", "Challenge", "textarea", rows=4, span=4),
        Field("approach", "Approach", "textarea", rows=4, span=4),
        Field("outcome", "Outcome", "textarea", rows=4, span=4),
        Field("metrics", "Headline metrics", "lines", rows=4, span=6,
              line_keys=("label", "value"),
              help="One per line: label | value. For example: Enquiries a month | 42"),
        Field("stack", "Built with", "csv", span=6, help="Comma separated."),
        Field("live_url", "Live URL", "url", span=6),
        Field("delivered_on", "Delivered", "date", span=6),
        *SEO_FIELDS,
        Field("media_id", "Main image", "media", span=6),
        Field("logo_media_id", "Client logo", "media", span=6),
        Field("flags_head", "Visibility", "heading"),
        Field("is_featured", "Show on the home page", "bool", span=6),
        Field("is_published", "Published", "bool", span=6),
    ],
)

TESTIMONIALS = Resource(
    key="testimonials", table="testimonials", label="Testimonial",
    label_plural="Testimonials", area="content", row_label="author",
    publishable=True, sortable=True, searchable=("author", "company", "quote"),
    icon="quote",
    intro="Short quotes outperform long ones. Two sentences with a name and a company "
          "is the format that gets read.",
    list_columns=[("author", "Who"), ("company", "Company"), ("rating", "Rating")],
    fields=[
        Field("author", "Name", "text", required=True, span=5),
        Field("role", "Role", "text", span=4),
        Field("company", "Company", "text", span=3),
        Field("quote", "Quote", "textarea", rows=4, span=12, required=True),
        Field("rating", "Rating out of 5", "int", span=3, default=5),
        Field("source", "Source", "select", span=4,
              options=[("direct", "Given to us directly"), ("google", "Google review"),
                       ("email", "From an email"), ("whatsapp", "From WhatsApp")]),
        Field("media_id", "Photo", "media", span=5),
        Field("is_published", "Published", "bool", span=12),
    ],
)

FAQS = Resource(
    key="faqs", table="faqs", label="FAQ", label_plural="FAQs",
    area="content", row_label="question", publishable=True, sortable=True,
    searchable=("question", "answer"), icon="help",
    intro="These become FAQPage structured data, so a good answer here can win a "
          "rich result as well as answer the question.",
    list_columns=[("question", "Question"), ("category", "Category")],
    fields=[
        Field("question", "Question", "text", required=True, span=9),
        Field("category", "Category", "select", span=3,
              options=[("general", "General"), ("pricing", "Pricing"), ("process", "Process"),
                       ("support", "Support"), ("seo", "SEO"), ("technical", "Technical")]),
        Field("answer", "Answer", "textarea", rows=5, span=12, required=True),
        Field("is_published", "Published", "bool", span=12),
    ],
)

POSTS = Resource(
    key="posts", table="posts", label="Insight", label_plural="Insights",
    area="content", row_label="title", slug_from="title", publishable=True,
    searchable=("title", "excerpt", "body"), icon="note", order_by="published_at DESC, id DESC",
    intro="Your own SEO shop window. Publishing one useful article a month beats "
          "publishing ten thin ones.",
    list_columns=[("title", "Post"), ("published_at", "Published"), ("tags", "Tags")],
    fields=[
        Field("title", "Title", "text", required=True, span=8),
        Field("slug", "URL slug", "slug", span=4),
        Field("excerpt", "Excerpt", "textarea", rows=2, span=12,
              help="Shown on the index and used as the meta description if that is blank."),
        Field("body", "Body", "textarea", rows=16, span=12,
              help="Blank lines separate paragraphs. A line starting with ## becomes a subheading."),
        Field("meta_head", "Publishing", "heading"),
        Field("author", "Author", "text", span=4),
        Field("published_at", "Publish date", "date", span=4),
        Field("tags", "Tags", "csv", span=4),
        *SEO_FIELDS,
        Field("media_id", "Cover image", "media", span=6),
        Field("is_published", "Published", "bool", span=6),
    ],
)

LEGAL = Resource(
    key="legal", table="legal_pages", label="Legal page", label_plural="Legal pages",
    area="content", row_label="title", publishable=True, sortable=True,
    searchable=("title", "body"), icon="shield", deletable=False,
    intro="Privacy, terms, refunds and the SLA. These are also what a payment gateway "
          "asks to see before it approves an account.",
    list_columns=[("title", "Page"), ("slug", "URL")],
    fields=[
        Field("title", "Title", "text", required=True, span=8),
        Field("slug", "URL slug", "text", span=4,
              help="Fixed: the footer and the gateway checklist link to these."),
        Field("intro", "Intro", "textarea", rows=2, span=12),
        Field("body", "Body", "textarea", rows=22, span=12,
              help="A line starting with ## becomes a heading. Blank lines separate paragraphs."),
        Field("is_published", "Published", "bool", span=12),
    ],
)

NAV = Resource(
    key="nav", table="nav_items", label="Menu item", label_plural="Navigation",
    area="content", row_label="label", activatable=True, sortable=True,
    icon="list",
    intro="The header and footer menus. Reorder by dragging.",
    list_columns=[("label", "Label"), ("url", "Links to"), ("location", "Where")],
    fields=[
        Field("label", "Label", "text", required=True, span=5),
        Field("url", "URL", "text", required=True, span=4, placeholder="/services"),
        Field("location", "Where", "select", span=3,
              options=[("header", "Header"), ("footer", "Footer"), ("footer_legal", "Footer, legal row")]),
        Field("is_button", "Style as a button", "bool", span=6),
        Field("is_active", "Show it", "bool", span=6),
    ],
)

STATS = Resource(
    key="stats", table="stats", label="Stat", label_plural="Stats and marquee",
    area="content", row_label="label", activatable=True, sortable=True, icon="trend",
    intro="The counters that animate on the home page. Keep them true - a number you "
          "cannot back up costs more than it wins.",
    list_columns=[("label", "Label"), ("value", "Value"), ("suffix", "Suffix")],
    fields=[
        Field("label", "Label", "text", required=True, span=6),
        Field("value", "Value", "number", span=2, step="0.1"),
        Field("prefix", "Prefix", "text", span=2, placeholder="\u20b9"),
        Field("suffix", "Suffix", "text", span=2, placeholder="+"),
        Field("is_active", "Show it", "bool", span=12),
    ],
)

TECH = Resource(
    key="tech", table="tech_items", label="Marquee item", label_plural="Marquee items",
    area="content", row_label="label", activatable=True, sortable=True, icon="refresh",
    intro="The scrolling strip of tools and platforms you work with.",
    list_columns=[("label", "Label"), ("category", "Group")],
    fields=[
        Field("label", "Label", "text", required=True, span=8),
        Field("category", "Group", "text", span=4),
        Field("is_active", "Show it", "bool", span=12),
    ],
)

for resource in (PAGES, SERVICES, WORK, TESTIMONIALS, FAQS, POSTS, LEGAL, NAV, STATS, TECH):
    crud.register(bp, resource)


# ── page blocks ─────────────────────────────────────────────────────────────
@bp.route("/pages/<int:page_id>/blocks")
@require_role("content")
def page_blocks(page_id):
    page = db.one("SELECT * FROM pages WHERE id = ?", (page_id,))
    if not page:
        abort(404)
    blocks = db.query(
        "SELECT * FROM page_blocks WHERE page_id = ? ORDER BY sort_order, id", (page_id,))
    return render_template("admin/page_blocks.html", title=f"{page['title']} blocks",
                           page=page, blocks=blocks, kinds=BLOCK_KINDS,
                           nav_active="admin.pages_list")


@bp.route("/pages/<int:page_id>/blocks/add", methods=["POST"])
@require_role("content")
def page_block_add(page_id):
    verify_csrf()
    kind = request.form.get("kind")
    if kind not in BLOCK_KINDS:
        flash("Pick a block type.", "error")
        return redirect(url_for("admin.page_blocks", page_id=page_id))
    block_id = db.insert("page_blocks", {
        "page_id": page_id, "kind": kind, "name": BLOCK_KINDS[kind],
        "data": dump_json(_block_defaults(kind)),
        "sort_order": db.next_sort_order("page_blocks", "page_id = ?", (page_id,)),
    })
    audit.log("create", "page_blocks", block_id, kind)
    return redirect(url_for("admin.page_block_edit", block_id=block_id))


def _block_defaults(kind: str) -> dict:
    if kind == "cta":
        return {"heading": "Ready when you are", "body": "", "button_label": "Start a project",
                "button_url": "/contact"}
    if kind == "steps":
        return {"heading": "How it goes", "items": "Discover | We agree the scope in writing"}
    if kind == "quote":
        return {"quote": "", "author": ""}
    if kind == "stats":
        return {"heading": "", "items": "12 | projects delivered"}
    if kind == "faq":
        return {"heading": "Questions", "category": "general"}
    if kind == "logos":
        return {"heading": "Trusted by"}
    return {"heading": "", "body": ""}


BLOCK_FIELDS = {
    "richtext": [("heading", "Heading", "text"), ("body", "Body", "textarea")],
    "cta": [("heading", "Heading", "text"), ("body", "Body", "textarea"),
            ("button_label", "Button label", "text"), ("button_url", "Button URL", "text")],
    "stats": [("heading", "Heading", "text"),
              ("items", "Items, one per line: value | label", "textarea")],
    "steps": [("heading", "Heading", "text"),
              ("items", "Steps, one per line: title | description", "textarea")],
    "logos": [("heading", "Heading", "text")],
    "faq": [("heading", "Heading", "text"), ("category", "FAQ category to pull", "text")],
    "quote": [("quote", "Quote", "textarea"), ("author", "Attributed to", "text")],
}


@bp.route("/blocks/<int:block_id>", methods=["GET", "POST"])
@require_role("content")
def page_block_edit(block_id):
    block = db.one("SELECT * FROM page_blocks WHERE id = ?", (block_id,))
    if not block:
        abort(404)
    page = db.one("SELECT * FROM pages WHERE id = ?", (block["page_id"],))

    if request.method == "POST":
        verify_csrf()
        data = {}
        for name, _label, _kind in BLOCK_FIELDS.get(block["kind"], []):
            data[name] = (request.form.get(name) or "").strip()
        db.update("page_blocks", block_id, {
            "data": dump_json(data),
            "name": (request.form.get("name") or BLOCK_KINDS.get(block["kind"], "Block")).strip(),
            "is_published": 1 if request.form.get("is_published") else 0,
            "updated_at": db.scalar("SELECT datetime('now')"),
        })
        audit.log("update", "page_blocks", block_id, block["kind"])
        flash("Block saved.", "ok")
        return redirect(url_for("admin.page_blocks", page_id=block["page_id"]))

    return render_template("admin/page_block_form.html", title=f"{BLOCK_KINDS.get(block['kind'])} block",
                           block=block, page=page, data=load_json(block["data"], {}),
                           spec=BLOCK_FIELDS.get(block["kind"], []),
                           nav_active="admin.pages_list")


@bp.route("/blocks/<int:block_id>/delete", methods=["POST"])
@require_role("content")
def page_block_delete(block_id):
    verify_csrf()
    block = db.one("SELECT * FROM page_blocks WHERE id = ?", (block_id,))
    if not block:
        abort(404)
    db.delete("page_blocks", block_id)
    audit.log("delete", "page_blocks", block_id, block["kind"], before=block)
    flash("Block removed.", "ok")
    return redirect(url_for("admin.page_blocks", page_id=block["page_id"]))


@bp.route("/blocks/<int:block_id>/move", methods=["POST"])
@require_role("content")
def page_block_move(block_id):
    verify_csrf()
    block = db.one("SELECT * FROM page_blocks WHERE id = ?", (block_id,))
    if not block:
        abort(404)
    step = -1 if request.form.get("direction") == "up" else 1
    siblings = db.query(
        "SELECT id, sort_order FROM page_blocks WHERE page_id = ? ORDER BY sort_order, id",
        (block["page_id"],))
    ids = [r["id"] for r in siblings]
    at = ids.index(block_id)
    target = at + step
    if 0 <= target < len(ids):
        ids[at], ids[target] = ids[target], ids[at]
        with db.transaction():
            for index, row_id in enumerate(ids):
                db.update("page_blocks", row_id, {"sort_order": index})
    return redirect(url_for("admin.page_blocks", page_id=block["page_id"]))


# ── SEO checklist ───────────────────────────────────────────────────────────
@bp.route("/seo")
@require_role("content")
def seo():
    """Score every public page against the basics you sell to clients.

    Deliberately mechanical: it checks what can be checked without guessing, and
    says nothing about the things it cannot see.
    """
    rows = []

    def score(kind: str, label: str, url: str, title: str, description: str,
              keyword: str = "", body: str = "", has_image: bool = False,
              edit_url: str = ""):
        checks = [
            ("Meta title set", bool(title)),
            ("Title length 25-60", 25 <= len(title or "") <= 60),
            ("Meta description set", bool(description)),
            ("Description length 80-165", 80 <= len(description or "") <= 165),
            ("Social share image", has_image),
            ("Target keyword recorded", bool(keyword)),
            ("Keyword appears in the title", bool(keyword) and keyword.lower() in (title or "").lower()),
            ("At least 300 words of copy", len((body or "").split()) >= 300),
        ]
        passed = sum(1 for _l, ok in checks if ok)
        rows.append({
            "kind": kind, "label": label, "url": url, "edit_url": edit_url,
            "checks": checks, "passed": passed, "total": len(checks),
            "pct": round(passed * 100 / len(checks)),
        })

    default_description = ""
    from core import settings as st
    default_description = st.get("seo.default_description") or ""
    og_default = bool(st.get("seo.og_media_id"))

    for page in db.query("SELECT * FROM pages WHERE is_published = 1 ORDER BY sort_order, id"):
        score("Page", page["title"], f"/{page['slug']}" if page["slug"] != "home" else "/",
              page["meta_title"] or page["title"],
              page["meta_description"] or default_description,
              page["seo_keyword"], page["intro"] or "",
              bool(page["og_media_id"]) or og_default,
              url_for("admin.pages_edit", row_id=page["id"]))

    for row in db.query("SELECT * FROM services WHERE is_published = 1 ORDER BY sort_order"):
        score("Service", row["name"], f"/services/{row['slug']}",
              row["meta_title"] or row["name"],
              row["meta_description"] or row["summary"] or default_description,
              row["seo_keyword"] if "seo_keyword" in row.keys() else "",
              (row["body"] or "") + " " + (row["summary"] or ""),
              bool(row["media_id"]) or og_default,
              url_for("admin.services_edit", row_id=row["id"]))

    for row in db.query("SELECT * FROM case_studies WHERE is_published = 1 ORDER BY sort_order"):
        body = " ".join(filter(None, [row["summary"], row["challenge"], row["approach"], row["outcome"]]))
        score("Case study", row["title"], f"/work/{row['slug']}",
              row["meta_title"] or row["title"],
              row["meta_description"] or row["summary"] or default_description,
              "", body, bool(row["media_id"]) or og_default,
              url_for("admin.work_edit", row_id=row["id"]))

    for row in db.query("SELECT * FROM posts WHERE is_published = 1 ORDER BY id DESC"):
        score("Insight", row["title"], f"/insights/{row['slug']}",
              row["meta_title"] or row["title"],
              row["meta_description"] or row["excerpt"] or default_description,
              row["seo_keyword"], row["body"] or "",
              bool(row["media_id"]) or og_default,
              url_for("admin.posts_edit", row_id=row["id"]))

    overall = round(sum(r["pct"] for r in rows) / len(rows)) if rows else 0
    weakest = sorted(rows, key=lambda r: r["pct"])[:6]
    return render_template("admin/seo.html", title="SEO checklist", rows=rows,
                           overall=overall, weakest=weakest,
                           indexable=st.get("seo.indexable"))
