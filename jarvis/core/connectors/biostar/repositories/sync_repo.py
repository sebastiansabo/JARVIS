"""Sync run tracking repository for BioStar connector."""

import uuid
from datetime import datetime

from core.base_repository import BaseRepository


class BioStarSyncRepository(BaseRepository):
    """Data access for biostar_sync_runs and biostar_sync_errors."""

    def create_run(self, sync_type):
        """Create a new sync run. Returns dict with run_id."""
        run_id = str(uuid.uuid4())
        return self.execute('''
            INSERT INTO biostar_sync_runs (run_id, sync_type)
            VALUES (%s, %s)
            RETURNING id, run_id, sync_type, started_at
        ''', (run_id, sync_type), returning=True)

    def complete_run(self, run_id, success=True, records_fetched=0,
                     records_created=0, records_updated=0, records_skipped=0,
                     errors_count=0, cursor_before=None, cursor_after=None,
                     error_summary=None):
        """Mark a sync run as completed."""
        return self.execute('''
            UPDATE biostar_sync_runs
            SET finished_at = NOW(), success = %s,
                records_fetched = %s, records_created = %s,
                records_updated = %s, records_skipped = %s,
                errors_count = %s, cursor_before = %s, cursor_after = %s,
                error_summary = %s
            WHERE run_id = %s
        ''', (success, records_fetched, records_created, records_updated,
              records_skipped, errors_count, cursor_before, cursor_after,
              error_summary, run_id))

    def record_error(self, run_id, error_type, error_message,
                     error_code=None, biostar_user_id=None, is_retryable=False):
        """Record a sync error."""
        return self.execute('''
            INSERT INTO biostar_sync_errors
            (run_id, error_type, error_code, error_message, biostar_user_id, is_retryable)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (run_id, error_type, error_code, error_message,
              biostar_user_id, is_retryable), returning=True)

    def get_recent_runs(self, sync_type=None, limit=20):
        """Get recent sync runs, most recent first."""
        if sync_type:
            return self.query_all('''
                SELECT * FROM biostar_sync_runs
                WHERE sync_type = %s
                ORDER BY started_at DESC LIMIT %s
            ''', (sync_type, limit))
        return self.query_all('''
            SELECT * FROM biostar_sync_runs
            ORDER BY started_at DESC LIMIT %s
        ''', (limit,))

    def get_run_errors(self, run_id):
        """Get errors for a specific sync run."""
        return self.query_all('''
            SELECT * FROM biostar_sync_errors
            WHERE run_id = %s ORDER BY created_at
        ''', (run_id,))

    def get_last_successful_run(self, sync_type=None):
        """Get the most recent successful run."""
        if sync_type:
            return self.query_one('''
                SELECT * FROM biostar_sync_runs
                WHERE success = TRUE AND sync_type = %s
                ORDER BY finished_at DESC LIMIT 1
            ''', (sync_type,))
        return self.query_one('''
            SELECT * FROM biostar_sync_runs
            WHERE success = TRUE
            ORDER BY finished_at DESC LIMIT 1
        ''')
