"""End-to-end coverage-endpoint check for CTR-790 (AW Next proforma No:7).

Exercises `api_get_anexa_detail` (the Hub coverage view, same per-car path the
PDF/EuroFib use) with the real shape: 2 × 56.136 € cars, one proportional
proforma whose stored/collected total is 11.226 €. The per-car slices must
reconcile to 11.226 (5.613 + 5.613), not overshoot to 11.228 (5.614 + 5.614).
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

ANEXA = {"id": 33, "contract_id": 31, "anexa_number": 1}
CONTRACT = {"id": 31, "supplier_id": 13, "customer_id": 13502, "contract_ref": "CTR-790"}
LINES = [
    {"id": 1044, "line_number": 1, "nr_comanda": "2619484", "vin": None,
     "model": "Volvo EX60 Ultra P10 22", "culoare": "Onyx Black",
     "list_price_eur": 0, "selling_price_eur": 56136.00, "qty": 1},
    {"id": 1045, "line_number": 2, "nr_comanda": "2619485", "vin": None,
     "model": "Volvo EX60 Ultra P10 22", "culoare": "Vapour Grey",
     "list_price_eur": 0, "selling_price_eur": 56136.00, "qty": 1},
]
PROFORMA = {
    "id": 992, "anexa_id": 33, "invoice_type": "PROFORMA", "invoice_state": "ISSUED",
    "sequence_number": 1, "invoice_number": 7, "issued_date": "2026-07-23",
    "total_amount_eur": 11226.00, "total_amount_ron": 0, "kurs_applied": None,
    "currency": "EUR", "intocmit_de": "Olosutean Cristina", "notes": None,
    "split_mode": "proportional", "payment_status": "UNPAID",
    "line_ids": [1044, 1045], "doc_mode": "single_doc", "round_decimals": False,
    "created_at": None,
}


class FakeRepo:
    def get_anexa_by_id(self, anexa_id):
        return dict(ANEXA)

    def get_contract_by_id(self, contract_id):
        return dict(CONTRACT)

    def get_lines_by_anexa(self, anexa_id):
        return [dict(l) for l in LINES]

    def get_invoices_by_anexa(self, anexa_id):
        return [dict(PROFORMA)]

    def get_document_number_map(self, invoice_id):
        return {}

    def query_one(self, sql, params=None):
        if "companies" in sql:
            return {"company": "Autoworld NEXT S.R.L."}
        if "crm_clients" in sql:
            return {"display_name": "STAIGER DICH ABO&LEASING GMBH & CO KG"}
        return None

    def query_all(self, sql, params=None):
        return []


@pytest.fixture(autouse=True)
def fake_repo(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(routes_orders, "_repo", repo)
    monkeypatch.setattr(routes_orders, "_check_perm", lambda action: True)
    monkeypatch.setattr(routes_orders._sm, "repo", repo)
    monkeypatch.setattr(routes_orders._sm, "get_next_actions", lambda anexa_id: [])
    monkeypatch.setattr(routes_orders._sm, "get_unpaired_proformas", lambda anexa_id: [])
    routes_orders._invalidate_doc_items_cache()
    return repo


def _detail():
    with _app.test_request_context("/facturare/api/anexas/33"):
        return routes_orders.api_get_anexa_detail(33).get_json()


def test_percar_slices_reconcile_to_collected_proforma_total():
    lines = _detail()["lines"]
    per_car = {l["id"]: l["proforma_eur"] for l in lines}
    assert per_car[1044] == 5613  # was 5614
    assert per_car[1045] == 5613  # was 5614
    assert sum(per_car.values()) == 11226  # the collected total, was 11228


def test_covered_by_amounts_match_the_proforma():
    lines = {l["id"]: l for l in _detail()["lines"]}
    shares = [c["amount_eur"] for c in lines[1044]["covered_by"]]
    assert shares == [5613]
