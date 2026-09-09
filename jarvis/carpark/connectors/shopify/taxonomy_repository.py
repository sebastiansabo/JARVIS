"""Data access for carpark_shopify_taxonomy_map."""
from typing import Any, Dict, List, Optional

from core.base_repository import BaseRepository


class TaxonomyMapRepository(BaseRepository):
    def get_map(self) -> Dict[str, Dict[str, dict]]:
        rows = self.query_all('SELECT * FROM carpark_shopify_taxonomy_map WHERE is_active = TRUE')
        out: Dict[str, Dict[str, dict]] = {}
        for r in rows:
            out.setdefault(r['dimension'], {})[r['source_value']] = {
                'target_gid': r.get('target_gid'),
                'target_label': r.get('target_label'),
                'shopify_attribute_gid': r.get('shopify_attribute_gid'),
            }
        return out

    def resolve(self, mapping: Dict[str, Dict[str, dict]],
                dimension: str, source_value: Optional[str]) -> Optional[dict]:
        if not source_value:
            return None
        return mapping.get(dimension, {}).get(source_value)

    def upsert(self, dimension: str, source_value: str,
               target_gid: Optional[str], target_label: Optional[str],
               shopify_attribute_gid: Optional[str], updated_by: Optional[int] = None) -> None:
        self.execute('''
            INSERT INTO carpark_shopify_taxonomy_map
                (dimension, source_value, target_gid, target_label, shopify_attribute_gid, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (dimension, source_value) DO UPDATE SET
                target_gid = EXCLUDED.target_gid,
                target_label = EXCLUDED.target_label,
                shopify_attribute_gid = EXCLUDED.shopify_attribute_gid,
                updated_by = EXCLUDED.updated_by,
                updated_at = CURRENT_TIMESTAMP
        ''', (dimension, source_value, target_gid, target_label, shopify_attribute_gid, updated_by))

    def distinct_source_values(self, dimension_to_column: Dict[str, str]) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        # Column names come from a trusted constant map, never user input.
        for dimension, column in dimension_to_column.items():
            rows = self.query_all(
                f"SELECT DISTINCT {column} AS v FROM carpark_vehicles "
                f"WHERE {column} IS NOT NULL AND {column} <> '' AND deleted_at IS NULL "
                f"ORDER BY v"
            )
            out[dimension] = [r['v'] for r in rows]
        return out
