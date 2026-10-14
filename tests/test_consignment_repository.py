import sys, os
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from carpark.repositories.consignment_repository import ConsignmentRepository


def test_create_inserts_vehicle_id_agreement_and_created_by():
    repo = ConsignmentRepository()
    agreement = {
        'owner_price': 10000, 'currency': 'EUR',
        'commission_type': 'percent', 'commission_value': 5,
        'min_sale_price': 9500, 'contract_number': 'C-1',
        'agreement_date': '2026-10-14', 'expiry_date': '2027-01-14',
    }
    with patch.object(ConsignmentRepository, 'execute', return_value={'vehicle_id': 42}) as ex:
        row = repo.create(42, agreement, created_by=7)
    sql, params = ex.call_args.args[0], ex.call_args.args[1]
    assert 'INSERT INTO carpark_vehicle_consignment' in sql
    assert params[0] == 42                 # vehicle_id first
    assert params[-1] == 7                 # created_by last
    assert 'percent' in params and 5 in params
    assert row == {'vehicle_id': 42}


def test_get_by_vehicle_queries_by_id():
    repo = ConsignmentRepository()
    with patch.object(ConsignmentRepository, 'query_one', return_value={'vehicle_id': 42}) as q:
        row = repo.get_by_vehicle(42)
    assert q.call_args.args[1] == (42,)
    assert row == {'vehicle_id': 42}
