#!/usr/bin/env python3
"""
Generate synthetic AP invoice demo files for the GDE AP Agent demo bucket.

Produces realistic Accounts Payable documents in the formats ailang-parse
handles deterministically (no LLM required):
  - DOCX  : Acme GmbH standard vendor invoice (Word)
  - XLSX  : TechCorp UK software licence expense report (Excel, multi-line)
  - EML   : Nordic Parts AB invoice email (MIME multipart)
  - CSV   : Q2 2026 batch invoice file (4 vendors, mixed currencies)
  - ODT   : Apex Consulting professional services invoice (OpenDocument)
  - MBOX  : AP approval thread (3-message mailbox)

Run from this directory:
    python3 generate_demo_files.py

Outputs all files into ./  (infrastructure/demo-invoices/).
"""

from __future__ import annotations

import io
import textwrap
import zipfile
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent

# ---------------------------------------------------------------------------
# 1. DOCX — Acme GmbH vendor invoice (python-docx)
# ---------------------------------------------------------------------------

def make_docx() -> None:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL

    doc = Document()

    # Page margins
    section = doc.sections[0]
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)

    # --- Header: vendor name ---
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = h.add_run("Acme GmbH")
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1A, 0x1F, 0x2E)

    vendor_info = doc.add_paragraph()
    vendor_info.add_run(
        "Friedrichstraße 123 · 10117 Berlin, Germany\n"
        "VAT-ID: DE123456789 · IBAN: DE89 3704 0044 0532 0130 00\n"
        "invoices@acme-gmbh.de · +49 30 2000-1234"
    ).font.size = Pt(9)

    doc.add_paragraph()  # spacer

    # --- Invoice header table ---
    tbl = doc.add_table(rows=2, cols=4)
    tbl.style = "Table Grid"
    labels = ["INVOICE NUMBER", "INVOICE DATE", "DUE DATE", "PO REFERENCE"]
    values = ["INV-2026-042", "01 June 2026", "01 July 2026", "PO-2026-0189"]
    for i, (lbl, val) in enumerate(zip(labels, values)):
        cell_lbl = tbl.cell(0, i)
        cell_lbl.text = lbl
        cell_lbl.paragraphs[0].runs[0].font.bold = True
        cell_lbl.paragraphs[0].runs[0].font.size = Pt(8)
        tbl.cell(1, i).text = val
        tbl.cell(1, i).paragraphs[0].runs[0].font.size = Pt(10)

    doc.add_paragraph()

    # --- Bill-to ---
    bt = doc.add_paragraph()
    bt.add_run("BILL TO\n").font.bold = True
    bt.add_run(
        "GDE AP Agent Ltd\n"
        "Accounts Payable Department\n"
        "1 Canada Square, Canary Wharf\n"
        "London E14 5AB, United Kingdom"
    ).font.size = Pt(10)

    doc.add_paragraph()

    # --- Line items table ---
    items = [
        ("Cloud Infrastructure Services — June 2026", "5200-OPEX", 1, 4_500.00),
        ("Managed Database Cluster (PostgreSQL HA)", "5200-OPEX", 1, 1_800.00),
        ("Bandwidth & CDN — 10 TB overage", "5200-OPEX", 3, 250.00),
        ("Support SLA Premium Tier — monthly", "5300-CONSULT", 1, 1_200.00),
    ]
    subtotal = sum(qty * price for _, _, qty, price in items)
    vat_rate = 0.19
    vat = subtotal * vat_rate
    total = subtotal + vat

    cols = ["DESCRIPTION", "GL CODE", "QTY", "UNIT PRICE (EUR)", "AMOUNT (EUR)"]
    item_tbl = doc.add_table(rows=1 + len(items) + 3, cols=5)
    item_tbl.style = "Table Grid"

    # Header row
    for j, col in enumerate(cols):
        cell = item_tbl.cell(0, j)
        cell.text = col
        p = cell.paragraphs[0]
        p.runs[0].font.bold = True
        p.runs[0].font.size = Pt(9)

    # Data rows
    for i, (desc, gl, qty, price) in enumerate(items, start=1):
        row_data = [desc, gl, str(qty), f"€ {price:,.2f}", f"€ {qty * price:,.2f}"]
        for j, val in enumerate(row_data):
            item_tbl.cell(i, j).text = val
            item_tbl.cell(i, j).paragraphs[0].runs[0].font.size = Pt(9)

    # Subtotal / VAT / Total rows
    offset = 1 + len(items)
    for label, amount in [
        ("Subtotal", f"€ {subtotal:,.2f}"),
        (f"VAT {int(vat_rate * 100)}% (DE VAT)", f"€ {vat:,.2f}"),
        ("TOTAL DUE", f"€ {total:,.2f}"),
    ]:
        r = item_tbl.rows[offset]
        r.cells[3].text = label
        r.cells[3].paragraphs[0].runs[0].font.bold = True
        r.cells[4].text = amount
        r.cells[4].paragraphs[0].runs[0].font.bold = True
        offset += 1

    doc.add_paragraph()

    # --- Payment terms ---
    terms = doc.add_paragraph()
    terms.add_run("PAYMENT TERMS & BANKING DETAILS\n").font.bold = True
    terms.add_run(
        "Payment due within 30 days of invoice date (Net 30).\n"
        "Bank: Commerzbank AG · BIC: COBADEFFXXX\n"
        "IBAN: DE89 3704 0044 0532 0130 00\n"
        "Reference: INV-2026-042\n\n"
        "Late payments will incur interest at 8% p.a. above ECB base rate."
    ).font.size = Pt(9)

    out_path = OUT / "acme-gmbh-invoice-2026-042.docx"
    doc.save(str(out_path))
    print(f"  ✓ {out_path.name}")


# ---------------------------------------------------------------------------
# 2. XLSX — TechCorp UK software licence expense report (openpyxl)
# ---------------------------------------------------------------------------

def make_xlsx() -> None:
    from openpyxl import Workbook
    from openpyxl.styles import (
        Alignment, Border, Font, PatternFill, Side
    )
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Invoice"

    NAVY = "1A1F2E"
    GOLD = "E8A800"
    LIGHT = "F5F7FA"

    def hdr_fill(hex_color: str) -> PatternFill:
        return PatternFill("solid", fgColor=hex_color)

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Column widths
    widths = [8, 18, 40, 14, 12, 14, 14, 12, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Row 1 — company header
    ws.merge_cells("A1:I1")
    ws["A1"] = "TechCorp Ltd — Accounts Payable Invoice"
    ws["A1"].font = Font(name="Calibri", bold=True, size=16, color="FFFFFF")
    ws["A1"].fill = hdr_fill(NAVY)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    # Row 2 — invoice metadata
    meta = [
        ("Invoice No:", "INV-2026-018"),
        ("Date:", "01-Jun-2026"),
        ("Due Date:", "01-Jul-2026"),
        ("Currency:", "GBP"),
        ("PO Ref:", "PO-UK-2026-0045"),
    ]
    for col_offset, (label, value) in enumerate(meta):
        col = col_offset * 2 + 1
        ws.cell(2, col, label).font = Font(bold=True, size=9)
        ws.cell(2, col + 1, value).font = Font(size=9)
    ws.row_dimensions[2].height = 18

    # Row 3 — blank
    ws.row_dimensions[3].height = 6

    # Row 4 — Bill To / From
    ws["A4"] = "FROM:"
    ws["A4"].font = Font(bold=True, size=9)
    ws["A5"] = "TechCorp Ltd"
    ws["A6"] = "25 Canada Square"
    ws["A7"] = "London E14 5LQ, UK"
    ws["A8"] = "VAT: GB 123 4567 89"
    ws["A9"] = "invoices@techcorp.co.uk"
    for r in range(4, 10):
        ws.cell(r, 1).font = Font(size=9)

    ws["E4"] = "TO:"
    ws["E4"].font = Font(bold=True, size=9)
    ws["E5"] = "GDE AP Agent Ltd"
    ws["E6"] = "Accounts Payable"
    ws["E7"] = "1 Canada Square"
    ws["E8"] = "London E14 5AB, UK"
    for r in range(4, 10):
        ws.cell(r, 5).font = Font(size=9)

    # Row 11 — line items header
    headers = ["#", "Invoice Date", "Description", "GL Code", "Qty", "Unit Price", "Amount", "VAT %", "VAT Amount"]
    for j, h in enumerate(headers, 1):
        cell = ws.cell(11, j, h)
        cell.font = Font(bold=True, size=9, color="FFFFFF")
        cell.fill = hdr_fill(NAVY)
        cell.border = border
        cell.alignment = Alignment(horizontal="center")
    ws.row_dimensions[11].height = 18

    # Line items
    items = [
        ("01-Jun-2026", "Microsoft 365 Business — 25 seats × 12 months", "5400-SOFT", 25, 120.00),
        ("01-Jun-2026", "GitHub Enterprise Cloud — 25 seats × 12 months", "5400-SOFT", 25, 180.00),
        ("01-Jun-2026", "Figma Organisation — 10 seats × 12 months",       "5400-SOFT", 10, 150.00),
        ("01-Jun-2026", "Datadog APM — Pro plan × 12 months",              "5200-OPEX",  1, 3_600.00),
        ("01-Jun-2026", "Annual software audit & licence review (consulting)", "5300-CONSULT", 4, 250.00),
    ]
    subtotal = 0.0
    for i, (inv_date, desc, gl, qty, unit) in enumerate(items):
        row = 12 + i
        amount = qty * unit
        vat_pct = 20
        vat_amt = amount * vat_pct / 100
        subtotal += amount
        data = [i + 1, inv_date, desc, gl, qty, unit, amount, vat_pct, vat_amt]
        for j, val in enumerate(data, 1):
            cell = ws.cell(row, j, val)
            cell.border = border
            cell.font = Font(size=9)
            cell.fill = hdr_fill(LIGHT) if i % 2 == 0 else PatternFill()
            if j in (6, 7, 9):
                cell.number_format = '£#,##0.00'
            if j == 8:
                cell.number_format = '0"%"'
        ws.row_dimensions[row].height = 16

    # Totals
    total_row = 12 + len(items)
    vat_total = subtotal * 0.20
    grand_total = subtotal + vat_total
    for label, amount, row_offset in [
        ("Subtotal (excl. VAT)", subtotal, 0),
        ("VAT 20% (UK)", vat_total, 1),
        ("TOTAL DUE (GBP)", grand_total, 2),
    ]:
        r = total_row + row_offset
        ws.merge_cells(f"A{r}:F{r}")
        lbl_cell = ws.cell(r, 1, label)
        lbl_cell.font = Font(bold=True, size=10 if row_offset == 2 else 9)
        lbl_cell.alignment = Alignment(horizontal="right")
        lbl_cell.fill = hdr_fill(GOLD) if row_offset == 2 else PatternFill()
        amt_cell = ws.cell(r, 7, amount)
        amt_cell.number_format = '£#,##0.00'
        amt_cell.font = Font(bold=True, size=10 if row_offset == 2 else 9)
        amt_cell.fill = hdr_fill(GOLD) if row_offset == 2 else PatternFill()

    # Terms sheet
    ws2 = wb.create_sheet("Payment Terms")
    ws2["A1"] = "Payment Terms & Conditions"
    ws2["A1"].font = Font(bold=True, size=14)
    terms = [
        "1. Payment due within 30 days of invoice date (Net 30).",
        "2. Bank: Barclays Bank PLC · Sort Code: 20-00-00 · Account: 12345678",
        "3. IBAN: GB29 NWBK 6016 1331 9268 19 · BIC: BARCGB22",
        "4. Reference: INV-2026-018 in all payments.",
        "5. Late payment: 8% p.a. above Bank of England base rate.",
        "6. Disputes must be raised within 5 business days of receipt.",
    ]
    for i, term in enumerate(terms, 3):
        ws2.cell(i, 1, term).font = Font(size=10)
    ws2.column_dimensions["A"].width = 80

    out_path = OUT / "techcorp-uk-expense-report-q2-2026.xlsx"
    wb.save(str(out_path))
    print(f"  ✓ {out_path.name}")


# ---------------------------------------------------------------------------
# 3. EML — Nordic Parts AB invoice email (MIME text)
# ---------------------------------------------------------------------------

def make_eml() -> None:
    inv_date = "2026-06-01"
    due_date = "2026-07-01"
    content = textwrap.dedent(f"""\
        From: Billing <invoices@nordic-parts.se>
        To: ap@gde-ap-agent.com
        Cc: purchasing@gde-ap-agent.com
        Subject: Invoice INV-2026-889 — Nordic Parts AB — EUR 3,200.00 — Due {due_date}
        Date: Sun, 01 Jun 2026 09:00:00 +0200
        Message-ID: <inv-2026-889@nordic-parts.se>
        MIME-Version: 1.0
        Content-Type: multipart/alternative; boundary="NordicParts_MIME_889"
        X-Invoice-Number: INV-2026-889
        X-Invoice-Amount: EUR 3200.00
        X-Invoice-Due: {due_date}
        X-Vendor-VAT: SE556123456701

        --NordicParts_MIME_889
        Content-Type: text/plain; charset=utf-8
        Content-Transfer-Encoding: 7bit

        Dear Accounts Payable Team,

        Please find below our invoice INV-2026-889 for spare parts supplied in May 2026.

        INVOICE DETAILS
        ===============
        Invoice Number : INV-2026-889
        Invoice Date   : {inv_date}
        Due Date       : {due_date} (Net 30)
        PO Reference   : PO-2026-0234
        Currency       : EUR

        LINE ITEMS
        ----------
        1. Hydraulic Seal Kit HS-400 (x10)
           GL Code: 5100-COGS
           Unit Price: EUR 120.00 | Amount: EUR 1,200.00

        2. Bearing Assembly BA-22 (x5)
           GL Code: 5100-COGS
           Unit Price: EUR 280.00 | Amount: EUR 1,400.00

        3. O-Ring Set Standard Grade (x50)
           GL Code: 5100-COGS
           Unit Price: EUR 12.00  | Amount: EUR 600.00

        TOTALS
        ------
        Subtotal : EUR 3,200.00
        VAT 0%   : EUR 0.00  (Intra-EU B2B — reverse charge applies)
        TOTAL    : EUR 3,200.00

        PAYMENT DETAILS
        ---------------
        Bank      : Nordea Bank Abp
        IBAN      : SE35 5000 0000 0549 1000 0003
        BIC/SWIFT : NDEASESS
        Reference : INV-2026-889

        Regards,
        Anna Lindqvist
        Chief Financial Officer
        Nordic Parts AB
        Industrigatan 45, 211 24 Malmö, Sweden
        VAT: SE556123456701

        --NordicParts_MIME_889
        Content-Type: text/html; charset=utf-8
        Content-Transfer-Encoding: quoted-printable

        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><style>
          body {{ font-family: Arial, sans-serif; font-size: 13px; color: #1a1f2e; }}
          .header {{ background: #1a1f2e; color: #fff; padding: 16px 24px; }}
          .header h1 {{ margin: 0; font-size: 22px; }}
          .header p {{ margin: 4px 0 0; font-size: 12px; opacity: 0.7; }}
          table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
          th {{ background: #1a1f2e; color: #e8a800; padding: 8px 12px; text-align: left; font-size: 11px; text-transform: uppercase; }}
          td {{ padding: 8px 12px; border-bottom: 1px solid #e5e7eb; font-size: 12px; }}
          .total-row td {{ font-weight: bold; background: #f9fafb; }}
          .footer {{ font-size: 11px; color: #6b7280; margin-top: 24px; }}
        </style></head>
        <body>
        <div class="header">
          <h1>Nordic Parts AB</h1>
          <p>Industrigatan 45 · 211 24 Malmö · Sweden · VAT: SE556123456701</p>
        </div>
        <p><strong>Invoice:</strong> INV-2026-889 &nbsp;|&nbsp;
           <strong>Date:</strong> {inv_date} &nbsp;|&nbsp;
           <strong>Due:</strong> {due_date} (Net 30) &nbsp;|&nbsp;
           <strong>PO:</strong> PO-2026-0234</p>
        <table>
          <tr><th>#</th><th>Description</th><th>GL Code</th><th>Qty</th><th>Unit Price</th><th>Amount</th></tr>
          <tr><td>1</td><td>Hydraulic Seal Kit HS-400</td><td>5100-COGS</td><td>10</td><td>EUR 120.00</td><td>EUR 1,200.00</td></tr>
          <tr><td>2</td><td>Bearing Assembly BA-22</td><td>5100-COGS</td><td>5</td><td>EUR 280.00</td><td>EUR 1,400.00</td></tr>
          <tr><td>3</td><td>O-Ring Set Standard Grade</td><td>5100-COGS</td><td>50</td><td>EUR 12.00</td><td>EUR 600.00</td></tr>
          <tr class="total-row"><td colspan="5" align="right">Subtotal:</td><td>EUR 3,200.00</td></tr>
          <tr class="total-row"><td colspan="5" align="right">VAT 0% (EU reverse charge):</td><td>EUR 0.00</td></tr>
          <tr class="total-row"><td colspan="5" align="right"><strong>TOTAL DUE:</strong></td><td><strong>EUR 3,200.00</strong></td></tr>
        </table>
        <p><strong>Payment:</strong> Nordea Bank · IBAN: SE35 5000 0000 0549 1000 0003 · BIC: NDEASESS · Ref: INV-2026-889</p>
        <div class="footer">Nordic Parts AB · Registered in Sweden · Corp. No. 556123-4567</div>
        </body></html>

        --NordicParts_MIME_889--
    """)
    out_path = OUT / "nordic-parts-invoice-email-2026.eml"
    out_path.write_text(content, encoding="utf-8")
    print(f"  ✓ {out_path.name}")


# ---------------------------------------------------------------------------
# 4. CSV — Q2 2026 batch invoice file (4 vendors, mixed currencies)
# ---------------------------------------------------------------------------

def make_csv() -> None:
    rows = [
        ["invoice_number", "invoice_date", "due_date", "vendor_name", "vendor_country",
         "vendor_vat", "po_number", "description", "gl_code", "currency", "subtotal",
         "vat_rate_pct", "vat_amount", "total_amount", "payment_terms", "bank_iban",
         "bank_bic", "notes"],
        ["INV-2026-042", "2026-06-01", "2026-07-01", "Acme GmbH", "DE",
         "DE123456789", "PO-2026-0189", "Cloud Infrastructure Services June 2026",
         "5200-OPEX", "EUR", "7563.00", "19", "1436.97", "9000.00",
         "NET30", "DE89370400440532013000", "COBADEFFXXX", "German VAT applies"],
        ["INV-2026-018", "2026-06-01", "2026-07-01", "TechCorp Ltd", "GB",
         "GB123456789", "PO-UK-2026-0045", "Software Licences Q2 2026 (5 products)",
         "5400-SOFT", "GBP", "10625.00", "20", "2125.00", "12750.00",
         "NET30", "GB29NWBK60161331926819", "BARCGB22", "UK VAT 20%"],
        ["INV-2026-889", "2026-06-01", "2026-07-01", "Nordic Parts AB", "SE",
         "SE556123456701", "PO-2026-0234", "Hydraulic Parts — May 2026 supply",
         "5100-COGS", "EUR", "3200.00", "0", "0.00", "3200.00",
         "NET30", "SE3550000000054910000003", "NDEASESS", "EU reverse charge — zero VAT"],
        ["INV-2026-103", "2026-06-01", "2026-07-31", "Apex Consulting LLC", "US",
         "US-EIN-47-1234567", "PO-US-2026-0012", "Digital Transformation Consulting — May 2026",
         "5300-CONSULT", "USD", "22000.00", "0", "0.00", "22000.00",
         "NET60", "", "CHASUS33", "US entity — no EU VAT. W-9 on file."],
    ]
    import csv
    out_path = OUT / "batch-invoices-q2-2026.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"  ✓ {out_path.name}")


# ---------------------------------------------------------------------------
# 5. ODT — Apex Consulting invoice (minimal OpenDocument ZIP)
# ---------------------------------------------------------------------------

def make_odt() -> None:
    # ODT is a ZIP containing XML files. We craft a minimal but valid one.
    manifest_xml = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
                   manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.names:tc:opendocument:xmlns:text:1.0"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""

    meta_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                      xmlns:dc="http://purl.org/dc/elements/1.1/"
                      xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0">
  <office:meta>
    <dc:title>Invoice INV-2026-103 — Apex Consulting LLC</dc:title>
    <dc:creator>Apex Consulting LLC</dc:creator>
    <dc:date>2026-06-01T00:00:00</dc:date>
    <meta:initial-creator>Apex Consulting LLC</meta:initial-creator>
    <meta:document-statistic meta:word-count="320"/>
  </office:meta>
</office:document-meta>"""

    styles_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">
  <office:styles>
    <style:style style:name="Standard" style:family="paragraph" style:class="text">
      <style:text-properties fo:font-size="11pt" fo:font-family="Calibri"/>
    </style:style>
    <style:style style:name="Heading1" style:family="paragraph" style:parent-style-name="Standard">
      <style:text-properties fo:font-size="20pt" fo:font-weight="bold"/>
    </style:style>
    <style:style style:name="Bold" style:family="text">
      <style:text-properties fo:font-weight="bold"/>
    </style:style>
  </office:styles>
  <office:automatic-styles/>
</office:document-styles>"""

    def p(text: str, bold: bool = False) -> str:
        style = 'Bold' if bold else 'Standard'
        return f'<text:p text:style-name="{style}">{text}</text:p>'

    def table_row(cells: list[tuple[str, bool]]) -> str:
        cells_xml = ""
        for text, bold in cells:
            style = 'Bold' if bold else 'Standard'
            cells_xml += (
                '<table:table-cell table:style-name="TableCell">'
                f'<text:p text:style-name="{style}">{text}</text:p>'
                '</table:table-cell>'
            )
        return f"<table:table-row>{cells_xml}</table:table-row>"

    items = [
        ("Discovery & requirements workshop (2 days)", "5300-CONSULT", 2, 2500.00),
        ("Architecture design — Cloud migration blueprint", "5300-CONSULT", 8, 1800.00),
        ("Implementation oversight & code reviews", "5300-CONSULT", 12, 1200.00),
        ("Executive stakeholder presentations (3 sessions)", "5300-CONSULT", 3, 1000.00),
        ("Project management & reporting (monthly retainer)", "5300-CONSULT", 1, 2500.00),
    ]
    subtotal = sum(qty * price for _, _, qty, price in items)
    grand_total = subtotal  # USD, no sales tax (B2B cross-border)

    rows_xml = table_row([
        ("#", True), ("Description", True), ("GL Code", True),
        ("Days / Units", True), ("Rate (USD)", True), ("Amount (USD)", True)
    ])
    for i, (desc, gl, qty, rate) in enumerate(items, 1):
        rows_xml += table_row([
            (str(i), False), (desc, False), (gl, False),
            (str(qty), False), (f"${rate:,.2f}", False), (f"${qty * rate:,.2f}", False)
        ])
    rows_xml += table_row([
        ("", False), ("", False), ("", False),
        ("", False), ("TOTAL DUE (USD)", True), (f"${grand_total:,.2f}", True)
    ])

    content_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
    xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
    xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">
  <office:automatic-styles>
    <style:style style:name="TableCell" style:family="table-cell">
      <style:table-cell-properties fo:padding="0.05in" fo:border="0.02cm solid #cccccc"/>
    </style:style>
    <style:style style:name="InvoiceTable" style:family="table">
      <style:table-properties style:width="6.5in"/>
    </style:style>
  </office:automatic-styles>
  <office:body>
    <office:text>
      {p("Apex Consulting LLC", bold=True)}
      {p("500 Montgomery Street, Suite 400, San Francisco, CA 94111, USA")}
      {p("EIN: 47-1234567  |  billing@apex-consulting.com  |  +1 (415) 555-0199")}
      {p("")}
      {p("INVOICE", bold=True)}
      {p("Invoice Number : INV-2026-103")}
      {p("Invoice Date   : 01 June 2026")}
      {p("Due Date       : 31 July 2026 (Net 60)")}
      {p("PO Reference   : PO-US-2026-0012")}
      {p("Currency       : USD")}
      {p("")}
      {p("BILL TO", bold=True)}
      {p("GDE AP Agent Ltd — Accounts Payable")}
      {p("1 Canada Square, Canary Wharf, London E14 5AB, UK")}
      {p("")}
      {p("SERVICES RENDERED — DIGITAL TRANSFORMATION CONSULTING", bold=True)}
      <table:table table:name="InvoiceLines" table:style-name="InvoiceTable">
        <table:table-column table:number-columns-repeated="6"/>
        {rows_xml}
      </table:table>
      {p("")}
      {p("PAYMENT INSTRUCTIONS", bold=True)}
      {p("Wire transfer only. No cheques accepted.")}
      {p("Bank: JPMorgan Chase  |  Routing: 021000021  |  Account: 987654321")}
      {p("SWIFT/BIC: CHASUS33  |  Reference: INV-2026-103")}
      {p("")}
      {p("Note: This invoice is payable in USD. Cross-border B2B service — no US sales tax.")}
      {p("W-9 form available on request. Late payment: 1.5% per month.")}
    </office:text>
  </office:body>
</office:document-content>"""

    out_path = OUT / "apex-consulting-invoice-2026-103.odt"
    with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/manifest.xml", manifest_xml)
        zf.writestr("meta.xml", meta_xml)
        zf.writestr("styles.xml", styles_xml)
        zf.writestr("content.xml", content_xml)
    print(f"  ✓ {out_path.name}")


# ---------------------------------------------------------------------------
# 6. MBOX — AP approval thread (3-message mailbox)
# ---------------------------------------------------------------------------

def make_mbox() -> None:
    content = textwrap.dedent("""\
        From invoices@acme-gmbh.de Sun Jun 01 09:00:00 2026
        From: Billing <invoices@acme-gmbh.de>
        To: ap@gde-ap-agent.com
        Subject: Invoice INV-2026-042 — EUR 9,000.00
        Date: Sun, 01 Jun 2026 09:00:00 +0200
        Message-ID: <inv-042-orig@acme-gmbh.de>
        MIME-Version: 1.0
        Content-Type: text/plain; charset=utf-8

        Dear Team,

        Please find enclosed Invoice INV-2026-042 for cloud services rendered in May 2026.
        Amount: EUR 9,000.00 (incl. 19% VAT). Due: 01 July 2026.
        PO Reference: PO-2026-0189.

        GL Coding suggestion: 5200-OPEX

        Regards,
        Klaus Weber, Acme GmbH Finance

        From ap-manager@gde-ap-agent.com Mon Jun 02 10:15:00 2026
        From: Sarah Chen <ap-manager@gde-ap-agent.com>
        To: ap@gde-ap-agent.com
        Subject: Re: Invoice INV-2026-042 — EUR 9,000.00 — APPROVAL REQUIRED
        Date: Mon, 02 Jun 2026 10:15:00 +0100
        Message-ID: <approval-req-042@gde-ap-agent.com>
        In-Reply-To: <inv-042-orig@acme-gmbh.de>
        References: <inv-042-orig@acme-gmbh.de>
        MIME-Version: 1.0
        Content-Type: text/plain; charset=utf-8

        Team,

        I've reviewed INV-2026-042 from Acme GmbH. The amounts match PO-2026-0189.
        GL coding 5200-OPEX is correct per our chart of accounts.

        Requesting approval from Finance Director before posting.

        — Sarah Chen, AP Manager

        From finance-director@gde-ap-agent.com Mon Jun 02 14:30:00 2026
        From: James Okonkwo <finance-director@gde-ap-agent.com>
        To: ap@gde-ap-agent.com
        Subject: Re: Invoice INV-2026-042 — EUR 9,000.00 — APPROVED
        Date: Mon, 02 Jun 2026 14:30:00 +0100
        Message-ID: <approved-042@gde-ap-agent.com>
        In-Reply-To: <approval-req-042@gde-ap-agent.com>
        References: <inv-042-orig@acme-gmbh.de> <approval-req-042@gde-ap-agent.com>
        MIME-Version: 1.0
        Content-Type: text/plain; charset=utf-8
        X-AP-Status: APPROVED
        X-AP-Approved-By: James Okonkwo
        X-AP-Approved-Date: 2026-06-02

        APPROVED.

        INV-2026-042 (Acme GmbH, EUR 9,000.00) is approved for posting.
        GL: 5200-OPEX. Cost centre: CC-INFRA-EU. Post to accounting period June 2026.

        — James Okonkwo, Finance Director
    """)
    out_path = OUT / "ap-approval-thread-inv-042.mbox"
    out_path.write_text(content, encoding="utf-8")
    print(f"  ✓ {out_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating AP demo invoice files...")
    make_docx()
    make_xlsx()
    make_eml()
    make_csv()
    make_odt()
    make_mbox()
    print(f"\nAll files written to: {OUT}")
    print("\nFormats covered:")
    print("  .docx  — Acme GmbH vendor invoice (Word, tables, VAT calc)")
    print("  .xlsx  — TechCorp UK software licences (Excel, 2 sheets, formulas)")
    print("  .eml   — Nordic Parts AB invoice email (MIME multipart, HTML+plain)")
    print("  .csv   — Q2 2026 batch: 4 vendors, EUR/GBP/USD")
    print("  .odt   — Apex Consulting USD services (OpenDocument)")
    print("  .mbox  — AP approval thread mailbox (3-message chain)")
