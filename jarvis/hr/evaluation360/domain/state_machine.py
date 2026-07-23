"""Review-cycle state machine (spec §5). Pure — no DB, no side effects.

    DRAFT → NOMINATION → ACTIVE → CALIBRATION → RELEASED → CLOSED → ARCHIVED

Calibration is an optional stage: ACTIVE may transition straight to RELEASED.
Transitions are forward-only; there is no silent skipping and no reopening of a
released cycle. Guards (dry-run validation, anonymity-lock, etc.) are enforced by
the service layer before it calls :func:`assert_transition`.
"""
from __future__ import annotations

DRAFT = 'draft'
NOMINATION = 'nomination'
ACTIVE = 'active'
CALIBRATION = 'calibration'
RELEASED = 'released'
CLOSED = 'closed'
ARCHIVED = 'archived'

STATES = (DRAFT, NOMINATION, ACTIVE, CALIBRATION, RELEASED, CLOSED, ARCHIVED)

# Allowed forward transitions. ACTIVE→RELEASED skips the optional calibration.
_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({NOMINATION}),
    NOMINATION: frozenset({ACTIVE}),
    ACTIVE: frozenset({CALIBRATION, RELEASED}),
    CALIBRATION: frozenset({RELEASED}),
    RELEASED: frozenset({CLOSED}),
    CLOSED: frozenset({ARCHIVED}),
    ARCHIVED: frozenset(),
}

TERMINAL_STATES = frozenset({ARCHIVED})


class InvalidTransition(Exception):
    """Raised when a requested cycle state transition is not permitted."""


def is_valid_state(state: str) -> bool:
    return state in STATES


def next_states(current: str) -> frozenset[str]:
    """The set of states reachable from ``current`` in one step."""
    return _TRANSITIONS.get(current, frozenset())


def can_transition(current: str, target: str) -> bool:
    return target in next_states(current)


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def assert_transition(current: str, target: str) -> None:
    """Raise :class:`InvalidTransition` unless ``current → target`` is allowed."""
    if not is_valid_state(current):
        raise InvalidTransition(f'unknown current state {current!r}')
    if not is_valid_state(target):
        raise InvalidTransition(f'unknown target state {target!r}')
    if not can_transition(current, target):
        raise InvalidTransition(f'transition {current} → {target} is not allowed')
