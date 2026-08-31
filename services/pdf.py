"""The PDF layout kit, on ReportLab.

Everything a client ever receives on paper comes through here: proposals, scopes
of work, AMCs, invoices, receipts and credit notes. One module so the letterhead,
the fonts, the footer and the signature block are defined once and cannot drift
apart between document types.

ReportLab rather than a HTML-to-PDF converter because it is pure Python. No
wkhtmltopdf binary, no Chromium download, no system libraries - `pip install`
and it works the same on the Windows machine this is written on and on whatever
Linux box it ends up on.

Public entry points:
    proposal_pdf(document)      -> bytes
    invoice_pdf(invoice)        -> bytes
    receipt_pdf(payment)        -> bytes
    credit_note_pdf(note)       -> bytes
"""

from __future__ import annotations

import io
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

from core import db, settings
from core.util import (amount_in_words, inr, load_json, parse_float, pretty_date,
                       render_vars, today_iso)

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
HEADER_H = 26 * mm
FOOTER_H = 16 * mm


# ── palette and text styles ─────────────────────────────────────────────────
def _palette() -> dict:
    """Read the brand colours out of Settings so a PDF matches the website."""
    def pick(key: str, fallback: str):
        value = (settings.get(key) or "").strip()
        try:
            return colors.HexColor(value) if value.startswith("#") else colors.HexColor(fallback)
        except (ValueError, AttributeError):
            return colors.HexColor(fallback)

    return {
        "brand": pick("theme.accent", "#7C5CFF"),
        "ink": colors.HexColor("#14161C"),
        "body": colors.HexColor("#33384A"),
        "mute": colors.HexColor("#767C90"),
        "line": colors.HexColor("#DDE0EA"),
        "wash": colors.HexColor("#F5F6FA"),
        "good": colors.HexColor("#1B8A5A"),
        "bad": colors.HexColor("#C0392B"),
    }


def _styles(palette: dict) -> dict:
    base = getSampleStyleSheet()
    out = {}

    def add(name, **kwargs):
        out[name] = ParagraphStyle(name, parent=base["Normal"], **kwargs)

    add("body", fontName="Helvetica", fontSize=9.2, leading=13.4, textColor=palette["body"])
    add("body_j", fontName="Helvetica", fontSize=9.2, leading=13.4,
        textColor=palette["body"], alignment=TA_JUSTIFY)
    add("small", fontName="Helvetica", fontSize=7.6, leading=10.4, textColor=palette["mute"])
    add("small_r", fontName="Helvetica", fontSize=7.6, leading=10.4,
        textColor=palette["mute"], alignment=TA_RIGHT)
    add("label", fontName="Helvetica-Bold", fontSize=7, leading=9.5,
        textColor=palette["mute"], spaceAfter=1.4)
    add("h1", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=palette["ink"],
        spaceAfter=4)
    add("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=palette["ink"],
        spaceBefore=11, spaceAfter=4)
    add("h3", fontName="Helvetica-Bold", fontSize=9.8, leading=13, textColor=palette["ink"],
        spaceBefore=7, spaceAfter=2)
    add("kicker", fontName="Helvetica-Bold", fontSize=8, leading=11,
        textColor=palette["brand"], spaceAfter=3)
    add("cell", fontName="Helvetica", fontSize=8.6, leading=11.6, textColor=palette["body"])
    add("cell_b", fontName="Helvetica-Bold", fontSize=8.6, leading=11.6, textColor=palette["ink"])
    add("cell_r", fontName="Helvetica", fontSize=8.6, leading=11.6,
        textColor=palette["body"], alignment=TA_RIGHT)
    add("cell_rb", fontName="Helvetica-Bold", fontSize=8.6, leading=11.6,
        textColor=palette["ink"], alignment=TA_RIGHT)
    add("clause", fontName="Helvetica", fontSize=8.4, leading=12.2,
        textColor=palette["body"], alignment=TA_JUSTIFY, spaceAfter=5)
    add("clause_h", fontName="Helvetica-Bold", fontSize=8.8, leading=12,
        textColor=palette["ink"], spaceBefore=6, spaceAfter=1.5)
    add("centre", fontName="Helvetica", fontSize=9, leading=13,
        textColor=palette["body"], alignment=TA_CENTER)
    add("total", fontName="Helvetica-Bold", fontSize=13, leading=17,
        textColor=palette["ink"], alignment=TA_RIGHT)
    return out


def esc(value) -> str:
    """ReportLab's Paragraph parses a mini-HTML, so client-supplied text has to be
    escaped or an ampersand in a company name aborts the whole render."""
    text = "" if value is None else str(value)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def rupees(value) -> str:
    """Helvetica has no rupee glyph, so the PDF says Rs. rather than a black box."""
    return "Rs. " + inr(value, 2)


# ── the page frame ──────────────────────────────────────────────────────────
class _Doc(BaseDocTemplate):
    """Letterhead, footer, page numbers and the optional DRAFT wash."""

    def __init__(self, buffer, *, title: str, watermark: str = "", **kwargs):
        super().__init__(buffer, pagesize=A4, title=title,
                         author=settings.get("brand.name") or "Aruka",
                         subject=title, creator="Aruka",
                         leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=MARGIN, bottomMargin=MARGIN, **kwargs)
        self.palette = _palette()
        self.watermark = watermark
        self.doc_title = title

        frame = Frame(MARGIN, MARGIN + FOOTER_H,
                      PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN - HEADER_H - FOOTER_H + 6 * mm,
                      id="body", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=self._furniture)])

    def _furniture(self, canvas, doc):
        palette = self.palette
        canvas.saveState()

        if self.watermark:
            canvas.saveState()
            canvas.translate(PAGE_W / 2, PAGE_H / 2)
            canvas.rotate(38)
            canvas.setFont("Helvetica-Bold", 74)
            canvas.setFillColor(colors.HexColor("#EEF0F6"))
            canvas.drawCentredString(0, 0, self.watermark)
            canvas.restoreState()

        top = PAGE_H - MARGIN
        brand = settings.get("brand.name") or "Aruka"

        canvas.setFillColor(palette["brand"])
        canvas.roundRect(MARGIN, top - 9 * mm, 9 * mm, 9 * mm, 2.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawCentredString(MARGIN + 4.5 * mm, top - 6.4 * mm, brand[:1].upper())

        canvas.setFillColor(palette["ink"])
        canvas.setFont("Helvetica-Bold", 12.5)
        canvas.drawString(MARGIN + 12 * mm, top - 4.4 * mm, brand)
        canvas.setFillColor(palette["mute"])
        canvas.setFont("Helvetica", 7.4)
        canvas.drawString(MARGIN + 12 * mm, top - 8.2 * mm,
                          settings.get("brand.tagline") or "")

        right = PAGE_W - MARGIN
        lines = [
            settings.get("contact.email") or "",
            settings.get("contact.phone") or "",
            settings.get("contact.website") or "",
        ]
        gstin = settings.get("gst.gstin") or ""
        if gstin and settings.gst_on():
            lines.append("GSTIN " + gstin)
        pan = settings.get("tax.pan") or ""
        if pan:
            lines.append("PAN " + pan)
        canvas.setFont("Helvetica", 7.2)
        for index, line in enumerate([l for l in lines if l][:4]):
            canvas.drawRightString(right, top - 4.4 * mm - index * 3.3 * mm, line)

        canvas.setStrokeColor(palette["line"])
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, top - HEADER_H + 6 * mm, right, top - HEADER_H + 6 * mm)

        canvas.line(MARGIN, MARGIN + FOOTER_H - 2 * mm, right, MARGIN + FOOTER_H - 2 * mm)
        canvas.setFillColor(palette["mute"])
        canvas.setFont("Helvetica", 7)
        address = " ".join((settings.get("contact.address") or "").split())
        canvas.drawString(MARGIN, MARGIN + FOOTER_H - 6.5 * mm, address[:120])
        canvas.drawRightString(right, MARGIN + FOOTER_H - 6.5 * mm,
                               f"{self.doc_title}  \u00b7  Page {doc.page}")
        canvas.restoreState()


def _build(story, *, title: str, watermark: str = "") -> bytes:
    buffer = io.BytesIO()
    doc = _Doc(buffer, title=title, watermark=watermark)
    doc.build(story)
    return buffer.getvalue()


# ── reusable blocks ─────────────────────────────────────────────────────────
def _kv_table(rows, styles, palette, widths=(30 * mm, 52 * mm)):
    data = [[Paragraph(esc(k), styles["label"]), Paragraph(esc(v), styles["cell"])]
            for k, v in rows if v not in (None, "")]
    if not data:
        return Spacer(1, 0)
    table = Table(data, colWidths=list(widths))
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def _party_block(styles, palette, *, heading: str, name: str, lines: list[str]):
    cells = [Paragraph(esc(heading).upper(), styles["label"]),
             Paragraph("<b>%s</b>" % esc(name), styles["cell_b"])]
    for line in lines:
        if line:
            cells.append(Paragraph(esc(line), styles["cell"]))
    return cells


def _money_table(rows, styles, palette, *, width=None, bold_last=True):
    width = width or (PAGE_W - 2 * MARGIN)
    data = []
    for label, value, *rest in rows:
        strong = rest[0] if rest else False
        data.append([
            Paragraph(esc(label), styles["cell_b"] if strong else styles["cell"]),
            Paragraph(esc(value), styles["cell_rb"] if strong else styles["cell_r"]),
        ])
    table = Table(data, colWidths=[width * 0.62, width * 0.38])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, palette["line"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]
    if bold_last and data:
        style += [("LINEABOVE", (0, -1), (-1, -1), 0.9, palette["ink"]),
                  ("TOPPADDING", (0, -1), (-1, -1), 5)]
    table.setStyle(TableStyle(style))
    return table


def _lines_table(lines, styles, palette, *, show_hsn: bool, show_tax: bool):
    """The itemised table shared by quotes and invoices."""
    width = PAGE_W - 2 * MARGIN
    head = ["#", "Description"]
    if show_hsn:
        head.append("HSN/SAC")
    head += ["Qty", "Rate", "Amount"]
    if show_tax:
        head.insert(len(head) - 1, "GST")

    data = [[Paragraph("<b>%s</b>" % esc(h),
                       styles["cell_rb"] if h in ("Qty", "Rate", "Amount", "GST")
                       else styles["cell_b"]) for h in head]]

    for index, line in enumerate(lines, start=1):
        row = [Paragraph(str(index), styles["cell"])]
        label = "<b>%s</b>" % esc(line["label"])
        if line.get("description"):
            label += "<br/><font size=7.4 color='#767C90'>%s</font>" % esc(line["description"])
        row.append(Paragraph(label, styles["cell"]))
        if show_hsn:
            row.append(Paragraph(esc(line.get("hsn_sac") or ""), styles["cell"]))
        qty = parse_float(line.get("qty"), 1)
        qty_text = f"{qty:g} {line.get('unit') or ''}".strip()
        row.append(Paragraph(esc(qty_text), styles["cell_r"]))
        row.append(Paragraph(rupees(line.get("unit_price")), styles["cell_r"]))
        if show_tax:
            row.append(Paragraph(f"{parse_float(line.get('tax_rate')):g}%", styles["cell_r"]))
        row.append(Paragraph(rupees(line.get("amount")), styles["cell_rb"]))
        data.append(row)

    if show_hsn and show_tax:
        widths = [8 * mm, width - 8 * mm - 22 * mm - 20 * mm - 24 * mm - 14 * mm - 26 * mm,
                  22 * mm, 20 * mm, 24 * mm, 14 * mm, 26 * mm]
    elif show_hsn:
        widths = [8 * mm, width - 8 * mm - 22 * mm - 22 * mm - 26 * mm - 28 * mm,
                  22 * mm, 22 * mm, 26 * mm, 28 * mm]
    elif show_tax:
        widths = [8 * mm, width - 8 * mm - 22 * mm - 26 * mm - 14 * mm - 28 * mm,
                  22 * mm, 26 * mm, 14 * mm, 28 * mm]
    else:
        widths = [8 * mm, width - 8 * mm - 24 * mm - 28 * mm - 30 * mm,
                  24 * mm, 28 * mm, 30 * mm]

    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), palette["wash"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, palette["line"]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, palette["line"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _signature_block(styles, palette, *, left_name: str, left_role: str,
                     right_name: str, right_role: str):
    width = PAGE_W - 2 * MARGIN
    cell = lambda name, role: [  # noqa: E731 - a two-line signature cell
        Spacer(1, 13 * mm),
        Paragraph("_" * 34, styles["small"]),
        Paragraph("<b>%s</b>" % esc(name or ""), styles["cell_b"]),
        Paragraph(esc(role), styles["small"]),
    ]
    table = Table([[cell(left_name, left_role), cell(right_name, right_role)]],
                  colWidths=[width / 2, width / 2])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (0, 0), 0),
                               ("RIGHTPADDING", (-1, 0), (-1, 0), 0)]))
    return table


def _payment_block(styles, palette):
    """Bank details, UPI and the QR, on everything that asks for money."""
    rows = [
        ("Account name", settings.get("invoice.bank_account_name")),
        ("Bank", settings.get("invoice.bank_name")),
        ("Account number", settings.get("invoice.bank_account_no")),
        ("IFSC", settings.get("invoice.bank_ifsc")),
        ("Branch", settings.get("invoice.bank_branch")),
        ("UPI", settings.get("invoice.upi_id")),
    ]
    rows = [(k, v) for k, v in rows if v]
    if not rows:
        return None

    width = PAGE_W - 2 * MARGIN
    left = [Paragraph("HOW TO PAY", styles["label"])]
    left.append(_kv_table(rows, styles, palette, widths=(26 * mm, 58 * mm)))

    cells = [left]
    widths = [width]
    qr = _upi_qr()
    if qr is not None:
        cells = [left, [qr, Paragraph("Scan with any UPI app", styles["small"])]]
        widths = [width - 34 * mm, 34 * mm]

    table = Table([cells], colWidths=widths)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), palette["wash"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.4, palette["line"]),
    ]))
    return table


def _upi_qr(size=28 * mm):
    """A UPI intent QR, drawn with ReportLab's own barcode module.

    No extra dependency and no third-party image service, which matters because
    the alternative is sending a client's payment string to someone else's server.
    """
    upi = (settings.get("invoice.upi_id") or "").strip()
    if not upi:
        return None
    name = (settings.get("invoice.bank_account_name")
            or settings.get("brand.name") or "Aruka").strip()
    from urllib.parse import quote

    payload = f"upi://pay?pa={quote(upi)}&pn={quote(name)}&cu=INR"
    try:
        from reportlab.graphics.barcode import qr
        from reportlab.graphics.shapes import Drawing

        code = qr.QrCodeWidget(payload)
        bounds = code.getBounds()
        w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        drawing = Drawing(size, size, transform=[size / w, 0, 0, size / h,
                                                 -bounds[0] * size / w, -bounds[1] * size / h])
        drawing.add(code)
        return drawing
    except Exception:  # noqa: BLE001 - a missing QR must never fail an invoice
        return None


def _paragraphs(text: str, style, *, bullets_style=None):
    """Turn a textarea into flowables: blank lines split paragraphs, a leading
    dash or bullet becomes a list item."""
    out = []
    for block in re.split(r"\n\s*\n", str(text or "").strip()):
        block = block.strip()
        if not block:
            continue
        rows = [r.strip() for r in block.splitlines() if r.strip()]
        if rows and all(r[:1] in "-*\u2022" for r in rows):
            for row in rows:
                out.append(Paragraph("&bull;&nbsp;&nbsp;" + esc(row.lstrip("-*\u2022 ").strip()),
                                     bullets_style or style))
        else:
            out.append(Paragraph(esc(" ".join(rows)), style))
    return out


# ── proposals, scopes of work and AMCs ──────────────────────────────────────
DOC_TITLES = {
    "proposal": "Proposal",
    "sow": "Scope of Work",
    "amc": "Annual Maintenance Contract",
    "quotation": "Quotation",
    "agreement": "Service Agreement",
    "nda": "Non-Disclosure Agreement",
}


def proposal_pdf(document) -> bytes:
    """A proposal, scope of work or AMC, built from a document row.

    The commercials come from the attached quote; the wording comes from the
    versioned clause library. Nothing is written by this function, so re-rendering
    a document a year later reproduces the clause versions it was issued with.
    """
    from core import pricing

    palette = _palette()
    styles = _styles(palette)
    payload = load_json(document["body_json"], {})

    quote = db.one("SELECT * FROM quotes WHERE id = ?", (document["quote_id"],)) \
        if document["quote_id"] else None
    client = db.one("SELECT * FROM clients WHERE id = ?", (document["client_id"],)) \
        if document["client_id"] else None
    lead = db.one("SELECT * FROM leads WHERE id = ?", (document["lead_id"],)) \
        if document["lead_id"] else None

    kind = document["kind"]
    heading = DOC_TITLES.get(kind, kind.replace("_", " ").title())
    draft = document["status"] == "draft"
    story: list = []

    # ── cover ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(heading.upper(), styles["kicker"]))
    story.append(Paragraph(esc(document["title"] or heading), styles["h1"]))

    to_name = (client["name"] if client else (lead["company"] or lead["name"] if lead else ""))
    to_person = (client["contact_name"] if client else (lead["name"] if lead else ""))
    to_lines = []
    source = client or lead
    if source is not None:
        to_lines = [
            source["city"] or "",
            source["email"] or "",
            source["phone"] or "",
        ]
    if client and client["gstin"]:
        to_lines.append("GSTIN " + client["gstin"])

    meta_rows = [
        ("Reference", document["ref"]),
        ("Date", pretty_date(document["issued_on"] or document["created_at"])),
        ("Valid until", pretty_date(document["valid_until"]) if document["valid_until"] else ""),
        ("Version", str(document["version"])),
        ("Prepared by", settings.get("doc.signatory_name") or settings.get("brand.name")),
    ]

    width = PAGE_W - 2 * MARGIN
    cover = Table([[
        _party_block(styles, palette, heading="Prepared for",
                     name=to_name or to_person or "Client",
                     lines=([to_person] if to_person and to_person != to_name else []) + to_lines),
        _kv_table(meta_rows, styles, palette, widths=(24 * mm, 46 * mm)),
    ]], colWidths=[width * 0.55, width * 0.45])
    cover.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 8)]))
    story.append(Spacer(1, 5 * mm))
    story.append(cover)
    story.append(Spacer(1, 4 * mm))

    if payload.get("intro"):
        story.append(Paragraph("Overview", styles["h2"]))
        story += _paragraphs(payload["intro"], styles["body_j"])

    # ── scope ──────────────────────────────────────────────────────────
    package = db.one("SELECT * FROM packages WHERE id = ?", (quote["package_id"],)) \
        if quote and quote["package_id"] else None

    def bullet_lines(override: str, fallback: str) -> list[str]:
        text = override.strip() or (fallback or "")
        return [line.strip().lstrip("-*\u2022 ").strip()
                for line in str(text).splitlines() if line.strip()]

    included = bullet_lines(payload.get("included") or "",
                            package["features"] if package else "")
    excluded = bullet_lines(payload.get("excluded") or "",
                            package["excluded"] if package else "")

    if included:
        story.append(Paragraph("What is included", styles["h2"]))
        for item in included:
            story.append(Paragraph("&bull;&nbsp;&nbsp;" + esc(item), styles["body"]))

    if excluded:
        story.append(Paragraph("What is not included", styles["h2"]))
        story.append(Paragraph(
            "Anything below is outside this scope. It can be added later as a change "
            "request, quoted separately.", styles["small"]))
        story.append(Spacer(1, 2))
        for item in excluded:
            story.append(Paragraph("&bull;&nbsp;&nbsp;" + esc(item), styles["body"]))

    if payload.get("deliverables"):
        story.append(Paragraph("What you will be handed", styles["h2"]))
        story += _paragraphs(payload["deliverables"], styles["body"])

    if payload.get("timeline"):
        story.append(Paragraph("Timeline", styles["h2"]))
        story += _paragraphs(payload["timeline"], styles["body_j"])

    # ── commercials ────────────────────────────────────────────────────
    if quote:
        lines = db.query(
            "SELECT * FROM quote_lines WHERE quote_id = ? AND is_recurring = 0 "
            "ORDER BY sort_order, id", (quote["id"],))
        recurring = db.query(
            "SELECT * FROM quote_lines WHERE quote_id = ? AND is_recurring = 1 "
            "ORDER BY sort_order, id", (quote["id"],))

        story.append(Paragraph("Investment", styles["h2"]))
        story.append(_lines_table([dict(l) for l in lines], styles, palette,
                                  show_hsn=False, show_tax=False))
        story.append(Spacer(1, 3 * mm))

        sums = [("Subtotal", rupees(quote["subtotal"]))]
        if parse_float(quote["surcharge_amount"]):
            sums.append(("Rush surcharge", rupees(quote["surcharge_amount"])))
        if parse_float(quote["discount_amount"]):
            sums.append(("Discount", "- " + rupees(quote["discount_amount"])))
        sums.append(("Taxable value", rupees(quote["taxable_value"])))
        if parse_float(quote["tax_amount"]):
            sums.append((f"GST at {settings.get('gst.default_rate')}%",
                         rupees(quote["tax_amount"])))
        sums.append(("Total payable", rupees(quote["total"]), True))

        holder = Table([["", _money_table(sums, styles, palette, width=78 * mm)]],
                       colWidths=[width - 78 * mm, 78 * mm])
        holder.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(holder)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("<b>In words:</b> " + esc(amount_in_words(quote["total"])),
                               styles["small"]))

        if not settings.gst_on():
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                "This is a bill of supply. No GST is charged, as the supplier is not "
                "registered under GST at the date of this document.", styles["small"]))

        if recurring:
            story.append(Paragraph("Running costs, from year two", styles["h3"]))
            for line in recurring:
                story.append(Paragraph(
                    "&bull;&nbsp;&nbsp;<b>%s</b> &mdash; %s per %s" % (
                        esc(line["label"]), rupees(line["unit_price"]),
                        esc((line["recurring_period"] or "year").replace("_", " "))),
                    styles["body"]))
            story.append(Paragraph(
                "Renewals keep the site online. If they lapse, the site goes down - that is "
                "the hosting and domain expiring, not a fault.", styles["small"]))

        milestones = pricing.milestone_split(parse_float(quote["total"]))
        if milestones:
            story.append(Paragraph("Payment schedule", styles["h3"]))
            rows = [(f"{m['label']} ({m['pct']:g}%)", rupees(m["amount"])) for m in milestones]
            story.append(_money_table(rows + [("Total", rupees(quote["total"]), True)],
                                      styles, palette, width=90 * mm))

        block = _payment_block(styles, palette)
        if block is not None:
            story.append(Spacer(1, 4 * mm))
            story.append(block)

    # ── clauses ────────────────────────────────────────────────────────
    clause_ids = payload.get("clause_ids") or []
    if clause_ids:
        placeholders = ",".join("?" * len(clause_ids))
        clauses = db.query(
            f"SELECT * FROM clause_library WHERE id IN ({placeholders}) "
            "ORDER BY sort_order, id", tuple(clause_ids))
    else:
        clauses = db.query(
            "SELECT * FROM clause_library WHERE is_active = 1 AND applies_to LIKE ? "
            "ORDER BY sort_order, id", (f"%{kind}%",))

    if clauses:
        story.append(PageBreak())
        story.append(Paragraph("Terms and conditions", styles["h2"]))
        story.append(Paragraph(
            "These terms form part of this " + esc(heading.lower()) +
            " and apply on acceptance.", styles["small"]))
        story.append(Spacer(1, 2 * mm))
        for index, clause in enumerate(clauses, start=1):
            group = [Paragraph(f"{index}. {esc(clause['title'])}", styles["clause_h"])]
            group += _paragraphs(_fill_clause(clause["body"], document, quote, client or lead),
                                 styles["clause"])
            story.append(KeepTogether(group))

    # ── acceptance ─────────────────────────────────────────────────────
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Acceptance", styles["h2"]))
    story.append(Paragraph(
        "Signing below, or accepting online through the link you were sent, confirms the "
        "scope, the commercials and the terms in this document. Work begins once the first "
        "payment is received.", styles["body_j"]))
    story.append(_signature_block(
        styles, palette,
        left_name=settings.get("doc.signatory_name") or settings.get("brand.name"),
        left_role="for " + (settings.get("brand.legal_name") or settings.get("brand.name") or ""),
        right_name=to_person or to_name,
        right_role="for " + (to_name or "the client")))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "<b>Please have this reviewed.</b> These terms are a sensible starting point drafted "
        "for Indian service work, not legal advice. Have a lawyer read them once before you "
        "rely on them, particularly the liability, indemnity and jurisdiction clauses.",
        styles["small"]))

    return _build(story, title=f"{heading} {document['ref']}",
                  watermark="DRAFT" if draft else "")


def _fill_clause(text: str, document, quote, party) -> str:
    """Substitute the handful of tokens the clause library uses."""
    return render_vars(text, {
        "brand": settings.get("brand.name") or "",
        "legal_name": settings.get("brand.legal_name") or settings.get("brand.name") or "",
        "client": (party["name"] if party is not None else "the Client"),
        "jurisdiction": settings.get("doc.jurisdiction_city") or "",
        "state": settings.get("doc.jurisdiction_state") or "",
        "late_interest": str(settings.get("doc.late_interest_pct") or 18),
        "validity_days": str(settings.get("doc.validity_days") or 15),
        "acceptance_days": str(settings.get("doc.deemed_acceptance_days") or 7),
        "support_months": str(settings.get("doc.warranty_months") or 1),
        "revisions": str(settings.get("doc.revision_rounds") or 2),
        "gst_rate": str(settings.get("gst.default_rate") or 18),
        "total": rupees(quote["total"]) if quote else "",
        "ref": document["ref"],
    })


# ── invoices ────────────────────────────────────────────────────────────────
def invoice_pdf(invoice) -> bytes:
    palette = _palette()
    styles = _styles(palette)
    client = db.one("SELECT * FROM clients WHERE id = ?", (invoice["client_id"],))
    lines = db.query("SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY sort_order, id",
                     (invoice["id"],))
    payments = db.query(
        "SELECT * FROM payments WHERE invoice_id = ? AND voided_at IS NULL ORDER BY paid_on",
        (invoice["id"],))

    tax_mode = invoice["doc_mode"] == "tax_invoice"
    kind_title = {
        "invoice": "Tax Invoice" if tax_mode else "Bill of Supply",
        "proforma": "Proforma Invoice",
        "advance": "Advance Receipt",
    }.get(invoice["kind"], "Invoice")

    width = PAGE_W - 2 * MARGIN
    story: list = [Spacer(1, 5 * mm)]
    story.append(Paragraph(kind_title.upper(), styles["kicker"]))
    story.append(Paragraph(invoice["ref"], styles["h1"]))

    bill_lines = [
        client["billing_address"] or client["city"] or "",
        client["email"] or "",
        client["phone"] or "",
    ]
    if client["gstin"]:
        bill_lines.append("GSTIN " + client["gstin"])
    if client["pan"]:
        bill_lines.append("PAN " + client["pan"])

    meta = [
        ("Invoice date", pretty_date(invoice["issued_on"] or today_iso())),
        ("Due date", pretty_date(invoice["due_on"]) if invoice["due_on"] else "On receipt"),
        ("Status", invoice["status"].replace("_", " ").title()),
    ]
    if tax_mode:
        meta += [
            ("Place of supply", invoice["place_of_supply"] or ""),
            ("Supply type", "Inter-state" if invoice["supply_type"] == "inter" else "Intra-state"),
            ("Reverse charge", "No"),
        ]

    head = Table([[
        _party_block(styles, palette, heading="Billed to",
                     name=client["name"], lines=bill_lines),
        _kv_table(meta, styles, palette, widths=(26 * mm, 46 * mm)),
    ]], colWidths=[width * 0.55, width * 0.45])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 8)]))
    story.append(Spacer(1, 4 * mm))
    story.append(head)
    story.append(Spacer(1, 5 * mm))

    story.append(_lines_table([dict(l) for l in lines], styles, palette,
                             show_hsn=tax_mode, show_tax=tax_mode))
    story.append(Spacer(1, 3 * mm))

    sums = [("Subtotal", rupees(invoice["subtotal"]))]
    if parse_float(invoice["discount_amount"]):
        sums.append(("Discount", "- " + rupees(invoice["discount_amount"])))
    sums.append(("Taxable value", rupees(invoice["taxable_value"])))
    if tax_mode:
        if parse_float(invoice["igst"]):
            sums.append(("IGST", rupees(invoice["igst"])))
        else:
            sums.append(("CGST", rupees(invoice["cgst"])))
            sums.append(("SGST", rupees(invoice["sgst"])))
    if parse_float(invoice["round_off"]):
        sums.append(("Rounding", rupees(invoice["round_off"])))
    sums.append(("Total", rupees(invoice["total"]), True))
    if parse_float(invoice["amount_paid"]):
        sums.append(("Received", "- " + rupees(invoice["amount_paid"])))
    if parse_float(invoice["tds_amount"]):
        sums.append(("TDS deducted by client", "- " + rupees(invoice["tds_amount"])))
    if parse_float(invoice["written_off"]):
        sums.append(("Written off", "- " + rupees(invoice["written_off"])))
    sums.append(("Balance due", rupees(invoice["balance"]), True))

    holder = Table([["", _money_table(sums, styles, palette, width=80 * mm)]],
                   colWidths=[width - 80 * mm, 80 * mm])
    holder.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(holder)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("<b>In words:</b> " + esc(amount_in_words(invoice["total"])),
                           styles["small"]))

    if not tax_mode:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            "Bill of supply. No GST charged, as the supplier is not registered under GST.",
            styles["small"]))

    if payments:
        story.append(Paragraph("Payments received", styles["h3"]))
        rows = [(f"{pretty_date(p['paid_on'])} \u00b7 {p['method']}"
                 + (f" \u00b7 {p['reference']}" if p["reference"] else ""),
                 rupees(p["amount"])) for p in payments]
        story.append(_money_table(rows, styles, palette, width=100 * mm, bold_last=False))

    if parse_float(invoice["balance"]) > 0:
        block = _payment_block(styles, palette)
        if block is not None:
            story.append(Spacer(1, 4 * mm))
            story.append(block)

    terms = invoice["terms"] or settings.get("invoice.footer_note") or ""
    if terms:
        story.append(Paragraph("Terms", styles["h3"]))
        story += _paragraphs(terms, styles["small"])
    if invoice["notes"]:
        story.append(Paragraph("Notes", styles["h3"]))
        story += _paragraphs(invoice["notes"], styles["small"])

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "This is a computer-generated document. " +
        ("A signature is not required." if invoice["kind"] == "proforma"
         else "Digitally issued by " + esc(settings.get("brand.name") or "")),
        styles["small"]))

    watermark = ""
    if invoice["status"] == "draft":
        watermark = "DRAFT"
    elif invoice["status"] == "cancelled":
        watermark = "CANCELLED"
    elif invoice["kind"] == "proforma":
        watermark = "PROFORMA"
    elif parse_float(invoice["balance"]) <= 0.01 and invoice["status"] == "paid":
        watermark = "PAID"

    return _build(story, title=f"{kind_title} {invoice['ref']}", watermark=watermark)


# ── receipts and credit notes ───────────────────────────────────────────────
def receipt_pdf(payment) -> bytes:
    palette = _palette()
    styles = _styles(palette)
    client = db.one("SELECT * FROM clients WHERE id = ?", (payment["client_id"],))
    invoice = db.one("SELECT * FROM invoices WHERE id = ?", (payment["invoice_id"],)) \
        if payment["invoice_id"] else None

    width = PAGE_W - 2 * MARGIN
    story = [Spacer(1, 8 * mm)]
    story.append(Paragraph("PAYMENT RECEIPT", styles["kicker"]))
    story.append(Paragraph(payment["ref"], styles["h1"]))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph(
        "Received with thanks from <b>%s</b> the sum of <b>%s</b> (%s) by %s%s on %s%s." % (
            esc(client["name"]), rupees(payment["amount"]),
            esc(amount_in_words(payment["amount"])), esc(payment["method"]),
            (" reference " + esc(payment["reference"])) if payment["reference"] else "",
            esc(pretty_date(payment["paid_on"])),
            (" against invoice " + esc(invoice["ref"])) if invoice else ""),
        styles["body_j"]))

    rows = [("Amount received", rupees(payment["amount"]))]
    if parse_float(payment["tds_amount"]):
        rows.append(("TDS deducted at source", rupees(payment["tds_amount"])))
        rows.append(("Gross credited to the invoice",
                     rupees(parse_float(payment["amount"]) + parse_float(payment["tds_amount"]))))
    if invoice:
        rows.append(("Invoice total", rupees(invoice["total"])))
        rows.append(("Balance now outstanding", rupees(invoice["balance"]), True))

    story.append(Spacer(1, 5 * mm))
    story.append(_money_table(rows, styles, palette, width=100 * mm))

    if payment["notes"]:
        story.append(Paragraph("Notes", styles["h3"]))
        story += _paragraphs(payment["notes"], styles["small"])

    story.append(Spacer(1, 10 * mm))
    story.append(_signature_block(
        styles, palette,
        left_name=settings.get("doc.signatory_name") or settings.get("brand.name"),
        left_role="Authorised signatory", right_name="", right_role=""))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "A receipt is not an invoice. It records money received against the invoice named "
        "above.", styles["small"]))

    return _build(story, title=f"Receipt {payment['ref']}",
                  watermark="VOID" if payment["voided_at"] else "")


def credit_note_pdf(note) -> bytes:
    palette = _palette()
    styles = _styles(palette)
    client = db.one("SELECT * FROM clients WHERE id = ?", (note["client_id"],))
    invoice = db.one("SELECT * FROM invoices WHERE id = ?", (note["invoice_id"],)) \
        if note["invoice_id"] else None

    story = [Spacer(1, 8 * mm)]
    story.append(Paragraph("CREDIT NOTE", styles["kicker"]))
    story.append(Paragraph(note["ref"], styles["h1"]))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        "Issued to <b>%s</b> on %s%s." % (
            esc(client["name"]), esc(pretty_date(note["issued_on"])),
            (" against invoice " + esc(invoice["ref"])) if invoice else ""),
        styles["body"]))

    story.append(Spacer(1, 4 * mm))
    story.append(_money_table([
        ("Credit amount", rupees(note["amount"]), True),
    ], styles, palette, width=100 * mm))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("<b>In words:</b> " + esc(amount_in_words(note["amount"])),
                           styles["small"]))

    if note["reason"]:
        story.append(Paragraph("Reason", styles["h3"]))
        story += _paragraphs(note["reason"], styles["body"])
    if note["notes"]:
        story.append(Paragraph("Notes", styles["h3"]))
        story += _paragraphs(note["notes"], styles["small"])

    story.append(Spacer(1, 10 * mm))
    story.append(_signature_block(
        styles, palette,
        left_name=settings.get("doc.signatory_name") or settings.get("brand.name"),
        left_role="Authorised signatory", right_name="", right_role=""))

    return _build(story, title=f"Credit note {note['ref']}")


def font_available(name: str) -> bool:
    """Used by the settings screen to say whether a chosen font really exists."""
    try:
        pdfmetrics.getFont(name)
        return True
    except Exception:  # noqa: BLE001
        return False
