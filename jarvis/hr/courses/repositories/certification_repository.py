"""Repository for HR course certification data access."""
from typing import List, Dict, Any, Optional
from core.base_repository import BaseRepository


class CertificationRepository(BaseRepository):
    """Repository for course certification data access."""

    def get_by_employee(self, employee_id: int) -> List[Dict[str, Any]]:
        """Get all certifications for an employee."""
        return self.query_all('''
            SELECT cc.*, ct.code as course_type_code, ct.name as course_type_name,
                   CASE WHEN cc.expiry_date IS NOT NULL
                        THEN cc.expiry_date - CURRENT_DATE
                        ELSE NULL END as days_until_expiry
            FROM hr.course_certifications cc
            JOIN hr.course_types ct ON cc.course_type_id = ct.id
            WHERE cc.employee_id = %s
            ORDER BY cc.expiry_date ASC NULLS LAST
        ''', (employee_id,))

    def get_expiring(self, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Get certifications expiring within N days."""
        return self.query_all('''
            SELECT cc.*, ct.code as course_type_code, ct.name as course_type_name,
                   u.name as employee_name,
                   cc.expiry_date - CURRENT_DATE as days_until_expiry
            FROM hr.course_certifications cc
            JOIN hr.course_types ct ON cc.course_type_id = ct.id
            JOIN public.users u ON cc.employee_id = u.id
            WHERE cc.status = 'active'
              AND cc.expiry_date IS NOT NULL
              AND cc.expiry_date <= CURRENT_DATE + %s
              AND cc.expiry_date >= CURRENT_DATE
            ORDER BY cc.expiry_date ASC
        ''', (days_ahead,))

    def create(self, enrollment_id, employee_id, course_type_id,
               issued_date, expiry_date=None, certificate_number=None) -> int:
        """Create a certification."""
        result = self.execute('''
            INSERT INTO hr.course_certifications
                (enrollment_id, employee_id, course_type_id, certificate_number,
                 issued_date, expiry_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (enrollment_id, employee_id, course_type_id, certificate_number,
              issued_date, expiry_date), returning=True)
        return result['id']

    def get_by_course(self, course_id: int) -> List[Dict[str, Any]]:
        """Get certifications for all enrollees of a course."""
        return self.query_all('''
            SELECT cc.*, ct.code as course_type_code, ct.name as course_type_name,
                   u.name as employee_name,
                   CASE WHEN cc.expiry_date IS NOT NULL
                        THEN cc.expiry_date - CURRENT_DATE
                        ELSE NULL END as days_until_expiry
            FROM hr.course_certifications cc
            JOIN hr.course_types ct ON cc.course_type_id = ct.id
            JOIN public.users u ON cc.employee_id = u.id
            JOIN hr.course_enrollments ce ON cc.enrollment_id = ce.id
            WHERE ce.course_id = %s
            ORDER BY u.name
        ''', (course_id,))

    def expire_overdue(self) -> int:
        """Mark expired certifications. Returns count updated."""
        result = self.execute('''
            UPDATE hr.course_certifications
            SET status = 'expired'
            WHERE status = 'active' AND expiry_date < CURRENT_DATE
        ''')
        return result
