"""Generate PROFORMA INVOICE PDFs using reportlab.

Differences from invoice_pdf.py:
- Title: FACTURA PROFORMA / PROFORMA INVOICE
- US number format: 27,560.00 (comma thousands, dot decimals)
- Model name splitting: Audi-specific multi-line display
- VIN shown as "Chassis number:" + value on next line
- Engine number: line (blank)
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
    """Split Audi model name into 1-3 display lines.

    Examples:
        'Audi Q5 Sportback 40 TDI quattro' → ['AUDI Q5', 'SPORTBACK', '40 TDI QUATTRO']
        'Audi A3 Allstreet 35 TDI'         → ['AUDI A3', 'ALLSTREET 35 TDI']
        'A3 Sportback 30 TDI'              → ['AUDI A3', 'SPORTBACK', '30 TDI']
    """
    s = (model or "").strip()
    if not s.lower().startswith("audi"):
        s = "Audi " + s
    parts = s.split()
    if len(parts) < 2:
        return [s.upper()]
    line1 = f"{parts[0]} {parts[1]}".upper()
    rest = parts[2:]
    out = [line1]
    if rest and rest[0].lower() in BODY_TYPES:
        out.append(rest[0].upper())
        rest = rest[1:]
    if rest:
        out.append(" ".join(w.upper() for w in rest))
    return out


# ── PDF Renderer ──────────────────────────────────────────────

class ProformaPdfRenderer:
    """Renders proforma invoice PDFs."""

    def __init__(self, supplier: dict, customer: dict, invoice_date: str,
                 intocmit_de: str = "Gabriela Oltean",
                 description_prefix: str = "1. ADVANCE PAYMENT"):
        self.supplier = supplier
        self.customer = customer
        self.invoice_date = invoice_date
        self.intocmit_de = intocmit_de
        self.description_prefix = description_prefix
        self.logo_path = DEFAULT_LOGO if DEFAULT_LOGO.exists() else None

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
        c.drawCentredString(W / 2, y, "FACTURA PROFORMA")
        y -= 5 * mm
        c.drawCentredString(W / 2, y, "PROFORMA INVOICE")
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

        # Description: prefix + model lines + chassis + engine + culoare + comanda
        desc_lines = [self.description_prefix]
        desc_lines.extend(split_model_lines(line.model))
        desc_lines.append("Chassis number:")
        desc_lines.append(line.vin or "")
        desc_lines.append("Engine number:")
        desc_lines.append("")  # blank — no engine number in proforma
        desc_lines.append(f"Culoare: {line.culoare}")

        # Build comanda line with anexa ref
        comanda_text = f"Comanda: {line.comanda}"
        if line.anexa_ref:
            comanda_text += f" / {line.anexa_ref}"
        desc_lines.append(comanda_text)

        # Numeric columns on first desc line
        c.drawString(LM + 78 * mm, y, "buc")
        c.drawRightString(LM + 105 * mm, y, "1")
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

        # ── Total ──
        y -= 12 * mm
        c.line(LM, y + 6 * mm, RM, y + 6 * mm)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(LM, y, "PRICE")
        c.drawRightString(RM, y, f"{fmt_us(line.advance)} EUR")

        # ── Footer ──
        y -= 18 * mm
        c.setFont("Helvetica", 9.5)
        c.drawString(LM, y, f"Intocmit de {self.intocmit_de}")

    def render_all_to_bytes(self, lines: list[OrderLine], start_no: int) -> bytes:
        """Render all proformas and return PDF as bytes."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        for i, line in enumerate(lines):
            inv_no = (line.start_no if line.start_no is not None else start_no) + i
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
