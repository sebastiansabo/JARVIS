import os
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from foi_parcurs.routes.export import _session_export_row


def test_export_row_distance_is_actual_not_estimate():
    r = {'km_start': 1236, 'km_end': 1258, 'distance_km': 1286}
    row = _session_export_row(r, {})
    assert row[-1] == 22  # actual odometer delta, not the 1286 estimate


def test_export_row_distance_zero_when_still_out():
    r = {'km_start': 921, 'km_end': 921, 'distance_km': 50}
    assert _session_export_row(r, {})[-1] == 0


def test_export_row_includes_brand_and_fuel_from_veh_map():
    r = {'vin': 'ABC123', 'km_start': 100, 'km_end': 110}
    veh_map = {'ABC123': {'brand': 'MG Motor', 'fuel_type': 'Hybrid'}}
    row = _session_export_row(r, veh_map)
    assert row[4] == 'ABC123'    # VIN
    assert row[5] == 'MG Motor'  # Brand / Departament
    assert row[6] == 'Hybrid'    # Combustibil


def test_export_row_brand_fuel_blank_when_vin_absent_from_map():
    r = {'vin': 'ZZZ999', 'km_start': 1, 'km_end': 1}
    row = _session_export_row(r, {})
    assert row[5] == '' and row[6] == ''
