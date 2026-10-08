"""Data access for buyback_company_config (per-tenant notification config).

One row per company_id. upsert() builds its column list only from the fixed
_UPDATABLE whitelist — unknown keys are dropped, never interpolated as SQL
identifiers; all values are %s-bound.
"""
from core.base_repository import BaseRepository

_UPDATABLE = (
    'enabled', 'acquisition_emails', 'channel_email', 'channel_in_app',
    'channel_push', 'notify_new_request', 'notify_milestones', 'notify_inspection',
)


class ConfigRepository(BaseRepository):

    def get(self, company_id) -> dict | None:
        return self.query_one(
            'SELECT * FROM buyback_company_config WHERE company_id = %s', (company_id,)
        )

    def upsert(self, company_id, fields: dict, updated_by=None) -> dict:
        cols = {k: fields[k] for k in fields if k in _UPDATABLE}
        insert_cols = ['company_id', 'updated_by', *cols.keys()]
        insert_vals = [company_id, updated_by, *cols.values()]
        placeholders = ', '.join(['%s'] * len(insert_cols))
        set_parts = [f'{k} = EXCLUDED.{k}' for k in cols]
        set_parts.append('updated_by = EXCLUDED.updated_by')
        set_parts.append('updated_at = NOW()')
        sql = (
            f'INSERT INTO buyback_company_config ({", ".join(insert_cols)}) '
            f'VALUES ({placeholders}) '
            f'ON CONFLICT (company_id) DO UPDATE SET {", ".join(set_parts)} '
            f'RETURNING *'
        )
        return self.execute(sql, tuple(insert_vals), returning=True)
