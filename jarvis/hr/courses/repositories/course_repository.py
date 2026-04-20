"""Repository for HR course data access operations."""
from typing import List, Dict, Any, Optional
from core.base_repository import BaseRepository


class CourseRepository(BaseRepository):
    """Repository for HR course data access."""

    def get_all(self, company_id=None, course_type_id=None, status=None,
                search=None, limit=200, offset=0) -> List[Dict[str, Any]]:
        """Get courses with optional filters."""
        query = '''
            SELECT c.*, ct.code as course_type_code, ct.name as course_type_name,
                   ct.requires_certification, ct.default_validity_months,
                   s.name as supplier_name,
                   u.name as created_by_name,
                   comp.name as company_name,
                   (SELECT COUNT(*) FROM hr.course_enrollments ce WHERE ce.course_id = c.id) as enrollment_count
            FROM hr.courses c
            LEFT JOIN hr.course_types ct ON c.course_type_id = ct.id
            LEFT JOIN suppliers s ON c.supplier_id = s.id
            LEFT JOIN public.users u ON c.created_by = u.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            WHERE 1=1
        '''
        params = []

        if company_id:
            query += ' AND c.company_id = %s'
            params.append(company_id)
        if course_type_id:
            query += ' AND c.course_type_id = %s'
            params.append(course_type_id)
        if status:
            query += ' AND c.status = %s'
            params.append(status)
        if search:
            query += ' AND (c.name ILIKE %s OR ct.name ILIKE %s OR s.name ILIKE %s)'
            like = f'%{search}%'
            params.extend([like, like, like])

        query += ' ORDER BY c.start_date DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])

        return self.query_all(query, params)

    def get_count(self, company_id=None, course_type_id=None, status=None, search=None) -> int:
        """Get total count with same filters."""
        query = '''
            SELECT COUNT(*) as cnt
            FROM hr.courses c
            LEFT JOIN hr.course_types ct ON c.course_type_id = ct.id
            LEFT JOIN suppliers s ON c.supplier_id = s.id
            WHERE 1=1
        '''
        params = []
        if company_id:
            query += ' AND c.company_id = %s'
            params.append(company_id)
        if course_type_id:
            query += ' AND c.course_type_id = %s'
            params.append(course_type_id)
        if status:
            query += ' AND c.status = %s'
            params.append(status)
        if search:
            query += ' AND (c.name ILIKE %s OR ct.name ILIKE %s OR s.name ILIKE %s)'
            like = f'%{search}%'
            params.extend([like, like, like])
        result = self.query_one(query, params)
        return result['cnt'] if result else 0

    def get_by_id(self, course_id: int) -> Optional[Dict[str, Any]]:
        """Get a single course by ID with all joins."""
        return self.query_one('''
            SELECT c.*, ct.code as course_type_code, ct.name as course_type_name,
                   ct.requires_certification, ct.default_validity_months,
                   s.name as supplier_name,
                   u.name as created_by_name,
                   comp.name as company_name,
                   (SELECT COUNT(*) FROM hr.course_enrollments ce WHERE ce.course_id = c.id) as enrollment_count
            FROM hr.courses c
            LEFT JOIN hr.course_types ct ON c.course_type_id = ct.id
            LEFT JOIN suppliers s ON c.supplier_id = s.id
            LEFT JOIN public.users u ON c.created_by = u.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            WHERE c.id = %s
        ''', (course_id,))

    def create(self, name, course_type_id, company_id, start_date, end_date,
               supplier_id=None, trainer_name=None, location=None,
               description=None, budget=None, currency='RON',
               created_by=None) -> int:
        """Create a new course. Returns the new course ID."""
        result = self.execute('''
            INSERT INTO hr.courses (name, course_type_id, company_id, supplier_id,
                                     trainer_name, start_date, end_date, location,
                                     description, budget, currency, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, course_type_id, company_id, supplier_id, trainer_name,
              start_date, end_date, location, description, budget, currency,
              created_by), returning=True)
        return result['id']

    def update(self, course_id, **kwargs) -> bool:
        """Update a course. Pass only fields to update."""
        allowed = {'name', 'course_type_id', 'company_id', 'supplier_id',
                   'trainer_name', 'start_date', 'end_date', 'location',
                   'description', 'budget', 'currency', 'status', 'approval_request_id'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        fields['updated_at'] = 'CURRENT_TIMESTAMP'

        sets = []
        params = []
        for k, v in fields.items():
            if v == 'CURRENT_TIMESTAMP':
                sets.append(f'{k} = CURRENT_TIMESTAMP')
            else:
                sets.append(f'{k} = %s')
                params.append(v)

        params.append(course_id)
        self.execute(f"UPDATE hr.courses SET {', '.join(sets)} WHERE id = %s", params)
        return True

    def delete(self, course_id: int) -> bool:
        """Delete a course (cascades to enrollments)."""
        self.execute('DELETE FROM hr.courses WHERE id = %s', (course_id,))
        return True

    def get_all_types(self, active_only=True) -> List[Dict[str, Any]]:
        """Get all course types."""
        query = 'SELECT * FROM hr.course_types'
        if active_only:
            query += ' WHERE is_active = TRUE'
        query += ' ORDER BY name'
        return self.query_all(query)

    def get_type_by_id(self, type_id: int) -> Optional[Dict[str, Any]]:
        """Get a single course type."""
        return self.query_one('SELECT * FROM hr.course_types WHERE id = %s', (type_id,))
