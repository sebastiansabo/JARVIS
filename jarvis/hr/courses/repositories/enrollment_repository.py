"""Repository for HR course enrollment data access."""
from typing import List, Dict, Any, Optional
from core.base_repository import BaseRepository


class EnrollmentRepository(BaseRepository):
    """Repository for course enrollment data access."""

    def get_by_course(self, course_id: int) -> List[Dict[str, Any]]:
        """Get all enrollments for a course."""
        return self.query_all('''
            SELECT ce.*, u.name as employee_name, u.company, u.department, u.brand
            FROM hr.course_enrollments ce
            JOIN public.users u ON ce.employee_id = u.id
            WHERE ce.course_id = %s
            ORDER BY u.name
        ''', (course_id,))

    def get_by_employee(self, employee_id: int) -> List[Dict[str, Any]]:
        """Get all enrollments for an employee."""
        return self.query_all('''
            SELECT ce.*, c.name as course_name, c.start_date, c.end_date, c.status as course_status,
                   ct.code as course_type_code, ct.name as course_type_name
            FROM hr.course_enrollments ce
            JOIN hr.courses c ON ce.course_id = c.id
            LEFT JOIN hr.course_types ct ON c.course_type_id = ct.id
            WHERE ce.employee_id = %s
            ORDER BY c.start_date DESC
        ''', (employee_id,))

    def create(self, course_id: int, employee_id: int, notes: str = None) -> int:
        """Enroll an employee in a course."""
        result = self.execute('''
            INSERT INTO hr.course_enrollments (course_id, employee_id, notes)
            VALUES (%s, %s, %s)
            ON CONFLICT (course_id, employee_id) DO NOTHING
            RETURNING id
        ''', (course_id, employee_id, notes), returning=True)
        return result['id'] if result else None

    def create_bulk(self, course_id: int, employee_ids: List[int]) -> int:
        """Enroll multiple employees. Returns count of new enrollments."""
        count = 0
        for eid in employee_ids:
            result = self.execute('''
                INSERT INTO hr.course_enrollments (course_id, employee_id)
                VALUES (%s, %s)
                ON CONFLICT (course_id, employee_id) DO NOTHING
                RETURNING id
            ''', (course_id, eid), returning=True)
            if result:
                count += 1
        return count

    def update_status(self, enrollment_id: int, status: str, completed_at=None) -> bool:
        """Update enrollment status."""
        if completed_at:
            self.execute('''
                UPDATE hr.course_enrollments SET enrollment_status = %s, completed_at = %s WHERE id = %s
            ''', (status, completed_at, enrollment_id))
        else:
            self.execute('''
                UPDATE hr.course_enrollments SET enrollment_status = %s WHERE id = %s
            ''', (status, enrollment_id))
        return True

    def delete(self, enrollment_id: int) -> bool:
        """Remove an enrollment."""
        self.execute('DELETE FROM hr.course_enrollments WHERE id = %s', (enrollment_id,))
        return True

    def get_by_id(self, enrollment_id: int) -> Optional[Dict[str, Any]]:
        """Get enrollment by ID."""
        return self.query_one('''
            SELECT ce.*, u.name as employee_name, c.name as course_name,
                   c.course_type_id, ct.requires_certification, ct.default_validity_months
            FROM hr.course_enrollments ce
            JOIN public.users u ON ce.employee_id = u.id
            JOIN hr.courses c ON ce.course_id = c.id
            LEFT JOIN hr.course_types ct ON c.course_type_id = ct.id
            WHERE ce.id = %s
        ''', (enrollment_id,))
