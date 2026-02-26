"""CRM AI Tools — search clients, deals for the AI agent."""

import logging
from ..registry import tool_registry

logger = logging.getLogger('jarvis.ai_agent.tools.crm')


# ════════════════════════════════════════════════════════════════
# Search Clients
# ════════════════════════════════════════════════════════════════

def search_clients(params: dict, user_id: int) -> dict:
    """Search CRM clients by name, phone, email, type, date, with sorting."""
    from crm.repositories import ClientRepository
    repo = ClientRepository()
    rows, total = repo.search(
        name=params.get('name'),
        phone=params.get('phone'),
        email=params.get('email'),
        client_type=params.get('client_type'),
        responsible=params.get('responsible'),
        date_from=params.get('date_from'),
        date_to=params.get('date_to'),
        sort_by=params.get('sort_by'),
        sort_order=params.get('sort_order'),
        limit=min(params.get('limit', 20), 50),
    )
    return {
        'clients': [{
            'id': r['id'], 'name': r['display_name'],
            'type': r['client_type'], 'phone': r.get('phone'),
            'email': r.get('email'), 'city': r.get('city'),
            'responsible': r.get('responsible'),
            'sources': r.get('source_flags', {}),
            'created_at': str(r.get('created_at') or ''),
        } for r in rows],
        'total': total,
    }


tool_registry.register(
    name='search_clients',
    description='Search CRM clients by name, phone, email, type, or responsible person. '
                'Returns client list with contact info, source flags, and created_at date. '
                'Supports sorting by created_at to find oldest/newest clients.',
    input_schema={
        'type': 'object',
        'properties': {
            'name': {'type': 'string', 'description': 'Client name to search (partial match)'},
            'phone': {'type': 'string', 'description': 'Exact phone number'},
            'email': {'type': 'string', 'description': 'Email (partial match)'},
            'client_type': {'type': 'string', 'enum': ['person', 'company'],
                           'description': 'person = Persoana fizica, company = Persoana juridica'},
            'responsible': {'type': 'string', 'description': 'Responsible person name'},
            'date_from': {'type': 'string', 'description': 'Created after date (YYYY-MM-DD)'},
            'date_to': {'type': 'string', 'description': 'Created before date (YYYY-MM-DD)'},
            'sort_by': {'type': 'string', 'enum': ['created_at', 'updated_at', 'display_name'],
                       'description': 'Sort field (default: updated_at)'},
            'sort_order': {'type': 'string', 'enum': ['asc', 'desc'],
                          'description': 'Sort direction (default: desc). Use asc for oldest first.'},
            'limit': {'type': 'integer', 'description': 'Max results (default 20, max 50)'},
        },
    },
    handler=search_clients,
    permission='crm.access',
)


# ════════════════════════════════════════════════════════════════
# Get Client Details
# ════════════════════════════════════════════════════════════════

def get_client_details(params: dict, user_id: int) -> dict:
    """Get full client profile with associated deals."""
    from crm.repositories import ClientRepository, DealRepository
    client_id = params.get('client_id')
    if not client_id:
        return {'error': 'client_id is required'}

    client = ClientRepository().get_by_id(client_id)
    if not client:
        return {'error': 'Client not found'}

    deals, _ = DealRepository().search(client_id=client_id, limit=20)

    return {
        'client': {
            'id': client['id'], 'name': client['display_name'],
            'type': client['client_type'], 'phone': client.get('phone'),
            'email': client.get('email'), 'address': client.get('street'),
            'city': client.get('city'), 'responsible': client.get('responsible'),
            'sources': client.get('source_flags', {}),
            'created_at': str(client.get('created_at') or ''),
        },
        'deals': [{
            'id': d['id'], 'type': d['source'], 'brand': d.get('brand'),
            'model': d.get('model_name'), 'status': d.get('dossier_status'),
            'price': str(d.get('sale_price_net') or d.get('gw_gross_value') or ''),
            'date': str(d.get('contract_date') or ''),
        } for d in deals],
    }


tool_registry.register(
    name='get_client_details',
    description='Get full client profile including all associated car deals (NW/GW).',
    input_schema={
        'type': 'object',
        'properties': {
            'client_id': {'type': 'integer', 'description': 'Client ID'},
        },
        'required': ['client_id'],
    },
    handler=get_client_details,
    permission='crm.access',
)


# ════════════════════════════════════════════════════════════════
# Search Deals (Car Dossiers)
# ════════════════════════════════════════════════════════════════

def search_deals(params: dict, user_id: int) -> dict:
    """Search car sales dossiers (NW new cars + GW used cars)."""
    from crm.repositories import DealRepository
    repo = DealRepository()
    rows, total = repo.search(
        source=params.get('source'),
        brand=params.get('brand'),
        model=params.get('model'),
        buyer=params.get('buyer'),
        vin=params.get('vin'),
        status=params.get('status'),
        date_from=params.get('date_from'),
        date_to=params.get('date_to'),
        limit=min(params.get('limit', 20), 50),
    )
    return {
        'deals': [{
            'id': d['id'], 'type': d['source'], 'dossier': d.get('dossier_number'),
            'brand': d.get('brand'), 'model': d.get('model_name'),
            'status': d.get('dossier_status'), 'buyer': d.get('buyer_name'),
            'fuel': d.get('fuel_type'), 'color': d.get('color'),
            'vin': d.get('vin'),
            'price': str(d.get('sale_price_net') or d.get('gw_gross_value') or ''),
            'profit': str(d.get('gross_profit') or ''),
            'date': str(d.get('contract_date') or ''),
        } for d in rows],
        'total': total,
    }


tool_registry.register(
    name='search_deals',
    description='Search car sales dossiers. Includes both NW (new cars) and GW (used/second-hand cars). '
                'Search by brand, model, buyer name, VIN, status, date range, or type (nw/gw).',
    input_schema={
        'type': 'object',
        'properties': {
            'source': {'type': 'string', 'enum': ['nw', 'gw'],
                      'description': 'nw = new cars, gw = used/second-hand cars'},
            'brand': {'type': 'string', 'description': 'Brand name (VW, Audi, Mazda, Volvo, MG, Toyota, etc.)'},
            'model': {'type': 'string', 'description': 'Model name (partial match)'},
            'buyer': {'type': 'string', 'description': 'Buyer/client name (partial match)'},
            'vin': {'type': 'string', 'description': 'VIN / serie sasiu'},
            'status': {'type': 'string', 'description': 'Dossier status (Livrat, Comandat, Achizitionat, etc.)'},
            'date_from': {'type': 'string', 'description': 'Contract date from (YYYY-MM-DD)'},
            'date_to': {'type': 'string', 'description': 'Contract date to (YYYY-MM-DD)'},
            'limit': {'type': 'integer', 'description': 'Max results (default 20, max 50)'},
        },
    },
    handler=search_deals,
    permission='crm.access',
)


# ════════════════════════════════════════════════════════════════
# Top Clients (by deal value / deal count)
# ════════════════════════════════════════════════════════════════

def get_top_clients(params: dict, user_id: int) -> dict:
    """Get top N CRM clients ranked by total deal value or deal count."""
    from core.database import get_db, get_cursor, release_db
    limit = min(int(params.get('limit', 10)), 50)
    sort_by = params.get('sort_by', 'value')  # 'value' or 'count'

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        order_col = 'total_value' if sort_by == 'value' else 'deal_count'
        cursor.execute(f"""
            SELECT c.id, c.display_name, c.client_type, c.city,
                   c.responsible,
                   COUNT(d.id) as deal_count,
                   COALESCE(SUM(d.sale_price_net), 0) as total_value
            FROM crm_clients c
            JOIN crm_deals d ON d.client_id = c.id
            WHERE c.merged_into_id IS NULL
            GROUP BY c.id
            ORDER BY {order_col} DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        return {
            'clients': [{
                'id': r['id'],
                'name': r['display_name'],
                'type': r['client_type'],
                'city': r.get('city'),
                'responsible': r.get('responsible'),
                'deal_count': r['deal_count'],
                'total_value': float(r['total_value']),
            } for r in rows],
            'sort_by': sort_by,
            'total': len(rows),
        }
    finally:
        release_db(conn)


tool_registry.register(
    name='get_top_clients',
    description='Get top N CRM clients (car buyers/customers) ranked by total deal value or deal count. '
                'Use when the user asks "cel mai mare client", "top clients", "biggest customers", or '
                '"who buys the most cars?". '
                'NOTE: These are CRM clients (car buyers), NOT invoice suppliers. '
                'For invoice suppliers, use get_top_suppliers instead.',
    input_schema={
        'type': 'object',
        'properties': {
            'limit': {'type': 'integer', 'description': 'Number of clients to return (default 10, max 50)'},
            'sort_by': {
                'type': 'string',
                'enum': ['value', 'count'],
                'description': 'Rank by total deal value (default) or deal count',
            },
        },
    },
    handler=get_top_clients,
    permission='crm.access',
)


# ════════════════════════════════════════════════════════════════
# CRM Stats
# ════════════════════════════════════════════════════════════════

def get_crm_stats(params: dict, user_id: int) -> dict:
    """Get CRM database summary statistics."""
    from crm.repositories import ClientRepository, DealRepository
    return {
        'clients': ClientRepository().get_stats(),
        'deals': DealRepository().get_stats(),
    }


tool_registry.register(
    name='get_crm_stats',
    description='Get CRM database summary: total clients, deals (NW/GW), brand count.',
    input_schema={
        'type': 'object',
        'properties': {},
    },
    handler=get_crm_stats,
    permission='crm.access',
)
