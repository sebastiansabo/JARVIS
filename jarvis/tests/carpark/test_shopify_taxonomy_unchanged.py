"""Shopify-isolation guard for the Autovit Taxonomy Mapping project (Task 8).

The whole project added a parallel Autovit taxonomy stack (cache + map
tables, repository, sync, routes, Settings UI) next to the pre-existing
Shopify connector's own `carpark_shopify_taxonomy_map` /
`carpark_shopify_field_map` / `carpark_shopify_value_map` tables and
`carpark/connectors/shopify/taxonomy_repository.py`. The two stacks must
never be edited together or reference each other's tables — the Shopify
publish path has to keep working byte-for-byte as it did before this
project started.

Two tests, both DB-free (always run, no skip):

  - test_no_autovit_migration_touches_shopify_tables(): reads
    schema_carpark.py source and proves, two independent ways, that the
    autovit-taxonomy additions and the pre-existing Shopify DDL never
    co-mingle:
      1. every individual `cursor.execute(...)` statement in the whole
         file that mentions a `carpark_autovit*` table does NOT also
         mention a `carpark_shopify*` table, and vice-versa (no single
         statement references both families) — robust to future
         reordering/reformatting of the file;
      2. the specific autovit-taxonomy block (the two CREATE TABLE
         statements for `carpark_autovit_taxonomy_cache` /
         `carpark_autovit_taxonomy_map` plus the one-time seed wiring
         that follows them) contains no `carpark_shopify` substring at
         all, and the specific pre-existing Shopify block contains no
         `carpark_autovit` substring at all.

  - test_shopify_taxonomy_repo_import_unchanged(): sanity that this
    project never touched `shopify/taxonomy_repository.py` — importing it
    still exposes the same `get_map`/`resolve`/`upsert` surface the
    Shopify publish path (and `carpark/connectors/shopify/connector.py`)
    depends on.

See docs/superpowers/plans/2026-10-19-autovit-taxonomy-mapping.md (Task 8)
and docs/superpowers/specs/2026-10-19-autovit-taxonomy-mapping-design.md.
"""
import re
from pathlib import Path

_SCHEMA_FILE = Path(__file__).resolve().parents[2] / 'migrations' / 'domains' / 'schema_carpark.py'

# Matches `cursor.execute(...)` regardless of quote style used for the SQL
# literal: triple-single, triple-double, single-line single, or
# single-line double. Returns the literal's inner text as whichever group
# matched (the others are None).
_EXECUTE_RE = re.compile(
    r"cursor\.execute\(\s*"
    r"(?:'''(?P<triple_single>.*?)'''"
    r"|\"\"\"(?P<triple_double>.*?)\"\"\""
    r"|'(?P<single>[^'\\]*(?:\\.[^'\\]*)*)'"
    r"|\"(?P<double>[^\"\\]*(?:\\.[^\"\\]*)*)\")",
    re.S,
)


def _execute_statements(text: str):
    """Yield the SQL/text literal of every `cursor.execute(...)` call in
    `text`, independent of whether it used triple or single quotes."""
    for m in _EXECUTE_RE.finditer(text):
        yield next(g for g in m.groups() if g is not None)


def test_no_autovit_migration_touches_shopify_tables():
    text = _SCHEMA_FILE.read_text()

    # Sanity: both families must actually still be present in the file —
    # otherwise the assertions below would trivially (and uselessly) pass.
    assert 'carpark_autovit_taxonomy_cache' in text
    assert 'carpark_autovit_taxonomy_map' in text
    assert 'carpark_shopify_taxonomy_map' in text

    # --- 1. Global, statement-level guard: no single cursor.execute(...)
    # call anywhere in the file mentions both an autovit-taxonomy table and
    # a Shopify table. This holds regardless of where in the file either
    # block lives, so it survives future reordering. ---
    statements = list(_execute_statements(text))
    assert statements, 'no cursor.execute(...) statements found — regex is broken, not the schema'

    comingled = [
        stmt for stmt in statements
        if 'carpark_autovit' in stmt and 'carpark_shopify' in stmt
    ]
    assert not comingled, (
        f'{len(comingled)} cursor.execute(...) statement(s) reference both '
        f'carpark_autovit* and carpark_shopify* tables: {comingled}'
    )

    # --- 2. Block-level guard: slice out the actual autovit-taxonomy
    # addition (both CREATE TABLE statements + the seed-wiring that follows
    # them) and the actual pre-existing Shopify block, and assert each is
    # entirely free of the other family's table-name prefix. ---
    autovit_start = text.index('carpark_autovit_taxonomy_cache')
    seed_call_idx = text.index('seed_map(cursor)', autovit_start)
    autovit_end = text.index('conn.commit()', seed_call_idx) + len('conn.commit()')
    autovit_block = text[autovit_start:autovit_end]

    assert 'carpark_shopify' not in autovit_block, (
        'the autovit-taxonomy CREATE TABLE / seed-wiring block references a '
        'carpark_shopify_* table'
    )

    shopify_start = text.index('carpark_shopify_taxonomy_map')
    # The Shopify DDL block ends exactly where the autovit-taxonomy block
    # begins (they are adjacent additions in the file today).
    shopify_block = text[shopify_start:autovit_start]

    assert 'carpark_autovit' not in shopify_block, (
        'the pre-existing Shopify taxonomy DDL block references a '
        'carpark_autovit* table'
    )


def test_shopify_taxonomy_repo_import_unchanged():
    """Sanity: carpark/connectors/shopify/taxonomy_repository.py was never
    edited by this project — it still exposes the same get_map/resolve/
    upsert surface the Shopify publish path depends on."""
    from carpark.connectors.shopify import taxonomy_repository

    assert hasattr(taxonomy_repository, 'TaxonomyMapRepository')
    repo_cls = taxonomy_repository.TaxonomyMapRepository

    for method in ('get_map', 'resolve', 'upsert'):
        assert hasattr(repo_cls, method), f'TaxonomyMapRepository lost its {method}() method'
        assert callable(getattr(repo_cls, method))
