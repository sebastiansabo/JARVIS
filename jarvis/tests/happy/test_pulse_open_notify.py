"""Pulse open must notify every invited user (in-app + push).

Regression for the reported bug: opening a Pulse only materialized
happy.pulse_invites and returned a count — no notification was ever sent,
so employees only discovered a pulse by polling GET /pulse/current.

DB-free: open_pulse's transaction body runs against a MagicMock cursor and
core.notifications.notify.notify_users is monkeypatched to capture the fan-out.
"""
from unittest.mock import MagicMock

import happy.repositories.pulse_repository as pr


def _fake_execute_many(invite_rows):
    """Run open_pulse's _work(cursor) against a MagicMock cursor whose final
    SELECT of invited user_ids returns invite_rows."""
    def _run(work):
        cur = MagicMock()
        cur.fetchall.return_value = invite_rows
        cur.fetchone.return_value = {"c": len(invite_rows)}
        return work(cur)
    return _run


def _draft_pulse(repo, monkeypatch):
    monkeypatch.setattr(repo, "get_pulse", lambda pulse_id: {"id": 7, "status": "draft", "title": "Pulse Q3"})
    monkeypatch.setattr(repo, "get_questions", lambda pulse_id: [{"id": 1}])


def test_open_pulse_notifies_every_invited_user(monkeypatch):
    repo = pr.PulseRepository()
    _draft_pulse(repo, monkeypatch)
    monkeypatch.setattr(repo, "execute_many",
                        _fake_execute_many([{"user_id": 11}, {"user_id": 22}, {"user_id": 33}]))

    captured = {}

    def _capture(user_ids, title, **kwargs):
        captured["user_ids"] = list(user_ids)
        captured["title"] = title
        captured["kwargs"] = kwargs

    monkeypatch.setattr("core.notifications.notify.notify_users", _capture)

    count = repo.open_pulse(pulse_id=7, now="2026-10-06T00:00:00Z")

    assert captured["user_ids"] == [11, 22, 33]        # all invitees notified
    assert captured["kwargs"].get("category") == "happy_announce"
    assert captured["kwargs"].get("link") == "/app/hub"
    assert count == 3                                   # return contract unchanged (count)


def test_open_pulse_with_no_invitees_sends_nothing(monkeypatch):
    repo = pr.PulseRepository()
    _draft_pulse(repo, monkeypatch)
    monkeypatch.setattr(repo, "execute_many", _fake_execute_many([]))

    calls = {"n": 0}
    monkeypatch.setattr("core.notifications.notify.notify_users",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))

    repo.open_pulse(pulse_id=7, now="2026-10-06T00:00:00Z")

    assert calls["n"] == 0


def test_open_pulse_survives_notification_failure(monkeypatch):
    """A push/in-app failure must never roll back or block going live."""
    repo = pr.PulseRepository()
    _draft_pulse(repo, monkeypatch)
    monkeypatch.setattr(repo, "execute_many", _fake_execute_many([{"user_id": 11}]))

    def _boom(*a, **k):
        raise RuntimeError("fcm down")

    monkeypatch.setattr("core.notifications.notify.notify_users", _boom)

    assert repo.open_pulse(pulse_id=7, now="2026-10-06T00:00:00Z") == 1
