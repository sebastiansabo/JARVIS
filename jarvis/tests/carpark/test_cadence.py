import pytest
from carpark.connectors.cadence import cadence_to_minutes, VALID_CADENCES


@pytest.mark.parametrize('c,expected', [
    ('1h', 60), ('2h', 120), ('3h', 180), ('5h', 300), ('daily', 1440),
    ('manual', None), ('instant', None),
])
def test_cadence_to_minutes(c, expected):
    assert cadence_to_minutes(c) == expected


def test_unknown_cadence_raises():
    with pytest.raises(ValueError):
        cadence_to_minutes('weekly')


def test_cadence_1h_is_60():
    """Task 6: the new 1h cadence resolves to 60 minutes and is a recognized
    cadence string (VALID_CADENCES derives from the same _MIN dict, so adding
    the entry picks both up automatically)."""
    assert cadence_to_minutes('1h') == 60
    assert '1h' in VALID_CADENCES
