"""Real-DB integration test for the intake service's stale-event guard —
Task 4 of the spine plan.

Two scenarios:
  1. An older event (event_ts < vehicle.last_event_ts) arriving for an
     order that already has a vehicle row must be ignored *before* it ever
     reaches a rule handler — so a late/out-of-order jarvis-alpha delivery
     can never clobber a human-confirmed field (e.g. the bay a car was
     actually received into; design spec §2 acceptance test 3).
  2. A genuinely newer event must still be applied *and* advance
     last_event_ts — proving the guard only blocks strictly older
     deliveries, it doesn't freeze the vehicle once last_event_ts is set
     (this also closes the "last_event_ts not stamped on ETA update"
     minor deferred from Task 3).

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002`. `logistics_cleanup` cascade-deletes
logistics_vehicles (-> tasks/history); the one logistics_locations/
logistics_positions row this file needs (to satisfy position_id's FK) is
created/deleted by the local `bay` fixture below.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/logistics/test_intake_stale.py -v
"""
import uuid

import pytest

from database import get_cursor, get_db, release_db
from logistics.repositories.location_repository import LocationRepository, PositionRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository
from logistics.services.intake import apply_event

from .conftest import TEST_COMPANY_ID


@pytest.fixture
def bay(require_real_db):
    """One real logistics_positions row — the FK target for
    logistics_vehicles.position_id. Deleted after the test:
    `logistics_cleanup` only cascades from logistics_vehicles, which never
    reaches logistics_locations/logistics_positions.

    `code` is globally UNIQUE on both tables, and the sentinel company_id
    is shared across worktrees against the same localhost DB (per repo
    convention), so a fixed literal could collide with a concurrent run —
    suffix with a fresh uuid to make this fixture self-isolating.
    """
    location_repo = LocationRepository()
    position_repo = PositionRepository()

    suffix = uuid.uuid4().hex[:8]
    location = location_repo.create_location({
        'name': 'Test Yard (stale-guard)',
        'code': f'TST-STALE-{suffix}',
        'company_id': TEST_COMPANY_ID,
    })
    position = position_repo.create_position({
        'location_id': location['id'],
        'code': f'A-STALE-{suffix}',
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


def test_older_event_does_not_overwrite_confirmed_bay(require_real_db, bay, logistics_cleanup):
    # `bay` set up before `logistics_cleanup` so teardown runs in the
    # opposite (LIFO) order: the vehicle (FK'd to the position) is deleted
    # by `logistics_cleanup` before `bay` deletes the position itself.
    vehicle_repo = LogisticsVehicleRepository()

    order_ref = 'AW-STALE-01'
    vehicle = vehicle_repo.create_vehicle({
        'order_ref': order_ref,
        'destinatie': 'Intern',
        'position_id': bay['id'],
        'confirmed_fields': {'position_id': True},
        'last_event_ts': 200,
        'company_id': TEST_COMPANY_ID,
    })

    stale_event = {
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 100,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Extern',
            # A different bay — never persisted, since the stale guard
            # must stop this event before any handler touches the row.
            'position_id': bay['id'] + 999999,
        },
    }
    result = apply_event(stale_event)

    assert result['result'] == 'ignored'
    assert result['vehicle_id'] == vehicle['id']

    fetched = vehicle_repo.get_vehicle_by_id(vehicle['id'])
    assert fetched['position_id'] == bay['id']
    assert fetched['destinatie'] == 'Intern'
    assert fetched['last_event_ts'] == 200


def test_newer_event_still_advances_last_event_ts(require_real_db, logistics_cleanup):
    vehicle_repo = LogisticsVehicleRepository()

    order_ref = 'AW-STALE-02'
    created = apply_event({
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 1000,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Intern',
            'eta': '2026-12-01T10:00:00',
        },
    })
    assert created['result'] == 'created'

    vehicle = vehicle_repo.get_vehicle_by_id(created['vehicle_id'])
    assert vehicle['last_event_ts'] == 1000

    updated = apply_event({
        'order_ref': order_ref,
        'code': 'ETA actualizat',
        'event_ts': 2000,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'eta': '2026-12-05T09:00:00',
        },
    })
    assert updated['result'] == 'updated'

    vehicle = vehicle_repo.get_vehicle_by_id(created['vehicle_id'])
    assert vehicle['last_event_ts'] == 2000
