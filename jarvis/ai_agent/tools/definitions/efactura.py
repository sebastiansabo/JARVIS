"""e-Factura query tools."""

from ai_agent.tools.registry import tool_registry
from ai_agent.services.analytics_service import AnalyticsService
from core.database import get_db, get_cursor, release_db

_analytics = AnalyticsService()


def get_efactura_summary(params: dict, user_id: int) -> dict:
    """Get e-Factura backlog summary (unallocated, hidden, allocated counts)."""
    return _analytics.get_efactura_summary()


def search_efactura(params: dict, user_id: int) -> dict:
    """Search e-Factura invoices."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        conditions = ["1=1"]
        values = []

        if params.get('supplier'):
            conditions.append("partner_name ILIKE %s")
            values.append(f"%{params['supplier']}%")

        if params.get('status'):
            conditions.append("allocation_status = %s")
            values.append(params['status'])

        if params.get('direction'):
            conditions.append("direction = %s")
            values.append(params['direction'])

        if params.get('date_from'):
            conditions.append("issue_date >= %s")
            values.append(params['date_from'])

        if params.get('date_to'):
            conditions.append("issue_date <= %s")
            values.append(params['date_to'])

        limit = min(int(params.get('limit', 20)), 50)
        where = " AND ".join(conditions)

        cursor.execute(f"""
            SELECT id, partner_name, partner_cif, invoice_number,
                   issue_date, total_amount, currency, direction,
                   allocation_status
            FROM efactura_invoices
            WHERE {where}
            ORDER BY issue_date DESC
            LIMIT %s
        """, values + [limit])

        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            if r.get('issue_date'):
                r['issue_date'] = str(r['issue_date'])
            if r.get('total_amount'):
                r['total_amount'] = float(r['total_amount'])

        return {'efactura_invoices': rows, 'count': len(rows)}
    finally:
        release_db(conn)


# Register tools
tool_registry.register(
    name='get_efactura_summary',
    description=(
        'Get e-Factura (ANAF) backlog overview: counts and totals for unallocated, hidden, and allocated electronic invoices. '
        'Use when the user asks about e-Factura status, ANAF backlog, or "câte e-facturi avem nealocate?". '
        'Returns: {by_company: [{company, direction, status, count, total}], totals: {unallocated, hidden, allocated}}. '
        'Takes no parameters — returns full summary.'
    ),
    input_schema={'type': 'object', 'properties': {}},
    handler=get_efactura_summary,
    permission='accounting.view',
)

tool_registry.register(
    name='search_efactura',
    description=(
        'Search individual e-Factura invoices from ANAF. '
        'Use when the user asks about specific e-Factura invoices, unallocated ANAF invoices, or invoices from a specific supplier via ANAF. '
        'Returns: {efactura_invoices: [{id, partner_name, partner_cif, invoice_number, issue_date, total_amount, currency, direction, allocation_status}], count}. '
        'Example: {supplier: "OMV", status: "unallocated", date_from: "2026-01-01"}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'supplier': {'type': 'string', 'description': 'Supplier/partner name (partial match)'},
            'status': {
                'type': 'string',
                'enum': ['unallocated', 'hidden', 'allocated'],
                'description': 'Allocation status',
            },
            'direction': {
                'type': 'string',
                'enum': ['sent', 'received'],
                'description': 'Invoice direction',
            },
            'date_from': {'type': 'string', 'description': 'Start date (YYYY-MM-DD)'},
            'date_to': {'type': 'string', 'description': 'End date (YYYY-MM-DD)'},
            'limit': {'type': 'integer', 'description': 'Max results (default 20, max 50)'},
        },
    },
    handler=search_efactura,
    permission='accounting.view',
)
