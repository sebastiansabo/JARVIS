import os
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import inspect
from foi_parcurs.services import pdf_service as ps


def test_odometer_distance_is_delta():
    assert ps._odometer_distance_km({'km_start': 1236, 'km_end': 1258}) == 22


def test_odometer_distance_none_without_return():
    assert ps._odometer_distance_km({'km_start': 1236, 'km_end': None}) is None


def test_odometer_distance_none_for_in_progress_placeholder():
    # In-progress sessions store km_end == km_start (placeholder), not NULL.
    assert ps._odometer_distance_km({'km_start': 921, 'km_end': 921}) is None


def test_odometer_distance_handles_missing_start():
    assert ps._odometer_distance_km({'km_end': 50}) == 50


def test_custom_pdf_never_shows_estimate():
    # The estimate (distance_km / "estimată") must not appear in any export.
    assert 'estimat' not in inspect.getsource(ps.generate_custom_pdf).lower()


def test_legal_pdf_uses_odometer_distance_not_estimate():
    src = inspect.getsource(ps.generate_legal_pdf)
    assert '_odometer_distance_km' in src
    # A raw `'distance_km' not in src` is unsatisfiable by construction: the
    # sanctioned helper name `_odometer_distance_km` itself contains that
    # substring. Strip the helper name first, then any remaining `distance_km`
    # (single/double quote, bracket access, getattr, etc.) is the forbidden
    # estimate field reappearing.
    assert 'distance_km' not in src.replace('_odometer_distance_km', '')
