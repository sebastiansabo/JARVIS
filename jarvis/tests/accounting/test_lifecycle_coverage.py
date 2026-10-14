"""Coverage-endpoint regressions for the per-car reconcile + FINAL-counted fixes.

Models CTR-605 (contract 20 / anexa 22): a bulk 10% proforma over many cars plus
a per-car 90%, then storno + final. Two invariants the v1 fix (reverted
JAR-2031/2) broke and these pin:

  1. a car's 10% + 90% = its whole price — the 90% closing slice subtracts the
     ACTUAL reconciled 10% (2159), not round(price*10%) (2160), so no Rest=1;
  2. a car billed by a FINAL (after its avansuri were stornoed) counts as
     invoiced — Rest 0, not Rest = full price.
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

_app = flask.Flask(__name__)
_app.config["LOGIN_DISABLED"] = True

ANEXA = {"id": 1, "contract_id": 1, "anexa_number": 1}
CONTRACT = {"id": 1, "supplier_id": 1, "customer_id": 1, "contract_ref": "CTR-605"}
# Two 21.598 cars; car 1 goes full lifecycle, car 2 stays at the bulk 10%.
LINES = [
    {"id": 1, "line_number": 1, "nr_comanda": "1", "vin": None, "model": "Taigo",
     "culoare": "", "list_price_eur": 0, "selling_price_eur": 21598, "qty": 1},
    {"id": 2, "line_number": 2, "nr_comanda": "2", "vin": None, "model": "Taigo",
     "culoare": "", "list_price_eur": 0, "selling_price_eur": 21598, "qty": 1},
]


def _inv(id_, itype, seq, date, total, lids, split="proportional"):
    return {"id": id_, "anexa_id": 1, "invoice_type": itype, "invoice_state": "ISSUED",
            "sequence_number": seq, "invoice_number": id_, "issued_date": date,
            "total_amount_eur": total, "total_amount_ron": 0, "kurs_applied": 5.0,
            "currency": "EUR", "intocmit_de": None, "notes": None, "split_mode": split,
            "payment_status": "UNPAID", "archived": False, "line_ids": lids,
            "doc_mode": "per_car", "round_decimals": False, "created_at": None}


# Bulk 10% over both cars: stored 4318 → Hamilton gives 2159/car (NOT round(2159.8)=2160).
BULK_10 = _inv(100, "PROFORMA", 1, "2026-03-27", 4318, [1, 2])
AVANS_10 = _inv(101, "INVOICE", 1, "2026-03-30", 4318, [1, 2])
# Car 1: 90% proforma + avans, then storno (reverses both avansuri) + final.
PRO_90_C1 = _inv(102, "PROFORMA", 2, "2026-05-26", 19439, [1])
AVANS_90_C1 = _inv(103, "INVOICE", 2, "2026-05-27", 19439, [1])
STORNO_C1 = _inv(104, "STORNO", 1, "2026-07-06", -21598, [1], split="equal")
FINAL_C1 = _inv(105, "FINAL", 1, "2026-07-06", 21598, [1])
INVOICES = [BULK_10, AVANS_10, PRO_90_C1, AVANS_90_C1, STORNO_C1, FINAL_C1]
# Storno 104 reverses the two car-1 avansuri (101 bulk 10% + 103 the 90%).
LINKS = [{"source_invoice_id": 101, "target_invoice_id": 104},
         {"source_invoice_id": 103, "target_invoice_id": 104}]


class FakeRepo:
    def get_anexa_by_id(self, anexa_id): return dict(ANEXA)
    def get_contract_by_id(self, cid): return dict(CONTRACT)
    def get_lines_by_anexa(self, anexa_id): return [dict(l) for l in LINES]
    def get_invoices_by_anexa(self, anexa_id): return [dict(i) for i in INVOICES]
    def get_document_number_map(self, invoice_id): return {}

    def query_one(self, sql, params=None):
        if "companies" in sql: return {"company": "AW"}
        if "crm_clients" in sql: return {"display_name": "Client"}
        return None

    def query_all(self, sql, params=None):
        if "facturare_invoice_links" in sql:
            tgts = set(params or [])
            return [l for l in LINKS if l["target_invoice_id"] in tgts]
        return []


@pytest.fixture(autouse=True)
def fake_repo(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(routes_orders, "_repo", repo)
    monkeypatch.setattr(routes_orders, "_check_perm", lambda a: True)
    monkeypatch.setattr(routes_orders._sm, "repo", repo)
    monkeypatch.setattr(routes_orders._sm, "get_next_actions", lambda a: [])
    monkeypatch.setattr(routes_orders._sm, "get_unpaired_proformas", lambda a: [])
    routes_orders._invalidate_doc_items_cache()
    return repo


def _lines_by_id():
    with _app.test_request_context("/facturare/api/anexas/1"):
        data = routes_orders.api_get_anexa_detail(1).get_json()
    return {l["id"]: l for l in data["lines"]}


def test_bulk10_plus_90_reconciles_to_price_no_one_euro_gap():
    # Car 2 (bulk 10% + 90% proforma) must reconcile to 21.598, not 21.597.
    car2 = _lines_by_id()[2]
    # car 2 only has the bulk 10% here → proforma covers just the 10% share.
    assert car2["proforma_eur"] == 2159
    # Car 1 proforma track: 2159 (bulk) + 19439 (90%) − 21598 (storno) = 0.
    car1 = _lines_by_id()[1]
    # The 90% covered_by amount is the ACTUAL residual 19439 (price − 2159), not 19438.
    cov = {c["invoice_id"]: c["amount_eur"] for c in car1["covered_by"]}
    assert cov[102] == 19439  # 90% proforma closing slice
    assert cov[103] == 19439  # 90% avans closing slice


def test_finalized_car_counts_as_invoiced_rest_zero():
    # Car 1: avansuri (2159+19439) − storno (21598) + FINAL (21598) = 21598 invoiced.
    car1 = _lines_by_id()[1]
    assert car1["invoiced_eur"] == 21598        # was 0 (final not counted) → Rest = full price
    assert car1["selling_price_eur"] - car1["invoiced_eur"] == 0
