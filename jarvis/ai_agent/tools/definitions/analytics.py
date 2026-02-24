"""Analytics and summary tools — wrappers around AnalyticsService."""

from ai_agent.tools.registry import tool_registry
from ai_agent.services.analytics_service import AnalyticsService

_analytics = AnalyticsService()


def get_invoice_summary(params: dict, user_id: int) -> dict:
    """Get invoice allocation summary grouped by a dimension."""
    return _analytics.get_invoice_summary(
        group_by=params.get('group_by', 'company'),
        company=params.get('company'),
        department=params.get('department'),
        brand=params.get('brand'),
        supplier=params.get('supplier'),
        start_date=params.get('start_date'),
        end_date=params.get('end_date'),
    )


def get_monthly_trend(params: dict, user_id: int) -> dict:
    """Get monthly spending trend."""
    return _analytics.get_monthly_trend(
        company=params.get('company'),
        department=params.get('department'),
        brand=params.get('brand'),
        supplier=params.get('supplier'),
        start_date=params.get('start_date'),
        end_date=params.get('end_date'),
    )


def get_top_suppliers(params: dict, user_id: int) -> dict:
    """Get top N suppliers by total spend."""
    return _analytics.get_top_suppliers(
        limit=min(int(params.get('limit', 10)), 50),
        company=params.get('company'),
        department=params.get('department'),
        brand=params.get('brand'),
        start_date=params.get('start_date'),
        end_date=params.get('end_date'),
    )


def get_transaction_summary(params: dict, user_id: int) -> dict:
    """Get bank transaction summary."""
    return _analytics.get_transaction_summary(
        company_cui=params.get('company_cui'),
        supplier=params.get('supplier'),
        date_from=params.get('date_from'),
        date_to=params.get('date_to'),
    )


# Register tools
tool_registry.register(
    name='get_invoice_summary',
    description=(
        'Get aggregated invoice totals grouped by company, department, brand, or supplier. '
        'Use when the user asks "how much did we spend?", "total invoices by company", or any spending summary. '
        'Returns: {summary: [{name, total_ron, total_eur, invoice_count}], grand_total_ron, grand_total_eur}. '
        'Example: {group_by: "supplier", start_date: "2026-01-01", company: "Autoworld"}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'group_by': {
                'type': 'string',
                'enum': ['company', 'department', 'brand', 'supplier'],
                'description': 'Dimension to group by (default: company)',
            },
            'company': {'type': 'string', 'description': 'Filter by company name'},
            'department': {'type': 'string', 'description': 'Filter by department'},
            'brand': {'type': 'string', 'description': 'Filter by brand'},
            'supplier': {'type': 'string', 'description': 'Filter by supplier'},
            'start_date': {'type': 'string', 'description': 'Start date (YYYY-MM-DD)'},
            'end_date': {'type': 'string', 'description': 'End date (YYYY-MM-DD)'},
        },
    },
    handler=get_invoice_summary,
    permission='accounting.view',
)

tool_registry.register(
    name='get_monthly_trend',
    description=(
        'Get monthly invoice spending trend over time. '
        'Use when the user asks about spending trends, month-by-month analysis, or "how has spending changed?". '
        'Returns: {months: [{month, total_ron, total_eur, invoice_count}]}. '
        'Example: {company: "Autoworld Premium", start_date: "2025-01-01", end_date: "2025-12-31"}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'company': {'type': 'string', 'description': 'Filter by company name'},
            'department': {'type': 'string', 'description': 'Filter by department'},
            'brand': {'type': 'string', 'description': 'Filter by brand'},
            'supplier': {'type': 'string', 'description': 'Filter by supplier'},
            'start_date': {'type': 'string', 'description': 'Start date (YYYY-MM-DD)'},
            'end_date': {'type': 'string', 'description': 'End date (YYYY-MM-DD)'},
        },
    },
    handler=get_monthly_trend,
    permission='accounting.view',
)

tool_registry.register(
    name='get_top_suppliers',
    description=(
        'Get the top N suppliers ranked by total spending (in RON). '
        'Use when the user asks "top suppliers", "biggest vendors", "who do we spend the most with?". '
        'Returns: {suppliers: [{supplier, total_ron, invoice_count}]}. '
        'Example: {limit: 5, company: "Autoworld", start_date: "2026-01-01"}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'limit': {'type': 'integer', 'description': 'Number of suppliers to return (default 10, max 50)'},
            'company': {'type': 'string', 'description': 'Filter by company name'},
            'department': {'type': 'string', 'description': 'Filter by department'},
            'brand': {'type': 'string', 'description': 'Filter by brand'},
            'start_date': {'type': 'string', 'description': 'Start date (YYYY-MM-DD)'},
            'end_date': {'type': 'string', 'description': 'End date (YYYY-MM-DD)'},
        },
    },
    handler=get_top_suppliers,
    permission='accounting.view',
)

tool_registry.register(
    name='get_transaction_summary',
    description=(
        'Get bank transaction summary with status breakdown and per-supplier totals. '
        'Use when the user asks about bank transactions, payment status, or transaction summaries. '
        'Returns: {total_count, total_amount, by_status: {pending: {count, total}, ...}, top_suppliers: [{name, total, count}]}. '
        'Example: {supplier: "OMV", date_from: "2026-01-01", date_to: "2026-01-31"}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'company_cui': {'type': 'string', 'description': 'Filter by company CUI/VAT'},
            'supplier': {'type': 'string', 'description': 'Filter by supplier/vendor name'},
            'date_from': {'type': 'string', 'description': 'Start date (YYYY-MM-DD)'},
            'date_to': {'type': 'string', 'description': 'End date (YYYY-MM-DD)'},
        },
    },
    handler=get_transaction_summary,
    permission='accounting.view',
)
