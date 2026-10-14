"""Buyback intake date naturalisation: validate_intake must accept common
Romanian date formats (DD.MM.YYYY, DD-MM-YYYY, DD/MM/YYYY, DD.MM.YY) as well
as ISO, normalise them to YYYY-MM-DD, treat blank as absent, and raise an
EXPLICIT error (naming the offending value) on anything unrecognised.

Regression cover for the production report: "manufacture_date must be an ISO
date (YYYY-MM-DD)" when a user entered a normal-looking date.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from buyback.routes._shared import validate_intake


@pytest.mark.parametrize('raw,expected', [
    ('2022-06-30', '2022-06-30'),   # ISO passes through unchanged
    ('30.06.2022', '2022-06-30'),   # DD.MM.YYYY (RO convention)
    ('30-06-2022', '2022-06-30'),   # DD-MM-YYYY
    ('30/06/2022', '2022-06-30'),   # DD/MM/YYYY
    ('30.06.22',   '2022-06-30'),   # DD.MM.YY (2-digit year)
    ('9.6.2022',   '2022-06-09'),   # single-digit day/month
])
def test_manufacture_date_naturalised_to_iso(raw, expected):
    out = validate_intake({'manufacture_date': raw})
    assert out['manufacture_date'] == expected


def test_first_registration_date_naturalised():
    out = validate_intake({'first_registration_date': '30.06.2022'})
    assert out['first_registration_date'] == '2022-06-30'


def test_blank_date_becomes_none():
    # The web form can POST '' for an untouched optional date — must not 400.
    out = validate_intake({'manufacture_date': ''})
    assert out['manufacture_date'] is None


def test_absent_date_untouched():
    out = validate_intake({'brand': 'Audi'})
    assert 'manufacture_date' not in out


def test_unrecognised_date_raises_explicit_error():
    with pytest.raises(ValueError) as e:
        validate_intake({'manufacture_date': 'June 2022'})
    msg = str(e.value)
    assert 'manufacture_date' in msg
    assert 'June 2022' in msg   # explicit: the error names the offending value


def test_impossible_date_raises():
    with pytest.raises(ValueError):
        validate_intake({'manufacture_date': '31.02.2022'})   # 31 Feb doesn't exist
