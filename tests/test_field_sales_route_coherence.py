import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
from field_sales.repositories.visit_repository import VisitRepository


def test_create_route_uses_per_stop_company_id_with_route_fallback():
    repo = VisitRepository()
    calls = []
    def fake_execute(sql, params, returning=False):
        calls.append(params)
        return {'id': len(calls)}
    repo.execute = fake_execute
    data = {
        'kam_id': 3, 'planned_date': '2026-08-10', 'name': 'R', 'created_by': 1,
        'company_id': 99,  # route-level fallback
        'stops': [{'client_id': 10, 'company_id': 20}, {'client_id': 11}],
    }
    repo.create_route(data)
    # calls[0] = route insert; calls[1] = stop 1; calls[2] = stop 2.
    # company_id is the LAST param in each stop's INSERT tuple.
    assert calls[1][-1] == 20  # stop 1 uses its own company_id
    assert calls[2][-1] == 99  # stop 2 falls back to the route company_id
