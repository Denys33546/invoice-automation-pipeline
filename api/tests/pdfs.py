"""Helpers that build small PDFs for the tests1 (no files on disk needed)."""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DEFAULT_ITEMS = [("Widget", "2", "$10.00", "$20.00")]


def build_invoice_pdf(
    *,
    vendor="Acme Parts",
    number="INV-9",
    issue_date="2026-02-01",
    customer="Buyer Ltd",
    items=DEFAULT_ITEMS,
    subtotal="$20.00",
    tax="$2.60",
    total="$22.60",
    extra_table=False,
) -> bytes:
    """An invoice PDF. Pass None to leave a part out, or wrong values to break the numbers."""
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    story = [Paragraph(vendor, styles["Title"]), Paragraph("INVOICE", styles["Heading2"])]
    if number is not None:
        story.append(Paragraph(f"Invoice No: {number}", styles["Normal"]))
    if issue_date is not None:
        story.append(Paragraph(f"Date: {issue_date}", styles["Normal"]))
    story += [Paragraph(f"Bill To: {customer}", styles["Normal"]), Spacer(1, 8 * mm)]

    if extra_table:
        notes = Table([["Note", "Value"], ["Terms", "Net 30"]], colWidths=[40 * mm, 40 * mm])
        notes.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, colors.black)]))
        story += [notes, Spacer(1, 6 * mm)]
    if items is not None:
        table = Table(
            [["Description", "Qty", "Unit Price", "Amount"], *items],
            colWidths=[85 * mm, 20 * mm, 35 * mm, 35 * mm],
        )
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, colors.black)]))
        story += [table, Spacer(1, 6 * mm)]

    totals = [
        [label, value]
        for label, value in (("Subtotal", subtotal), ("Tax (13%)", tax), ("Total", total))
        if value is not None
    ]
    if totals:
        story.append(Table(totals, colWidths=[40 * mm, 35 * mm], hAlign="RIGHT"))
    doc.build(story)
    return buffer.getvalue()


def build_text_pdf(lines: list[str], pages: int = 1) -> bytes:
    """A PDF that only contains the given lines of text on every page."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for _ in range(pages):
        for number, line in enumerate(lines):
            pdf.drawString(50, 780 - number * 20, line)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_blank_pdf(pages: int = 1) -> bytes:
    """Pages without any text, like a scan would look to a text extractor."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for _ in range(pages):
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()
