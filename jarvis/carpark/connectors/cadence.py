"""Cadence → interval mapping for listing auto-update schedules."""
# 'manual' and 'instant' both map to None (no fixed polling interval). 'instant' is not
# scheduled via next_run_at — it's meant to be handled event-driven (triggered on vehicle
# save) by the future scheduler.
_MIN = {'2h': 120, '3h': 180, '5h': 300, 'daily': 1440, 'manual': None, 'instant': None}

# Single source of truth for the accepted cadence values (route validation etc.).
VALID_CADENCES = frozenset(_MIN.keys())


def cadence_to_minutes(cadence: str):
    if cadence not in _MIN:
        raise ValueError(f'Unknown cadence: {cadence}')
    return _MIN[cadence]
