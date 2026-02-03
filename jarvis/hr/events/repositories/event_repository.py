"""Event Repository - Data access for HR events.

Handles all database operations for the hr.events table.
"""
from typing import Optional, List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from database import get_db, get_cursor, release_db, dict_from_row


class EventRepository:
    """Repository for HR event data access operations."""

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all HR events ordered by date.

        Returns:
            List of event dictionaries
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT e.*, u.name as created_by_name
            FROM hr.events e
            LEFT JOIN public.users u ON e.created_by = u.id
            ORDER BY e.start_date DESC
        ''')
        rows = cursor.fetchall()
        release_db(conn)
        return [dict_from_row(row) for row in rows]

    def get_by_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Get a single HR event by ID.

        Args:
            event_id: The event ID

        Returns:
            Event dict or None if not found
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT e.*, u.name as created_by_name
            FROM hr.events e
            LEFT JOIN public.users u ON e.created_by = u.id
            WHERE e.id = %s
        ''', (event_id,))
        row = cursor.fetchone()
        release_db(conn)
        return dict_from_row(row) if row else None

    def create(
        self,
        name: str,
        start_date: str,
        end_date: str,
        company: str = None,
        brand: str = None,
        description: str = None,
        created_by: int = None
    ) -> int:
        """Create a new HR event.

        Args:
            name: Event name
            start_date: Start date
            end_date: End date
            company: Company name
            brand: Brand name
            description: Event description
            created_by: User ID who created the event

        Returns:
            The new event ID
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            INSERT INTO hr.events (name, start_date, end_date, company, brand, description, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, start_date, end_date, company, brand, description, created_by))
        event_id = cursor.fetchone()['id']
        conn.commit()
        release_db(conn)
        return event_id

    def update(
        self,
        event_id: int,
        name: str,
        start_date: str,
        end_date: str,
        company: str = None,
        brand: str = None,
        description: str = None
    ) -> bool:
        """Update an HR event.

        Args:
            event_id: The event ID
            name: Event name
            start_date: Start date
            end_date: End date
            company: Company name
            brand: Brand name
            description: Event description

        Returns:
            True if successful
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE hr.events
            SET name = %s, start_date = %s, end_date = %s, company = %s, brand = %s, description = %s
            WHERE id = %s
        ''', (name, start_date, end_date, company, brand, description, event_id))
        conn.commit()
        release_db(conn)
        return True

    def delete(self, event_id: int) -> bool:
        """Delete an HR event (cascades to bonuses).

        Args:
            event_id: The event ID

        Returns:
            True if successful
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('DELETE FROM hr.events WHERE id = %s', (event_id,))
        conn.commit()
        release_db(conn)
        return True
