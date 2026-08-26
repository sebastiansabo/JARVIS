"""Editing a PLANNED draft in place accepts the full-edit fields — Piece 1.

The /plan route already took company/vin/client/km/dates/advisor; the full-edit
(Corectează on a not-started session) also needs driver contact (snapshotted),
itinerary, observations and event. PLANNED-only.
"""
import sys, os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(
        secret_key='test-secret-key-for-tests',
        database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['LOGIN_DISABLED'] = True
    return application


PLANNED = {'id': 405, 'route_type': 'TD', 'status': 'PLANNED', 'fuel_tank_capacity_liters': 50}
CONTACT = {'id': 10, 'full_name': 'Calin Gonta', 'phone': '+40 742 757 404', 'email': 'g@x.ro',
           'driver_license_serie': '', 'driver_license_number': 'C00782060J',
           'driver_license_expiry': '2032-05-16', 'driver_license_photo': 'data:image/png;base64,AA'}


def _call(app, payload, contract=PLANNED):
    from foi_parcurs.routes import test_drive
    repo = MagicMock()
    repo.get_contract_by_id.return_value = contract
    repo.update_plan.return_value = {**contract, 'id': contract['id']}
    contact_repo = MagicMock()
    contact_repo.get.return_value = CONTACT
    with app.test_request_context('/x', method='PUT', json=payload):
        with patch.object(test_drive, '_fp_repo', repo), \
             patch.object(test_drive, '_contact_repo', contact_repo), \
             patch.object(test_drive, 'log_history', MagicMock()):
            resp = test_drive.api_update_plan(405)
    status = resp[1] if isinstance(resp, tuple) else 200
    return status, repo.update_plan


def test_accepts_driver_itinerary_observation_event(app):
    status, update_plan = _call(app, {
        'driver_contact_id': 10, 'itinerary': 'Traseu X',
        'general_observation': 'note', 'event_id': 7,
    })
    assert status == 200
    update = update_plan.call_args[0][1]
    assert update['driver_contact_id'] == 10
    assert update['driver_name'] == 'Calin Gonta'      # snapshotted from the contact
    assert update['driver_phone'] == '+40 742 757 404'
    assert update['itinerary'] == 'Traseu X'
    assert update['general_observation'] == 'note'
    assert update['event_id'] == 7


def test_blank_event_clears_it(app):
    status, update_plan = _call(app, {'event_id': None, 'itinerary': 'x'})
    assert status == 200
    assert update_plan.call_args[0][1]['event_id'] is None


def test_only_planned_drafts_editable(app):
    status, update_plan = _call(app, {'itinerary': 'x'}, contract={**PLANNED, 'status': 'FILLED'})
    assert status == 409 and not update_plan.called
