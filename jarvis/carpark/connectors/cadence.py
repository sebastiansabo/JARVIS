"""Cadence → interval mapping for listing auto-update schedules."""
_MIN = {'2h': 120, '3h': 180, '5h': 300, 'daily': 1440, 'manual': None, 'instant': None}


def cadence_to_minutes(cadence: str):
    if cadence not in _MIN:
        raise ValueError(f'Unknown cadence: {cadence}')
    return _MIN[cadence]
