"""Lightweight fleet list for pickers (e.g. the Test-Drive form car dropdown).

The full `_LIST_SELECT` computes a per-vehicle `mileage_floor` correlated
subquery (MAX(km_end) over all non-draft drives) plus on-drive / upcoming
LATERALs. On a large `foi_de_parcurs` history that mileage subquery is the
dominant cost and makes the form's car-picker fetch slow. Pickers only need the
base fields + the (cheap, indexed) active-block flag, so `get_all(light=True)`
must drop the heavy subqueries while keeping `blocked_now`.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
from foi_parcurs.repositories.vehicle_repository import FPVehicleRepository


def _built_sql(light):
    repo = FPVehicleRepository()
    repo.query_all = MagicMock(return_value=[])
    repo.get_all(light=light)
    return repo.query_all.call_args[0][0]


def test_light_list_omits_heavy_subqueries_but_keeps_block_flag():
    sql = _built_sql(light=True)
    # the expensive correlated subquery + the unneeded session LATERALs are gone
    assert 'mileage_floor' not in sql
    assert 'on_drive' not in sql
    assert 'upcoming_planned' not in sql
    # the cheap, indexed active-block flag pickers rely on to grey out cars stays
    assert 'blocked_now' in sql
    # still the base columns a picker renders
    assert 'v.vin' in sql and 'v.mark' in sql and 'v.model' in sql


def test_full_list_still_includes_mileage_floor():
    sql = _built_sql(light=False)
    assert 'mileage_floor' in sql
    assert 'on_drive' in sql
    assert 'upcoming_planned' in sql
