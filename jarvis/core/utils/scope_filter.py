"""Scope-based SQL WHERE clause helper for V2 permission filtering.

Converts a permission scope value ('own' | 'department' | 'all') + user context
into an (sql_fragment, params) tuple that can be appended to any query.

Usage:
    scope_sql, scope_params = apply_scope_filter(
        scope, user_context,
        user_id_col='id',
        dept_col='department',
        company_col='company',
    )
    query += scope_sql
    params.extend(scope_params)

Column names default to the users-table convention (id, department, company)
but can be overridden for joined queries (e.g. 'b.user_id', 'u.department').
"""
from typing import Optional


def apply_scope_filter(
    scope: str,
    user_context: Optional[dict],
    user_id_col: str = 'id',
    dept_col: str = 'department',
    company_col: str = 'company',
) -> tuple[str, list]:
    """Return (sql_fragment, params) for scope-based WHERE clause filtering.

    Args:
        scope: Permission scope string — 'own', 'department', or 'all'.
        user_context: Dict with keys 'user_id', 'department', 'company'.
            If None or missing keys, filter is silently skipped.
        user_id_col: SQL column expression for user identity (default: 'id').
        dept_col: SQL column expression for department (default: 'department').
        company_col: SQL column expression for company (default: 'company').

    Returns:
        Tuple of (sql_fragment, params_list).
        sql_fragment starts with ' AND ' and is ready to append to a query string.
        Returns ('', []) for 'all' scope or when required context is missing.
    """
    if scope == 'own' and user_context:
        return f' AND {user_id_col} = %s', [user_context.get('user_id')]

    if scope == 'department' and user_context:
        dept = user_context.get('department')
        company = user_context.get('company')
        if dept and company:
            return f' AND {dept_col} = %s AND {company_col} = %s', [dept, company]

    return '', []
