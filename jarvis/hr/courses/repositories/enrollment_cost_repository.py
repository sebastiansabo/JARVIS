"""Repository for per-enrollment cost breakdown (mirrors legacy Excel)."""
from typing import List, Dict, Any, Optional
from core.base_repository import BaseRepository


class EnrollmentCostRepository(BaseRepository):
    """Per-enrollment cost tracking: training fee, per diem, accommodation, transport, taxi."""

    def get_by_enrollment(self, enrollment_id: int) -> Optional[Dict[str, Any]]:
        """Get cost record for a single enrollment."""
        return self.query_one(
            'SELECT * FROM hr.enrollment_costs WHERE enrollment_id = %s',
            (enrollment_id,))

    def get_by_course(self, course_id: int) -> List[Dict[str, Any]]:
        """Get all enrollment costs for a course with employee info."""
        return self.query_all('''
            SELECT ec.*, ce.employee_id, ce.enrollment_status,
                   ce.order_number, ce.travel_order, ce.additional_act,
                   ce.department as enrollment_department, ce.travel_mode as enrollment_travel_mode,
                   u.name as employee_name, u.company as employee_company,
                   u.department as user_department
            FROM hr.enrollment_costs ec
            JOIN hr.course_enrollments ce ON ec.enrollment_id = ce.id
            JOIN public.users u ON ce.employee_id = u.id
            WHERE ce.course_id = %s
            ORDER BY u.name
        ''', (course_id,))

    def upsert(self, enrollment_id: int, training_fee=0, per_diem=0,
               accommodation=0, transport=0, taxi=0, currency='RON',
               notes=None) -> int:
        """Insert or update cost record for an enrollment."""
        result = self.execute('''
            INSERT INTO hr.enrollment_costs
                (enrollment_id, training_fee, per_diem, accommodation, transport, taxi, currency, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (enrollment_id) DO UPDATE SET
                training_fee = EXCLUDED.training_fee,
                per_diem = EXCLUDED.per_diem,
                accommodation = EXCLUDED.accommodation,
                transport = EXCLUDED.transport,
                taxi = EXCLUDED.taxi,
                currency = EXCLUDED.currency,
                notes = EXCLUDED.notes,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        ''', (enrollment_id, training_fee, per_diem, accommodation, transport,
              taxi, currency, notes), returning=True)
        return result['id'] if result else None

    def get_cost_summary_by_course(self, course_id: int) -> Dict[str, Any]:
        """Aggregate costs for a course — mirrors Excel totals row."""
        return self.query_one('''
            SELECT COALESCE(SUM(ec.training_fee), 0) as total_training_fee,
                   COALESCE(SUM(ec.per_diem), 0) as total_per_diem,
                   COALESCE(SUM(ec.accommodation), 0) as total_accommodation,
                   COALESCE(SUM(ec.transport), 0) as total_transport,
                   COALESCE(SUM(ec.taxi), 0) as total_taxi,
                   COALESCE(SUM(ec.total_cost), 0) as total_cost,
                   COUNT(*) as enrollment_count
            FROM hr.enrollment_costs ec
            JOIN hr.course_enrollments ce ON ec.enrollment_id = ce.id
            WHERE ce.course_id = %s
        ''', (course_id,)) or {}

    def get_cost_summary_by_company(self, year: int, month: int = None) -> List[Dict[str, Any]]:
        """Cost summary grouped by company — mirrors Excel 'Costuri' sheet."""
        query = '''
            SELECT comp.id as company_id, comp.company as company_name,
                   COALESCE(SUM(ec.training_fee), 0) as training_fee,
                   COALESCE(SUM(ec.per_diem), 0) as per_diem,
                   COALESCE(SUM(ec.accommodation), 0) as accommodation,
                   COALESCE(SUM(ec.transport), 0) as transport,
                   COALESCE(SUM(ec.taxi), 0) as taxi,
                   COALESCE(SUM(ec.total_cost), 0) as total_cost,
                   COUNT(DISTINCT c.id) as course_count,
                   COUNT(DISTINCT ce.employee_id) as participant_count,
                   COALESCE(SUM(c.end_date - c.start_date + 1), 0) as total_days
            FROM hr.enrollment_costs ec
            JOIN hr.course_enrollments ce ON ec.enrollment_id = ce.id
            JOIN hr.courses c ON ce.course_id = c.id
            LEFT JOIN companies comp ON c.company_id = comp.id
            WHERE c.deleted_at IS NULL
              AND EXTRACT(YEAR FROM c.start_date) = %s
        '''
        params = [year]
        if month:
            query += ' AND EXTRACT(MONTH FROM c.start_date) = %s'
            params.append(month)
        query += ' GROUP BY comp.id, comp.company ORDER BY comp.company'
        return self.query_all(query, params)

    def get_cost_summary_by_department(self, company_id: int, year: int,
                                       month: int = None) -> List[Dict[str, Any]]:
        """Cost summary by department within a company — mirrors Excel sub-tables."""
        query = '''
            SELECT COALESCE(ce.department, u.department, 'Unassigned') as department,
                   COALESCE(SUM(ec.training_fee), 0) as training_fee,
                   COALESCE(SUM(ec.per_diem), 0) as per_diem,
                   COALESCE(SUM(ec.accommodation), 0) as accommodation,
                   COALESCE(SUM(ec.transport), 0) as transport,
                   COALESCE(SUM(ec.taxi), 0) as taxi,
                   COALESCE(SUM(ec.total_cost), 0) as total_cost,
                   COUNT(DISTINCT c.id) as course_count,
                   COUNT(DISTINCT ce.employee_id) as participant_count
            FROM hr.enrollment_costs ec
            JOIN hr.course_enrollments ce ON ec.enrollment_id = ce.id
            JOIN hr.courses c ON ce.course_id = c.id
            JOIN public.users u ON ce.employee_id = u.id
            WHERE c.deleted_at IS NULL
              AND c.company_id = %s
              AND EXTRACT(YEAR FROM c.start_date) = %s
        '''
        params = [company_id, year]
        if month:
            query += ' AND EXTRACT(MONTH FROM c.start_date) = %s'
            params.append(month)
        query += ' GROUP BY department ORDER BY department'
        return self.query_all(query, params)

    def get_cost_by_month(self, year: int, company_id: int = None) -> List[Dict[str, Any]]:
        """Monthly cost breakdown for chart display."""
        query = '''
            SELECT EXTRACT(MONTH FROM c.start_date)::int as month,
                   COALESCE(SUM(ec.training_fee), 0) as training_fee,
                   COALESCE(SUM(ec.per_diem), 0) as per_diem,
                   COALESCE(SUM(ec.accommodation), 0) as accommodation,
                   COALESCE(SUM(ec.transport), 0) as transport,
                   COALESCE(SUM(ec.taxi), 0) as taxi,
                   COALESCE(SUM(ec.total_cost), 0) as total_cost,
                   COUNT(DISTINCT c.id) as course_count
            FROM hr.enrollment_costs ec
            JOIN hr.course_enrollments ce ON ec.enrollment_id = ce.id
            JOIN hr.courses c ON ce.course_id = c.id
            WHERE c.deleted_at IS NULL
              AND EXTRACT(YEAR FROM c.start_date) = %s
        '''
        params = [year]
        if company_id:
            query += ' AND c.company_id = %s'
            params.append(company_id)
        query += ' GROUP BY month ORDER BY month'
        return self.query_all(query, params)
