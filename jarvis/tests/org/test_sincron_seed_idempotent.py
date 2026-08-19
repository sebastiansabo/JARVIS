"""seed_from_departments must be idempotent across the whole node tree.

Regression for the prod bug where clicking "Seed from departments" AFTER the
org had been reorganized (departments nested as L2 children under a grouping
node like 'Aftersales') re-created every department as a fresh L1 root — because
the idempotency guard only looked at level-1 nodes. Result: doubled departments.
localhost/defaultdb only.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import psycopg2  # noqa: F401

from core.connectors.sincron.repositories.sincron_org_node_repository import (
    SincronOrgNodeRepository,
)


def test_reseed_after_nesting_does_not_duplicate(seed_fixture):
    repo = SincronOrgNodeRepository()
    cid = seed_fixture['company_id']

    # ── First seed → two L1 department nodes, members assigned ──
    r1 = repo.seed_from_departments(cid)
    assert r1['created'] == 2
    nodes1 = repo.get_by_company(cid)
    assert sorted(n['name'] for n in nodes1) == ['Dept Alpha', 'Dept Beta']
    alpha = next(n for n in nodes1 if n['name'] == 'Dept Alpha')

    # ── Reorganize: add a grouping node and nest 'Dept Alpha' under it (→ L2) ──
    group_id = repo.create(cid, 'Aftersales', parent_id=None, node_type='department')
    repo.execute('UPDATE sincron_org_nodes SET parent_id = %s, level = 2 WHERE id = %s',
                 (group_id, alpha['id']))

    # ── Re-seed → must NOT recreate 'Dept Alpha' as a second L1 root ──
    r2 = repo.seed_from_departments(cid)
    nodes2 = repo.get_by_company(cid)
    alpha_rows = [n for n in nodes2 if n['name'] == 'Dept Alpha']
    assert len(alpha_rows) == 1, f'Dept Alpha duplicated on re-seed: {alpha_rows}'
    assert r2['created'] == 0

    # ── Members stay on the real (now nested) node, not a fresh duplicate ──
    members = repo.get_all_members()
    alpha_member_nodes = {m['node_id'] for m in members
                          if m['sincron_employee_id'] in ('SEED_1', 'SEED_2')}
    assert alpha_member_nodes == {alpha['id']}
