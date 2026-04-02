"""Sync run tracking repository for Sincron connector."""

import uuid

from core.base_repository import BaseRepository


class SincronSyncRepository(BaseRepository):
    """Data access for sincron_sync_runs."""

    def create_run(self, sync_type='timesheet', company_name=None, year=None, month=None):
        """Create a new sync run. Returns dict with run_id."""
        run_id = str(uuid.uuid4())
        return self.execute('''
            INSERT INTO sincron_sync_runs
                (run_id, sync_type, company_name, year, month)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, run_id, sync_type, started_at
        ''', (run_id, sync_type, company_name, year, month), returning=True)

    def complete_run(self, run_id, success=True, employees_synced=0,
                     records_created=0, records_updated=0, error_message=None):
        """Mark a sync run as completed."""
        status = 'completed' if success else 'failed'
        return self.execute('''
            UPDATE sincron_sync_runs
            SET finished_at = NOW(), status = %s,
                employees_synced = %s, records_created = %s,
                records_updated = %s, error_message = %s
            WHERE run_id = %s
        ''', (status, employees_synced, records_created, records_updated,
              error_message, run_id))

    def get_recent_runs(self, sync_type=None, limit=20):
        """Get recent sync runs."""
        if sync_type:
            return self.query_all('''
                SELECT * FROM sincron_sync_runs
                WHERE sync_type = %s
                ORDER BY started_at DESC LIMIT %s
            ''', (sync_type, limit))
        return self.query_all('''
            SELECT * FROM sincron_sync_runs
            ORDER BY started_at DESC LIMIT %s
        ''', (limit,))

    def get_last_successful_run(self, sync_type=None, company_name=None):
        """Get the most recent successful run."""
        query = "SELECT * FROM sincron_sync_runs WHERE status = 'completed'"
        params = []
        if sync_type:
            query += ' AND sync_type = %s'
            params.append(sync_type)
        if company_name:
            query += ' AND company_name = %s'
            params.append(company_name)
        query += ' ORDER BY finished_at DESC LIMIT 1'
        return self.query_one(query, tuple(params))
