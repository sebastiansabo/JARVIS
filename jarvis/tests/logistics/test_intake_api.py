"""Real-DB integration tests for the logistics intake HTTP surface —
POST /api/logistics/intake/events + GET /api/logistics/intake/mapping
(Task 5 of the spine plan).

Uses the real Flask app (`app.py`) so the actual blueprint registration is
exercised end-to-end (mirrors jarvis/tests/carpark/test_photo_upload.py).
Unlike the carpark route tests, these endpoints are the server-to-server
jarvis-alpha feed — no @login_required, no session login needed.

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


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _count_vehicles(order_ref: str) -> int:
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT COUNT(*) AS cnt FROM logistics_vehicles WHERE order_ref = %s', (order_ref,))
        return cur.fetchone()['cnt']
    finally:
        release_db(conn)


def test_post_twice_created_then_duplicate_one_vehicle(client, require_real_db, logistics_cleanup):
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


def test_malformed_body_returns_ignored_and_logs_event(client, require_real_db):
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


def test_malformed_non_json_body_returns_ignored_not_500(client, require_real_db):
    """A body that isn't even JSON must also be a soft 'ignored' 200, never
    a 500 — jarvis-alpha retries any non-2xx, so a permanently-malformed
    delivery must not retry forever."""
    r = client.post(_EVENTS_URL, data='not json at all', content_type='text/plain')
    assert r.status_code == 200
    assert r.get_json() == {'result': 'ignored'}


def test_mapping_endpoint_returns_rules_list(client, require_real_db):
    r = client.get(_MAPPING_URL)
    assert r.status_code == 200
    body = r.get_json()
    assert 'rules' in body
    assert isinstance(body['rules'], list)
