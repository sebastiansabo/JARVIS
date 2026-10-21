"""P3c Task 2 — render_contract_pdf_from_parts renders ALREADY-FINAL text
(no token substitution), the path the inline-edit flow uses. Pure, no DB."""
import io

from buyback.services.contract_pdf import render_contract_pdf_from_parts
from PyPDF2 import PdfReader


def _text(pdf: bytes) -> str:
    return "\n".join((p.extract_text() or '') for p in PdfReader(io.BytesIO(pdf)).pages)


def test_from_parts_renders_final_text_without_substitution():
    # A {token}-looking string in the body must survive verbatim — from_parts
    # does NOT run render_contract_template, so nothing is substituted.
    pdf = render_contract_pdf_from_parts(
        'Contract achiziție', 'Mașină {already} cu ăâîșț și preț', 'Condiții GDPR',
        signatory='Ion Administrator',
    )
    assert pdf[:5] == b'%PDF-'
    text = _text(pdf)
    assert '{already}' in text          # not substituted
    assert 'ă' in text or 'â' in text   # diacritics survive the font path


def test_from_parts_escapes_markup_no_crash():
    pdf = render_contract_pdf_from_parts('T', 'Vânzător <img src="http://x"/> & <b>x</b>', '')
    assert pdf[:5] == b'%PDF-'


def test_from_parts_empty_body_still_valid_pdf():
    pdf = render_contract_pdf_from_parts('T', '', '')
    assert pdf[:5] == b'%PDF-'
