"""Tests for the Test Drive OVERDUE-RETURN alert pass
(tasks.foi_parcurs_sessions.notify_overdue_returns).

A session whose scheduled return_datetime has passed (+1h grace) and that the
consilier never returned is nudged: in-app + push to the consilier, plus an
email To: the consilier with the brand dealer inbox on CC. Re-fires are gated by
the SQL (get_overdue_return_sessions already excludes sessions on cooldown), so
these tests exercise pure orchestration with the repo/collaborators mocked.
"""
import os
from datetime import datetime

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import tasks.foi_parcurs_sessions as sess_mod


class FakeRepo:
    """Stand-in for FoiParcursRepository — records mark_* calls."""
    def __init__(self, overdue=None):
        self._overdue = overdue or []
        self.marked = []

    # overdue-return pass
    def get_overdue_return_sessions(self):
        return self._overdue

    def mark_overdue_return_notified(self, session_id):
        self.marked.append(session_id)

    # the other two passes run_session_lifecycle drives — no-ops here
    def get_sessions_pending_late_notify(self):
        return []

    def archive_missed_sessions(self):
        return 0


def _row(**o):
    r = {
        'id': 7,
        'advisor_name': 'Ana Pop',
        'advisor_user_id': 42,
        'advisor_email': 'ana.pop@autoworld.ro',
        'client_name': 'Ion Popescu',
        'vin': 'WVWZZZ1KZAW000001',
        'mark': 'Volkswagen',
        'model': 'Golf',
        'registration_number': 'CJ01ABC',
        'return_datetime': datetime(2026, 8, 12, 14, 0, 0),
        'company_id': 10,
        'company_name': 'Autoworld INTERNATIONAL S.R.L.',
        'vehicle_brand': 'Volkswagen (PKW)',
        'overdue_hours': 3,
    }
    r.update(o)
    return r


@pytest.fixture
def wired(monkeypatch):
    """Wire notify_overdue_returns' collaborators and capture their calls."""
    box = {'push': [], 'email': [], 'dealer_for': []}

    def fake_push(user_ids, title, message=None, **kwargs):
        box['push'].append({'user_ids': user_ids, 'title': title,
                            'message': message, **kwargs})
    monkeypatch.setattr(sess_mod, 'notify_with_push', fake_push)

    def fake_send(**kwargs):
        box['email'].append(kwargs)
        return True, ''
    monkeypatch.setattr(sess_mod, 'send_email', fake_send)

    def fake_dealer(company, brand):
        box['dealer_for'].append((company, brand))
        return {'email': box.get('_brand_email', 'vanzarivw@autoworld.ro')}
    monkeypatch.setattr(sess_mod, 'get_dealer_config', fake_dealer)

    return box


def _use_repo(monkeypatch, repo):
    monkeypatch.setattr(sess_mod, 'FoiParcursRepository', lambda: repo)


def test_overdue_return_notifies_consilier_and_marks(wired, monkeypatch):
    repo = FakeRepo(overdue=[_row()])
    _use_repo(monkeypatch, repo)

    sess_mod.notify_overdue_returns()

    # In-app + push to the consilier only
    assert len(wired['push']) == 1
    push = wired['push'][0]
    assert push['user_ids'] == [42]
    assert push['entity_type'] == 'foi_parcurs_td'
    assert push['entity_id'] == 7
    assert push['link'] == '/sales/test-drive/7'
    assert push['category'] == 'system'
    assert push['type'] == 'warning'
    # Message names client + vehicle + plate
    assert 'Ion Popescu' in push['message']
    assert 'Golf' in push['message']
    assert 'CJ01ABC' in push['message']

    # Email To: consilier, CC: brand inbox
    assert len(wired['email']) == 1
    email = wired['email'][0]
    assert email['to_email'] == 'ana.pop@autoworld.ro'
    assert email['department_cc'] == 'vanzarivw@autoworld.ro'
    assert email['subject'] == push['title']
    # Brand resolved from the session's (company, brand)
    assert wired['dealer_for'] == [('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen (PKW)')]
    # HTML email carries an absolute deep-link
    assert 'https://jarvis.autoworld.ro/sales/test-drive/7' in email['html_body']

    # Cooldown written exactly once
    assert repo.marked == [7]


def test_overdue_return_omits_cc_when_brand_email_blank(wired, monkeypatch):
    wired['_brand_email'] = ''  # brand configured with no email
    repo = FakeRepo(overdue=[_row()])
    _use_repo(monkeypatch, repo)

    sess_mod.notify_overdue_returns()

    assert len(wired['email']) == 1
    assert wired['email'][0]['department_cc'] is None
    assert repo.marked == [7]


def test_overdue_return_skips_when_advisor_unresolved(wired, monkeypatch):
    repo = FakeRepo(overdue=[_row(advisor_user_id=None, advisor_email=None)])
    _use_repo(monkeypatch, repo)

    sess_mod.notify_overdue_returns()

    assert wired['push'] == []
    assert wired['email'] == []
    assert repo.marked == []  # no cooldown → retried later


def test_overdue_return_isolates_per_session_failures(wired, monkeypatch):
    # First session's push raises; the second must still be processed.
    def boom_push(user_ids, title, message=None, **kwargs):
        if kwargs.get('entity_id') == 1:
            raise RuntimeError('push down')
        wired['push'].append({'user_ids': user_ids, 'entity_id': kwargs.get('entity_id')})
    monkeypatch.setattr(sess_mod, 'notify_with_push', boom_push)

    repo = FakeRepo(overdue=[_row(id=1), _row(id=2)])
    _use_repo(monkeypatch, repo)

    sess_mod.notify_overdue_returns()

    # Session 1 failed before marking; session 2 fully processed.
    assert repo.marked == [2]
    assert [p['entity_id'] for p in wired['push']] == [2]


def test_run_session_lifecycle_invokes_overdue_pass(monkeypatch):
    called = {'overdue': False}
    monkeypatch.setattr(sess_mod, 'FoiParcursRepository', lambda: FakeRepo())
    monkeypatch.setattr(sess_mod, 'notify_overdue_returns',
                        lambda: called.__setitem__('overdue', True))

    sess_mod.run_session_lifecycle()

    assert called['overdue'] is True
