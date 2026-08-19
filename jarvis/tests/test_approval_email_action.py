"""Email one-tap decide: GET /go/approval/act renders a no-login confirm page and
NEVER mutates (defeats mail-client link prefetch); POST performs the decision via the
approval engine. Token is per-approver + signed; a decided request short-circuits."""
import pytest
from flask import Flask

import core.deeplink.routes as dl
from core.approvals.action_token import make_action_token

SECRET = 'test-secret-key'


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = SECRET
    app.register_blueprint(dl.deeplink_bp)
    # Default: a pending leave request with a known summary.
    monkeypatch.setattr(dl, '_load_request', lambda rid: {
        'entity_type': 'form_submission', 'entity_id': 28, 'status': 'pending'})
    monkeypatch.setattr(dl, '_leave_summary_for', lambda req: {
        'requester_name': 'Seba', 'leave_date': '2026-08-20', 'start': '07:00',
        'end': '10:00', 'hours': 3, 'reason': 'Personal', 'notes': ''})
    calls = []
    monkeypatch.setattr(dl, '_do_decide',
                        lambda rid, decision, decided_by, comment: calls.append(
                            (rid, decision, decided_by, comment)))
    return app.test_client(), calls


def test_get_valid_token_renders_confirm_and_does_not_decide(client):
    c, calls = client
    tok = make_action_token(28, 1, 'approve', SECRET)
    r = c.get(f'/go/approval/act?token={tok}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '07:00' in body and '10:00' in body      # leave interval shown
    assert '<form' in body.lower()                   # decision happens via POST
    assert calls == []                               # GET must not mutate


def test_get_invalid_token_is_rejected_and_does_not_decide(client):
    c, calls = client
    r = c.get('/go/approval/act?token=garbage')
    assert r.status_code == 400
    assert calls == []


def test_post_approve_records_approved_decision(client):
    c, calls = client
    tok = make_action_token(28, 1, 'approve', SECRET)
    r = c.post('/go/approval/act', data={'token': tok})
    assert r.status_code == 200
    assert calls == [(28, 'approved', 1, None)]


def test_post_reject_requires_a_reason(client):
    c, calls = client
    tok = make_action_token(28, 1, 'reject', SECRET)
    r = c.post('/go/approval/act', data={'token': tok, 'reason': ''})
    assert r.status_code == 400
    assert calls == []                               # no decision without a reason


def test_post_reject_with_reason_records_rejected(client):
    c, calls = client
    tok = make_action_token(28, 1, 'reject', SECRET)
    r = c.post('/go/approval/act', data={'token': tok, 'reason': 'nu se poate'})
    assert r.status_code == 200
    assert calls == [(28, 'rejected', 1, 'nu se poate')]


def test_already_decided_request_short_circuits(client, monkeypatch):
    c, calls = client
    monkeypatch.setattr(dl, '_load_request', lambda rid: {
        'entity_type': 'form_submission', 'entity_id': 28, 'status': 'approved'})
    tok = make_action_token(28, 1, 'approve', SECRET)
    r = c.post('/go/approval/act', data={'token': tok})
    assert r.status_code == 200
    assert calls == []                               # not re-decided


def test_expired_token_post_does_not_decide(client):
    c, calls = client
    tok = make_action_token(28, 1, 'approve', SECRET)
    monkeypatch_secret = SECRET
    # simulate expiry by reading with a past max_age via the route's verifier
    import core.deeplink.routes as _dl
    orig = _dl.read_action_token
    _dl.read_action_token = lambda t, s, **k: orig(t, s, max_age=-1)
    try:
        r = c.post('/go/approval/act', data={'token': tok})
    finally:
        _dl.read_action_token = orig
    assert r.status_code == 400
    assert calls == []
