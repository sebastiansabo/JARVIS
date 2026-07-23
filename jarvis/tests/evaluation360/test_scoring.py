"""Tests for 360 scoring & aggregation (spec §8)."""
from hr.evaluation360.domain import scoring as s


def test_not_observed_excluded_from_mean():
    # Ratings 4, 5, (not observed), 3  → mean of [4,5,3] = 4.0
    assert s.category_score([4, 5, None, 3], min_n=3) == 4.0


def test_category_gated_below_threshold():
    # Only 2 observed ratings, threshold 3 → hidden (None)
    assert s.category_score([4, 5], min_n=3) is None
    # 3 observed → shown
    assert s.category_score([4, 5, 3], min_n=3) == 4.0


def test_attributed_category_shows_at_n1():
    # Manager/self category (attributed) shows even at n=1
    assert s.category_score([5], min_n=3, attributed=True) == 5.0


def test_others_composite_is_mean_of_means_not_pooled():
    # 8 peers all rate 4 (mean 4.0); 3 direct reports all rate 2 (mean 2.0).
    peers = s.category_score([4] * 8, min_n=3)
    reports = s.category_score([2] * 3, min_n=3)
    composite = s.others_composite([peers, reports])
    assert composite == 3.0  # (4 + 2) / 2, NOT the pooled 38/11 ≈ 3.45
    pooled = (8 * 4 + 3 * 2) / 11
    assert abs(pooled - 3.454) < 0.01
    assert composite != round(pooled, 3)


def test_others_composite_ignores_hidden_categories():
    assert s.others_composite([4.0, None, 2.0]) == 3.0
    assert s.others_composite([None, None]) is None


def test_gap_and_johari_flag():
    assert s.gap(4.5, 3.0) == 1.5
    assert s.gap(4.0, None) is None
    assert s.flags_johari(1.5) is True
    assert s.flags_johari(0.5) is False
    assert s.flags_johari(None) is False


def test_johari_quadrants():
    assert s.johari_quadrant(4.0, 4.0) == s.CONFIRMED_STRENGTH
    assert s.johari_quadrant(4.0, 3.0) == s.BLIND_SPOT
    assert s.johari_quadrant(3.0, 4.0) == s.HIDDEN_STRENGTH
    assert s.johari_quadrant(2.0, 2.0) == s.AGREED_GROWTH
    # exactly on the split counts as "high"
    assert s.johari_quadrant(3.5, 3.5) == s.CONFIRMED_STRENGTH
    assert s.johari_quadrant(None, 3.0) is None


def test_single_rater_outlier_leave_one_out():
    # One rater at 1 against a cohort of 4s → clear outlier (works even at small n)
    ratings = [4, 4, 4, 4, 1]
    assert s.is_outlier(1, ratings) is True
    assert s.is_outlier(4, ratings) is False


def test_unanimous_cohort_has_no_outlier():
    # Everyone agrees → the matching rating is not an outlier
    assert s.is_outlier(3, [3, 3, 3, 3]) is False


def test_outlier_needs_min_three():
    assert s.is_outlier(1, [1, 5]) is False            # n < 3
    assert s.is_outlier(None, [4, 4, 4, 1]) is False   # not-observed is never an outlier
