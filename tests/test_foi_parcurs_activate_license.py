"""Activating a PLANNED test-drive draft must capture the driver's licence.

A draft can be booked ahead of time without a licence (create defers it), and the
one-step live submit already requires the licence photo for a person client. The
draft -> activate path used to skip it entirely, so a car could go out with no
licence on file. Activation now mirrors the submit gate for person clients:
require the licence photo (from the payload, or already on the contract) and
persist any licence fields sent at activation.
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


PLANNED_PERSON = {
    'id': 576, 'route_type': 'TD', 'status': 'PLANNED', 'document_type': 'sales',
    'company_id': 9, 'vin': 'LSJWC4390TZ585468', 'client_id': 52432,
    'fuel_tank_capacity_liters': 50, 'km_start': 1062,
    'departure_datetime': '2026-09-25T16:00', 'driver_license_photo': None,
    'signature_ai_generated': '',
}
PERSON_CLIENT = {'id': 52432, 'client_type': 'person', 'display_name': 'Cosmin Hurghis',
                 'phone': '+40752021352', 'cui': None}
VEH = {'vin': 'LSJWC4390TZ585468', 'document_type': 'sales', 'brand': 'MG Motor',
       'fuel_tank_capacity_liters': 50}


def _activate(app, payload, contract=PLANNED_PERSON, client=PERSON_CLIENT, prior_license=None):
    from foi_parcurs.routes import test_drive
    fp = MagicMock()
    fp.get_contract_by_id.return_value = contract
    fp.get_mileage_floor.return_value = 1062
    # Returning-client licence reuse: default to "no prior licence on file" so the
    # gate tests exercise a genuinely first-time client; individual tests override.
    fp.get_latest_license_for_client.return_value = prior_license
    fp.record_activation.return_value = {**contract, 'status': 'FILLED'}
    veh_repo = MagicMock()
    veh_repo.get_lock_by_vin.return_value = None
    veh_repo.get_by_vin.return_value = VEH
    crm = MagicMock(); crm.get_by_id.return_value = client
    dealer = MagicMock(); dealer.get_general_conditions.return_value = ''
    dt = MagicMock(); dt.is_rental.return_value = False; dt.get.return_value = {}
    with app.test_request_context('/x', method='PUT', json=payload):
        with patch.object(test_drive, '_fp_repo', fp), \
             patch.object(test_drive, '_vehicle_repo', veh_repo), \
             patch.object(test_drive, '_crm_client_repo', crm), \
             patch.object(test_drive, '_dealer_repo', dealer), \
             patch.object(test_drive, '_dt_repo', dt), \
             patch.object(test_drive, 'pools_match', lambda *a, **k: True), \
             patch.object(test_drive, 'is_privileged', lambda: False), \
             patch.object(test_drive, 'open_session_block', lambda *a, **k: None), \
             patch.object(test_drive, 'log_history', MagicMock()), \
             patch.object(test_drive, 'log_status_change', MagicMock()), \
             patch.object(test_drive, '_autosend_contract', MagicMock()), \
             patch('foi_parcurs.services.pdf_service.generate_legal_pdf', lambda *a, **k: '/tmp/x.pdf'), \
             patch('foi_parcurs.services.pdf_service.generate_custom_pdf', lambda *a, **k: '/tmp/y.pdf'), \
             patch('foi_parcurs.services.pdf_service.generate_service_contract_pdf', lambda *a, **k: '/tmp/z.pdf'):
            resp = test_drive.api_activate_test_drive(576)
    status = resp[1] if isinstance(resp, tuple) else 200
    body = (resp[0] if isinstance(resp, tuple) else resp).get_json()
    return status, body, fp.record_activation


def test_activation_requires_license_photo_for_person_client(app):
    status, body, rec = _activate(app, {'client_signature': 'sig'})
    assert status == 400
    assert 'Permis' in (body.get('error') or '')
    assert not rec.called


def test_activation_persists_license_fields_from_payload(app):
    status, body, rec = _activate(app, {
        'client_signature': 'sig',
        'driver_license_photo': 'data:image/png;base64,AAA',
        'driver_license_number': 'CJ123456',
        'driver_license_expiry': '2030-01-01',
    })
    assert status == 200
    update = rec.call_args[0][1]
    assert update['driver_license_photo'] == 'data:image/png;base64,AAA'
    assert update['driver_license_number'] == 'CJ123456'
    assert update['driver_license_expiry'] == '2030-01-01'


def test_activation_allowed_when_license_already_on_contract(app):
    contract = {**PLANNED_PERSON, 'driver_license_photo': 'data:image/png;base64,OLD'}
    status, body, rec = _activate(app, {'client_signature': 'sig'}, contract=contract)
    assert status == 200
    assert rec.called


def test_activation_reuses_prior_session_license_for_returning_client(app):
    # No licence on the payload or this session, but the client has one captured
    # on a prior session — reuse it instead of blocking (Option B).
    prior = {'driver_license_photo': 'data:image/png;base64,PRIOR',
             'driver_license_number': 'PB999', 'driver_license_expiry': '2031-02-02',
             'driver_license_serie': ''}
    status, body, rec = _activate(app, {'client_signature': 'sig'}, prior_license=prior)
    assert status == 200
    update = rec.call_args[0][1]
    assert update['driver_license_photo'] == 'data:image/png;base64,PRIOR'
    assert update['driver_license_number'] == 'PB999'


def test_activation_blocks_when_no_license_anywhere(app):
    # No payload, no contract, no prior session licence → still blocked.
    status, body, rec = _activate(app, {'client_signature': 'sig'}, prior_license=None)
    assert status == 400
    assert 'Permis' in (body.get('error') or '')
    assert not rec.called
