"""
Query Parser

Lightweight intent detection and entity extraction for analytics queries.
Uses keyword matching and regex — no LLM call needed.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional, List, Dict

from core.utils.logging_config import get_logger

logger = get_logger('jarvis.ai_agent.services.query_parser')

# Analytics intent keywords (case-insensitive)
ANALYTICS_KEYWORDS = {
    'total', 'sum', 'spend', 'spending', 'spent', 'how much', 'cost', 'costs',
    'compare', 'comparison', 'top', 'biggest', 'largest', 'most', 'highest',
    'monthly', 'trend', 'breakdown', 'report', 'summary', 'average',
    'count', 'budget', 'expense', 'expenses', 'revenue',
    'overview', 'statistics', 'stats', 'aggregate',
    'per month', 'per quarter', 'quarterly', 'yearly', 'annual',
    'how many', 'what is the total', 'what are the',
}

# Monthly trend keywords
TREND_KEYWORDS = {'monthly', 'trend', 'per month', 'month by month', 'over time', 'quarterly', 'per quarter'}

# Top suppliers keywords
TOP_SUPPLIER_KEYWORDS = {'top supplier', 'top vendors', 'biggest supplier', 'largest supplier', 'most expensive supplier'}

# Transaction/bank keywords
TRANSACTION_KEYWORDS = {'bank', 'transaction', 'transactions', 'statement', 'statements', 'pending', 'reconcil'}

# e-Factura keywords
EFACTURA_KEYWORDS = {
    'efactura', 'e-factura', 'factura electronica', 'anaf',
    'unallocated', 'nealocate', 'nealocata', 'hidden', 'ascunse',
    'allocated', 'alocate', 'alocata',
}

# Group-by keywords
GROUP_BY_KEYWORDS = {
    'company': ['by company', 'per company', 'each company', 'companies'],
    'department': ['by department', 'per department', 'each department', 'departments'],
    'brand': ['by brand', 'per brand', 'each brand', 'brands', 'business line'],
    'supplier': ['by supplier', 'per supplier', 'each supplier', 'suppliers', 'vendors', 'by vendor'],
}

# Month name mappings (English + Romanian)
MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    # Romanian
    'ianuarie': 1, 'februarie': 2, 'martie': 3, 'aprilie': 4,
    'mai': 5, 'iunie': 6, 'iulie': 7, 'august': 8,
    'septembrie': 9, 'octombrie': 10, 'noiembrie': 11, 'decembrie': 12,
}

QUARTER_MAP = {
    'q1': (1, 3), 'q2': (4, 6), 'q3': (7, 9), 'q4': (10, 12),
}


# Simple/greeting keywords — queries that don't need a powerful model
SIMPLE_KEYWORDS = {
    'hello', 'hi', 'hey', 'buna', 'salut', 'ciao',
    'thanks', 'thank you', 'mersi', 'multumesc',
    'bye', 'goodbye', 'pa', 'ok', 'okay',
    'who are you', 'what are you', 'what can you do',
    'help', 'ajutor',
}

# Complex keywords — queries that benefit from a powerful model
COMPLEX_KEYWORDS = {
    'analyze', 'analyse', 'explain', 'why', 'recommend', 'suggest',
    'forecast', 'predict', 'compare', 'correlation', 'anomaly',
    'strategy', 'optimize', 'plan', 'evaluate', 'assess',
    'detailed', 'in-depth', 'comprehensive', 'elaborate',
}


@dataclass
class ParsedQuery:
    """Result of parsing a user query for analytics intent."""
    is_analytics: bool = False
    query_types: List[str] = field(default_factory=list)
    group_by: Optional[str] = None
    filters: Dict[str, str] = field(default_factory=dict)
    top_n: Optional[int] = None
    complexity: str = 'default'  # 'simple', 'default', or 'complex'


def parse_query(user_message: str, known_entities: Optional[Dict[str, List[str]]] = None) -> ParsedQuery:
    """Parse a user message for analytics intent and extract filters.

    Args:
        user_message: The raw user message
        known_entities: Dict with keys 'companies', 'departments', 'brands', 'suppliers'

    Returns:
        ParsedQuery with intent and extracted entities
    """
    msg_lower = user_message.lower().strip()
    result = ParsedQuery()

    # 1. Check analytics intent
    if not _has_analytics_intent(msg_lower):
        return result
    result.is_analytics = True

    # 2. Detect query types
    result.query_types = _detect_query_types(msg_lower)

    # 3. Extract date filters
    dates = _extract_dates(msg_lower)
    if dates.get('start_date'):
        result.filters['start_date'] = dates['start_date']
    if dates.get('end_date'):
        result.filters['end_date'] = dates['end_date']

    # 4. Extract entity filters
    if known_entities:
        _extract_entities(msg_lower, known_entities, result)

    # 5. Detect group_by
    result.group_by = _detect_group_by(msg_lower, result)

    # 6. Extract top N
    result.top_n = _extract_top_n(msg_lower)

    # 7. Classify complexity
    result.complexity = classify_complexity(user_message)

    logger.debug(
        f"Parsed query: analytics={result.is_analytics}, types={result.query_types}, "
        f"group_by={result.group_by}, filters={result.filters}, complexity={result.complexity}"
    )

    return result


def _has_analytics_intent(msg_lower: str) -> bool:
    """Check if the message has analytics/aggregation intent."""
    for keyword in ANALYTICS_KEYWORDS:
        if keyword in msg_lower:
            return True
    # e-Factura queries are always analytics
    for keyword in EFACTURA_KEYWORDS:
        if keyword in msg_lower:
            return True
    return False


def _detect_query_types(msg_lower: str) -> List[str]:
    """Detect which analytics query types are relevant."""
    types = []

    # Check for trend/monthly
    if any(kw in msg_lower for kw in TREND_KEYWORDS):
        types.append('monthly_trend')

    # Check for top suppliers
    if any(kw in msg_lower for kw in TOP_SUPPLIER_KEYWORDS):
        types.append('top_suppliers')
    elif 'top' in msg_lower and any(w in msg_lower for w in ['supplier', 'vendor']):
        types.append('top_suppliers')

    # Check for transaction/bank
    if any(kw in msg_lower for kw in TRANSACTION_KEYWORDS):
        types.append('transaction_summary')

    # Check for e-Factura
    if any(kw in msg_lower for kw in EFACTURA_KEYWORDS):
        types.append('efactura_summary')

    # Default: invoice summary (if no specific type detected, or always include)
    if not types or any(kw in msg_lower for kw in ['invoice', 'spend', 'cost', 'total', 'budget', 'expense']):
        types.append('invoice_summary')

    return types


def _extract_dates(msg_lower: str) -> Dict[str, str]:
    """Extract date ranges from the message."""
    today = date.today()
    result: Dict[str, str] = {}

    # "this month"
    if 'this month' in msg_lower or 'luna aceasta' in msg_lower:
        result['start_date'] = today.replace(day=1).isoformat()
        result['end_date'] = today.isoformat()
        return result

    # "last month"
    if 'last month' in msg_lower or 'luna trecuta' in msg_lower:
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        result['start_date'] = last_month_start.isoformat()
        result['end_date'] = last_month_end.isoformat()
        return result

    # "this quarter"
    if 'this quarter' in msg_lower:
        quarter = (today.month - 1) // 3
        start_month = quarter * 3 + 1
        result['start_date'] = today.replace(month=start_month, day=1).isoformat()
        result['end_date'] = today.isoformat()
        return result

    # "last quarter"
    if 'last quarter' in msg_lower:
        quarter = (today.month - 1) // 3
        if quarter == 0:
            start_month, end_month = 10, 12
            year = today.year - 1
        else:
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            year = today.year
        result['start_date'] = date(year, start_month, 1).isoformat()
        last_day = date(year, end_month + 1, 1) - timedelta(days=1) if end_month < 12 else date(year, 12, 31)
        result['end_date'] = last_day.isoformat()
        return result

    # "this year" / "2026" / "2025"
    if 'this year' in msg_lower or 'anul acesta' in msg_lower:
        result['start_date'] = date(today.year, 1, 1).isoformat()
        result['end_date'] = today.isoformat()
        return result

    if 'last year' in msg_lower or 'anul trecut' in msg_lower:
        result['start_date'] = date(today.year - 1, 1, 1).isoformat()
        result['end_date'] = date(today.year - 1, 12, 31).isoformat()
        return result

    # "Q1 2026", "Q2 2025"
    q_match = re.search(r'\b(q[1-4])\s*(\d{4})\b', msg_lower)
    if q_match:
        q = q_match.group(1)
        year = int(q_match.group(2))
        start_m, end_m = QUARTER_MAP[q]
        result['start_date'] = date(year, start_m, 1).isoformat()
        last_day = date(year, end_m + 1, 1) - timedelta(days=1) if end_m < 12 else date(year, 12, 31)
        result['end_date'] = last_day.isoformat()
        return result

    # "January 2026", "Feb 2025", "ianuarie 2026"
    for month_name, month_num in MONTH_NAMES.items():
        pattern = rf'\b{re.escape(month_name)}\s+(\d{{4}})\b'
        m = re.search(pattern, msg_lower)
        if m:
            year = int(m.group(1))
            result['start_date'] = date(year, month_num, 1).isoformat()
            if month_num == 12:
                result['end_date'] = date(year, 12, 31).isoformat()
            else:
                result['end_date'] = (date(year, month_num + 1, 1) - timedelta(days=1)).isoformat()
            return result

    # Bare year "2025", "2026" (only if it's clearly a year reference)
    year_match = re.search(r'\b(202[0-9])\b', msg_lower)
    if year_match:
        # Make sure it's not part of a larger number or date
        year = int(year_match.group(1))
        result['start_date'] = date(year, 1, 1).isoformat()
        if year == today.year:
            result['end_date'] = today.isoformat()
        else:
            result['end_date'] = date(year, 12, 31).isoformat()
        return result

    return result


def _extract_entities(msg_lower: str, known_entities: Dict[str, List[str]], result: ParsedQuery):
    """Match known entity names in the message."""
    # Check companies
    for company in known_entities.get('companies', []):
        if company.lower() in msg_lower:
            result.filters['company'] = company
            break

    # Check suppliers (only if not already matched as company)
    if 'supplier' not in result.filters:
        for supplier in known_entities.get('suppliers', []):
            if supplier.lower() in msg_lower:
                result.filters['supplier'] = supplier
                break

    # Check departments
    for dept in known_entities.get('departments', []):
        if dept.lower() in msg_lower:
            result.filters['department'] = dept
            break

    # Check brands
    for brand in known_entities.get('brands', []):
        if brand.lower() in msg_lower:
            result.filters['brand'] = brand
            break


def _detect_group_by(msg_lower: str, result: ParsedQuery) -> Optional[str]:
    """Detect the GROUP BY dimension from keywords."""
    for group, keywords in GROUP_BY_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                return group

    # Infer from query type
    if 'top_suppliers' in result.query_types:
        return 'supplier'

    # Infer from filters: if a company is specified, group by department
    if 'company' in result.filters and 'department' not in result.filters:
        return 'department'

    # Default
    return 'company'


def _extract_top_n(msg_lower: str) -> Optional[int]:
    """Extract 'top N' limit from the message."""
    m = re.search(r'\btop\s+(\d+)\b', msg_lower)
    if m:
        n = int(m.group(1))
        return min(n, 50)  # Cap at 50

    if 'top' in msg_lower:
        return 10  # Default top 10

    return None


def classify_complexity(user_message: str) -> str:
    """Classify query complexity for model routing.

    Returns:
        'simple'  — greetings, thanks, short lookups → route to cheap model
        'complex' — analysis, comparisons, reasoning → route to powerful model
        'default' — everything else → use default model
    """
    msg_lower = user_message.lower().strip()
    word_count = len(msg_lower.split())

    # Very short messages that are greetings/thanks
    if word_count <= 5:
        for kw in SIMPLE_KEYWORDS:
            if kw in msg_lower:
                return 'simple'

    # Complex analysis requests
    for kw in COMPLEX_KEYWORDS:
        if kw in msg_lower:
            return 'complex'

    # Long multi-sentence queries tend to be complex
    if word_count > 40:
        return 'complex'

    return 'default'
