"""Scheduled vehicle blocks (to-do #3) — route logic (repos monkeypatched)."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.vehicles as vroutes


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def _patch(monkeypatch, *, conflicts=None, created={'id': 7}):
    monkeypatch.setattr(vroutes._vehicle_repo, 'get_identity',
                        lambda vid: {'id': vid, 'vin': 'VIN1', 'company_id': 11})
    monkeypatch.setattr(vroutes._vehicle_repo, 'get_active_lockout_slugs',
                        lambda: {'service', 'damage'})
    monkeypatch.setattr(vroutes._fp_repo, 'find_conflicts',
                        lambda vin, frm, to, *a, **k: conflicts or [])
    captured = {}
    def fake_create(vehicle_id, category, note, start_date, end_date, user_id):
        captured.update(dict(vehicle_id=vehicle_id, category=category,
                             start_date=start_date, end_date=end_date))
        return {**created, **captured}
    monkeypatch.setattr(vroutes._vehicle_repo, 'create_scheduled_block', fake_create)
    return captured


def test_create_happy_path(client, monkeypatch):
    cap = _patch(monkeypatch)
    r = client.post('/api/foi-parcurs/vehicles/3/scheduled-blocks',
                    json={'category': 'service', 'start_date': '2026-09-01', 'end_date': '2026-09-03'})
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    assert cap['vehicle_id'] == 3 and cap['category'] == 'service'


def test_overlap_blocks_without_confirm(client, monkeypatch):
    _patch(monkeypatch, conflicts=[{'id': 99, 'status': 'PLANNED', 'client_name': 'X'}])
    r = client.post('/api/foi-parcurs/vehicles/3/scheduled-blocks',
                    json={'category': 'service', 'start_date': '2026-09-01', 'end_date': '2026-09-03'})
    assert r.status_code == 409
    assert r.get_json()['conflicts'][0]['id'] == 99


def test_overlap_allowed_with_confirm(client, monkeypatch):
    cap = _patch(monkeypatch, conflicts=[{'id': 99}])
    r = client.post('/api/foi-parcurs/vehicles/3/scheduled-blocks',
                    json={'category': 'service', 'start_date': '2026-09-01',
                          'end_date': '2026-09-03', 'allow_conflicts': True})
    assert r.status_code == 200 and cap['vehicle_id'] == 3


def test_invalid_category(client, monkeypatch):
    _patch(monkeypatch)
    r = client.post('/api/foi-parcurs/vehicles/3/scheduled-blocks',
                    json={'category': 'nope', 'start_date': '2026-09-01', 'end_date': '2026-09-03'})
    assert r.status_code == 400


def test_end_before_start(client, monkeypatch):
    _patch(monkeypatch)
    r = client.post('/api/foi-parcurs/vehicles/3/scheduled-blocks',
                    json={'category': 'service', 'start_date': '2026-09-05', 'end_date': '2026-09-01'})
    assert r.status_code == 400


def test_cancel(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(vroutes._vehicle_repo, 'get_scheduled_block',
                        lambda bid: {'id': bid, 'vehicle_id': 3})
    monkeypatch.setattr(vroutes._vehicle_repo, 'cancel_scheduled_block',
                        lambda bid: seen.setdefault('id', bid) or {'id': bid})
    r = client.delete('/api/foi-parcurs/vehicles/3/scheduled-blocks/5')
    assert r.status_code == 200 and seen['id'] == 5


def test_list(client, monkeypatch):
    monkeypatch.setattr(vroutes._vehicle_repo, 'list_scheduled_blocks',
                        lambda vid: [{'id': 1, 'state': 'upcoming'}])
    r = client.get('/api/foi-parcurs/vehicles/3/scheduled-blocks')
    assert r.status_code == 200 and r.get_json()['blocks'][0]['state'] == 'upcoming'
