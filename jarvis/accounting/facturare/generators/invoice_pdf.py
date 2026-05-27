"""Generate FACTURA / PROFORMA INVOICE PDFs using reportlab."""
import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from ..config import JobConfig
from ..models import OrderLine

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_LOGO = ASSETS_DIR / "logo.jpg"


def fmt_eur(val: float) -> str:
    """Format number as Romanian style: 380.400,00"""
    s = f"{float(val):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


class InvoicePdfRenderer:
    """Renders invoice/proforma PDFs from config + OrderLines."""

    def __init__(self, cfg: JobConfig):
        self.cfg = cfg
        self.logo_path = DEFAULT_LOGO if DEFAULT_LOGO.exists() else None

    def render_one(self, c: canvas.Canvas, inv_no: int, line: OrderLine):
        """Draw a single invoice page on the canvas."""
        cfg = self.cfg
        W, H = A4
        LM = 18 * mm
        RM = W - 18 * mm
        is_storno = line.qty < 0

        # ---- Logo ----
        if self.logo_path:
            img = ImageReader(str(self.logo_path))
            iw, ih = img.getSize()
            tw = 55 * mm
            th = tw * ih / iw
            c.drawImage(img, (W - tw) / 2, H - 22 * mm - th, tw, th, mask='auto')
            y = H - 24 * mm - th
        else:
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(W / 2, H - 25 * mm, cfg.supplier.name.split()[0])
            y = H - 32 * mm

        # underline rule
        c.setStrokeColorRGB(0.65, 0.78, 0.30)
        c.setLineWidth(0.6)
        c.line(LM, y, RM, y)
        c.setStrokeColorRGB(0, 0, 0)

        # ---- Title ----
        y -= 18 * mm
        c.setFont("Helvetica-Bold", 13)
        if cfg.invoice.kind == "proforma":
            c.drawCentredString(W / 2, y, "FACTURA PROFORMA")
            y -= 5 * mm
            c.drawCentredString(W / 2, y, "PROFORMA INVOICE")
        else:
            title = "FACTURA STORNO" if is_storno else "FACTURA"
            c.drawCentredString(W / 2, y, title)
            y -= 5 * mm
            title2 = "STORNO INVOICE" if is_storno else "INVOICE"
            c.drawCentredString(W / 2, y, title2)

        y -= 5 * mm
        c.drawCentredString(W / 2, y, f"No:{inv_no}")
        y -= 5 * mm
        date_str = cfg.invoice.date.strftime("%d.%m.%Y")
        c.drawCentredString(W / 2, y, f"Data/ Date: {date_str}")

        # ---- Supplier / Customer ----
        y -= 14 * mm
        col_l = LM
        col_r = LM + 95 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_l, y, "Furnizor/ Supplier:")
        c.drawString(col_r, y, "Cumparator/ Customer:")

        y -= 7 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_l, y, cfg.supplier.name)
        c.drawString(col_r, y, cfg.customer.name)

        c.setFont("Helvetica", 9.5)

        # Supplier lines
        supplier_lines = list(cfg.supplier.address_lines)
        if cfg.supplier.reg_no:
            supplier_lines.append(cfg.supplier.reg_no)
        if cfg.supplier.vat:
            supplier_lines.append(f"VAT-nr: {cfg.supplier.vat}")
        if cfg.supplier.iban:
            supplier_lines.append("Cont/ Account no.:")
            supplier_lines.append(cfg.supplier.iban)
        if cfg.supplier.bank:
            supplier_lines.append(cfg.supplier.bank)
        if cfg.supplier.swift:
            supplier_lines.append(f"SWIFT/BIC: {cfg.supplier.swift}")

        # Customer lines
        customer_lines = list(cfg.customer.address_lines)
        if cfg.customer.vat:
            customer_lines.append("")
            customer_lines.append(cfg.customer.vat)

        yl = y - 5 * mm
        for ln in supplier_lines:
            c.drawString(col_l, yl, ln)
            yl -= 4.5 * mm
        yr = y - 5 * mm
        for ln in customer_lines:
            c.drawString(col_r, yr, ln)
            yr -= 4.5 * mm

        y = min(yl, yr) - 4 * mm

        # ---- Items table header ----
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

        currency = cfg.fx.currency
        headers_bot3 = [
            (currency, LM + 115 * mm),
            (currency, LM + 140 * mm),
            (currency, LM + 160 * mm),
        ]
        for txt, x in headers_bot3:
            c.drawString(x, y - 17 * mm, txt)

        c.line(LM, y - 19 * mm, RM, y - 19 * mm)

        # ---- Item row ----
        y -= 24 * mm
        c.setFont("Helvetica", 9.5)

        has_overrides = line.start_no is not None or line.kurs is not None
        desc_lines = []
        if is_storno and line.storno_description:
            desc_lines.append(f"STORNO ADVANCE INVOICE {line.storno_description}")
        elif not has_overrides or is_storno:
            desc_lines.append(cfg.invoice.description_prefix)
        desc_lines.extend([
            str(line.model).upper(),
            f"Culoare: {line.culoare}",
        ])
        if line.vin:
            desc_lines.append(f"VIN: {line.vin}")
        desc_lines.append(f"Comanda: {line.comanda} / {cfg.contract.anexa_ref}")

        qty = line.qty
        unit_price = abs(line.advance)
        total_value = line.advance * qty  # negative when storno

        c.drawString(LM + 78 * mm, y, "buc")
        c.drawRightString(LM + 105 * mm, y, str(qty))
        c.drawRightString(LM + 138 * mm, y, fmt_eur(unit_price))
        c.drawRightString(LM + 158 * mm, y, fmt_eur(total_value))

        yl = y
        for ln in desc_lines:
            c.drawString(LM, yl, ln)
            yl -= 4.7 * mm

        y = yl - 3 * mm
        c.drawString(LM, y, "Scutire conform art. 138 din Directiva 2006/112/CE")
        y -= 4.7 * mm
        c.drawString(LM, y, "Livrare Ex Works")

        # ---- Total ----
        y -= 12 * mm
        c.line(LM, y + 6 * mm, RM, y + 6 * mm)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(LM, y, "PRICE")
        c.drawRightString(RM, y, f"{fmt_eur(total_value)} {currency}")

        # ---- Footer ----
        y -= 18 * mm
        c.setFont("Helvetica", 9.5)
        c.drawString(LM, y, f"Intocmit de {cfg.invoice.intocmit_de}")

    def _resolve_inv_no(self, idx: int, line: OrderLine) -> int:
        """Per-row invoice number override, or fall back to sequential."""
        return line.start_no if line.start_no is not None else self.cfg.invoice.start_no + idx

    def render_all(self, lines: list[OrderLine], out_path: Path) -> Path:
        """Render all invoices into a single multi-page PDF."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(out_path), pagesize=A4)
        for i, line in enumerate(lines):
            inv_no = self._resolve_inv_no(i, line)
            self.render_one(c, inv_no, line)
            c.showPage()
        c.save()
        return out_path

    def render_all_to_bytes(self, lines: list[OrderLine]) -> bytes:
        """Render all invoices and return PDF as bytes (for web download)."""
        import io
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        for i, line in enumerate(lines):
            inv_no = self._resolve_inv_no(i, line)
            self.render_one(c, inv_no, line)
            c.showPage()
        c.save()
        return buf.getvalue()

    def render_single(self, line: OrderLine, inv_no: int, out_path: Path) -> Path:
        """Render a single invoice PDF."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(out_path), pagesize=A4)
        self.render_one(c, inv_no, line)
        c.showPage()
        c.save()
        return out_path
