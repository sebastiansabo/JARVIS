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

    # Orchestration tests must not depend on the real wall-clock: force the
    # weekday/business-hours send window open. Its own gating is covered below.
    monkeypatch.setattr(sess_mod, '_within_send_window', lambda *a, **k: True)

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


def test_overdue_message_formats_iso_string_return_datetime():
    """dict_from_row serializes timestamps to ISO strings, so in production
    return_datetime reaches the message as '2026-08-12T14:00:00+00:00', not a
    datetime. The alert must render the Bucharest wall-clock '12.08 14:00' and
    never leak the raw ISO string with its misleading +00:00 offset."""
    row = _row(return_datetime='2026-08-12T14:00:00+00:00')
    text, body_html = sess_mod._overdue_return_message(row)
    assert '12.08 14:00' in text
    assert '+00:00' not in text
    assert 'T14:00' not in text
    assert '12.08 14:00' in body_html


def test_overdue_message_frames_as_unrecorded_return():
    """The nudge is about an unrecorded return, not a physically overdue car
    (the return may already have happened on time). Wording must ask to record
    the return and drop the alarming 'trebuia predat' phrasing."""
    row = _row(return_datetime='2026-08-12T14:00:00+00:00', overdue_hours=2)
    text, _ = sess_mod._overdue_return_message(row)
    assert 'înregistrat' in text.lower()
    assert 'trebuia predat' not in text


@pytest.mark.parametrize('dt, expected', [
    # Mon 2026-08-17 .. Fri 2026-08-21 are weekdays; Sat/Sun 22/23 are weekend.
    (datetime(2026, 8, 17, 8, 0), True),    # Monday 08:00 — start edge, inclusive
    (datetime(2026, 8, 17, 12, 30), True),  # Monday midday
    (datetime(2026, 8, 21, 17, 59), True),  # Friday 17:59 — still inside
    (datetime(2026, 8, 17, 7, 59), False),  # Monday 07:59 — before window
    (datetime(2026, 8, 17, 18, 0), False),  # Monday 18:00 — end edge, exclusive
    (datetime(2026, 8, 17, 23, 30), False), # Monday night
    (datetime(2026, 8, 17, 3, 0), False),   # Monday small hours
    (datetime(2026, 8, 22, 10, 0), False),  # Saturday inside hours — still skipped
    (datetime(2026, 8, 23, 10, 0), False),  # Sunday inside hours — still skipped
])
def test_within_send_window(dt, expected):
    assert sess_mod._within_send_window(now=dt) is expected


def test_overdue_return_suppressed_outside_window(wired, monkeypatch):
    """When the send window is closed the pass is a full no-op: it never even
    queries the repo, so nothing is sent and no cooldown is written — the alert
    simply waits for the next in-window tick."""
    monkeypatch.setattr(sess_mod, '_within_send_window', lambda *a, **k: False)

    def boom():
        raise AssertionError('repo must not be queried outside the send window')
    monkeypatch.setattr(sess_mod, 'FoiParcursRepository', boom)

    sess_mod.notify_overdue_returns()

    assert wired['push'] == []
    assert wired['email'] == []


def test_run_session_lifecycle_invokes_overdue_pass(monkeypatch):
    called = {'overdue': False}
    monkeypatch.setattr(sess_mod, 'FoiParcursRepository', lambda: FakeRepo())
    monkeypatch.setattr(sess_mod, 'notify_overdue_returns',
                        lambda: called.__setitem__('overdue', True))

    sess_mod.run_session_lifecycle()

    assert called['overdue'] is True
