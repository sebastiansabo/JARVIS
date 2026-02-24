"""Invoice search and lookup tools."""

from ai_agent.tools.registry import tool_registry
from core.database import get_db, get_cursor, release_db


def search_invoices(params: dict, user_id: int) -> dict:
    """Search invoices by supplier, date range, amount range, or status."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        conditions = ["1=1"]
        values = []

        if params.get('supplier'):
            conditions.append("i.supplier ILIKE %s")
            values.append(f"%{params['supplier']}%")

        if params.get('invoice_number'):
            conditions.append("i.invoice_number ILIKE %s")
            values.append(f"%{params['invoice_number']}%")

        if params.get('status'):
            conditions.append("i.status = %s")
            values.append(params['status'])

        if params.get('date_from'):
            conditions.append("i.invoice_date >= %s")
            values.append(params['date_from'])

        if params.get('date_to'):
            conditions.append("i.invoice_date <= %s")
            values.append(params['date_to'])

        if params.get('min_amount'):
            conditions.append("i.invoice_value >= %s")
            values.append(float(params['min_amount']))

        if params.get('max_amount'):
            conditions.append("i.invoice_value <= %s")
            values.append(float(params['max_amount']))

        if params.get('company'):
            conditions.append("""
                EXISTS (SELECT 1 FROM allocations a
                        WHERE a.invoice_id = i.id AND a.company ILIKE %s)
            """)
            values.append(f"%{params['company']}%")

        limit = min(int(params.get('limit', 20)), 50)
        where = " AND ".join(conditions)

        cursor.execute(f"""
            SELECT i.id, i.supplier, i.invoice_number, i.invoice_date,
                   i.invoice_value, i.currency, i.status, i.invoice_type
            FROM invoices i
            WHERE {where}
            ORDER BY i.invoice_date DESC
            LIMIT %s
        """, values + [limit])

        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            if r.get('invoice_date'):
                r['invoice_date'] = str(r['invoice_date'])
            if r.get('invoice_value'):
                r['invoice_value'] = float(r['invoice_value'])

        return {'invoices': rows, 'count': len(rows)}
    finally:
        release_db(conn)


def get_invoice_details(params: dict, user_id: int) -> dict:
    """Get full details of a specific invoice including allocations."""
    invoice_id = params.get('invoice_id')
    if not invoice_id:
        return {'error': 'invoice_id is required'}

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute("""
            SELECT i.id, i.supplier, i.supplier_vat, i.invoice_number,
                   i.invoice_date, i.invoice_value, i.currency, i.status,
                   i.invoice_type, i.description
            FROM invoices i WHERE i.id = %s
        """, [invoice_id])
        inv = cursor.fetchone()
        if not inv:
            return {'error': f'Invoice {invoice_id} not found'}

        result = dict(inv)
        if result.get('invoice_date'):
            result['invoice_date'] = str(result['invoice_date'])
        if result.get('invoice_value'):
            result['invoice_value'] = float(result['invoice_value'])

        # Get allocations
        cursor.execute("""
            SELECT company, brand, department, subdepartment,
                   percentage, value_ron
            FROM allocations WHERE invoice_id = %s
            ORDER BY company, department
        """, [invoice_id])
        allocs = [dict(r) for r in cursor.fetchall()]
        for a in allocs:
            if a.get('value_ron'):
                a['value_ron'] = float(a['value_ron'])
            if a.get('percentage'):
                a['percentage'] = float(a['percentage'])

        result['allocations'] = allocs
        if not allocs:
            result['allocation_note'] = 'This invoice has no allocations yet (not assigned to any company/department).'

        return result
    finally:
        release_db(conn)


# Register tools
tool_registry.register(
    name='search_invoices',
    description=(
        'Search invoices in the JARVIS database. Use when the user asks about invoices, '
        'supplier spending, invoice lists, or wants to find specific invoices. '
        'Returns: {invoices: [{id, supplier, invoice_number, invoice_date, invoice_value, currency, status, invoice_type}], count}. '
        'Example: {supplier: "Porsche", date_from: "2026-01-01", status: "pending"}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'supplier': {'type': 'string', 'description': 'Supplier name (partial match)'},
            'invoice_number': {'type': 'string', 'description': 'Invoice number (partial match)'},
            'status': {'type': 'string', 'description': 'Invoice status (e.g. pending, approved, paid)'},
            'date_from': {'type': 'string', 'description': 'Start date (YYYY-MM-DD)'},
            'date_to': {'type': 'string', 'description': 'End date (YYYY-MM-DD)'},
            'min_amount': {'type': 'number', 'description': 'Minimum invoice value'},
            'max_amount': {'type': 'number', 'description': 'Maximum invoice value'},
            'company': {'type': 'string', 'description': 'Company name (partial match on allocations)'},
            'limit': {'type': 'integer', 'description': 'Max results (default 20, max 50)'},
        },
    },
    handler=search_invoices,
    permission='accounting.view',
)

tool_registry.register(
    name='get_invoice_details',
    description=(
        'Get full details of a specific invoice by ID, including allocations to companies/departments/brands. '
        'Use when the user asks about a specific invoice or its allocation breakdown. '
        'Returns: {id, supplier, supplier_vat, invoice_number, invoice_date, invoice_value, currency, status, description, allocations: [{company, brand, department, percentage, value_ron}]}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'invoice_id': {'type': 'integer', 'description': 'The invoice ID'},
        },
        'required': ['invoice_id'],
    },
    handler=get_invoice_details,
    permission='accounting.view',
)
