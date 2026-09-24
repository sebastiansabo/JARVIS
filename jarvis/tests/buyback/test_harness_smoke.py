"""Smoke test for the buyback test harness (Task 0): proves the `client`
fixture boots the real app (`from app import app`) without needing any
buyback product code (none exists yet).
"""


def test_client_fixture_boots(client):
    # any always-mounted route returns without a 5xx; proves the app + client fixture work
    resp = client.get('/health')
    assert resp.status_code in (200, 302, 401, 404)
