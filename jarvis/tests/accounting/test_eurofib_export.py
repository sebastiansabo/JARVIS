"""Hermetic tests for the EuroFib XLSX export line-building logic.

Reproduces the production scenario for comanda 352716 (VW Caddy, anexa 21):
a STORNO reversing two advances (2,290 € @ 5.0927 and 20,610 € @ 5.2429)
followed by a FINAL for the full 22,900 €.

Two accounting requirements are asserted:

1. Every row of a single STORNO invoice must carry that storno's own
   invoice number (both lines = 9103805), not a per-row incremented number
   (the 2nd line was wrongly getting 9103806 — the FINAL's number).

2. The FINAL invoice's RON value must equal the summed RON of the reversed
   advances (11,662.28 + 108,056.17 = 119,718.45), so the client ledger nets
   to zero — not 22,900 × (last advance's kurs) = 120,062.41.

The route module opens a DB pool at import, so DATABASE_URL must point at a
reachable Postgres. No query actually runs: the module-level `_repo` is
replaced with a fake that returns canned rows for this scenario.
"""
import io
import os
import sys

import pytest

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

# Import-time only: the pool connects but every query is intercepted by FakeRepo.
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

from openpyxl import load_workbook  # noqa: E402

from accounting.facturare import routes_orders  # noqa: E402
from accounting.facturare.generators.eurofib_xlsx import EurofibXlsxRenderer  # noqa: E402

# ── Column indices in the EuroFib template (1-based) ─────────────
COL_BELEGNUMMER = 8   # H
COL_FWBETRAG = 13     # M
COL_KURS = 33         # AG

# ── Canned scenario data (single car) ────────────────────────────
LINE_840 = {
    "id": 840, "anexa_id": 1, "line_number": 1, "nr_comanda": "352716",
    "model": "Caddy Maxi Cargo 2.0 TDI 75 kW", "culoare": "",
    "list_price_eur": 0, "selling_price_eur": 22900, "qty": 1,
}
ADV_A = {  # first advance — 2,290 € @ 5.0927
    "id": 91, "invoice_number": 9103741, "total_amount_eur": 2290,
    "split_mode": "proportional", "kurs_applied": 5.0927,
    "issued_date": "2026-04-27", "line_ids": [840],
}
ADV_B = {  # second advance — 20,610 € @ 5.2429
    "id": 92, "invoice_number": 9103742, "total_amount_eur": 20610,
    "split_mode": "proportional", "kurs_applied": 5.2429,
    "issued_date": "2026-07-19", "line_ids": [840],
}
STORNO_ROW = {
    "id": 100, "invoice_type": "STORNO", "invoice_number": 9103805, "anexa_id": 1,
    "total_amount_eur": -22900, "split_mode": "equal", "kurs_applied": 5.1893,
    "issued_date": "2026-07-27", "line_ids": [840],
}
FINAL_ROW = {
    "id": 101, "invoice_type": "FINAL", "invoice_number": 9103806, "anexa_id": 1,
    "total_amount_eur": 22900, "split_mode": "proportional", "kurs_applied": 5.2279,
    "issued_date": "2026-07-27", "line_ids": [840],
}

# Stored document numbers per invoice (facturare_document_numbers), keyed by
# invoice id — this is what the export now reads instead of deriving.
DOCNUM_MAP_BY_INVOICE = {
    100: {840: 9103805},  # storno
    101: {840: 9103806},  # final
}

# ── Canned scenario data (multi-car anexa, ids 838/839/840) ──────
LINE_838 = {
    "id": 838, "anexa_id": 2, "line_number": 1, "nr_comanda": "838-1",
    "model": "Model A", "culoare": "", "list_price_eur": 0,
    "selling_price_eur": 10000, "qty": 1,
}
LINE_839 = {
    "id": 839, "anexa_id": 2, "line_number": 2, "nr_comanda": "838-2",
    "model": "Model B", "culoare": "", "list_price_eur": 0,
    "selling_price_eur": 10000, "qty": 1,
}
LINE_840_MULTI = {
    "id": 840, "anexa_id": 2, "line_number": 3, "nr_comanda": "838-3",
    "model": "Model C", "culoare": "", "list_price_eur": 0,
    "selling_price_eur": 10000, "qty": 1,
}
ADVANCE_3CAR = {  # single_doc: all three cars share ONE stored number
    "id": 200, "invoice_type": "INVOICE", "invoice_number": 300, "anexa_id": 2,
    "total_amount_eur": 9126, "split_mode": "equal", "kurs_applied": 5.0,
    "issued_date": "2026-07-27", "line_ids": [838, 839, 840],
}
ADVANCE_2CAR = {  # per_car: each car has its OWN stored number
    "id": 201, "invoice_type": "INVOICE", "invoice_number": 301, "anexa_id": 2,
    "total_amount_eur": 6084, "split_mode": "equal", "kurs_applied": 5.0,
    "issued_date": "2026-07-27", "line_ids": [838, 839],
}


class FakeRepo:
    """Returns canned rows for the 352716 scenario; dispatches raw SQL by substring."""

    def get_anexa_by_id(self, anexa_id):
        return {"id": 1, "contract_id": 1, "anexa_number": 21}

    def get_contract_by_id(self, contract_id):
        return {"id": 1, "contract_ref": "C-1", "supplier_id": 16, "customer_id": 18}

    def get_lines_by_anexa(self, anexa_id):
        return [dict(LINE_840)]

    def get_document_number_map(self, invoice_id):
        return dict(DOCNUM_MAP_BY_INVOICE.get(invoice_id, {}))

    def match_venituri_rule(self, supplier_id, nr_comanda):
        return None  # FINAL falls back to konto_config credit (707128)

    def query_one(self, sql, params=None):
        if "facturare_konto_config" in sql:
            invoice_type = params[1]
            credit = 419968 if invoice_type == "STORNO" else 707128
            return {"konto_credit": credit, "text_template": None}
        if "FROM companies" in sql:
            return {"eurofib_klient_id": 139}
        if "FROM crm_clients" in sql:
            return {"eurofib_konto_debit": {"139": "41217835"}}
        if "ORDER BY sequence_number DESC" in sql:   # legacy last-advance lookup
            return dict(ADV_B)
        return None

    def query_all(self, sql, params=None):
        if "facturare_invoice_links" in sql:
            return [{"source_invoice_id": 91}, {"source_invoice_id": 92}]
        if "id IN" in sql:                            # reversed invoices for storno
            return [dict(ADV_A), dict(ADV_B)]
        if "invoice_type = 'INVOICE'" in sql:         # all advances for anexa
            return [dict(ADV_A), dict(ADV_B)]
        return []


class MultiCarFakeRepo(FakeRepo):
    """3-car anexa (line ids 838/839/840) used for the multi-car advance tests.

    Only `get_document_number_map` is scenario-specific — the caller supplies
    the stored map (single_doc: all cars share one number; per_car: each car
    has its own).
    """

    def __init__(self, docnum_map):
        self._docnum_map = docnum_map

    def get_anexa_by_id(self, anexa_id):
        return {"id": 2, "contract_id": 1, "anexa_number": 99}

    def get_lines_by_anexa(self, anexa_id):
        return [dict(LINE_838), dict(LINE_839), dict(LINE_840_MULTI)]

    def get_document_number_map(self, invoice_id):
        return dict(self._docnum_map)


@pytest.fixture(autouse=True)
def fake_repo(monkeypatch):
    monkeypatch.setattr(routes_orders, "_repo", FakeRepo())


def _render(inv_row):
    cfg, lines = routes_orders._build_eurofib_batch(inv_row)
    wb = load_workbook(io.BytesIO(EurofibXlsxRenderer(cfg).render_to_bytes(lines)))
    return wb.active


def _betrag(ws, row):
    """betrag = fwbetrag * kurs (the renderer writes betrag as an Excel formula)."""
    return round(ws.cell(row=row, column=COL_FWBETRAG).value
                 * ws.cell(row=row, column=COL_KURS).value, 2)


def test_storno_lines_share_the_storno_invoice_number():
    """Belegnummer comes from DOCNUM_MAP_BY_INVOICE[100] = {840: 9103805}, not
    derived — every reversed-advance row of car 840 gets that stored number."""
    ws = _render(STORNO_ROW)
    # Two reversed advances → rows 3/4 (line 0) and 5/6 (line 1)
    belegnummers = {ws.cell(row=r, column=COL_BELEGNUMMER).value for r in (3, 4, 5, 6)}
    assert belegnummers == {9103805}, (
        f"all storno rows must carry 9103805, got {sorted(belegnummers)}"
    )
    # Sanity: the two reversed advances are still represented at their own rates
    assert _betrag(ws, 3) == -11662.28
    assert _betrag(ws, 5) == -108056.17


def test_final_ron_equals_summed_storno_ron():
    """Belegnummer comes from DOCNUM_MAP_BY_INVOICE[101] = {840: 9103806}."""
    ws = _render(FINAL_ROW)
    assert ws.cell(row=3, column=COL_BELEGNUMMER).value == 9103806
    assert ws.cell(row=3, column=COL_FWBETRAG).value == 22900
    # 11,662.28 + 108,056.17 = 119,718.45 (net-zero against the storno)
    assert _betrag(ws, 3) == 119718.45


def test_daily_export_storno_plus_final_nets_to_zero():
    """The combined daily sheet (storno batch + final batch) must net to ~0 RON."""
    storno_batch = routes_orders._build_eurofib_batch(STORNO_ROW)
    final_batch = routes_orders._build_eurofib_batch(FINAL_ROW)
    xlsx = EurofibXlsxRenderer.render_multi_to_bytes([storno_batch, final_batch])
    ws = load_workbook(io.BytesIO(xlsx)).active

    # Debit rows only (odd export rows 3,5,7) hold each position once.
    belegnummers = [ws.cell(row=r, column=COL_BELEGNUMMER).value for r in (3, 5, 7)]
    assert belegnummers == [9103805, 9103805, 9103806]

    net = sum(_betrag(ws, r) for r in (3, 5, 7))
    assert abs(net) < 0.01, f"storno + final should net to zero, got {net}"


def test_multi_car_advance_single_doc_shares_stored_number(monkeypatch):
    """single_doc: all three cars were stored under the SAME document number.

    The old `start_no + idx` derivation would have produced 9103042/43/44 for
    the three rows — wrong, since this invoice's per-car numbers were actually
    stored identically (single_doc mode). The export must read the map.
    """
    monkeypatch.setattr(routes_orders, "_repo", MultiCarFakeRepo(
        {838: 9103042, 839: 9103042, 840: 9103042}))
    ws = _render(ADVANCE_3CAR)
    belegnummers = [ws.cell(row=r, column=COL_BELEGNUMMER).value for r in (3, 5, 7)]
    assert belegnummers == [9103042, 9103042, 9103042]


def test_multi_car_advance_per_car_stored_numbers(monkeypatch):
    """per_car: each car was stored with its OWN document number."""
    monkeypatch.setattr(routes_orders, "_repo", MultiCarFakeRepo(
        {838: 9103042, 839: 9103043}))
    ws = _render(ADVANCE_2CAR)
    belegnummers = [ws.cell(row=r, column=COL_BELEGNUMMER).value for r in (3, 5)]
    assert belegnummers == [9103042, 9103043]
