"""PricingService must not mutate the price of vehicles that are no longer for
sale. _get_eligible_vehicles (criteria + manual) and get_aging_vehicles pulled
from get_catalog with NO status filter, so execute_rule/simulate_rules wrote
current_price onto SOLD/DELIVERED cars and the aging alert listed them.

No DB: PricingService() builds repo objects whose methods we monkeypatch per
instance (runs under jarvis/conftest.py's psycopg2 mock).
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from carpark.services.pricing_service import PricingService


def test_eligible_criteria_excludes_terminal_statuses(monkeypatch):
    svc = PricingService()
    catalog = {'items': [
        {'id': 1, 'status': 'LISTED', 'current_price': 10000},
        {'id': 2, 'status': 'SOLD', 'current_price': 10000},
        {'id': 3, 'status': 'DELIVERED', 'current_price': 10000},
        {'id': 4, 'status': 'PRICE_REDUCED', 'current_price': 9000},
        {'id': 5, 'status': 'TRANSFERRED', 'current_price': 9000},
    ]}
    monkeypatch.setattr(svc._vehicle_repo, 'get_catalog',
                        lambda f, page=1, per_page=200: catalog)
    out = svc._get_eligible_vehicles({'id': 1, 'target_mode': 'criteria'}, company_id=1)
    assert {v['id'] for v in out} == {1, 4}  # SOLD/DELIVERED/TRANSFERRED excluded


def test_eligible_manual_excludes_terminal_statuses(monkeypatch):
    svc = PricingService()
    monkeypatch.setattr(svc._pricing_repo, 'get_rule_vehicle_ids', lambda rid: [1, 2, 3])
    rows = {1: {'id': 1, 'status': 'LISTED'},
            2: {'id': 2, 'status': 'SOLD'},
            3: {'id': 3, 'status': 'RESERVED'}}
    monkeypatch.setattr(svc._vehicle_repo, 'get_by_id', lambda vid: rows.get(vid))
    out = svc._get_eligible_vehicles({'id': 1, 'target_mode': 'manual'}, company_id=1)
    assert {v['id'] for v in out} == {1, 3}  # SOLD excluded; RESERVED kept (not terminal)


def test_aging_excludes_terminal_statuses(monkeypatch):
    svc = PricingService()
    catalog = {'items': [
        {'id': 1, 'status': 'LISTED', 'days_listed': 100, 'vin': 'V1',
         'current_price': 1, 'list_price': 1},
        {'id': 2, 'status': 'SOLD', 'days_listed': 200, 'vin': 'V2',
         'current_price': 1, 'list_price': 1},
    ]}
    monkeypatch.setattr(svc._vehicle_repo, 'get_catalog',
                        lambda f, page=1, per_page=200: catalog)
    out = svc.get_aging_vehicles(company_id=1, min_days=60)
    assert {v['vehicle_id'] for v in out} == {1}  # sold car not "aging stock"
