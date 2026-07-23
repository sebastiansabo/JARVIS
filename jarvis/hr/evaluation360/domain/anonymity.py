"""Anonymity engine (spec §4, indicator B6). Pure — no DB.

A relationship category renders only with at least ``min_n`` submitted responses.
Self and manager categories are always attributed (n=1 is inherently
identifiable and both parties know it). Any attempt to expose a below-threshold,
non-attributed category is a hard error that must **fail closed** — the report
builder calls :func:`assert_renderable` on every category before rendering, and a
raised :class:`AnonymityViolation` blocks the render rather than leaking identity.
"""
from __future__ import annotations

ATTRIBUTED_RELATIONSHIPS = frozenset({'self', 'manager'})
DEFAULT_MIN_N = 3


class AnonymityViolation(Exception):
    """Raised on any attempt to expose a category below the anonymity threshold."""


def is_attributed(relationship: str) -> bool:
    """Whether a relationship is always shown (self / manager)."""
    return relationship in ATTRIBUTED_RELATIONSHIPS


def category_visible(relationship: str, n: int, min_n: int = DEFAULT_MIN_N) -> bool:
    """Whether a category may be rendered given its submitted-response count."""
    if is_attributed(relationship):
        return True
    return n >= min_n


def apply_anonymity(counts_by_relationship: dict, min_n: int = DEFAULT_MIN_N):
    """Split ``{relationship: n_submitted}`` into ``(visible, hidden)`` name lists."""
    visible, hidden = [], []
    for relationship, n in counts_by_relationship.items():
        target = visible if category_visible(relationship, n, min_n) else hidden
        target.append(relationship)
    return sorted(visible), sorted(hidden)


def assert_renderable(relationship: str, n: int, min_n: int = DEFAULT_MIN_N) -> None:
    """Fail-closed gate: raise unless the category is safe to render."""
    if not category_visible(relationship, n, min_n):
        raise AnonymityViolation(
            f"category {relationship!r} has n={n} < {min_n} and is not attributed — render blocked"
        )
