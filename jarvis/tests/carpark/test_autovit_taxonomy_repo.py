"""Tests for AutovitTaxonomyRepository (Task 3 of the Autovit Taxonomy
Mapping project). Mostly DB-free: `query_all`/`execute`/`execute_many` are
monkeypatched, mirroring test_shopify_taxonomy_repo.py's idiom — no real
Postgres connection is made.

One test (`test_upsert_stores_folded_source_value`, the fold-fix correctness
ruling) IS DB-gated — it exercises the real `upsert()` SQL round-trip
against localhost/defaultdb, mirroring the REAL_DB_AVAILABLE idiom in
test_autovit_taxonomy_schema.py/test_autovit_push.py; it skips when no real
Postgres connection is available.
"""
import pytest

from carpark.connectors.autovit.taxonomy_repository import AutovitTaxonomyRepository

from .conftest import REAL_DB_AVAILABLE


def test_get_map_groups_by_dimension_and_make():
    rows = [
        {'dimension': 'fuel_type', 'source_value': 'Motorină', 'make': None,
         'target_code': 'diesel', 'target_label': 'Diesel'},
        {'dimension': 'model', 'source_value': 'A6', 'make': 'audi',
         'target_code': 'a6', 'target_label': 'A6'},
        {'dimension': 'model', 'source_value': 'A6', 'make': 'volkswagen',
         'target_code': 'a6-other', 'target_label': 'A6 (other make)'},
    ]
    repo = AutovitTaxonomyRepository()
    repo.query_all = lambda *a, **k: rows
    m = repo.get_map()
    assert m['fuel_type'][('Motorină', None)]['target_code'] == 'diesel'
    assert m['model'][('A6', 'audi')]['target_code'] == 'a6'
    assert m['model'][('A6', 'volkswagen')]['target_code'] == 'a6-other'


def test_repo_resolve_delegates_to_pure_module_resolver():
    # The row's source_value is pre-folded ('negru', not 'Negru') — that's
    # the real invariant once upsert() folds before writing (every row
    # get_map() ever returns was written through upsert()/the seed, both of
    # which fold). resolve() then folds the raw-cased 'Negru' LOOKUP to
    # match it.
    rows = [{'dimension': 'color', 'source_value': 'negru', 'make': None,
             'target_code': 'black', 'target_label': 'Black'}]
    repo = AutovitTaxonomyRepository()
    repo.query_all = lambda *a, **k: rows
    assert repo.resolve('color', 'Negru')['target_code'] == 'black'
    assert repo.resolve('color', 'UNKNOWN') is None


def test_upsert_null_make_updates_in_place_not_duplicate():
    # make IS NULL rows can't dedupe via a plain SQL UNIQUE/ON CONFLICT (NULL
    # <> NULL) — upsert must UPDATE first and only INSERT when no row matched.
    calls = []

    class FakeCursor:
        def __init__(self):
            self.rowcount = 1  # simulate an existing row -> UPDATE hits it

        def execute(self, sql, params):
            calls.append((sql.strip().split()[0], params))

    repo = AutovitTaxonomyRepository()
    repo.execute_many = lambda cb: cb(FakeCursor())
    repo.upsert('fuel_type', 'Motorină', None, 'diesel', 'Diesel', updated_by=1)
    # Only the UPDATE ran (rowcount=1 on the fake cursor) — no INSERT follows.
    assert calls[0][0] == 'UPDATE'
    assert len(calls) == 1


def test_upsert_null_make_inserts_when_no_existing_row():
    calls = []

    class FakeCursor:
        def __init__(self):
            self.rowcount = 0  # simulate no existing row -> UPDATE misses

        def execute(self, sql, params):
            calls.append((sql.strip().split()[0], params))

    repo = AutovitTaxonomyRepository()
    repo.execute_many = lambda cb: cb(FakeCursor())
    repo.upsert('fuel_type', 'Motorină', None, 'diesel', 'Diesel', updated_by=1)
    assert [c[0] for c in calls] == ['UPDATE', 'INSERT']


def test_upsert_with_make_uses_on_conflict():
    calls = []

    class FakeCursor:
        def execute(self, sql, params):
            calls.append((sql.strip().split()[0], params))

    repo = AutovitTaxonomyRepository()
    repo.execute_many = lambda cb: cb(FakeCursor())
    repo.upsert('model', 'A6', 'audi', 'a6', 'A6', updated_by=1)
    # source_value is folded ('A6' -> 'a6') before the write; `make` ('audi')
    # was already folded, target_code/target_label are never folded.
    assert calls == [('INSERT', ('model', 'a6', 'audi', 'a6', 'A6', 1))]


def test_get_cache_filters_by_dimension():
    repo = AutovitTaxonomyRepository()
    seen = {}

    def _fake_query_all(sql, params=None):
        seen['sql'] = sql
        seen['params'] = params
        return [{'dimension': 'equipment', 'code': 'apple_carplay'}]

    repo.query_all = _fake_query_all
    out = repo.get_cache('equipment')
    assert out == [{'dimension': 'equipment', 'code': 'apple_carplay'}]
    assert seen['params'] == ('equipment',)


def test_replace_cache_deletes_then_inserts_each_row():
    calls = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append(sql.strip().split()[0])

    repo = AutovitTaxonomyRepository()
    repo.execute_many = lambda cb: cb(FakeCursor())
    repo.replace_cache([
        {'dimension': 'equipment', 'code': 'apple_carplay', 'ro_label': 'CarPlay',
         'param_type': 'checkbox', 'make': None, 'options': None},
        {'dimension': 'model', 'code': 'a6', 'ro_label': 'A6',
         'param_type': None, 'make': 'audi', 'options': {'a': 1}},
    ])
    assert calls == ['DELETE', 'INSERT', 'INSERT']


def test_upsert_stores_folded_source_value():
    """Controller-ruling correctness fix: upsert() must fold `source_value`
    (and `make`) BEFORE writing, so `get_map()`'s output is keyed the exact
    same way `taxonomy_map.resolve()` folds a raw-cased/diacritic lookup —
    otherwise a real round trip through the DB reproduces the bug resolve()
    alone can't show (fold is correct but the write side still stores the
    raw key). Real-DB test: creates/upserts via the actual schema.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip('requires localhost/defaultdb')

    from database import get_db, release_db
    from psycopg2.extras import RealDictCursor
    from migrations.domains.schema_carpark import create_schema_carpark

    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        create_schema_carpark(conn, cur)
        conn.commit()
    finally:
        release_db(conn)

    repo = AutovitTaxonomyRepository()
    # fuel_type/benzina->petrol is one of Task 4's seeded rows, so this is
    # very likely an update-in-place of an existing row — capture its prior
    # value and restore it afterward so the test leaves shared local-DB
    # state untouched either way.
    before = repo.get_map().get('fuel_type', {}).get(('benzina', None))
    try:
        repo.upsert('fuel_type', 'Benzină', None, 'petrol', 'Petrol', updated_by=None)
        m = repo.get_map()
        assert ('benzina', None) in m['fuel_type']
        assert m['fuel_type'][('benzina', None)]['target_code'] == 'petrol'
    finally:
        if before is not None:
            repo.upsert('fuel_type', 'benzina', None,
                       before['target_code'], before['target_label'])
