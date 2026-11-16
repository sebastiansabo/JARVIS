"""Tests for the CarPark -> Driving Hub fleet push service (mapping +
orchestration). No DB access: `FPVehicleRepository`/`VehicleRepository` are
monkeypatched onto the module-level singletons the service uses by default
(mirrors the `r._taxonomy_repo` / `r._photo_repo` monkeypatch idiom already
used by tests/carpark/test_autovit_push.py), and `create_fp_vehicle` (Task 1)
is monkeypatched directly so these tests never touch its own validation —
only the push service's own orchestration (company resolution, duplicate-VIN
short-circuit, payload building, best-effort is_test_drive flag write).
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock

import pytest

from carpark.services import driving_hub_push_service as svc


# ─────────────────────────────────────────────────────────────────────────
# map_fuel_to_fleet
# ─────────────────────────────────────────────────────────────────────────

def test_map_fuel_benzina():
    assert svc.map_fuel_to_fleet('Benzină') == 'Benzina'


def test_map_fuel_diesel():
    assert svc.map_fuel_to_fleet('Motorină') == 'Diesel'
    assert svc.map_fuel_to_fleet('diesel') == 'Diesel'


def test_map_fuel_mild_hybrid():
    assert svc.map_fuel_to_fleet('mild hybrid petrol') == 'Hybrid'


def test_map_fuel_plugin():
    assert svc.map_fuel_to_fleet('plug-in hybrid') == 'Plug-in Hybrid'


def test_map_fuel_unknown_is_none():
    assert svc.map_fuel_to_fleet('rocket fuel') is None


def test_map_fuel_blank_is_none():
    assert svc.map_fuel_to_fleet(None) is None
    assert svc.map_fuel_to_fleet('') is None


# ─────────────────────────────────────────────────────────────────────────
# build_suggested
# ─────────────────────────────────────────────────────────────────────────

def test_build_suggested_maps_carpark_fields():
    carpark_vehicle = {
        'brand': 'Volkswagen',
        'model': 'Golf',
        'registration_number': 'B 123 ABC',
        'fuel_type': 'Motorină',
        'company_id': 7,
        'mileage_km': 45000,
        'color_exterior': 'Gri',
    }
    suggested = svc.build_suggested(carpark_vehicle)
    assert suggested == {
        'mark': 'Volkswagen',
        'brand': 'Volkswagen',
        'model': 'Golf',
        'registration_number': 'B 123 ABC',
        'fuel_type': 'Diesel',
        'company_id': 7,
        'odometer_km': 45000,
        'color': 'Gri',
    }
    # Capacity keys are omitted — CarPark has no tank/battery capacity fields.
    assert 'fuel_tank_capacity_liters' not in suggested
    assert 'battery_capacity_kwh' not in suggested


def test_build_suggested_unmapped_fuel_is_none():
    suggested = svc.build_suggested({'fuel_type': 'rocket fuel'})
    assert suggested['fuel_type'] is None


# ─────────────────────────────────────────────────────────────────────────
# get_fleet_status
# ─────────────────────────────────────────────────────────────────────────

def test_status_not_in_fleet(monkeypatch):
    fp_repo = MagicMock()
    fp_repo.get_by_vin.return_value = None
    monkeypatch.setattr(svc, '_fp_repo', fp_repo)

    carpark_vehicle = {'vin': 'WVWZZZ1KZAW000001', 'brand': 'Volkswagen', 'model': 'Golf'}
    status = svc.get_fleet_status(carpark_vehicle)

    assert status['in_fleet'] is False
    assert status['archived'] is False
    assert status['fp_vehicle_id'] is None
    assert status['suggested'] == svc.build_suggested(carpark_vehicle)


def test_status_archived(monkeypatch):
    fp_repo = MagicMock()
    fp_repo.get_by_vin.return_value = {'id': 5, 'is_active': False}
    monkeypatch.setattr(svc, '_fp_repo', fp_repo)

    carpark_vehicle = {'vin': 'WVWZZZ1KZAW000002', 'brand': 'Volkswagen', 'model': 'Golf'}
    status = svc.get_fleet_status(carpark_vehicle)

    assert status['in_fleet'] is True
    assert status['archived'] is True
    assert status['fp_vehicle_id'] == 5


# ─────────────────────────────────────────────────────────────────────────
# push_to_fleet
# ─────────────────────────────────────────────────────────────────────────

COMPANY_ID = 10
OTHER_COMPANY_ID = 99
ACTABLE = {COMPANY_ID}

BASE_CARPARK_VEHICLE = {
    'id': 123,
    'vin': 'WVWZZZ1KZAW000009',
    'brand': 'Volkswagen',
    'model': 'Golf',
    'registration_number': 'B 123 ABC',
    'fuel_type': 'Motorină',
    'company_id': COMPANY_ID,
    'mileage_km': 45000,
    'color_exterior': 'Gri',
}


def _patched(monkeypatch, get_by_vin_return=None, create_fp_vehicle_return=None,
             brand_labels=None):
    """Wire up the service's module-level repo singletons + create_fp_vehicle
    as mocks, returning (fp_repo, vehicle_repo, create_mock).

    `brand_labels` seeds the catalog the brand guard validates against; it
    defaults to a catalog containing the BASE vehicle's make ('Volkswagen') so
    the happy-path tests clear the guard. Pass `[]` to simulate a company with
    no sales catalog (make fallback), or a list NOT containing the effective
    brand to trip the 400."""
    fp_repo = MagicMock()
    fp_repo.get_by_vin.return_value = get_by_vin_return
    fp_repo.list_sales_brand_labels.return_value = (
        ['Volkswagen'] if brand_labels is None else brand_labels)
    vehicle_repo = MagicMock()
    create_mock = MagicMock(return_value=create_fp_vehicle_return or (None, None))

    monkeypatch.setattr(svc, '_fp_repo', fp_repo)
    monkeypatch.setattr(svc, '_vehicle_repo', vehicle_repo)
    monkeypatch.setattr(svc, 'create_fp_vehicle', create_mock)

    return fp_repo, vehicle_repo, create_mock


def test_push_duplicate_vin_409(monkeypatch):
    _patched(monkeypatch, get_by_vin_return={'id': 5, 'vin': BASE_CARPARK_VEHICLE['vin']})

    result, err = svc.push_to_fleet(
        BASE_CARPARK_VEHICLE, {}, ACTABLE, is_admin=False)

    assert result is None
    assert err == {
        'status': 409,
        'message': 'Vehiculul este deja în flota Driving Hub',
        'fp_vehicle_id': 5,
    }


def test_push_company_not_actable_403(monkeypatch):
    _patched(monkeypatch, get_by_vin_return=None)

    result, err = svc.push_to_fleet(
        BASE_CARPARK_VEHICLE, {'company_id': OTHER_COMPANY_ID}, ACTABLE, is_admin=False)

    assert result is None
    assert err == {'status': 403, 'message': 'Companie neautorizată'}


def test_push_company_not_actable_but_admin_passes(monkeypatch):
    _patched(monkeypatch, get_by_vin_return=None,
             create_fp_vehicle_return=({'id': 11}, None))

    result, err = svc.push_to_fleet(
        BASE_CARPARK_VEHICLE, {'company_id': OTHER_COMPANY_ID, 'brand': 'Volkswagen'},
        ACTABLE, is_admin=True)

    assert err is None
    assert result == {'fp_vehicle_id': 11}


def test_push_no_company_required_400(monkeypatch):
    _patched(monkeypatch, get_by_vin_return=None)

    carpark_vehicle = dict(BASE_CARPARK_VEHICLE, company_id=None)
    result, err = svc.push_to_fleet(carpark_vehicle, {}, ACTABLE, is_admin=False)

    assert result is None
    assert err == {'status': 400, 'message': 'Selectează o companie'}


def test_push_translates_create_fp_vehicle_error(monkeypatch):
    _patched(monkeypatch, get_by_vin_return=None,
             create_fp_vehicle_return=(None, ('Mark is required', 400)))

    result, err = svc.push_to_fleet(BASE_CARPARK_VEHICLE, {}, ACTABLE, is_admin=False)

    assert result is None
    assert err == {'status': 400, 'message': 'Mark is required'}


def test_push_success_sets_is_test_drive(monkeypatch):
    fp_repo, vehicle_repo, create_mock = _patched(
        monkeypatch, get_by_vin_return=None,
        create_fp_vehicle_return=({'id': 7}, None))

    result, err = svc.push_to_fleet(
        BASE_CARPARK_VEHICLE, {'brand': 'Volkswagen'}, ACTABLE, is_admin=False)

    assert err is None
    assert result == {'fp_vehicle_id': 7}
    # the service's own lookup (BEFORE create_fp_vehicle) used the repo it
    # also hands to create_fp_vehicle, so both agree on duplicate state.
    create_mock.assert_called_once()
    (payload,), kwargs = create_mock.call_args
    assert kwargs.get('repo') is fp_repo
    # the validated catalog brand lands on the fp_vehicles payload; mark keeps
    # the CarPark make.
    assert payload['brand'] == 'Volkswagen'
    assert payload['mark'] == 'Volkswagen'
    vehicle_repo.set_test_drive.assert_called_once_with(
        BASE_CARPARK_VEHICLE['id'], True)


def test_push_flag_write_failure_still_succeeds(monkeypatch):
    fp_repo, vehicle_repo, create_mock = _patched(
        monkeypatch, get_by_vin_return=None,
        create_fp_vehicle_return=({'id': 9}, None))
    vehicle_repo.set_test_drive.side_effect = Exception('boom')

    result, err = svc.push_to_fleet(
        BASE_CARPARK_VEHICLE, {'brand': 'Volkswagen'}, ACTABLE, is_admin=False)

    assert err is None
    assert result == {'fp_vehicle_id': 9}


# ── brand / catalog validation ──────────────────────────────────────────────

def test_push_brand_not_in_catalog_400(monkeypatch):
    """An override brand outside a NON-EMPTY catalog is rejected (never created)."""
    _, _, create_mock = _patched(
        monkeypatch, get_by_vin_return=None, brand_labels=['Dacia', 'Ford'])

    result, err = svc.push_to_fleet(
        BASE_CARPARK_VEHICLE, {'brand': 'Tesla'}, ACTABLE, is_admin=False)

    assert result is None
    assert err == {'status': 400, 'message': 'Selectează o marcă validă din flotă'}
    create_mock.assert_not_called()


def test_push_make_not_in_nonempty_catalog_400(monkeypatch):
    """With no override, the make fallback must still be a catalog label."""
    _patched(monkeypatch, get_by_vin_return=None, brand_labels=['Dacia', 'Ford'])

    result, err = svc.push_to_fleet(BASE_CARPARK_VEHICLE, {}, ACTABLE, is_admin=False)

    assert result is None
    assert err == {'status': 400, 'message': 'Selectează o marcă validă din flotă'}


def test_push_valid_brand_override_written_to_payload(monkeypatch):
    """The chosen catalog label (e.g. 'MG Motor' vs CarPark make 'MG') is what
    lands on fp_vehicles.brand, while mark keeps the raw make."""
    _, _, create_mock = _patched(
        monkeypatch, get_by_vin_return=None, brand_labels=['MG Motor', 'Volkswagen'],
        create_fp_vehicle_return=({'id': 31}, None))

    result, err = svc.push_to_fleet(
        BASE_CARPARK_VEHICLE, {'brand': 'MG Motor'}, ACTABLE, is_admin=False)

    assert err is None
    assert result == {'fp_vehicle_id': 31}
    (payload,), _ = create_mock.call_args
    assert payload['brand'] == 'MG Motor'
    assert payload['mark'] == 'Volkswagen'


def test_push_empty_catalog_allows_make_fallback(monkeypatch):
    """A company with no sales catalog (courtesy/rental-only) allows the make
    straight through as the fleet brand."""
    _, _, create_mock = _patched(
        monkeypatch, get_by_vin_return=None, brand_labels=[],
        create_fp_vehicle_return=({'id': 21}, None))

    result, err = svc.push_to_fleet(BASE_CARPARK_VEHICLE, {}, ACTABLE, is_admin=False)

    assert err is None
    assert result == {'fp_vehicle_id': 21}
    (payload,), _ = create_mock.call_args
    assert payload['brand'] == 'Volkswagen'
    assert payload['mark'] == 'Volkswagen'
