"""Shared org-hierarchy scope helper for L0-L5 department filtering.

Extracts the recursive CTE logic used by ProfileRepository so both Profile
and Accounting routes can determine which employees / allocations a user
is allowed to see based on the organigram.

Usage (Accounting):
    from core.utils.org_scope import get_org_scope_filter
    org = get_org_scope_filter(cursor, user_id)
    # org.sees_all  → True if L0 (company responsable) — no filtering needed
    # org.company_ids  → set of company IDs where user is L0
    # org.node_names_by_company  → {company_name: set(node_names)} for L1-L5
    # org.has_any  → True if user has any org role at all
"""
from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrgScope:
    """Result of org-hierarchy lookup for a single user."""
    # L0 company responsable — sees all invoices for these companies
    l0_company_ids: set[int] = field(default_factory=set)
    l0_company_names: set[str] = field(default_factory=set)
    # L1-L5 node names grouped by company name (excluding L0-covered companies)
    node_names_by_company: dict[str, set[str]] = field(default_factory=dict)

    @property
    def has_any(self) -> bool:
        return bool(self.l0_company_ids or self.node_names_by_company)

    @property
    def sees_all_companies(self) -> bool:
        """True when user is L0 for at least one company and has no L1-L5 nodes outside those."""
        return bool(self.l0_company_ids) and not self.node_names_by_company


# Simple TTL cache: {user_id: (OrgScope, timestamp)}
_cache: dict[int, tuple[OrgScope, float]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 60  # seconds


def _invalidate_expired():
    now = time.time()
    expired = [k for k, (_, ts) in _cache.items() if now - ts > _CACHE_TTL]
    for k in expired:
        del _cache[k]


def get_org_scope(cursor, user_id: int) -> OrgScope:
    """Build OrgScope for user from L0 company_responsables + L1-L5 structure_nodes.

    Results are cached for 60 seconds per user_id.
    """
    with _cache_lock:
        _invalidate_expired()
        cached = _cache.get(user_id)
        if cached:
            return cached[0]

    scope = _build_org_scope(cursor, user_id)

    with _cache_lock:
        _cache[user_id] = (scope, time.time())

    return scope


def _build_org_scope(cursor, user_id: int) -> OrgScope:
    """Core logic — runs the two DB queries."""
    scope = OrgScope()

    # L0: company responsable assignments
    cursor.execute('''
        SELECT c.id as company_id, c.company
        FROM company_responsables cr
        JOIN companies c ON cr.company_id = c.id
        WHERE cr.user_id = %s
    ''', (user_id,))
    for row in cursor.fetchall():
        scope.l0_company_ids.add(row['company_id'])
        scope.l0_company_names.add(row['company'])

    # L1-L5: nodes where user is responsable + all descendants (recursive)
    cursor.execute('''
        WITH RECURSIVE resp_nodes AS (
            SELECT sn.id, sn.name, sn.level, sn.company_id
            FROM structure_node_members snm
            JOIN structure_nodes sn ON snm.node_id = sn.id
            WHERE snm.user_id = %s AND snm.role = 'responsable'
        ),
        descendants AS (
            SELECT id, name, level, company_id FROM resp_nodes
            UNION ALL
            SELECT sn.id, sn.name, sn.level, sn.company_id
            FROM structure_nodes sn
            JOIN descendants d ON sn.parent_id = d.id
        )
        SELECT DISTINCT d.name, d.level, d.company_id, c.company
        FROM descendants d
        JOIN companies c ON d.company_id = c.id
    ''', (user_id,))

    company_names = defaultdict(set)
    for row in cursor.fetchall():
        # Skip companies already covered by L0
        if row['company_id'] in scope.l0_company_ids:
            continue
        company_names[row['company']].add(row['name'].lower())

    scope.node_names_by_company = dict(company_names)
    return scope


def build_allocation_org_filter(org: OrgScope) -> tuple[str, list]:
    """Build SQL WHERE fragment for allocations table (alias 'a') using OrgScope.

    Returns (sql_fragment, params). Fragment is an OR clause like:
        (a.company = %s) OR (a.company = %s AND (LOWER(a.department) IN (...) OR LOWER(COALESCE(a.subdepartment, '')) IN (...)))

    Returns ('', []) if user has no org role.
    """
    if not org.has_any:
        return '', []

    conditions = []
    params = []

    # L0: all invoices for the company
    for comp in org.l0_company_names:
        conditions.append('a.company = %s')
        params.append(comp)

    # L1-L5: match department/subdepartment against node names
    for comp, names in org.node_names_by_company.items():
        name_list = list(names)
        placeholders = ','.join(['%s'] * len(name_list))
        conditions.append(
            f'(a.company = %s AND (LOWER(a.department) IN ({placeholders})'
            f' OR LOWER(COALESCE(a.subdepartment, \'\')) IN ({placeholders})))'
        )
        params.append(comp)
        params.extend(name_list)
        params.extend(name_list)

    if not conditions:
        return '', []

    return '(' + ' OR '.join(conditions) + ')', params
