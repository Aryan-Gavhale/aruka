"""Small helpers shared by the public site, the client portal and the admin panel."""

from __future__ import annotations

import json
import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    text = _SLUG_STRIP.sub("-", text.lower()).strip("-")
    return text or fallback


def unique_slug(value: str, exists) -> str:
    """`exists(slug) -> bool` decides whether a candidate is taken."""
    base = slugify(value)
    candidate = base
    n = 2
    while exists(candidate):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def ref_code(prefix: str, length: int = 5) -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    tail = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}-{tail}"


def token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def numeric_code(digits: int = 6) -> str:
    """A one-time code a client can read over the phone."""
    return "".join(secrets.choice("0123456789") for _ in range(digits))


def client_ip() -> str:
    """The address to rate-limit and log against.

    X-Forwarded-For is only read when TRUSTED_PROXIES says a proxy really is in
    front of us, because anything self-reported by the caller can be rotated per
    request, which would make every per-IP limit here decorative.
    """
    from flask import current_app, request

    remote = request.remote_addr or ""
    hops = int(current_app.config.get("TRUSTED_PROXIES", 0) or 0)
    if hops <= 0:
        return remote

    chain = [p.strip() for p in (request.headers.get("X-Forwarded-For") or "").split(",") if p.strip()]
    if not chain:
        return remote
    # The rightmost entries were added by our own proxies; step back over them.
    index = max(0, len(chain) - hops)
    return chain[index] if index < len(chain) else chain[0]


_CSV_TRIGGER = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value) -> str:
    """Defuse spreadsheet formula injection.

    Lead names and messages come from anonymous visitors and end up in a file
    opened in Excel, where a leading = + - @ is executed. Prefixing with an
    apostrophe makes the cell text, which is what it always was.
    """
    text = "" if value is None else str(value)
    if text[:1] in _CSV_TRIGGER:
        return "'" + text
    return text


def inr(value, decimals: int = 0) -> str:
    """Format a number the Indian way: 12,34,567."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    negative = amount < 0
    amount = abs(amount)
    whole = int(amount)
    frac = amount - whole
    digits = str(whole)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        digits = f"{head},{tail}"
    out = digits
    if decimals:
        out = f"{digits}.{int(round(frac * (10 ** decimals))):0{decimals}d}"
    return ("-" if negative else "") + out


def money(value, decimals: int = 0) -> str:
    return "\u20b9" + inr(value, decimals)


def money2(value) -> str:
    return money(value, 2)


def compact_money(value) -> str:
    """1.2L / 24.5K, for dashboard tiles where the full number does not fit."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 10_000_000:
        return f"{sign}\u20b9{amount / 10_000_000:.2f}Cr".replace(".00", "")
    if amount >= 100_000:
        return f"{sign}\u20b9{amount / 100_000:.2f}L".replace(".00", "")
    if amount >= 1_000:
        return f"{sign}\u20b9{amount / 1_000:.1f}K".replace(".0", "")
    return f"{sign}\u20b9{int(amount)}"


def parse_float(value, default=0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").replace("\u20b9", "").strip())
    except (TypeError, ValueError):
        return default


def parse_int(value, default=0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def parse_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "on", "yes", "y"}


def load_json(raw, default=None):
    if isinstance(raw, (dict, list)):
        return raw
    if not raw:
        return default if default is not None else {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default if default is not None else {}


def dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_date(value, default=None):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value).strip()[:10], fmt).date()
        except (ValueError, TypeError, AttributeError):
            continue
    return default


def parse_datetime(value, default=None):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip()[:19], fmt)
        except (ValueError, TypeError, AttributeError):
            continue
    return default


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    # clamp to the last valid day of the target month
    day = start.day
    while day > 28:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return date(year, month, day)


def add_days(start: date, days: int) -> date:
    return start + timedelta(days=days)


def add_minutes(minutes: int, start: datetime | None = None) -> str:
    """A SQLite-shaped timestamp `minutes` from now, for short-lived tokens."""
    base = start or datetime.now()
    return (base + timedelta(minutes=int(minutes))).strftime("%Y-%m-%d %H:%M:%S")


def pretty_date(value, fmt: str = "%d %b %Y") -> str:
    parsed = parse_date(value)
    if parsed:
        return parsed.strftime(fmt)
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").strftime(fmt)
    except (ValueError, TypeError):
        return str(value or "")


def pretty_datetime(value, fmt: str = "%d %b %Y, %H:%M") -> str:
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").strftime(fmt)
    except (ValueError, TypeError):
        return pretty_date(value, fmt)


def time_ago(value) -> str:
    try:
        stamp = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        parsed = parse_date(value)
        if not parsed:
            return ""
        stamp = datetime.combine(parsed, datetime.min.time())
    delta = datetime.now() - stamp
    seconds = int(delta.total_seconds())
    if seconds < 0:
        seconds = abs(seconds)
        prefix, suffix = "in ", ""
    else:
        prefix, suffix = "", " ago"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{prefix}{mins} min{suffix}"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{prefix}{hours} hour{'s' if hours > 1 else ''}{suffix}"
    days = seconds // 86400
    if days < 30:
        return f"{prefix}{days} day{'s' if days > 1 else ''}{suffix}"
    months = days // 30
    if months < 12:
        return f"{prefix}{months} month{'s' if months > 1 else ''}{suffix}"
    years = days // 365
    return f"{prefix}{years} year{'s' if years > 1 else ''}{suffix}"


def days_until(value) -> int | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    return (parsed - date.today()).days


def hours_between(start, end=None) -> float:
    """Elapsed hours between two timestamps; used by the ticket SLA clock."""
    a = parse_datetime(start)
    if not a:
        return 0.0
    b = parse_datetime(end) if end else datetime.now()
    if not b:
        b = datetime.now()
    return (b - a).total_seconds() / 3600.0


def week_bounds(reference: date | None = None) -> tuple[str, str]:
    ref = reference or date.today()
    start = ref - timedelta(days=ref.weekday())
    return start.isoformat(), (start + timedelta(days=7)).isoformat()


def month_bounds(reference: date | None = None) -> tuple[str, str]:
    ref = reference or date.today()
    start = ref.replace(day=1)
    return start.isoformat(), add_months(start, 1).isoformat()


# ── Indian financial year ───────────────────────────────────────────────────
def _as_date(reference) -> date:
    """Accept a date, a datetime, an ISO string or nothing.

    Every caller of the FY helpers has one of those and none of them should have to
    remember which, least of all a template.
    """
    if reference is None:
        return date.today()
    return parse_date(reference) or date.today()


def fy_bounds(reference=None) -> tuple[str, str]:
    """April 1 to the following March 31, exclusive end."""
    year = fy_start_year(reference)
    return date(year, 4, 1).isoformat(), date(year + 1, 4, 1).isoformat()


def fy_label(reference=None) -> str:
    """The 2026-27 form used on Indian invoice number series."""
    year = fy_start_year(reference)
    return f"{year}-{str(year + 1)[-2:]}"


def fy_start_year(reference=None) -> int:
    ref = _as_date(reference)
    return ref.year if ref.month >= 4 else ref.year - 1


def fy_months(start_year: int) -> list[tuple[str, str]]:
    """The twelve (iso-first-of-month, short label) pairs of one financial year."""
    out = []
    cursor = date(start_year, 4, 1)
    for _ in range(12):
        out.append((cursor.isoformat(), cursor.strftime("%b %y")))
        cursor = add_months(cursor, 1)
    return out


def quarter_of(value) -> str:
    """Indian FY quarter: Apr-Jun is Q1."""
    parsed = parse_date(value)
    if not parsed:
        return ""
    index = (parsed.month - 4) % 12 // 3 + 1
    return f"Q{index}"


def clean_phone(value: str) -> str:
    return re.sub(r"[^\d+]", "", value or "")


def wa_number(value: str, default_cc: str = "91") -> str:
    """Digits only with a country code, which is what wa.me links want."""
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    if len(digits) == 10:
        return default_cc + digits
    if digits.startswith("0") and len(digits) == 11:
        return default_cc + digits[1:]
    return digits


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match((value or "").strip()))


def valid_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return 8 <= len(digits) <= 15


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def valid_gstin(value: str) -> bool:
    return bool(GSTIN_RE.match((value or "").strip().upper()))


def gstin_state_code(value: str) -> str:
    text = (value or "").strip()
    return text[:2] if len(text) >= 2 and text[:2].isdigit() else ""


def truncate(value: str, length: int = 120) -> str:
    text = (value or "").strip()
    if len(text) <= length:
        return text
    return text[: length - 1].rstrip() + "\u2026"


def initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def split_list(value: str, sep: str = ",") -> list[str]:
    return [p.strip() for p in (value or "").split(sep) if p.strip()]


def split_lines(value: str) -> list[str]:
    """One entry per line, with any leading bullet character dropped.

    Used wherever a settings field holds a list. Accepting a pasted bulleted list
    without complaining is worth the two characters of stripping.
    """
    out = []
    for line in str(value or "").splitlines():
        cleaned = line.strip().lstrip("-*\u2022").strip()
        if cleaned:
            out.append(cleaned)
    return out


def pct(part, whole, decimals: int = 0) -> float:
    try:
        whole = float(whole or 0)
        if not whole:
            return 0.0
        return round(float(part or 0) * 100.0 / whole, decimals)
    except (TypeError, ValueError):
        return 0.0


def render_vars(template: str, values: dict) -> str:
    """Replace {{ key }} placeholders. Unknown keys are left visible on purpose,
    so a half-filled message is obvious before it is sent rather than after."""
    text = str(template or "")

    def swap(match):
        key = match.group(1).strip()
        if key in values and values[key] not in (None, ""):
            return str(values[key])
        return match.group(0)

    return re.sub(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", swap, text)


def template_vars(template: str) -> list[str]:
    return sorted({m.strip() for m in re.findall(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", str(template or ""))})


def amount_in_words(value) -> str:
    """Indian numbering words for the invoice PDF, which conventionally
    restates the total in words to make tampering obvious."""
    ones = ("zero one two three four five six seven eight nine ten eleven twelve "
            "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

    def under_hundred(n: int) -> str:
        if n < 20:
            return ones[n]
        return tens[n // 10] + ("-" + ones[n % 10] if n % 10 else "")

    def under_thousand(n: int) -> str:
        if n < 100:
            return under_hundred(n)
        head = ones[n // 100] + " hundred"
        return head + (" and " + under_hundred(n % 100) if n % 100 else "")

    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return ""
    negative = amount < 0
    amount = abs(amount)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    if paise == 100:
        rupees, paise = rupees + 1, 0

    if rupees == 0:
        words = "zero"
    else:
        chunks = []
        crore, rupees_rest = divmod(rupees, 10_000_000)
        lakh, rupees_rest = divmod(rupees_rest, 100_000)
        thousand, rest = divmod(rupees_rest, 1_000)
        if crore:
            chunks.append(under_thousand(crore) + " crore")
        if lakh:
            chunks.append(under_thousand(lakh) + " lakh")
        if thousand:
            chunks.append(under_thousand(thousand) + " thousand")
        if rest:
            chunks.append(under_thousand(rest))
        words = " ".join(chunks)

    out = f"Rupees {words}"
    if paise:
        out += f" and {under_hundred(paise)} paise"
    out += " only"
    if negative:
        out = "Minus " + out
    return out[0].upper() + out[1:]
