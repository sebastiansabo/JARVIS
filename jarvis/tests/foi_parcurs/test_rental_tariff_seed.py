import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from foi_parcurs.services.rental_tariff_seed import (
    SHARETOO_INTERVALS, SHARETOO_CATEGORIES, SHARETOO_COMPANY_ID,
)


def test_five_intervals_open_ended_top():
    assert len(SHARETOO_INTERVALS) == 5
    assert SHARETOO_INTERVALS[0][1] == 1 and SHARETOO_INTERVALS[0][2] == 8
    assert SHARETOO_INTERVALS[-1][1] == 181 and SHARETOO_INTERVALS[-1][2] is None


def test_eighteen_categories_each_with_five_prices():
    assert len(SHARETOO_CATEGORIES) == 18
    for name, note, fr, ekm, prices in SHARETOO_CATEGORIES:
        assert len(prices) == 5, name
        assert all(p > 0 for p in prices), name
        assert fr > 0 and ekm > 0, name


def test_spot_check_known_cells():
    by_name = {c[0]: c for c in SHARETOO_CATEGORIES}
    # SUV+ : 33/31/28/24/23, franchise 250, extra-km 0.25
    assert by_name['SUV+'][2] == 250
    assert by_name['SUV+'][3] == 0.25
    assert by_name['SUV+'][4] == (33, 31, 28, 24, 23)
    # LUXURY : 105/99/94/86/80, franchise 500, extra-km 0.50
    assert by_name['LUXURY'][4] == (105, 99, 94, 86, 80)
    assert by_name['LUXURY'][2] == 500
    # PREMIUM + : 45/42/32/30/29
    assert by_name['PREMIUM +'][4] == (45, 42, 32, 30, 29)


def test_company_is_autoworld_premium():
    assert SHARETOO_COMPANY_ID == 11
