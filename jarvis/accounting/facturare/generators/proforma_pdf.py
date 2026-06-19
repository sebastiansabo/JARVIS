"""Generate PROFORMA INVOICE PDFs using reportlab.

Differences from invoice_pdf.py:
- Title: FACTURA PROFORMA / PROFORMA INVOICE
- US number format: 27,560.00 (comma thousands, dot decimals)
- Model name splitting: Audi-specific multi-line display
- VIN shown as "Chassis number:" + value on next line
- Default signatory: Gabriela Oltean
"""
import io
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from ..models import OrderLine

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_LOGO = ASSETS_DIR / "logo.jpg"

# ── Number formatting ──────────────────────────────────────────

def fmt_us(val: float) -> str:
    """Format number as US style: 27,560.00"""
    return f"{float(val):,.2f}"


# ── Model name splitting ──────────────────────────────────────

BODY_TYPES = {"sportback", "allstreet", "avant"}


def split_model_lines(model: str) -> list[str]:
    """Split model name into 1-2 display lines.

    Examples:
        'Audi Q5 Sportback 40 TDI quattro' → ['AUDI Q5 SPORTBACK', '40 TDI QUATTRO']
        'Audi A6 Avant 40 TDI'             → ['AUDI A6 AVANT', '40 TDI']
        'VW MULTIVAN LIFE 2.0 TDI'         → ['VW MULTIVAN', 'LIFE 2.0 TDI']
        'MG ZS EV Standard'                → ['MG ZS', 'EV STANDARD']
    """
    s = (model or "").strip()
    parts = s.split()
    if len(parts) < 2:
        return [s.upper()]
    line1 = f"{parts[0]} {parts[1]}".upper()
    rest = parts[2:]
    if rest and rest[0].lower() in BODY_TYPES:
        line1 += f" {rest[0].upper()}"
        rest = rest[1:]
    out = [line1]
    if rest:
        out.append(" ".join(w.upper() for w in rest))
    return out


# ── PDF Renderer ──────────────────────────────────────────────

class ProformaPdfRenderer:
    """Renders proforma invoice PDFs."""

    def __init__(self, supplier: dict, customer: dict, invoice_date: str,
                 intocmit_de: str = "Gabriela Oltean",
                 description_prefix: str = "1. ADVANCE PAYMENT",
                 note: str = "",
                 title_lines: list[str] | None = None,
                 kurs_applied: float | None = None,
                 total_amount_ron: float | None = None):
        self.supplier = supplier
        self.customer = customer
        self.invoice_date = invoice_date
        self.intocmit_de = intocmit_de
        self.description_prefix = description_prefix
        self.note = note
        self.title_lines = title_lines or ["FACTURA PROFORMA", "PROFORMA INVOICE"]
        self.logo_path = DEFAULT_LOGO if DEFAULT_LOGO.exists() else None
        self.kurs_applied = kurs_applied
        self.total_amount_ron = total_amount_ron

    def render_one(self, c: canvas.Canvas, inv_no: int, line: OrderLine):
        """Draw a single proforma page."""
        W, H = A4
        LM = 18 * mm
        RM = W - 18 * mm

        # ── Logo ──
        if self.logo_path:
            img = ImageReader(str(self.logo_path))
            iw, ih = img.getSize()
            tw = 55 * mm
            th = tw * ih / iw
            c.drawImage(img, (W - tw) / 2, H - 22 * mm - th, tw, th, mask='auto')
            y = H - 24 * mm - th
        else:
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(W / 2, H - 25 * mm, self.supplier.get("name", "").split()[0])
            y = H - 32 * mm

        # underline rule
        c.setStrokeColorRGB(0.65, 0.78, 0.30)
        c.setLineWidth(0.6)
        c.line(LM, y, RM, y)
        c.setStrokeColorRGB(0, 0, 0)

        # ── Title ──
        y -= 18 * mm
        c.setFont("Helvetica-Bold", 13)
        for title_line in self.title_lines:
            c.drawCentredString(W / 2, y, title_line)
            y -= 5 * mm
        c.drawCentredString(W / 2, y, f"No:{inv_no}")
        y -= 5 * mm

        # Use per-row invoice_date if available, else global
        date_str = line.invoice_date or self.invoice_date
        # Convert YYYY-MM-DD to DD.MM.YYYY
        if date_str and "-" in date_str:
            parts = date_str.split("-")
            date_str = f"{parts[2]}.{parts[1]}.{parts[0]}"
        c.drawCentredString(W / 2, y, f"Data/ Date: {date_str}")

        # ── Supplier / Customer ──
        y -= 14 * mm
        col_l = LM
        col_r = LM + 95 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_l, y, "Furnizor/ Supplier:")
        c.drawString(col_r, y, "Cumparator/ Customer:")

        y -= 7 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_l, y, self.supplier.get("name", ""))
        c.drawString(col_r, y, self.customer.get("name", ""))

        c.setFont("Helvetica", 9.5)

        # Supplier lines
        supplier_lines = list(self.supplier.get("address_lines", []))
        if self.supplier.get("reg_no"):
            supplier_lines.append(self.supplier["reg_no"])
        if self.supplier.get("vat"):
            supplier_lines.append(f"VAT-nr: {self.supplier['vat']}")
        if self.supplier.get("iban"):
            supplier_lines.append("Cont/ Account no.:")
            supplier_lines.append(self.supplier["iban"])
        if self.supplier.get("bank"):
            supplier_lines.append(self.supplier["bank"])
        if self.supplier.get("swift"):
            supplier_lines.append(f"SWIFT/BIC: {self.supplier['swift']}")

        # Customer lines
        customer_lines = list(self.customer.get("address_lines", []))
        if self.customer.get("vat"):
            customer_lines.append("")
            customer_lines.append(self.customer["vat"])

        yl = y - 5 * mm
        for ln in supplier_lines:
            c.drawString(col_l, yl, ln)
            yl -= 4.5 * mm
        yr = y - 5 * mm
        for ln in customer_lines:
            c.drawString(col_r, yr, ln)
            yr -= 4.5 * mm

        y = min(yl, yr) - 4 * mm

        # ── Items table header ──
        c.setFont("Helvetica-Bold", 9.5)
        c.setLineWidth(0.4)
        c.line(LM, y + 1, RM, y + 1)

        headers_top = [
            ("Denumirea produselor", LM),
            ("U.m.", LM + 78 * mm),
            ("Cantitatea", LM + 92 * mm),
            ("Pret unitar", LM + 115 * mm),
            ("Valoarea", LM + 140 * mm),
            ("Valoarea TVA", LM + 160 * mm),
        ]
        for txt, x in headers_top:
            c.drawString(x, y - 4 * mm, txt)

        c.drawString(LM, y - 8 * mm, "sau a serviciilor")

        headers_bot2 = [
            ("Description", LM),
            ("Quantity", LM + 92 * mm),
            ("Unit price", LM + 115 * mm),
            ("Price", LM + 140 * mm),
            ("TVA/ VAT", LM + 160 * mm),
        ]
        for txt, x in headers_bot2:
            c.drawString(x, y - 12.5 * mm, txt)

        headers_bot3 = [
            ("EUR", LM + 115 * mm),
            ("EUR", LM + 140 * mm),
            ("EUR", LM + 160 * mm),
        ]
        for txt, x in headers_bot3:
            c.drawString(x, y - 17 * mm, txt)

        c.line(LM, y - 19 * mm, RM, y - 19 * mm)

        # ── Item row ──
        y -= 24 * mm
        c.setFont("Helvetica", 9.5)

        # Description: prefix + optional storno ref + model lines + chassis + culoare + comanda
        desc_lines = [self.description_prefix] if self.description_prefix else []
        if line.storno_description:
            desc_lines.append(line.storno_description)
        desc_lines.append((line.model or "").upper())
        desc_lines.append("Chassis number:")
        desc_lines.append(line.vin or "")
        desc_lines.append(f"Culoare: {line.culoare}")

        # Build comanda line with anexa ref
        comanda_text = f"Comanda: {line.comanda}"
        if line.anexa_ref:
            comanda_text += f" / {line.anexa_ref}"
        desc_lines.append(comanda_text)

        # Numeric columns on first desc line
        qty_display = str(line.qty) if line.qty != 1 else ("1" if line.advance >= 0 else "-1")
        c.drawString(LM + 78 * mm, y, "buc")
        c.drawRightString(LM + 105 * mm, y, qty_display)
        c.drawRightString(LM + 138 * mm, y, fmt_us(line.advance))
        c.drawRightString(LM + 158 * mm, y, fmt_us(line.advance))

        yl = y
        for ln in desc_lines:
            c.drawString(LM, yl, ln)
            yl -= 4.7 * mm

        y = yl - 3 * mm
        c.drawString(LM, y, "Scutire conform art. 138 din Directiva 2006/112/CE")
        y -= 4.7 * mm
        c.drawString(LM, y, "Livrare Ex Works")

        # ── Note ──
        if self.note:
            y -= 8 * mm
            c.setFont("Helvetica", 9)
            for note_line in self.note.split("\n"):
                c.drawString(LM, y, note_line)
                y -= 4.5 * mm

        # ── Total ──
        y -= 12 * mm
        c.line(LM, y + 6 * mm, RM, y + 6 * mm)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(LM, y, "PRICE")
        c.drawRightString(RM, y, f"{fmt_us(line.advance)} EUR")

        # Exchange rate
        if self.kurs_applied:
            y -= 6 * mm
            c.setFont("Helvetica", 9.5)
            c.drawString(LM, y, f"Curs BNR / Exchange rate: {self.kurs_applied:.4f}")

        # ── Footer ──
        y -= 18 * mm
        c.setFont("Helvetica", 9.5)
        c.drawString(LM, y, f"Intocmit de {self.intocmit_de}")

    def render_storno_multipage(self, groups: list[list[OrderLine]], start_no: int) -> bytes:
        """Render storno: one page per car, each listing all reversed invoices for that car."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        for page_idx, car_items in enumerate(groups):
            inv_no = start_no + page_idx
            self._render_storno_page(c, inv_no, car_items)
            c.showPage()
        c.save()
        return buf.getvalue()

    def _render_storno_page(self, c: canvas.Canvas, inv_no: int, items: list[OrderLine]):
        """Draw one storno page with multiple reversed invoice item blocks."""
        W, H = A4
        LM = 18 * mm
        RM = W - 18 * mm

        # ── Header (logo + rule) ──
        if self.logo_path:
            img = ImageReader(str(self.logo_path))
            iw, ih = img.getSize()
            tw = 55 * mm
            th = tw * ih / iw
            c.drawImage(img, (W - tw) / 2, H - 22 * mm - th, tw, th, mask='auto')
            y = H - 24 * mm - th
        else:
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(W / 2, H - 25 * mm, self.supplier.get("name", "").split()[0])
            y = H - 32 * mm

        c.setStrokeColorRGB(0.65, 0.78, 0.30)
        c.setLineWidth(0.6)
        c.line(LM, y, RM, y)
        c.setStrokeColorRGB(0, 0, 0)

        # ── Title ──
        y -= 18 * mm
        c.setFont("Helvetica-Bold", 13)
        for tl in self.title_lines:
            c.drawCentredString(W / 2, y, tl)
            y -= 5 * mm
        c.drawCentredString(W / 2, y, f"No:{inv_no}")
        y -= 5 * mm
        date_str = self.invoice_date
        if date_str and "-" in date_str:
            p = date_str.split("-")
            date_str = f"{p[2]}.{p[1]}.{p[0]}"
        c.drawCentredString(W / 2, y, f"Data/ Date: {date_str}")

        # ── Supplier / Customer ──
        y -= 14 * mm
        col_l, col_r = LM, LM + 95 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_l, y, "Furnizor/ Supplier:")
        c.drawString(col_r, y, "Cumparator/ Customer:")
        y -= 7 * mm
        c.drawString(col_l, y, self.supplier.get("name", ""))
        c.drawString(col_r, y, self.customer.get("name", ""))
        c.setFont("Helvetica", 9.5)
        sup_lines = list(self.supplier.get("address_lines", []))
        if self.supplier.get("reg_no"): sup_lines.append(self.supplier["reg_no"])
        if self.supplier.get("vat"):    sup_lines.append(f"VAT-nr: {self.supplier['vat']}")
        if self.supplier.get("iban"):   sup_lines += ["Cont/ Account no.:", self.supplier["iban"]]
        if self.supplier.get("bank"):   sup_lines.append(self.supplier["bank"])
        if self.supplier.get("swift"):  sup_lines.append(f"SWIFT/BIC: {self.supplier['swift']}")
        cust_lines = list(self.customer.get("address_lines", []))
        if self.customer.get("vat"):    cust_lines += ["", self.customer["vat"]]
        yl = y - 5 * mm
        for ln in sup_lines:  c.drawString(col_l, yl, ln); yl -= 4.5 * mm
        yr = y - 5 * mm
        for ln in cust_lines: c.drawString(col_r, yr, ln); yr -= 4.5 * mm
        y = min(yl, yr) - 4 * mm

        # ── Table header ──
        c.setFont("Helvetica-Bold", 9.5)
        c.setLineWidth(0.4)
        c.line(LM, y + 1, RM, y + 1)
        for txt, x in [("Denumirea produselor", LM), ("U.m.", LM + 78*mm), ("Cantitatea", LM + 92*mm),
                       ("Pret unitar", LM + 115*mm), ("Valoarea", LM + 140*mm), ("Valoarea TVA", LM + 160*mm)]:
            c.drawString(x, y - 4*mm, txt)
        c.drawString(LM, y - 8*mm, "sau a serviciilor")
        for txt, x in [("Description", LM), ("Quantity", LM + 92*mm), ("Unit price", LM + 115*mm),
                       ("Price", LM + 140*mm), ("TVA/ VAT", LM + 160*mm)]:
            c.drawString(x, y - 12.5*mm, txt)
        for txt, x in [("EUR", LM + 115*mm), ("EUR", LM + 140*mm), ("EUR", LM + 160*mm)]:
            c.drawString(x, y - 17*mm, txt)
        c.line(LM, y - 19*mm, RM, y - 19*mm)
        y -= 24 * mm

        # ── One item block per reversed invoice ──
        c.setFont("Helvetica", 9.5)
        total_eur = 0.0
        for i, line in enumerate(items):
            if i > 0:
                y -= 3 * mm
            item_y = y
            desc = ["STORNO ADVANCE"]
            if line.storno_description:
                desc.append(line.storno_description)
            desc.append((line.model or "").upper())
            desc.append(f"Culoare: {line.culoare}")
            if line.vin:
                desc.append(f"VIN: {line.vin}")
            comanda_text = f"Comanda: {line.comanda}"
            if line.anexa_ref:
                comanda_text += f" / {line.anexa_ref}"
            desc.append(comanda_text)

            c.drawString(LM + 78*mm, item_y, "buc")
            c.drawRightString(LM + 105*mm, item_y, "-1")
            c.drawRightString(LM + 138*mm, item_y, fmt_us(abs(line.advance)))
            c.drawRightString(LM + 158*mm, item_y, fmt_us(line.advance))
            total_eur += line.advance

            yl = item_y
            for ln in desc:
                c.drawString(LM, yl, ln)
                yl -= 4.7 * mm

            # Kurs reference below item
            if line.kurs:
                c.setFont("Helvetica", 8.5)
                c.drawString(LM + 78*mm, yl, f"Kurs: {line.kurs:.4f}")
                yl -= 4.7 * mm
                c.setFont("Helvetica", 9.5)

            y = yl

        # ── Footer text ──
        y -= 5 * mm
        c.drawString(LM, y, "Scutire conform art. 138 din Directiva 2006/112/CE")
        y -= 4.7 * mm
        c.drawString(LM, y, "Livrare Ex Works")

        if self.note:
            y -= 8 * mm
            c.setFont("Helvetica", 9)
            for note_line in self.note.split("\n"):
                c.drawString(LM, y, note_line)
                y -= 4.5 * mm

        # ── Total ──
        y -= 12 * mm
        c.line(LM, y + 6*mm, RM, y + 6*mm)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(LM, y, "PRICE")
        c.drawRightString(RM, y, f"{fmt_us(total_eur)} EUR")

        y -= 14 * mm
        c.setFont("Helvetica", 9.5)
        c.drawString(LM, y, f"Intocmit de {self.intocmit_de}")

    def _draw_header(self, c: canvas.Canvas, inv_no: int, date_str: str | None = None):
        """Draw shared header block: logo, title, No:, date, supplier/customer. Returns y position."""
        W, H = A4
        LM = 18 * mm
        RM = W - 18 * mm

        # Logo
        if self.logo_path:
            img = ImageReader(str(self.logo_path))
            iw, ih = img.getSize()
            tw = 55 * mm
            th = tw * ih / iw
            c.drawImage(img, (W - tw) / 2, H - 22 * mm - th, tw, th, mask='auto')
            y = H - 24 * mm - th
        else:
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(W / 2, H - 25 * mm, self.supplier.get("name", "").split()[0])
            y = H - 32 * mm

        c.setStrokeColorRGB(0.65, 0.78, 0.30)
        c.setLineWidth(0.6)
        c.line(LM, y, RM, y)
        c.setStrokeColorRGB(0, 0, 0)

        # Title
        y -= 18 * mm
        c.setFont("Helvetica-Bold", 13)
        for tl in self.title_lines:
            c.drawCentredString(W / 2, y, tl)
            y -= 5 * mm
        c.drawCentredString(W / 2, y, f"No:{inv_no}")
        y -= 5 * mm
        ds = date_str or self.invoice_date
        if ds and "-" in ds:
            p = ds.split("-")
            ds = f"{p[2]}.{p[1]}.{p[0]}"
        c.drawCentredString(W / 2, y, f"Data/ Date: {ds}")

        # Supplier / Customer
        y -= 14 * mm
        col_l, col_r = LM, LM + 95 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_l, y, "Furnizor/ Supplier:")
        c.drawString(col_r, y, "Cumparator/ Customer:")
        y -= 7 * mm
        c.drawString(col_l, y, self.supplier.get("name", ""))
        c.drawString(col_r, y, self.customer.get("name", ""))
        c.setFont("Helvetica", 9.5)
        sup_lines = list(self.supplier.get("address_lines", []))
        if self.supplier.get("reg_no"): sup_lines.append(self.supplier["reg_no"])
        if self.supplier.get("vat"):    sup_lines.append(f"VAT-nr: {self.supplier['vat']}")
        if self.supplier.get("iban"):   sup_lines += ["Cont/ Account no.:", self.supplier["iban"]]
        if self.supplier.get("bank"):   sup_lines.append(self.supplier["bank"])
        if self.supplier.get("swift"):  sup_lines.append(f"SWIFT/BIC: {self.supplier['swift']}")
        cust_lines = list(self.customer.get("address_lines", []))
        if self.customer.get("vat"):    cust_lines += ["", self.customer["vat"]]
        yl = y - 5 * mm
        for ln in sup_lines:  c.drawString(col_l, yl, ln); yl -= 4.5 * mm
        yr = y - 5 * mm
        for ln in cust_lines: c.drawString(col_r, yr, ln); yr -= 4.5 * mm
        return min(yl, yr) - 4 * mm

    def _draw_single_doc_table_header(self, c: canvas.Canvas, y: float) -> float:
        """Draw compact table header for single-doc mode. Returns y after header."""
        LM = 18 * mm
        RM = A4[0] - 18 * mm
        c.setFont("Helvetica-Bold", 8)
        c.setLineWidth(0.4)
        c.line(LM, y + 1, RM, y + 1)

        cols = [
            ("Nr.", LM + 1 * mm),
            ("Comanda", LM + 9 * mm),
            ("Denumire / Description", LM + 28 * mm),
            ("VIN / Chassis", LM + 85 * mm),
            ("Cant.", LM + 120 * mm),
            ("Pret unitar EUR", LM + 132 * mm),
            ("Valoare EUR", LM + 157 * mm),
        ]
        for txt, x in cols:
            c.drawString(x, y - 3.5 * mm, txt)
        c.line(LM, y - 5.5 * mm, RM, y - 5.5 * mm)
        return y - 8 * mm

    def render_single_doc(self, c: canvas.Canvas, inv_no: int, lines: list[OrderLine]):
        """Render a single document with all cars as compact table rows."""
        W, H = A4
        LM = 18 * mm
        RM = W - 18 * mm
        ROW_H = 4.5 * mm
        FOOTER_SPACE = 55 * mm  # reserve for total + footer

        # Header
        y = self._draw_header(c, inv_no)

        # Description prefix
        if self.description_prefix:
            c.setFont("Helvetica-Bold", 9)
            c.drawString(LM, y, self.description_prefix)
            y -= 6 * mm

        # Table header
        y = self._draw_single_doc_table_header(c, y)

        # Table rows
        c.setFont("Helvetica", 7.5)
        grand_total = 0.0
        for i, line in enumerate(lines):
            # Page overflow: start new page with continuation header
            if y < FOOTER_SPACE:
                c.showPage()
                y = H - 20 * mm
                c.setFont("Helvetica", 8)
                c.drawString(LM, y, f"No:{inv_no} (cont.)")
                y -= 6 * mm
                y = self._draw_single_doc_table_header(c, y)
                c.setFont("Helvetica", 7.5)

            # Nr.
            c.drawRightString(LM + 7 * mm, y, str(i + 1))
            # Comanda
            c.drawString(LM + 9 * mm, y, str(line.comanda) if line.comanda else "—")
            # Model (truncate to ~22 chars)
            model_str = (line.model or "").upper()
            if len(model_str) > 28:
                model_str = model_str[:27] + "…"
            c.drawString(LM + 28 * mm, y, model_str)
            # VIN
            c.drawString(LM + 85 * mm, y, line.vin or "—")
            # Qty
            c.drawCentredString(LM + 123 * mm, y, "1")
            # Unit price (= advance per car)
            c.drawRightString(LM + 153 * mm, y, fmt_us(line.advance))
            # Amount
            c.drawRightString(RM - 1 * mm, y, fmt_us(line.advance))

            grand_total += line.advance
            y -= ROW_H

            # Light separator every row
            c.setStrokeColorRGB(0.85, 0.85, 0.85)
            c.setLineWidth(0.2)
            c.line(LM, y + 1.5 * mm, RM, y + 1.5 * mm)
            c.setStrokeColorRGB(0, 0, 0)

        # Annexa ref (from first line)
        if lines and lines[0].anexa_ref:
            y -= 3 * mm
            c.setFont("Helvetica", 8)
            c.drawString(LM, y, lines[0].anexa_ref)
            y -= 4 * mm

        # Scutire / Livrare
        y -= 2 * mm
        c.setFont("Helvetica", 8.5)
        c.drawString(LM, y, "Scutire conform art. 138 din Directiva 2006/112/CE")
        y -= 4 * mm
        c.drawString(LM, y, "Livrare Ex Works")

        # Note
        if self.note:
            y -= 6 * mm
            c.setFont("Helvetica", 8.5)
            for note_line in self.note.split("\n"):
                c.drawString(LM, y, note_line)
                y -= 4 * mm

        # Total
        y -= 8 * mm
        c.setLineWidth(0.4)
        c.line(LM, y + 5 * mm, RM, y + 5 * mm)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(LM, y, "PRICE")
        c.drawRightString(RM, y, f"{fmt_us(grand_total)} EUR")

        # Exchange rate
        if self.kurs_applied:
            y -= 6 * mm
            c.setFont("Helvetica", 9.5)
            c.drawString(LM, y, f"Curs BNR / Exchange rate: {self.kurs_applied:.4f}")

        # Intocmit de
        y -= 14 * mm
        c.setFont("Helvetica", 9.5)
        c.drawString(LM, y, f"Intocmit de {self.intocmit_de}")

    def render_single_doc_to_bytes(self, lines: list[OrderLine], inv_no: int) -> bytes:
        """Render single-doc mode and return PDF bytes."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        self.render_single_doc(c, inv_no, lines)
        c.showPage()
        c.save()
        return buf.getvalue()

    def render_all_to_bytes(self, lines: list[OrderLine], start_no: int, same_number: bool = False) -> bytes:
        """Render all proformas and return PDF as bytes.
        If same_number=True, all pages use the same invoice number (single invoice covering multiple cars).
        """
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        for i, line in enumerate(lines):
            inv_no = (line.start_no if line.start_no is not None else start_no) + (0 if same_number else i)
            self.render_one(c, inv_no, line)
            c.showPage()
        c.save()
        return buf.getvalue()

    def render_all(self, lines: list[OrderLine], start_no: int, out_path: Path) -> Path:
        """Render all proformas into a single multi-page PDF on disk."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(out_path), pagesize=A4)
        for i, line in enumerate(lines):
            inv_no = (line.start_no if line.start_no is not None else start_no) + i
            self.render_one(c, inv_no, line)
            c.showPage()
        c.save()
        return out_path

    # ── Collapsed (single invoice, multiple positions) ────────

    def render_collapsed_to_bytes(self, lines: list[OrderLine], start_no: int) -> bytes:
        """Render all lines as a single proforma invoice with a table."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        self._render_collapsed_pages(c, start_no, lines)
        c.save()
        return buf.getvalue()

    def _build_columns(self, lines: list[OrderLine]) -> list[tuple[str, str, float]]:
        """Build dynamic column list based on which fields have data.

        Returns list of (header, field_key, width_mm) tuples.
        """
        has_vin = any(l.vin for l in lines)
        has_culoare = any(l.culoare for l in lines)
        has_contract = any(l.contract_ref for l in lines)
        has_anexa = any(l.anexa_ref for l in lines)

        cols: list[tuple[str, str, float]] = [
            ("Nr.", "nr", 8),
            ("Comanda", "comanda", 18),
            ("Model", "model", 0),  # flex — gets remaining space
        ]
        if has_vin:
            cols.append(("VIN", "vin", 38))
        if has_culoare:
            cols.append(("Culoare", "culoare", 22))
        if has_contract:
            cols.append(("Contract", "contract_ref", 22))
        if has_anexa:
            cols.append(("Anexa", "anexa_ref", 20))
        cols.append(("Qty", "qty", 10))
        cols.append(("Amount (EUR)", "amount", 28))

        # Calculate model column width (flex)
        fixed = sum(w for _, _, w in cols if w > 0)
        page_w = (A4[0] - 2 * 18 * mm) / mm  # usable width in mm
        model_w = page_w - fixed
        cols = [(h, k, model_w if k == "model" else w) for h, k, w in cols]

        return cols

    def _render_collapsed_pages(self, c: canvas.Canvas, inv_no: int, lines: list[OrderLine]):
        """Draw collapsed proforma — splits across pages if needed."""
        W, H = A4
        LM = 18 * mm
        RM = W - 18 * mm

        ROW_HEIGHT = 4.2 * mm
        MAX_ROWS_FIRST_PAGE = 18
        MAX_ROWS_CONT_PAGE = 35

        total = sum(l.advance for l in lines)
        cols = self._build_columns(lines)
        page_num = 0
        line_idx = 0

        while line_idx < len(lines):
            if page_num == 0:
                y = self._draw_collapsed_header(c, inv_no, W, H, LM, RM, cols)
                max_rows = MAX_ROWS_FIRST_PAGE
            else:
                # Continuation page — minimal header
                y = H - 20 * mm
                c.setFont("Helvetica-Bold", 10)
                c.drawString(LM, y, f"{self.title_lines[-1]} No:{inv_no} (continued)")
                y -= 10 * mm
                y = self._draw_table_header(c, y, LM, RM, cols)
                max_rows = MAX_ROWS_CONT_PAGE

            # Determine how many rows fit on this page
            is_last_batch = (line_idx + max_rows >= len(lines))
            if is_last_batch:
                rows_this_page = len(lines) - line_idx
            else:
                rows_this_page = max_rows

            # Draw table rows
            c.setFont("Helvetica", 8.5)
            for i in range(rows_this_page):
                line = lines[line_idx]
                row_y = y - (i * ROW_HEIGHT)
                x = LM + 1 * mm
                for _, key, w in cols:
                    if key == "nr":
                        c.drawString(x, row_y, str(line_idx + 1))
                    elif key == "comanda":
                        c.drawString(x, row_y, str(line.comanda))
                    elif key == "model":
                        c.drawString(x, row_y, (line.model or "")[:35])
                    elif key == "vin":
                        c.drawString(x, row_y, (line.vin or "")[:20])
                    elif key == "culoare":
                        c.drawString(x, row_y, (line.culoare or "")[:15])
                    elif key == "contract_ref":
                        c.drawString(x, row_y, (line.contract_ref or "")[:18])
                    elif key == "anexa_ref":
                        c.drawString(x, row_y, (line.anexa_ref or "")[:16])
                    elif key == "qty":
                        c.drawRightString(x + w * mm - 2 * mm, row_y, str(line.qty))
                    elif key == "amount":
                        c.drawRightString(x + w * mm - 2 * mm, row_y, fmt_us(line.advance))
                    x += w * mm
                line_idx += 1

            y = y - (rows_this_page * ROW_HEIGHT) - 3 * mm

            # Draw total + footer only on last page
            if is_last_batch:
                c.setLineWidth(0.4)
                c.line(LM, y + 2 * mm, RM, y + 2 * mm)
                y -= 5 * mm
                c.setFont("Helvetica-Bold", 11)
                c.drawString(LM, y, "TOTAL")
                c.drawRightString(RM - 2 * mm, y, f"{fmt_us(total)} EUR")

                y -= 10 * mm
                c.setFont("Helvetica", 9)
                c.drawString(LM, y, "Scutire conform art. 138 din Directiva 2006/112/CE")
                y -= 4.5 * mm
                c.drawString(LM, y, "Livrare Ex Works")
                if self.note:
                    y -= 6 * mm
                    for note_line in self.note.split("\n"):
                        c.drawString(LM, y, note_line)
                        y -= 4.5 * mm
                y -= 10 * mm
                c.drawString(LM, y, f"Intocmit de {self.intocmit_de}")

            c.showPage()
            page_num += 1

    def _draw_collapsed_header(self, c: canvas.Canvas, inv_no: int,
                               W: float, H: float, LM: float, RM: float,
                               cols: list[tuple[str, str, float]]) -> float:
        """Draw the header (logo, title, supplier/customer) and return Y position for table."""
        # ── Logo ──
        if self.logo_path:
            img = ImageReader(str(self.logo_path))
            iw, ih = img.getSize()
            tw = 55 * mm
            th = tw * ih / iw
            c.drawImage(img, (W - tw) / 2, H - 22 * mm - th, tw, th, mask='auto')
            y = H - 24 * mm - th
        else:
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(W / 2, H - 25 * mm, self.supplier.get("name", "").split()[0])
            y = H - 32 * mm

        # underline rule
        c.setStrokeColorRGB(0.65, 0.78, 0.30)
        c.setLineWidth(0.6)
        c.line(LM, y, RM, y)
        c.setStrokeColorRGB(0, 0, 0)

        # ── Title ──
        y -= 14 * mm
        c.setFont("Helvetica-Bold", 13)
        for tl in self.title_lines:
            c.drawCentredString(W / 2, y, tl)
            y -= 5 * mm
        c.drawCentredString(W / 2, y, f"No:{inv_no}")
        y -= 5 * mm

        date_str = self.invoice_date
        if date_str and "-" in date_str:
            parts = date_str.split("-")
            date_str = f"{parts[2]}.{parts[1]}.{parts[0]}"
        c.drawCentredString(W / 2, y, f"Data/ Date: {date_str}")

        # ── Supplier / Customer (compact) ──
        y -= 10 * mm
        col_l = LM
        col_r = LM + 95 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(col_l, y, "Furnizor/ Supplier:")
        c.drawString(col_r, y, "Cumparator/ Customer:")

        y -= 5 * mm
        c.drawString(col_l, y, self.supplier.get("name", ""))
        c.drawString(col_r, y, self.customer.get("name", ""))

        c.setFont("Helvetica", 8.5)
        supplier_lines = list(self.supplier.get("address_lines", []))
        if self.supplier.get("vat"):
            supplier_lines.append(f"VAT: {self.supplier['vat']}")
        if self.supplier.get("iban"):
            supplier_lines.append(f"IBAN: {self.supplier['iban']}")

        customer_lines = list(self.customer.get("address_lines", []))
        if self.customer.get("vat"):
            customer_lines.append(self.customer["vat"])

        yl = y - 4 * mm
        for ln in supplier_lines:
            c.drawString(col_l, yl, ln)
            yl -= 3.8 * mm
        yr = y - 4 * mm
        for ln in customer_lines:
            c.drawString(col_r, yr, ln)
            yr -= 3.8 * mm

        y = min(yl, yr) - 5 * mm

        # ── Table header ──
        y = self._draw_table_header(c, y, LM, RM, cols)
        return y

    def _draw_table_header(self, c: canvas.Canvas, y: float, LM: float, RM: float,
                           cols: list[tuple[str, str, float]]) -> float:
        """Draw the items table header and return Y for first data row."""
        c.setLineWidth(0.4)
        c.line(LM, y + 2 * mm, RM, y + 2 * mm)

        c.setFont("Helvetica-Bold", 8.5)
        x = LM + 1 * mm
        for header, key, w in cols:
            if key in ("qty", "amount"):
                c.drawRightString(x + w * mm - 2 * mm, y - 3 * mm, header)
            else:
                c.drawString(x, y - 3 * mm, header)
            x += w * mm

        c.line(LM, y - 5.5 * mm, RM, y - 5.5 * mm)
        return y - 9 * mm
