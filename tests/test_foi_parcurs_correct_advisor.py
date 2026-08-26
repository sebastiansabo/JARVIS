"""The session-correction route accepts a consilier (advisor_name) change.

Piece 2 of the Corectează work: an admin can fix a mis-assigned advisor from the
light correction dialog. The route must forward a non-empty advisor_name to
correct_session, allow an advisor-only correction (no km/date), and never wipe
the advisor with a blank value.
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


class _Admin:
    is_authenticated = True
    is_admin = True
    email = 'admin@example.ro'


CONTRACT = {'id': 405, 'status': 'FILLED', 'vin': 'WV1', 'km_start': 7491, 'km_end': 7491,
            'advisor_name': 'Sabo Sebastian Nicolae', 'departure_datetime': None, 'return_datetime': None}


def _call_correct(app, payload):
    """Invoke api_correct_contract with patched deps; return the correct_session mock."""
    from foi_parcurs.routes import contracts
    from core.roles import decorators
    repo = MagicMock()
    repo.get_contract_by_id.return_value = CONTRACT
    repo.correct_session.return_value = {**CONTRACT, **payload}
    repo.revive_to_active_if_window_open.return_value = None  # don't take the revive branch
    admin = _Admin()
    with app.test_request_context('/x', method='PUT', json=payload):
        with patch.object(contracts, '_fp_repo', repo), \
             patch.object(contracts, '_vehicle_repo', MagicMock()), \
             patch.object(contracts, 'current_user', admin), \
             patch.object(decorators, 'current_user', admin), \
             patch.object(contracts, 'log_history', MagicMock()), \
             patch.object(contracts, 'log_status_change', MagicMock()):
            resp = contracts.api_correct_contract(405)
    status = resp[1] if isinstance(resp, tuple) else 200
    return status, repo.correct_session


def test_advisor_only_correction_is_accepted_and_forwarded(app):
    status, correct = _call_correct(app, {'advisor_name': 'Pop Marius'})
    assert status == 200
    correct.assert_called_once()
    fields = correct.call_args[0][1]
    assert fields.get('advisor_name') == 'Pop Marius'


def test_blank_advisor_name_is_not_forwarded(app):
    # A blank advisor must never wipe the existing consilier. With no other
    # field, that leaves nothing to correct → 400.
    status, correct = _call_correct(app, {'advisor_name': '   '})
    assert status == 400
    assert not correct.called


def test_advisor_name_rides_along_with_km(app):
    status, correct = _call_correct(app, {'advisor_name': 'Pop Marius', 'km_start': 7500, 'km_end': 7600})
    assert status == 200
    fields = correct.call_args[0][1]
    assert fields.get('advisor_name') == 'Pop Marius'
    assert fields.get('km_start') == 7500 and fields.get('km_end') == 7600
