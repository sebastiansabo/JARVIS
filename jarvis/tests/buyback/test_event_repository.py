"""Tests for the buyback EventRepository (Task 7): log/list_for_record
against buyback_events, the append-only audit log.

DB-backed (uses `require_real_db` from tests/buyback/conftest.py) — obtains
its connection via the repository's own `database` layer, NOT raw
psycopg2.connect, since jarvis/conftest.py mocks psycopg2 at collection time
for the rest of the suite (see tests/buyback/test_record_repository.py for
the same pattern). Each test creates its own parent buyback_records row via
RecordRepository().create() with a unique record_code + VIN, then exercises
the event repo against it, so reruns against the shared localhost/defaultdb
never collide with leftover rows from a previous run.
"""
import os

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.event_repository import EventRepository


def _code(prefix='BB-EVENT'):
    return f'{prefix}-{os.urandom(4).hex()}'


def _vin():
    # Not checksum-valid (the schema doesn't enforce VIN format), just a
    # unique 17-char alnum string so concurrent/rerun tests never collide.
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _record(**overrides):
    data = {
        'record_code': _code(),
        'company_id': 1,
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'created_by': 1,
    }
    data.update(overrides)
    return RecordRepository().create(data)


def test_log_and_list_for_record(require_real_db):
    rid = _record()['id']
    repo = EventRepository()

    logged = repo.log(
        rid, 'status_changed', 1,
        {'from': 'PENDING_EVALUATION', 'to': 'INITIAL_OFFER'},
    )

    assert logged['id']
    assert logged['record_id'] == rid
    assert logged['action'] == 'status_changed'
    assert logged['actor'] == 1
    assert logged['details']['to'] == 'INITIAL_OFFER'
    assert logged['created_at'] is not None

    rows = repo.list_for_record(rid)
    assert rows and rows[0]['action'] == 'status_changed'
    assert rows[0]['details']['to'] == 'INITIAL_OFFER'


def test_log_without_details(require_real_db):
    rid = _record()['id']
    repo = EventRepository()

    logged = repo.log(rid, 'record_created', 1)

    assert logged['details'] is None

    rows = repo.list_for_record(rid)
    assert rows[0]['details'] is None


def test_list_for_record_orders_newest_first(require_real_db):
    rid = _record()['id']
    repo = EventRepository()

    first = repo.log(rid, 'note_added', 1, {'seq': 1})
    second = repo.log(rid, 'note_added', 1, {'seq': 2})

    rows = repo.list_for_record(rid)
    assert [r['id'] for r in rows[:2]] == [second['id'], first['id']]


def test_list_for_record_empty_when_no_events(require_real_db):
    rid = _record()['id']
    repo = EventRepository()
    assert repo.list_for_record(rid) == []


def test_list_for_record_scoped_to_record(require_real_db):
    rid_a = _record()['id']
    rid_b = _record()['id']
    repo = EventRepository()

    repo.log(rid_a, 'status_changed', 1, {'to': 'A'})
    repo.log(rid_b, 'status_changed', 1, {'to': 'B'})

    rows_a = repo.list_for_record(rid_a)
    assert len(rows_a) == 1
    assert rows_a[0]['details']['to'] == 'A'
