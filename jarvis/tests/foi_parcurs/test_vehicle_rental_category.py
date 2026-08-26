import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
from foi_parcurs.repositories.vehicle_repository import FPVehicleRepository


def test_update_allows_rental_category_id():
    repo = FPVehicleRepository()
    repo.execute = MagicMock(return_value={'id': 3})
    repo.update(3, {'rental_category_id': 7})
    sql, params = repo.execute.call_args[0][0], repo.execute.call_args[0][1]
    assert 'rental_category_id' in sql
    assert 7 in params


def test_create_includes_rental_category_id_column():
    repo = FPVehicleRepository()
    repo.execute = MagicMock(return_value={'id': 1})
    repo.create({'vin': 'V1', 'mark': 'VW', 'model': 'T-Roc',
                 'fuel_type': 'petrol', 'rental_category_id': 7})
    sql = repo.execute.call_args[0][0]
    assert 'rental_category_id' in sql
