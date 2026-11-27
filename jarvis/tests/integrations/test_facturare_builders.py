"""Pure builders for the facturare lookup endpoint — no DB.

_pick_current: choose the live fiscal invoice from a document chain.
_build_results: group repo rows into the JSON-ready response + not_found list.
"""
from datetime import date
from decimal import Decimal

from core.integrations.routes_facturare import _pick_current, _build_results


def test_pick_current_prefers_final_over_invoice_ignores_archived_and_null_date():
    docs = [
        {"invoice_number": 9200850, "invoice_type": "INVOICE", "issued_date": date(2026, 2, 13), "archived": False},
        {"invoice_number": 9200939, "invoice_type": "FINAL",   "issued_date": date(2026, 3, 17), "archived": False},
        {"invoice_number": 9200999, "invoice_type": "FINAL",   "issued_date": None,              "archived": True},
    ]
    assert _pick_current(docs)["invoice_number"] == 9200939


def test_pick_current_none_when_only_proforma_or_storno():
    docs = [{"invoice_number": 206, "invoice_type": "PROFORMA", "issued_date": date(2025, 10, 29), "archived": False}]
    assert _pick_current(docs) is None


def test_build_results_summary_documents_jsonready_dedup_and_not_found():
    rows = [
        {"nr_comanda": "150019", "vin": "WAU", "model": "Audi Q3 35 TFSI", "line_id": 1,
         "invoice_number": 9202036, "invoice_type": "INVOICE", "issued_date": date(2026, 9, 9),
         "total_amount_eur": Decimal("31828.00"), "total_amount_ron": Decimal("167170.20"),
         "currency": "EUR", "archived": False},
    ]
    results, not_found = _build_results(["150019", " 150019 ", "999999"], rows)
    assert len(results) == 1                      # deduped
    r = results[0]
    assert r["has_invoice"] is True and r["invoice_number"] == "9202036"
    assert r["invoice_date"] == "2026-09-09"      # ISO string, not date
    assert isinstance(r["amount_eur"], float) and r["amount_eur"] == 31828.00  # float, not Decimal
    assert r["item"] == "Audi Q3 35 TFSI" and len(r["documents"]) == 1
    assert not_found == ["999999"]


def test_build_results_line_without_invoice_is_has_invoice_false():
    rows = [{"nr_comanda": "B", "vin": None, "model": "M", "line_id": 9, "invoice_number": None,
             "invoice_type": None, "issued_date": None, "total_amount_eur": None,
             "total_amount_ron": None, "currency": None, "archived": None}]
    results, not_found = _build_results(["B"], rows)
    assert results[0]["has_invoice"] is False and results[0]["documents"] == [] and not_found == []
