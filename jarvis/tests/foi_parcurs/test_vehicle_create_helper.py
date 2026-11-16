"""Unit tests for the shared `create_fp_vehicle` helper (no DB — mock repo).

This helper is the single source of truth for fp_vehicles create-validation,
extracted out of the manual Add-Vehicle route (POST /api/foi-parcurs/vehicles)
so a later "push to Driving Hub fleet" path can reuse the exact same rules
without drifting from the manual-add behavior.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock

from foi_parcurs.services.vehicle_create import create_fp_vehicle


def _repo(existing=None, created=None):
    """A MagicMock repo: get_by_vin -> existing row (or None), create -> created row."""
    repo = MagicMock()
    repo.get_by_vin.return_value = existing
    repo.create.return_value = created
    return repo


def _data(**over):
    d = {'vin': 'WAUZZZF4T1021365', 'mark': 'MG', 'model': 'ZS HEV'}
    d.update(over)
    return d


def test_rejects_missing_vin():
    repo = _repo()
    vehicle, err = create_fp_vehicle(_data(vin=''), repo=repo)
    assert vehicle is None
    assert err == ('VIN is required', 400)
    repo.create.assert_not_called()


def test_rejects_missing_mark():
    repo = _repo()
    vehicle, err = create_fp_vehicle(_data(mark=''), repo=repo)
    assert vehicle is None
    assert err == ('Mark is required', 400)
    repo.create.assert_not_called()


def test_rejects_missing_model():
    repo = _repo()
    vehicle, err = create_fp_vehicle(_data(model=''), repo=repo)
    assert vehicle is None
    assert err == ('Model is required', 400)
    repo.create.assert_not_called()


def test_rejects_unknown_fuel_type():
    repo = _repo()
    vehicle, err = create_fp_vehicle(_data(fuel_type='Nuclear'), repo=repo)
    assert vehicle is None
    assert err[1] == 400
    assert 'fuel_type' in err[0]
    repo.create.assert_not_called()


def test_rejects_missing_tank_capacity():
    repo = _repo()
    vehicle, err = create_fp_vehicle(_data(fuel_type='Diesel'), repo=repo)
    assert vehicle is None
    assert err == ('Fuel capacity (L) is required for this fuel type', 400)
    repo.create.assert_not_called()


def test_rejects_missing_battery_capacity():
    repo = _repo()
    vehicle, err = create_fp_vehicle(_data(fuel_type='Electric'), repo=repo)
    assert vehicle is None
    assert err == ('Battery capacity (kWh) is required for this fuel type', 400)
    repo.create.assert_not_called()


def test_hybrid_does_not_require_battery():
    """HEV: tank only — must not be gated on battery capacity (regression guard
    mirrored from test_vehicle_fuel_validation.py)."""
    repo = _repo(created={'id': 1})
    vehicle, err = create_fp_vehicle(
        _data(fuel_type='Hybrid', fuel_tank_capacity_liters=45), repo=repo)
    assert err is None
    assert vehicle == {'id': 1}
    kwargs = repo.create.call_args[0][0]
    assert kwargs['battery_capacity_kwh'] is None
    assert kwargs['fuel_tank_capacity_liters'] == 45.0


def test_duplicate_vin_returns_409():
    repo = _repo(existing={'id': 99, 'vin': 'WAUZZZF4T1021365'})
    vehicle, err = create_fp_vehicle(_data(fuel_type='Diesel', fuel_tank_capacity_liters=50), repo=repo)
    assert vehicle is None
    assert err == ('Vehicle with VIN WAUZZZF4T1021365 already exists', 409)
    repo.create.assert_not_called()


def test_success_sets_document_type_sales():
    repo = _repo(created={'id': 7})
    create_fp_vehicle(_data(fuel_type='Diesel', fuel_tank_capacity_liters=50, document_type=''), repo=repo)
    kwargs = repo.create.call_args[0][0]
    assert kwargs['document_type'] == 'sales'


def test_success_returns_created_vehicle():
    repo = _repo(created={'id': 7, 'vin': 'WAUZZZF4T1021365'})
    vehicle, err = create_fp_vehicle(
        _data(fuel_type='Diesel', fuel_tank_capacity_liters=50), repo=repo)
    assert err is None
    assert vehicle == {'id': 7, 'vin': 'WAUZZZF4T1021365'}


def test_create_payload_preserves_all_fields():
    """Field-preservation guard: every column the manual-add route previously
    built inline must still reach repo.create() — dropping any would silently
    break the Add-Vehicle form."""
    repo = _repo(created={'id': 1})
    data = {
        'vin': 'wauzzzf4t1021365',
        'mark': 'MG',
        'model': 'ZS HEV',
        'brand': 'MG Motor',
        'registration_number': 'sb 01 abc',
        'car_id': 'CAR-9',
        'color': 'Alb',
        'fuel_type': 'Diesel',
        'fuel_tank_capacity_liters': 50,
        'odometer_km': 12345,
        'norma_combustibil': 6.5,
        'norma_energie': 15.2,
        'category': 'SUV',
        'company_id': '3',
        'document_type': 'service',
        'svc_tariff_eur_day': 25,
        'svc_tariff_eur_month': 400,
        'svc_km_included_day': 150,
        'svc_extra_km_eur': 0.2,
        'svc_deposit_eur': 300,
        'svc_franchise_eur': 500,
        'vignette_valid_until': '2027-01-01',
        'itp_valid_until': '2027-02-01',
        'insurance_valid_until': '2027-03-01',
        'insurance_doc': 'data:application/pdf;base64,AAA',
        'talon_doc': 'data:application/pdf;base64,BBB',
        'civ_doc': 'data:application/pdf;base64,CCC',
        'registration_doc': 'data:application/pdf;base64,DDD',
        'offer_doc': 'data:application/pdf;base64,EEE',
    }
    create_fp_vehicle(data, repo=repo)
    payload = repo.create.call_args[0][0]
    assert payload == {
        'vin': 'WAUZZZF4T1021365',
        'registration_number': 'SB 01 ABC',
        'car_id': 'CAR-9',
        'mark': 'MG',
        'brand': 'MG Motor',
        'model': 'ZS HEV',
        'color': 'Alb',
        'fuel_type': 'Diesel',
        'fuel_tank_capacity_liters': 50.0,
        'battery_capacity_kwh': None,
        'odometer_km': 12345,
        'norma_combustibil': 6.5,
        'norma_energie': 15.2,
        'category': 'SUV',
        'company_id': 3,
        'document_type': 'service',
        'svc_tariff_eur_day': 25.0,
        'svc_tariff_eur_month': 400.0,
        'svc_km_included_day': 150,
        'svc_extra_km_eur': 0.2,
        'svc_deposit_eur': 300.0,
        'svc_franchise_eur': 500.0,
        'vignette_valid_until': '2027-01-01',
        'itp_valid_until': '2027-02-01',
        'insurance_valid_until': '2027-03-01',
        'insurance_doc': 'data:application/pdf;base64,AAA',
        'talon_doc': 'data:application/pdf;base64,BBB',
        'civ_doc': 'data:application/pdf;base64,CCC',
        'registration_doc': 'data:application/pdf;base64,DDD',
        'offer_doc': 'data:application/pdf;base64,EEE',
    }


def test_default_repo_is_module_level_fp_vehicle_repository():
    """repo kwarg is optional, defaulting to a module-level FPVehicleRepository()
    instance (production callers don't have to wire one up by hand)."""
    import foi_parcurs.services.vehicle_create as vc
    from foi_parcurs.repositories import FPVehicleRepository
    import inspect

    assert isinstance(vc._default_repo, FPVehicleRepository)
    assert 'repo' in inspect.signature(create_fp_vehicle).parameters
