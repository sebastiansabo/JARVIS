"""Regression test: Meta ads invoice parser must not lose the first campaign
of a non-first page.

Bug: ``extract_text_from_pdf`` concatenated PyPDF2 pages with no separator
(``text += page.extract_text()``). PyPDF2 does not append a trailing newline,
so the last line of page N glued onto the first line of page N+1, e.g.::

    Q7 Q8 (-21%) 166 de Afişări 6,31 RONQ5 Magyar

``parse_meta_invoice`` then treated that merged string as the campaign name for
page 2's first campaign (``Q5 Magyar``). Because the merged text contains
``de Afişări`` (a skip keyword), the whole campaign was silently dropped — the
Cost Distribution total came up short by exactly that campaign's value.

The fix joins pages with a newline. These tests pin that behaviour with no real
PDF (the source invoice carries financial data) — PdfReader is faked so the two
page texts reproduce the exact boundary.

No database required.
"""
import os
import sys

import pytest

# Ensure the jarvis package root is on sys.path.
JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

from accounting.bugetare import bulk_processor  # noqa: E402
from accounting.bugetare.bulk_processor import (  # noqa: E402
    extract_text_from_pdf,
    parse_meta_invoice,
)

# Page 1 ends with a sub-item line (contains "de Afişări") and — crucially — no
# trailing newline, mirroring PyPDF2's real output.
_PAGE1 = (
    "Campanii\n"
    "Q7 Q8 (-21%)\n"
    "12 sept. 2026, 00:00 - 16 sept. 2026, 23:596,31 RON\n"
    "Q7 Q8 (-21%) 166 de Afişări 6,31 RON"
)
# Page 2 starts with a campaign whose name is NOT one of the prefixes the parser
# pre-splits ([CA]/Postare:/Stoc_/GENERARE), so it depends entirely on the page
# join inserting a newline.
_PAGE2 = (
    "Q5 Magyar\n"
    "12 sept. 2026, 00:00 - 16 sept. 2026, 23:593,00 RON\n"
    "Q5 Magyar 126 de Afişări 3,00 RON\n"
    "(S) Stoc AAP\n"
    "12 sept. 2026, 00:00 - 16 sept. 2026, 23:598,87 RON\n"
    "(S) Stoc AAP 1.383 de Afişări 8,87 RON"
)


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakeReader:
    def __init__(self, _f):
        self.pages = [_FakePage(_PAGE1), _FakePage(_PAGE2)]


@pytest.fixture
def pdf_path(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_processor.PyPDF2, "PdfReader", _FakeReader)
    p = tmp_path / "meta.pdf"
    p.write_bytes(b"%PDF-1.4 fake")  # content ignored — PdfReader is faked
    return str(p)


def test_pages_joined_with_separator(pdf_path):
    """The glued form must never appear — pages get a newline between them."""
    text = extract_text_from_pdf(pdf_path)
    assert "RONQ5 Magyar" not in text
    assert "6,31 RON\nQ5 Magyar" in text


def test_first_campaign_of_second_page_is_parsed(pdf_path):
    items = parse_meta_invoice(extract_text_from_pdf(pdf_path))["items"]

    # The campaign that used to be dropped is present, with a clean name.
    assert "Q5 Magyar" in items
    assert items["Q5 Magyar"] == pytest.approx(3.00)

    # Neighbours on either side of the page break still parse.
    assert items["Q7 Q8 (-21%)"] == pytest.approx(6.31)
    assert items["(S) Stoc AAP"] == pytest.approx(8.87)

    # No corrupted merged key leaked through.
    assert not any("Magyar" in name and name.strip() != "Q5 Magyar" for name in items)
