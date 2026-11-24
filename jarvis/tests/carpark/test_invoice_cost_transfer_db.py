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
from carpark.repositories.cost_line_repository import CostLineRepository
from carpark.repositories.document_repository import DocumentRepository
from carpark.services.vehicle_service import VehicleService


def test_source_document_id_not_mass_assignable():
    """Always-run (no DB): source_document_id must NOT be in COST_FIELDS — it's
    server-controlled (set only by the transfer via the create() kwarg), so
    user-supplied `data` on the generic cost routes can't fake a document->cost
    link (IDOR)."""
    assert 'source_document_id' not in COST_FIELDS


def test_source_document_id_in_data_is_ignored(require_real_db, invoice_transfer_seed):
    """Passing source_document_id in `data` (the generic-route path) must not
    write it — only the explicit server-controlled kwarg does."""
    seed = invoice_transfer_seed
    cost = CostRepository().create(seed['vehicle_id'],
                                   {'cost_type': 'other', 'amount': 5, 'source_document_id': seed['doc_id']})
    assert cost['source_document_id'] is None


def test_source_document_id_unique_per_document(require_real_db, invoice_transfer_seed):
    # Two costs can't point at the same source document (partial unique index).
    seed = invoice_transfer_seed  # {'vehicle_id', 'doc_id'}
    CostRepository().create(seed['vehicle_id'], {'cost_type': 'other', 'amount': 10}, source_document_id=seed['doc_id'])
    with pytest.raises(Exception):  # unique_violation
        CostRepository().create(seed['vehicle_id'], {'cost_type': 'other', 'amount': 20}, source_document_id=seed['doc_id'])


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


def test_second_transfer_reuses_existing_cost_line(require_real_db, invoice_transfer_seed):
    """Two different documents of the same cost_type on one vehicle land under
    the SAME cost line — exercises the find/reuse branch of
    get_or_create_for_type (the 'idempotent' half of find-or-create). The
    second document references the same vehicle_id, so the fixture's
    vehicle-delete teardown cascades it away — no extra cleanup needed."""
    seed = invoice_transfer_seed
    vehicle_id = seed['vehicle_id']
    svc = VehicleService()

    # A second invoice document on the SAME vehicle.
    doc2 = DocumentRepository().create(vehicle_id, {
        'document_type': 'factura_achizitie', 'title': 'Test Factură achiziție 2'})

    cost1 = svc.transfer_document_to_cost(
        vehicle_id, seed['doc_id'], {'cost_type': 'transport', 'amount': 100}, None)
    cost2 = svc.transfer_document_to_cost(
        vehicle_id, doc2['id'], {'cost_type': 'transport', 'amount': 200}, None)

    # Reuse branch: both costs hang off one shared line (not two).
    assert cost1['cost_line_id'] == cost2['cost_line_id']

    transport_lines = [l for l in CostLineRepository().get_lines_by_vehicle(vehicle_id)
                       if l['cost_type'] == 'transport']
    assert len(transport_lines) == 1


# ── Fix wave (post-review hardening) ───────────────────────────────────────


def test_transfer_rejects_nonpositive_amount(require_real_db, invoice_transfer_seed):
    """Server-side guard: a missing/non-positive amount must be rejected even
    though the UI disables the confirm button for the same case — never trust
    the client on a financial write."""
    seed = invoice_transfer_seed
    with pytest.raises(ValueError):
        VehicleService().transfer_document_to_cost(
            seed['vehicle_id'], seed['doc_id'], {'cost_type': 'other', 'amount': 0}, None)


def test_transfer_updates_line_spent_amount(require_real_db, invoice_transfer_seed):
    """CostRepository.create() (used by the transfer path) is a flat insert
    that doesn't recalc the parent line's stored spent_amount the way
    CostLineRepository.create_cost() does — assert the service closes that
    gap by recalculating it explicitly after the transfer."""
    seed = invoice_transfer_seed
    cost = VehicleService().transfer_document_to_cost(
        seed['vehicle_id'], seed['doc_id'], {'cost_type': 'transport', 'amount': 250}, None)

    line = CostLineRepository().get_line_by_id(cost['cost_line_id'])
    assert float(line['spent_amount']) == 250


# ── VehicleService.transfer_document_to_revenue (income mirror) ────────────


def test_transfer_document_to_revenue_creates_linked_revenue(require_real_db, invoice_transfer_seed):
    seed = invoice_transfer_seed
    revenue = VehicleService().transfer_document_to_revenue(
        seed['vehicle_id'], seed['doc_id'],
        {'revenue_type': 'sale', 'amount': 1000, 'client_name': 'X', 'currency': 'RON'},
        None)
    assert revenue['source_document_id'] == seed['doc_id']
    assert revenue['revenue_type'] == 'sale'


def test_transfer_to_revenue_rejects_nonpositive_amount(require_real_db, invoice_transfer_seed):
    """Same server-side guard as the cost-transfer path (see
    test_transfer_rejects_nonpositive_amount above) — never trust the
    client's disabled-button validation on a financial write."""
    seed = invoice_transfer_seed
    with pytest.raises(ValueError):
        VehicleService().transfer_document_to_revenue(
            seed['vehicle_id'], seed['doc_id'], {'revenue_type': 'sale', 'amount': 0}, None)


def test_cross_table_dedup_cost_then_revenue(require_real_db, invoice_transfer_seed):
    """One document goes to one place: once a document has been transferred
    to a COST, transferring the SAME document to a REVENUE must be rejected
    too — the cross-table pre-check in transfer_document_to_revenue
    (find_by_source_document on both repos), not just the single-table
    partial unique index on carpark_vehicle_revenues."""
    seed = invoice_transfer_seed
    svc = VehicleService()
    svc.transfer_document_to_cost(seed['vehicle_id'], seed['doc_id'], {'cost_type': 'other', 'amount': 5}, None)
    with pytest.raises(ValueError):
        svc.transfer_document_to_revenue(
            seed['vehicle_id'], seed['doc_id'], {'revenue_type': 'sale', 'amount': 5}, None)


def test_cross_table_dedup_revenue_then_cost(require_real_db, invoice_transfer_seed):
    """Reverse of the above: a document already transferred to a REVENUE
    must reject a subsequent transfer to a COST."""
    seed = invoice_transfer_seed
    svc = VehicleService()
    svc.transfer_document_to_revenue(seed['vehicle_id'], seed['doc_id'], {'revenue_type': 'sale', 'amount': 5}, None)
    with pytest.raises(ValueError):
        svc.transfer_document_to_cost(
            seed['vehicle_id'], seed['doc_id'], {'cost_type': 'other', 'amount': 5}, None)


# ── CostLineRepository.delete_line cascade ──────────────────────────────────


def test_delete_line_cascades_and_frees_document(require_real_db, invoice_transfer_seed):
    """delete_line's cost_line_id FK is ON DELETE SET NULL, not CASCADE — left
    alone, deleting a line would orphan its costs (cost_line_id -> NULL)
    rather than remove them, leaving a ghost cost row that still keeps its
    source document locked ("already transferred"). Assert delete_line
    deletes the child cost row outright (not just detaches it)."""
    seed = invoice_transfer_seed
    cost = VehicleService().transfer_document_to_cost(
        seed['vehicle_id'], seed['doc_id'], {'cost_type': 'transport', 'amount': 100}, None)
    line_id = cost['cost_line_id']

    assert CostLineRepository().delete_line(line_id) is True

    remaining = CostRepository().find_by_source_document(seed['doc_id'])
    assert remaining is None
