"""Real-DB integration tests for the invoice-document -> cost link column.

Covers Task 1 of the carpark invoice-to-cost feature:
`carpark_vehicle_costs.source_document_id` (FK -> carpark_vehicle_documents,
ON DELETE SET NULL) plus the partial unique index `uq_vcc_source_document`
that enforces at most one cost row per source document.

Runs against localhost/defaultdb via the probe in conftest.py (which drops
jarvis/conftest.py's psycopg2 mock and rebinds the real driver). The
DB-backed test depends on `require_real_db` + the `invoice_transfer_seed`
fixture (both in conftest.py); it seeds one vehicle + one
'factura_achizitie' document under the sentinel `company_id=990001` and
tears them down (cascade-deleting the document and any cost rows) in a
`finally` block, asserting zero rows remain afterwards.

This file will also host Task 4's test (the invoice-document -> cost
transfer endpoint/service).

Invocation:
    venv/bin/python -m pytest jarvis/tests/carpark/test_invoice_cost_transfer_db.py -v
"""
import pytest

from carpark.repositories.cost_repository import CostRepository, COST_FIELDS
from carpark.services.vehicle_service import VehicleService


def test_source_document_id_in_cost_fields():
    """Always-run (no DB) evidence that the field is insertable:
    CostRepository.create filters incoming data to COST_FIELDS, so
    'source_document_id' must be present for it to ever reach the INSERT."""
    assert 'source_document_id' in COST_FIELDS


def test_source_document_id_unique_per_document(require_real_db, invoice_transfer_seed):
    # Two costs can't point at the same source document.
    seed = invoice_transfer_seed  # {'vehicle_id', 'doc_id'}
    CostRepository().create(seed['vehicle_id'], {'cost_type': 'other', 'amount': 10, 'source_document_id': seed['doc_id']})
    with pytest.raises(Exception):  # unique_violation
        CostRepository().create(seed['vehicle_id'], {'cost_type': 'other', 'amount': 20, 'source_document_id': seed['doc_id']})


# ── Task 4: VehicleService.transfer_document_to_cost ──────────────────────


def test_transfer_creates_linked_cost_under_line(require_real_db, invoice_transfer_seed):
    seed = invoice_transfer_seed
    cost = VehicleService().transfer_document_to_cost(seed['vehicle_id'], seed['doc_id'],
        {'cost_type': 'transport', 'amount': 1000, 'vat_rate': 19, 'vat_amount': 190,
         'invoice_number': 'F1', 'supplier_name': 'AUTO', 'currency': 'RON', 'date': '2026-11-10'},
        created_by=None)
    assert cost['source_document_id'] == seed['doc_id']
    assert cost['cost_line_id'] is not None and cost['cost_type'] == 'transport'


def test_second_transfer_of_same_document_is_rejected(require_real_db, invoice_transfer_seed):
    seed = invoice_transfer_seed
    svc = VehicleService()
    svc.transfer_document_to_cost(seed['vehicle_id'], seed['doc_id'], {'cost_type': 'other', 'amount': 5}, None)
    with pytest.raises(ValueError):
        svc.transfer_document_to_cost(seed['vehicle_id'], seed['doc_id'], {'cost_type': 'other', 'amount': 9}, None)
