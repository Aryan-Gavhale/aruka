"""Route and write smoke test, stdlib only. Needs the dev server running.

Signs in, GETs every public, portal and admin page, then drives the whole business
end to end - an enquiry becomes a lead, the lead is priced, the quote becomes a
proposal PDF, the proposal is shared and accepted, that creates a client and a
project, the project is invoiced, the invoice is part-paid and receipted, a ticket
is raised and breached and replied to, a credential is vaulted and read back, an
expense is logged, analytics and the exports are read, the client signs into the
portal and a backup is taken - and checks that CSRF is actually enforced.

It removes its own rows on the way out. Every row it makes carries the word Smoke
somewhere, which is what the purge matches on.

    python app.py                    (in another terminal)
    python check_routes.py
    python check_routes.py --keep    leave the test data behind to look at
"""

from __future__ import annotations

import base64
import json
import re
import sqlite3
import sys
import time
import zlib
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = "http://127.0.0.1:8140"
ROOT = Path(__file__).resolve().parent
DB = ROOT / "db" / "aruka.db"
MARK = "Smoke"

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
problems = 0


# ── plumbing ────────────────────────────────────────────────────────────────
def credentials() -> tuple[str, str]:
    """The generated first-login pair, or the config's own, or the documented default."""
    stamp = ROOT / "db" / "first-login.txt"
    if stamp.exists():
        lines = [line.strip() for line in stamp.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]
    config = ROOT / "config.json"
    if config.exists():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
            if data.get("owner_password"):
                return data.get("owner_email", "owner@aruka.local"), data["owner_password"]
        except ValueError:
            pass
    return "owner@aruka.local", "aruka-owner-2026"


def get(path: str):
    try:
        with opener.open(BASE + path, timeout=60) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def post(path: str, data: dict):
    """Follows redirects, so the body returned is the page the owner would land on."""
    pairs = []
    for key, value in data.items():
        if isinstance(value, (list, tuple)):
            pairs += [(key, str(v)) for v in value]
        else:
            pairs.append((key, str(value)))
    body = urllib.parse.urlencode(pairs).encode()
    try:
        with opener.open(BASE + path, data=body, timeout=90) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.url
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), exc.url
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc), ""


def post_json(path: str, payload: dict, csrf: str):
    request = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf})
    try:
        with opener.open(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode() or "{}")
        except ValueError:
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}


def raw(path: str):
    """Status, headers and byte length - for PDFs, CSVs and zips."""
    status, headers, payload = raw_bytes(path)
    return status, headers, len(payload)


def raw_bytes(path: str):
    try:
        with opener.open(BASE + path, timeout=120) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}, b""


def pdf_text(payload: bytes) -> str:
    """The words on the page, out of a ReportLab PDF, with nothing but the stdlib.

    Content streams arrive ASCII85-then-Flate encoded. Undo both, then collect the
    string literals the text operators draw. Checking a PDF says the right thing is
    worth this much work - a byte count only proves something was generated.
    """
    words: list[str] = []
    for chunk in re.findall(rb"stream\r?\n(.*?)endstream", payload, re.S):
        body = chunk
        for decode in (lambda b: base64.a85decode(b.strip().rstrip(b"~>"), adobe=False),
                       lambda b: b):
            try:
                raw_stream = decode(body)
            except Exception:  # noqa: BLE001
                continue
            for attempt in (zlib.decompress, lambda b: b):
                try:
                    text = attempt(raw_stream)
                except Exception:  # noqa: BLE001
                    continue
                if b"Tj" in text or b"TJ" in text:
                    words += [m.decode("latin-1") for m in
                              re.findall(rb"\((?:[^()\\]|\\.)*\)", text)]
                    break
            else:
                continue
            break
    # ReportLab kerns by splitting a line into several literals, so join and let the
    # caller match on words rather than on exact spacing.
    return re.sub(r"\s+", " ", " ".join(w[1:-1].replace("\\(", "(").replace("\\)", ")")
                                       for w in words))


def pdf_says(path: str, *wanted: str) -> tuple[bool, str]:
    status, headers, payload = raw_bytes(path)
    if status != 200:
        return False, f"{status} {re.sub(r'[^ -~]', '', payload[:200].decode('latin-1'))}"
    if (headers.get("Content-Type") or "") != "application/pdf":
        return False, f"content-type {headers.get('Content-Type')}"
    if not payload.startswith(b"%PDF"):
        return False, "the body is not a PDF"
    page = pdf_text(payload)
    squashed = page.replace(" ", "")
    missing = [w for w in wanted if w not in page and w.replace(" ", "") not in squashed]
    if missing:
        return False, f"{len(payload)} bytes, but the page never says {missing}"
    return True, f"{len(payload)} bytes"


def token(html: str) -> str:
    found = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return found.group(1) if found else ""


def csrf_from(path: str) -> str:
    return token(get(path)[1])


def check(label: str, ok: bool, detail: str = "") -> None:
    global problems
    print(f"{'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        problems += 1
        if detail:
            print("      " + re.sub(r"\s+", " ", str(detail))[:420])


def sql(statement: str, args=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(statement, args).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def scalar(statement: str, args=()):
    rows = sql(statement, args)
    return rows[0][0] if rows else None


def last_id(table: str, where: str, args=()) -> int:
    value = scalar(f"SELECT id FROM {table} WHERE {where} ORDER BY id DESC LIMIT 1", args)
    return int(value or 0)


# The public forms stamp when they were opened and carry an unfilled honeypot. Both
# have to be present or the form is treated as a bot, which is the point of them.
def guard(csrf: str) -> dict:
    return {"csrf_token": csrf, "opened_at": str(time.time() - 30), "website": ""}


# A 200 with any of these in the body is a template bug a status code will not catch:
# a missing variable, a row object printed instead of a column, a method not called.
LEAKS = ("UndefinedError", "Traceback (most recent call last)", "jinja2.exceptions",
         ">None<", "sqlite3.Row object", "&lt;bound method", "&lt;built-in method",
         "&lt;generator object")


# ── the GET sweep ───────────────────────────────────────────────────────────
def sweep() -> None:
    """Every page a person can reach, with real ids where the route needs one.

    The ids come from the database rather than being assumed to be 1, because a
    database that has been used for a while has no row 1 left.
    """
    lead = last_id("leads", "1 = 1")
    client = last_id("clients", "1 = 1")
    project = last_id("projects", "1 = 1")
    quote = last_id("quotes", "1 = 1")
    document = last_id("documents", "1 = 1")
    invoice = last_id("invoices", "1 = 1")
    ticket = last_id("tickets", "1 = 1")

    paths = [
        # public
        "/", "/services", "/work", "/about", "/insights",
        "/pricing", "/contact", "/support", "/support/status",
        "/legal/privacy-policy", "/legal/terms-of-service", "/legal/refund-policy",
        "/legal/sla", "/sitemap.xml", "/robots.txt",
        # the filtered lists, which take a different path through the query builder
        "/work?sector=Healthcare", "/insights?tag=pricing",
        "/contact?utm_source=smoke&utm_medium=script&service=SEO",
        "/portal/login", "/portal/verify",
        # the panel
        "/admin/", "/admin/search?q=smoke", "/admin/notifications", "/admin/account",
        "/admin/leads", "/admin/leads/board", "/admin/leads/followups",
        "/admin/leads/conversion", "/admin/leads/export", "/admin/leads/import",
        "/admin/leads/new",
        "/admin/quotes", "/admin/quotes/new", "/admin/ratecard",
        "/admin/documents", "/admin/documents/new", "/admin/clauses",
        "/admin/clients", "/admin/clients/new",
        "/admin/projects", "/admin/projects/new",
        "/admin/tickets", "/admin/tickets/new", "/admin/tickets/report", "/admin/sla",
        "/admin/invoices", "/admin/invoices/new", "/admin/invoices/export",
        "/admin/receivables", "/admin/payments",
        "/admin/recurring", "/admin/renewals", "/admin/referrals",
        "/admin/expenses", "/admin/expenses/new", "/admin/subscriptions",
        "/admin/categories",
        "/admin/analytics", "/admin/analytics?view=month", "/admin/analytics?view=quarter",
        "/admin/vault",
        "/admin/whatsapp/log", "/admin/whatsapp/bulk", "/admin/wa_templates",
        "/admin/email_templates", "/admin/optouts",
        "/admin/packages", "/admin/addons", "/admin/pricing_rules", "/admin/sources",
        "/admin/pages", "/admin/services", "/admin/work", "/admin/testimonials",
        "/admin/faqs", "/admin/posts", "/admin/legal", "/admin/nav", "/admin/stats",
        "/admin/tech", "/admin/seo", "/admin/reviews",
        "/admin/media", "/admin/media/picker",
        "/admin/settings", "/admin/settings/contact", "/admin/settings/theme",
        "/admin/settings/seo", "/admin/settings/whatsapp", "/admin/settings/email",
        "/admin/settings/tax", "/admin/settings/documents", "/admin/settings/pricing",
        "/admin/settings/support", "/admin/settings/portal", "/admin/settings/crm",
        "/admin/setup", "/admin/setup/money", "/admin/setup/legal", "/admin/setup/pricing",
        "/admin/users", "/admin/users/new", "/admin/audit", "/admin/backup",
        # not found
        "/no-such-page-here", "/services/nope", "/work/nope", "/insights/nope",
        "/legal/nope", "/d/not-a-real-token",
    ]

    # Every published service, case study and post, taken from the database rather
    # than hard-coded, so adding one to the seed puts it under test automatically.
    for table, prefix in (("services", "/services"), ("case_studies", "/work"),
                          ("posts", "/insights")):
        paths += [f"{prefix}/{r['slug']}" for r in
                  sql(f"SELECT slug FROM {table} WHERE is_published = 1 ORDER BY id")]

    for row_id, path in ((lead, "/admin/leads/%d"), (lead, "/admin/leads/%d/convert"),
                         (client, "/admin/clients/%d"), (project, "/admin/projects/%d"),
                         (project, "/admin/analytics/project/%d"), (quote, "/admin/quotes/%d"),
                         (document, "/admin/documents/%d"), (invoice, "/admin/invoices/%d"),
                         (ticket, "/admin/tickets/%d")):
        if row_id:
            paths.append(path % row_id)

    print("-- GET sweep --")
    global problems
    failed = 0
    for path in paths:
        expected = 404 if ("no-such-page" in path or "nope" in path
                           or "not-a-real-token" in path) else 200
        status, body = get(path)
        if status != expected:
            problems += 1
            failed += 1
            print(f"FAIL {status} {path}")
            print("      " + re.sub(r"\s+", " ", body)[:300])
            continue
        leak = next((smell for smell in LEAKS if smell in body), "")
        if leak:
            problems += 1
            failed += 1
            print(f"FAIL {path} leaked {leak!r} into the page")
    print(f"{'ok  ' if not failed else 'FAIL'} {len(paths)} pages, {failed} bad")


# ── enquiry to lead ─────────────────────────────────────────────────────────
def enquiry_to_lead() -> int:
    print("\n-- enquiry to lead --")
    csrf = csrf_from("/contact")
    check("the enquiry form carries a CSRF token", bool(csrf))

    status, body, _ = post("/contact", {"name": "Smoke No Token", "phone": "9800000009",
                                        "message": "No token."})
    check("an enquiry with no CSRF token is refused", status == 400, body)

    status, body, _ = post("/contact", {
        **guard(csrf), "name": f"{MARK} Kalyani", "company": f"{MARK} Textiles",
        "email": "smoke@example.invalid", "phone": "9800000001",
        "service_interest": "Websites", "budget_band": "25,000 - 50,000",
        "message": "We need a site and we sell in Italy too. Raised by the smoke test.",
        "utm_source": "smoke"})
    check("the enquiry is accepted and thanks them", status == 200, body[:300])

    lead_id = last_id("leads", "name LIKE ?", (f"{MARK}%",))
    check("it became a lead", lead_id > 0)
    if not lead_id:
        return 0

    row = sql("SELECT * FROM leads WHERE id = ?", (lead_id,))[0]
    check("the lead is not flagged as spam", row["is_spam"] == 0)
    check("it carries a reference", bool(row["ref"]), row["ref"])
    check("the UTM source was kept", row["utm_source"] == "smoke", row["utm_source"])
    check("it was scored", (row["score"] or 0) > 0, row["score"])
    check("it appears on the pipeline board", row["name"] in get("/admin/leads/board")[1])

    # The honeypot has to answer as though it worked, or a bot learns which field
    # gave it away.
    before = scalar("SELECT COUNT(*) FROM leads")
    post("/contact", {**guard(csrf), "name": f"{MARK} Bot", "email": "bot@example.invalid",
                      "message": "spam", "website": "http://spam.example"})
    check("a filled honeypot is dropped silently",
          scalar("SELECT COUNT(*) FROM leads") == before)

    before = scalar("SELECT COUNT(*) FROM leads")
    post("/contact", {"csrf_token": csrf, "opened_at": str(time.time()), "website": "",
                      "name": f"{MARK} Fast", "email": "fast@example.invalid",
                      "message": "spam"})
    check("a submission faster than a human could type is dropped",
          scalar("SELECT COUNT(*) FROM leads") == before)

    csrf = csrf_from(f"/admin/leads/{lead_id}")
    status, payload = post_json("/admin/leads/move",
                                {"lead_id": lead_id, "stage": "qualified"}, csrf)
    check("dragging it to another column works", payload.get("ok") is True, payload)
    check("the move is on the timeline",
          (scalar("SELECT COUNT(*) FROM lead_events WHERE lead_id = ? AND kind = 'stage'",
                  (lead_id,)) or 0) >= 1)

    status, body, _ = post(f"/admin/leads/{lead_id}", {
        "csrf_token": csrf_from(f"/admin/leads/{lead_id}"),
        "name": f"{MARK} Kalyani", "email": "smoke@example.invalid",
        "phone": "9800000001", "stage": "qualified",
        "next_followup_on": "2026-01-01",
        "followup_note": "Overdue on purpose, by the smoke test."})
    check("a follow-up date can be set", status == 200, body[:300])
    check("an overdue follow-up shows in the queue",
          f"{MARK} Kalyani" in get("/admin/leads/followups")[1])

    status, body, _ = post(f"/admin/leads/{lead_id}/snooze", {
        "csrf_token": csrf_from(f"/admin/leads/{lead_id}"), "days": "3",
        "note": "Snoozed by the smoke test."})
    check("it can be snoozed", status == 200, body[:300])

    status, body, _ = post(f"/admin/leads/{lead_id}/event", {
        "csrf_token": csrf_from(f"/admin/leads/{lead_id}"), "kind": "call",
        "body": "Called, wants Italian as well. Smoke test note."})
    check("a call lands on the timeline", "Smoke test note" in body, body[:300])
    return lead_id


# ── the calculator ──────────────────────────────────────────────────────────
def price_it(lead_id: int) -> int:
    print("\n-- the calculator --")
    package = scalar("SELECT id FROM packages WHERE slug = 'growth'") \
        or scalar("SELECT id FROM packages ORDER BY id LIMIT 1")
    extra = scalar("SELECT id FROM addons WHERE is_quantity = 1 AND is_active = 1 "
                   "ORDER BY id LIMIT 1")
    recurring = scalar("SELECT id FROM addons WHERE is_recurring = 1 AND is_active = 1 "
                       "ORDER BY id LIMIT 1")

    config = {"package_id": package, "pages": 16, "rush": "1", "complexity": "1.2"}
    if extra:
        config[f"addon_{extra}"] = 4
    if recurring:
        config[f"addon_{recurring}"] = "1"

    csrf = csrf_from("/admin/quotes/new")
    status, payload = post_json("/admin/quotes/preview", config, csrf)
    check("the live preview prices a configuration", payload.get("ok") is True, payload)
    check("the owner sees their own margin", payload.get("margin") is not None, payload)
    check("a rush job carries its surcharge", (payload.get("surcharge") or 0) > 0, payload)
    if recurring:
        check("recurring lines are counted apart from the build",
              (payload.get("recurring_yearly") or 0) > 0, payload)
    check("it proposes a payment schedule", len(payload.get("milestones") or []) >= 2, payload)
    previewed = payload.get("total")

    status, body, _ = post("/admin/quotes/new", {
        "csrf_token": csrf_from("/admin/quotes/new"), "title": f"{MARK} website and SEO",
        "lead_id": lead_id, "notes": "Priced by the smoke test.", **config})
    check("the quote saves", status == 200, body[:300])

    quote_id = last_id("quotes", "title LIKE ?", (f"{MARK}%",))
    check("the quote exists", quote_id > 0)
    if not quote_id:
        return 0

    quote = sql("SELECT * FROM quotes WHERE id = ?", (quote_id,))[0]
    check("the saved total matches what was previewed",
          abs(quote["total"] - (previewed or 0)) < 1,
          f"saved {quote['total']} vs previewed {previewed}")
    check("the lead's own value came from the quote",
          scalar("SELECT quote_value FROM leads WHERE id = ?", (lead_id,)) == quote["total"])
    check("pricing a lead moved it to quoted",
          scalar("SELECT stage FROM leads WHERE id = ?", (lead_id,)) == "quoted")

    lines = sql("SELECT * FROM quote_lines WHERE quote_id = ? ORDER BY id", (quote_id,))
    check("it has line items", len(lines) >= 2, len(lines))
    if lines:
        status, body, _ = post(f"/admin/quotes/{quote_id}/line/{lines[0]['id']}", {
            "csrf_token": csrf_from(f"/admin/quotes/{quote_id}"),
            "unit_price": "9999", "qty": "1",
            "description": "Overridden by the smoke test"})
        check("a single line can be overridden by hand",
              "Overridden by the smoke test" in body, body[:300])
        after = sql("SELECT * FROM quotes WHERE id = ?", (quote_id,))[0]
        check("overriding a line re-totals the quote", after["total"] != quote["total"],
              f"{quote['total']} -> {after['total']}")
    return quote_id


# ── the document builder ────────────────────────────────────────────────────
def propose(quote_id: int, lead_id: int) -> tuple[int, str]:
    print("\n-- the document builder --")
    csrf = csrf_from(f"/admin/documents/new?quote_id={quote_id}&lead_id={lead_id}")
    status, body, _ = post("/admin/documents/new", {
        "csrf_token": csrf, "kind": "proposal", "quote_id": quote_id, "lead_id": lead_id,
        "title": f"{MARK} proposal", "scope": "A five page site, by the smoke test."})
    check("a proposal is built from the quote", status == 200, body[:300])

    document_id = last_id("documents", "title LIKE ?", (f"{MARK}%",))
    check("the document exists", document_id > 0)
    if not document_id:
        return 0, ""

    document = sql("SELECT * FROM documents WHERE id = ?", (document_id,))[0]
    check("it has an FY-scoped reference", "/" in (document["ref"] or ""), document["ref"])
    check("it starts as a draft", document["status"] == "draft", document["status"])
    check("the clause ids were stored on the document",
          len(json.loads(document["body_json"] or "{}").get("clause_ids") or []) > 5)

    ok, detail = pdf_says(f"/admin/documents/{document_id}/pdf",
                          document["ref"], f"{MARK} proposal", "smoke test")
    check("the proposal renders as a PDF carrying its reference and scope", ok, detail)

    status, body, _ = post(f"/admin/documents/{document_id}/status", {
        "csrf_token": csrf_from(f"/admin/documents/{document_id}"), "status": "sent"})
    check("it can be marked sent", status == 200, body[:300])

    status, body, _ = post(f"/admin/documents/{document_id}/share", {
        "csrf_token": csrf_from(f"/admin/documents/{document_id}"), "days": "30"})
    check("a share link is issued", status == 200, body[:300])
    share = scalar("SELECT token FROM document_shares WHERE document_id = ? "
                   "AND revoked_at IS NULL ORDER BY id DESC LIMIT 1", (document_id,))
    check("the share token was stored", bool(share))
    return document_id, share or ""


def client_accepts(document_id: int, share: str, lead_id: int) -> None:
    print("\n-- the client accepts --")
    if not share:
        return
    status, body = get(f"/d/{share}")
    check("the share link opens without a login", status == 200, body[:300])
    check("the shared page is noindex", 'name="robots"' in body and "noindex" in body)
    check("the lawyer-review banner is on it", "Have your own lawyer read this" in body)
    check("opening it was counted",
          (scalar("SELECT views FROM document_shares WHERE token = ?", (share,)) or 0) >= 1)
    check("opening it moved the document to viewed",
          scalar("SELECT status FROM documents WHERE id = ?", (document_id,)) == "viewed")

    ok, detail = pdf_says(f"/d/{share}/pdf",
                          scalar("SELECT ref FROM documents WHERE id = ?", (document_id,)))
    check("the client can download the PDF from the share link", ok, detail)
    check("an unknown share token is a 404", get("/d/not-a-real-token-at-all")[0] == 404)

    csrf = token(get(f"/d/{share}")[1])
    status, body, _ = post(f"/d/{share}/respond", {
        **guard(csrf), "action": "accept", "name": f"{MARK} Kalyani"})
    check("accepting without ticking the box is refused",
          scalar("SELECT status FROM documents WHERE id = ?", (document_id,)) != "accepted",
          "it accepted without consent")

    csrf = token(get(f"/d/{share}")[1])
    status, body, _ = post(f"/d/{share}/respond", {
        **guard(csrf), "action": "accept", "agree": "1", "name": f"{MARK} Kalyani",
        "note": "Happy with it. Smoke test."})
    check("the client can accept online", status == 200, body[:300])

    document = sql("SELECT * FROM documents WHERE id = ?", (document_id,))[0]
    check("the document is marked accepted", document["status"] == "accepted", document["status"])
    check("who accepted it, when, and from where were recorded",
          bool(document["accepted_by"] and document["accepted_at"] and document["accepted_ip"]))
    check("accepting moved the lead to won",
          scalar("SELECT stage FROM leads WHERE id = ?", (lead_id,)) == "won",
          scalar("SELECT stage FROM leads WHERE id = ?", (lead_id,)))
    check("accepting marked the quote accepted",
          scalar("SELECT status FROM quotes WHERE id = ?",
                 (document["quote_id"],)) == "accepted")
    check("it raised a notification",
          (scalar("SELECT COUNT(*) FROM notifications WHERE entity = 'document_accepted' "
                  "AND entity_id = ?", (str(document_id),)) or 0) >= 1)


# ── lead becomes a client and a project ─────────────────────────────────────
def convert(lead_id: int, quote_id: int) -> tuple[int, int]:
    print("\n-- lead becomes a client and a project --")
    status, body, _ = post(f"/admin/leads/{lead_id}/convert", {
        "csrf_token": csrf_from(f"/admin/leads/{lead_id}/convert"),
        "project_name": f"{MARK} website build", "billing_type": "milestone",
        "quote_id": quote_id})
    check("converting works", status == 200, body[:300])

    client_id = last_id("clients", "name LIKE ?", (f"{MARK}%",))
    project_id = last_id("projects", "name LIKE ?", (f"{MARK}%",))
    check("a client was created", client_id > 0)
    check("a project was created", project_id > 0)
    if not (client_id and project_id):
        return client_id, project_id

    check("the lead now points at its client",
          scalar("SELECT client_id FROM leads WHERE id = ?", (lead_id,)) == client_id)
    check("the project took its value from the quote",
          scalar("SELECT value FROM projects WHERE id = ?", (project_id,))
          == scalar("SELECT total FROM quotes WHERE id = ?", (quote_id,)))
    check("a payment schedule was seeded",
          (scalar("SELECT COUNT(*) FROM milestones WHERE project_id = ?",
                  (project_id,)) or 0) >= 2)
    check("the launch checklist was copied onto the project",
          (scalar("SELECT COUNT(*) FROM launch_checklist WHERE project_id = ?",
                  (project_id,)) or 0) > 4)

    step = scalar("SELECT id FROM launch_checklist WHERE project_id = ? ORDER BY id LIMIT 1",
                  (project_id,))
    status, payload = post_json(f"/admin/checklist/{step}/toggle", {},
                                csrf_from(f"/admin/projects/{project_id}"))
    check("a checklist item ticks off", payload.get("ok") is True, payload)

    status, body, _ = post(f"/admin/projects/{project_id}/tasks", {
        "csrf_token": csrf_from(f"/admin/projects/{project_id}"),
        "title": f"{MARK} write the home page copy", "status": "todo"})
    check("a task can be added to the board", status == 200, body[:300])

    task = last_id("tasks", "title LIKE ?", (f"{MARK}%",))
    if task:
        status, payload = post_json(f"/admin/tasks/{task}/move", {"status": "done"},
                                    csrf_from(f"/admin/projects/{project_id}"))
        check("a task can be dragged across the board", payload.get("ok") is True, payload)
        check("finishing tasks moves the progress figure",
              (scalar("SELECT progress_pct FROM projects WHERE id = ?",
                      (project_id,)) or 0) > 0)
    return client_id, project_id


# ── the vault ───────────────────────────────────────────────────────────────
def vault(client_id: int, project_id: int) -> None:
    print("\n-- the vault --")
    status, body, _ = post("/admin/vault/assets", {
        "csrf_token": csrf_from("/admin/vault"), "client_id": client_id,
        "project_id": project_id, "kind": "domain", "label": f"{MARK} domain",
        "provider": "GoDaddy", "identifier": "smoketextiles.in",
        "expires_on": "2026-09-15", "renew_cost": "900", "owned_by": "client",
        "make_recurring": "1", "renew_price": "1800"})
    check("an asset can be stored", status == 200, body[:300])
    check("an expiring asset is on the vault screen",
          f"{MARK} domain" in get("/admin/vault")[1])
    check("asking for a renewal item created one",
          (scalar("SELECT COUNT(*) FROM recurring_items WHERE label LIKE ?",
                  (f"{MARK}%",)) or 0) == 1)

    secret = "not-a-real-password-9x"
    status, body, _ = post("/admin/vault/credentials", {
        "csrf_token": csrf_from("/admin/vault"), "client_id": client_id,
        "label": f"{MARK} hosting panel", "username": "smoke", "secret": secret,
        "url": "https://panel.example.invalid"})
    check("a credential can be stored", status == 200, body[:300])

    row_id = last_id("credentials", "label LIKE ?", (f"{MARK}%",))
    if row_id:
        stored = dict(sql("SELECT * FROM credentials WHERE id = ?", (row_id,))[0])
        check("the secret is not readable in the database", secret not in str(stored),
              "the plaintext is sitting in the row")
        status, payload = post_json(f"/admin/vault/credentials/{row_id}/reveal", {},
                                    csrf_from("/admin/vault"))
        check("it decrypts back for the owner", payload.get("secret") == secret, payload)
        check("reading it was written to the activity log",
              (scalar("SELECT COUNT(*) FROM audit_log WHERE entity = 'credentials' "
                      "AND action = 'view' AND entity_id = ?", (row_id,)) or 0) >= 1)


# ── money ───────────────────────────────────────────────────────────────────
BANK_KEYS = ("invoice.upi_id", "invoice.bank_name", "invoice.bank_account_name",
             "invoice.bank_account_no", "invoice.bank_ifsc", "invoice.bank_branch")


def bank_details(fill: bool) -> None:
    """Fill in or clear the pay-me block, through the settings screen the owner uses.

    A fresh install has no bank details, so an invoice PDF has nothing to pay into.
    The test puts them in, proves they reach the PDF, then puts them back as they were.
    """
    values = {
        "invoice.upi_id": "smoke@upi", "invoice.bank_name": "Smoke Bank",
        "invoice.bank_account_name": "Aruka", "invoice.bank_account_no": "000111222333",
        "invoice.bank_ifsc": "SMOK0000123", "invoice.bank_branch": "Pune",
    } if fill else dict.fromkeys(BANK_KEYS, "")
    form = {"csrf_token": csrf_from("/admin/settings/tax"), **values}
    # Bool fields absent from a POST read as off, so carry the one on this tab through.
    if scalar("SELECT value FROM settings WHERE key = 'gst.composition'") == "true":
        form["gst.composition"] = "1"
    post("/admin/settings/tax", form)


def bill(client_id: int, project_id: int, quote_id: int) -> int:
    print("\n-- money --")
    bank_details(True)
    check("the pay-me details save from the settings screen",
          scalar("SELECT value FROM settings WHERE key = 'invoice.upi_id'") == '"smoke@upi"',
          scalar("SELECT value FROM settings WHERE key = 'invoice.upi_id'"))

    status, body, _ = post("/admin/invoices/new", {
        "csrf_token": csrf_from("/admin/invoices/new"), "client_id": client_id,
        "project_id": project_id, "quote_id": quote_id, "from_quote": "1",
        "share_pct": "100", "notes": f"{MARK} first invoice"})
    check("an invoice is raised from the quote", status == 200, body[:300])

    invoice_id = last_id("invoices", "client_id = ?", (client_id,))
    check("the invoice exists", invoice_id > 0)
    if not invoice_id:
        return 0

    invoice = sql("SELECT * FROM invoices WHERE id = ?", (invoice_id,))[0]
    check("it starts as a draft", invoice["status"] == "draft", invoice["status"])
    check("lines were copied from the quote",
          (scalar("SELECT COUNT(*) FROM invoice_lines WHERE invoice_id = ?",
                  (invoice_id,)) or 0) > 0)
    check("it is a bill of supply while GST is off",
          invoice["doc_mode"] == "bill_of_supply", invoice["doc_mode"])
    check("nothing is paid yet", invoice["amount_paid"] == 0)

    status, body, _ = post(f"/admin/invoices/{invoice_id}/issue", {
        "csrf_token": csrf_from(f"/admin/invoices/{invoice_id}")})
    check("it can be issued", status == 200, body[:300])
    issued = sql("SELECT * FROM invoices WHERE id = ?", (invoice_id,))[0]
    check("issuing takes a number from the FY series",
          bool(issued["ref"]) and "/" in issued["ref"], issued["ref"])
    check("a due date was worked out from the payment terms", bool(issued["due_on"]))
    check("the balance is the whole total", issued["balance"] == issued["total"])

    ok, detail = pdf_says(f"/admin/invoices/{invoice_id}/pdf", issued["ref"], "BILL OF SUPPLY")
    check("the invoice renders as a PDF headed bill of supply", ok, detail)
    ok, detail = pdf_says(f"/admin/invoices/{invoice_id}/pdf",
                          "smoke@upi", "SMOK0000123", "000111222333")
    check("the UPI id and bank block are on the invoice", ok, detail)

    part = round(issued["total"] / 3, 2)
    status, body, _ = post("/admin/payments/new", {
        "csrf_token": csrf_from(f"/admin/invoices/{invoice_id}"), "invoice_id": invoice_id,
        "client_id": client_id, "amount": part, "method": "UPI",
        "reference": "SMOKE-UPI-1", "paid_on": "2026-08-08",
        "notes": "First third, by the smoke test."})
    check("a part payment is accepted", status == 200, body[:300])

    after = sql("SELECT * FROM invoices WHERE id = ?", (invoice_id,))[0]
    check("the invoice knows it is part paid", after["status"] == "part_paid", after["status"])
    check("the balance came down", after["balance"] < after["total"],
          f"{after['balance']} of {after['total']}")

    payment_id = last_id("payments", "invoice_id = ?", (invoice_id,))
    payment = sql("SELECT * FROM payments WHERE id = ?", (payment_id,))[0]
    check("the receipt has its own number", bool(payment["ref"]), payment["ref"])
    ok, detail = pdf_says(f"/admin/payments/{payment_id}/pdf",
                          payment["ref"], "SMOKE-UPI-1")
    check("the receipt renders as a PDF quoting the payment reference", ok, detail)

    status, body, _ = post("/admin/payments/new", {
        "csrf_token": csrf_from(f"/admin/invoices/{invoice_id}"), "invoice_id": invoice_id,
        "client_id": client_id, "amount": after["balance"] + 5000, "method": "UPI",
        "paid_on": "2026-08-09"})
    check("overpaying is refused rather than silently swallowed",
          "more than" in body.lower() or "balance" in body.lower(), body[:300])
    check("the refused overpayment left the ledger alone",
          scalar("SELECT COUNT(*) FROM payments WHERE invoice_id = ?", (invoice_id,)) == 1)

    balance = scalar("SELECT balance FROM invoices WHERE id = ?", (invoice_id,))
    status, body, _ = post("/admin/payments/new", {
        "csrf_token": csrf_from(f"/admin/invoices/{invoice_id}"), "invoice_id": invoice_id,
        "client_id": client_id, "amount": balance, "method": "Bank transfer (NEFT/IMPS)",
        "reference": "SMOKE-NEFT-2", "paid_on": "2026-08-20"})
    check("the rest can be settled", status == 200, body[:300])
    check("the invoice is now paid",
          scalar("SELECT status FROM invoices WHERE id = ?", (invoice_id,)) == "paid",
          scalar("SELECT status FROM invoices WHERE id = ?", (invoice_id,)))
    check("the receipt shows in the ledger", "SMOKE-UPI-1" in get("/admin/payments")[1])

    status, body, _ = post(f"/admin/invoices/{invoice_id}/credit", {
        "csrf_token": csrf_from(f"/admin/invoices/{invoice_id}"),
        "amount": "1000", "reason": "Goodwill, by the smoke test."})
    check("a credit note can be raised", status == 200, body[:300])
    note_id = last_id("credit_notes", "invoice_id = ?", (invoice_id,))
    if note_id:
        ok, detail = pdf_says(f"/admin/credit-notes/{note_id}/pdf",
                              scalar("SELECT ref FROM credit_notes WHERE id = ?", (note_id,)))
        check("the credit note renders as a PDF", ok, detail)

    # A milestone invoice is the other way money is raised, so it gets its own pass.
    milestone = scalar("SELECT id FROM milestones WHERE project_id = ? AND invoice_id IS NULL "
                       "ORDER BY sort_order LIMIT 1", (project_id,))
    if milestone:
        status, body, _ = post(f"/admin/milestones/{milestone}/invoice", {
            "csrf_token": csrf_from(f"/admin/projects/{project_id}")})
        check("a milestone can be invoiced on its own", status == 200, body[:300])
        check("the milestone remembers which invoice it became",
              bool(scalar("SELECT invoice_id FROM milestones WHERE id = ?", (milestone,))))

    check("receivables shows the aging buckets", "days" in get("/admin/receivables")[1].lower())
    bank_details(False)
    return invoice_id


# ── support ─────────────────────────────────────────────────────────────────
def support(client_id: int, project_id: int) -> int:
    print("\n-- support --")
    csrf = csrf_from("/support")
    status, body, _ = post("/support/new", {
        **guard(csrf), "contact_name": f"{MARK} Kalyani",
        "contact_email": "smoke@example.invalid", "contact_phone": "9800000001",
        "subject": f"{MARK} contact form is not sending", "priority": "p1",
        "category": "bug", "body": "Nothing arrives when the form is submitted."})
    check("a client can raise a ticket from the public site", status == 200, body[:300])
    check("they are given a reference to quote",
          re.search(r"TKT-\d+", body) is not None, body[:300])

    ticket_id = last_id("tickets", "subject LIKE ?", (f"{MARK}%",))
    check("the ticket exists", ticket_id > 0)
    if not ticket_id:
        return 0

    ticket = sql("SELECT * FROM tickets WHERE id = ?", (ticket_id,))[0]
    check("an SLA clock was set from the priority",
          bool(ticket["response_due_at"] and ticket["resolve_due_at"]))

    # Attach it to the client so the portal has something to show, and backdate it so
    # the promise is already broken.
    sql("UPDATE tickets SET client_id = ?, project_id = ?, "
        "created_at = datetime('now', '-5 days'), "
        "response_due_at = datetime('now', '-4 days'), "
        "resolve_due_at = datetime('now', '-3 days') WHERE id = ?",
        (client_id, project_id, ticket_id))

    body = get("/admin/tickets?sla=breached")[1]
    check("a breached P1 is findable in the queue", ticket["ref"] in body, body[:300])

    status, body, _ = post(f"/admin/tickets/{ticket_id}/reply", {
        "csrf_token": csrf_from(f"/admin/tickets/{ticket_id}"),
        "body": "Looking at it now. Smoke test reply."})
    check("a reply can be sent", "Smoke test reply" in body, body[:300])
    check("the first-response clock stopped",
          bool(scalar("SELECT first_response_at FROM tickets WHERE id = ?", (ticket_id,))))

    status, body, _ = post(f"/admin/tickets/{ticket_id}/reply", {
        "csrf_token": csrf_from(f"/admin/tickets/{ticket_id}"),
        "body": "Internal: it is the SMTP password. Smoke test note.", "is_internal": "1"})
    check("an internal note can be kept out of the thread", status == 200, body[:300])
    check("the note is flagged internal in the database",
          (scalar("SELECT COUNT(*) FROM ticket_messages WHERE ticket_id = ? "
                  "AND is_internal = 1", (ticket_id,)) or 0) == 1)

    status, body, _ = post(f"/admin/tickets/{ticket_id}/time", {
        "csrf_token": csrf_from(f"/admin/tickets/{ticket_id}"),
        "minutes": "90", "note": "Debugging, by the smoke test.", "is_billable": "1"})
    check("time can be logged against it", status == 200, body[:300])

    status, body, _ = post(f"/admin/tickets/{ticket_id}/status", {
        "csrf_token": csrf_from(f"/admin/tickets/{ticket_id}"), "status": "resolved"})
    check("it can be resolved", status == 200, body[:300])
    check("the resolution was stamped",
          bool(scalar("SELECT resolved_at FROM tickets WHERE id = ?", (ticket_id,))))

    status, body, _ = post(f"/admin/tickets/{ticket_id}/change-request", {
        "csrf_token": csrf_from(f"/admin/tickets/{ticket_id}")})
    check("an out-of-scope ticket becomes a quote", status == 200, body[:300])
    change_quote = scalar("SELECT quote_id FROM tickets WHERE id = ?", (ticket_id,))
    check("the ticket now points at that quote", bool(change_quote), change_quote)
    check("the ticket is flagged as a change request",
          scalar("SELECT is_change_request FROM tickets WHERE id = ?", (ticket_id,)) == 1)
    if change_quote:
        check("the quote was priced from the time already logged",
              (scalar("SELECT total FROM quotes WHERE id = ?", (change_quote,)) or 0) > 0,
              scalar("SELECT total FROM quotes WHERE id = ?", (change_quote,)))

    check("the SLA report renders", "SLA" in get("/admin/tickets/report")[1])
    return ticket_id


# ── the client portal ───────────────────────────────────────────────────────
def portal(client_id: int) -> None:
    print("\n-- the client portal --")
    email = scalar("SELECT email FROM clients WHERE id = ?", (client_id,))
    if not email:
        check("the client has an email to sign in with", False)
        return

    status, body, _ = post("/portal/login", {
        "csrf_token": csrf_from("/portal/login"), "email": email})
    check("asking for a code works", status == 200, body[:300])
    check("the answer gives nothing away about whether the address is ours",
          "on its way" in body.lower(), body[:300])

    row = sql("SELECT * FROM client_logins WHERE email = ? AND used_at IS NULL "
              "ORDER BY id DESC LIMIT 1", (email,))
    check("a one-time code was issued", bool(row))
    if not row:
        return
    check("only the hash of the code is stored",
          bool(row[0]["code_hash"]) and len(row[0]["code_hash"]) > 40)

    # With email off the code is pushed into a notification for the owner to read
    # out, which is the documented fallback and the only place it exists in clear.
    note = scalar("SELECT body FROM notifications WHERE body LIKE ? ORDER BY id DESC LIMIT 1",
                  (f"%{email}%",))
    found = re.search(r"code is (\d{6})", note or "")
    check("the owner can read the code when email is off", bool(found), note)
    if not found:
        return
    code = found.group(1)

    status, body, _ = post("/portal/verify", {
        "csrf_token": csrf_from("/portal/verify"), "email": email, "code": "000000"})
    check("a wrong code is refused",
          not scalar("SELECT used_at FROM client_logins WHERE id = ?", (row[0]["id"],)))

    status, body, _ = post("/portal/verify", {
        "csrf_token": csrf_from("/portal/verify"), "email": email, "code": code})
    check("the right code signs the client in", status == 200, body[:300])
    check("the code cannot be used twice",
          bool(scalar("SELECT used_at FROM client_logins WHERE id = ?", (row[0]["id"],))))

    for path in ("/portal/home", "/portal/invoices", "/portal/documents",
                 "/portal/tickets", "/portal/tickets/new"):
        status, body = get(path)
        check(f"the client can see {path}", status == 200, body[:300])

    body = get("/portal/home")[1]
    check("they see their own project", f"{MARK} website build" in body)
    check("their internal cost is not on the page", "internal" not in body.lower())

    mine = sql("SELECT id, ref FROM invoices WHERE client_id = ? AND status != 'draft' "
               "ORDER BY id LIMIT 1", (client_id,))
    if mine:
        ok, detail = pdf_says(f"/portal/invoices/{mine[0]['id']}.pdf", mine[0]["ref"])
        check("they can download their own invoice", ok, detail)

    other = scalar("SELECT id FROM invoices WHERE client_id != ? AND status != 'draft' "
                   "LIMIT 1", (client_id,))
    if other:
        status, _ = get(f"/portal/invoices/{other}.pdf")
        check("another client's invoice is not reachable", status == 404, str(status))

    status, body, _ = post("/portal/tickets/new", {
        "csrf_token": csrf_from("/portal/tickets/new"),
        "subject": f"{MARK} portal change request", "priority": "p3",
        "category": "feature", "body": "Add a careers page.", "is_change_request": "1"})
    check("they can raise a request from the portal", status == 200, body[:300])
    check("it was logged as a change request",
          (scalar("SELECT is_change_request FROM tickets WHERE subject LIKE ?",
                  (f"{MARK} portal%",)) or 0) == 1)

    post("/portal/logout", {"csrf_token": csrf_from("/portal/home")})
    status, _ = get("/portal/home")
    check("signing out ends the portal session", status in (200, 302))


# ── expenses and analytics ──────────────────────────────────────────────────
def money_out(project_id: int) -> None:
    print("\n-- expenses and analytics --")
    category = scalar("SELECT id FROM expense_categories WHERE kind = 'cogs' LIMIT 1") \
        or scalar("SELECT id FROM expense_categories ORDER BY id LIMIT 1")
    status, body, _ = post("/admin/expenses/new", {
        "csrf_token": csrf_from("/admin/expenses/new"),
        "description": f"{MARK} illustrator for the hero", "vendor": "Smoke Studio",
        "category_id": category, "project_id": project_id, "amount": "6000",
        "paid_on": "2026-08-12", "method": "UPI", "reference": "SMOKE-EXP-1"})
    check("an expense is recorded", status == 200, body[:300])
    expense_id = last_id("expenses", "description LIKE ?", (f"{MARK}%",))
    check("it got its own reference",
          bool(scalar("SELECT ref FROM expenses WHERE id = ?", (expense_id,))))

    body = get("/admin/analytics")[1]
    check("the analytics page renders the money", "Collected" in body, body[:300])
    body = get(f"/admin/analytics/project/{project_id}")[1]
    check("per-project P&L shows the tagged cost", f"{MARK} illustrator" in body, body[:300])
    check("it shows a margin", "argin" in body)

    for name in ("collected", "invoiced", "expenses", "receivables"):
        status, headers, size = raw(f"/admin/analytics/export/{name}")
        check(f"the {name} CSV downloads",
              status == 200 and "csv" in (headers.get("Content-Type") or "") and size > 20,
              f"{status} {headers.get('Content-Type')} {size}")


# ── WhatsApp ────────────────────────────────────────────────────────────────
def messaging(lead_id: int) -> None:
    print("\n-- WhatsApp --")
    compose = f"/admin/whatsapp/send/lead/{lead_id}"
    status, body = get(compose)
    check("the composer opens for a lead", status == 200, body[:300])

    template = scalar("SELECT id FROM message_templates WHERE channel = 'whatsapp' LIMIT 1")
    status, payload = post_json("/admin/whatsapp/preview",
                                {"template_id": template, "values": {"name": "Kalyani"}},
                                csrf_from(compose))
    check("a template previews with the placeholders filled",
          payload.get("ok") is True and "Kalyani" in (payload.get("body") or ""), payload)

    status, body, url = post(compose, {
        "csrf_token": csrf_from(compose), "number": "9800000001",
        "body": "Hello from the smoke test."})
    check("a message is logged and handed off to WhatsApp",
          "handoff" in (url or "") or "wa.me" in body, url or body[:300])

    message_id = last_id("messages", "body LIKE ?", ("%smoke test%",))
    check("the message is in the log", message_id > 0)
    if message_id:
        check("it waits at ready rather than claiming it was sent",
              scalar("SELECT status FROM messages WHERE id = ?", (message_id,)) == "ready",
              scalar("SELECT status FROM messages WHERE id = ?", (message_id,)))
        status, body, _ = post(f"/admin/whatsapp/confirm/{message_id}", {
            "csrf_token": csrf_from(f"/admin/whatsapp/handoff/{message_id}"),
            "outcome": "sent"})
        check("click-to-chat asks what actually happened", status == 200, body[:300])
        check("the log says sent only once we said so",
              scalar("SELECT status FROM messages WHERE id = ?", (message_id,)) == "sent")

    status, body, _ = post("/admin/optouts/new", {
        "csrf_token": csrf_from("/admin/optouts/new"), "name": f"{MARK} Kalyani",
        "number": "919800000001", "channel": "whatsapp",
        "reason": "Asked us to stop. Smoke test."})
    check("someone can be opted out", status == 200, body[:300])

    body = get(compose)[1]
    check("the composer warns about an opted-out number", "opted out" in body.lower(),
          body[:300])
    before = scalar("SELECT COUNT(*) FROM messages")
    post(compose, {"csrf_token": csrf_from(compose), "number": "9800000001",
                   "body": "Should not be allowed. Smoke test."})
    check("messaging an opted-out number is refused",
          scalar("SELECT COUNT(*) FROM messages") == before)


# ── the public side of pricing and support ──────────────────────────────────
def self_serve() -> None:
    """What a visitor can do without ever speaking to anyone.

    The panel has its own calculator and its own ticket screens; these are the public
    routes, which have to price the same way while also refusing bots and refusing to
    show one person another person's ticket.
    """
    print("\n-- what a visitor can do alone --")
    package = scalar("SELECT id FROM packages WHERE slug = 'growth'") \
        or scalar("SELECT id FROM packages ORDER BY id LIMIT 1")
    addon = scalar("SELECT id FROM addons WHERE is_active = 1 ORDER BY id LIMIT 1")
    config = {"package_id": package, "pages": "9", "complexity": "1.4", "rush": "1"}
    if addon:
        config[f"addon_{addon}"] = "1"

    csrf = csrf_from("/pricing")
    status, body, _ = post("/pricing/estimate", {"csrf_token": csrf, **config})
    payload = json.loads(body or "{}") if status == 200 else {}
    check("the public calculator prices live",
          payload.get("ok") is True and (payload.get("total") or 0) > 0, body[:300])
    check("it itemises what it charged for", len(payload.get("lines") or []) >= 2, body[:300])
    check("the public estimate hides the internal cost",
          "internal_cost" not in body and "margin" not in body, body[:300])

    status, body, _ = post("/pricing", {"csrf_token": csrf, **config})
    check("the page also totals server-side, for a visitor with no JavaScript",
          status == 200 and "total__v" in body, body[:300])

    before = scalar("SELECT COUNT(*) FROM leads")
    status, body, _ = post("/pricing", {
        **guard(csrf_from("/pricing")), **config, "name": f"{MARK} Estimator",
        "email": "estimate@example.invalid", "phone": "9800000002"})
    check("leaving contact details turns an estimate into a lead",
          scalar("SELECT COUNT(*) FROM leads") == before + 1, body[:300])
    lead_id = last_id("leads", "name LIKE ?", (f"{MARK} Estimator%",))
    check("the estimate was saved as a quote against that lead",
          (scalar("SELECT COUNT(*) FROM quotes WHERE lead_id = ?", (lead_id,)) or 0) == 1)
    check("the saved quote records where it came from",
          scalar("SELECT source FROM quotes WHERE lead_id = ?", (lead_id,)) == "public",
          scalar("SELECT source FROM quotes WHERE lead_id = ?", (lead_id,)))

    csrf = csrf_from("/support")
    status, body, _ = post("/support/new", {
        **guard(csrf), "contact_name": f"{MARK} Anonymous",
        "contact_email": "anon@example.invalid",
        "subject": f"{MARK} public lookup", "category": "question", "priority": "p3",
        "body": "Raised without an account, by the smoke test."})
    found = re.search(r"TKT-[\w-]+", body)
    check("a stranger can raise a ticket and is given a reference", bool(found), body[:300])
    if not found:
        return
    ref = found.group(0)

    csrf = csrf_from("/support/status")
    body = post("/support/status", {"csrf_token": csrf, "ref": ref,
                                    "email": "anon@example.invalid"})[1]
    check("the reference plus the matching email opens it", f"{MARK} public lookup" in body,
          body[:300])
    body = post("/support/status", {"csrf_token": csrf_from("/support/status"), "ref": ref,
                                    "email": "someone-else@example.invalid"})[1]
    check("the same reference with the wrong email shows nothing",
          f"{MARK} public lookup" not in body, body[:300])

    status, body, _ = post(f"/support/{ref}/reply", {
        "csrf_token": csrf_from("/support/status"), "email": "anon@example.invalid",
        "body": "Adding a detail. Smoke test."})
    check("they can add to their own ticket without signing in", status == 200, body[:300])
    ticket_id = last_id("tickets", "subject LIKE ?", (f"{MARK} public lookup%",))
    check("the reply is on the thread as the client's",
          (scalar("SELECT COUNT(*) FROM ticket_messages WHERE ticket_id = ? "
                  "AND author_kind = 'client'", (ticket_id,)) or 0) >= 1)

    # The opener follows redirects, so the proof is which page you end up on.
    status, body = get("/support/new")
    check("landing on the bare submit URL puts you on the form",
          status == 200 and 'action="/support/new"' in body, f"{status} {body[:200]}")

    body = get("/robots.txt")[1]
    check("robots.txt points crawlers at the sitemap", "Sitemap:" in body, body[:200])
    body = get("/sitemap.xml")[1]
    check("the sitemap lists the whole public site", body.count("<loc>") >= 15,
          f"{body.count('<loc>')} URLs")


# ── security and housekeeping ───────────────────────────────────────────────
def housekeeping() -> None:
    print("\n-- security and housekeeping --")
    status, body, _ = post("/admin/expenses/new", {"description": "No token at all"})
    check("an admin form without a CSRF token is rejected", status == 400, body[:300])

    status, payload = post_json("/admin/leads/move", {"lead_id": "nonsense", "stage": "won"},
                                csrf_from("/admin/leads/board"))
    check("a malformed JSON write is a 400, not a 500", status == 400, payload)

    status, _ = get("/admin/logout")
    check("signing out cannot be triggered by a link", status == 405, str(status))

    headers = raw("/")[1]
    check("every response carries a content security policy",
          bool(headers.get("Content-Security-Policy")), headers.get("Content-Security-Policy"))
    headers = raw("/admin/")[1]
    check("admin pages are never cached",
          "no-store" in (headers.get("Cache-Control") or ""), headers.get("Cache-Control"))

    body = get("/robots.txt")[1]
    check("robots.txt keeps crawlers out of the panel and the portal",
          "/admin" in body and "/portal" in body, body[:200])
    body = get("/sitemap.xml")[1]
    check("the sitemap lists no private URL",
          "/admin" not in body and "/portal" not in body)

    status, headers, size = raw("/admin/backup/download")
    check("a backup downloads as a zip",
          status == 200 and "zip" in (headers.get("Content-Type") or "") and size > 20000,
          f"{status} {headers.get('Content-Type')} {size}")

    status, body, _ = post("/admin/notifications", {
        "csrf_token": csrf_from("/admin/notifications"), "action": "sweep"})
    check("the digest sweep runs", status == 200, body[:300])

    body = get("/admin/search?q=Smoke")[1]
    check("global search finds the test rows across modules", MARK in body, body[:300])
    body = get("/admin/audit")[1]
    check("the activity log recorded the work", "reated" in body or "pdate" in body)
    body = get("/admin/seo")[1]
    check("the SEO checklist scores the site", "%" in body, body[:300])


# ── cleanup ─────────────────────────────────────────────────────────────────
def purge() -> None:
    """Remove every row this script made. Children before parents."""
    lead_ids = [r["id"] for r in sql("SELECT id FROM leads WHERE name LIKE ?", (f"{MARK}%",))]
    client_ids = [r["id"] for r in sql("SELECT id FROM clients WHERE name LIKE ?",
                                       (f"{MARK}%",))]
    ticket_ids = [r["id"] for r in sql("SELECT id FROM tickets WHERE subject LIKE ?",
                                       (f"{MARK}%",))]
    project_ids = [r["id"] for r in sql("SELECT id FROM projects WHERE name LIKE ?",
                                        (f"{MARK}%",))]

    sql("DELETE FROM messages WHERE to_name LIKE ? OR body LIKE ?",
        (f"{MARK}%", "%smoke test%"))
    sql("DELETE FROM optouts WHERE name LIKE ?", (f"{MARK}%",))
    sql("DELETE FROM notifications WHERE title LIKE ? OR body LIKE ?",
        (f"%{MARK}%", f"%{MARK}%"))
    sql("DELETE FROM expenses WHERE description LIKE ?", (f"{MARK}%",))

    for ticket_id in ticket_ids:
        sql("DELETE FROM ticket_messages WHERE ticket_id = ?", (ticket_id,))
        sql("DELETE FROM ticket_time_logs WHERE ticket_id = ?", (ticket_id,))
        sql("DELETE FROM tickets WHERE id = ?", (ticket_id,))

    for row in sql("SELECT id FROM documents WHERE title LIKE ?", (f"{MARK}%",)):
        sql("DELETE FROM document_views WHERE document_id = ?", (row["id"],))
        sql("DELETE FROM document_shares WHERE document_id = ?", (row["id"],))
        sql("DELETE FROM documents WHERE id = ?", (row["id"],))

    quote_ids = {r["id"] for r in sql("SELECT id FROM quotes WHERE title LIKE ?",
                                      (f"%{MARK}%",))}
    for lead_id in lead_ids:
        quote_ids |= {r["id"] for r in sql("SELECT id FROM quotes WHERE lead_id = ?",
                                          (lead_id,))}
    for quote_id in quote_ids:
        sql("DELETE FROM quote_lines WHERE quote_id = ?", (quote_id,))
        sql("DELETE FROM quotes WHERE id = ?", (quote_id,))

    for client_id in client_ids:
        for row in sql("SELECT id FROM invoices WHERE client_id = ?", (client_id,)):
            sql("DELETE FROM invoice_lines WHERE invoice_id = ?", (row["id"],))
        sql("DELETE FROM credit_notes WHERE client_id = ?", (client_id,))
        sql("DELETE FROM payments WHERE client_id = ?", (client_id,))
        sql("DELETE FROM invoices WHERE client_id = ?", (client_id,))
        sql("DELETE FROM recurring_items WHERE client_id = ?", (client_id,))
        sql("DELETE FROM credentials WHERE client_id = ?", (client_id,))
        sql("DELETE FROM assets WHERE client_id = ?", (client_id,))
        sql("DELETE FROM contacts WHERE client_id = ?", (client_id,))
        sql("DELETE FROM client_logins WHERE client_id = ?", (client_id,))

    for project_id in project_ids:
        sql("DELETE FROM launch_checklist WHERE project_id = ?", (project_id,))
        sql("DELETE FROM milestones WHERE project_id = ?", (project_id,))
        sql("DELETE FROM tasks WHERE project_id = ?", (project_id,))
        sql("DELETE FROM projects WHERE id = ?", (project_id,))

    for client_id in client_ids:
        sql("DELETE FROM clients WHERE id = ?", (client_id,))
    for lead_id in lead_ids:
        sql("DELETE FROM lead_events WHERE lead_id = ?", (lead_id,))
        sql("DELETE FROM leads WHERE id = ?", (lead_id,))

    sql("DELETE FROM tasks WHERE title LIKE ?", (f"{MARK}%",))
    sql("DELETE FROM portal_attempts WHERE email LIKE ?", ("%example.invalid",))
    sql("DELETE FROM login_attempts WHERE email LIKE ?", ("%example.invalid",))
    print("     (test rows removed)")


def main() -> int:
    keep = "--keep" in sys.argv
    email, password = credentials()

    status, html = get("/admin/login")
    if status != 200:
        print(f"the panel is not answering on {BASE}: {status}")
        print("start it with:  python app.py")
        return 1

    status, html, _ = post("/admin/login", {
        "csrf_token": token(html), "email": email, "password": password, "next": ""})
    if "side__brand" not in html:
        print(f"sign-in failed for {email}. Put the right password in config.json, or "
              f"reset it with:\n  python app.py user {email} Owner <password> owner")
        return 1
    print(f"signed in as {email}\n")

    purge()
    sweep()

    lead_id = enquiry_to_lead()
    if lead_id:
        quote_id = price_it(lead_id)
        document_id, share = propose(quote_id, lead_id) if quote_id else (0, "")
        if document_id:
            client_accepts(document_id, share, lead_id)
        client_id, project_id = convert(lead_id, quote_id)
        if client_id and project_id:
            vault(client_id, project_id)
            bill(client_id, project_id, quote_id)
            support(client_id, project_id)
            portal(client_id)
            money_out(project_id)
        messaging(lead_id)
    self_serve()
    housekeeping()

    if keep:
        print("\n     (--keep: test data left in place)")
    else:
        purge()

    print(f"\n{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
