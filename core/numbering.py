"""Document and money numbering on the Indian financial year.

A GST invoice series has to be consecutive and unbroken within a financial year,
so the counter is per (series, FY) and is bumped inside a transaction. The same
machinery numbers proposals, receipts and credit notes, which keeps one place to
look when a number has to be explained to an accountant.

    ARK/PRO/2026-27/001     proposal
    ARK/INV/2026-27/014     invoice
    ARK/RCP/2026-27/031     receipt
"""

from __future__ import annotations

from core import db, settings
from core.util import fy_label, parse_date

SERIES = {
    "proposal":    ("PRO", "Proposal"),
    "quotation":   ("QTN", "Quotation"),
    "sow":         ("SOW", "Scope of work"),
    "nda":         ("NDA", "Non-disclosure agreement"),
    "amc":         ("AMC", "Care plan contract"),
    "handover":    ("HND", "Handover note"),
    "invoice":     ("INV", "Invoice"),
    "proforma":    ("PRF", "Proforma invoice"),
    "receipt":     ("RCP", "Receipt"),
    "credit_note": ("CRN", "Credit note"),
    "quote":       ("QT",  "Internal quote"),
    "lead":        ("LD",  "Lead"),
    "client":      ("CL",  "Client"),
    "project":     ("PR",  "Project"),
    "ticket":      ("TKT", "Ticket"),
    "expense":     ("EXP", "Expense"),
}

# Series that must never skip a number, because a tax authority reads them.
STRICT = {"invoice", "proforma", "receipt", "credit_note"}


def series_code(series: str) -> str:
    return SERIES.get(series, (series.upper()[:3], series))[0]


def peek(series: str, on=None) -> str:
    """What the next number would be, without consuming it."""
    fy = fy_label(parse_date(on))
    code = series_code(series)
    prefix = settings.get("invoice.prefix") or "ARK"
    row = db.one("SELECT last_number FROM number_series WHERE series = ? AND fy = ?", (series, fy))
    nxt = (row["last_number"] if row else 0) + 1
    return _format(prefix, code, fy, nxt, series)


def take(series: str, on=None) -> str:
    """Consume and return the next number in the series."""
    fy = fy_label(parse_date(on))
    code = series_code(series)
    prefix = settings.get("invoice.prefix") or "ARK"
    with db.transaction():
        row = db.one("SELECT * FROM number_series WHERE series = ? AND fy = ?", (series, fy))
        if row is None:
            db.insert("number_series", {"series": series, "fy": fy, "prefix": prefix,
                                        "last_number": 1})
            nxt = 1
        else:
            nxt = int(row["last_number"]) + 1
            db.execute(
                "UPDATE number_series SET last_number = ?, prefix = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (nxt, prefix, row["id"]),
            )
    return _format(prefix, code, fy, nxt, series)


def _format(prefix: str, code: str, fy: str, number: int, series: str) -> str:
    if series in ("lead", "client", "project", "ticket", "expense", "quote"):
        # Internal references are read aloud far more often than they are filed,
        # so they stay short and lose the financial year.
        return f"{code}-{number:04d}"
    return f"{prefix}/{code}/{fy}/{number:03d}"


def current(series: str, on=None) -> int:
    fy = fy_label(parse_date(on))
    return int(db.scalar(
        "SELECT last_number FROM number_series WHERE series = ? AND fy = ?", (series, fy), 0))


def all_series():
    return db.query("SELECT * FROM number_series ORDER BY fy DESC, series")


def gaps(series: str, table: str, column: str = "ref", on=None) -> list[str]:
    """Numbers issued but no longer present, which is what an auditor asks about.

    A cancelled invoice keeps its row precisely so this list stays empty; anything
    reported here means a row was deleted rather than cancelled.
    """
    fy = fy_label(parse_date(on))
    last = current(series, on)
    if not last:
        return []
    prefix = settings.get("invoice.prefix") or "ARK"
    code = series_code(series)
    have = {r[column] for r in db.query(f"SELECT {column} FROM {table}")}
    missing = []
    for n in range(1, last + 1):
        ref = _format(prefix, code, fy, n, series)
        if ref not in have:
            missing.append(ref)
    return missing
