import pytest
from carpark.connectors.cadence import cadence_to_minutes


@pytest.mark.parametrize('c,expected', [
    ('2h', 120), ('3h', 180), ('5h', 300), ('daily', 1440),
    ('manual', None), ('instant', None),
])
def test_cadence_to_minutes(c, expected):
    assert cadence_to_minutes(c) == expected


def test_unknown_cadence_raises():
    with pytest.raises(ValueError):
        cadence_to_minutes('weekly')
