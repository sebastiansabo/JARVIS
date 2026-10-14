"""Connector Repository - Data access layer for connector operations.

Handles connector CRUD and sync log operations.
"""
import json
from datetime import datetime
from typing import Optional

from core.base_repository import BaseRepository


class ConnectorRepository(BaseRepository):
    """Repository for connector data access operations."""

    def get_all(self) -> list[dict]:
        """Get all connectors."""
        return self.query_all('SELECT * FROM connectors ORDER BY name')

    def get(self, connector_id: int) -> Optional[dict]:
        """Get a specific connector by ID."""
        return self.query_one('SELECT * FROM connectors WHERE id = %s', (connector_id,))

    def get_by_type(self, connector_type: str) -> Optional[dict]:
        """Get a connector by type (e.g., 'google_ads', 'meta')."""
        return self.query_one('SELECT * FROM connectors WHERE connector_type = %s', (connector_type,))

    def get_all_by_type(self, connector_type: str) -> list[dict]:
        """Get all connectors of a given type."""
        return self.query_all('SELECT * FROM connectors WHERE connector_type = %s ORDER BY name', (connector_type,))

    def save(self, connector_type: str, name: str, status: str = 'disconnected',
             config: dict = None, credentials: dict = None) -> int:
        """Save a new connector. Returns connector ID."""
        result = self.execute('''
            INSERT INTO connectors (connector_type, name, status, config, credentials)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (connector_type, name, status,
              json.dumps(config or {}), json.dumps(credentials or {})),
            returning=True)
        return result['id']

    def update(self, connector_id: int, name: str = None, status: str = None,
               config: dict = None, credentials: dict = None,
               last_sync: datetime = None, last_error: str = None) -> bool:
        """Update a connector. Returns True if updated."""
        updates = []
        params = []

        if name is not None:
            updates.append('name = %s')
            params.append(name)
        if status is not None:
            updates.append('status = %s')
            params.append(status)
        if config is not None:
            updates.append('config = %s')
            params.append(json.dumps(config))
        if credentials is not None:
            updates.append('credentials = %s')
            params.append(json.dumps(credentials))
        if last_sync is not None:
            updates.append('last_sync = %s')
            params.append(last_sync)
        if last_error is not None:
            updates.append('last_error = %s')
            params.append(last_error)

        if not updates:
            return False

        updates.append('updated_at = CURRENT_TIMESTAMP')
        params.append(connector_id)
        return self.execute(f"UPDATE connectors SET {', '.join(updates)} WHERE id = %s", params) > 0

    def delete(self, connector_id: int) -> bool:
        """Delete a connector and its sync logs."""
        return self.execute('DELETE FROM connectors WHERE id = %s', (connector_id,)) > 0

    def add_sync_log(self, connector_id: int, sync_type: str, status: str,
                     invoices_found: int = 0, invoices_imported: int = 0,
                     error_message: str = None, details: dict = None) -> int:
        """Add a sync log entry. Returns log ID."""
        result = self.execute('''
            INSERT INTO connector_sync_log
            (connector_id, sync_type, status, invoices_found, invoices_imported, error_message, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (connector_id, sync_type, status, invoices_found, invoices_imported,
              error_message, json.dumps(details or {})),
            returning=True)
        return result['id']

    def update_sync_log(self, log_id: int, status: str = None,
                        invoices_imported: int = None, error_message: str = None,
                        details: dict = None):
        """Patch an existing sync-log row — used to flip a 'running' job to its
        terminal state and bump the live progress count. Only the fields passed
        are written; a call with nothing to set is a no-op. Column names are
        static literals (never user input), values are parameterized."""
        sets, params = [], []
        if status is not None:
            sets.append('status=%s'); params.append(status)
        if invoices_imported is not None:
            sets.append('invoices_imported=%s'); params.append(invoices_imported)
        if error_message is not None:
            sets.append('error_message=%s'); params.append(error_message)
        if details is not None:
            sets.append('details=%s'); params.append(json.dumps(details))
        if not sets:
            return None
        params.append(log_id)
        return self.execute(
            f"UPDATE connector_sync_log SET {', '.join(sets)} WHERE id=%s", tuple(params))

    def get_sync_logs(self, connector_id: int, limit: int = 20) -> list[dict]:
        """Get sync logs for a connector, most recent first."""
        return self.query_all('''
            SELECT * FROM connector_sync_log
            WHERE connector_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        ''', (connector_id, limit))

    def get_latest_sync_log(self, connector_id: int, sync_type: str, vehicle_id: int):
        """Most recent sync-log row for one vehicle, matched on the JSONB
        details->>'vehicle_id'. Bounded to a single row so a busy, fleet-wide
        connector can't push a still-running job out of a fixed recent-rows
        window (which would make a per-vehicle status poll falsely read idle)."""
        return self.query_one('''
            SELECT * FROM connector_sync_log
            WHERE connector_id = %s AND sync_type = %s AND details->>'vehicle_id' = %s
            ORDER BY created_at DESC
            LIMIT 1
        ''', (connector_id, sync_type, str(vehicle_id)))
