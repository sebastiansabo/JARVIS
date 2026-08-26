import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.rental_tariffs as mod


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_get_categories_returns_list(client, monkeypatch):
    monkeypatch.setattr(mod._repo, 'list_categories',
                        lambda cid, active_only=False: [{'id': 7, 'name': 'SUV+', 'prices': {1: 33}}])
    r = client.get('/api/foi-parcurs/rental-tariffs/categories?company_id=11')
    assert r.status_code == 200
    assert r.get_json()['categories'][0]['name'] == 'SUV+'


def test_set_price_requires_admin(client, monkeypatch):
    monkeypatch.setattr(mod, '_is_admin', lambda: False)
    r = client.put('/api/foi-parcurs/rental-tariffs/prices',
                   json={'company_id': 11, 'category_id': 7, 'interval_id': 1, 'eur_per_day': 33})
    assert r.status_code == 403


def test_set_price_admin_ok(client, monkeypatch):
    monkeypatch.setattr(mod, '_is_admin', lambda: True)
    called = {}
    monkeypatch.setattr(mod._repo, 'set_price',
                        lambda *a: called.setdefault('args', a))
    r = client.put('/api/foi-parcurs/rental-tariffs/prices',
                   json={'company_id': 11, 'category_id': 7, 'interval_id': 1, 'eur_per_day': 33})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert called['args'] == (11, 7, 1, 33)


def test_delete_category_in_use_returns_400(client, monkeypatch):
    monkeypatch.setattr(mod, '_is_admin', lambda: True)
    def _boom(cid, catid):
        raise ValueError('folosită de 3 mașini')
    monkeypatch.setattr(mod._repo, 'delete_category', _boom)
    r = client.delete('/api/foi-parcurs/rental-tariffs/categories',
                      json={'company_id': 11, 'id': 7})
    assert r.status_code == 400
    assert 'mașini' in r.get_json()['error']
