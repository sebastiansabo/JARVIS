"""Event Repository - Data access layer for user event/audit logging.

This module handles all database operations related to user events.
"""
import json
from typing import Optional, Dict, Any

from core.base_repository import BaseRepository


class EventRepository(BaseRepository):
    """Repository for user event/audit log operations."""

    def log_event(
        self,
        event_type: str,
        event_description: str = None,
        user_id: int = None,
        user_email: str = None,
        entity_type: str = None,
        entity_id: int = None,
        ip_address: str = None,
        user_agent: str = None,
        details: Dict[str, Any] = None
    ) -> int:
        """Log a user event/action for audit purposes.

        Args:
            event_type: Type of event (login, logout, password_changed, etc.)
            event_description: Human-readable description
            user_id: ID of the user who performed the action
            user_email: Email of the user
            entity_type: Type of entity affected (invoice, user, etc.)
            entity_id: ID of the entity affected
            ip_address: IP address of the request
            user_agent: User agent string
            details: Additional JSON-serializable details

        Returns:
            The ID of the created event record
        """
        result = self.execute('''
            INSERT INTO user_events
            (user_id, user_email, event_type, event_description, entity_type, entity_id,
             ip_address, user_agent, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            user_id, user_email, event_type, event_description,
            entity_type, entity_id, ip_address, user_agent,
            json.dumps(details or {})
        ), returning=True)
        return result['id']

    def get_events(self, limit: int = 100, offset: int = 0, user_id: int = None,
                   event_type: str = None, entity_type: str = None,
                   start_date: str = None, end_date: str = None) -> list[dict]:
        """Get user events with optional filtering."""
        query = '''
            SELECT ue.*, u.name as user_name
            FROM user_events ue
            LEFT JOIN users u ON ue.user_id = u.id
        '''
        params = []
        conditions = []
        if user_id:
            conditions.append('ue.user_id = %s')
            params.append(user_id)
        if event_type:
            conditions.append('ue.event_type = %s')
            params.append(event_type)
        if entity_type:
            conditions.append('ue.entity_type = %s')
            params.append(entity_type)
        if start_date:
            conditions.append('ue.created_at >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('ue.created_at <= %s')
            params.append(end_date)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY ue.created_at DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])
        return self.query_all(query, params)

    def get_event_types(self) -> list[str]:
        """Get distinct event types for filtering."""
        rows = self.query_all('''
            SELECT DISTINCT event_type FROM user_events
            ORDER BY event_type
        ''')
        return [row['event_type'] for row in rows]
