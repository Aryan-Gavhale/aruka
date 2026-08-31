"""Inbound callbacks. Only WhatsApp Cloud API for now.

Kept apart from the public site because these routes are machine-to-machine: no
CSRF token, no session, and a signature check instead. They are also exempt from
the site's CSP because nothing is rendered.
"""

from __future__ import annotations

import hashlib
import hmac

from flask import Blueprint, current_app, request

from core import settings
from services import whatsapp

bp = Blueprint("webhooks", __name__, url_prefix="/hooks")


@bp.route("/whatsapp", methods=["GET"])
def whatsapp_verify():
    """Meta's subscription handshake: echo the challenge if the token matches."""
    expected = settings.get("whatsapp.cloud_verify_token") or ""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge") or ""
    if mode == "subscribe" and expected and hmac.compare_digest(token or "", expected):
        return challenge, 200, {"Content-Type": "text/plain"}
    return "", 403


@bp.route("/whatsapp", methods=["POST"])
def whatsapp_events():
    """Delivery receipts and inbound replies.

    The app secret signature is verified when one is configured. Without it we
    would be accepting anyone's claim that a message was read, so a missing secret
    means the payload is refused rather than trusted.
    """
    if not whatsapp.cloud_api_on():
        return {"ok": False, "reason": "cloud_api_off"}, 200

    secret = settings.get("whatsapp.cloud_app_secret") or ""
    signature = request.headers.get("X-Hub-Signature-256") or ""
    body = request.get_data() or b""

    if secret:
        digest = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, signature):
            current_app.logger.warning("WhatsApp webhook rejected: bad signature.")
            return {"ok": False, "reason": "bad_signature"}, 403
    elif not current_app.config.get("ALLOW_UNSIGNED_WEBHOOKS"):
        current_app.logger.warning("WhatsApp webhook rejected: no app secret configured.")
        return {"ok": False, "reason": "no_app_secret"}, 403

    payload = request.get_json(silent=True) or {}
    try:
        applied = whatsapp.handle_webhook(payload)
    except Exception:  # noqa: BLE001 - never make Meta retry a payload we cannot parse
        current_app.logger.exception("WhatsApp webhook could not be applied.")
        return {"ok": True, "applied": {}}, 200
    return {"ok": True, "applied": applied}, 200
