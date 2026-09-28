"""The activate form prefills a returning person-client's licence, so the backend
exposes the client's most recently captured licence (photo + number + expiry).
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


def _call(app, client_id, latest):
    from foi_parcurs.routes import clients
    fp = MagicMock()
    fp.get_latest_license_for_client.return_value = latest
    with app.test_request_context(f'/api/foi-parcurs/clients/{client_id}/last-license'):
        with patch.object(clients, '_fp_repo', fp):
            resp = clients.api_client_last_license(client_id)
    status = resp[1] if isinstance(resp, tuple) else 200
    body = (resp[0] if isinstance(resp, tuple) else resp).get_json()
    return status, body, fp.get_latest_license_for_client


def test_returns_client_prior_license(app):
    lic = {'driver_license_photo': 'data:image/png;base64,PRIOR',
           'driver_license_number': 'PB999', 'driver_license_expiry': '2031-02-02',
           'driver_license_serie': ''}
    status, body, getter = _call(app, 52432, lic)
    assert status == 200
    assert body['success'] is True
    assert body['license']['driver_license_photo'] == 'data:image/png;base64,PRIOR'
    assert body['license']['driver_license_number'] == 'PB999'
    getter.assert_called_once_with(52432)


def test_returns_null_when_no_license_on_file(app):
    status, body, _ = _call(app, 52432, None)
    assert status == 200
    assert body['success'] is True
    assert body['license'] is None
