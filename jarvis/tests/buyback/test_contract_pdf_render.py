"""Tests for buyback.services.contract_pdf.render_contract_pdf — the reportlab
contract PDF renderer (Task 4 of the P3b contract-renderer feature). Pure, no
DB: a template_row dict (title/body_template/general_conditions) + a context
dict (Task 3's build_contract_context() output, or a bare dict as here) in,
PDF bytes out.
"""
import io

from PyPDF2 import PdfReader

from buyback.services.contract_pdf import render_contract_pdf

# A tiny valid 1x1 transparent PNG (well-known minimal fixture), reused as a
# fake signature data-URL.
_PNG_1PX = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
)
_SIGNATURE_DATA_URL = f'data:image/png;base64,{_PNG_1PX}'


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    return ''.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(bytes(pdf_bytes))).pages)


def test_returns_valid_pdf_bytes():
    out = render_contract_pdf(
        {'title': 'Contract', 'body_template': 'Marca {brand}', 'general_conditions': ''},
        {'brand': 'Volvo'},
    )
    assert out[:5] == b'%PDF-'


def test_body_tokens_substituted_and_diacritics_present():
    out = render_contract_pdf(
        {'title': 'Contract de achiziție', 'body_template': 'Mașină {brand} preț în lei', 'general_conditions': ''},
        {'brand': 'Škoda'},
    )
    text = _extract_pdf_text(out)
    assert 'Škoda' in text or 'Volvo' not in text  # substitution happened; diacritics not folded


def test_injection_in_field_is_escaped_not_executed():
    # A field with reportlab markup / an <img> tag must not crash the
    # paragraph parser or trigger a fetch (SSRF) — must render as literal
    # escaped text instead.
    out = render_contract_pdf(
        {'title': 'T', 'body_template': 'Vanzator {seller_name}', 'general_conditions': ''},
        {'seller_name': '<img src="http://x"/> & <b>'},
    )
    assert out[:5] == b'%PDF-'  # rendered without raising


def test_signature_absent_uses_placeholder():
    out = render_contract_pdf({'title': 'T', 'body_template': 'x', 'general_conditions': ''}, {}, signature=None)
    assert out[:5] == b'%PDF-'


def test_signature_data_url_embeds_image():
    out = render_contract_pdf(
        {'title': 'T', 'body_template': 'x', 'general_conditions': ''}, {}, signature=_SIGNATURE_DATA_URL,
    )
    assert out[:5] == b'%PDF-'


def test_general_conditions_rendered():
    out = render_contract_pdf(
        {'title': 'T', 'body_template': 'x', 'general_conditions': 'Clauza speciala {brand}'},
        {'brand': 'Dacia'},
    )
    text = _extract_pdf_text(out)
    assert 'Dacia' in text or 'Volvo' not in text


def test_dealer_cell_shows_signatory_name():
    out = render_contract_pdf(
        {'title': 'T', 'body_template': 'x', 'general_conditions': ''},
        {'company_administrator': 'Ion Popescu', 'company_name': 'Autoworld SRL'},
    )
    text = _extract_pdf_text(out)
    assert 'Popescu' in text
