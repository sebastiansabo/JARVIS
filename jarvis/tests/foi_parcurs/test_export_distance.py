import os
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from foi_parcurs.routes.export import _session_export_row


def test_export_row_distance_is_actual_not_estimate():
    r = {'km_start': 1236, 'km_end': 1258, 'distance_km': 1286}
    row = _session_export_row(r)
    assert row[-1] == 22  # actual odometer delta, not the 1286 estimate


def test_export_row_distance_zero_when_still_out():
    r = {'km_start': 921, 'km_end': 921, 'distance_km': 50}
    assert _session_export_row(r)[-1] == 0
