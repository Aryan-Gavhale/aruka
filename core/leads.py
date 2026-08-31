"""The CRM: stages, the activity timeline, follow-ups, scoring and conversion.

The pipeline is deliberately linear with two exits. Everything that happens to a
lead is written to lead_events, so "why did this go quiet" has an answer that does
not depend on anyone's memory.
"""

from __future__ import annotations

from datetime import date

from core import audit, db, numbering, settings
from core.auth import current_user
from core.util import (add_days, clean_phone, dump_json, parse_date, parse_float,
                       parse_int, pct, today_iso, valid_email, wa_number)

STAGES = ("new", "contacted", "qualified", "quoted", "negotiation", "won", "lost", "dormant")
STAGE_LABELS = {
    "new": "New",
    "contacted": "Contacted",
    "qualified": "Qualified",
    "quoted": "Quoted",
    "negotiation": "Negotiation",
    "won": "Won",
    "lost": "Lost",
    "dormant": "Dormant",
}
# The board only shows the live pipeline; won, lost and dormant have their own views
# so a year of closed work does not push today's follow-ups off the screen.
BOARD_STAGES = ("new", "contacted", "qualified", "quoted", "negotiation", "won")
OPEN_STAGES = ("new", "contacted", "qualified", "quoted", "negotiation")
CLOSED_STAGES = ("won", "lost")

EVENT_LABELS = {
    "created": "Created",
    "stage": "Stage change",
    "note": "Note",
    "call": "Call",
    "whatsapp": "WhatsApp",
    "email": "Email",
    "meeting": "Meeting",
    "quote": "Quote",
    "document": "Document",
    "followup": "Follow-up",
    "converted": "Converted",
    "spam": "Spam",
    "import": "Imported",
}


# ── reads ───────────────────────────────────────────────────────────────────
def get(lead_id):
    return db.one("SELECT * FROM leads WHERE id = ?", (lead_id,))


def by_ref(ref: str):
    return db.one("SELECT * FROM leads WHERE ref = ?", (ref,))


def probability(stage: str) -> int:
    table = settings.get("crm.stage_probability") or {}
    return parse_int(table.get(stage, 0))


def board():
    """Leads grouped by stage for the kanban, newest first inside each column."""
    rows = db.query(
        "SELECT l.*, s.name AS source_name FROM leads l "
        "LEFT JOIN lead_sources s ON s.id = l.source_id "
        "WHERE l.is_spam = 0 AND l.stage IN ({}) "
        "ORDER BY l.sort_order, l.id DESC".format(",".join("?" * len(BOARD_STAGES))),
        BOARD_STAGES,
    )
    grouped = {stage: [] for stage in BOARD_STAGES}
    for row in rows:
        grouped[row["stage"]].append(row)
    return grouped


def search(stage: str = "", source_id=None, owner_id=None, q: str = "",
           spam: bool = False, followup: str = "", limit: int = 400):
    sql = ("SELECT l.*, s.name AS source_name, c.name AS client_name FROM leads l "
           "LEFT JOIN lead_sources s ON s.id = l.source_id "
           "LEFT JOIN clients c ON c.id = l.client_id WHERE l.is_spam = ?")
    args: list = [1 if spam else 0]
    if stage and stage in STAGES:
        sql += " AND l.stage = ?"
        args.append(stage)
    elif stage == "open":
        sql += " AND l.stage IN ({})".format(",".join("?" * len(OPEN_STAGES)))
        args += list(OPEN_STAGES)
    if source_id:
        sql += " AND l.source_id = ?"
        args.append(source_id)
    if owner_id:
        sql += " AND l.owner_user_id = ?"
        args.append(owner_id)
    if q:
        sql += (" AND (l.name LIKE ? OR l.company LIKE ? OR l.email LIKE ? "
                "OR l.phone LIKE ? OR l.ref LIKE ?)")
        args += [f"%{q}%"] * 5
    if followup == "due":
        sql += " AND l.next_followup_on IS NOT NULL AND l.next_followup_on <= date('now')"
    elif followup == "overdue":
        sql += " AND l.next_followup_on IS NOT NULL AND l.next_followup_on < date('now')"
    elif followup == "none":
        sql += " AND (l.next_followup_on IS NULL OR l.next_followup_on = '')"
    sql += " ORDER BY l.id DESC LIMIT ?"
    args.append(limit)
    return db.query(sql, args)


def timeline(lead_id, limit: int = 200):
    return db.query(
        "SELECT * FROM lead_events WHERE lead_id = ? ORDER BY id DESC LIMIT ?",
        (lead_id, limit),
    )


def followups_due():
    return db.query(
        "SELECT * FROM leads WHERE is_spam = 0 AND stage IN ({}) "
        "AND next_followup_on IS NOT NULL AND next_followup_on <= date('now') "
        "ORDER BY next_followup_on, id".format(",".join("?" * len(OPEN_STAGES))),
        OPEN_STAGES,
    )


def followups_overdue():
    return db.query(
        "SELECT * FROM leads WHERE is_spam = 0 AND stage IN ({}) "
        "AND next_followup_on IS NOT NULL AND next_followup_on < date('now') "
        "ORDER BY next_followup_on, id".format(",".join("?" * len(OPEN_STAGES))),
        OPEN_STAGES,
    )


def going_quiet():
    """Open leads with no contact for longer than the dormancy window and no
    follow-up booked - the ones that quietly become nothing."""
    days = parse_int(settings.get("crm.dormant_after_days"), 30)
    return db.query(
        "SELECT * FROM leads WHERE is_spam = 0 AND stage IN ({}) "
        "AND (next_followup_on IS NULL OR next_followup_on = '') "
        "AND COALESCE(last_contact_at, created_at) < datetime('now', ?) "
        "ORDER BY COALESCE(last_contact_at, created_at)".format(",".join("?" * len(OPEN_STAGES))),
        list(OPEN_STAGES) + [f"-{days} days"],
    )


# ── writes ──────────────────────────────────────────────────────────────────
def score_of(data: dict) -> int:
    """A rough 0-100 sort order for the board, not a prophecy.

    Contactability first, because a lead with no number is not a lead; then budget,
    then how much they actually told us, then whether they came from a paid click.
    """
    score = 0
    if data.get("phone") or data.get("whatsapp"):
        score += 25
    if valid_email(data.get("email") or ""):
        score += 15
    if data.get("company"):
        score += 10
    band = (data.get("budget_band") or "").lower()
    if "above" in band:
        score += 30
    elif "2,00,000" in band or "75,000" in band:
        score += 22
    elif "30,000" in band:
        score += 14
    elif "10,000" in band:
        score += 8
    message = data.get("message") or ""
    if len(message) > 200:
        score += 12
    elif len(message) > 60:
        score += 7
    if data.get("service_interest"):
        score += 5
    if (data.get("utm_medium") or "").lower() in ("cpc", "paid", "ppc"):
        score += 3
    return min(100, score)


def add_event(lead_id, kind: str, body: str = "", meta: dict | None = None,
              actor: str = "") -> int:
    user = current_user()
    return db.insert("lead_events", {
        "lead_id": lead_id,
        "kind": kind,
        "body": body[:4000],
        "meta": dump_json(meta or {}),
        "user_id": user["id"] if user else None,
        "user_email": (user["email"] if user else actor) or "system",
    })


def create(data: dict, source: str = "admin", actor: str = "") -> int:
    """Insert a lead and open its timeline. `data` is already-cleaned column values."""
    payload = dict(data)
    payload.setdefault("stage", "new")
    payload["ref"] = numbering.take("lead")
    payload["whatsapp"] = wa_number(payload.get("whatsapp") or payload.get("phone") or "")
    payload["phone"] = clean_phone(payload.get("phone") or "")
    payload["score"] = score_of(payload)
    if not payload.get("next_followup_on"):
        payload["next_followup_on"] = add_days(
            date.today(), parse_int(settings.get("crm.followup_days"), 2)).isoformat()

    columns = set(db.table_columns("leads"))
    lead_id = db.insert("leads", {k: v for k, v in payload.items() if k in columns})
    add_event(lead_id, "created", f"Lead captured from {source}.", {"source": source}, actor=actor)
    audit.log("create", "leads", lead_id, payload.get("name", ""), after=payload, actor=actor)
    return lead_id


def set_stage(lead_id, stage: str, note: str = "", lost_reason: str = "") -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    lead = get(lead_id)
    if not lead:
        return
    before = lead["stage"]
    changes = {"stage": stage, "updated_at": db.scalar("SELECT datetime('now')")}
    if stage == "lost":
        changes["lost_reason"] = lost_reason or lead["lost_reason"] or ""
        changes["closed_at"] = db.scalar("SELECT datetime('now')")
        changes["next_followup_on"] = None
    elif stage == "won":
        changes["closed_at"] = db.scalar("SELECT datetime('now')")
    else:
        changes["closed_at"] = None
    db.update("leads", lead_id, changes)
    body = f"{STAGE_LABELS.get(before, before)} to {STAGE_LABELS.get(stage, stage)}"
    if note:
        body += f" - {note}"
    if stage == "lost" and changes.get("lost_reason"):
        body += f" ({changes['lost_reason']})"
    add_event(lead_id, "stage", body, {"from": before, "to": stage})
    audit.log("update", "leads", lead_id, lead["name"],
              before={"stage": before}, after={"stage": stage})


def touch(lead_id, kind: str, body: str = "", meta: dict | None = None,
          bump_followup: bool = True) -> None:
    """Record a real contact attempt and move the follow-up date along."""
    changes = {"last_contact_at": db.scalar("SELECT datetime('now')")}
    if bump_followup:
        changes["next_followup_on"] = add_days(
            date.today(), parse_int(settings.get("crm.followup_days"), 2)).isoformat()
    db.update("leads", lead_id, changes)
    add_event(lead_id, kind, body, meta)
    lead = get(lead_id)
    if lead and lead["stage"] == "new":
        set_stage(lead_id, "contacted", "First contact recorded.")


def snooze(lead_id, days: int, note: str = "") -> str:
    when = add_days(date.today(), max(1, days)).isoformat()
    db.update("leads", lead_id, {"next_followup_on": when, "followup_note": note})
    add_event(lead_id, "followup", f"Follow-up moved to {when}." + (f" {note}" if note else ""))
    return when


def mark_spam(lead_id, spam: bool = True) -> None:
    db.update("leads", lead_id, {"is_spam": 1 if spam else 0})
    add_event(lead_id, "spam", "Marked as spam." if spam else "Restored from spam.")


def sweep_dormant() -> int:
    """Anything untouched past the window with no follow-up drops to dormant, so the
    board shows what is actually being worked rather than everything ever received."""
    stale = going_quiet()
    for lead in stale:
        set_stage(lead["id"], "dormant", "No contact inside the dormancy window.")
    return len(stale)


# ── conversion ──────────────────────────────────────────────────────────────
def convert(lead_id, project_name: str = "", value: float = 0.0,
            billing_type: str = "milestone", quote_id=None) -> tuple[int, int]:
    """Won lead becomes a client, a project and a milestone schedule.

    Returns (client_id, project_id). Idempotent on the client: a lead converted
    twice reuses the client it already created rather than duplicating it.
    """
    from core import billing

    lead = get(lead_id)
    if not lead:
        raise ValueError("lead not found")

    with db.transaction():
        client_id = lead["client_id"]
        if not client_id:
            client_id = db.insert("clients", {
                "ref": numbering.take("client"),
                "name": lead["company"] or lead["name"],
                "contact_name": lead["name"],
                "email": lead["email"] or "",
                "phone": lead["phone"] or "",
                "whatsapp": lead["whatsapp"] or "",
                "city": lead["city"] or "",
                "state_code": settings.get("gst.state_code") or "",
                "referral_code": _referral_code(lead["company"] or lead["name"]),
            })

        project_id = db.insert("projects", {
            "ref": numbering.take("project"),
            "client_id": client_id,
            "name": project_name or (lead["service_interest"] or "New engagement"),
            "quote_id": quote_id,
            "status": "planned",
            "billing_type": billing_type,
            "value": parse_float(value) or parse_float(lead["quote_value"]),
            "start_on": today_iso(),
        })

        if quote_id:
            quote = db.one("SELECT * FROM quotes WHERE id = ?", (quote_id,))
            if quote:
                db.update("quotes", quote_id, {"client_id": client_id, "project_id": project_id})
                db.update("projects", project_id, {
                    "internal_cost": quote["internal_cost"],
                    "recurring_yearly": quote["recurring_yearly"],
                    "package_id": quote["package_id"],
                })

        billing.seed_milestones(project_id)
        seed_launch_checklist(project_id)

        db.update("leads", lead_id, {
            "client_id": client_id,
            "converted_at": db.scalar("SELECT datetime('now')"),
        })

    add_event(lead_id, "converted",
              f"Converted to client #{client_id} and project #{project_id}.",
              {"client_id": client_id, "project_id": project_id})
    if lead["stage"] != "won":
        set_stage(lead_id, "won", "Converted to a project.")
    audit.log("create", "projects", project_id, project_name or lead["name"],
              after={"from_lead": lead["ref"]})
    return client_id, project_id


def _referral_code(name: str) -> str:
    from core.util import ref_code, slugify
    stem = (slugify(name) or "client").split("-")[0][:8].upper()
    return ref_code(stem, 4)


LAUNCH_ITEMS = (
    "Domain pointed and DNS propagated",
    "SSL issued and forced HTTPS",
    "Google Analytics 4 installed and firing",
    "Search Console verified",
    "Sitemap submitted and robots.txt checked",
    "Meta titles and descriptions on every page",
    "Favicon and social share image in place",
    "Enquiry form delivering to the client inbox",
    "WhatsApp button tested on a real handset",
    "Mobile pass at 390px, no horizontal scroll",
    "Page speed pass on the home and top landing page",
    "404 page and broken-link sweep",
    "Legal pages published (privacy, terms, refund)",
    "Backups scheduled and one restore rehearsed",
    "Admin handover recorded and credentials transferred",
)


def seed_launch_checklist(project_id) -> None:
    """The list a website hand-over is not finished without.

    Copied onto the project rather than referenced, so editing it for one job never
    changes what the next project inherits.
    """
    for index, label in enumerate(LAUNCH_ITEMS):
        db.insert("launch_checklist", {
            "project_id": project_id, "label": label, "sort_order": index,
        })


# ── conversion analytics ────────────────────────────────────────────────────
def funnel(since: str = "", until: str = "") -> list[dict]:
    """Count and value per stage, plus the stage-to-stage conversion rate.

    Rates are computed against the count that ever reached the previous stage,
    which for a linear pipeline is the count now at or beyond it.
    """
    where, args = _range_clause(since, until)
    rows = db.query(
        f"SELECT stage, COUNT(*) AS n, COALESCE(SUM(quote_value), 0) AS value "
        f"FROM leads WHERE is_spam = 0 {where} GROUP BY stage", args)
    counts = {r["stage"]: r["n"] for r in rows}
    values = {r["stage"]: r["value"] for r in rows}

    ordered = ("new", "contacted", "qualified", "quoted", "negotiation", "won")
    reached = {}
    for index, stage in enumerate(ordered):
        reached[stage] = sum(counts.get(s, 0) for s in ordered[index:])
    # A lost lead still reached every stage up to where it died, but we cannot know
    # which without walking the events, so lost is reported beside the funnel.

    out = []
    previous = None
    for stage in ordered:
        n = reached.get(stage, 0)
        out.append({
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "at_stage": counts.get(stage, 0),
            "reached": n,
            "value": values.get(stage, 0),
            "rate": pct(n, previous) if previous else 100.0,
        })
        previous = n
    return out


def by_source(since: str = "", until: str = "") -> list[dict]:
    where, args = _range_clause(since, until, table="l")
    rows = db.query(
        "SELECT COALESCE(s.name, 'Not recorded') AS source, s.id AS source_id, "
        "COALESCE(s.cost_monthly, 0) AS cost_monthly, COUNT(*) AS leads, "
        "SUM(CASE WHEN l.stage = 'won' THEN 1 ELSE 0 END) AS won, "
        "SUM(CASE WHEN l.stage = 'lost' THEN 1 ELSE 0 END) AS lost, "
        "COALESCE(SUM(CASE WHEN l.stage = 'won' THEN l.quote_value ELSE 0 END), 0) AS won_value "
        f"FROM leads l LEFT JOIN lead_sources s ON s.id = l.source_id "
        f"WHERE l.is_spam = 0 {where} GROUP BY l.source_id ORDER BY leads DESC", args)
    out = []
    for row in rows:
        out.append({
            "source": row["source"],
            "source_id": row["source_id"],
            "leads": row["leads"],
            "won": row["won"],
            "lost": row["lost"],
            "won_value": row["won_value"],
            "conversion": pct(row["won"], row["leads"], 1),
            "avg_deal": (row["won_value"] / row["won"]) if row["won"] else 0,
        })
    return out


def lost_reasons(since: str = "", until: str = "") -> list[dict]:
    where, args = _range_clause(since, until)
    rows = db.query(
        "SELECT CASE WHEN lost_reason = '' OR lost_reason IS NULL THEN 'Not recorded' "
        "ELSE lost_reason END AS reason, COUNT(*) AS n, "
        "COALESCE(SUM(quote_value), 0) AS value FROM leads "
        f"WHERE is_spam = 0 AND stage = 'lost' {where} GROUP BY reason ORDER BY n DESC", args)
    return [dict(r) for r in rows]


def headline(since: str = "", until: str = "") -> dict:
    where, args = _range_clause(since, until)
    total = int(db.scalar(f"SELECT COUNT(*) FROM leads WHERE is_spam = 0 {where}", args, 0))
    won = int(db.scalar(
        f"SELECT COUNT(*) FROM leads WHERE is_spam = 0 AND stage = 'won' {where}", args, 0))
    lost = int(db.scalar(
        f"SELECT COUNT(*) FROM leads WHERE is_spam = 0 AND stage = 'lost' {where}", args, 0))
    won_value = parse_float(db.scalar(
        f"SELECT COALESCE(SUM(quote_value), 0) FROM leads WHERE is_spam = 0 "
        f"AND stage = 'won' {where}", args, 0))
    days = db.scalar(
        "SELECT AVG(julianday(closed_at) - julianday(created_at)) FROM leads "
        f"WHERE stage = 'won' AND closed_at IS NOT NULL {where}", args, 0)
    quoted = int(db.scalar(
        "SELECT COUNT(DISTINCT lead_id) FROM quotes WHERE lead_id IS NOT NULL", (), 0))
    return {
        "leads": total,
        "won": won,
        "lost": lost,
        "open": total - won - lost,
        "won_value": won_value,
        "win_rate": pct(won, won + lost, 1),
        "conversion": pct(won, total, 1),
        "avg_deal": (won_value / won) if won else 0,
        "avg_days_to_close": round(float(days or 0), 1),
        "quoted_leads": quoted,
    }


def pipeline_forecast() -> dict:
    """Open value weighted by the configured stage probability."""
    rows = db.query(
        "SELECT stage, COALESCE(SUM(quote_value), 0) AS value, COUNT(*) AS n FROM leads "
        "WHERE is_spam = 0 AND stage IN ({}) GROUP BY stage".format(",".join("?" * len(OPEN_STAGES))),
        OPEN_STAGES,
    )
    detail, raw, weighted = [], 0.0, 0.0
    for row in rows:
        p = probability(row["stage"])
        raw += row["value"]
        weighted += row["value"] * p / 100.0
        detail.append({"stage": row["stage"], "label": STAGE_LABELS[row["stage"]],
                       "n": row["n"], "value": row["value"], "probability": p,
                       "weighted": row["value"] * p / 100.0})
    detail.sort(key=lambda d: STAGES.index(d["stage"]))
    return {"raw": raw, "weighted": weighted, "detail": detail}


def _range_clause(since: str, until: str, table: str = ""):
    prefix = f"{table}." if table else ""
    where, args = "", []
    if since:
        where += f" AND {prefix}created_at >= ?"
        args.append(since)
    if until:
        where += f" AND {prefix}created_at < ?"
        args.append(until)
    return where, args
