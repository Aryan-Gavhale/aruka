"""Symmetric encryption for the credential vault.

This is deliberately small and honest about what it is. The key lives outside the
database in db/vault.key (or config.json), so a stolen .db file alone does not
hand over client passwords. It is AES-free by design - no third-party crypto
dependency - using HMAC-SHA256 in counter mode for the keystream plus a separate
HMAC tag, which is an encrypt-then-MAC construction over the standard library.

What this does NOT protect against: anyone who can read both the database and the
key file, which includes anyone with shell access to the server. The README says
so plainly and recommends storing only "where the credential lives" for anything
that would be catastrophic to lose. A password manager is the right tool for
secrets; this exists so the vault does not keep them in plain sight.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from pathlib import Path

from flask import current_app

MAGIC = b"ARKV1"


def _root_key() -> bytes:
    configured = (current_app.config.get("VAULT_KEY") or "").strip()
    if configured:
        return hashlib.sha256(configured.encode("utf-8")).digest()

    path = Path(current_app.root_path) / "db" / "vault.key"
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return hashlib.sha256(existing.encode("utf-8")).digest()
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = base64.urlsafe_b64encode(os.urandom(48)).decode("ascii")
    path.write_text(generated, encoding="utf-8")
    current_app.logger.warning("Generated a new vault key in db/vault.key - back it up. "
                               "Losing it makes stored secrets unreadable.")
    return hashlib.sha256(generated.encode("utf-8")).digest()


def _subkeys(salt: bytes) -> tuple[bytes, bytes]:
    """Separate keys for the keystream and the tag, both bound to this record's salt."""
    root = _root_key()
    enc = hmac.new(root, b"enc" + salt, hashlib.sha256).digest()
    mac = hmac.new(root, b"mac" + salt, hashlib.sha256).digest()
    return enc, mac


def _keystream(key: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def encrypt(plaintext: str) -> str:
    """Returns an opaque base64 string safe to keep in a TEXT column."""
    if plaintext in (None, ""):
        return ""
    data = str(plaintext).encode("utf-8")
    salt = os.urandom(16)
    enc_key, mac_key = _subkeys(salt)
    cipher = bytes(a ^ b for a, b in zip(data, _keystream(enc_key, len(data))))
    tag = hmac.new(mac_key, MAGIC + salt + cipher, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(MAGIC + salt + tag + cipher).decode("ascii")


def decrypt(token: str) -> str:
    """Returns '' for anything that does not verify, rather than raising, so one
    unreadable row cannot take down the whole vault screen."""
    if not token:
        return ""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
    except (ValueError, TypeError):
        return ""
    if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 32:
        return ""
    body = raw[len(MAGIC):]
    salt, tag, cipher = body[:16], body[16:32], body[32:]
    enc_key, mac_key = _subkeys(salt)
    expected = hmac.new(mac_key, MAGIC + salt + cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected):
        return ""
    try:
        return bytes(a ^ b for a, b in zip(cipher, _keystream(enc_key, len(cipher)))).decode("utf-8")
    except UnicodeDecodeError:
        return ""


def available() -> bool:
    """Whether a vault key is already in place.

    Called before the vault screen offers to store anything, so the warning about
    backing the key up appears before the first secret goes in rather than after.
    """
    if (current_app.config.get("VAULT_KEY") or "").strip():
        return True
    return (Path(current_app.root_path) / "db" / "vault.key").exists()


def mask(secret: str) -> str:
    """What the vault list shows: enough to recognise, not enough to use."""
    text = str(secret or "")
    if not text:
        return "-"
    if len(text) <= 4:
        return "\u2022" * len(text)
    return text[:2] + "\u2022" * min(8, len(text) - 4) + text[-2:]
