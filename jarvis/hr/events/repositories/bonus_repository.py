"""Bonus Repository - Data access for event bonuses.

Handles all database operations for the hr.event_bonuses and hr.bonus_types tables.
"""
from typing import Optional, List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from database import get_db, get_cursor, release_db, dict_from_row


class BonusRepository:
    """Repository for event bonus data access operations."""

    # ============== Event Bonuses ==============

    def get_all(
        self,
        year: int = None,
        month: int = None,
        employee_id: int = None,
        event_id: int = None
    ) -> List[Dict[str, Any]]:
        """Get event bonuses with optional filters.

        Args:
            year: Filter by year
            month: Filter by month
            employee_id: Filter by employee
            event_id: Filter by event

        Returns:
            List of bonus dictionaries
        """
        conn = get_db()
        cursor = get_cursor(conn)

        query = '''
            SELECT b.*, u.name as employee_name, u.department, u.brand, u.company,
                   ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
                   creator.name as created_by_name,
                   b.employee_id as effective_employee_id
            FROM hr.event_bonuses b
            LEFT JOIN public.users u ON u.id = b.employee_id
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
            query += ' AND b.employee_id = %s'
            params.append(employee_id)
        if event_id:
            query += ' AND b.event_id = %s'
            params.append(event_id)

        query += ' ORDER BY b.year DESC, b.month DESC, u.name'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        release_db(conn)
        return [dict_from_row(row) for row in rows]

    def get_by_id(self, bonus_id: int) -> Optional[Dict[str, Any]]:
        """Get a single event bonus by ID.

        Args:
            bonus_id: The bonus ID

        Returns:
            Bonus dict or None if not found
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT b.*, u.name as employee_name, u.department, u.brand, u.company,
                   ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
                   b.employee_id as effective_employee_id
            FROM hr.event_bonuses b
            LEFT JOIN public.users u ON u.id = b.employee_id
            JOIN hr.events ev ON b.event_id = ev.id
            WHERE b.id = %s
        ''', (bonus_id,))
        row = cursor.fetchone()
        release_db(conn)
        return dict_from_row(row) if row else None

    def create(
        self,
        employee_id: int,
        event_id: int,
        year: int,
        month: int,
        participation_start: str = None,
        participation_end: str = None,
        bonus_days: int = None,
        hours_free: float = None,
        bonus_net: float = None,
        details: str = None,
        allocation_month: int = None,
        created_by: int = None
    ) -> int:
        """Create a new event bonus record.

        Args:
            employee_id: The employee/user ID
            event_id: The event ID
            year: Bonus year
            month: Bonus month
            participation_start: Start date of participation
            participation_end: End date of participation
            bonus_days: Number of bonus days
            hours_free: Hours free
            bonus_net: Net bonus amount
            details: Additional details
            allocation_month: Month for allocation
            created_by: User ID who created the bonus

        Returns:
            The new bonus ID
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            INSERT INTO hr.event_bonuses
            (employee_id, event_id, year, month, participation_start, participation_end,
             bonus_days, hours_free, bonus_net, details, allocation_month, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (employee_id, event_id, year, month, participation_start, participation_end,
              bonus_days, hours_free, bonus_net, details, allocation_month, created_by))
        bonus_id = cursor.fetchone()['id']
        conn.commit()
        release_db(conn)
        return bonus_id

    def create_bulk(self, bonuses: List[Dict[str, Any]], created_by: int = None) -> List[int]:
        """Bulk create event bonus records.

        Args:
            bonuses: List of bonus dictionaries
            created_by: User ID who created the bonuses

        Returns:
            List of new bonus IDs
        """
        conn = get_db()
        cursor = get_cursor(conn)

        created_ids = []
        for b in bonuses:
            cursor.execute('''
                INSERT INTO hr.event_bonuses
                (employee_id, event_id, year, month, participation_start, participation_end,
                 bonus_days, hours_free, bonus_net, details, allocation_month, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (b['employee_id'], b['event_id'], b['year'], b['month'],
                  b.get('participation_start'), b.get('participation_end'),
                  b.get('bonus_days'), b.get('hours_free'), b.get('bonus_net'),
                  b.get('details'), b.get('allocation_month'), created_by))
            created_ids.append(cursor.fetchone()['id'])

        conn.commit()
        release_db(conn)
        return created_ids

    def update(
        self,
        bonus_id: int,
        employee_id: int,
        event_id: int,
        year: int,
        month: int,
        participation_start: str = None,
        participation_end: str = None,
        bonus_days: int = None,
        hours_free: float = None,
        bonus_net: float = None,
        details: str = None,
        allocation_month: int = None
    ) -> bool:
        """Update an event bonus record.

        Args:
            bonus_id: The bonus ID
            employee_id: The employee/user ID
            event_id: The event ID
            year: Bonus year
            month: Bonus month
            participation_start: Start date of participation
            participation_end: End date of participation
            bonus_days: Number of bonus days
            hours_free: Hours free
            bonus_net: Net bonus amount
            details: Additional details
            allocation_month: Month for allocation

        Returns:
            True if successful
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE hr.event_bonuses
            SET employee_id = %s, event_id = %s, year = %s, month = %s,
                participation_start = %s, participation_end = %s, bonus_days = %s,
                hours_free = %s, bonus_net = %s, details = %s, allocation_month = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (employee_id, event_id, year, month, participation_start, participation_end,
              bonus_days, hours_free, bonus_net, details, allocation_month, bonus_id))
        conn.commit()
        release_db(conn)
        return True

    def delete(self, bonus_id: int) -> bool:
        """Delete an event bonus record.

        Args:
            bonus_id: The bonus ID

        Returns:
            True if successful
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('DELETE FROM hr.event_bonuses WHERE id = %s', (bonus_id,))
        conn.commit()
        release_db(conn)
        return True

    # ============== Summary/Stats ==============

    def get_summary(self, year: int = None) -> Dict[str, Any]:
        """Get summary stats for event bonuses.

        Args:
            year: Filter by year

        Returns:
            Summary statistics dictionary
        """
        conn = get_db()
        cursor = get_cursor(conn)

        query = '''
            SELECT
                COUNT(DISTINCT b.employee_id) as total_employees,
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

        cursor.execute(query, params)
        row = cursor.fetchone()
        release_db(conn)
        return dict_from_row(row)

    def get_by_month(self, year: int) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by month for a year.

        Args:
            year: The year to filter by

        Returns:
            List of monthly totals
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT month, COUNT(*) as count, SUM(bonus_net) as total
            FROM hr.event_bonuses
            WHERE year = %s
            GROUP BY month
            ORDER BY month
        ''', (year,))
        rows = cursor.fetchall()
        release_db(conn)
        return [dict_from_row(row) for row in rows]

    def get_by_employee(self, year: int = None, month: int = None) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by employee.

        Args:
            year: Filter by year
            month: Filter by month

        Returns:
            List of employee bonus totals
        """
        conn = get_db()
        cursor = get_cursor(conn)

        query = '''
            SELECT u.id, u.name, u.department, u.company, u.brand,
                   COUNT(*) as bonus_count,
                   COALESCE(SUM(b.bonus_days), 0) as total_days,
                   COALESCE(SUM(b.hours_free), 0) as total_hours,
                   COALESCE(SUM(b.bonus_net), 0) as total_bonus
            FROM hr.event_bonuses b
            LEFT JOIN public.users u ON u.id = b.employee_id
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

        cursor.execute(query, params)
        rows = cursor.fetchall()
        release_db(conn)
        return [dict_from_row(row) for row in rows]

    def get_by_event(self, year: int = None, month: int = None) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by event.

        Args:
            year: Filter by year
            month: Filter by month

        Returns:
            List of event bonus totals
        """
        conn = get_db()
        cursor = get_cursor(conn)

        query = '''
            SELECT e.id, e.name, e.start_date, e.end_date, e.company, e.brand,
                   b.year, b.month,
                   COUNT(*) as bonus_count,
                   COUNT(DISTINCT b.employee_id) as employee_count,
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

        cursor.execute(query, params)
        rows = cursor.fetchall()
        release_db(conn)
        return [dict_from_row(row) for row in rows]

    # ============== Bonus Types ==============

    def get_all_types(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all bonus types.

        Args:
            active_only: If True, only return active types

        Returns:
            List of bonus type dictionaries
        """
        conn = get_db()
        cursor = get_cursor(conn)

        query = 'SELECT * FROM hr.bonus_types'
        if active_only:
            query += ' WHERE is_active = TRUE'
        query += ' ORDER BY name'

        cursor.execute(query)
        rows = cursor.fetchall()
        release_db(conn)
        return [dict_from_row(row) for row in rows]

    def get_type_by_id(self, bonus_type_id: int) -> Optional[Dict[str, Any]]:
        """Get a single bonus type by ID.

        Args:
            bonus_type_id: The bonus type ID

        Returns:
            Bonus type dict or None if not found
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('SELECT * FROM hr.bonus_types WHERE id = %s', (bonus_type_id,))
        row = cursor.fetchone()
        release_db(conn)
        return dict_from_row(row) if row else None

    def create_type(
        self,
        name: str,
        amount: float,
        days_per_amount: int = 1,
        description: str = None
    ) -> int:
        """Create a new bonus type.

        Args:
            name: Bonus type name
            amount: Amount per bonus
            days_per_amount: Days per amount
            description: Description

        Returns:
            The new bonus type ID
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            INSERT INTO hr.bonus_types (name, amount, days_per_amount, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (name, amount, days_per_amount, description))
        bonus_type_id = cursor.fetchone()['id']
        conn.commit()
        release_db(conn)
        return bonus_type_id

    def update_type(
        self,
        bonus_type_id: int,
        name: str,
        amount: float,
        days_per_amount: int = 1,
        description: str = None,
        is_active: bool = True
    ) -> bool:
        """Update a bonus type.

        Args:
            bonus_type_id: The bonus type ID
            name: Bonus type name
            amount: Amount per bonus
            days_per_amount: Days per amount
            description: Description
            is_active: Whether type is active

        Returns:
            True if successful
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE hr.bonus_types
            SET name = %s, amount = %s, days_per_amount = %s, description = %s, is_active = %s
            WHERE id = %s
        ''', (name, amount, days_per_amount, description, is_active, bonus_type_id))
        conn.commit()
        release_db(conn)
        return True

    def delete_type(self, bonus_type_id: int) -> bool:
        """Soft delete a bonus type.

        Args:
            bonus_type_id: The bonus type ID

        Returns:
            True if successful
        """
        conn = get_db()
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE hr.bonus_types SET is_active = FALSE WHERE id = %s
        ''', (bonus_type_id,))
        conn.commit()
        release_db(conn)
        return True
