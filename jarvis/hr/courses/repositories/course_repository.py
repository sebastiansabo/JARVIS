"""Repository for HR course data access operations."""
from typing import List, Dict, Any, Optional
from core.base_repository import BaseRepository


class CourseRepository(BaseRepository):
    """Repository for HR course data access."""

    def get_all(self, company_id=None, course_type_id=None, status=None,
                search=None, year=None, month=None, include_deleted=False,
                limit=200, offset=0) -> List[Dict[str, Any]]:
        """Get courses with optional filters."""
        query = '''
            SELECT c.*, ct.code as course_type_code, ct.name as course_type_name,
                   ct.requires_certification, ct.default_validity_months,
                   s.name as supplier_name,
                   u.name as created_by_name,
                   comp.company as company_name,
                   (SELECT COUNT(*) FROM hr.course_enrollments ce WHERE ce.course_id = c.id) as enrollment_count
            FROM hr.courses c
            LEFT JOIN hr.course_types ct ON c.course_type_id = ct.id
            LEFT JOIN suppliers s ON c.supplier_id = s.id
            LEFT JOIN public.users u ON c.created_by = u.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            WHERE 1=1
        '''
        params = []

        if include_deleted:
            query += ' AND c.deleted_at IS NOT NULL'
        else:
            query += ' AND c.deleted_at IS NULL'

        if company_id:
            query += ' AND c.company_id = %s'
            params.append(company_id)
        if course_type_id:
            query += ' AND c.course_type_id = %s'
            params.append(course_type_id)
        if status:
            query += ' AND c.status = %s'
            params.append(status)
        if year:
            query += ' AND EXTRACT(YEAR FROM c.start_date) = %s'
            params.append(year)
        if month:
            query += ' AND EXTRACT(MONTH FROM c.start_date) = %s'
            params.append(month)
        if search:
            query += ' AND (c.name ILIKE %s OR ct.name ILIKE %s OR s.name ILIKE %s)'
            like = f'%{search}%'
            params.extend([like, like, like])

        query += ' ORDER BY c.start_date DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])

        return self.query_all(query, params)

    def get_count(self, company_id=None, course_type_id=None, status=None,
                  search=None, year=None, month=None, include_deleted=False) -> int:
        """Get total count with same filters."""
        query = '''
            SELECT COUNT(*) as cnt
            FROM hr.courses c
            LEFT JOIN hr.course_types ct ON c.course_type_id = ct.id
            LEFT JOIN suppliers s ON c.supplier_id = s.id
            WHERE 1=1
        '''
        params = []
        if include_deleted:
            query += ' AND c.deleted_at IS NOT NULL'
        else:
            query += ' AND c.deleted_at IS NULL'
        if company_id:
            query += ' AND c.company_id = %s'
            params.append(company_id)
        if course_type_id:
            query += ' AND c.course_type_id = %s'
            params.append(course_type_id)
        if status:
            query += ' AND c.status = %s'
            params.append(status)
        if year:
            query += ' AND EXTRACT(YEAR FROM c.start_date) = %s'
            params.append(year)
        if month:
            query += ' AND EXTRACT(MONTH FROM c.start_date) = %s'
            params.append(month)
        if search:
            query += ' AND (c.name ILIKE %s OR ct.name ILIKE %s OR s.name ILIKE %s)'
            like = f'%{search}%'
            params.extend([like, like, like])
        result = self.query_one(query, params)
        return result['cnt'] if result else 0

    def get_available_years(self) -> List[int]:
        """Get distinct years from course start dates."""
        rows = self.query_all('''
            SELECT DISTINCT EXTRACT(YEAR FROM start_date)::int as year
            FROM hr.courses WHERE deleted_at IS NULL
            ORDER BY year DESC
        ''')
        return [r['year'] for r in rows]

    def get_by_id(self, course_id: int) -> Optional[Dict[str, Any]]:
        """Get a single course by ID with all joins."""
        return self.query_one('''
            SELECT c.*, ct.code as course_type_code, ct.name as course_type_name,
                   ct.requires_certification, ct.default_validity_months,
                   s.name as supplier_name,
                   u.name as created_by_name,
                   comp.company as company_name,
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
               course_code=None, duration_hours=None, travel_mode=None,
               created_by=None) -> int:
        """Create a new course. Returns the new course ID."""
        result = self.execute('''
            INSERT INTO hr.courses (name, course_type_id, company_id, supplier_id,
                                     trainer_name, start_date, end_date, location,
                                     description, budget, currency, course_code,
                                     duration_hours, travel_mode, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, course_type_id, company_id, supplier_id, trainer_name,
              start_date, end_date, location, description, budget, currency,
              course_code, duration_hours, travel_mode, created_by), returning=True)
        return result['id']

    def update(self, course_id, **kwargs) -> bool:
        """Update a course. Pass only fields to update."""
        allowed = {'name', 'course_type_id', 'company_id', 'supplier_id',
                   'trainer_name', 'start_date', 'end_date', 'location',
                   'description', 'budget', 'currency', 'status', 'approval_request_id',
                   'course_code', 'duration_hours', 'travel_mode'}
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
        """Soft delete a course (move to bin)."""
        return self.execute(
            'UPDATE hr.courses SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s AND deleted_at IS NULL',
            (course_id,)) > 0

    def restore(self, course_id: int) -> bool:
        """Restore a soft-deleted course from the bin."""
        return self.execute(
            'UPDATE hr.courses SET deleted_at = NULL WHERE id = %s AND deleted_at IS NOT NULL',
            (course_id,)) > 0

    def permanently_delete(self, course_id: int) -> bool:
        """Permanently delete a course and its enrollments."""
        return self.execute('DELETE FROM hr.courses WHERE id = %s', (course_id,)) > 0

    def bulk_soft_delete(self, course_ids: List[int]) -> int:
        """Soft delete multiple courses. Returns count deleted."""
        if not course_ids:
            return 0
        placeholders = ','.join(['%s'] * len(course_ids))
        return self.execute(
            f'UPDATE hr.courses SET deleted_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders}) AND deleted_at IS NULL',
            course_ids)

    def bulk_restore(self, course_ids: List[int]) -> int:
        """Restore multiple soft-deleted courses. Returns count restored."""
        if not course_ids:
            return 0
        placeholders = ','.join(['%s'] * len(course_ids))
        return self.execute(
            f'UPDATE hr.courses SET deleted_at = NULL WHERE id IN ({placeholders}) AND deleted_at IS NOT NULL',
            course_ids)

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

    def get_dashboard_stats(self, year: int, company_id: int = None) -> Dict[str, Any]:
        """Dashboard summary stats for a year."""
        where = 'c.deleted_at IS NULL AND EXTRACT(YEAR FROM c.start_date) = %s'
        params = [year]
        if company_id:
            where += ' AND c.company_id = %s'
            params.append(company_id)

        totals = self.query_one(f'''
            SELECT COUNT(*) as total_courses,
                   COUNT(DISTINCT ce.employee_id) as total_participants,
                   COALESCE(SUM(ec.total_cost), 0) as total_cost,
                   COALESCE(SUM(c.end_date - c.start_date + 1), 0) as total_days
            FROM hr.courses c
            LEFT JOIN hr.course_enrollments ce ON ce.course_id = c.id
            LEFT JOIN hr.enrollment_costs ec ON ec.enrollment_id = ce.id
            WHERE {where}
        ''', params)

        by_status = self.query_all(f'''
            SELECT c.status, COUNT(*) as count
            FROM hr.courses c
            WHERE {where}
            GROUP BY c.status ORDER BY count DESC
        ''', params)

        return {
            **(totals or {}),
            'by_status': by_status,
        }
