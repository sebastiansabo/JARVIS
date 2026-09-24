"""Tests for the buyback RecordRepository (Task 4): create/get/list-scoped/
update/set_status against buyback_records.

DB-backed (uses `require_real_db` from tests/buyback/conftest.py) — obtains
its connection via the repository's own `database` layer, NOT raw
psycopg2.connect, since jarvis/conftest.py mocks psycopg2 at collection time
for the rest of the suite (see tests/buyback/test_schema_buyback.py for the
same pattern). Each test seeds its own uniquely-coded record(s)
(record_code/vin carry a random suffix) so reruns against the shared
localhost/defaultdb never collide with leftover rows from a previous run.
"""
import os

from buyback.repositories.record_repository import RecordRepository


def _code(prefix='BB-TEST'):
    return f'{prefix}-{os.urandom(4).hex()}'


def _vin():
    # Not checksum-valid (the schema doesn't enforce VIN format), just a
    # unique 17-char alnum string so concurrent/rerun tests never collide.
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _base(**overrides):
    data = {
        'record_code': _code(),
        'company_id': 1,
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'created_by': 1,
        'status': 'PENDING_EVALUATION',
    }
    data.update(overrides)
    return data


def test_create_and_get(require_real_db):
    repo = RecordRepository()
    rec = repo.create(_base())
    assert rec['id'] and rec['status'] == 'PENDING_EVALUATION'
    got = repo.get_by_id(rec['id'])
    assert got['record_code'] == rec['record_code']


def test_get_by_id_missing_returns_none(require_real_db):
    repo = RecordRepository()
    assert repo.get_by_id(999999999) is None


def test_list_scoped_by_company(require_real_db):
    repo = RecordRepository()
    company_a = 900001 + int.from_bytes(os.urandom(2), 'big')
    company_b = company_a + 1
    rec1 = repo.create(_base(company_id=company_a))
    rec2 = repo.create(_base(company_id=company_b))
    rows, total = repo.list(company_id=company_a, per_page=100)
    assert all(r['company_id'] == company_a for r in rows)
    assert any(r['record_code'] == rec1['record_code'] for r in rows)
    assert not any(r['record_code'] == rec2['record_code'] for r in rows)
    assert total >= 1


def test_list_sort_whitelist_ignores_bad_key(require_real_db):
    repo = RecordRepository()
    # malicious sort_by must fall back to created_at and never raise / inject
    rows, total = repo.list(sort_by='vin; DROP TABLE buyback_records', per_page=5)
    assert isinstance(rows, list)
    assert isinstance(total, int)


def test_list_filters_by_status_and_q(require_real_db):
    repo = RecordRepository()
    tag = os.urandom(3).hex()
    rec = repo.create(_base(brand=f'ZZZBRAND{tag}', status='INITIAL_OFFER'))
    rows, total = repo.list(status='INITIAL_OFFER', q=tag, per_page=50)
    assert any(r['record_code'] == rec['record_code'] for r in rows)
    assert all(r['status'] == 'INITIAL_OFFER' for r in rows)


def test_list_date_range_excludes_out_of_range(require_real_db):
    repo = RecordRepository()
    tag = os.urandom(3).hex()
    rec = repo.create(_base(brand=f'DATEBRAND{tag}'))
    rows, total = repo.list(q=tag, date_from='2099-01-01', date_to='2099-12-31', per_page=50)
    assert not any(r['record_code'] == rec['record_code'] for r in rows)
    assert total == 0


def test_list_pagination(require_real_db):
    repo = RecordRepository()
    tag = os.urandom(3).hex()
    for _ in range(3):
        repo.create(_base(brand=f'PGBRAND{tag}'))
    rows_p1, total = repo.list(q=tag, per_page=2, page=1)
    rows_p2, total2 = repo.list(q=tag, per_page=2, page=2)
    assert len(rows_p1) == 2
    assert len(rows_p2) == 1
    assert total == 3 and total2 == 3
    ids_p1 = {r['id'] for r in rows_p1}
    ids_p2 = {r['id'] for r in rows_p2}
    assert ids_p1.isdisjoint(ids_p2)


def test_list_includes_company_name_via_join(require_real_db):
    repo = RecordRepository()
    rec = repo.create(_base())
    rows, _ = repo.list(company_id=rec['company_id'], per_page=50)
    assert any('company_name' in r for r in rows)


def test_update_field(require_real_db):
    repo = RecordRepository()
    rec = repo.create(_base())
    updated = repo.update(rec['id'], {'mileage_km': 12345})
    assert updated['mileage_km'] == 12345
    assert updated['updated_at'] is not None


def test_update_ignores_unrecognized_key_no_raise(require_real_db):
    repo = RecordRepository()
    rec = repo.create(_base())
    # a bogus/unknown column name must never reach raw SQL as an identifier
    updated = repo.update(rec['id'], {'id; DROP TABLE buyback_records; --': 'x'})
    assert updated is not None
    assert updated['id'] == rec['id']


def test_set_status(require_real_db):
    repo = RecordRepository()
    rec = repo.create(_base())
    updated = repo.set_status(rec['id'], 'INITIAL_OFFER', actor=1)
    assert updated['status'] == 'INITIAL_OFFER'
