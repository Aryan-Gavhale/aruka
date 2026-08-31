"""Authentication, roles, CSRF and login throttling - no third-party auth libs.

Aruka is a single-owner tool. The roles below exist so a second pair of hands can
be given the day-to-day work later without also handing over pricing, money and
settings; on a fresh install there is exactly one owner account.

Roles
  owner    everything, including users, settings and the danger zone
  admin    everything except user management
  staff    leads, messages, tickets and delivery - no pricing, money or settings
"""

from __future__ import annotations

import hmac
import secrets
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core import db

ROLES = ("owner", "admin", "staff")
ROLE_LABELS = {
    "owner": "Owner",
    "admin": "Administrator",
    "staff": "Team",
}

# What each role may reach; checked by require_role.
#
# "money" is the ledger policy layer - editing an issued invoice, voiding a
# receipt, writing an amount off - kept apart from "billing", which is the
# day-to-day of raising an invoice and recording a payment against it. Pricing
# and internal cost margins are deliberately out of reach of staff.
AREAS = (
    "content", "media", "leads", "messages", "tickets", "pricing", "documents",
    "billing", "money", "projects", "vault", "analytics", "settings", "users", "audit",
)

PERMISSIONS = {
    "owner": set(AREAS),
    "admin": set(AREAS) - {"users"},
    "staff": {"leads", "messages", "tickets", "projects", "media"},
}

MAX_ATTEMPTS = 8            # per address
MAX_ATTEMPTS_EMAIL = 12     # per account, across addresses
ATTEMPT_WINDOW_MIN = 15

# Compared against when the email is unknown, so a missing account costs the same
# time as a wrong password and cannot be told apart by a stopwatch.
_DUMMY_HASH = generate_password_hash("not-a-real-password", method="pbkdf2:sha256:260000")


# ── users ───────────────────────────────────────────────────────────────────
def hash_password(raw: str) -> str:
    return generate_password_hash(raw, method="pbkdf2:sha256:260000")


def create_user(email: str, name: str, password: str, role: str = "staff") -> int:
    return db.insert(
        "users",
        {
            "email": email.strip().lower(),
            "name": name.strip(),
            "password_hash": hash_password(password),
            "role": role if role in ROLES else "staff",
            "is_active": 1,
        },
    )


def find_user(email: str):
    return db.one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))


def current_user():
    """The signed-in user, or None.

    None is also the honest answer outside a request - a CLI command, the digest,
    a scheduled job. Those still write audit rows, and they should record "system"
    rather than crash on a session that was never there.
    """
    try:
        if "user" not in g:
            g.user = None
            uid = session.get("uid")
            if uid:
                g.user = db.one("SELECT * FROM users WHERE id = ? AND is_active = 1", (uid,))
        return g.user
    except RuntimeError:
        return None


def can(area: str) -> bool:
    """True when the signed-in user may reach an area.

    "owner" is accepted as an area name so a route that must never be delegated -
    deleting money records, the danger zone, the credential vault key - can say
    require_role("owner") and read the same as every other gate.
    """
    user = current_user()
    if not user:
        return False
    if area == "owner":
        return user["role"] == "owner"
    return area in PERMISSIONS.get(user["role"], set())


def is_owner() -> bool:
    user = current_user()
    return bool(user and user["role"] == "owner")


# ── throttling ──────────────────────────────────────────────────────────────
def recent_failures(ip: str) -> int:
    return int(
        db.scalar(
            "SELECT COUNT(*) FROM login_attempts WHERE ip = ? AND ok = 0 "
            f"AND created_at > datetime('now', '-{ATTEMPT_WINDOW_MIN} minutes')",
            (ip,),
            0,
        )
    )


def recent_failures_for(email: str) -> int:
    """Counted separately so a distributed attempt on one account still trips."""
    return int(
        db.scalar(
            "SELECT COUNT(*) FROM login_attempts WHERE email = ? AND ok = 0 "
            f"AND created_at > datetime('now', '-{ATTEMPT_WINDOW_MIN} minutes')",
            (email.strip().lower()[:120],),
            0,
        )
    )


def record_attempt(ip: str, email: str, ok: bool) -> None:
    db.insert("login_attempts", {"ip": ip, "email": email[:120], "ok": 1 if ok else 0})
    db.execute("DELETE FROM login_attempts WHERE created_at < datetime('now', '-2 days')")


def attempt_login(email: str, password: str, ip: str):
    """Returns (user_row, error_message)."""
    if recent_failures(ip) >= MAX_ATTEMPTS:
        return None, "Too many attempts from this address. Try again in 15 minutes."
    if recent_failures_for(email) >= MAX_ATTEMPTS_EMAIL:
        return None, "Too many attempts on that account. Try again in 15 minutes."

    user = find_user(email)
    if not user or not user["is_active"]:
        check_password_hash(_DUMMY_HASH, password)   # keep the timing flat
        record_attempt(ip, email, False)
        return None, "Those details do not match an active account."
    if not check_password_hash(user["password_hash"], password):
        record_attempt(ip, email, False)
        return None, "Those details do not match an active account."

    record_attempt(ip, email, True)
    session.clear()
    session["uid"] = user["id"]
    session["csrf"] = secrets.token_urlsafe(32)
    session.permanent = True
    db.update("users", user["id"], {"last_login_at": db.scalar("SELECT datetime('now')")})
    return user, None


def logout() -> None:
    session.clear()


# ── CSRF ────────────────────────────────────────────────────────────────────
def csrf_token() -> str:
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


def csrf_ok() -> bool:
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    return bool(sent) and hmac.compare_digest(sent, session.get("csrf", ""))


def verify_csrf() -> None:
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not csrf_ok():
        abort(400, "The form expired or the security token did not match. Please try again.")


# ── decorators ──────────────────────────────────────────────────────────────
def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("admin.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapper


def require_role(*areas: str):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user():
                return redirect(url_for("admin.login", next=request.full_path))
            if areas and not any(can(a) for a in areas):
                flash("Your account does not have access to that area.", "error")
                return redirect(url_for("admin.dashboard"))
            return view(*args, **kwargs)

        return wrapper

    return decorator


def bootstrap_owner(app) -> None:
    """Create the first owner account if the table is empty.

    With no password configured one is generated and written to db/first-login.txt
    rather than falling back to a default that is the same in every copy of this
    codebase, which anyone reading the source could use.
    """
    from pathlib import Path

    with app.app_context():
        if int(db.scalar("SELECT COUNT(*) FROM users", (), 0)):
            return
        email = app.config.get("OWNER_EMAIL") or "owner@example.com"
        name = app.config.get("OWNER_NAME") or "Aruka Owner"
        password = app.config.get("OWNER_PASSWORD") or ""
        generated = not password
        if generated:
            password = secrets.token_urlsafe(12)

        create_user(email, name, password, "owner")
        if generated:
            note = Path(app.root_path) / "db" / "first-login.txt"
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text(f"{email}\n{password}\n", encoding="utf-8")
            print("\n  First login")
            print(f"    {email}")
            print(f"    {password}")
            print(f"  Also written to {note.relative_to(Path(app.root_path))}. "
                  "Change it and delete that file.\n")
        app.logger.warning("Created first owner account: %s", email)
