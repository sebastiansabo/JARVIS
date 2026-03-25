"""Bonus Repository - Data access for event bonuses.

Handles all database operations for the hr.event_bonuses and hr.bonus_types tables.
"""
from typing import Optional, List, Dict, Any

from core.base_repository import BaseRepository


class BonusRepository(BaseRepository):
    """Repository for event bonus data access operations."""

    # ============== Event Bonuses ==============

    def get_all(
        self,
        year: int = None,
        month: int = None,
        employee_id: int = None,
        event_id: int = None,
        scope: str = 'all',
        user_context: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Get event bonuses with optional filters and scope-based access control."""
        query = '''
            SELECT b.*, u.name as employee_name, u.department, u.brand, u.company,
                   ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
                   creator.name as created_by_name,
                   b.user_id as effective_employee_id
            FROM hr.event_bonuses b
            LEFT JOIN public.users u ON u.id = b.user_id
            JOIN hr.events ev ON b.event_id = ev.id
            LEFT JOIN public.users creator ON b.created_by = creator.id
            WHERE 1=1
        '''
        params = []

        if year:
            query += ' AND b.year = %s'
            params.append(year)
        if month:
            query += ' AND b.month = %s'
            params.append(month)
        if employee_id:
            query += ' AND b.user_id = %s'
            params.append(employee_id)
        if event_id:
            query += ' AND b.event_id = %s'
            params.append(event_id)

        if scope == 'own' and user_context:
            query += ' AND b.user_id = %s'
            params.append(user_context.get('user_id'))
        elif scope == 'department' and user_context:
            if user_context.get('department') and user_context.get('company'):
                query += ' AND u.department = %s AND u.company = %s'
                params.append(user_context['department'])
                params.append(user_context['company'])

        query += ' ORDER BY b.year DESC, b.month DESC, u.name'
        return self.query_all(query, params)

    def get_by_id(self, bonus_id: int) -> Optional[Dict[str, Any]]:
        """Get a single event bonus by ID."""
        return self.query_one('''
            SELECT b.*, u.name as employee_name, u.department, u.brand, u.company,
                   ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
                   b.user_id as effective_employee_id
            FROM hr.event_bonuses b
            LEFT JOIN public.users u ON u.id = b.user_id
            JOIN hr.events ev ON b.event_id = ev.id
            WHERE b.id = %s
        ''', (bonus_id,))

    def can_access(self, bonus_id: int, scope: str, user_context: Dict[str, Any]) -> bool:
        """Check if user can access a bonus based on their scope."""
        if scope == 'all':
            return True
        bonus = self.get_by_id(bonus_id)
        if not bonus:
            return False
        if scope == 'own':
            return bonus.get('user_id') == user_context.get('user_id')
        if scope == 'department':
            return (bonus.get('company') == user_context.get('company') and
                    bonus.get('department') == user_context.get('department'))
        return False

    def create(
        self, employee_id: int, event_id: int, year: int, month: int,
        participation_start: str = None, participation_end: str = None,
        bonus_days: int = None, hours_free: float = None, bonus_net: float = None,
        details: str = None, allocation_month: int = None, created_by: int = None
    ) -> int:
        """Create a new event bonus record. Returns the new bonus ID."""
        result = self.execute('''
            INSERT INTO hr.event_bonuses
            (user_id, event_id, year, month, participation_start, participation_end,
             bonus_days, hours_free, bonus_net, details, allocation_month, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (employee_id, event_id, year, month, participation_start, participation_end,
              bonus_days, hours_free, bonus_net, details, allocation_month, created_by),
            returning=True)
        return result['id']

    def create_bulk(self, bonuses: List[Dict[str, Any]], created_by: int = None) -> List[int]:
        """Bulk create event bonus records. Returns list of new bonus IDs."""
        def _work(cursor):
            created_ids = []
            for b in bonuses:
                cursor.execute('''
                    INSERT INTO hr.event_bonuses
                    (user_id, event_id, year, month, participation_start, participation_end,
                     bonus_days, hours_free, bonus_net, details, allocation_month, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (b['employee_id'], b['event_id'], b['year'], b['month'],
                      b.get('participation_start'), b.get('participation_end'),
                      b.get('bonus_days'), b.get('hours_free'), b.get('bonus_net'),
                      b.get('details'), b.get('allocation_month'), created_by))
                created_ids.append(cursor.fetchone()['id'])
            return created_ids
        return self.execute_many(_work)

    def update(
        self, bonus_id: int, employee_id: int, event_id: int, year: int, month: int,
        participation_start: str = None, participation_end: str = None,
        bonus_days: int = None, hours_free: float = None, bonus_net: float = None,
        details: str = None, allocation_month: int = None
    ) -> bool:
        """Update an event bonus record."""
        self.execute('''
            UPDATE hr.event_bonuses
            SET user_id = %s, event_id = %s, year = %s, month = %s,
                participation_start = %s, participation_end = %s, bonus_days = %s,
                hours_free = %s, bonus_net = %s, details = %s, allocation_month = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (employee_id, event_id, year, month, participation_start, participation_end,
              bonus_days, hours_free, bonus_net, details, allocation_month, bonus_id))
        return True

    def delete(self, bonus_id: int) -> bool:
        """Delete an event bonus record."""
        self.execute('DELETE FROM hr.event_bonuses WHERE id = %s', (bonus_id,))
        return True

    # ============== Summary/Stats ==============

    def get_summary(self, year: int = None) -> Dict[str, Any]:
        """Get summary stats for event bonuses."""
        query = '''
            SELECT
                COUNT(DISTINCT b.user_id) as total_employees,
                COUNT(DISTINCT b.event_id) as total_events,
                COUNT(*) as total_bonuses,
                SUM(b.bonus_net) as total_bonus_amount,
                SUM(b.hours_free) as total_hours,
                SUM(b.bonus_days) as total_days
            FROM hr.event_bonuses b
        '''
        params = []
        if year:
            query += ' WHERE b.year = %s'
            params.append(year)
        return self.query_one(query, params)

    def get_by_month(self, year: int) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by month for a year."""
        return self.query_all('''
            SELECT month, COUNT(*) as count, SUM(bonus_net) as total
            FROM hr.event_bonuses
            WHERE year = %s
            GROUP BY month
            ORDER BY month
        ''', (year,))

    def get_by_employee(self, year: int = None, month: int = None) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by employee."""
        query = '''
            SELECT u.id, u.name, u.department, u.company, u.brand,
                   COUNT(*) as bonus_count,
                   COALESCE(SUM(b.bonus_days), 0) as total_days,
                   COALESCE(SUM(b.hours_free), 0) as total_hours,
                   COALESCE(SUM(b.bonus_net), 0) as total_bonus
            FROM hr.event_bonuses b
            LEFT JOIN public.users u ON u.id = b.user_id
            WHERE 1=1
        '''
        params = []
        if year:
            query += ' AND b.year = %s'
            params.append(year)
        if month:
            query += ' AND b.month = %s'
            params.append(month)
        query += ' GROUP BY u.id, u.name, u.department, u.company, u.brand ORDER BY total_bonus DESC'
        return self.query_all(query, params)

    def get_by_event(self, year: int = None, month: int = None) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by event."""
        query = '''
            SELECT e.id, e.name, e.start_date, e.end_date, e.company, e.brand,
                   b.year, b.month,
                   COUNT(*) as bonus_count,
                   COUNT(DISTINCT b.user_id) as employee_count,
                   COALESCE(SUM(b.bonus_days), 0) as total_days,
                   COALESCE(SUM(b.hours_free), 0) as total_hours,
                   COALESCE(SUM(b.bonus_net), 0) as total_bonus
            FROM hr.event_bonuses b
            JOIN hr.events e ON e.id = b.event_id
            WHERE 1=1
        '''
        params = []
        if year:
            query += ' AND b.year = %s'
            params.append(year)
        if month:
            query += ' AND b.month = %s'
            params.append(month)
        query += ' GROUP BY e.id, e.name, e.start_date, e.end_date, e.company, e.brand, b.year, b.month ORDER BY b.year DESC, b.month DESC, total_bonus DESC'
        return self.query_all(query, params)

    # ============== Bonus Types ==============

    def get_all_types(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all bonus types, including restricted employee name."""
        query = '''
            SELECT bt.*, u.name AS restricted_to_user_name
            FROM hr.bonus_types bt
            LEFT JOIN public.users u ON u.id = bt.restricted_to_user_id
        '''
        if active_only:
            query += ' WHERE bt.is_active = TRUE'
        query += ' ORDER BY bt.name'
        return self.query_all(query)

    def get_type_by_id(self, bonus_type_id: int) -> Optional[Dict[str, Any]]:
        """Get a single bonus type by ID."""
        return self.query_one('''
            SELECT bt.*, u.name AS restricted_to_user_name
            FROM hr.bonus_types bt
            LEFT JOIN public.users u ON u.id = bt.restricted_to_user_id
            WHERE bt.id = %s
        ''', (bonus_type_id,))

    def create_type(self, name: str, amount: float, days_per_amount: int = 1,
                    description: str = None, restricted_to_user_id: int = None) -> int:
        """Create a new bonus type. Returns the new bonus type ID."""
        result = self.execute('''
            INSERT INTO hr.bonus_types (name, amount, days_per_amount, description, restricted_to_user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, amount, days_per_amount, description, restricted_to_user_id), returning=True)
        return result['id']

    def update_type(self, bonus_type_id: int, name: str, amount: float,
                    days_per_amount: int = 1, description: str = None, is_active: bool = True,
                    restricted_to_user_id: int = None) -> bool:
        """Update a bonus type."""
        self.execute('''
            UPDATE hr.bonus_types
            SET name = %s, amount = %s, days_per_amount = %s, description = %s,
                is_active = %s, restricted_to_user_id = %s
            WHERE id = %s
        ''', (name, amount, days_per_amount, description, is_active, restricted_to_user_id, bonus_type_id))
        return True

    def delete_type(self, bonus_type_id: int) -> bool:
        """Soft delete a bonus type."""
        self.execute('UPDATE hr.bonus_types SET is_active = FALSE WHERE id = %s', (bonus_type_id,))
        return True
