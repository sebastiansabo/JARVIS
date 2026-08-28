"""The per-session contract PDF must NOT carry the auto-generation date footer.

Regression guard for the removal of 'Document generat automat • <date>' from the
legal + service contract PDFs.
"""
import PyPDF2

from foi_parcurs.services import pdf_service as ps
from test_foi_parcurs_service_context import _fake_service_contract


def _pdf_text(path):
    reader = PyPDF2.PdfReader(path)
    return '\n'.join((page.extract_text() or '') for page in reader.pages)


def test_legal_pdf_has_no_generation_footer():
    out = ps.generate_legal_pdf(_fake_service_contract(contract_id='FP-FOOTER-LEGAL'))
    text = _pdf_text(out)
    # Sanity: it really is the contract PDF…
    assert 'Contract Driving Auto' in text
    # …and the generation-date footer is gone.
    assert 'Document generat automat' not in text
