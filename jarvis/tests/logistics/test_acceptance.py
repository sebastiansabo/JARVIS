"""End-to-end acceptance test for the JARVIS Parc logistics spine (Task 11).

One ordered scenario proving the user's exact story works across the whole
pipeline — intake (HTTP) -> register (LogisticsVehicleRepository.list_vehicles)
-> move (move_task) -- using the real Flask app (`app.py`) for the POSTs, so
the actual blueprint/auth wiring is exercised, not just the service layer
directly (mirrors test_intake_api.py).

Scenario (design spec's end-to-end acceptance test):
  1. POST `Transport in derulare` for one order, TWICE -> exactly one
     `logistics_vehicles` row and exactly one Recepție card (2nd POST is a
     `duplicate`, per Task 2's idempotency contract).
  2. POST `ETA actualizat` with a new ETA -> the SAME Recepție card's
     `due_at` changes, still exactly one task for the order (Task 3).
  3. `move_task(..., 'Finalizat', {'reception': {...}})` ("Confirmă
     recepția") -> the task is Finalizat AND the confirmed bay
     (`location_id`/`position_id`) shows up on the vehicle via
     `list_vehicles` — the Parc register read (Task 6/9).
  4. POST an OLDER `Transport in derulare` (lower `event_ts`, a DIFFERENT
     `position_id` in its payload) -> `ignored`, and the confirmed bay is
     UNCHANGED (Task 4's stale-event ordering guard protects a
     human-confirmed field from a late/out-of-order feed delivery).
  5. Throughout all of the above, `predare` never moves off its schema
     default (`'În așteptare'`) — handover is a separate, manual action
     this flow never triggers (not exercised by any rule handler or move
     gate in the current spine).

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002`. `logistics_cleanup` cascade-deletes
logistics_vehicles (-> tasks/history); the one logistics_locations/
logistics_positions row this file needs (the confirmed bay's FK target) is
created/deleted by the local `bay` fixture, same pattern as
test_move_reception.py / test_intake_stale.py.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/logistics/test_acceptance.py -v
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import uuid  # noqa: E402

import pytest  # noqa: E402

from app import app as flask_app  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from logistics.repositories.location_repository import LocationRepository, PositionRepository  # noqa: E402
from logistics.repositories.task_repository import TaskRepository  # noqa: E402
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository  # noqa: E402
from logistics.services.moves import move_task  # noqa: E402

from .conftest import TEST_COMPANY_ID  # noqa: E402

_EVENTS_URL = '/api/logistics/intake/events'
_RECEPTIE = 'Recepție'
_DEFAULT_PREDARE = 'În așteptare'


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


@pytest.fixture
def allow_unauth(monkeypatch):
    """Same dev/test bypass as test_intake_api.py — no shared secret
    configured, LOGISTICS_INTAKE_ALLOW_UNAUTH=1 so the POSTs are accepted
    without threading a secret header through the whole scenario."""
    monkeypatch.delenv('LOGISTICS_INTAKE_SECRET', raising=False)
    monkeypatch.setenv('LOGISTICS_INTAKE_ALLOW_UNAUTH', '1')


@pytest.fixture
def bay(require_real_db):
    """One real logistics_locations + logistics_positions row under
    TEST_COMPANY_ID — the valid-bay FK target the reception step confirms
    onto the vehicle. Deleted after the test: `logistics_cleanup` only
    cascades from logistics_vehicles, which never reaches
    logistics_locations/logistics_positions.

    Listed BEFORE `logistics_cleanup` in test signatures so its teardown
    runs AFTER logistics_cleanup's (LIFO) — the vehicle (FK'd to the
    position) is deleted first, then the position/location themselves.
    """
    location_repo = LocationRepository()
    position_repo = PositionRepository()

    suffix = uuid.uuid4().hex[:8]
    location = location_repo.create_location({
        'name': 'Test Yard (acceptance)',
        'code': f'TST-ACCEPT-{suffix}',
        'company_id': TEST_COMPANY_ID,
    })
    position = position_repo.create_position({
        'location_id': location['id'],
        'code': f'A-ACCEPT-{suffix}',
        'company_id': TEST_COMPANY_ID,
    })
    try:
        yield position
    finally:
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('DELETE FROM logistics_positions WHERE id = %s', (position['id'],))
            cur.execute('DELETE FROM logistics_locations WHERE id = %s', (location['id'],))
            conn.commit()
        finally:
            release_db(conn)


def _count_vehicles(order_ref: str) -> int:
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT COUNT(*) AS cnt FROM logistics_vehicles WHERE order_ref = %s', (order_ref,))
        return cur.fetchone()['cnt']
    finally:
        release_db(conn)


def _register_row(order_ref: str) -> dict:
    """The Parc register's own read path (Task 6) — `list_vehicles` scoped
    to TEST_COMPANY_ID, searched by the (unique) order_ref."""
    rows = LogisticsVehicleRepository().list_vehicles({'company_id': TEST_COMPANY_ID, 'q': order_ref})
    assert len(rows) == 1, f'expected exactly one register row for {order_ref!r}, got {len(rows)}'
    return rows[0]


def test_intake_register_move_acceptance(client, allow_unauth, require_real_db, bay, logistics_cleanup):
    order_ref = 'AW-ACCEPT-1'
    task_repo = TaskRepository()

    # ── Step 1: "Transport in derulare" posted twice -> one vehicle, one card ──
    transport_event = {
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 1000,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Intern',
            'eta': '2026-12-01T10:00:00',
        },
    }

    first = client.post(_EVENTS_URL, json=transport_event)
    assert first.status_code == 200
    first_body = first.get_json()
    assert first_body['result'] == 'created'
    vehicle_id = first_body['vehicle_id']
    assert vehicle_id is not None

    second = client.post(_EVENTS_URL, json=transport_event)
    assert second.status_code == 200
    assert second.get_json()['result'] == 'duplicate'

    assert _count_vehicles(order_ref) == 1
    reception_tasks = task_repo.list_tasks({'vehicle_id': vehicle_id, 'type': _RECEPTIE})
    assert len(reception_tasks) == 1
    reception_task_id = reception_tasks[0]['id']
    assert reception_tasks[0]['due_at'] == '2026-12-01T10:00:00'

    assert _register_row(order_ref)['predare'] == _DEFAULT_PREDARE

    # ── Step 2: "ETA actualizat" updates the SAME card, never a second one ──
    eta_event = {
        'order_ref': order_ref,
        'code': 'ETA actualizat',
        'event_ts': 1100,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'eta': '2026-12-05T09:00:00',
        },
    }

    eta_resp = client.post(_EVENTS_URL, json=eta_event)
    assert eta_resp.status_code == 200
    eta_body = eta_resp.get_json()
    assert eta_body['result'] == 'updated'
    assert eta_body['vehicle_id'] == vehicle_id
    assert eta_body['task_id'] == reception_task_id  # same card, not a new one

    reception_tasks_after_eta = task_repo.list_tasks({'vehicle_id': vehicle_id, 'type': _RECEPTIE})
    assert len(reception_tasks_after_eta) == 1
    assert reception_tasks_after_eta[0]['id'] == reception_task_id
    assert reception_tasks_after_eta[0]['due_at'] == '2026-12-05T09:00:00'

    assert _register_row(order_ref)['predare'] == _DEFAULT_PREDARE

    # ── Step 3: confirm reception -> Finalizat + confirmed bay on the vehicle ──
    reception_ctx = {
        'reception': {
            'vin': 'WVWZZZ1KZAW000777',
            'location_id': bay['location_id'],
            'position_id': bay['id'],
            'keys': 2,
            'condition': 'Bună',
        },
    }
    moved = move_task(reception_task_id, 'Finalizat', reception_ctx)
    assert moved['status'] == 'Finalizat'

    persisted_task = task_repo.get_task_by_id(reception_task_id)
    assert persisted_task['status'] == 'Finalizat'

    register_row = _register_row(order_ref)
    assert register_row['position_id'] == bay['id']
    assert register_row['location_id'] == bay['location_id']
    assert register_row['predare'] == _DEFAULT_PREDARE  # reception never touches it

    # ── Step 4: an OLDER intake event (different bay) is ignored, bay preserved ──
    stale_event = {
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 500,  # older than last_event_ts (1100, stamped by the ETA update)
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Extern',
            # A different bay -- must never be applied; the ordering guard
            # has to stop this event before any handler runs.
            'position_id': bay['id'] + 999999,
        },
    }
    stale_resp = client.post(_EVENTS_URL, json=stale_event)
    assert stale_resp.status_code == 200
    assert stale_resp.get_json()['result'] == 'ignored'

    final_row = _register_row(order_ref)
    assert final_row['position_id'] == bay['id']  # bay preserved
    assert final_row['location_id'] == bay['location_id']

    # ── Step 5: `predare` was never touched by the feed, start to finish ──
    # Handover ("Predare") is a separate manual action -- neither intake nor
    # reception ever sets it; it stays at the schema default throughout.
    assert final_row['predare'] == _DEFAULT_PREDARE
