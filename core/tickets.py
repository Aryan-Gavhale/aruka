"""The support desk and its SLA clock.

A ticket's two deadlines are stamped on at creation from the SLA policy for its
priority, so changing a policy later never silently rewrites history on tickets
already in flight. `sla_state` is the single place that decides whether a ticket
is on time, at risk or breached - the list, the dashboard and the analytics all
ask it rather than each re-deriving the rule.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from core import audit, db, numbering, settings
from core.auth import current_user
from core.util import hours_between, parse_float, parse_int, pct, today_iso

PRIORITIES = ("p1", "p2", "p3", "p4")
PRIORITY_LABELS = {
    "p1": "P1 - down",
    "p2": "P2 - broken",
    "p3": "P3 - normal",
    "p4": "P4 - whenever",
}
PRIORITY_SHORT = {"p1": "P1", "p2": "P2", "p3": "P3", "p4": "P4"}

TICKET_STATUSES = ("open", "in_progress", "waiting_client", "resolved", "closed")
TICKET_STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "waiting_client": "Waiting on client",
    "resolved": "Resolved",
    "closed": "Closed",
}
LIVE_STATUSES = ("open", "in_progress", "waiting_client")

CATEGORIES = {
    "bug": "Something is broken",
    "downtime": "Site or app is down",
    "content": "Content or copy change",
    "seo": "SEO or ranking",
    "billing": "Invoice or payment",
    "feature": "New feature or change request",
    "question": "Question",
    "other": "Something else",
}

# Waiting on the client stops the resolve clock: an agency cannot be held to a
# deadline it has handed back. The response clock has already been met by then.
CLOCK_PAUSED = ("waiting_client", "resolved", "closed")


def policy(priority: str):
    row = db.one("SELECT * FROM sla_policies WHERE priority = ? AND is_active = 1", (priority,))
    if row:
        return {"response_hours": parse_float(row["response_hours"], 24),
                "resolve_hours": parse_float(row["resolve_hours"], 120),
                "label": row["label"]}
    return {
        "response_hours": parse_float(settings.get(f"sla.{priority}_response_hours"), 24),
        "resolve_hours": parse_float(settings.get(f"sla.{priority}_resolve_hours"), 120),
        "label": PRIORITY_LABELS.get(priority, priority),
    }


def get(ticket_id):
    return db.one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))


def by_ref(ref: str):
    return db.one("SELECT * FROM tickets WHERE ref = ?", (ref.strip().upper(),))


def messages(ticket_id, include_internal: bool = True):
    sql = "SELECT * FROM ticket_messages WHERE ticket_id = ?"
    if not include_internal:
        sql += " AND is_internal = 0"
    return db.query(sql + " ORDER BY id", (ticket_id,))


def time_logs(ticket_id):
    return db.query("SELECT * FROM ticket_time_logs WHERE ticket_id = ? ORDER BY id", (ticket_id,))


def create(data: dict, source: str = "web") -> int:
    """Raise a ticket, stamp its SLA deadlines and open the thread with the body."""
    priority = data.get("priority") if data.get("priority") in PRIORITIES else "p3"
    sla = policy(priority)
    now = datetime.now()

    payload = {
        "ref": numbering.take("ticket"),
        "client_id": data.get("client_id"),
        "project_id": data.get("project_id"),
        "contact_name": (data.get("contact_name") or "")[:200],
        "contact_email": (data.get("contact_email") or "")[:200],
        "contact_phone": (data.get("contact_phone") or "")[:60],
        "subject": (data.get("subject") or "Support request")[:300],
        "body": data.get("body") or "",
        "category": data.get("category") if data.get("category") in CATEGORIES else "other",
        "priority": priority,
        "status": "open",
        "source": source,
        "is_change_request": 1 if data.get("is_change_request") else 0,
        "rate_per_hour": parse_float(settings.get("ticket.default_rate_per_hour"), 1200),
        "ip": (data.get("ip") or "")[:60],
        "response_due_at": (now + timedelta(hours=sla["response_hours"])).strftime("%Y-%m-%d %H:%M:%S"),
        "resolve_due_at": (now + timedelta(hours=sla["resolve_hours"])).strftime("%Y-%m-%d %H:%M:%S"),
    }
    ticket_id = db.insert("tickets", payload)
    if payload["body"]:
        db.insert("ticket_messages", {
            "ticket_id": ticket_id,
            "author_kind": "client",
            "author_name": payload["contact_name"] or "Client",
            "body": payload["body"],
            "is_internal": 0,
        })
    audit.log("create", "tickets", ticket_id, payload["subject"], after={"source": source})
    return ticket_id


def reply(ticket_id, body: str, *, author_kind: str = "agent", author_name: str = "",
          is_internal: bool = False, media_id=None) -> int:
    ticket = get(ticket_id)
    if not ticket:
        raise ValueError("ticket not found")
    user = current_user()
    message_id = db.insert("ticket_messages", {
        "ticket_id": ticket_id,
        "author_kind": author_kind,
        "author_name": author_name or (user["name"] if user else "Aruka"),
        "body": body,
        "is_internal": 1 if is_internal else 0,
        "media_id": media_id,
        "user_id": user["id"] if user else None,
    })

    changes: dict = {"updated_at": db.scalar("SELECT datetime('now')")}
    # Only a client-visible agent reply stops the response clock; an internal note
    # is us talking to ourselves and should not count as answering anyone.
    if author_kind == "agent" and not is_internal and not ticket["first_response_at"]:
        changes["first_response_at"] = db.scalar("SELECT datetime('now')")
    if author_kind == "agent" and not is_internal and ticket["status"] == "open":
        changes["status"] = "in_progress"
    if author_kind == "client" and ticket["status"] in ("waiting_client", "resolved"):
        changes["status"] = "in_progress"
        changes["resolved_at"] = None
        if ticket["status"] == "resolved":
            changes["reopened_count"] = parse_int(ticket["reopened_count"], 0) + 1
    db.update("tickets", ticket_id, changes)
    return message_id


def set_status(ticket_id, status: str, note: str = "") -> None:
    if status not in TICKET_STATUSES:
        raise ValueError(f"unknown status: {status}")
    ticket = get(ticket_id)
    if not ticket:
        return
    changes: dict = {"status": status, "updated_at": db.scalar("SELECT datetime('now')")}
    now = db.scalar("SELECT datetime('now')")
    if status == "resolved":
        changes["resolved_at"] = now
    elif status == "closed":
        changes["resolved_at"] = ticket["resolved_at"] or now
        changes["closed_at"] = now
    else:
        changes["resolved_at"] = None
        changes["closed_at"] = None
    db.update("tickets", ticket_id, changes)
    if note:
        reply(ticket_id, note, is_internal=True)
    audit.log("update", "tickets", ticket_id, ticket["subject"],
              before={"status": ticket["status"]}, after={"status": status})


def log_time(ticket_id, minutes: int, note: str = "", billable: bool = False) -> int:
    ticket = get(ticket_id)
    if not ticket:
        raise ValueError("ticket not found")
    user = current_user()
    return db.insert("ticket_time_logs", {
        "ticket_id": ticket_id,
        "project_id": ticket["project_id"],
        "user_id": user["id"] if user else None,
        "minutes": max(0, parse_int(minutes, 0)),
        "note": note[:500],
        "logged_on": today_iso(),
        "is_billable": 1 if billable else 0,
    })


def logged_minutes(ticket_id) -> int:
    return parse_int(db.scalar(
        "SELECT COALESCE(SUM(minutes), 0) FROM ticket_time_logs WHERE ticket_id = ?",
        (ticket_id,), 0))


def billable_amount(ticket_id) -> float:
    minutes = parse_int(db.scalar(
        "SELECT COALESCE(SUM(minutes), 0) FROM ticket_time_logs "
        "WHERE ticket_id = ? AND is_billable = 1", (ticket_id,), 0))
    ticket = get(ticket_id)
    rate = parse_float(ticket["rate_per_hour"]) if ticket else 0
    return round(minutes / 60.0 * rate, 2)


# ── the clock ───────────────────────────────────────────────────────────────
def sla_state(ticket) -> dict:
    """on_time | at_risk | breached | met, for both the response and the resolve leg."""
    at_risk_pct = parse_float(settings.get("sla.at_risk_pct"), 75)
    sla = policy(ticket["priority"])

    def leg(due_at, met_at, budget_hours):
        if met_at:
            late = due_at and str(met_at)[:19] > str(due_at)[:19]
            return {"state": "breached" if late else "met",
                    "hours_left": 0.0, "used_pct": 100.0, "met_at": met_at}
        if not due_at:
            return {"state": "on_time", "hours_left": 0.0, "used_pct": 0.0, "met_at": None}
        left = -hours_between(due_at)          # positive while the deadline is ahead
        used = pct(max(0.0, budget_hours - left), budget_hours, 0) if budget_hours else 0
        if left < 0:
            state = "breached"
        elif used >= at_risk_pct:
            state = "at_risk"
        else:
            state = "on_time"
        return {"state": state, "hours_left": round(left, 1), "used_pct": used, "met_at": None}

    response = leg(ticket["response_due_at"], ticket["first_response_at"], sla["response_hours"])

    paused = ticket["status"] in CLOCK_PAUSED and ticket["status"] == "waiting_client"
    if paused:
        resolve = {"state": "paused", "hours_left": 0.0, "used_pct": 0.0, "met_at": None}
    else:
        resolve = leg(ticket["resolve_due_at"],
                      ticket["resolved_at"] or ticket["closed_at"], sla["resolve_hours"])

    worst = "met"
    for candidate in ("breached", "at_risk", "paused", "on_time", "met"):
        if response["state"] == candidate or resolve["state"] == candidate:
            worst = candidate
            break
    return {"response": response, "resolve": resolve, "state": worst,
            "policy": sla, "label": PRIORITY_LABELS.get(ticket["priority"], ticket["priority"])}


def search(status: str = "", priority: str = "", client_id=None, category: str = "",
           q: str = "", assignee_id=None, sla: str = "", limit: int = 300):
    sql = ("SELECT t.*, c.name AS client_name, p.name AS project_name "
           "FROM tickets t LEFT JOIN clients c ON c.id = t.client_id "
           "LEFT JOIN projects p ON p.id = t.project_id WHERE 1 = 1")
    args: list = []
    if status == "live":
        sql += " AND t.status IN ({})".format(",".join("?" * len(LIVE_STATUSES)))
        args += list(LIVE_STATUSES)
    elif status and status in TICKET_STATUSES:
        sql += " AND t.status = ?"
        args.append(status)
    if priority in PRIORITIES:
        sql += " AND t.priority = ?"
        args.append(priority)
    if client_id:
        sql += " AND t.client_id = ?"
        args.append(client_id)
    if category in CATEGORIES:
        sql += " AND t.category = ?"
        args.append(category)
    if assignee_id:
        sql += " AND t.assignee_user_id = ?"
        args.append(assignee_id)
    if q:
        sql += " AND (t.subject LIKE ? OR t.body LIKE ? OR t.ref LIKE ? OR t.contact_email LIKE ?)"
        args += [f"%{q}%"] * 4
    sql += " ORDER BY CASE t.priority WHEN 'p1' THEN 1 WHEN 'p2' THEN 2 "
    sql += "WHEN 'p3' THEN 3 ELSE 4 END, t.id DESC LIMIT ?"
    args.append(limit)
    rows = db.query(sql, args)
    if sla in ("breached", "at_risk"):
        rows = [r for r in rows if sla_state(r)["state"] == sla]
    return rows


def at_risk():
    """Live tickets that are at risk or already breached, worst first."""
    rows = search(status="live", limit=500)
    flagged = [(r, sla_state(r)) for r in rows]
    order = {"breached": 0, "at_risk": 1}
    flagged = [(r, s) for r, s in flagged if s["state"] in order]
    flagged.sort(key=lambda pair: (order[pair[1]["state"]], pair[0]["priority"]))
    return flagged


def stats(since: str = "", until: str = "") -> dict:
    where, args = "", []
    if since:
        where += " AND created_at >= ?"
        args.append(since)
    if until:
        where += " AND created_at < ?"
        args.append(until)

    total = int(db.scalar(f"SELECT COUNT(*) FROM tickets WHERE 1 = 1 {where}", args, 0))
    live = int(db.scalar(
        "SELECT COUNT(*) FROM tickets WHERE status IN ({}) {}".format(
            ",".join("?" * len(LIVE_STATUSES)), where), list(LIVE_STATUSES) + args, 0))
    resolved = db.query(
        f"SELECT * FROM tickets WHERE resolved_at IS NOT NULL {where}", args)

    met = sum(1 for t in resolved if sla_state(t)["resolve"]["state"] == "met")
    responded = [t for t in resolved if t["first_response_at"]]
    avg_response = (sum(hours_between(t["created_at"], t["first_response_at"])
                        for t in responded) / len(responded)) if responded else 0
    avg_resolve = (sum(hours_between(t["created_at"], t["resolved_at"])
                       for t in resolved) / len(resolved)) if resolved else 0

    by_priority = db.query(
        f"SELECT priority, COUNT(*) AS n FROM tickets WHERE 1 = 1 {where} GROUP BY priority", args)
    by_category = db.query(
        f"SELECT category, COUNT(*) AS n FROM tickets WHERE 1 = 1 {where} "
        "GROUP BY category ORDER BY n DESC", args)

    return {
        "total": total,
        "live": live,
        "resolved": len(resolved),
        "sla_met": met,
        "sla_pct": pct(met, len(resolved), 1),
        "avg_response_hours": round(avg_response, 1),
        "avg_resolve_hours": round(avg_resolve, 1),
        "by_priority": {r["priority"]: r["n"] for r in by_priority},
        "by_category": [dict(r) for r in by_category],
        "reopened": int(db.scalar(
            f"SELECT COALESCE(SUM(reopened_count), 0) FROM tickets WHERE 1 = 1 {where}", args, 0)),
    }


def to_change_request(ticket_id, package_id=None) -> int:
    """An out-of-scope ticket becomes a quote, so "can you just..." has a price.

    The quote starts from the logged time at the ticket's rate, which is the honest
    floor, and every line stays editable before it is sent.
    """
    from core import pricing

    ticket = get(ticket_id)
    if not ticket:
        raise ValueError("ticket not found")

    minutes = logged_minutes(ticket_id) or 60
    hours = round(max(1.0, minutes / 60.0), 1)
    rate = parse_float(ticket["rate_per_hour"], 1200)

    priced = {
        "package": None,
        "lines": [{
            "kind": "addon",
            "label": f"Change request - {ticket['subject']}"[:300],
            "description": f"Raised as ticket {ticket['ref']}.",
            "qty": hours, "unit": "hour",
            "unit_price": rate, "amount": round(hours * rate, 2),
            "internal_cost": round(hours * rate * 0.4, 2),
            "is_recurring": 0, "recurring_period": "", "addon_id": None,
        }],
        "build_total": hours * rate,
        "complexity": 1.0,
        "subtotal": round(hours * rate, 2),
        "surcharge_amount": 0.0,
        "discount_amount": 0.0,
        "taxable_value": round(hours * rate, 2),
        "tax_rate": 0.0,
        "tax_amount": 0.0,
        "total": round(hours * rate, 2),
        "recurring_yearly": 0.0,
        "internal_cost": round(hours * rate * 0.4, 2),
        "margin": round(hours * rate * 0.6, 2),
        "margin_pct": 60.0,
        "extra_pages": 0,
        "milestones": [],
        "delivery_days": 7,
    }
    from core import billing
    priced["tax_rate"] = billing.default_tax_rate()
    priced["tax_amount"] = round(priced["taxable_value"] * priced["tax_rate"] / 100.0, 2)
    priced["total"] = round(priced["taxable_value"] + priced["tax_amount"], 2)

    quote_id = pricing.save_quote(
        {"package_id": package_id, "pages": 0, "rush": False, "complexity": 1.0,
         "annual_prepay": False, "referral": False, "addons": [],
         "note": f"From ticket {ticket['ref']}"},
        priced, client_id=ticket["client_id"], project_id=ticket["project_id"],
        title=f"Change request - {ticket['subject']}"[:200], source="ticket")

    db.update("tickets", ticket_id, {"quote_id": quote_id, "is_change_request": 1,
                                     "is_billable": 1})
    reply(ticket_id, f"Raised change request quote for {hours} hour(s) at "
                     f"{rate:g} per hour.", is_internal=True)
    return quote_id
