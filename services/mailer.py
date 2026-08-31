"""SMTP email, with its own template library and a log.

Email is optional throughout Aruka. With no SMTP host configured every call here
returns quietly and writes a skipped row to the log, so a studio that runs entirely
on WhatsApp never sees an error - and can see, in one place, what would have been
sent if email were on.

Nothing here raises on a delivery failure either. A proposal must not fail to be
recorded because a mail server was unreachable; the failure belongs in the log,
where it can be retried, not in the middle of a business action.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from flask import current_app, url_for

from core import db, settings
from core.util import render_vars


def configured() -> bool:
    return bool(current_app.config.get("SMTP_HOST")
                and (current_app.config.get("SMTP_FROM")
                     or current_app.config.get("SMTP_USER")))


def enabled() -> bool:
    return bool(settings.get("email.enabled")) and configured()


def status() -> dict:
    """What the settings screen shows about email, without probing the server."""
    return {
        "configured": configured(),
        "enabled": enabled(),
        "host": current_app.config.get("SMTP_HOST") or "",
        "port": current_app.config.get("SMTP_PORT") or 0,
        "from": _from_address(),
        "tls": bool(current_app.config.get("SMTP_TLS")),
    }


def _from_address() -> str:
    return (current_app.config.get("SMTP_FROM")
            or current_app.config.get("SMTP_USER") or "")


def _log(to_email: str, subject: str, ok: bool, detail: str, message_id=None) -> int:
    return db.insert("email_log", {
        "message_id": message_id,
        "to_email": (to_email or "")[:200],
        "subject": (subject or "")[:300],
        "ok": 1 if ok else 0,
        "detail": (detail or "")[:500],
    })


def send(to_email: str, subject: str, body: str, *, html: str = "",
         reply_to: str = "", attachments=None, message_id=None) -> dict:
    """Send one message. Returns a result dict rather than raising."""
    if not to_email:
        _log(to_email, subject, False, "No address.", message_id)
        return {"ok": False, "skipped": True, "error": "No address."}

    if not enabled():
        reason = ("Email is switched off in Settings." if configured()
                  else "No SMTP host is configured.")
        _log(to_email, subject, False, f"Skipped: {reason}", message_id)
        return {"ok": False, "skipped": True, "error": reason}

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.get("email.from_name")
                                  or settings.get("brand.name") or "Aruka", _from_address()))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    reply = reply_to or settings.get("email.reply_to") or settings.get("contact.email")
    if reply:
        message["Reply-To"] = reply

    signature = settings.get("email.signature") or ""
    message.set_content(body + (f"\n\n{signature}" if signature else ""))
    if html:
        message.add_alternative(html, subtype="html")

    for item in attachments or []:
        message.add_attachment(item["content"],
                              maintype=item.get("maintype", "application"),
                              subtype=item.get("subtype", "pdf"),
                              filename=item.get("filename", "attachment.pdf"))

    host = current_app.config["SMTP_HOST"]
    port = int(current_app.config.get("SMTP_PORT") or 587)
    user = current_app.config.get("SMTP_USER") or ""
    password = current_app.config.get("SMTP_PASSWORD") or ""
    use_tls = bool(current_app.config.get("SMTP_TLS"))
    verify = bool(current_app.config.get("VERIFY_TLS", True))

    context = ssl.create_default_context()
    if not verify:
        # Only for a self-signed relay on a private network, and the README says so.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
        with server:
            if port != 465 and use_tls:
                server.starttls(context=context)
            if user:
                server.login(user, password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        current_app.logger.warning("Email to %s failed: %s", to_email, exc)
        _log(to_email, subject, False, str(exc), message_id)
        return {"ok": False, "skipped": False, "error": str(exc)}

    _log(to_email, subject, True, "Sent.", message_id)
    return {"ok": True, "skipped": False, "error": ""}


# ── templates ───────────────────────────────────────────────────────────────
def template(code: str):
    return db.one("SELECT * FROM message_templates WHERE code = ? AND channel = 'email' "
                  "AND is_active = 1", (code,))


def send_template(code: str, to_email: str, values: dict, *, attachments=None,
                  **links) -> dict:
    """Send a library template, logging it in `messages` as well as `email_log`
    so one screen shows every outbound message whatever the channel."""
    row = template(code)
    if not row:
        return {"ok": False, "skipped": True, "error": f"No email template coded {code}."}

    merged = {**base_values(), **values}
    subject = render_vars(row["subject"] or "", merged)
    body = render_vars(row["body"] or "", merged)

    from services import whatsapp
    message_id = whatsapp.log_row(channel="email", body=body, subject=subject,
                                  to_email=to_email,
                                  to_name=str(values.get("name") or ""),
                                  template_id=row["id"], **links)
    result = send(to_email, subject, body, attachments=attachments, message_id=message_id)
    db.update("messages", message_id, {
        "status": "sent" if result["ok"] else "failed",
        "error": result.get("error", "")[:500],
        "sent_at": db.scalar("SELECT datetime('now')") if result["ok"] else None,
        "failed_at": None if result["ok"] else db.scalar("SELECT datetime('now')"),
    })
    return result


def base_values() -> dict:
    """Placeholders every template can rely on, whoever it is going to."""
    try:
        site = url_for("public.home", _external=True)
    except RuntimeError:
        site = current_app.config.get("PUBLIC_BASE_URL") or ""
    return {
        "brand": settings.get("brand.name") or "Aruka",
        "sender": settings.get("doc.signatory_name") or settings.get("brand.name") or "Aruka",
        "phone": settings.get("contact.phone") or "",
        "email": settings.get("contact.email") or "",
        "site": site.rstrip("/"),
        "upi": settings.get("invoice.upi_id") or "",
    }
