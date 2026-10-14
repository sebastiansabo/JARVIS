"""Smoke test for the buyback test harness (Task 0): proves the `client`
fixture boots the real app (`from app import app`) without needing any
buyback product code (none exists yet).
"""


def test_client_fixture_boots(client):
    # any always-mounted route returns without a 5xx; proves the app + client fixture work
    resp = client.get('/health')
    assert resp.status_code in (200, 302, 401, 404)


def test_external_notifications_are_muted():
    """Regression: conftest's autouse `_mute_external_notifications` must stub
    the real email/push sinks so no buyback test can leak a real notification
    (DB-backed decision tests transition records whose owner != actor, firing
    notify_owner at the real owner — see the fixture docstring).

    Discriminators: the real send_email returns (True, '') on success / (False,
    msg) on failure — never (True, None); the real send_push_to_users would run
    the cache/DB/FCM pipeline for a non-empty user list — the stub returns None.
    """
    import core.services.notification_service as ns
    import core.notifications.push_service as ps

    assert ns.send_email(to_email='x@x.ro', subject='s',
                         html_body='<p>h</p>', text_body='t') == (True, None)
    assert ps.send_push_to_users([1], 'title', 'body') is None
