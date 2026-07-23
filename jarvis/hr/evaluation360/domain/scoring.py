"""Scoring & aggregation for 360 reports (spec §8). Pure — no DB.

Rules encoded here (each has a proving test):
  * category score  = mean of *observed* ratings ("Not observed" excluded),
    displayed only when n ≥ anonymity threshold (self/manager attributed → n=1 OK);
  * others composite = mean of category means (NOT pooled responses) so a large
    peer group cannot drown out direct reports;
  * gap = self − others; |gap| ≥ 1.0 flags a Johari placement;
  * Johari quadrant split at 3.5 / 3.5;
  * single-rater outlier = a rating more than 2σ from its category mean (n ≥ 3).

"Not observed" is represented as ``None`` inside a ratings list.
"""
from __future__ import annotations

from statistics import mean, pstdev

NOT_OBSERVED = None
JOHARI_SPLIT = 3.5
GAP_FLAG = 1.0
OUTLIER_SIGMA = 2.0

# Johari quadrant labels
CONFIRMED_STRENGTH = 'confirmed_strength'
BLIND_SPOT = 'blind_spot'
HIDDEN_STRENGTH = 'hidden_strength'
AGREED_GROWTH = 'agreed_growth'


def observed(ratings: list) -> list:
    """The subset of ratings that are not 'Not observed' (``None``)."""
    return [r for r in ratings if r is not None]


def category_score(ratings: list, min_n: int = 3, attributed: bool = False):
    """Mean of observed ratings, or ``None`` when below the anonymity threshold.

    ``attributed=True`` (self / manager categories) bypasses the n-gate because
    those are inherently identifiable and both parties know it (spec §4.2).
    """
    obs = observed(ratings)
    n = len(obs)
    if n == 0:
        return None
    if not attributed and n < min_n:
        return None
    return round(mean(obs), 3)


def others_composite(category_means: list):
    """Mean of per-category means (equal weight per relationship), ignoring ``None``.

    NOT a pooled mean of all responses — that would let a large peer group
    dominate. Returns ``None`` if no category cleared its threshold.
    """
    vals = [m for m in category_means if m is not None]
    if not vals:
        return None
    return round(mean(vals), 3)


def gap(self_score, others_score):
    """self − others, or ``None`` if either side is missing."""
    if self_score is None or others_score is None:
        return None
    return round(self_score - others_score, 3)


def flags_johari(gap_value) -> bool:
    """Whether a gap is large enough (|gap| ≥ 1.0) to flag a Johari placement."""
    return gap_value is not None and abs(gap_value) >= GAP_FLAG


def johari_quadrant(self_score, others_score, split: float = JOHARI_SPLIT):
    """Classify (self, others) into one of the four Johari quadrants, or ``None``."""
    if self_score is None or others_score is None:
        return None
    hi_self = self_score >= split
    hi_others = others_score >= split
    if hi_self and hi_others:
        return CONFIRMED_STRENGTH
    if hi_self and not hi_others:
        return BLIND_SPOT
    if not hi_self and hi_others:
        return HIDDEN_STRENGTH
    return AGREED_GROWTH


def is_outlier(rating, category_ratings: list, sigma: float = OUTLIER_SIGMA) -> bool:
    """True if a single rater's ``rating`` is more than ``sigma``-σ from the rest.

    Computed *leave-one-out* — the target rating is compared against the mean/σ of
    the OTHER ratings in the category. This is both the intended framing ("is this
    one reviewer off from everyone else") and mathematically necessary: with the
    point included, population σ caps a single value at (n-1)/√n σ, so at small n
    (≤5) nothing could ever exceed 2σ. Requires at least 3 observed ratings; a
    unanimous cohort flags any differing target.
    """
    obs = observed(category_ratings)
    if rating is None or len(obs) < 3:
        return False
    others = list(obs)
    if rating in others:
        others.remove(rating)  # drop the single instance under test
    if len(others) < 2:
        return False
    m = mean(others)
    sd = pstdev(others)
    if sd == 0:
        return rating != m  # differs from a unanimous cohort → outlier
    return abs(rating - m) > sigma * sd
