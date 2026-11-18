"""Regression test for the storno-avans PDF losing its PRICE total.

Bug: `_render_storno_page` laid out one car's reversed advances on a single A4
page with absolute, ever-decreasing y and no pagination. A car with 3+ reversed
advances (e.g. Aurento / CTR-338, storno 9105181: 10% + 15% + 75%) pushed the
`PRICE` total and the `Intocmit de` signatory below the bottom edge (y < 0), so
they rendered off-page and were invisible on the printed invoice.

These tests render the storno page for N = 1..6 reversed advances and assert —
against the real PDF bytes, via a PyPDF2 text-position visitor — that the PRICE
label, the grand-total amount, and the signatory are all drawn inside the
visible page area (0 <= y <= page_height), and that NO text is ever drawn below
the bottom edge.
"""
import importlib.util
import io
import os
import sys
import types

import pytest

import PyPDF2
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rc

# Load the renderer directly from its file. Importing it via the package
# (`accounting.facturare...`) runs the facturare __init__ → routes → core →
# migrations/init_db import cascade, which both needs a live DB and trips a
# known cold-import circular-import trap. The renderer itself depends only on
# `..models.OrderLine` + reportlab, so we load just those two files under
# synthetic parent packages — hermetic, DB-free, and stable.
_FACTURARE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "accounting", "facturare",
)
for _pkg in ("jarvis", "jarvis.accounting", "jarvis.accounting.facturare",
             "jarvis.accounting.facturare.generators"):
    if _pkg not in sys.modules:
        _m = types.ModuleType(_pkg)
        _m.__path__ = []  # mark as a package so relative imports resolve
        sys.modules[_pkg] = _m


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


_load("jarvis.accounting.facturare.models", os.path.join(_FACTURARE, "models.py"))
_pf = _load("jarvis.accounting.facturare.generators.proforma_pdf",
            os.path.join(_FACTURARE, "generators", "proforma_pdf.py"))
ProformaPdfRenderer = _pf.ProformaPdfRenderer
fmt_us = _pf.fmt_us
OrderLine = sys.modules["jarvis.accounting.facturare.models"].OrderLine

PAGE_H = A4[1]

# A deliberately *large* supplier block (AW International) — the real-world case
# that overflows. Fewer supplier lines would mask the bug.
SUPPLIER = {
    "name": "Autoworld INTERNATIONAL S.R.L.",
    "address_lines": ["Calea Floresti 145", "Cluj-Napoca, jud. Cluj", "Romania"],
    "reg_no": "J2024002657125", "vat": "RO 50186890",
    "iban": "RO88 BACX 0000 0027 0096 8001", "bank": "Unicredit Bank",
    "swift": "BACXROBU",
}
CUSTOMER = {
    "name": "AURENTO GMBH",
    "address_lines": ["Steinbecker Meile 1", "Wuppertal", "Germania"],
    "vat": "DE348588948",
}
# Real advances from storno 9105181, extended with extra slices for N>3.
ADVANCES = [
    ("Ref: Factura Nr. 9102714 / 03.03.2026 (10%)", -1732.00, 5.0972),
    ("Ref: Factura Nr. 9104421 / 24.09.2026 (15%)", -2598.00, 5.2788),
    ("Ref: Factura Nr. 9105019 / 03.11.2026 (75%)", -12991.00, 5.3403),
    ("Ref: Factura Nr. 9105100 / 04.11.2026 (5%)", -866.00, 5.34),
    ("Ref: Factura Nr. 9105101 / 05.11.2026 (5%)", -866.00, 5.34),
    ("Ref: Factura Nr. 9105102 / 06.11.2026 (5%)", -866.00, 5.34),
]


def _items(n):
    """One car (same model/VIN/colour), n reversed advances — mirrors the route."""
    return [
        OrderLine(
            comanda=507823, model="POLO PRIME 1.0 TSI DSG",
            culoare="Negru (deep black pearlescent)",
            list_price=0.0, selling_price=17320.0, advance=adv, rest=None,
            vin="WVWZZZAW8VU052335", qty=1,
            anexa_ref="Anexa 1 / Contract CTR-338",
            storno_description=desc, kurs=kurs,
        )
        for desc, adv, kurs in ADVANCES[:n]
    ]


def _render(n, note="Reverses invoices for 1 vehicle(s)"):
    """Render a one-car storno exactly as api_generate_pdf does (per-car page)."""
    renderer = ProformaPdfRenderer(
        supplier=SUPPLIER, customer=CUSTOMER, invoice_date="2026-11-16",
        intocmit_de="Ilona Foszto",
        title_lines=["FACTURA STORNO", "STORNO INVOICE"],
        description_prefix="1. STORNO ADVANCE",
        note=note,
    )
    buf = io.BytesIO()
    c = rc.Canvas(buf, pagesize=A4)
    renderer._render_storno_page(c, 9105181, _items(n))
    c.showPage()
    c.save()
    return buf.getvalue()


def _text_positions(pdf_bytes):
    """[(text, y_pt)] for every text draw across all pages, via PyPDF2 visitor."""
    hits = []

    def visitor(text, cm, tm, font_dict, font_size):
        if text and text.strip():
            hits.append((text.strip(), tm[5]))

    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages:
        page.extract_text(visitor_text=visitor)
    return hits


def _visible(hits, needle):
    """Return hits containing `needle` that are drawn inside the page area."""
    return [(t, y) for (t, y) in hits if needle in t and 0 <= y <= PAGE_H]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 6])
def test_price_total_is_visible_for_n_advances(n):
    hits = _text_positions(_render(n))

    # The PRICE label must be drawn on a visible part of some page.
    assert _visible(hits, "PRICE"), f"PRICE total off-page for N={n} advances"

    # The grand-total amount (sum of the reversed advances) must be visible too.
    grand_total = sum(adv for _, adv, _ in ADVANCES[:n])
    total_str = fmt_us(grand_total)  # e.g. "-17,321.00"
    assert _visible(hits, total_str), f"total {total_str} off-page for N={n}"

    # And the signatory line.
    assert _visible(hits, "Intocmit de"), f"signatory off-page for N={n}"


@pytest.mark.parametrize("n", [1, 2, 3, 4, 6])
def test_no_text_drawn_below_bottom_edge(n):
    hits = _text_positions(_render(n))
    clipped = [(t, y) for (t, y) in hits if y < 0]
    assert not clipped, f"text clipped below page for N={n}: {clipped[:5]}"


@pytest.mark.parametrize("note_lines", [1, 3, 5, 8])
@pytest.mark.parametrize("n", [1, 3, 6])
def test_price_total_visible_with_multiline_note(n, note_lines):
    """The footer reserve must account for the (user-editable, possibly
    multi-line) invoice note — a long note must not push the total/signatory
    off the page."""
    note = "\n".join(f"Nota linia {i + 1}" for i in range(note_lines))
    hits = _text_positions(_render(n, note=note))
    assert _visible(hits, "PRICE"), f"PRICE off-page: N={n}, note_lines={note_lines}"
    assert _visible(hits, "Intocmit de"), f"signatory off-page: N={n}, note_lines={note_lines}"
    assert not [(t, y) for (t, y) in hits if y < 0], \
        f"text clipped: N={n}, note_lines={note_lines}"


def test_many_advances_paginate_with_total_on_last_page():
    """A pathological car with many reversed advances overflows one page; the
    renderer must break to continuation page(s) and still land the total on a
    visible page, with nothing clipped off the bottom."""
    renderer = ProformaPdfRenderer(
        supplier=SUPPLIER, customer=CUSTOMER, invoice_date="2026-11-16",
        intocmit_de="Ilona Foszto",
        title_lines=["FACTURA STORNO", "STORNO INVOICE"],
        description_prefix="1. STORNO ADVANCE",
        note="Reverses invoices for 1 vehicle(s)",
    )
    items = [
        OrderLine(
            comanda=507823, model="POLO PRIME 1.0 TSI DSG",
            culoare="Negru (deep black pearlescent)",
            list_price=0.0, selling_price=17320.0, advance=-100.0 * (i + 1),
            rest=None, vin="WVWZZZAW8VU052335", qty=1,
            anexa_ref="Anexa 1 / Contract CTR-338",
            storno_description=f"Ref: Factura Nr. {9100000 + i} / 01.11.2026 ({i + 1}%)",
            kurs=5.3,
        )
        for i in range(14)
    ]
    buf = io.BytesIO()
    c = rc.Canvas(buf, pagesize=A4)
    renderer._render_storno_page(c, 9105181, items)
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) > 1, "14 advances should overflow onto a continuation page"

    hits = _text_positions(pdf_bytes)
    assert not [(t, y) for (t, y) in hits if y < 0], "text clipped below page"
    assert _visible(hits, "PRICE"), "PRICE total off-page"
    expected_total = fmt_us(sum(-100.0 * (i + 1) for i in range(14)))
    assert _visible(hits, expected_total), f"total {expected_total} off-page"
    assert _visible(hits, "Intocmit de"), "signatory off-page"
    # Continuation pages carry a '(cont.)' marker so the reader isn't orphaned.
    assert _visible(hits, "(cont.)"), "missing continuation header"
