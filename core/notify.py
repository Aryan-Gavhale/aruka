"""In-app notifications and the daily digest.

The digest answers one question every morning: what will go wrong today if nobody
touches it. It reads the same functions the dashboard tiles use, so the two can
never disagree.
"""

from __future__ import annotations

from datetime import date

from core import billing, db, leads, settings, tickets
from core.util import add_days, compact_money, parse_int, today_iso


def push(title: str, body: str = "", *, kind: str = "info", url: str = "",
         entity: str = "", entity_id="") -> int:
    return db.insert("notifications", {
        "kind": kind, "title": title[:300], "body": body[:1000], "url": url[:300],
        "entity": entity, "entity_id": str(entity_id or ""),
    })


def unread(limit: int = 20):
    return db.query(
        "SELECT * FROM notifications WHERE is_read = 0 ORDER BY id DESC LIMIT ?", (limit,))


def unread_count() -> int:
    return parse_int(db.scalar("SELECT COUNT(*) FROM notifications WHERE is_read = 0", (), 0))


def recent(limit: int = 60):
    return db.query("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,))


def mark_read(notification_id=None) -> None:
    if notification_id:
        db.update("notifications", notification_id, {"is_read": 1})
    else:
        db.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")


# ── the digest ──────────────────────────────────────────────────────────────
def expiring_assets(within_days: int | None = None):
    days = parse_int(settings.get("ops.expiry_warn_days"), 30) if within_days is None else within_days
    horizon = add_days(date.today(), days).isoformat()
    return db.query(
        "SELECT a.*, c.name AS client_name FROM assets a JOIN clients c ON c.id = a.client_id "
        "WHERE a.is_active = 1 AND a.expires_on IS NOT NULL AND a.expires_on != '' "
        "AND a.expires_on <= ? ORDER BY a.expires_on", (horizon,))


def digest() -> dict:
    """Everything that needs a human today, gathered once."""
    notice_days = parse_int(settings.get("ops.renewal_notice_days"), 21)
    due = leads.followups_due()
    overdue = leads.followups_overdue()
    aging = billing.aging()
    flagged = tickets.at_risk()
    renewals = billing.recurring_due(notice_days)
    expiries = expiring_assets()
    reminders = billing.due_reminders()
    quiet = leads.going_quiet()

    return {
        "date": today_iso(),
        "followups_due": due,
        "followups_overdue": overdue,
        "leads_going_quiet": quiet,
        "receivables": aging["total"],
        "aging": aging,
        "invoices_open": aging["count"],
        "reminders": reminders,
        "tickets_flagged": flagged,
        "renewals": renewals,
        "expiries": expiries,
        "collected_this_month": billing.collected_between(*_month()),
        "spent_this_month": billing.spent_between(*_month()),
        "mrr": billing.mrr(),
        "needs_attention": bool(overdue or flagged or renewals or expiries or reminders),
    }


def _month():
    from core.util import month_bounds
    return month_bounds()


def digest_text() -> str:
    """A plain-text digest for a cron job to mail or print."""
    d = digest()
    brand = settings.get("brand.name")
    lines = [f"{brand} - digest for {d['date']}", "=" * 46, ""]

    def block(title: str, rows, render):
        if not rows:
            return
        lines.append(f"{title} ({len(rows)})")
        for row in rows[:12]:
            lines.append("  - " + render(row))
        if len(rows) > 12:
            lines.append(f"  ... and {len(rows) - 12} more")
        lines.append("")

    block("Follow-ups due", d["followups_due"],
          lambda r: f"{r['name']} ({r['company'] or 'no company'}) - due {r['next_followup_on']}")
    block("Follow-ups overdue", d["followups_overdue"],
          lambda r: f"{r['name']} - was due {r['next_followup_on']}")
    block("Leads going quiet", d["leads_going_quiet"],
          lambda r: f"{r['name']} - no contact since {(r['last_contact_at'] or r['created_at'])[:10]}")
    block("Tickets at risk or breached", d["tickets_flagged"],
          lambda pair: f"{pair[0]['ref']} {pair[0]['subject'][:50]} - {pair[1]['state']}")
    block("Payment reminders to send", d["reminders"],
          lambda r: f"{r['invoice']['ref']} {r['invoice']['client_name']} - "
                    f"{compact_money(r['invoice']['balance'])} ({r['label']})")
    block("Renewals coming up", d["renewals"],
          lambda r: f"{r['label']} for {r['client_name']} - due {r['next_due_on']} "
                    f"({compact_money(r['amount'])})")
    block("Domains, SSL and hosting expiring", d["expiries"],
          lambda r: f"{r['label']} ({r['client_name']}) - expires {r['expires_on']}")

    lines += [
        "Money",
        f"  Collected this month  {compact_money(d['collected_this_month'])}",
        f"  Spent this month      {compact_money(d['spent_this_month'])}",
        f"  Receivables open      {compact_money(d['receivables'])} across {d['invoices_open']} invoices",
        f"  Recurring per month   {compact_money(d['mrr'])}",
        "",
    ]
    if not d["needs_attention"]:
        lines.append("Nothing is on fire. Go build something.")
    return "\n".join(lines)


def sweep() -> dict:
    """Turn today's digest into in-app notifications, skipping anything already
    raised today so running it twice does not double the noise."""
    d = digest()
    made = 0

    def once(kind: str, title: str, body: str, url: str, entity: str, entity_id) -> None:
        nonlocal made
        seen = db.one(
            "SELECT 1 FROM notifications WHERE entity = ? AND entity_id = ? "
            "AND date(created_at) = date('now')", (entity, str(entity_id)))
        if seen:
            return
        push(title, body, kind=kind, url=url, entity=entity, entity_id=entity_id)
        made += 1

    for lead in d["followups_overdue"]:
        once("warn", f"Follow-up overdue: {lead['name']}",
             f"Was due {lead['next_followup_on']}.",
             f"/admin/leads/{lead['id']}", "lead_followup", lead["id"])
    for ticket, state in d["tickets_flagged"]:
        once("error" if state["state"] == "breached" else "warn",
             f"Ticket {state['state'].replace('_', ' ')}: {ticket['ref']}",
             ticket["subject"], f"/admin/tickets/{ticket['id']}", "ticket_sla", ticket["id"])
    for item in d["renewals"]:
        once("info", f"Renewal due: {item['label']}",
             f"{item['client_name']}, due {item['next_due_on']}.",
             f"/admin/recurring", "recurring", item["id"])
    for asset in d["expiries"]:
        once("warn", f"Expiring: {asset['label']}",
             f"{asset['client_name']} - {asset['expires_on']}.",
             f"/admin/clients/{asset['client_id']}", "asset_expiry", asset["id"])
    for row in d["reminders"]:
        invoice = row["invoice"]
        once("warn", f"Payment reminder: {invoice['ref']}",
             f"{invoice['client_name']} owes {compact_money(invoice['balance'])} ({row['label']}).",
             f"/admin/invoices/{invoice['id']}", "invoice_dunning", invoice["id"])
    return {"created": made, "digest": d}
