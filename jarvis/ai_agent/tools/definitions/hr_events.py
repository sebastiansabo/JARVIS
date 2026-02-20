"""HR events and bonuses query tools."""

from ai_agent.tools.registry import tool_registry
from core.database import get_db, get_cursor, release_db


def search_hr_events(params: dict, user_id: int) -> dict:
    """Search HR events by name, company, brand, or date range."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        conditions = ["1=1"]
        values = []

        if params.get('name'):
            conditions.append("e.name ILIKE %s")
            values.append(f"%{params['name']}%")

        if params.get('company'):
            conditions.append("e.company ILIKE %s")
            values.append(f"%{params['company']}%")

        if params.get('brand'):
            conditions.append("e.brand ILIKE %s")
            values.append(f"%{params['brand']}%")

        if params.get('date_from'):
            conditions.append("e.start_date >= %s")
            values.append(params['date_from'])

        if params.get('date_to'):
            conditions.append("e.end_date <= %s")
            values.append(params['date_to'])

        if params.get('year'):
            conditions.append("EXTRACT(YEAR FROM e.start_date) = %s")
            values.append(int(params['year']))

        limit = min(int(params.get('limit', 25)), 50)
        where = " AND ".join(conditions)

        cursor.execute(f"""
            SELECT e.id, e.name, e.start_date, e.end_date,
                   e.company, e.brand, e.description,
                   COUNT(b.id) AS bonus_count,
                   COALESCE(SUM(b.bonus_net), 0) AS total_bonus_net,
                   COALESCE(SUM(b.bonus_days), 0) AS total_bonus_days
            FROM hr.events e
            LEFT JOIN hr.event_bonuses b ON b.event_id = e.id
            WHERE {where}
            GROUP BY e.id
            ORDER BY e.start_date DESC
            LIMIT %s
        """, values + [limit])

        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for k in ('start_date', 'end_date'):
                if r.get(k):
                    r[k] = str(r[k])
            for k in ('total_bonus_net', 'total_bonus_days'):
                if r.get(k):
                    r[k] = float(r[k])

        return {'events': rows, 'count': len(rows)}
    finally:
        release_db(conn)


def get_hr_event_details(params: dict, user_id: int) -> dict:
    """Get full details of a specific HR event including bonuses."""
    event_id = params.get('event_id')
    if not event_id:
        return {'error': 'event_id is required'}

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute("""
            SELECT e.id, e.name, e.start_date, e.end_date,
                   e.company, e.brand, e.description,
                   u.name AS created_by_name
            FROM hr.events e
            LEFT JOIN users u ON u.id = e.created_by
            WHERE e.id = %s
        """, [event_id])
        event = cursor.fetchone()
        if not event:
            return {'error': f'Event {event_id} not found'}

        result = dict(event)
        for k in ('start_date', 'end_date'):
            if result.get(k):
                result[k] = str(result[k])

        # Get bonuses for this event
        cursor.execute("""
            SELECT b.id, u.name AS employee, b.year, b.month,
                   b.bonus_days, b.hours_free, b.bonus_net,
                   b.participation_start, b.participation_end, b.details
            FROM hr.event_bonuses b
            JOIN users u ON u.id = b.user_id
            WHERE b.event_id = %s
            ORDER BY u.name
        """, [event_id])
        result['bonuses'] = [dict(r) for r in cursor.fetchall()]
        for b in result['bonuses']:
            for k in ('participation_start', 'participation_end'):
                if b.get(k):
                    b[k] = str(b[k])
            for k in ('bonus_days', 'bonus_net'):
                if b.get(k):
                    b[k] = float(b[k])

        return result
    finally:
        release_db(conn)


def search_bonuses(params: dict, user_id: int) -> dict:
    """Search bonuses by employee, event, year, or month."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        conditions = ["1=1"]
        values = []

        if params.get('employee'):
            conditions.append("u.name ILIKE %s")
            values.append(f"%{params['employee']}%")

        if params.get('event'):
            conditions.append("e.name ILIKE %s")
            values.append(f"%{params['event']}%")

        if params.get('year'):
            conditions.append("b.year = %s")
            values.append(int(params['year']))

        if params.get('month'):
            conditions.append("b.month = %s")
            values.append(int(params['month']))

        if params.get('company'):
            conditions.append("e.company ILIKE %s")
            values.append(f"%{params['company']}%")

        limit = min(int(params.get('limit', 25)), 50)
        where = " AND ".join(conditions)

        cursor.execute(f"""
            SELECT b.id, u.name AS employee, e.name AS event_name,
                   b.year, b.month, b.bonus_days, b.hours_free,
                   b.bonus_net, b.participation_start, b.participation_end,
                   e.company, e.brand
            FROM hr.event_bonuses b
            JOIN users u ON u.id = b.user_id
            JOIN hr.events e ON e.id = b.event_id
            WHERE {where}
            ORDER BY b.year DESC, b.month DESC, u.name
            LIMIT %s
        """, values + [limit])

        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for k in ('participation_start', 'participation_end'):
                if r.get(k):
                    r[k] = str(r[k])
            for k in ('bonus_days', 'bonus_net'):
                if r.get(k):
                    r[k] = float(r[k])

        # Summary
        total_net = sum(r.get('bonus_net', 0) or 0 for r in rows)
        total_days = sum(r.get('bonus_days', 0) or 0 for r in rows)

        return {
            'bonuses': rows,
            'count': len(rows),
            'total_bonus_net': total_net,
            'total_bonus_days': total_days,
        }
    finally:
        release_db(conn)


# Register tools
tool_registry.register(
    name='search_hr_events',
    description=(
        'Search HR events (company events, team activities, dealer open doors, etc). '
        'Filter by name, company, brand, date range, or year.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'name': {'type': 'string', 'description': 'Event name (partial match)'},
            'company': {'type': 'string', 'description': 'Company name (partial match)'},
            'brand': {'type': 'string', 'description': 'Brand name (partial match)'},
            'date_from': {'type': 'string', 'description': 'Start date (YYYY-MM-DD)'},
            'date_to': {'type': 'string', 'description': 'End date (YYYY-MM-DD)'},
            'year': {'type': 'integer', 'description': 'Filter by year (e.g. 2025, 2026)'},
            'limit': {'type': 'integer', 'description': 'Max results (default 25, max 50)'},
        },
    },
    handler=search_hr_events,
    permission='hr.view',
)

tool_registry.register(
    name='get_hr_event_details',
    description='Get full details of a specific HR event including all employee bonuses.',
    input_schema={
        'type': 'object',
        'properties': {
            'event_id': {'type': 'integer', 'description': 'The HR event ID'},
        },
        'required': ['event_id'],
    },
    handler=get_hr_event_details,
    permission='hr.view',
)

tool_registry.register(
    name='search_bonuses',
    description=(
        'Search employee bonuses across HR events. '
        'Filter by employee name, event name, year, month, or company. '
        'Returns individual bonus records with totals.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'employee': {'type': 'string', 'description': 'Employee name (partial match)'},
            'event': {'type': 'string', 'description': 'Event name (partial match)'},
            'year': {'type': 'integer', 'description': 'Bonus year'},
            'month': {'type': 'integer', 'description': 'Bonus month (1-12)'},
            'company': {'type': 'string', 'description': 'Company name (partial match)'},
            'limit': {'type': 'integer', 'description': 'Max results (default 25, max 50)'},
        },
    },
    handler=search_bonuses,
    permission='hr.view',
)
