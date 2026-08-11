"""Tests for DispoService — guarded status transitions with side effects.

All collaborators (DocumentRepository, ReservationRepository, VehicleRepository,
VehicleService, PublishingService, notify_user) are injected as mocks via the
constructor — mirrors the DI-via-constructor style used by
hr/evaluation360/services/*_service.py tests. No DB access; runs fine under the
psycopg2 mock installed by jarvis/conftest.py.
"""
from datetime import date
from unittest.mock import ANY, MagicMock

import pytest

from carpark.services.dispo_service import DispoService, REQUIRED_DOCS

COMPANY_ID = 10
OTHER_COMPANY_ID = 99
USER = {'id': 42, 'name': 'Ana Pop'}

BASE_VEHICLE = {
    'id': 1,
    'company_id': COMPANY_ID,
    'status': 'READY_FOR_SALE',
    'minimum_price': 9000,
    'acquisition_price': 8000,
    'sale_price': None,
    'salesperson_user_id': 55,
}


def _svc(vehicle=None):
    """Build a DispoService with every collaborator mocked.

    Returns (svc, mocks) where mocks is a dict of the six injected mocks so
    tests can set return_values / assert calls.
    """
    document_repo = MagicMock()
    reservation_repo = MagicMock()
    vehicle_repo = MagicMock()
    vehicle_service = MagicMock()
    publishing_service = MagicMock()
    notify_fn = MagicMock()

    vehicle_repo.get_by_id.return_value = dict(vehicle if vehicle is not None else BASE_VEHICLE)
    vehicle_service.get_status_history.return_value = []
    # get_cost_totals mirrors CostRepository.get_totals_by_vehicle: total_amount is
    # the VAT-EXCLUSIVE SUM(amount) the low-margin gate must key off (see
    # DispoService._low_margin_reasons); total_with_vat is VAT-inclusive.
    vehicle_service.get_cost_totals.return_value = {
        'total_amount': 0, 'total_vat': 0, 'total_with_vat': 0}
    vehicle_service.change_status.return_value = {'id': 1, 'status': 'CHANGED'}
    vehicle_service.update_vehicle.return_value = {'id': 1, 'status': 'UPDATED'}
    reservation_repo.create.return_value = {'id': 5, 'status': 'active'}
    reservation_repo.active_for_vehicle.return_value = None
    document_repo.has_type.return_value = True

    svc = DispoService(
        document_repo=document_repo,
        reservation_repo=reservation_repo,
        vehicle_repo=vehicle_repo,
        vehicle_service=vehicle_service,
        publishing_service=publishing_service,
        notify_fn=notify_fn,
    )
    mocks = {
        'document_repo': document_repo,
        'reservation_repo': reservation_repo,
        'vehicle_repo': vehicle_repo,
        'vehicle_service': vehicle_service,
        'publishing_service': publishing_service,
        'notify_fn': notify_fn,
    }
    return svc, mocks


# ── TENANT GUARD ──────────────────────────────────────────────────────────

def test_cross_company_vehicle_raises_permission_error_on_reserve():
    svc, mocks = _svc()
    with pytest.raises(PermissionError):
        svc.reserve(1, OTHER_COMPANY_ID, USER, {'client_name': 'X', 'reservation_end': date(2026, 9, 1)})
    mocks['reservation_repo'].create.assert_not_called()
    mocks['vehicle_service'].change_status.assert_not_called()


def test_missing_vehicle_raises_value_error():
    svc, mocks = _svc()
    mocks['vehicle_repo'].get_by_id.return_value = None
    with pytest.raises(ValueError):
        svc.reserve(999, COMPANY_ID, USER, {'client_name': 'X', 'reservation_end': date(2026, 9, 1)})


def test_checklist_tenant_guard():
    svc, mocks = _svc()
    with pytest.raises(PermissionError):
        svc.checklist(1, OTHER_COMPANY_ID)


# ── RESERVE ───────────────────────────────────────────────────────────────

def test_reserve_requires_client():
    svc, _ = _svc()
    with pytest.raises(ValueError):
        svc.reserve(1, COMPANY_ID, USER, {'reservation_end': date(2026, 9, 1)})


def test_reserve_requires_reservation_end():
    svc, _ = _svc()
    with pytest.raises(ValueError):
        svc.reserve(1, COMPANY_ID, USER, {'client_name': 'Ion Pop'})


def test_reserve_inserts_reservation_and_moves_to_reserved():
    svc, mocks = _svc()
    mocks['vehicle_service'].change_status.return_value = {'id': 1, 'status': 'RESERVED'}

    data = {'client_name': 'Ion Pop', 'reservation_end': date(2026, 9, 1), 'deposit_amount': 500}
    result = svc.reserve(1, COMPANY_ID, USER, data)

    create_args, create_kwargs = mocks['reservation_repo'].create.call_args
    assert create_args[0] == 1
    inserted = create_args[1]
    assert inserted['status'] == 'active'
    assert inserted['client_name'] == 'Ion Pop'
    assert inserted['deposit_amount'] == 500

    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'RESERVED', changed_by=42, notes=ANY)

    mocks['notify_fn'].assert_called_once()
    assert mocks['notify_fn'].call_args[0][0] == 55  # salesperson_user_id

    assert result['vehicle']['status'] == 'RESERVED'
    assert result['reservation']['id'] == 5


def test_reserve_without_salesperson_skips_notify():
    vehicle = dict(BASE_VEHICLE, salesperson_user_id=None)
    svc, mocks = _svc(vehicle)
    svc.reserve(1, COMPANY_ID, USER, {'client_name': 'Ion Pop', 'reservation_end': date(2026, 9, 1)})
    mocks['notify_fn'].assert_not_called()


# ── CANCEL RESERVATION ───────────────────────────────────────────────────

def test_cancel_reservation_requires_reason():
    svc, mocks = _svc()
    mocks['reservation_repo'].active_for_vehicle.return_value = {'id': 7}
    with pytest.raises(ValueError):
        svc.cancel_reservation(1, COMPANY_ID, USER, reason='')


def test_cancel_reservation_requires_active_reservation():
    svc, mocks = _svc()
    mocks['reservation_repo'].active_for_vehicle.return_value = None
    with pytest.raises(ValueError):
        svc.cancel_reservation(1, COMPANY_ID, USER, reason='Client backed out')


def test_cancel_reservation_restores_prior_status_from_history():
    svc, mocks = _svc()
    mocks['reservation_repo'].active_for_vehicle.return_value = {'id': 7}
    mocks['vehicle_service'].get_status_history.return_value = [
        {'old_status': 'LISTED', 'new_status': 'RESERVED'},   # most recent (DESC order)
        {'old_status': 'ACQUIRED', 'new_status': 'LISTED'},
    ]

    svc.cancel_reservation(1, COMPANY_ID, USER, reason='Client backed out')

    mocks['reservation_repo'].set_status.assert_called_once_with(7, 'cancelled')
    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'LISTED', changed_by=42, notes='Client backed out')


def test_cancel_reservation_falls_back_to_ready_for_sale_when_no_history():
    svc, mocks = _svc()
    mocks['reservation_repo'].active_for_vehicle.return_value = {'id': 7}
    mocks['vehicle_service'].get_status_history.return_value = []

    svc.cancel_reservation(1, COMPANY_ID, USER, reason='Client backed out')

    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'READY_FOR_SALE', changed_by=42, notes='Client backed out')


# ── SELL ──────────────────────────────────────────────────────────────────

def _sell_data(**overrides):
    data = {'sale_price': 12000, 'sale_type': 'CASH', 'sale_date': date(2026, 8, 10),
             'buyer_name': 'Popescu Vasile'}
    data.update(overrides)
    return data


def test_sell_requires_fields():
    svc, _ = _svc()
    with pytest.raises(ValueError):
        svc.sell(1, COMPANY_ID, USER, {'sale_price': 12000})


def test_sell_below_minimum_price_raises_low_margin_without_confirm():
    svc, mocks = _svc()  # minimum_price=9000
    with pytest.raises(ValueError) as exc_info:
        svc.sell(1, COMPANY_ID, USER, _sell_data(sale_price=8000))
    assert str(exc_info.value).startswith('LOW_MARGIN')
    mocks['vehicle_service'].update_vehicle.assert_not_called()
    mocks['vehicle_service'].change_status.assert_not_called()


def test_sell_negative_margin_without_minimum_price_raises():
    vehicle = dict(BASE_VEHICLE, minimum_price=None)  # acquisition_price=8000
    svc, mocks = _svc(vehicle)
    mocks['vehicle_service'].get_cost_totals.return_value = {
        'total_amount': 5000, 'total_vat': 0, 'total_with_vat': 5000,
    }
    with pytest.raises(ValueError) as exc_info:
        svc.sell(1, COMPANY_ID, USER, _sell_data(sale_price=10000))  # 10000-8000-5000 = -3000
    assert str(exc_info.value).startswith('LOW_MARGIN')


def test_sell_low_margin_gate_uses_vat_exclusive_cost_basis():
    """The low-margin gate must key off SUM(amount) (VAT-exclusive), matching
    DispoRepository's canonical gross_margin — NOT total_with_vat. Here the
    VAT-exclusive margin is positive (+500) so the sale proceeds; had the gate
    wrongly used the VAT-inclusive total (total_with_vat=2300) the margin would
    read -300 and LOW_MARGIN would fire. The non-zero vat_amount must not flip
    the decision."""
    vehicle = dict(BASE_VEHICLE, minimum_price=None)  # acquisition_price=8000
    svc, mocks = _svc(vehicle)
    mocks['vehicle_service'].get_cost_totals.return_value = {
        'total_amount': 1500, 'total_vat': 800, 'total_with_vat': 2300,
    }
    # 10000 - 8000 - 1500 = +500 (VAT-exclusive) → OK; VAT-inclusive would be -300.
    svc.sell(1, COMPANY_ID, USER, _sell_data(sale_price=10000))
    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'SOLD', changed_by=42, notes=ANY)


def test_sell_with_confirm_low_margin_proceeds_and_closes_reservation_and_deactivates():
    svc, mocks = _svc()
    mocks['reservation_repo'].active_for_vehicle.return_value = {'id': 9, 'status': 'active'}
    mocks['vehicle_service'].change_status.return_value = {'id': 1, 'status': 'SOLD'}

    result = svc.sell(1, COMPANY_ID, USER, _sell_data(sale_price=8000, confirm_low_margin=True))

    mocks['vehicle_service'].update_vehicle.assert_called_once()
    update_args = mocks['vehicle_service'].update_vehicle.call_args[0]
    assert update_args[0] == 1
    assert update_args[1]['sale_price'] == 8000
    assert update_args[1]['sale_type'] == 'CASH'
    assert update_args[1]['buyer_name'] == 'Popescu Vasile'

    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'SOLD', changed_by=42, notes=ANY)
    mocks['reservation_repo'].set_status.assert_called_once_with(9, 'converted')
    mocks['publishing_service'].deactivate_all.assert_called_once_with(1)
    mocks['notify_fn'].assert_called_once()
    assert result['vehicle']['status'] == 'SOLD'


def test_sell_at_or_above_minimum_with_positive_margin_does_not_require_confirm():
    svc, mocks = _svc()
    svc.sell(1, COMPANY_ID, USER, _sell_data(sale_price=12000))
    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'SOLD', changed_by=42, notes=ANY)


def test_sell_persists_crm_buyer_client_id():
    """A CRM-linked buyer writes buyer_client_id through to the vehicle."""
    svc, mocks = _svc()
    svc.sell(1, COMPANY_ID, USER, _sell_data(sale_price=12000, buyer_client_id=123))
    persisted = mocks['vehicle_service'].update_vehicle.call_args[0][1]
    assert persisted['buyer_client_id'] == 123
    assert persisted['buyer_name'] == 'Popescu Vasile'


def test_sell_free_text_buyer_clears_stale_crm_link():
    """Switching from a CRM-linked buyer to a walk-in / free-text name must
    CLEAR the old buyer_client_id (persist explicit None), not leave a stale
    link pointing at the wrong CRM client. The frontend sends buyer_client_id
    as an explicit null in this case; sell() keys off presence, not truthiness,
    so the None reaches update_vehicle and NULLs the column."""
    vehicle = dict(BASE_VEHICLE, buyer_client_id=123)
    svc, mocks = _svc(vehicle)
    svc.sell(1, COMPANY_ID, USER,
             _sell_data(sale_price=12000, buyer_client_id=None, buyer_name='Walk-in'))
    persisted = mocks['vehicle_service'].update_vehicle.call_args[0][1]
    assert 'buyer_client_id' in persisted
    assert persisted['buyer_client_id'] is None
    assert persisted['buyer_name'] == 'Walk-in'


# ── DELIVER ───────────────────────────────────────────────────────────────

def test_deliver_without_pv_livrare_raises():
    svc, mocks = _svc()
    mocks['document_repo'].has_type.return_value = False
    with pytest.raises(ValueError) as exc_info:
        svc.deliver(1, COMPANY_ID, USER, {'delivery_date': date(2026, 8, 10)})
    assert str(exc_info.value).startswith('MISSING_PV_LIVRARE')
    mocks['vehicle_service'].change_status.assert_not_called()


def test_deliver_requires_delivery_date():
    svc, mocks = _svc()
    mocks['document_repo'].has_type.return_value = True
    with pytest.raises(ValueError):
        svc.deliver(1, COMPANY_ID, USER, {})


def test_deliver_with_pv_livrare_succeeds():
    svc, mocks = _svc()
    mocks['document_repo'].has_type.return_value = True
    mocks['vehicle_service'].change_status.return_value = {'id': 1, 'status': 'DELIVERED'}

    result = svc.deliver(1, COMPANY_ID, USER, {'delivery_date': date(2026, 8, 10)})

    mocks['document_repo'].has_type.assert_called_once_with(1, 'pv_livrare')
    mocks['vehicle_service'].update_vehicle.assert_called_once_with(
        1, {'delivery_date': date(2026, 8, 10)}, updated_by=42, updated_by_name='Ana Pop')
    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'DELIVERED', changed_by=42, notes=ANY)
    mocks['notify_fn'].assert_called_once()
    assert result['vehicle']['status'] == 'DELIVERED'


# ── REMOVE FROM STOCK ─────────────────────────────────────────────────────

def test_remove_from_stock_requires_eligible_status():
    svc, _ = _svc(dict(BASE_VEHICLE, status='READY_FOR_SALE'))
    with pytest.raises(ValueError):
        svc.remove_from_stock(1, COMPANY_ID, USER)


@pytest.mark.parametrize('status', ['DELIVERED', 'TRANSFERRED', 'SCRAPPED', 'RETURNED'])
def test_remove_from_stock_succeeds_for_eligible_statuses(status):
    svc, mocks = _svc(dict(BASE_VEHICLE, status=status))
    svc.remove_from_stock(1, COMPANY_ID, USER)
    args, kwargs = mocks['vehicle_service'].update_vehicle.call_args
    assert args[0] == 1
    assert args[1]['stock_removed'] is True
    assert args[1]['stock_removed_date'] == date.today()


# ── REOPEN ────────────────────────────────────────────────────────────────

def test_reopen_requires_reason():
    svc, _ = _svc(dict(BASE_VEHICLE, status='SOLD'))
    with pytest.raises(ValueError):
        svc.reopen(1, COMPANY_ID, USER, reason='', target_status='LISTED')


def test_reopen_from_sold_clears_sale_fields():
    svc, mocks = _svc(dict(BASE_VEHICLE, status='SOLD'))
    svc.reopen(1, COMPANY_ID, USER, reason='Wrong price entered', target_status='LISTED')

    mocks['vehicle_service'].update_vehicle.assert_called_once()
    cleared = mocks['vehicle_service'].update_vehicle.call_args[0][1]
    assert cleared['sale_price'] is None
    assert cleared['sale_date'] is None
    assert cleared['buyer_name'] is None

    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'LISTED', changed_by=42, notes='Wrong price entered')


def test_reopen_from_delivered_also_clears_delivery_date():
    svc, mocks = _svc(dict(BASE_VEHICLE, status='DELIVERED'))
    svc.reopen(1, COMPANY_ID, USER, reason='Customer returned car', target_status='RETURNED')

    cleared = mocks['vehicle_service'].update_vehicle.call_args[0][1]
    assert cleared['delivery_date'] is None
    assert cleared['sale_price'] is None


def test_reopen_from_non_sale_status_does_not_touch_sale_fields():
    svc, mocks = _svc(dict(BASE_VEHICLE, status='LISTED'))
    svc.reopen(1, COMPANY_ID, USER, reason='Re-listing', target_status='READY_FOR_SALE')
    mocks['vehicle_service'].update_vehicle.assert_not_called()
    mocks['vehicle_service'].change_status.assert_called_once_with(
        1, 'READY_FOR_SALE', changed_by=42, notes='Re-listing')


def test_reopen_propagates_illegal_transition_from_change_status():
    svc, mocks = _svc(dict(BASE_VEHICLE, status='SCRAPPED'))
    mocks['vehicle_service'].change_status.side_effect = ValueError('Tranziție interzisă: SCRAPPED -> LISTED')
    with pytest.raises(ValueError):
        svc.reopen(1, COMPANY_ID, USER, reason='oops', target_status='LISTED')


# ── CHECKLIST ─────────────────────────────────────────────────────────────

def test_checklist_blocks_delivery_true_when_pv_livrare_absent():
    svc, mocks = _svc()
    mocks['document_repo'].distinct_types.return_value = ['pv_intrare']

    result = svc.checklist(1, COMPANY_ID)

    assert result['blocks_delivery'] is True
    assert 'pv_livrare' in result['missing']
    assert set(result['required']) == set(
        doc for docs in REQUIRED_DOCS.values() for doc in docs)


def test_checklist_blocks_delivery_false_when_pv_livrare_present():
    svc, mocks = _svc()
    all_docs = [d for docs in REQUIRED_DOCS.values() for d in docs]
    mocks['document_repo'].distinct_types.return_value = all_docs

    result = svc.checklist(1, COMPANY_ID)

    assert result['blocks_delivery'] is False
    assert result['missing'] == []
    assert result['present'] == all_docs
