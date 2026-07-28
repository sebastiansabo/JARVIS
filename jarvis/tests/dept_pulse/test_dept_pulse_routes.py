"""GET/POST /profile/api/dept-pulse — gating, validation, shape, floor (Task 4)."""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

import core.profile.routes as routes
from core.profile import profile_bp


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.is_authenticated = True


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(profile_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    monkeypatch.setattr(routes, 'current_user', FakeUser(42))
    return app.test_client()


def test_get_returns_shape_and_floor_blanks_aggregate(client, monkeypatch):
    r = routes._dept_pulse_repo
    monkeypatch.setattr(r, 'resolve_department', lambda uid: {'node_id': 7, 'name': 'Vânzări', 'company_id': 11})
    monkeypatch.setattr(r, 'available_departments', lambda uid: [{'node_id': 7, 'name': 'Vânzări'}])
    monkeypatch.setattr(r, 'get_voter_count', lambda nid: 2)  # below floor
    monkeypatch.setattr(r, 'get_aggregate', lambda nid: [{'perspective': 'peer', 'competency_key': 'communication', 'avg': 4.0, 'voters': 2}])
    monkeypatch.setattr(r, 'get_my_votes', lambda uid, nid: [{'perspective': 'self', 'competency_key': 'communication', 'rating': 4}])

    resp = client.get('/profile/api/dept-pulse')
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['department']['node_id'] == 7
    assert body['min_voters'] == 3
    assert body['voter_count'] == 2
    assert body['aggregate'] == []          # blanked: voter_count < min_voters
    assert body['my_votes'][0]['rating'] == 4


def test_get_returns_aggregate_at_floor(client, monkeypatch):
    r = routes._dept_pulse_repo
    monkeypatch.setattr(r, 'resolve_department', lambda uid: {'node_id': 7, 'name': 'Vânzări', 'company_id': 11})
    monkeypatch.setattr(r, 'available_departments', lambda uid: [{'node_id': 7, 'name': 'Vânzări'}])
    monkeypatch.setattr(r, 'get_voter_count', lambda nid: 3)
    monkeypatch.setattr(r, 'get_aggregate', lambda nid: [{'perspective': 'peer', 'competency_key': 'communication', 'avg': 4.0, 'voters': 3}])
    monkeypatch.setattr(r, 'get_my_votes', lambda uid, nid: [])
    resp = client.get('/profile/api/dept-pulse')
    assert resp.get_json()['aggregate'][0]['voters'] == 3


def test_get_no_department_returns_null(client, monkeypatch):
    r = routes._dept_pulse_repo
    monkeypatch.setattr(r, 'resolve_department', lambda uid: None)
    monkeypatch.setattr(r, 'available_departments', lambda uid: [])
    resp = client.get('/profile/api/dept-pulse')
    body = resp.get_json()
    assert body['department'] is None
    assert body['aggregate'] == []
    assert body['my_votes'] == []


def test_get_ineligible_department_403(client, monkeypatch):
    r = routes._dept_pulse_repo
    monkeypatch.setattr(r, 'is_eligible', lambda uid, nid: False)
    monkeypatch.setattr(r, 'available_departments', lambda uid: [])
    resp = client.get('/profile/api/dept-pulse?department=999')
    assert resp.status_code == 403


def test_post_upserts_when_eligible(client, monkeypatch):
    r = routes._dept_pulse_repo
    calls = {}
    monkeypatch.setattr(r, 'is_eligible', lambda uid, nid: True)
    monkeypatch.setattr(r, 'upsert_vote', lambda *a: calls.setdefault('upsert', a))
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'peer',
        'competency_key': 'communication', 'rating': 4})
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True
    assert calls['upsert'] == (42, 7, 'peer', 'communication', 4)


def test_post_zero_rating_deletes(client, monkeypatch):
    r = routes._dept_pulse_repo
    calls = {}
    monkeypatch.setattr(r, 'is_eligible', lambda uid, nid: True)
    monkeypatch.setattr(r, 'delete_vote', lambda *a: calls.setdefault('delete', a))
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'peer',
        'competency_key': 'communication', 'rating': 0})
    assert resp.status_code == 200
    assert calls['delete'] == (42, 7, 'peer', 'communication')


def test_post_ineligible_403(client, monkeypatch):
    monkeypatch.setattr(routes._dept_pulse_repo, 'is_eligible', lambda uid, nid: False)
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'peer',
        'competency_key': 'communication', 'rating': 4})
    assert resp.status_code == 403


def test_post_invalid_perspective_400(client):
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'boss',
        'competency_key': 'communication', 'rating': 4})
    assert resp.status_code == 400


def test_post_invalid_rating_400(client, monkeypatch):
    monkeypatch.setattr(routes._dept_pulse_repo, 'is_eligible', lambda uid, nid: True)
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'peer',
        'competency_key': 'communication', 'rating': 9})
    assert resp.status_code == 400
