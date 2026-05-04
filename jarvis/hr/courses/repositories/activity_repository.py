"""Repository for HR course activity log."""
from typing import List, Dict, Any
from core.base_repository import BaseRepository


class CourseActivityRepository(BaseRepository):
    """Activity audit trail for course changes."""

    def get_by_course(self, course_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get activity log for a course, newest first."""
        return self.query_all('''
            SELECT ca.*, u.name as actor_display_name
            FROM hr.course_activity ca
            LEFT JOIN public.users u ON ca.actor_id = u.id
            WHERE ca.course_id = %s
            ORDER BY ca.created_at DESC
            LIMIT %s
        ''', (course_id, limit))

    def log(self, course_id: int, action: str, actor_id: int = None,
            actor_name: str = None, details: dict = None) -> int:
        """Record an activity entry. Returns the new activity ID."""
        import json
        result = self.execute('''
            INSERT INTO hr.course_activity (course_id, action, actor_id, actor_name, details)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (course_id, action, actor_id, actor_name,
              json.dumps(details or {})), returning=True)
        return result['id'] if result else None
