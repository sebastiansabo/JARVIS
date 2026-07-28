"""Hermetic tests for Task 7: the anexa-detail display, the document-items
list, and the PDF generator all read stored per-car document numbers
(facturare_document_numbers via get_document_number_map) instead of deriving
`base_no + idx`, with the old derivation preserved as a fallback for
pre-backfill invoices that have no map entry.

Covers:
  1. `_resolve_doc_no` — the tiny shared lookup-with-fallback helper used by
     all three sites (unit-level, no Flask needed).
  2. `api_get_anexa_detail` — asserts `covered_by[].invoice_number` per line.
  3. `api_document_items` — asserts `doc_number` per item.
  4. `api_generate_pdf` — spies on the renderer to capture the `inv_no`
     actually passed to each render call, for both per_car (advance/final)
     and STORNO (reversed-invoice reference + own per-car number) flows.
     `render_single_doc_to_bytes`/individual/`?car=N` fallbacks are covered by
     code inspection (see task-7-report.md) since they share the exact same
     `_resolve_doc_no` call already exercised here.

The route module opens a DB pool at import, so DATABASE_URL must point at a
reachable Postgres (or run under plain pytest, where jarvis/conftest.py mocks
psycopg2 before import). No query actually runs: the module-level `_repo` is
replaced with a fake that returns canned rows.
"""
import os
import sys

import pytest

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

import flask  # noqa: E402

from accounting.facturare import routes_orders  # noqa: E402
from accounting.facturare.generators import proforma_pdf as proforma_pdf_module  # noqa: E402

_app = flask.Flask(__name__)
_app.config["LOGIN_DISABLED"] = True


# ── Canned scenario: 2-car anexa (line ids 10/20) ─────────────────
ANEXA = {"id": 1, "contract_id": 10, "anexa_number": 5}
CONTRACT = {"id": 10, "supplier_id": 100, "customer_id": 200, "contract_ref": "CTR-1"}
LINE_10 = {
    "id": 10, "line_number": 1, "nr_comanda": "111", "vin": None,
    "model": "Model A", "culoare": "", "list_price_eur": 0,
    "selling_price_eur": 10000, "qty": 1,
}
LINE_20 = {
    "id": 20, "line_number": 2, "nr_comanda": "222", "vin": None,
    "model": "Model B", "culoare": "", "list_price_eur": 0,
    "selling_price_eur": 10000, "qty": 1,
}

# Invoice 500: doc_mode=per_car, BOTH cars have a stored number in the map —
# deliberately NOT equal to base_no + idx (9000000 / 9000001) so a test that
# still derives instead of reading the map would fail.
INVOICE_MAPPED = {
    "id": 500, "anexa_id": 1, "invoice_type": "INVOICE", "invoice_state": "ISSUED",
    "sequence_number": 1, "invoice_number": 9000000, "issued_date": "2026-07-20",
    "total_amount_eur": 20000, "total_amount_ron": 0, "kurs_applied": 5.0,
    "currency": "EUR", "intocmit_de": None, "notes": None, "split_mode": "equal",
    "payment_status": "UNPAID",
    "line_ids": [10, 20], "doc_mode": "per_car", "created_at": None,
}
# Invoice 501: doc_mode=per_car, NO stored numbers (pre-backfill) — must fall
# back to base_no + idx (9000010 / 9000011).
INVOICE_UNMAPPED = {
    "id": 501, "anexa_id": 1, "invoice_type": "PROFORMA", "invoice_state": "ISSUED",
    "sequence_number": 2, "invoice_number": 9000010, "issued_date": "2026-07-21",
    "total_amount_eur": 20000, "total_amount_ron": 0, "kurs_applied": 5.0,
    "currency": "EUR", "intocmit_de": None, "notes": None, "split_mode": "equal",
    "payment_status": "UNPAID",
    "line_ids": [10, 20], "doc_mode": "per_car", "created_at": None,
}

DOCNUM_BY_INVOICE = {500: {10: 9100001, 20: 9100002}, 501: {}}


class FakeRepo:
    """Canned repo for the anexa-detail and document-items endpoints."""

    def get_anexa_by_id(self, anexa_id):
        return dict(ANEXA)

    def get_contract_by_id(self, contract_id):
        return dict(CONTRACT)

    def get_lines_by_anexa(self, anexa_id):
        return [dict(LINE_10), dict(LINE_20)]

    def get_invoices_by_anexa(self, anexa_id):
        return [dict(INVOICE_MAPPED), dict(INVOICE_UNMAPPED)]

    def get_document_number_map(self, invoice_id):
        return dict(DOCNUM_BY_INVOICE.get(invoice_id, {}))

    def query_one(self, sql, params=None):
        if "companies" in sql:
            return {"company": "ACME SRL"}
        if "crm_clients" in sql:
            return {"display_name": "Client X"}
        return None

    def query_all(self, sql, params=None):
        if "facturare_invoices i" in sql:
            rows = []
            for base in (INVOICE_MAPPED, INVOICE_UNMAPPED):
                r = dict(base)
                r["invoice_id"] = r.pop("id")
                r.update({
                    "anexa_number": ANEXA["anexa_number"],
                    "contract_id": CONTRACT["id"], "contract_ref": CONTRACT["contract_ref"],
                    "supplier_id": CONTRACT["supplier_id"], "customer_id": CONTRACT["customer_id"],
                    "supplier_name": "ACME SRL", "customer_name": "Client X",
                })
                rows.append(r)
            return rows
        if "facturare_anexa_lines" in sql:
            l10, l20 = dict(LINE_10), dict(LINE_20)
            l10["anexa_id"] = l20["anexa_id"] = ANEXA["id"]
            return [l10, l20]
        return []  # e.g. storno-links query (unused in this scenario)


@pytest.fixture(autouse=True)
def fake_repo(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(routes_orders, "_repo", repo)
    monkeypatch.setattr(routes_orders, "_check_perm", lambda action: True)
    # _sm is a module-level InvoiceStateMachine constructed at import time with
    # the ORIGINAL _repo; redirect its internal repo too so get_next_actions /
    # get_unpaired_proformas (called by api_get_anexa_detail) don't hit the DB.
    monkeypatch.setattr(routes_orders._sm, "repo", repo)
    routes_orders._invalidate_doc_items_cache()
    return repo


# ── 1. _resolve_doc_no (shared helper) ────────────────────────────

def test_resolve_doc_no_prefers_stored_value():
    assert routes_orders._resolve_doc_no({10: 9100001}, 10, fallback=12345) == 9100001


def test_resolve_doc_no_falls_back_when_missing():
    assert routes_orders._resolve_doc_no({}, 10, fallback=12345) == 12345
    assert routes_orders._resolve_doc_no({20: 555}, 10, fallback=12345) == 12345


# ── 2. api_get_anexa_detail ────────────────────────────────────────

def _get_anexa_detail():
    with _app.test_request_context("/facturare/api/anexas/1"):
        resp = routes_orders.api_get_anexa_detail(1)
        return resp.get_json()


def test_anexa_detail_reads_stored_number_not_derived():
    data = _get_anexa_detail()
    by_line = {l["id"]: l["covered_by"] for l in data["lines"]}
    cov_10 = next(c for c in by_line[10] if c["invoice_id"] == 500)
    cov_20 = next(c for c in by_line[20] if c["invoice_id"] == 500)
    # Stored map values (9100001/9100002), NOT the naive base_no + idx
    # derivation (9000000/9000001).
    assert cov_10["invoice_number"] == 9100001
    assert cov_20["invoice_number"] == 9100002


def test_anexa_detail_falls_back_to_derivation_when_map_empty():
    data = _get_anexa_detail()
    by_line = {l["id"]: l["covered_by"] for l in data["lines"]}
    cov_10 = next(c for c in by_line[10] if c["invoice_id"] == 501)
    cov_20 = next(c for c in by_line[20] if c["invoice_id"] == 501)
    # Invoice 501's map is empty -> base_no + idx (today's pre-backfill behavior).
    assert cov_10["invoice_number"] == 9000010
    assert cov_20["invoice_number"] == 9000011


# ── 3. api_document_items ──────────────────────────────────────────

def _get_document_items(doc_types="INVOICE,PROFORMA"):
    with _app.test_request_context(f"/facturare/api/document-items?type={doc_types}"):
        resp = routes_orders.api_document_items()
        return resp.get_json()


def test_document_items_reads_stored_number_not_derived():
    data = _get_document_items()
    items_500 = [it for it in data["items"] if it["invoice_id"] == 500]
    by_car = {it["nr_comanda"]: it["doc_number"] for it in items_500}
    assert by_car["111"] == 9100001
    assert by_car["222"] == 9100002


def test_document_items_falls_back_to_derivation_when_map_empty():
    data = _get_document_items()
    items_501 = [it for it in data["items"] if it["invoice_id"] == 501]
    by_car = {it["nr_comanda"]: it["doc_number"] for it in items_501}
    assert by_car["111"] == 9000010
    assert by_car["222"] == 9000011


# ── 4. api_generate_pdf ─────────────────────────────────────────────
# Spy on ProformaPdfRenderer to capture the inv_no each render call actually
# receives, without needing to parse PDF bytes.

class _RecordingRenderer:
    """Drop-in for ProformaPdfRenderer: records inv_no per call, draws nothing."""

    calls = []  # list of (method, inv_no) across the renderer's lifetime

    def __init__(self, **kwargs):
        self.note = kwargs.get("note", "")

    def render_one(self, c, inv_no, line):
        _RecordingRenderer.calls.append(("render_one", inv_no))

    def _render_storno_page(self, c, inv_no, items):
        _RecordingRenderer.calls.append(("storno_page", inv_no))

    def render_single_doc_to_bytes(self, lines, inv_no):
        _RecordingRenderer.calls.append(("single_doc", inv_no))
        return b"%PDF-fake"

    def render_all_to_bytes(self, lines, start_no, same_number=False):
        _RecordingRenderer.calls.append(("render_all_to_bytes", start_no))
        return b"%PDF-fake"


class PdfFakeRepo(FakeRepo):
    """Extends FakeRepo with get_invoice_by_id + query_one/query_all shapes
    used directly by api_generate_pdf (distinct SQL strings from the
    anexa-detail/document-items endpoints)."""

    def __init__(self, invoice_row, docnum_by_invoice, reversed_invoices=None):
        self._invoice_row = invoice_row
        self._docnum_by_invoice = docnum_by_invoice
        self._reversed_invoices = reversed_invoices or []

    def get_invoice_by_id(self, invoice_id):
        return dict(self._invoice_row)

    def get_document_number_map(self, invoice_id):
        return dict(self._docnum_by_invoice.get(invoice_id, {}))

    def query_one(self, sql, params=None):
        if "companies" in sql:
            return {"company": "ACME SRL", "vat": "", "reg_no": "", "iban": "",
                    "bank": "", "swift": "", "street": "", "city": "", "county": ""}
        if "crm_clients" in sql:
            return {"display_name": "Client X", "nr_reg": "", "street": "",
                    "city": "", "country": ""}
        if "facturare_invoice_links l" in sql:
            return None  # no linked proforma
        return None

    def query_all(self, sql, params=None):
        if "facturare_invoice_links" in sql:
            return []  # no reversed-invoice links (reversed_inv_ids stays None)
        if "facturare_invoices" in sql:
            return [dict(r) for r in self._reversed_invoices]
        return []


@pytest.fixture(autouse=True)
def _reset_renderer_spy(monkeypatch):
    _RecordingRenderer.calls = []
    monkeypatch.setattr(proforma_pdf_module, "ProformaPdfRenderer", _RecordingRenderer)


def _generate_pdf(invoice_id, repo, query_args=""):
    routes_orders._repo = repo  # api_generate_pdf's module-level _repo, used directly
    with _app.test_request_context(f"/facturare/api/invoices/{invoice_id}/pdf{query_args}"):
        return routes_orders.api_generate_pdf(invoice_id)


def test_pdf_per_car_advance_reads_stored_numbers(monkeypatch):
    """INVOICE (advance), doc_mode=per_car, mapped -> render_one gets the
    stored per-car numbers (9100001/9100002), not start_no + idx (9000000/1)."""
    invoice_row = dict(INVOICE_MAPPED)
    invoice_row["invoice_type"] = "INVOICE"
    repo = PdfFakeRepo(invoice_row, {500: {10: 9100001, 20: 9100002}})
    _generate_pdf(500, repo)
    render_one_calls = [c for m, c in _RecordingRenderer.calls if m == "render_one"]
    assert render_one_calls == [9100001, 9100002]


def test_pdf_per_car_advance_falls_back_when_unmapped(monkeypatch):
    """Same invoice, empty map -> falls back to start_no + idx (9000000/9000001)."""
    invoice_row = dict(INVOICE_MAPPED)
    invoice_row["invoice_type"] = "INVOICE"
    repo = PdfFakeRepo(invoice_row, {})
    _generate_pdf(500, repo)
    render_one_calls = [c for m, c in _RecordingRenderer.calls if m == "render_one"]
    assert render_one_calls == [9000000, 9000001]


def test_pdf_single_doc_uses_stored_shared_number(monkeypatch):
    """doc_mode=single_doc: renderer.render_single_doc_to_bytes gets the ONE
    stored number shared by all cars, not the invoice's own invoice_number."""
    invoice_row = dict(INVOICE_MAPPED)
    invoice_row["invoice_type"] = "INVOICE"
    invoice_row["doc_mode"] = "single_doc"
    repo = PdfFakeRepo(invoice_row, {500: {10: 9200500, 20: 9200500}})
    _generate_pdf(500, repo)
    single_doc_calls = [c for m, c in _RecordingRenderer.calls if m == "single_doc"]
    assert single_doc_calls == [9200500]


def test_pdf_storno_reads_own_and_reversed_stored_numbers(monkeypatch):
    """STORNO invoice: the reversed-invoice's stored number appears in the
    'Ref: Factura Nr.' text (verified indirectly is out of scope for the
    spy — covered by code inspection instead); the storno's OWN per-car
    number passed to _render_storno_page comes from the map."""
    storno_row = {
        "id": 900, "anexa_id": 1, "invoice_type": "STORNO", "invoice_state": "ISSUED",
        "sequence_number": 1, "invoice_number": 9300000, "issued_date": "2026-07-27",
        "total_amount_eur": -20000, "total_amount_ron": 0, "kurs_applied": 5.0,
        "currency": "EUR", "intocmit_de": None, "notes": None, "split_mode": "equal",
        "payment_status": "UNPAID", "line_ids": [10, 20], "doc_mode": "per_car",
        "created_at": None,
    }
    reversed_invoice = dict(INVOICE_MAPPED)
    reversed_invoice["invoice_type"] = "INVOICE"
    repo = PdfFakeRepo(
        storno_row,
        docnum_by_invoice={900: {10: 9300001, 20: 9300002}, 500: {10: 9100001, 20: 9100002}},
        reversed_invoices=[reversed_invoice],
    )
    _generate_pdf(900, repo)
    storno_calls = [c for m, c in _RecordingRenderer.calls if m == "storno_page"]
    assert storno_calls == [9300001, 9300002]


def test_pdf_storno_falls_back_when_own_map_unmapped(monkeypatch):
    """STORNO's own map is empty -> falls back to start_no + page_idx."""
    storno_row = {
        "id": 900, "anexa_id": 1, "invoice_type": "STORNO", "invoice_state": "ISSUED",
        "sequence_number": 1, "invoice_number": 9300000, "issued_date": "2026-07-27",
        "total_amount_eur": -20000, "total_amount_ron": 0, "kurs_applied": 5.0,
        "currency": "EUR", "intocmit_de": None, "notes": None, "split_mode": "equal",
        "payment_status": "UNPAID", "line_ids": [10, 20], "doc_mode": "per_car",
        "created_at": None,
    }
    reversed_invoice = dict(INVOICE_MAPPED)
    reversed_invoice["invoice_type"] = "INVOICE"
    repo = PdfFakeRepo(
        storno_row,
        docnum_by_invoice={900: {}, 500: {10: 9100001, 20: 9100002}},
        reversed_invoices=[reversed_invoice],
    )
    _generate_pdf(900, repo)
    storno_calls = [c for m, c in _RecordingRenderer.calls if m == "storno_page"]
    assert storno_calls == [9300000, 9300001]
