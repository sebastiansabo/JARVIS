"""VehicleRepository.set_test_drive — the best-effort is_test_drive flag write
the Driving Hub push service (carpark/services/driving_hub_push_service.py)
calls after a successful push, so the raw SQL stays in the repository (no
SQL outside repositories). Mirrors tests/foi_parcurs/test_vehicle_light_list.py's
MagicMock-query style: mock the repo's own `execute()` and assert the SQL +
params it was called with, with no real DB access.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock

from carpark.repositories.vehicle_repository import VehicleRepository


def test_set_test_drive_issues_expected_update():
    repo = VehicleRepository()
    repo.execute = MagicMock(return_value=1)

    result = repo.set_test_drive(42, True)

    sql, params = repo.execute.call_args[0]
    assert 'UPDATE carpark_vehicles' in sql
    assert 'is_test_drive = %s' in sql
    assert 'WHERE id = %s' in sql
    assert 'deleted_at IS NULL' in sql
    assert params == (True, 42)
    assert result is True


def test_set_test_drive_defaults_to_true():
    repo = VehicleRepository()
    repo.execute = MagicMock(return_value=1)

    repo.set_test_drive(7)

    params = repo.execute.call_args[0][1]
    assert params == (True, 7)


def test_set_test_drive_returns_false_when_no_row_updated():
    repo = VehicleRepository()
    repo.execute = MagicMock(return_value=0)

    assert repo.set_test_drive(99) is False
