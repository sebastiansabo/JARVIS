"""Event Repository - Data access for HR events.

Handles all database operations for the hr.events table.
"""
from typing import Optional, List, Dict, Any

from core.base_repository import BaseRepository


class HREventRepository(BaseRepository):
    """Repository for HR event data access operations."""

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all HR events ordered by date."""
        return self.query_all('''
            SELECT e.*, u.name as created_by_name
            FROM hr.events e
            LEFT JOIN public.users u ON e.created_by = u.id
            ORDER BY e.start_date DESC
        ''')

    def get_by_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Get a single HR event by ID."""
        return self.query_one('''
            SELECT e.*, u.name as created_by_name
            FROM hr.events e
            LEFT JOIN public.users u ON e.created_by = u.id
            WHERE e.id = %s
        ''', (event_id,))

    def create(self, name: str, start_date: str, end_date: str,
               company: str = None, brand: str = None,
               description: str = None, created_by: int = None) -> int:
        """Create a new HR event. Returns the new event ID."""
        result = self.execute('''
            INSERT INTO hr.events (name, start_date, end_date, company, brand, description, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, start_date, end_date, company, brand, description, created_by),
            returning=True)
        return result['id']

    def update(self, event_id: int, name: str, start_date: str, end_date: str,
               company: str = None, brand: str = None, description: str = None) -> bool:
        """Update an HR event."""
        self.execute('''
            UPDATE hr.events
            SET name = %s, start_date = %s, end_date = %s, company = %s, brand = %s, description = %s
            WHERE id = %s
        ''', (name, start_date, end_date, company, brand, description, event_id))
        return True

    def delete(self, event_id: int) -> bool:
        """Delete an HR event (cascades to bonuses)."""
        self.execute('DELETE FROM hr.events WHERE id = %s', (event_id,))
        return True
