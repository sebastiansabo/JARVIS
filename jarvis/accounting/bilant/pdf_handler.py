"""Bilant PDF Handler — generate ANAF-styled PDF from bilant data using fpdf2.

Produces a portrait A4 PDF mimicking the ANAF F10 bilant layout:
- Header with company name, CIF, period
- 4-column table: Nr.rd | Description | C1 (prior year) | C2 (current year)
- Bold for totals/sections, indented sub-items
- Signature footer
"""

import io
import os
import unicodedata
import logging
from fpdf import FPDF

logger = logging.getLogger('jarvis.bilant.pdf_handler')

# TTF font search paths (Linux/DO + macOS fallbacks)
_FONT_SEARCH = {
    'regular': [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ],
    'bold': [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    ],
}


def _find_font(style='regular'):
    for path in _FONT_SEARCH.get(style, []):
        if os.path.exists(path):
            return path
    return None


def _strip_diacritics(text):
    """Remove diacritics and replace non-Latin-1 characters for Helvetica fallback."""
    text = str(text)
    # Replace common non-Latin-1 characters first
    replacements = {'—': '-', '–': '-', '\u2018': "'", '\u2019': "'",
                    '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u00a0': ' '}
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Strip combining diacritical marks
    nfkd = unicodedata.normalize('NFKD', text)
    result = ''.join(c for c in nfkd if not unicodedata.combining(c))
    # Final safety: drop any remaining non-Latin-1 characters
    return result.encode('latin-1', errors='replace').decode('latin-1')


def _fmt_number(val):
    """Format number Romanian-style (dot separator, no decimals)."""
    if val is None or val == '' or val == 0:
        return ''
    try:
        n = float(val)
        if n == 0:
            return ''
        # Format with dot thousands separator
        formatted = f'{abs(n):,.0f}'.replace(',', '.')
        return f'-{formatted}' if n < 0 else formatted
    except (ValueError, TypeError):
        return ''


class BilantPDF(FPDF):
    """Custom FPDF subclass for ANAF-styled bilant output."""

    def __init__(self, generation):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.generation = generation
        self._unicode = False
        self._font_family = 'Helvetica'
        self._setup_fonts()

    def _setup_fonts(self):
        regular = _find_font('regular')
        bold = _find_font('bold')
        if regular:
            try:
                self.add_font('bilant', '', regular)
                if bold:
                    self.add_font('bilant', 'B', bold)
                else:
                    self.add_font('bilant', 'B', regular)
                self._unicode = True
                self._font_family = 'bilant'
                logger.debug('Using Unicode font: %s', regular)
            except Exception:
                logger.debug('Failed to load Unicode font, using Helvetica')
        else:
            logger.debug('No Unicode font found, using Helvetica with diacritic stripping')

    def _t(self, text):
        """Return text, stripping diacritics if no Unicode font available."""
        if self._unicode:
            return str(text) if text else ''
        return _strip_diacritics(text) if text else ''

    def header(self):
        gen = self.generation
        f = self._font_family
        self.set_font(f, 'B', 14)
        self.cell(0, 8, self._t('BILANT'), align='C', new_x='LMARGIN', new_y='NEXT')
        self.set_font(f, '', 9)
        company = gen.get('company_name', '')
        period = gen.get('period_label', '')
        self.cell(0, 5, self._t(f'{company} — {period}'), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font(self._font_family, '', 7)
        self.cell(0, 10, f'Pagina {self.page_no()}/{{nb}}', align='C')


def generate_bilant_pdf(generation, results, prior_results=None):
    """Generate ANAF-styled PDF from bilant generation data.

    Args:
        generation: dict with company_name, period_label, period_date, etc.
        results: list of result dicts (nr_rd, description, value, row_type, is_bold, indent_level)
        prior_results: optional dict {nr_rd: value} for C1 (prior year) column

    Returns:
        io.BytesIO containing the PDF
    """
    pdf = BilantPDF(generation)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)

    f = pdf._font_family

    # Column widths: A4 = 210mm, margins 10mm each = 190mm usable
    col_w = [12, 120, 29, 29]
    row_h = 5

    # Table header
    pdf.set_font(f, 'B', 7)
    pdf.set_fill_color(37, 99, 235)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(['Nr.rd', 'Denumirea elementului', 'Sold C1', 'Sold C2']):
        pdf.cell(col_w[i], row_h + 2, pdf._t(h), border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    # Table body
    for r in results:
        nr_rd = r.get('nr_rd', '') or ''
        desc = r.get('description', '') or ''
        value = r.get('value', 0) or 0
        is_bold = r.get('is_bold') or r.get('row_type') in ('total', 'section')
        indent = r.get('indent_level', 0)
        row_type = r.get('row_type', 'data')

        # C1 from prior period
        c1_val = prior_results.get(nr_rd, 0) if prior_results and nr_rd else 0

        # Section headers span full width
        if row_type == 'section':
            pdf.set_font(f, 'B', 7)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(sum(col_w), row_h, pdf._t(f'  {desc}'), border='LR', fill=True)
            pdf.ln()
            continue

        pdf.set_font(f, 'B' if is_bold else '', 7)

        desc_text = ('   ' * indent + desc) if indent else desc

        pdf.cell(col_w[0], row_h, pdf._t(nr_rd), border='LR', align='C')
        pdf.cell(col_w[1], row_h, pdf._t(desc_text[:85]), border='LR')
        pdf.cell(col_w[2], row_h, _fmt_number(c1_val), border='LR', align='R')
        pdf.cell(col_w[3], row_h, _fmt_number(value), border='LR', align='R')
        pdf.ln()

    # Bottom border
    pdf.cell(sum(col_w), 0, '', border='T')
    pdf.ln(12)

    # Signature area
    pdf.set_font(f, '', 8)
    pdf.cell(95, 6, pdf._t('Administrator,'))
    pdf.cell(95, 6, pdf._t('Intocmit,'))
    pdf.ln(15)
    pdf.cell(95, 6, '_________________________')
    pdf.cell(95, 6, '_________________________')

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return output
