# tests/test_buyback_custody_handoff.py
import sys, os
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from buyback.services import carpark_handoff

RECORD = {
    'id': 11, 'company_id': 3, 'vin': 'WAUZZZ8V1JA123456',
    'brand': 'Audi', 'model': 'A3', 'variant': 'S line',
    'manufacture_date': None, 'mileage_km': 40000, 'fuel_type': 'petrol',
    'transmission': 'automatic', 'seller_name': 'Ion Pop', 'seller_cui': None,
    'is_trade_in': False,
}
AGREEMENT = {
    'owner_price': 10000, 'currency': 'EUR', 'commission_type': 'percent',
    'commission_value': 5, 'min_sale_price': 9500, 'contract_number': 'C-1',
    'agreement_date': '2026-10-14', 'expiry_date': None,
}


def test_handoff_custody_creates_consignment_vehicle_and_agreement():
    created = {'id': 77, 'vin': RECORD['vin']}
    svc = MagicMock()
    svc.create_vehicle.return_value = created
    consign_repo = MagicMock()
    with patch('carpark.services.vehicle_service.VehicleService', return_value=svc), \
         patch('carpark.repositories.consignment_repository.ConsignmentRepository', return_value=consign_repo), \
         patch.object(carpark_handoff, '_carry_photos') as carry, \
         patch.object(carpark_handoff, '_backlink') as backlink:
        veh = carpark_handoff.handoff_to_carpark_custody(RECORD, AGREEMENT, actor=9)

    data = svc.create_vehicle.call_args.args[0]
    assert data['is_consignment'] is True
    assert data['source'] == 'CUSTODIE'
    assert data['status'] == 'ACQUIRED'
    assert data['purchase_price_net'] is None
    assert data['company_id'] == 3
    consign_repo.create.assert_called_once_with(77, AGREEMENT, created_by=9)
    carry.assert_called_once_with(11, 77)
    backlink.assert_called_once_with(77, 11, 9)
    assert veh == created


def test_handoff_custody_propagates_vin_valueerror():
    svc = MagicMock()
    svc.create_vehicle.side_effect = ValueError('A vehicle with VIN X already exists')
    with patch('carpark.services.vehicle_service.VehicleService', return_value=svc), \
         patch('carpark.repositories.consignment_repository.ConsignmentRepository'):
        try:
            carpark_handoff.handoff_to_carpark_custody(RECORD, AGREEMENT, actor=9)
            assert False, 'expected ValueError'
        except ValueError as e:
            assert 'already exists' in str(e)
