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
from database import get_db, get_cursor, release_db


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
    # Query the distinctive non-hex brand marker, NOT the bare hex tag: `q` is an
    # ILIKE over vin/record_code too, and a short hex tag can collide with hex
    # substrings in the shared DB's other records (flaky `total`). 'PGBRAND…'
    # appears only in these three records' brand.
    tag = os.urandom(3).hex()
    marker = f'PGBRAND{tag}'
    for _ in range(3):
        repo.create(_base(brand=marker))
    rows_p1, total = repo.list(q=marker, per_page=2, page=1)
    rows_p2, total2 = repo.list(q=marker, per_page=2, page=2)
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


def test_delete_removes_row_and_returns_rowcount(require_real_db):
    repo = RecordRepository()
    rec = repo.create(_base())
    assert repo.delete(rec['id']) == 1
    assert repo.get_by_id(rec['id']) is None


def test_delete_missing_id_returns_zero(require_real_db):
    repo = RecordRepository()
    assert repo.delete(999999999) == 0


# ── group_company_ids: the Autoworld corporate family for cross-company VIN history ──

def _mk_company(cur, cid, parent=None):
    cur.execute(
        'INSERT INTO companies (id, company, parent_company_id) VALUES (%s, %s, %s) '
        'ON CONFLICT (id) DO NOTHING',
        (cid, f'BB Test Co {cid}', parent),
    )


def test_group_company_ids_returns_parent_family(require_real_db):
    """A VIN seen at any sibling under the same parent must be discoverable:
    group_company_ids(child) = {parent} ∪ all children of that parent, and an
    unrelated company (different/no parent) is excluded."""
    repo = RecordRepository()
    base = 950000 + int.from_bytes(os.urandom(2), 'big')
    parent, child1, child2, unrelated = base, base + 1, base + 2, base + 3
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _mk_company(cur, parent, None)
        _mk_company(cur, child1, parent)
        _mk_company(cur, child2, parent)
        _mk_company(cur, unrelated, None)
        conn.commit()

        fam = set(repo.group_company_ids(child1))
        assert {parent, child1, child2} <= fam
        assert unrelated not in fam
        # querying by the parent itself yields the same family
        assert set(repo.group_company_ids(parent)) == fam
    finally:
        cur = get_cursor(conn)
        cur.execute('DELETE FROM companies WHERE id = ANY(%s)',
                    ([parent, child1, child2, unrelated],))
        conn.commit()
        release_db(conn)


def test_group_company_ids_unknown_company_falls_back_to_self(require_real_db):
    """A company_id with no companies row still scopes to itself (never widens
    to all companies)."""
    repo = RecordRepository()
    missing = 980000 + int.from_bytes(os.urandom(2), 'big')
    assert set(repo.group_company_ids(missing)) == {missing}


# ── market_price_eur (Preț Piață) persists through update + list ──

def test_update_sets_market_price(require_real_db):
    repo = RecordRepository()
    rec = repo.create(_base())
    updated = repo.update(rec['id'], {'market_price_eur': 21500})
    assert float(updated['market_price_eur']) == 21500.0


def test_list_includes_market_price(require_real_db):
    repo = RecordRepository()
    cid = 960000 + int.from_bytes(os.urandom(2), 'big')
    rec = repo.create(_base(company_id=cid, market_price_eur=18000))
    rows, _ = repo.list(company_id=cid, per_page=100)
    row = next(r for r in rows if r['record_code'] == rec['record_code'])
    assert float(row['market_price_eur']) == 18000.0


# ── vin_history: cross-company prior buyback evaluations for a VIN ──

def _add_offer(cur, record_id, amount, offer_type='initial', vat='no_vat'):
    cur.execute(
        'INSERT INTO buyback_offers (record_id, offer_type, amount_eur, vat_status) '
        'VALUES (%s, %s, %s, %s)',
        (record_id, offer_type, amount, vat),
    )


def test_vin_history_returns_prior_with_latest_offer(require_real_db):
    """A prior record for the same VIN surfaces with its MOST RECENT offer
    (the 'ultima ofertă' Norbert wants), the evaluating company, and advisor."""
    repo = RecordRepository()
    cid = 962000 + int.from_bytes(os.urandom(2), 'big')
    vin = _vin()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        prior = repo.create(_base(company_id=cid, vin=vin, advisor_name='Arthur'))
        _add_offer(cur, prior['id'], 9000, 'initial')
        _add_offer(cur, prior['id'], 8500, 'final')
        conn.commit()

        hist = repo.vin_history(vin, [cid])
        assert len(hist) == 1
        h = hist[0]
        assert h['id'] == prior['id']
        assert h['advisor_name'] == 'Arthur'
        assert float(h['last_offer_eur']) == 8500.0  # latest offer, not the initial
        assert h['last_offer_type'] == 'final'
        assert 'company_name' in h
    finally:
        cur = get_cursor(conn)
        cur.execute('DELETE FROM buyback_records WHERE id = %s', (prior['id'],))
        conn.commit()
        release_db(conn)


def test_vin_history_excludes_self_and_out_of_group(require_real_db):
    """Only prior records in the caller's company family count; the current
    record (exclude_record_id) and any same-VIN record in an unrelated company
    are not returned."""
    repo = RecordRepository()
    base = 961000 + int.from_bytes(os.urandom(2), 'big')
    parent, c1, c2, outside = base, base + 1, base + 2, base + 3
    vin = _vin()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _mk_company(cur, parent, None)
        _mk_company(cur, c1, parent)
        _mk_company(cur, c2, parent)
        _mk_company(cur, outside, None)
        conn.commit()

        prior = repo.create(_base(company_id=c1, vin=vin))        # sibling in group
        current = repo.create(_base(company_id=c2, vin=vin))      # "current" record
        foreign = repo.create(_base(company_id=outside, vin=vin))  # unrelated company

        group = repo.group_company_ids(c2)
        hist = repo.vin_history(vin, group, exclude_record_id=current['id'])
        ids = {h['id'] for h in hist}
        assert prior['id'] in ids
        assert current['id'] not in ids   # excluded self
        assert foreign['id'] not in ids   # out of group
    finally:
        cur = get_cursor(conn)
        cur.execute('DELETE FROM buyback_records WHERE company_id = ANY(%s)',
                    ([c1, c2, outside],))
        cur.execute('DELETE FROM companies WHERE id = ANY(%s)',
                    ([parent, c1, c2, outside],))
        conn.commit()
        release_db(conn)


def test_vin_history_blank_vin_returns_empty(require_real_db):
    repo = RecordRepository()
    assert repo.vin_history('', [1]) == []
    assert repo.vin_history(None, [1]) == []


# ── list(): is_repeat flag (the digital 'yellow highlight') ──

def test_list_flags_is_repeat_for_vin_seen_in_group(require_real_db):
    repo = RecordRepository()
    base = 963000 + int.from_bytes(os.urandom(2), 'big')
    parent, c1, c2 = base, base + 1, base + 2
    vin = _vin()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _mk_company(cur, parent, None)
        _mk_company(cur, c1, parent)
        _mk_company(cur, c2, parent)
        conn.commit()
        repo.create(_base(company_id=c1, vin=vin))          # prior eval at sibling c1
        current = repo.create(_base(company_id=c2, vin=vin))  # same VIN, now at c2
        fresh = repo.create(_base(company_id=c2, vin=_vin()))  # unique VIN → not a repeat

        group = repo.group_company_ids(c2)
        rows, _ = repo.list(company_id=c2, per_page=100, repeat_scope_ids=group)
        by_id = {r['id']: r for r in rows}
        assert by_id[current['id']]['is_repeat'] is True
        assert by_id[fresh['id']]['is_repeat'] is False
    finally:
        cur = get_cursor(conn)
        cur.execute('DELETE FROM buyback_records WHERE company_id = ANY(%s)', ([c1, c2],))
        cur.execute('DELETE FROM companies WHERE id = ANY(%s)', ([parent, c1, c2],))
        conn.commit()
        release_db(conn)
