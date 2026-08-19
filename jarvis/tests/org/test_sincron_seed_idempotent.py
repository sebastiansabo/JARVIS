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


def test_seed_marks_new_department_unallocated(seed_fixture):
    """A department that doesn't exist as a node yet is seeded at L1 but flagged
    node_type='unallocated' (needs a manager or placement), not 'department'."""
    repo = SincronOrgNodeRepository()
    cid = seed_fixture['company_id']

    repo.seed_from_departments(cid)
    nodes = {n['name']: n for n in repo.get_by_company(cid)}
    assert nodes['Dept Alpha']['node_type'] == 'unallocated'
    assert nodes['Dept Alpha']['level'] == 1
    assert nodes['Dept Beta']['node_type'] == 'unallocated'


def test_assigning_responsable_clears_unallocated(seed_fixture):
    """Placing a manager (responsable) on an unallocated node clears the flag."""
    repo = SincronOrgNodeRepository()
    cid = seed_fixture['company_id']
    repo.seed_from_departments(cid)
    alpha = next(n for n in repo.get_by_company(cid) if n['name'] == 'Dept Alpha')
    assert alpha['node_type'] == 'unallocated'

    repo.set_members(alpha['id'], 'responsable',
                     [('SEED_1', seed_fixture['company_name'])])

    assert repo.get(alpha['id'])['node_type'] == 'department'
    # A plain member does NOT clear it
    beta = next(n for n in repo.get_by_company(cid) if n['name'] == 'Dept Beta')
    repo.set_members(beta['id'], 'member', [('SEED_3', seed_fixture['company_name'])])
    assert repo.get(beta['id'])['node_type'] == 'unallocated'


def test_reparent_clears_unallocated_and_recomputes_level(seed_fixture):
    """Moving an unallocated dept under a parent clears the flag and recomputes
    level for the node (and its descendants)."""
    repo = SincronOrgNodeRepository()
    cid = seed_fixture['company_id']
    repo.seed_from_departments(cid)
    alpha = next(n for n in repo.get_by_company(cid) if n['name'] == 'Dept Alpha')
    group_id = repo.create(cid, 'Aftersales', parent_id=None, node_type='department')

    # Give alpha a child first, to prove the level cascade reaches descendants.
    child_id = repo.create(cid, 'Alpha Team', parent_id=alpha['id'], node_type='team')
    assert repo.get(child_id)['level'] == 2

    repo.set_parent(alpha['id'], group_id)

    moved = repo.get(alpha['id'])
    assert moved['parent_id'] == group_id
    assert moved['level'] == 2
    assert moved['node_type'] == 'department'          # cleared
    assert repo.get(child_id)['level'] == 3            # descendant shifted


def test_reparent_rejects_cycles(seed_fixture):
    """A node cannot be moved under itself or one of its own descendants."""
    import pytest
    repo = SincronOrgNodeRepository()
    cid = seed_fixture['company_id']
    parent_id = repo.create(cid, 'Grp', parent_id=None, node_type='department')
    child_id = repo.create(cid, 'Sub', parent_id=parent_id, node_type='department')

    with pytest.raises(ValueError):
        repo.set_parent(parent_id, parent_id)          # self
    with pytest.raises(ValueError):
        repo.set_parent(parent_id, child_id)           # under own descendant
