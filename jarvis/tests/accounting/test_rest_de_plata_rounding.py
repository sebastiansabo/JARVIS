"""Regression tests for the "rest de plată" +1 EUR rounding bug (CTR-945,
comanda 352848, client Sapphire Consulting).

A 45.750 € car is billed as a 5% advance then a 95% remainder. Both slices land
exactly on X.50, and each was independently rounded half-up:

    advance = round_half_up(45750 * 0.05) = round_half_up(2287.50) = 2288
    rest    = round_half_up(45750 * 0.95) = round_half_up(43462.50) = 43463

so advance + rest = 45751 = selling + 1. The invoice, the proforma and the
displayed Proforma/Facturat totals were all 1 € high.

Correct behaviour: the invoice that *closes* a car's coverage (cumulative
fraction reaches 100%) must book the residual `selling - advances_already_booked`
= 45750 - 2288 = 43462, so the slices reconcile to the car's whole-EUR price
exactly.
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


# ── 1. Pure helper: _car_slice_eur (cumulative-rounding residual) ──────────────

def test_advance_slice_rounds_half_up():
    # First (non-closing) slice keeps the half-up behaviour: 2287.50 -> 2288.
    assert routes_orders._car_slice_eur(45750, 0.05, []) == 2288


def test_closing_slice_is_residual_not_independent_round():
    # The 95% remainder closes coverage -> residual 45750 - 2288 = 43462,
    # NOT round_half_up(45750 * 0.95) = 43463.
    assert routes_orders._car_slice_eur(45750, 0.95, [0.05]) == 43462


def test_advance_plus_rest_reconcile_to_selling():
    advance = routes_orders._car_slice_eur(45750, 0.05, [])
    rest = routes_orders._car_slice_eur(45750, 0.95, [0.05])
    assert advance + rest == 45750


def test_full_final_books_whole_selling():
    # A 100% invoice (FINAL) with no priors books the whole car.
    assert routes_orders._car_slice_eur(45750, 1.0, []) == 45750


def test_non_half_amounts_unchanged():
    # A car whose slices don't land on X.50 is unaffected either way.
    assert routes_orders._car_slice_eur(20000, 0.05, []) == 1000
    assert routes_orders._car_slice_eur(20000, 0.95, [0.05]) == 19000


# ── 2. Coverage endpoint: api_get_anexa_detail (CTR-945 scenario) ──────────────

ANEXA = {"id": 1, "contract_id": 10, "anexa_number": 1}
CONTRACT = {"id": 10, "supplier_id": 100, "customer_id": 200, "contract_ref": "CTR-945"}
LINE = {
    "id": 10, "line_number": 1, "nr_comanda": "352848", "vin": "WV2ZZZ",
    "model": "Multivan Life", "culoare": "", "list_price_eur": 0,
    "selling_price_eur": 45750, "qty": 1,
}


def _inv(id_, itype, seq, date, total, number):
    return {
        "id": id_, "anexa_id": 1, "invoice_type": itype, "invoice_state": "ISSUED",
        "sequence_number": seq, "invoice_number": number, "issued_date": date,
        "total_amount_eur": total, "total_amount_ron": 0, "kurs_applied": 5.2,
        "currency": "EUR", "intocmit_de": None, "notes": None,
        "split_mode": "proportional", "payment_status": "UNPAID",
        "line_ids": [10], "doc_mode": "per_car", "created_at": None,
    }


PROFORMA_5 = _inv(915, "PROFORMA", 1, "2026-05-13", 2287.50, 915)
AVANS_5 = _inv(9103195, "INVOICE", 2, "2026-05-18", 2287.50, 9103195)
PROFORMA_95 = _inv(1049, "PROFORMA", 3, "2026-07-08", 43462.50, 1049)
AVANS_95 = _inv(9103869, "INVOICE", 4, "2026-08-06", 43462.50, 9103869)
INVOICES = [PROFORMA_5, AVANS_5, PROFORMA_95, AVANS_95]


class FakeRepo:
    def get_anexa_by_id(self, anexa_id):
        return dict(ANEXA)

    def get_contract_by_id(self, contract_id):
        return dict(CONTRACT)

    def get_lines_by_anexa(self, anexa_id):
        return [dict(LINE)]

    def get_invoices_by_anexa(self, anexa_id):
        return [dict(i) for i in INVOICES]

    def get_document_number_map(self, invoice_id):
        return {}

    def query_one(self, sql, params=None):
        if "companies" in sql:
            return {"company": "SAPPHIRE CONSULTING GMBH"}
        if "crm_clients" in sql:
            return {"display_name": "Autoworld INTERNATIONAL S.R.L."}
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
    with _app.test_request_context("/facturare/api/anexas/1"):
        return routes_orders.api_get_anexa_detail(1).get_json()


def test_line_totals_reconcile_to_selling():
    line = _detail()["lines"][0]
    assert line["proforma_eur"] == 45750  # was 45751
    assert line["invoiced_eur"] == 45750  # was 45751


def test_per_invoice_shares_use_residual_for_closing():
    cov = {c["invoice_id"]: c["amount_eur"] for c in _detail()["lines"][0]["covered_by"]}
    assert cov[915] == 2288       # proforma 5%
    assert cov[1049] == 43462     # proforma 95% (rest) — was 43463
    assert cov[9103195] == 2288   # avans 5%
    assert cov[9103869] == 43462  # avans 95% (rest) — was 43463
