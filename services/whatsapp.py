"""WhatsApp, behind one provider interface.

Two implementations, chosen by the `whatsapp.provider` setting:

  ClickToChatProvider  (default, works day one, no account needed)
      Renders the template, logs the message as `ready`, and hands back a wa.me
      deep link. Nothing is sent by the server: the owner taps the link, WhatsApp
      opens with the text already in it, and the log records that it happened.
      Free, no approval process, and no risk of a number being banned.

  CloudApiProvider     (written, off until switched on in Settings)
      Posts to the Meta WhatsApp Cloud API and records the provider message id, so
      delivery receipts and inbound replies arrive on the webhook and update the
      same log rows. Needs a verified Business number and pre-approved templates,
      which is why it is not the default.

Nothing outside this module knows which one is active. `send()` returns the same
Result either way, and callers deal with `result.link` being present or not.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from flask import current_app, url_for

from core import db, settings
from core.util import render_vars, wa_number

PROVIDERS = {
    "click_to_chat": "Click to chat (wa.me links, no account needed)",
    "cloud_api": "Meta WhatsApp Cloud API (verified number, real sending)",
}

STATUS_LABELS = {
    "queued": "Queued",
    "ready": "Ready to send",
    "sent": "Sent",
    "delivered": "Delivered",
    "read": "Read",
    "failed": "Failed",
    "received": "Received",
}

TEMPLATE_CATEGORIES = {
    "first_touch": "First touch",
    "followup": "Follow-up",
    "quote": "Quote and proposal",
    "payment": "Payment and invoice",
    "ticket": "Support",
    "renewal": "Renewal",
    "review": "Review request",
    "greeting": "Greeting",
    "onboarding": "Onboarding",
}


@dataclass
class Result:
    ok: bool
    status: str
    message_id: int | None = None
    link: str = ""
    provider_message_id: str = ""
    error: str = ""
    meta: dict = dc_field(default_factory=dict)


# ── providers ───────────────────────────────────────────────────────────────
class Provider:
    code = "base"
    label = "Base"
    sends_itself = False

    def send(self, *, number: str, body: str, row_id: int, template=None) -> Result:
        raise NotImplementedError


class ClickToChatProvider(Provider):
    code = "click_to_chat"
    label = PROVIDERS["click_to_chat"]
    sends_itself = False

    def send(self, *, number: str, body: str, row_id: int, template=None) -> Result:
        from urllib.parse import quote

        digits = wa_number(number, settings.get("whatsapp.default_country_code") or "91")
        if not digits:
            _mark(row_id, "failed", error="No usable WhatsApp number on that contact.")
            return Result(False, "failed", row_id, error="No usable WhatsApp number.")
        link = f"https://wa.me/{digits}?text={quote(body)}"
        _mark(row_id, "ready")
        return Result(True, "ready", row_id, link=link)


class CloudApiProvider(Provider):
    code = "cloud_api"
    label = PROVIDERS["cloud_api"]
    sends_itself = True

    def send(self, *, number: str, body: str, row_id: int, template=None) -> Result:
        import requests

        token = settings.get("whatsapp.cloud_token") or ""
        phone_id = settings.get("whatsapp.cloud_phone_number_id") or ""
        version = settings.get("whatsapp.cloud_api_version") or "v21.0"
        digits = wa_number(number, settings.get("whatsapp.default_country_code") or "91")

        if not token or not phone_id:
            _mark(row_id, "failed", error="Cloud API is on but the token or phone number id is missing.")
            return Result(False, "failed", row_id, error="Cloud API is not configured.")
        if not digits:
            _mark(row_id, "failed", error="No usable WhatsApp number on that contact.")
            return Result(False, "failed", row_id, error="No usable WhatsApp number.")

        # A free-form text message only reaches a contact inside the 24-hour
        # customer service window. Outside it Meta requires an approved template,
        # so a template row carrying a cloud_template_name is used when it has one.
        cloud_name = (template["cloud_template_name"] if template and
                      "cloud_template_name" in template.keys() else "") or ""
        if cloud_name:
            payload = {
                "messaging_product": "whatsapp",
                "to": digits,
                "type": "template",
                "template": {"name": cloud_name, "language": {"code": "en"},
                             "components": [{"type": "body", "parameters": [
                                 {"type": "text", "text": body[:1024]}]}]},
            }
        else:
            payload = {"messaging_product": "whatsapp", "to": digits,
                       "type": "text", "text": {"preview_url": True, "body": body[:4096]}}

        try:
            response = requests.post(
                f"https://graph.facebook.com/{version}/{phone_id}/messages",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=12,
                verify=current_app.config.get("VERIFY_TLS", True),
            )
            data = response.json() if response.content else {}
        except Exception as exc:  # noqa: BLE001 - any transport failure is a failed send
            _mark(row_id, "failed", error=f"{type(exc).__name__}: {exc}"[:400])
            return Result(False, "failed", row_id, error=str(exc))

        if response.status_code >= 400:
            detail = (data.get("error") or {}).get("message") or response.text[:300]
            _mark(row_id, "failed", error=detail[:400])
            return Result(False, "failed", row_id, error=detail)

        provider_id = ""
        try:
            provider_id = data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError):
            pass
        _mark(row_id, "sent", provider_message_id=provider_id)
        return Result(True, "sent", row_id, provider_message_id=provider_id)


def provider() -> Provider:
    code = settings.get("whatsapp.provider") or "click_to_chat"
    if code == "cloud_api":
        return CloudApiProvider()
    return ClickToChatProvider()


def provider_label() -> str:
    return provider().label


def provider_name() -> str:
    return provider().code


def cloud_api_on() -> bool:
    return settings.get("whatsapp.provider") == "cloud_api"


def send_test(number: str) -> dict:
    """One message to your own number, to prove the credentials before you rely on them."""
    if not cloud_api_on():
        return {"ok": False,
                "error": "Click-to-chat has nothing to test - it opens WhatsApp on your "
                         "machine rather than sending anything itself."}
    brand = settings.get("brand.name") or "Aruka"
    result = provider().send(
        number=number,
        body=f"Test from the {brand} panel. If you are reading this, the Cloud API "
             f"credentials work.",
        row_id=log_row(body="Cloud API credential test", to_number=number, to_name="Self test"),
    )
    return {"ok": result.ok, "status": result.status,
            "error": result.error, "provider_message_id": result.provider_message_id}


# ── logging ─────────────────────────────────────────────────────────────────
def _mark(row_id: int, status: str, *, error: str = "", provider_message_id: str = "") -> None:
    now = db.scalar("SELECT datetime('now')")
    changes = {"status": status}
    if status in ("sent", "ready"):
        changes["sent_at"] = now
    if status == "delivered":
        changes["delivered_at"] = now
    if status == "read":
        changes["read_at"] = now
    if status == "failed":
        changes["failed_at"] = now
        changes["error"] = error[:500]
    if provider_message_id:
        changes["provider_message_id"] = provider_message_id
    db.update("messages", row_id, changes)


def log_row(*, channel: str = "whatsapp", body: str, to_name: str = "", to_number: str = "",
            to_email: str = "", subject: str = "", template_id=None, batch_id: str = "",
            **links) -> int:
    from core.auth import current_user

    user = current_user()
    payload = {
        "channel": channel,
        "direction": "out",
        "template_id": template_id,
        "to_name": to_name[:200],
        "to_number": to_number[:40],
        "to_email": to_email[:200],
        "subject": subject[:300],
        "body": body,
        "status": "queued",
        "provider": provider().code if channel == "whatsapp" else "smtp",
        "user_id": user["id"] if user else None,
        "batch_id": batch_id,
        "queued_at": db.scalar("SELECT datetime('now')"),
    }
    for key in ("lead_id", "client_id", "ticket_id", "invoice_id", "document_id", "recurring_id"):
        payload[key] = links.get(key)
    return db.insert("messages", payload)


# ── the one entry point ─────────────────────────────────────────────────────
def send(*, body: str, number: str, to_name: str = "", template=None,
         batch_id: str = "", **links) -> Result:
    """Log the message, hand it to whichever provider is on, mirror it to any
    linked lead's timeline."""
    row_id = log_row(body=body, to_number=number, to_name=to_name,
                     template_id=(template["id"] if template else None),
                     batch_id=batch_id, **links)
    result = provider().send(number=number, body=body, row_id=row_id, template=template)
    result.message_id = row_id

    if links.get("lead_id"):
        from core import leads
        note = body if len(body) < 600 else body[:597] + "\u2026"
        leads.touch(links["lead_id"], "whatsapp", note,
                    {"message_id": row_id, "status": result.status})
    return result


def render(template_row, values: dict) -> str:
    """Fill a template's variables and append the signature."""
    body = render_vars(template_row["body"], values)
    signature = settings.get("whatsapp.signature") or ""
    if signature:
        body += render_vars(signature, values)
    return body


def context_for(*, lead=None, client=None, invoice=None, ticket=None, document=None,
                project=None, extra: dict | None = None) -> dict:
    """Every variable a template can use, gathered from whatever rows are to hand."""
    from core.util import money, pretty_date

    base = current_app.config.get("PUBLIC_BASE_URL") or ""
    values = {
        "brand": settings.get("brand.name"),
        "sender": settings.get("doc.signatory_name") or settings.get("brand.name"),
        "phone": settings.get("contact.phone"),
        "email": settings.get("contact.email"),
        "site": base or "",
        "upi": settings.get("invoice.upi_id") or "",
        "support_link": (base + "/support/new") if base else "/support/new",
    }
    if lead is not None:
        values.update({
            "name": (lead["name"] or "").split(" ")[0] or lead["name"],
            "full_name": lead["name"],
            "company": lead["company"] or "",
            "service": lead["service_interest"] or "your project",
            "ref": lead["ref"],
        })
    if client is not None:
        values.setdefault("name", (client["contact_name"] or client["name"] or "").split(" ")[0])
        values.update({"company": client["name"], "client_ref": client["ref"]})
    if project is not None:
        values["project"] = project["name"]
    if invoice is not None:
        values.update({
            "invoice_no": invoice["ref"],
            "amount": money(invoice["total"]),
            "balance": money(invoice["balance"]),
            "due_date": pretty_date(invoice["due_on"]),
        })
    if ticket is not None:
        values.update({
            "ticket_ref": ticket["ref"],
            "subject": ticket["subject"],
            "status": ticket["status"].replace("_", " "),
        })
    if document is not None:
        values.update({"document_no": document["ref"], "document_title": document["title"]})
        share = db.one(
            "SELECT * FROM document_shares WHERE document_id = ? AND revoked_at IS NULL "
            "ORDER BY id DESC", (document["id"],))
        if share:
            try:
                path = url_for("public.document_share", token=share["token"])
            except RuntimeError:
                path = f"/d/{share['token']}"
            values["link"] = (base + path) if base else path
    if extra:
        values.update({k: v for k, v in extra.items() if v not in (None, "")})
    return values


# ── inbound and delivery receipts (Cloud API only) ──────────────────────────
def handle_webhook(payload: dict) -> dict:
    """Apply Meta's status and inbound-message callbacks to the message log.

    Delivery receipts are matched on the provider message id we stored at send
    time. Inbound replies are logged as their own rows and attached to a lead or
    client by phone number, so a reply lands on the timeline it belongs to.
    """
    applied = {"statuses": 0, "inbound": 0}
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}

            for status in value.get("statuses") or []:
                row = db.one("SELECT * FROM messages WHERE provider_message_id = ?",
                             (status.get("id") or "",))
                if not row:
                    continue
                state = (status.get("status") or "").lower()
                if state in ("delivered", "read", "sent", "failed"):
                    _mark(row["id"], state,
                          error=str((status.get("errors") or [{}])[0].get("title", ""))[:400])
                    applied["statuses"] += 1

            for message in value.get("messages") or []:
                number = message.get("from") or ""
                text = ((message.get("text") or {}).get("body")
                        or f"[{message.get('type', 'non-text')} message]")
                lead = db.one("SELECT * FROM leads WHERE whatsapp = ? ORDER BY id DESC", (number,))
                client = db.one("SELECT * FROM clients WHERE whatsapp = ? ORDER BY id DESC", (number,))
                row_id = db.insert("messages", {
                    "channel": "whatsapp", "direction": "in",
                    "to_number": number, "body": text, "status": "received",
                    "provider": "cloud_api",
                    "provider_message_id": message.get("id") or "",
                    "lead_id": lead["id"] if lead else None,
                    "client_id": client["id"] if client else None,
                    "sent_at": db.scalar("SELECT datetime('now')"),
                })
                if lead:
                    from core import leads as leads_mod
                    leads_mod.add_event(lead["id"], "whatsapp", f"Reply received: {text[:400]}",
                                        {"message_id": row_id, "direction": "in"})
                applied["inbound"] += 1
    return applied
