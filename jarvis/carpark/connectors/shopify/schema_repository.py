"""Data access + reconcile engine for carpark_shopify_field_map / carpark_shopify_value_map.

reconcile() diffs the connector's stored field map against the store's live
metafield definitions (as returned by ShopifyClient.fetch_metafield_definitions(),
a {"namespace.key": type} dict) and reports what's new in the store, what's gone
stale (mapped but no longer defined in the store), and what changed type. As a
side effect it keeps last_seen_in_store in sync so the mapper can skip stale rows.
"""
from typing import Any, Dict, List, Optional

from core.base_repository import BaseRepository
from . import translations


class SchemaRepository(BaseRepository):
    # Set once a process has backfilled the defaults, so the ~150-row backfill
    # runs at most once per worker (not on every publish). Reset on redeploy.
    _defaults_ensured = False

    def ensure_defaults(self) -> None:
        """Backfill the built-in default field/value maps — adding any MISSING rows
        without overwriting existing ones (ON CONFLICT DO NOTHING).

        Replaces the old seed-only-when-empty behavior, which never backfilled:
        once a connector's maps had ANY rows, entries added to the defaults LATER
        (e.g. the all-wheel-*/mild-hybrid drive+fuel mappings, or new fuel/body/
        color choices) never reached that install, so the mapper fell back to the
        raw English slug (storefront showed `all-wheel-auto` instead of Integral).
        DO NOTHING preserves manual edits made via the schema admin. Idempotent;
        gated to run once per process."""
        if SchemaRepository._defaults_ensured:
            return
        for r in translations.DEFAULT_FIELD_MAP:
            self._insert_field_default(r['source_expr'], r['target_namespace'],
                                       r['target_key'], r.get('target_type'),
                                       r.get('transform', 'raw'))
        for dim, m in translations.VALUE_TRANSLATIONS_SEED.items():
            for src, rov in m.items():
                self._insert_value_default(dim, src, rov)
        SchemaRepository._defaults_ensured = True

    # Back-compat alias — callers (publish/preview/bulk/schema GET) keep calling
    # seed_defaults_if_empty; it now backfills missing defaults, not just seeds.
    def seed_defaults_if_empty(self) -> None:
        self.ensure_defaults()

    def _insert_field_default(self, source_expr, target_namespace, target_key,
                              target_type, transform) -> None:
        self.execute('''
            INSERT INTO carpark_shopify_field_map
                (source_expr, target_namespace, target_key, target_type, transform,
                 is_active, updated_at)
            VALUES (%s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (target_namespace, target_key) DO NOTHING
        ''', (source_expr if source_expr is not None else '', target_namespace,
              target_key, target_type, transform))

    def _insert_value_default(self, dimension, source_value, ro_value) -> None:
        self.execute('''
            INSERT INTO carpark_shopify_value_map
                (dimension, source_value, ro_value, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (dimension, source_value) DO NOTHING
        ''', (dimension, source_value, ro_value))

    def get_field_map(self) -> List[dict]:
        return self.query_all(
            'SELECT * FROM carpark_shopify_field_map ORDER BY target_namespace, target_key'
        )

    def get_active_field_map(self) -> List[dict]:
        return self.query_all(
            'SELECT * FROM carpark_shopify_field_map '
            'WHERE is_active = TRUE AND last_seen_in_store = TRUE '
            'ORDER BY target_namespace, target_key'
        )

    def upsert_field(self, source_expr: str, target_namespace: str, target_key: str,
                      target_type: Optional[str], transform: Optional[str],
                      is_active: bool = True, updated_by: Optional[int] = None) -> None:
        source_expr = source_expr if source_expr is not None else ''
        self.execute('''
            INSERT INTO carpark_shopify_field_map
                (source_expr, target_namespace, target_key, target_type, transform,
                 is_active, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (target_namespace, target_key) DO UPDATE SET
                source_expr = EXCLUDED.source_expr,
                target_type = EXCLUDED.target_type,
                transform = EXCLUDED.transform,
                is_active = EXCLUDED.is_active,
                updated_by = EXCLUDED.updated_by,
                updated_at = CURRENT_TIMESTAMP
        ''', (source_expr, target_namespace, target_key, target_type, transform, is_active, updated_by))

    def get_value_map(self) -> Dict[str, Dict[str, str]]:
        rows = self.query_all('SELECT * FROM carpark_shopify_value_map')
        out: Dict[str, Dict[str, str]] = {}
        for r in rows:
            out.setdefault(r['dimension'], {})[r['source_value']] = r.get('ro_value')
        return out

    def upsert_value(self, dimension: str, source_value: str, ro_value: Optional[str],
                      updated_by: Optional[int] = None) -> None:
        self.execute('''
            INSERT INTO carpark_shopify_value_map
                (dimension, source_value, ro_value, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (dimension, source_value) DO UPDATE SET
                ro_value = EXCLUDED.ro_value,
                updated_by = EXCLUDED.updated_by,
                updated_at = CURRENT_TIMESTAMP
        ''', (dimension, source_value, ro_value, updated_by))

    def reconcile(self, store_defs: Dict[str, str], persist: bool = True) -> dict:
        """Diff the stored field map against the store's live metafield defs.

        store_defs: {"namespace.key": shopify_type} as returned by
        ShopifyClient.fetch_metafield_definitions().

        Returns {'new': [...], 'stale': [...], 'type_changed': [...], 'ok': int}
        and, when persist=True (default), updates last_seen_in_store as a side
        effect on rows whose seen-state changed (present-in-store vs not) so the
        mapper can skip stale rows without re-running this diff. Callers that only
        want to read drift (e.g. a GET endpoint) should pass persist=False so the
        diff runs with no writes.
        """
        field_map = self.get_field_map()
        map_by_target = {f"{r['target_namespace']}.{r['target_key']}": r for r in field_map}

        new: List[dict] = []
        for target, store_type in store_defs.items():
            if target not in map_by_target:
                namespace, _, key = target.partition('.')
                new.append({'namespace': namespace, 'key': key, 'type': store_type})

        stale: List[dict] = []
        type_changed: List[dict] = []
        ok = 0

        for target, row in map_by_target.items():
            was_seen = bool(row.get('last_seen_in_store'))
            in_store = target in store_defs

            if not in_store:
                stale.append({'target_namespace': row['target_namespace'], 'target_key': row['target_key']})
            else:
                store_type = store_defs[target]
                if row.get('target_type') != store_type:
                    type_changed.append({
                        'target_namespace': row['target_namespace'],
                        'target_key': row['target_key'],
                        'map_type': row.get('target_type'),
                        'store_type': store_type,
                    })
                else:
                    ok += 1

            if in_store != was_seen and persist:
                self.execute(
                    'UPDATE carpark_shopify_field_map SET last_seen_in_store = %s '
                    'WHERE target_namespace = %s AND target_key = %s',
                    (in_store, row['target_namespace'], row['target_key'])
                )

        return {'new': new, 'stale': stale, 'type_changed': type_changed, 'ok': ok}
