"""Schema tests for the Autovit taxonomy cache + map tables (Task 1 of the
Autovit Taxonomy Mapping project).

`carpark_autovit_taxonomy_cache` / `carpark_autovit_taxonomy_map` mirror the
existing `carpark_shopify_taxonomy_map` pattern, but target Autovit's own
category-29 code taxonomy instead of Shopify's metafield GIDs. `make` is a
deliberate departure from the Shopify shape: Autovit models are make-scoped
(same model label can mean different things under different makes), so both
tables carry a nullable `make` column and the UNIQUE constraint includes it.

See docs/superpowers/plans/2026-10-19-autovit-taxonomy-mapping.md (Task 1)
and docs/superpowers/specs/2026-10-19-autovit-taxonomy-mapping-design.md.

Two tiers:
  - test_autovit_taxonomy_tables_declared_in_source(): DB-free, always runs
    (no skip). Reads schema_carpark.py source and asserts both
    `CREATE TABLE IF NOT EXISTS` statements, their UNIQUE constraints, and
    their dimension indexes are present. Mirrors the existing DB-free
    pattern in test_shopify_schema.py / test_shopify_schema_tables.py. This
    is the test that actually proves the DDL exists when no real DB is
    available to run the test below.
  - test_autovit_taxonomy_tables_exist(): DB-gated on REAL_DB_AVAILABLE
    (mirrors test_carpark_schema_widths.py). Runs the real carpark schema
    init against localhost/defaultdb, then verifies both tables' columns,
    nullability, and UNIQUE constraints via information_schema/pg_indexes.
    Skips (not fails) when no real Postgres connection is available.
"""
import re
from pathlib import Path

import pytest

from .conftest import REAL_DB_AVAILABLE

_SCHEMA_FILE = Path(__file__).resolve().parents[2] / 'migrations' / 'domains' / 'schema_carpark.py'

_CACHE_TABLE = 'carpark_autovit_taxonomy_cache'
_MAP_TABLE = 'carpark_autovit_taxonomy_map'

# column -> (expected data_type, expected character_maximum_length or None, is_nullable 'YES'/'NO')
_CACHE_COLUMNS = {
    'dimension': ('character varying', 40, 'NO'),
    'code': ('text', None, 'NO'),
    'ro_label': ('text', None, 'YES'),
    'param_type': ('character varying', 20, 'YES'),
    'make': ('character varying', 60, 'YES'),
    'options': ('jsonb', None, 'YES'),
    'synced_at': ('timestamp without time zone', None, 'YES'),
}
_MAP_COLUMNS = {
    'dimension': ('character varying', 40, 'NO'),
    'source_value': ('text', None, 'NO'),
    'make': ('character varying', 60, 'YES'),
    'target_code': ('text', None, 'YES'),
    'target_label': ('text', None, 'YES'),
    'is_active': ('boolean', None, 'YES'),
    'updated_at': ('timestamp without time zone', None, 'YES'),
    'updated_by': ('integer', None, 'YES'),
}


def test_autovit_taxonomy_tables_declared_in_source():
    """DB-free: proves the DDL is declared even when no real DB is available
    to run the gated test below against."""
    text = _SCHEMA_FILE.read_text()

    assert f'CREATE TABLE IF NOT EXISTS {_CACHE_TABLE}' in text
    assert f'CREATE TABLE IF NOT EXISTS {_MAP_TABLE}' in text

    assert re.search(r'UNIQUE\s*\(\s*dimension\s*,\s*code\s*,\s*make\s*\)', text), (
        f'{_CACHE_TABLE} missing UNIQUE(dimension, code, make)'
    )
    assert re.search(r'UNIQUE\s*\(\s*dimension\s*,\s*source_value\s*,\s*make\s*\)', text), (
        f'{_MAP_TABLE} missing UNIQUE(dimension, source_value, make)'
    )

    # Both new tables get an index on (dimension), mirroring idx_cstm_dimension.
    assert re.search(
        rf"CREATE INDEX IF NOT EXISTS \w+ ON {_CACHE_TABLE}\(dimension\)", text
    ), f'{_CACHE_TABLE} missing a dimension index'
    assert re.search(
        rf"CREATE INDEX IF NOT EXISTS \w+ ON {_MAP_TABLE}\(dimension\)", text
    ), f'{_MAP_TABLE} missing a dimension index'

    # Hard global constraint: adding these tables must never touch Shopify's.
    assert 'carpark_shopify_taxonomy_map' in text  # pre-existing, must stay untouched
    shopify_block = text[text.index('carpark_shopify_taxonomy_map') - 200:]
    # The new autovit tables must not appear inside a statement that also
    # references a carpark_shopify_* table name.
    for stmt in re.findall(r"cursor\.execute\(\s*'''(.*?)'''", text, re.S):
        if 'carpark_shopify' in stmt:
            assert 'carpark_autovit' not in stmt, (
                'a shopify DDL statement was edited to reference an autovit table'
            )


def test_autovit_taxonomy_tables_exist():
    if not REAL_DB_AVAILABLE:
        pytest.skip('requires localhost/defaultdb')

    from database import get_db, release_db
    from psycopg2.extras import RealDictCursor
    from migrations.domains.schema_carpark import create_schema_carpark

    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        create_schema_carpark(conn, cur)

        for table in (_CACHE_TABLE, _MAP_TABLE):
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                (table,),
            )
            assert cur.fetchone() is not None, f'{table} was not created by create_schema_carpark()'

        _assert_columns(cur, _CACHE_TABLE, _CACHE_COLUMNS)
        _assert_columns(cur, _MAP_TABLE, _MAP_COLUMNS)

        _assert_unique(cur, _CACHE_TABLE, {'dimension', 'code', 'make'})
        _assert_unique(cur, _MAP_TABLE, {'dimension', 'source_value', 'make'})

        _assert_index(cur, _CACHE_TABLE, 'dimension')
        _assert_index(cur, _MAP_TABLE, 'dimension')
    finally:
        release_db(conn)


def _assert_columns(cur, table, expected):
    cur.execute(
        """SELECT column_name, data_type, character_maximum_length, is_nullable
           FROM information_schema.columns WHERE table_name = %s""",
        (table,),
    )
    by_name = {row['column_name']: row for row in cur.fetchall()}
    assert 'id' in by_name, f'{table} missing id column'

    for col, (data_type, max_len, nullable) in expected.items():
        assert col in by_name, f'{table} missing column {col}'
        row = by_name[col]
        assert row['data_type'] == data_type, (
            f'{table}.{col} is {row["data_type"]}, expected {data_type}'
        )
        if max_len is not None:
            assert row['character_maximum_length'] == max_len, (
                f'{table}.{col} is VARCHAR({row["character_maximum_length"]}), expected VARCHAR({max_len})'
            )
        assert row['is_nullable'] == nullable, (
            f'{table}.{col} is_nullable={row["is_nullable"]}, expected {nullable}'
        )


def _assert_unique(cur, table, expected_cols):
    cur.execute(
        """
        SELECT tc.constraint_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_name = %s AND tc.constraint_type = 'UNIQUE'
        """,
        (table,),
    )
    by_constraint = {}
    for row in cur.fetchall():
        by_constraint.setdefault(row['constraint_name'], set()).add(row['column_name'])
    assert expected_cols in by_constraint.values(), (
        f'{table} missing UNIQUE{tuple(sorted(expected_cols))}; found {list(by_constraint.values())}'
    )


def _assert_index(cur, table, column):
    cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename = %s", (table,))
    defs = [row['indexdef'] for row in cur.fetchall()]
    assert any(f'({column})' in d for d in defs), (
        f'{table} missing an index on ({column}); found: {defs}'
    )
