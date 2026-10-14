# tests/test_buyback_custody_route.py
"""Regression cover for POST /api/buyback/records/<id>/custody — the IDOR/
permission-sensitive route that transfers a failed (LOST) buyback record onto
CarPark custody (consignment).

The route is wrapped by @login_required + @v2_permission_required('buyback',
'record', 'custody'); tests call the route function directly inside
app.test_request_context(json=body) with app.config['LOGIN_DISABLED']=True so
@login_required's gate is skipped, and patch custody.current_user,
custody._shared.current_user, and core.roles.decorators.current_user with an
admin stand-in so the permission decorator's fast path (is_admin OR
can_access_settings) passes and runs the view body. _shared.current_user
specifically must be patched too (not just custody's own binding) because
`from flask_login import current_user` in _shared.py binds its own module
attribute — _shared._permitted_company_ids() (called by _guard_company) reads
ITS OWN `current_user` name, which an unpatched run would resolve to flask-
login's real AnonymousUserMixin (no session, no user_loader hit) and crash on
`.id`.

For the cross-company 403 case, building a non-admin user that still clears
the permission gate is hard against a mocked DB, so that test instead keeps
the admin user (passes the gate) and patches _shared._permitted_company_ids
directly to simulate a caller restricted to company 3 — _guard_company then
403s on a company-8 record before any vehicle/hand-off work happens. All
other tests leave _permitted_company_ids unpatched (the admin's real
unrestricted path through _guard_company).
"""
import sys, os
import pytest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


# ---- validator (pure) ----
from buyback.routes.custody import validate_custody_agreement


def test_validator_requires_known_commission_type():
    with pytest.raises(ValueError):
        validate_custody_agreement({'commission_type': 'maybe', 'commission_value': 5})


def test_validator_rejects_percent_over_100():
    with pytest.raises(ValueError):
        validate_custody_agreement({'commission_type': 'percent', 'commission_value': 150})


def test_validator_allows_large_fixed_commission():
    out = validate_custody_agreement({'commission_type': 'fixed', 'commission_value': 1500})
    assert out['commission_type'] == 'fixed'
    assert float(out['commission_value']) == 1500.0
    assert out['currency'] == 'EUR'  # default


def test_validator_rejects_expiry_before_agreement():
    with pytest.raises(ValueError):
        validate_custody_agreement({
            'commission_type': 'fixed', 'commission_value': 100,
            'agreement_date': '2026-10-14', 'expiry_date': '2026-01-01',
        })


def test_validator_rejects_dict_contract_number():
    with pytest.raises(ValueError):
        validate_custody_agreement({'commission_type': 'fixed', 'commission_value': 100, 'contract_number': {'x': 1}})


def test_validator_rejects_list_contract_number():
    with pytest.raises(ValueError):
        validate_custody_agreement({'commission_type': 'fixed', 'commission_value': 100, 'contract_number': ['a', 'b']})


# ---- route ----
@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(secret_key='t', database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'))
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['LOGIN_DISABLED'] = True
    return application


class _User:
    """Admin stand-in: is_admin/can_access_settings both True satisfies
    @v2_permission_required's fast path (sets scope 'all', runs the view)."""
    def __init__(self, company_id=3):
        self.id = 9
        self.company_id = company_id
        self.is_authenticated = True
        self.is_admin = True
        self.can_access_settings = True


LOST_REC = {'id': 11, 'status': 'LOST', 'company_id': 3, 'carpark_vehicle_id': None}
VALID_BODY = {'commission_type': 'fixed', 'commission_value': 500}


def _post(app, record, body, *, user_company=3):
    from buyback.routes import custody
    from core.roles import decorators
    records_repo = MagicMock()
    records_repo.get_by_id.return_value = record
    records_repo.update.return_value = {**(record or {}), 'carpark_vehicle_id': 77}
    with app.test_request_context(json=body):
        with patch.object(custody._shared, 'records_repo', records_repo), \
             patch.object(custody, 'current_user', _User(user_company)), \
             patch.object(custody._shared, 'current_user', _User(user_company)), \
             patch.object(decorators, 'current_user', _User(user_company)), \
             patch.object(custody, 'handoff_to_carpark_custody', return_value={'id': 77}) as handoff:
            resp = custody.transfer_to_custody(record['id'] if record else 11)
    status = resp[1] if isinstance(resp, tuple) else 200
    return status, handoff, records_repo


def test_happy_path_creates_and_links(app):
    status, handoff, repo = _post(app, LOST_REC, VALID_BODY)
    assert status == 200
    handoff.assert_called_once()
    repo.update.assert_called_once_with(11, {'carpark_vehicle_id': 77})


def test_non_lost_is_409(app):
    status, handoff, _ = _post(app, {**LOST_REC, 'status': 'BOUGHT'}, VALID_BODY)
    assert status == 409
    handoff.assert_not_called()


def test_already_transferred_is_409(app):
    status, handoff, _ = _post(app, {**LOST_REC, 'carpark_vehicle_id': 55}, VALID_BODY)
    assert status == 409
    handoff.assert_not_called()


def test_cross_company_is_403(app):
    """Caller permitted only company 3 (patched _permitted_company_ids), but
    the record belongs to company 8 -> _guard_company 403s before the status/
    agreement/handoff logic ever runs."""
    from buyback.routes import custody
    from core.roles import decorators
    record = {**LOST_REC, 'company_id': 8}
    records_repo = MagicMock()
    records_repo.get_by_id.return_value = record
    with app.test_request_context(json=VALID_BODY):
        with patch.object(custody._shared, 'records_repo', records_repo), \
             patch.object(custody._shared, '_permitted_company_ids', return_value={3}), \
             patch.object(custody, 'current_user', _User(3)), \
             patch.object(decorators, 'current_user', _User(3)), \
             patch.object(custody, 'handoff_to_carpark_custody', return_value={'id': 77}) as handoff:
            resp = custody.transfer_to_custody(11)
    status = resp[1] if isinstance(resp, tuple) else 200
    assert status == 403
    handoff.assert_not_called()
    records_repo.update.assert_not_called()


def test_bad_agreement_is_400(app):
    status, handoff, _ = _post(app, LOST_REC, {'commission_type': 'maybe', 'commission_value': 1})
    assert status == 400
    handoff.assert_not_called()


def test_missing_record_is_404(app):
    status, handoff, _ = _post(app, None, VALID_BODY)
    assert status == 404
    handoff.assert_not_called()


# ---- GET /api/buyback/records/<id> — consignment embed (Task 6) ----
# get_record() is decorated with @v2_permission_required('buyback', 'record',
# 'view') and calls _shared._guard_company -> _shared._permitted_company_ids,
# which reads _shared's OWN `current_user` binding (see module docstring
# above), so the admin stand-in must be patched into THREE places:
# core.roles.decorators.current_user (decorator's fast path), records_mod's
# own `current_user` (unused here but kept for parity), and
# records_mod._shared.current_user (the one that actually matters for the
# guard).

def _get_record(app, record, *, consignment_return=None):
    from buyback.routes import records as records_mod
    from core.roles import decorators
    records_repo = MagicMock()
    records_repo.get_by_id.return_value = record
    with app.test_request_context():
        with patch.object(records_mod._shared, 'records_repo', records_repo), \
             patch.object(records_mod._shared, 'offers_repo', MagicMock(list_for_record=MagicMock(return_value=[]))), \
             patch.object(records_mod._shared, 'photos_repo', MagicMock(get_by_record=MagicMock(return_value=[]))), \
             patch.object(records_mod._shared, 'events_repo', MagicMock(list_for_record=MagicMock(return_value=[]))), \
             patch.object(records_mod, 'current_user', _User(3)), \
             patch.object(records_mod._shared, 'current_user', _User(3)), \
             patch.object(decorators, 'current_user', _User(3)), \
             patch('carpark.repositories.consignment_repository.ConsignmentRepository') as CR:
            CR.return_value.get_by_vehicle.return_value = consignment_return
            resp = records_mod.get_record(record['id'])
    body = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
    return body, CR


def test_record_get_includes_consignment_when_lost_and_linked(app):
    rec = {'id': 11, 'status': 'LOST', 'company_id': 3, 'carpark_vehicle_id': 77}
    expected = {'vehicle_id': 77, 'commission_type': 'fixed'}
    body, CR = _get_record(app, rec, consignment_return=expected)
    assert body['consignment'] == expected
    CR.return_value.get_by_vehicle.assert_called_once_with(77)


def test_record_get_consignment_absent_when_not_lost_or_unlinked(app):
    # Non-LOST record: gate short-circuits on status, repo must not be hit.
    rec_bought = {'id': 12, 'status': 'BOUGHT', 'company_id': 3, 'carpark_vehicle_id': 77}
    body, CR = _get_record(app, rec_bought, consignment_return={'vehicle_id': 77})
    assert body['consignment'] is None
    CR.return_value.get_by_vehicle.assert_not_called()

    # LOST but never linked to a carpark vehicle: gate short-circuits on id.
    rec_unlinked = {'id': 13, 'status': 'LOST', 'company_id': 3, 'carpark_vehicle_id': None}
    body, CR = _get_record(app, rec_unlinked, consignment_return={'vehicle_id': 99})
    assert body['consignment'] is None
    CR.return_value.get_by_vehicle.assert_not_called()
