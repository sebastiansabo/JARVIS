"""Generate FACTURA / PROFORMA INVOICE PDFs using reportlab."""
import io
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
        elif line.advance < 0:
            c.drawCentredString(W / 2, y, "FACTURA STORNO")
            y -= 5 * mm
            c.drawCentredString(W / 2, y, "STORNO INVOICE")
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

    # ── Collapsed (single invoice, multiple positions) ────────

    def render_collapsed_to_bytes(self, lines: list[OrderLine]) -> bytes:
        """Render all lines as a single invoice with a table."""
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        inv_no = self.cfg.invoice.start_no
        self._render_collapsed_pages(c, inv_no, lines)
        c.save()
        return buf.getvalue()

    def _build_columns(self, lines: list[OrderLine]) -> list[tuple[str, str, float]]:
        """Build dynamic column list based on which fields have data."""
        has_vin = any(l.vin for l in lines)
        has_culoare = any(l.culoare for l in lines)

        cols: list[tuple[str, str, float]] = [
            ("Nr.", "nr", 8),
            ("Comanda", "comanda", 18),
            ("Model", "model", 0),  # flex — gets remaining space
        ]
        if has_vin:
            cols.append(("VIN", "vin", 38))
        if has_culoare:
            cols.append(("Culoare", "culoare", 22))
        cols.append(("Qty", "qty", 10))
        currency = self.cfg.fx.currency
        cols.append((f"Amount ({currency})", "amount", 28))

        # Calculate model column width (flex)
        fixed = sum(w for _, _, w in cols if w > 0)
        page_w = (A4[0] - 2 * 18 * mm) / mm
        model_w = page_w - fixed
        cols = [(h, k, model_w if k == "model" else w) for h, k, w in cols]

        return cols

    def _render_collapsed_pages(self, c: canvas.Canvas, inv_no: int, lines: list[OrderLine]):
        """Draw collapsed invoice — splits across pages if needed."""
        cfg = self.cfg
        W, H = A4
        LM = 18 * mm
        RM = W - 18 * mm

        ROW_HEIGHT = 4.2 * mm
        MAX_ROWS_FIRST_PAGE = 18
        MAX_ROWS_CONT_PAGE = 35

        total = sum(l.advance for l in lines)
        cols = self._build_columns(lines)
        currency = cfg.fx.currency
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
                c.drawString(LM, y, f"INVOICE No:{inv_no} (continued)")
                y -= 10 * mm
                y = self._draw_table_header(c, y, LM, RM, cols)
                max_rows = MAX_ROWS_CONT_PAGE

            is_last_batch = (line_idx + max_rows >= len(lines))
            rows_this_page = len(lines) - line_idx if is_last_batch else max_rows

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
                    elif key == "qty":
                        c.drawRightString(x + w * mm - 2 * mm, row_y, "1")
                    elif key == "amount":
                        c.drawRightString(x + w * mm - 2 * mm, row_y, fmt_eur(line.advance))
                    x += w * mm
                line_idx += 1

            y = y - (rows_this_page * ROW_HEIGHT) - 3 * mm

            # Draw total + footer only on last page
            if is_last_batch:
                c.setLineWidth(0.4)
                c.line(LM, y + 2 * mm, RM, y + 2 * mm)
                y -= 5 * mm
                c.setFont("Helvetica-Bold", 11)
                c.drawString(LM, y, "PRICE")
                c.drawRightString(RM - 2 * mm, y, f"{fmt_eur(total)} {currency}")

                y -= 10 * mm
                c.setFont("Helvetica", 9)
                c.drawString(LM, y, "Scutire conform art. 138 din Directiva 2006/112/CE")
                y -= 4.5 * mm
                c.drawString(LM, y, "Livrare Ex Works")
                y -= 10 * mm
                c.drawString(LM, y, f"Intocmit de {cfg.invoice.intocmit_de}")

            c.showPage()
            page_num += 1

    def _draw_collapsed_header(self, c: canvas.Canvas, inv_no: int,
                               W: float, H: float, LM: float, RM: float,
                               cols: list[tuple[str, str, float]]) -> float:
        """Draw the header (logo, title, supplier/customer) and return Y for table."""
        cfg = self.cfg

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
            c.drawCentredString(W / 2, H - 25 * mm, cfg.supplier.name.split()[0])
            y = H - 32 * mm

        # underline rule
        c.setStrokeColorRGB(0.65, 0.78, 0.30)
        c.setLineWidth(0.6)
        c.line(LM, y, RM, y)
        c.setStrokeColorRGB(0, 0, 0)

        # ── Title ──
        y -= 14 * mm
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(W / 2, y, "FACTURA")
        y -= 5 * mm
        c.drawCentredString(W / 2, y, "INVOICE")
        y -= 5 * mm
        c.drawCentredString(W / 2, y, f"No:{inv_no}")
        y -= 5 * mm

        date_str = cfg.invoice.date.strftime("%d.%m.%Y")
        c.drawCentredString(W / 2, y, f"Data/ Date: {date_str}")

        # ── Supplier / Customer (compact) ──
        y -= 10 * mm
        col_l = LM
        col_r = LM + 95 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(col_l, y, "Furnizor/ Supplier:")
        c.drawString(col_r, y, "Cumparator/ Customer:")

        y -= 5 * mm
        c.drawString(col_l, y, cfg.supplier.name)
        c.drawString(col_r, y, cfg.customer.name)

        c.setFont("Helvetica", 8.5)
        supplier_lines = list(cfg.supplier.address_lines)
        if cfg.supplier.vat:
            supplier_lines.append(f"VAT: {cfg.supplier.vat}")
        if cfg.supplier.iban:
            supplier_lines.append(f"IBAN: {cfg.supplier.iban}")

        customer_lines = list(cfg.customer.address_lines)
        if cfg.customer.vat:
            customer_lines.append(cfg.customer.vat)

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
