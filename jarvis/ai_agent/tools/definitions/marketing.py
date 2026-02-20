"""Marketing project query tools."""

from ai_agent.tools.registry import tool_registry
from core.database import get_db, get_cursor, release_db


def search_marketing_projects(params: dict, user_id: int) -> dict:
    """Search marketing projects by name, status, type, or company."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        conditions = ["1=1"]
        values = []

        if params.get('name'):
            conditions.append("p.name ILIKE %s")
            values.append(f"%{params['name']}%")

        if params.get('status'):
            conditions.append("p.status = %s")
            values.append(params['status'])

        if params.get('type'):
            conditions.append("p.type = %s")
            values.append(params['type'])

        if params.get('company'):
            # company_ids is INTEGER[] — check array overlap
            conditions.append("""
                EXISTS (SELECT 1 FROM company_structure cs
                        WHERE cs.id = ANY(p.company_ids) AND cs.name ILIKE %s)
            """)
            values.append(f"%{params['company']}%")

        if params.get('channel'):
            conditions.append("%s = ANY(p.channel_mix)")
            values.append(params['channel'])

        limit = min(int(params.get('limit', 25)), 50)
        where = " AND ".join(conditions)

        cursor.execute(f"""
            SELECT p.id, p.name, p.status, p.type, p.start_date, p.end_date,
                   p.description, p.channel_mix,
                   u.name AS owner,
                   COALESCE(SUM(bl.amount), 0) AS total_budget,
                   COALESCE(SUM(bt.amount), 0) AS total_spent,
                   COUNT(DISTINCT k.id) AS kpi_count
            FROM mkt_projects p
            LEFT JOIN users u ON u.id = p.owner_id
            LEFT JOIN mkt_budget_lines bl ON bl.project_id = p.id
            LEFT JOIN mkt_budget_transactions bt ON bt.budget_line_id = bl.id
            LEFT JOIN mkt_project_kpis k ON k.project_id = p.id
            WHERE {where}
            GROUP BY p.id, u.name
            ORDER BY p.created_at DESC
            LIMIT %s
        """, values + [limit])

        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for k in ('start_date', 'end_date'):
                if r.get(k):
                    r[k] = str(r[k])
            for k in ('total_budget', 'total_spent'):
                if r.get(k):
                    r[k] = float(r[k])

        return {'projects': rows, 'count': len(rows)}
    finally:
        release_db(conn)


def get_marketing_project_details(params: dict, user_id: int) -> dict:
    """Get full details of a marketing project."""
    project_id = params.get('project_id')
    if not project_id:
        return {'error': 'project_id is required'}

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute("""
            SELECT p.id, p.name, p.status, p.type, p.start_date, p.end_date,
                   p.description, p.channel_mix, p.company_ids, p.brand_ids,
                   p.department_ids, u.name AS owner
            FROM mkt_projects p
            LEFT JOIN users u ON u.id = p.owner_id
            WHERE p.id = %s
        """, [project_id])
        project = cursor.fetchone()
        if not project:
            return {'error': f'Project {project_id} not found'}

        result = dict(project)
        for k in ('start_date', 'end_date'):
            if result.get(k):
                result[k] = str(result[k])

        # Budget lines
        cursor.execute("""
            SELECT bl.id, bl.name, bl.category, bl.amount, bl.currency,
                   COALESCE(SUM(bt.amount), 0) AS spent
            FROM mkt_budget_lines bl
            LEFT JOIN mkt_budget_transactions bt ON bt.budget_line_id = bl.id
            WHERE bl.project_id = %s
            GROUP BY bl.id
            ORDER BY bl.name
        """, [project_id])
        result['budget_lines'] = [dict(r) for r in cursor.fetchall()]
        for bl in result['budget_lines']:
            for k in ('amount', 'spent'):
                if bl.get(k):
                    bl[k] = float(bl[k])

        # KPIs
        cursor.execute("""
            SELECT k.id, d.name AS kpi_name, d.category, k.target_value,
                   k.current_value, k.unit
            FROM mkt_project_kpis k
            JOIN mkt_kpi_definitions d ON d.id = k.kpi_definition_id
            WHERE k.project_id = %s
            ORDER BY d.category, d.name
        """, [project_id])
        result['kpis'] = [dict(r) for r in cursor.fetchall()]
        for k in result['kpis']:
            for f in ('target_value', 'current_value'):
                if k.get(f):
                    k[f] = float(k[f])

        # Team members
        cursor.execute("""
            SELECT u.name, m.role
            FROM mkt_project_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.project_id = %s
            ORDER BY m.role, u.name
        """, [project_id])
        result['team'] = [dict(r) for r in cursor.fetchall()]

        return result
    finally:
        release_db(conn)


# Register tools
tool_registry.register(
    name='search_marketing_projects',
    description=(
        'Search marketing projects. Filter by project name, status '
        '(draft/pending/active/paused/completed), type, company, or channel.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'name': {'type': 'string', 'description': 'Project name (partial match)'},
            'status': {
                'type': 'string',
                'enum': ['draft', 'pending', 'active', 'paused', 'completed'],
                'description': 'Project status',
            },
            'type': {'type': 'string', 'description': 'Project type'},
            'company': {'type': 'string', 'description': 'Company name (partial match)'},
            'channel': {'type': 'string', 'description': 'Marketing channel (e.g. social_media, events)'},
            'limit': {'type': 'integer', 'description': 'Max results (default 25, max 50)'},
        },
    },
    handler=search_marketing_projects,
    permission='marketing.view',
)

tool_registry.register(
    name='get_marketing_project_details',
    description=(
        'Get full details of a specific marketing project including budget lines, '
        'spending, KPIs, and team members.'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'project_id': {'type': 'integer', 'description': 'The marketing project ID'},
        },
        'required': ['project_id'],
    },
    handler=get_marketing_project_details,
    permission='marketing.view',
)
