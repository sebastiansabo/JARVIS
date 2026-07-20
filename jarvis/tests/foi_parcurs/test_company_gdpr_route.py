import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
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


def test_company_gdpr_returns_text(client, monkeypatch):
    monkeypatch.setattr(settings_mod, '_company_gdpr_lookup', lambda cid: '## T\n\nbody' if cid == 5 else '')
    r = client.get('/api/foi-parcurs/company-gdpr?company_id=5')
    assert r.status_code == 200
    assert r.get_json()['text'] == '## T\n\nbody'


def test_company_gdpr_empty(client, monkeypatch):
    monkeypatch.setattr(settings_mod, '_company_gdpr_lookup', lambda cid: '')
    r = client.get('/api/foi-parcurs/company-gdpr?company_id=999')
    assert r.status_code == 200
    assert r.get_json()['text'] == ''
