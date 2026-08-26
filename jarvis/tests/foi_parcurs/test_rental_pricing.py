import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from foi_parcurs.services.rental_pricing import select_interval, compute_category_pricing

INTERVALS = [
    {'id': 1, 'min_days': 1, 'max_days': 8},
    {'id': 2, 'min_days': 9, 'max_days': 30},
    {'id': 3, 'min_days': 31, 'max_days': 90},
    {'id': 4, 'min_days': 91, 'max_days': 180},
    {'id': 5, 'min_days': 181, 'max_days': None},
]


def test_select_interval_lower_boundary():
    assert select_interval(INTERVALS, 1)['id'] == 1
    assert select_interval(INTERVALS, 8)['id'] == 1


def test_select_interval_crosses_boundary():
    assert select_interval(INTERVALS, 9)['id'] == 2
    assert select_interval(INTERVALS, 30)['id'] == 2
    assert select_interval(INTERVALS, 31)['id'] == 3
    assert select_interval(INTERVALS, 180)['id'] == 4


def test_select_interval_open_ended_top_band():
    assert select_interval(INTERVALS, 181)['id'] == 5
    assert select_interval(INTERVALS, 5000)['id'] == 5


def test_select_interval_no_match_returns_none():
    assert select_interval(INTERVALS, 0) is None
    assert select_interval([], 5) is None


def test_select_interval_unsorted_input():
    shuffled = list(reversed(INTERVALS))
    assert select_interval(shuffled, 15)['id'] == 2


def test_compute_category_pricing_multiplies_and_rounds():
    snap = compute_category_pricing(10, 33, 250, 0.25, 300)
    assert snap['svc_rate_basis'] == 'day'
    assert snap['svc_tariff_eur'] == 33
    assert snap['svc_units'] == 10
    assert snap['svc_total_eur'] == 330.0
    assert snap['svc_km_included_day'] == 300
    assert snap['svc_extra_km_eur'] == 0.25
    assert snap['svc_fransiza_eur'] == 250
    assert 'svc_garantie_eur' not in snap


def test_compute_category_pricing_none_rate_is_zero():
    snap = compute_category_pricing(5, None, None, None, None)
    assert snap['svc_tariff_eur'] == 0
    assert snap['svc_total_eur'] == 0
