"""Real-DB integration tests for the logistics intake HTTP surface —
POST /api/logistics/intake/events + GET /api/logistics/intake/mapping
(Task 5 of the spine plan; auth + tenant-scoping hardening from review).

Uses the real Flask app (`app.py`) so the actual blueprint registration is
exercised end-to-end (mirrors jarvis/tests/carpark/test_photo_upload.py).
Unlike the carpark route tests, these endpoints are the server-to-server
jarvis-alpha feed — no @login_required. Auth is a FAIL-CLOSED shared-secret
gate: with no `LOGISTICS_INTAKE_SECRET` set, the endpoint 503s unless the
explicit `LOGISTICS_INTAKE_ALLOW_UNAUTH=1` dev/test bypass is present.

Env is controlled per-test with monkeypatch.setenv/delenv (auto-undone), so
these tests never depend on (or leak into) the ambient process environment.

Runs against localhost/defaultdb via the probe in conftest.py; DB-backed
assertions use the sentinel `TEST_COMPANY_ID` (990002) and the
`require_real_db` / `logistics_cleanup` fixtures already defined there.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb venv/bin/python -m pytest \
        jarvis/tests/logistics/test_intake_api.py -v
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository  # noqa: E402

from .conftest import TEST_COMPANY_ID  # noqa: E402

_EVENTS_URL = '/api/logistics/intake/events'
_MAPPING_URL = '/api/logistics/intake/mapping'

# A second sentinel company used only to prove /mapping scoping — distinct
# from TEST_COMPANY_ID so a cross-tenant leak would be visible.
_OTHER_COMPANY_ID = 990003


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


@pytest.fixture
def allow_unauth(monkeypatch):
    """Put the intake auth gate into the explicit dev/test bypass mode:
    no shared secret configured, but LOGISTICS_INTAKE_ALLOW_UNAUTH=1 so
    requests are accepted. Lets the body/validation/scoping behaviour be
    tested without threading a secret header through every request."""
    monkeypatch.delenv('LOGISTICS_INTAKE_SECRET', raising=False)
    monkeypatch.setenv('LOGISTICS_INTAKE_ALLOW_UNAUTH', '1')


def _count_vehicles(order_ref: str) -> int:
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT COUNT(*) AS cnt FROM logistics_vehicles WHERE order_ref = %s', (order_ref,))
        return cur.fetchone()['cnt']
    finally:
        release_db(conn)


# ── Auth gate (fail-closed) ──────────────────────────────────────────────

def test_post_without_secret_and_no_bypass_returns_503(client, monkeypatch):
    """Fail-closed: no LOGISTICS_INTAKE_SECRET and no bypass flag -> 503, the
    request never reaches validation/apply_event."""
    monkeypatch.delenv('LOGISTICS_INTAKE_SECRET', raising=False)
    monkeypatch.delenv('LOGISTICS_INTAKE_ALLOW_UNAUTH', raising=False)
    r = client.post(_EVENTS_URL, json={
        'order_ref': 'AW-NOAUTH', 'code': 'Transport in derulare',
        'event_ts': 1732600000, 'payload': {},
    })
    assert r.status_code == 503
    assert r.get_json() == {'error': 'Intake auth not configured'}


def test_post_with_secret_correct_header_works_wrong_header_401(client, monkeypatch, require_real_db, logistics_cleanup):
    """With a shared secret configured: correct X-Intake-Secret header is
    accepted; wrong/missing header is 401."""
    monkeypatch.setenv('LOGISTICS_INTAKE_SECRET', 's3cr3t-token')
    monkeypatch.delenv('LOGISTICS_INTAKE_ALLOW_UNAUTH', raising=False)

    order_ref = 'AW-INTAKE-API-SECRET'
    event = {
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 1732600300,
        'payload': {'company_id': TEST_COMPANY_ID, 'destinatie': 'Intern'},
    }

    # Wrong header -> 401, nothing created.
    bad = client.post(_EVENTS_URL, json=event, headers={'X-Intake-Secret': 'nope'})
    assert bad.status_code == 401
    assert _count_vehicles(order_ref) == 0

    # Missing header -> 401.
    missing = client.post(_EVENTS_URL, json=event)
    assert missing.status_code == 401

    # Correct header -> processed.
    ok = client.post(_EVENTS_URL, json=event, headers={'X-Intake-Secret': 's3cr3t-token'})
    assert ok.status_code == 200
    assert ok.get_json()['result'] == 'created'
    assert _count_vehicles(order_ref) == 1


# ── Events: create / duplicate / malformed ───────────────────────────────

def test_post_twice_created_then_duplicate_one_vehicle(client, allow_unauth, require_real_db, logistics_cleanup):
    order_ref = 'AW-INTAKE-API-1'
    event = {
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 1732600100,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Intern',
            'eta': '2026-12-02T10:00:00',
        },
    }

    first = client.post(_EVENTS_URL, json=event)
    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body['result'] == 'created'
    assert first_body.get('vehicle_id') is not None

    second = client.post(_EVENTS_URL, json=event)
    assert second.status_code == 200
    assert second.get_json()['result'] == 'duplicate'

    assert _count_vehicles(order_ref) == 1
    vehicle_repo = LogisticsVehicleRepository()
    vehicle = vehicle_repo.get_vehicle_by_order_ref(order_ref, TEST_COMPANY_ID)
    assert vehicle is not None
    assert vehicle['id'] == first_body['vehicle_id']


def test_malformed_body_returns_ignored_and_logs_event(client, allow_unauth, require_real_db):
    marker_code = 'TEST-MALFORMED-INTAKE-MARKER'

    def _delete_marker_rows():
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('DELETE FROM logistics_intake_events WHERE code = %s', (marker_code,))
            conn.commit()
        finally:
            release_db(conn)

    _delete_marker_rows()  # defensive: wipe any leftover row from a crashed prior run
    try:
        # Deliberately missing `order_ref` — malformed per the validation
        # contract (order_ref/code/event_ts/payload all required).
        bad_body = {
            'code': marker_code,
            'event_ts': 1732600200,
            'payload': {'company_id': TEST_COMPANY_ID},
        }

        r = client.post(_EVENTS_URL, json=bad_body)

        assert r.status_code == 200
        assert r.get_json() == {'result': 'ignored'}

        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('SELECT * FROM logistics_intake_events WHERE code = %s', (marker_code,))
            rows = cur.fetchall()
        finally:
            release_db(conn)
        assert len(rows) == 1
        assert rows[0]['result'] == 'ignored'
    finally:
        _delete_marker_rows()


def test_malformed_non_json_body_returns_ignored_not_500(client, allow_unauth, require_real_db):
    """A body that isn't even JSON must also be a soft 'ignored' 200, never
    a 500 — jarvis-alpha retries any non-2xx, so a permanently-malformed
    delivery must not retry forever."""
    r = client.post(_EVENTS_URL, data='not json at all', content_type='text/plain')
    assert r.status_code == 200
    assert r.get_json() == {'result': 'ignored'}


# ── Mapping: auth + tenant scoping ────────────────────────────────────────

def test_mapping_without_company_id_returns_400(client, allow_unauth, require_real_db):
    r = client.get(_MAPPING_URL)
    assert r.status_code == 400
    assert 'company_id' in r.get_json()['error']


def test_mapping_scopes_to_requested_company(client, allow_unauth, require_real_db):
    """Seed an active rule under each of two companies and assert GET
    /mapping?company_id=<X> returns ONLY company X's rules — no cross-tenant
    leak."""
    def _seed(trigger_code, company_id):
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute(
                "INSERT INTO logistics_mapping_rules (trigger_code, mode, is_active, company_id) "
                "VALUES (%s, 'Activ', TRUE, %s)",
                (trigger_code, company_id),
            )
            conn.commit()
        finally:
            release_db(conn)

    def _cleanup():
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute(
                'DELETE FROM logistics_mapping_rules WHERE company_id IN (%s, %s)',
                (TEST_COMPANY_ID, _OTHER_COMPANY_ID),
            )
            conn.commit()
        finally:
            release_db(conn)

    _cleanup()  # defensive
    try:
        _seed('MINE-RULE', TEST_COMPANY_ID)
        _seed('OTHER-RULE', _OTHER_COMPANY_ID)

        r = client.get(_MAPPING_URL, query_string={'company_id': TEST_COMPANY_ID})
        assert r.status_code == 200
        rules = r.get_json()['rules']
        company_ids = {rule['company_id'] for rule in rules}
        assert company_ids == {TEST_COMPANY_ID}, (
            f'/mapping leaked rules for other companies: {company_ids}'
        )
        trigger_codes = {rule['trigger_code'] for rule in rules}
        assert 'MINE-RULE' in trigger_codes
        assert 'OTHER-RULE' not in trigger_codes
    finally:
        _cleanup()


def test_mapping_requires_auth(client, monkeypatch):
    """The read endpoint is behind the same fail-closed gate as the write
    endpoint — no secret + no bypass -> 503, before any DB read."""
    monkeypatch.delenv('LOGISTICS_INTAKE_SECRET', raising=False)
    monkeypatch.delenv('LOGISTICS_INTAKE_ALLOW_UNAUTH', raising=False)
    r = client.get(_MAPPING_URL, query_string={'company_id': TEST_COMPANY_ID})
    assert r.status_code == 503
