"""Buyback intake write-failure handling: a DB write that fails must be
captured (telemetry) and returned as an EXPLICIT message, never the global
"An internal error occurred" that masked the equipment-overflow 500.
"""
import sys
import os

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(
        secret_key='test-secret',
        database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['LOGIN_DISABLED'] = True
    return application


class _User:
    id = 9


def test_intake_write_failed_returns_explicit_message_and_logs(app):
    from buyback.routes import records as rmod
    with app.test_request_context():
        with patch.object(rmod, 'current_user', _User()), \
             patch.object(rmod.logger, 'exception') as log:
            resp = rmod._intake_write_failed(
                'create',
                {'vin': 'WVGZZZCSZNY047528', 'company_id': 3, 'equipment': 'x' * 400},
                RuntimeError('boom'),
            )
    body, status = resp
    assert status == 500
    err = body.get_json()['error']
    assert err != 'An internal error occurred'   # explicit, not the opaque global message
    assert err                                     # non-empty, user-facing
    log.assert_called_once()                       # telemetry: the failure is recorded


def test_intake_write_failed_truncation_gives_field_hint(app):
    from buyback.routes import records as rmod

    class StringDataRightTruncation(Exception):
        pass

    with app.test_request_context():
        with patch.object(rmod, 'current_user', _User()), \
             patch.object(rmod.logger, 'exception'):
            resp = rmod._intake_write_failed(
                'create',
                {'equipment': 'x' * 400},
                StringDataRightTruncation(),
            )
    assert 'lungimea maximă' in resp[0].get_json()['error']


def test_intake_write_failed_payload_summary_excludes_long_strings(app):
    """Long strings are logged as str(len=N), not dumped verbatim (no PII/bloat)."""
    from buyback.routes import records as rmod
    with app.test_request_context():
        with patch.object(rmod, 'current_user', _User()), \
             patch.object(rmod.logger, 'exception') as log:
            rmod._intake_write_failed('create', {'equipment': 'y' * 400}, RuntimeError('x'))
    logged_args = log.call_args.args
    summary = logged_args[-1]            # last %s arg is the field summary dict
    assert summary['equipment'] == 'str(len=400)'


def test_intake_write_failed_redacts_seller_pii(app):
    """Seller contact/fiscal-id must be redacted (length only) in failure logs."""
    from buyback.routes import records as rmod
    with app.test_request_context():
        with patch.object(rmod, 'current_user', _User()), \
             patch.object(rmod.logger, 'exception') as log:
            rmod._intake_write_failed(
                'create',
                {'seller_name': 'Ion Pop', 'seller_cui': 'RO12345678',
                 'seller_phone': '0721234567', 'vin': 'WVGZZZCSZNY047528'},
                RuntimeError('x'),
            )
    summary = log.call_args.args[-1]
    assert 'Ion Pop' not in str(summary)          # no seller name
    assert 'RO12345678' not in str(summary)       # no fiscal id
    assert '0721234567' not in str(summary)       # no phone
    assert summary['seller_cui'].startswith('<redacted')
    assert summary['vin'] == 'WVGZZZCSZNY047528'  # non-PII kept for diagnosis


def test_create_route_truncation_returns_explicit_500(app):
    """End-to-end: a StringDataRightTruncation from the real create path (the
    equipment-overflow failure mode) returns 500 with the explicit Romanian
    message, not the opaque global handler, and never calls through further."""
    from buyback.routes import records as rmod
    from core.roles import decorators

    class StringDataRightTruncation(Exception):
        pass

    class _Admin:
        id = 9
        company_id = 3
        is_authenticated = True
        is_admin = True
        can_access_settings = True

    repo = MagicMock()
    repo.create.side_effect = StringDataRightTruncation()
    body = {'vin': 'WVGZZZCSZNY047528', 'brand': 'Volkswagen', 'model': 'Taigo',
            'equipment': 'x' * 400}
    with app.test_request_context(json=body):
        with patch.object(rmod._shared, 'records_repo', repo), \
             patch.object(rmod, '_scoped_company_id', return_value=3), \
             patch.object(rmod, 'current_user', _Admin()), \
             patch.object(decorators, 'current_user', _Admin()), \
             patch.object(rmod.logger, 'exception'):
            resp = rmod.create_record()
    body_json, status = resp
    assert status == 500
    assert 'lungimea maximă' in body_json.get_json()['error']
    repo.create.assert_called_once()
