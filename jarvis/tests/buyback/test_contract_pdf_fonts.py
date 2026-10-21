"""Tests for the diacritics-safe PDF primitives in buyback.services.contract_pdf.

These primitives are the foundation of the contract PDF renderer (P3b): a
Unicode TrueType font registration (so Romanian diacritics render for real,
instead of being ASCII-folded like every other reportlab PDF in this repo)
and an HTML-escaping text helper that keeps those diacritics intact.
"""
import io

from buyback.services.contract_pdf import FONT_BOLD, FONT_REGULAR, _ptext, _register_fonts


def test_register_fonts_returns_dejavu_names():
    reg, bold = _register_fonts()
    assert reg == 'DejaVuSans' and bold == 'DejaVuSans-Bold'


def test_register_fonts_matches_module_constants():
    assert FONT_REGULAR == 'DejaVuSans'
    assert FONT_BOLD == 'DejaVuSans-Bold'


def test_register_fonts_is_idempotent():
    # Calling repeatedly must not raise (e.g. "font already registered").
    first = _register_fonts()
    second = _register_fonts()
    third = _register_fonts()
    assert first == second == third == ('DejaVuSans', 'DejaVuSans-Bold')


def test_ptext_escapes_markup_but_keeps_diacritics():
    assert _ptext('Ștefan & <b>X</b>') == 'Ștefan &amp; &lt;b&gt;X&lt;/b&gt;'


def test_ptext_handles_none():
    assert _ptext(None) == ''


def test_ptext_preserves_all_romanian_diacritics():
    raw = 'ăâîșțĂÂÎȚȘ'
    escaped = _ptext(raw)
    for ch in raw:
        assert ch in escaped, f"diacritic {ch!r} was folded/lost by _ptext"


def _render_probe_pdf(text: str) -> bytes:
    """Minimal one-paragraph PDF using the registered DejaVu font. Test-local
    helper only — production code must not expose a PDF-building helper."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    regular, _bold = _register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    styles['Normal'].fontName = regular
    doc.build([Paragraph(_ptext(text), styles['Normal'])])
    return buf.getvalue()


def test_diacritics_survive_in_a_rendered_pdf():
    pdf = _render_probe_pdf('Mașină cu preț în lei: ăâîșț')
    # Two assertions that must always hold, regardless of extraction
    # reliability: the renderer produced a real, non-empty PDF using the
    # Unicode font (no crash from unescaped markup or a missing font), and
    # _ptext itself did not ASCII-fold the diacritics before they ever
    # reached reportlab — that folding is the regression this task exists to
    # prevent.
    assert isinstance(pdf, (bytes, bytearray))
    assert bytes(pdf[:4]) == b'%PDF'
    assert len(pdf) > 500
    assert _ptext('ăâîșț') == 'ăâîșț'

    # Extra verification: PyPDF2 extraction of the subset-embedded TTF is
    # confirmed reliable in this environment (verified manually), so also
    # pin that the glyphs round-trip through a real PDF reader. If this ever
    # proves flaky in CI (lossy subsetter/CMap on another platform), the two
    # assertions above are the ones that matter and this block alone should
    # be relaxed/removed rather than the whole test.
    from PyPDF2 import PdfReader
    extracted = ''.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(bytes(pdf))).pages)
    assert 'ș' in extracted and 'ț' in extracted and 'ă' in extracted
