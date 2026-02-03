"""Event Repository - Data access layer for user event/audit logging.

This module handles all database operations related to user events.
"""
import json
from typing import Optional, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
from database import get_db, get_cursor, release_db


class EventRepository:
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
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            cursor.execute('''
                INSERT INTO user_events
                (user_id, user_email, event_type, event_description, entity_type, entity_id,
                 ip_address, user_agent, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                user_id,
                user_email,
                event_type,
                event_description,
                entity_type,
                entity_id,
                ip_address,
                user_agent,
                json.dumps(details or {})
            ))

            event_id = cursor.fetchone()['id']
            conn.commit()
            return event_id
        finally:
            release_db(conn)
