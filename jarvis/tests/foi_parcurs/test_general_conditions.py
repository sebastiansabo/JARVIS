import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock
from foi_parcurs.repositories.dealer_config_repository import DealerConfigRepository


def test_get_general_conditions_returns_text():
    repo = DealerConfigRepository()
    repo.query_one = MagicMock(return_value={'general_conditions': '## Titlu\n\ntext'})
    out = repo.get_general_conditions(5, 'MG Motor')
    assert out == '## Titlu\n\ntext'
    sql, params = repo.query_one.call_args[0]
    assert 'fp_dealer_config' in sql and 'general_conditions' in sql
    assert params == (5, 'MG Motor')


def test_get_general_conditions_empty_when_none():
    repo = DealerConfigRepository()
    repo.query_one = MagicMock(return_value=None)
    assert repo.get_general_conditions(5, 'MG Motor') == ''
    repo.query_one = MagicMock(return_value={'general_conditions': None})
    assert repo.get_general_conditions(5, 'MG Motor') == ''


import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.settings as settings_mod


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_get_general_conditions_by_vin(client, monkeypatch):
    monkeypatch.setattr(settings_mod._vehicle_repo, 'get_by_vin',
                        lambda vin: {'brand': 'MG Motor'})
    monkeypatch.setattr(settings_mod._dealer_repo, 'get_general_conditions',
                        lambda cid, brand: '## T\n\ntext' if (cid, brand) == (7, 'MG Motor') else '')
    r = client.get('/api/foi-parcurs/general-conditions?company_id=7&vin=WVW1')
    assert r.status_code == 200
    body = r.get_json()
    assert body['text'] == '## T\n\ntext'
    assert body['brand'] == 'MG Motor'


def test_get_general_conditions_empty_when_no_brand(client, monkeypatch):
    monkeypatch.setattr(settings_mod._vehicle_repo, 'get_by_vin', lambda vin: None)
    r = client.get('/api/foi-parcurs/general-conditions?company_id=7&vin=NOPE')
    assert r.status_code == 200
    assert r.get_json()['text'] == ''
