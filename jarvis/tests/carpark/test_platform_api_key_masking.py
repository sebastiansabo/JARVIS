"""Publishing-platform responses must never return the stored API key.

carpark_publishing_platforms.api_key_encrypted is write-only (set via
create/update); no client reads it back. Before this, GET /platforms and
GET /platforms/<id> returned SELECT * / p.* rows verbatim, leaking the key to
any CarPark user. All four response paths (list/get/create/update) must mask it.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from carpark import carpark_bp
import carpark.routes.vehicles as vehicles_mod
import carpark.routes.publishing as publishing_mod


class FakeUser:
    id = 1
    company_id = 1
    is_authenticated = True
    can_access_carpark = True
    can_edit_carpark = True
    can_access_settings = False


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(carpark_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    user = FakeUser()
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(publishing_mod, 'current_user', user)
    return app.test_client()


SECRET = 'SUPER-SECRET-KEY'


def _platform_row():
    return {'id': 1, 'name': 'Autovit', 'platform_type': 'autovit',
            'api_key_encrypted': SECRET, 'dealer_account_id': 'D1',
            'is_active': True, 'website_url': 'https://autovit.ro'}


def test_list_platforms_masks_api_key(client, monkeypatch):
    monkeypatch.setattr(publishing_mod._pub_service, 'list_platforms',
                        lambda company_id, active_only: [_platform_row()])
    r = client.get('/api/carpark/platforms')
    assert r.status_code == 200
    platforms = r.get_json()['platforms']
    assert len(platforms) == 1
    p = platforms[0]
    assert SECRET not in str(p), 'api key leaked in /platforms list'
    assert 'api_key_encrypted' not in p
    assert p['has_api_key'] is True          # "configured" hint preserved
    assert p['name'] == 'Autovit' and p['id'] == 1   # metadata intact


def test_get_platform_masks_api_key(client, monkeypatch):
    monkeypatch.setattr(publishing_mod._pub_service, 'get_platform',
                        lambda pid: _platform_row())
    r = client.get('/api/carpark/platforms/1')
    assert r.status_code == 200
    p = r.get_json()['platform']
    assert SECRET not in str(p), 'api key leaked in GET /platforms/<id>'
    assert 'api_key_encrypted' not in p
    assert p['has_api_key'] is True
    assert p['name'] == 'Autovit'


def test_has_api_key_false_when_unset(client, monkeypatch):
    row = _platform_row()
    row['api_key_encrypted'] = None
    monkeypatch.setattr(publishing_mod._pub_service, 'get_platform', lambda pid: row)
    r = client.get('/api/carpark/platforms/1')
    assert r.status_code == 200
    p = r.get_json()['platform']
    assert p['has_api_key'] is False
