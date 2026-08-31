"""Documents: what goes in one, how it is versioned, and how a client accepts it.

A document is a snapshot, not a live view. The clause ids and the body copy are
frozen into body_json when it is issued, so re-rendering a proposal a year later
reproduces the wording that was actually agreed rather than today's wording. That
is the whole reason the clause library is versioned.
"""

from __future__ import annotations

from datetime import date

from core import audit, db, numbering, settings
from core.auth import current_user
from core.util import (add_days, dump_json, load_json, parse_int, today_iso, token)

KINDS = {
    "proposal": "Proposal",
    "sow": "Scope of work",
    "amc": "Annual maintenance contract",
    "quotation": "Quotation",
    "agreement": "Service agreement",
    "nda": "Non-disclosure agreement",
}

STATUSES = {
    "draft": "Draft",
    "sent": "Sent",
    "viewed": "Viewed",
    "accepted": "Accepted",
    "declined": "Declined",
    "expired": "Expired",
    "superseded": "Superseded",
}

CLAUSE_CATEGORIES = {
    "commercial": "Money and payment",
    "delivery": "Scope and delivery",
    "ip": "Ownership and IP",
    "data": "Data and privacy",
    "liability": "Liability and risk",
    "exit": "Ending the engagement",
    "legal": "Law and disputes",
}

BODY_FIELDS = ("intro", "included", "excluded", "deliverables", "timeline",
               "assumptions", "closing")

# What the editor calls each section, and why it is worth filling in. The help text
# is the difference between a proposal that wins the work and one that gets argued
# over later, so it lives next to the field rather than in a manual nobody reads.
BODY_LABELS = {
    "intro": (
        "Opening",
        "What you understood them to need, in their words rather than yours. A client who "
        "reads their own problem described accurately has already half decided."),
    "included": (
        "What is included",
        "One line per item. Be specific enough that 'is that included?' has an answer on "
        "the page. A dash starts a bullet."),
    "excluded": (
        "What is not included",
        "The most valuable section in the document. Everything you write here is an "
        "argument you will not be having in month three."),
    "deliverables": (
        "What you actually get",
        "The files, logins and artefacts that change hands. Source, hosting access, a "
        "handover recording - list them, because 'the website' is not a deliverable."),
    "timeline": (
        "Timeline",
        "Working days, and what the dates depend on. Say plainly that silence moves the "
        "finish date; it is the only defence against a project that drifts for months."),
    "assumptions": (
        "Assumptions",
        "What has to be true for the price and dates to hold. If one turns out false, "
        "this section is what makes a change request a conversation rather than a fight."),
    "closing": (
        "Closing",
        "Optional. A short paragraph on what happens after they accept - the kick-off "
        "call, the first invoice, who they talk to."),
}


# ── reads ───────────────────────────────────────────────────────────────────
def get(document_id):
    return db.one("SELECT * FROM documents WHERE id = ?", (document_id,))


def by_ref(ref: str):
    return db.one("SELECT * FROM documents WHERE ref = ?", (ref,))


def clauses_for(kind: str, active_only: bool = True):
    """The current version of every clause that applies to a document kind.

    Grouped by code with the highest version winning, so the library can hold
    three generations of the payment clause without the picker showing all three.
    """
    rows = db.query(
        "SELECT * FROM clause_library WHERE applies_to LIKE ?"
        + (" AND is_active = 1" if active_only else "")
        + " ORDER BY sort_order, code, version DESC", (f"%{kind}%",))
    latest: dict[str, object] = {}
    for row in rows:
        latest.setdefault(row["code"], row)
    return sorted(latest.values(), key=lambda r: (r["sort_order"], r["code"]))


def required_clause_ids(kind: str) -> list[int]:
    return [r["id"] for r in clauses_for(kind) if r["is_required"]]


def shares(document_id):
    return db.query(
        "SELECT * FROM document_shares WHERE document_id = ? ORDER BY id DESC", (document_id,))


def live_share(document_id):
    return db.one(
        "SELECT * FROM document_shares WHERE document_id = ? AND revoked_at IS NULL "
        "AND (expires_on IS NULL OR expires_on >= date('now')) ORDER BY id DESC",
        (document_id,))


def views(document_id, limit: int = 50):
    return db.query(
        "SELECT * FROM document_views WHERE document_id = ? ORDER BY id DESC LIMIT ?",
        (document_id, limit))


# ── writes ──────────────────────────────────────────────────────────────────
def create(*, kind: str, title: str, quote_id=None, lead_id=None, client_id=None,
           project_id=None, body: dict | None = None, clause_ids=None) -> int:
    payload = dict(body or {})
    payload["clause_ids"] = [int(c) for c in (clause_ids or required_clause_ids(kind))]

    document_id = db.insert("documents", {
        "ref": numbering.take("document"),
        "kind": kind if kind in KINDS else "proposal",
        "title": title[:300],
        "status": "draft",
        "version": 1,
        "quote_id": quote_id,
        "lead_id": lead_id,
        "client_id": client_id,
        "project_id": project_id,
        "body_json": dump_json(payload),
        "issued_on": today_iso(),
        "valid_until": add_days(
            date.today(), parse_int(settings.get("doc.validity_days"), 15)).isoformat(),
    })
    audit.log("create", "documents", document_id, title)
    if lead_id:
        from core import leads
        leads.add_event(lead_id, "document", f"{KINDS.get(kind, kind)} {title} drafted.",
                        {"document_id": document_id})
    return document_id


def save_body(document_id, body: dict, clause_ids=None) -> None:
    document = get(document_id)
    if not document:
        return
    payload = load_json(document["body_json"], {})
    payload.update({k: v for k, v in body.items() if k in BODY_FIELDS})
    if clause_ids is not None:
        payload["clause_ids"] = [int(c) for c in clause_ids]
    db.update("documents", document_id, {
        "body_json": dump_json(payload),
        "updated_at": db.scalar("SELECT datetime('now')"),
    })


def new_version(document_id) -> int:
    """Copy a document forward. The old one is kept and marked superseded.

    Editing an issued document in place would mean the PDF a client is holding no
    longer matches the record, which is exactly the argument this is meant to avoid.
    """
    document = get(document_id)
    if not document:
        raise ValueError("document not found")

    with db.transaction():
        new_id = db.insert("documents", {
            **{k: document[k] for k in document.keys()
               if k not in ("id", "ref", "created_at", "updated_at", "sent_at",
                            "accepted_at", "accepted_by", "accepted_ip",
                            "declined_at", "decline_note", "pdf_filename")},
            "ref": numbering.take("document"),
            "version": parse_int(document["version"], 1) + 1,
            "status": "draft",
            "issued_on": today_iso(),
            "valid_until": add_days(
                date.today(), parse_int(settings.get("doc.validity_days"), 15)).isoformat(),
        })
        db.update("documents", document_id, {"status": "superseded"})
        db.execute("UPDATE document_shares SET revoked_at = datetime('now') "
                   "WHERE document_id = ? AND revoked_at IS NULL", (document_id,))

    audit.log("create", "documents", new_id,
              f"version {parse_int(document['version'], 1) + 1} of {document['ref']}")
    return new_id


def set_status(document_id, status: str, note: str = "") -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    document = get(document_id)
    if not document:
        return
    changes = {"status": status, "updated_at": db.scalar("SELECT datetime('now')")}
    if status == "sent" and not document["sent_at"]:
        changes["sent_at"] = db.scalar("SELECT datetime('now')")
    if status == "declined":
        changes["declined_at"] = db.scalar("SELECT datetime('now')")
        changes["decline_note"] = note[:500]
    db.update("documents", document_id, changes)
    audit.log("update", "documents", document_id, document["ref"],
              before={"status": document["status"]}, after={"status": status})


def share(document_id, days: int | None = None) -> str:
    """Mint a tokenised link. Any earlier link is revoked so only one is live.

    A long random token rather than a login: asking a prospect to create an account
    to read a proposal loses proposals. It expires, it is revocable, and every open
    is recorded.
    """
    document = get(document_id)
    if not document:
        raise ValueError("document not found")
    window = days if days is not None else parse_int(settings.get("doc.share_days"), 30)

    with db.transaction():
        db.execute("UPDATE document_shares SET revoked_at = datetime('now') "
                   "WHERE document_id = ? AND revoked_at IS NULL", (document_id,))
        value = token(24)
        db.insert("document_shares", {
            "document_id": document_id,
            "token": value,
            "expires_on": add_days(date.today(), max(1, window)).isoformat(),
        })
        if document["status"] == "draft":
            db.update("documents", document_id,
                      {"status": "sent", "sent_at": db.scalar("SELECT datetime('now')")})
    audit.log("create", "document_shares", document_id, document["ref"],
              after={"expires_in_days": window})
    return value


def revoke_shares(document_id) -> int:
    rows = db.query("SELECT id FROM document_shares WHERE document_id = ? AND revoked_at IS NULL",
                    (document_id,))
    db.execute("UPDATE document_shares SET revoked_at = datetime('now') "
               "WHERE document_id = ? AND revoked_at IS NULL", (document_id,))
    return len(rows)


def open_share(share_token: str):
    """Resolve a token to (document, share) or (None, reason)."""
    row = db.one("SELECT * FROM document_shares WHERE token = ?", (share_token,))
    if not row:
        return None, "unknown"
    if row["revoked_at"]:
        return None, "revoked"
    if row["expires_on"] and row["expires_on"] < today_iso():
        return None, "expired"
    document = get(row["document_id"])
    if not document:
        return None, "unknown"
    return document, row


def record_view(document_id, share_id=None, ip: str = "", agent: str = "") -> None:
    db.insert("document_views", {
        "document_id": document_id,
        "share_id": share_id,
        "ip": ip[:64],
        "user_agent": agent[:300],
    })
    if share_id:
        db.execute(
            "UPDATE document_shares SET views = views + 1, "
            "last_viewed_at = datetime('now') WHERE id = ?", (share_id,))
    document = get(document_id)
    if document and document["status"] == "sent":
        db.update("documents", document_id, {"status": "viewed"})


def accept(document_id, *, name: str, ip: str = "", note: str = "") -> None:
    """Online acceptance. Moves the quote and the lead along with it.

    Acceptance is the one client action that changes the state of the business, so
    it writes through to the quote and the pipeline rather than sitting in its own
    corner waiting to be noticed.
    """
    document = get(document_id)
    if not document:
        raise ValueError("document not found")
    if document["status"] == "accepted":
        return

    with db.transaction():
        db.update("documents", document_id, {
            "status": "accepted",
            "accepted_at": db.scalar("SELECT datetime('now')"),
            "accepted_by": name[:200],
            "accepted_ip": ip[:64],
        })
        if document["quote_id"]:
            db.update("quotes", document["quote_id"], {
                "status": "accepted",
                "accepted_at": db.scalar("SELECT datetime('now')"),
            })

    if document["lead_id"]:
        from core import leads
        leads.add_event(document["lead_id"], "document",
                        f"{document['ref']} accepted online by {name}."
                        + (f" Note: {note}" if note else ""),
                        {"document_id": document_id, "ip": ip})
        lead = leads.get(document["lead_id"])
        if lead and lead["stage"] not in ("won",):
            leads.set_stage(document["lead_id"], "won", "Proposal accepted online.")

    audit.log("update", "documents", document_id, document["ref"],
              after={"status": "accepted", "by": name}, actor=name)

    from core import notify
    notify.push(f"Accepted: {document['title']}",
                f"{name} accepted {document['ref']} online.",
                kind="ok", url=f"/admin/documents/{document_id}",
                entity="document_accepted", entity_id=document_id)


def decline(document_id, *, name: str, note: str = "", ip: str = "") -> None:
    document = get(document_id)
    if not document:
        return
    set_status(document_id, "declined", note)
    if document["quote_id"]:
        db.update("quotes", document["quote_id"], {"status": "declined"})
    if document["lead_id"]:
        from core import leads
        leads.add_event(document["lead_id"], "document",
                        f"{document['ref']} declined by {name}."
                        + (f" Reason: {note}" if note else ""),
                        {"document_id": document_id, "ip": ip})
    from core import notify
    notify.push(f"Declined: {document['title']}",
                f"{name} declined {document['ref']}." + (f" {note}" if note else ""),
                kind="warn", url=f"/admin/documents/{document_id}",
                entity="document_declined", entity_id=document_id)


def expire_stale() -> int:
    """Move past-validity documents to expired so the list stops lying."""
    rows = db.query(
        "SELECT id FROM documents WHERE status IN ('sent', 'viewed', 'draft') "
        "AND valid_until IS NOT NULL AND valid_until < date('now')")
    for row in rows:
        db.update("documents", row["id"], {"status": "expired"})
    return len(rows)


def default_body(kind: str, *, quote=None, package=None, party=None) -> dict:
    """Pre-fill a new document so the owner edits prose rather than writing it."""
    brand = settings.get("brand.name") or "Aruka"
    name = (party["name"] if party is not None else "you")
    days = 0
    if quote is not None:
        from core import pricing
        days = pricing.quote(load_json(quote["config_json"], {})).get("delivery_days", 0)

    intro = {
        "proposal": (
            f"Thank you for talking to {brand} about this. What follows is what we "
            f"understand you need, what we will build, what it costs and when it will be "
            f"finished.\n\nIf anything below does not match the conversation, say so before "
            f"you accept it - the scope in this document is what we will be held to, and "
            f"what we will hold to."),
        "sow": (
            f"This scope of work sets out exactly what {brand} will deliver for {name}, "
            f"what is not included, and what we need from you to keep to the dates."),
        "amc": (
            f"This annual maintenance contract covers keeping what we built for {name} "
            f"online, current and backed up for the next twelve months."),
    }.get(kind, "")

    timeline = ""
    if days:
        timeline = (
            f"Around {days} working days from the first payment and the content being with "
            f"us.\n\nDates assume replies inside two working days. A week of silence moves "
            f"the finish date by a week - not as a penalty, simply because the work cannot "
            f"proceed without answers.")

    return {
        "intro": intro,
        "included": (package["features"] if package is not None else ""),
        "excluded": (package["excluded"] if package is not None else ""),
        "deliverables": "",
        "timeline": timeline,
        "assumptions": (
            "- Content, images and logos are supplied by you unless an add-on says otherwise\n"
            "- Hosting and domain are in your name, or transferred to you on request\n"
            f"- {settings.get('doc.revision_rounds') or 2} rounds of revisions per stage\n"
            "- Third-party costs (domains, licences, paid plugins) are billed at cost"),
        "closing": "",
        "clause_ids": required_clause_ids(kind),
    }


def author_name() -> str:
    user = current_user()
    return (user["name"] if user else settings.get("brand.name")) or "Aruka"
