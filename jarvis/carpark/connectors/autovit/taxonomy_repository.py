"""Data access for carpark_autovit_taxonomy_map / carpark_autovit_taxonomy_cache.

Mirrors `carpark/connectors/shopify/taxonomy_repository.py`'s shape
(`get_map`/`resolve`/`upsert`), extended for Autovit's two departures from
the Shopify table (see docs/superpowers/specs/2026-10-19-autovit-taxonomy-
mapping-design.md): a nullable `make` column (the `model` dimension is
make-scoped; every other dimension stores `make=NULL`) and a separate
synced-vocabulary cache table (`carpark_autovit_taxonomy_cache`) alongside
the editable map.

`get_map()` produces the `{dimension: {(source_value, make):
{target_code, target_label}}}` shape that `taxonomy_map.resolve()`/
`emit()` (Task 2) consume directly — the publish path (Task 6) loads it
ONCE and passes it into `vehicle_to_advert` (Task 3), rather than hitting
the DB per field.
"""
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extras import Json

from core.base_repository import BaseRepository
from . import taxonomy_map as _taxonomy_map


class AutovitTaxonomyRepository(BaseRepository):

    def get_map(self) -> Dict[str, Dict[Tuple[Any, Optional[str]], dict]]:
        """{dimension: {(source_value, make): {target_code, target_label}}}
        over every active map row. `make` is NULL for every dimension except
        `model` — stored verbatim as the dict key's second element, so a
        lookup must pass the same make representation used here (the
        *resolved Autovit make code*, per the model make-scoping ruling)."""
        rows = self.query_all('SELECT * FROM carpark_autovit_taxonomy_map WHERE is_active = TRUE')
        out: Dict[str, Dict[Tuple[Any, Optional[str]], dict]] = {}
        for r in rows:
            out.setdefault(r['dimension'], {})[(r['source_value'], r.get('make'))] = {
                'target_code': r.get('target_code'),
                'target_label': r.get('target_label'),
            }
        return out

    def resolve(self, dimension: str, source_value: Any,
                make: Optional[str] = None) -> Optional[dict]:
        """One-off lookup: loads the map fresh and delegates to the pure
        `taxonomy_map.resolve()`. The hot path (publish) should call
        `get_map()` once and resolve every dimension against that same dict
        instead of calling this per field."""
        return _taxonomy_map.resolve(self.get_map(), dimension, source_value, make)

    def upsert(self, dimension: str, source_value: str, make: Optional[str],
               target_code: Optional[str], target_label: Optional[str],
               updated_by: Optional[int] = None) -> None:
        """Insert or update a map row.

        `make` is NULL for every dimension except `model`. A plain SQL
        `UNIQUE(dimension, source_value, make)` constraint does NOT treat
        two NULLs as equal, so a naive `ON CONFLICT (dimension,
        source_value, make)` would silently INSERT a duplicate row instead
        of updating whenever `make IS NULL` (i.e. for 10 of the 11
        dimensions). Do an explicit UPDATE-then-insert-if-missing for the
        NULL case instead; the make-scoped (`model`) case can safely use
        `ON CONFLICT` since a real make value is never NULL-ambiguous.

        `source_value`/`make` are `_taxonomy_map.fold()`ed BEFORE writing —
        the stored key must be canonical-folded so `get_map()`'s output
        matches what `taxonomy_map.resolve()` folds a raw-cased/diacritic
        lookup to (the admin UI/API caller may submit "Benzină"; the row
        must land keyed on "benzina", same as the seed).
        """
        source_value = _taxonomy_map.fold(source_value)
        if make is not None:
            make = _taxonomy_map.fold(make)

        def _work(cursor):
            if make is None:
                cursor.execute('''
                    UPDATE carpark_autovit_taxonomy_map
                    SET target_code = %s, target_label = %s, updated_by = %s,
                        is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                    WHERE dimension = %s AND source_value = %s AND make IS NULL
                ''', (target_code, target_label, updated_by, dimension, source_value))
                if cursor.rowcount == 0:
                    cursor.execute('''
                        INSERT INTO carpark_autovit_taxonomy_map
                            (dimension, source_value, make, target_code, target_label, updated_by)
                        VALUES (%s, %s, NULL, %s, %s, %s)
                    ''', (dimension, source_value, target_code, target_label, updated_by))
            else:
                cursor.execute('''
                    INSERT INTO carpark_autovit_taxonomy_map
                        (dimension, source_value, make, target_code, target_label, updated_by, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (dimension, source_value, make) DO UPDATE SET
                        target_code = EXCLUDED.target_code,
                        target_label = EXCLUDED.target_label,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = CURRENT_TIMESTAMP
                ''', (dimension, source_value, make, target_code, target_label, updated_by))
        self.execute_many(_work)

    def get_cache(self, dimension: Optional[str] = None) -> List[dict]:
        if dimension:
            return self.query_all(
                'SELECT * FROM carpark_autovit_taxonomy_cache WHERE dimension = %s ORDER BY code',
                (dimension,))
        return self.query_all('SELECT * FROM carpark_autovit_taxonomy_cache ORDER BY dimension, code')

    def replace_cache(self, rows: List[dict]) -> None:
        """Full replace of the synced-vocabulary cache (not a merge) — a
        sync pulls Autovit's CURRENT live taxonomy, so stale codes must
        disappear, not linger. Each row: {dimension, code, ro_label,
        param_type, make, options}."""
        def _work(cursor):
            cursor.execute('DELETE FROM carpark_autovit_taxonomy_cache')
            for row in rows:
                options = row.get('options')
                cursor.execute('''
                    INSERT INTO carpark_autovit_taxonomy_cache
                        (dimension, code, ro_label, param_type, make, options, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ''', (row.get('dimension'), row.get('code'), row.get('ro_label'),
                      row.get('param_type'), row.get('make'),
                      Json(options) if options is not None else None))
        self.execute_many(_work)

    # ── Distinct in-use CarPark values (Task 7: Settings taxonomy admin UI) ──
    #
    # The admin page needs to know WHICH CarPark values are actually in use,
    # per dimension, so a human can map each one to its exact Autovit code.
    # Mirrors shopify/taxonomy_repository.py's `distinct_source_values()`
    # (same name, same "column names are a trusted constant, never user
    # input" shape), extended for Autovit's two dimensions that don't fit
    # a flat "one column, one value" query: `model` (make-scoped — pairs
    # carry their make) and `equipment` (two source columns: the Dotări
    # TEXT[] and the legacy JSONB flag dict — see taxonomy.vehicle_to_advert
    # for the authoritative read of both).

    def distinct_source_values(self, dimension_to_column: Dict[str, str]) -> Dict[str, List[str]]:
        """Distinct, non-blank, in-use CarPark values per SIMPLE (single
        source column, not make-scoped) dimension. `dimension_to_column`
        maps a dimension name to its `carpark_vehicles` column — a trusted
        constant the caller controls, never user input, so it is safe to
        interpolate into the SQL (no placeholder exists for identifiers)."""
        out: Dict[str, List[str]] = {}
        for dimension, column in dimension_to_column.items():
            rows = self.query_all(
                f"SELECT DISTINCT {column} AS v FROM carpark_vehicles "
                f"WHERE {column} IS NOT NULL AND {column} <> '' AND deleted_at IS NULL "
                f"ORDER BY v"
            )
            out[dimension] = [r['v'] for r in rows]
        return out

    def distinct_models(self) -> List[Dict[str, str]]:
        """Distinct (brand, model) pairs in use — each row carries its make
        so the admin UI can group by make and resolve `model` scoped by the
        RESOLVED Autovit make code, per Task 3's make-scoping rule."""
        rows = self.query_all('''
            SELECT DISTINCT brand, model FROM carpark_vehicles
            WHERE deleted_at IS NULL
              AND brand IS NOT NULL AND brand <> ''
              AND model IS NOT NULL AND model <> ''
            ORDER BY brand, model
        ''')
        return [{'make': r['brand'], 'value': r['model']} for r in rows]

    def distinct_equipment(self) -> List[str]:
        """Distinct equipment source values: UNNEST(equipment_options)
        (the editor's Dotări TEXT[]) union the TRUTHY keys of the legacy
        `equipment` JSONB flag dict (Autovit-imported vehicles) — the same
        two sources `taxonomy.vehicle_to_advert` folds into one 'equipment'
        resolve. `jsonb_each` on a NULL/empty object yields zero rows, so no
        extra guard is needed beyond the `deleted_at` scope."""
        rows = self.query_all('''
            SELECT DISTINCT val FROM (
                SELECT UNNEST(equipment_options) AS val FROM carpark_vehicles
                WHERE deleted_at IS NULL AND equipment_options IS NOT NULL
                UNION
                SELECT kv.key AS val FROM carpark_vehicles cv
                CROSS JOIN LATERAL jsonb_each(cv.equipment) AS kv(key, value)
                WHERE cv.deleted_at IS NULL AND kv.value::text = 'true'
            ) t
            WHERE val IS NOT NULL AND val <> ''
            ORDER BY val
        ''')
        return [r['val'] for r in rows]
