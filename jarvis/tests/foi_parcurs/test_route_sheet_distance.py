import os
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from foi_parcurs.services.route_sheet_service import session_actual_km, _span_km


def test_session_actual_km_is_odometer_delta():
    assert session_actual_km({'km_start': 1236, 'km_end': 1258}) == 22


def test_session_actual_km_zero_when_still_out():
    assert session_actual_km({'km_start': 921, 'km_end': 921}) == 0


def test_session_actual_km_handles_none():
    assert session_actual_km({'km_start': None, 'km_end': None}) == 0


def test_span_km_is_max_end_minus_min_start():
    trips = [
        {'km_start': 921, 'km_end': 921},
        {'km_start': 1236, 'km_end': 1258},
        {'km_start': 1270, 'km_end': 1286},
        {'km_start': 1281, 'km_end': 1313},
        {'km_start': 1313, 'km_end': 1335},
    ]
    assert _span_km(trips) == 414  # 1335 − 921


def test_span_km_empty():
    assert _span_km([]) == 0
