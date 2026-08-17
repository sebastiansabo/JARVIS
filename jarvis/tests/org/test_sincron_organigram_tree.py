"""SincronOrgNodeRepository.get_organigram_tree — read-only organigram view.

The view must mirror the node tree built in the editor (sincron_org_nodes /
sincron_org_members), NOT the stale flat sincron_employees.department column.
An active employee assigned to NO node is the only thing that belongs under
'Neatribuit'. localhost/defaultdb only.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import psycopg2  # noqa: F401

from core.connectors.sincron.repositories.sincron_org_node_repository import (
    SincronOrgNodeRepository,
)

_MARK = 'ZZ_ORG_TEST_CO'  # must match tests/org/conftest.py org_fixture


def _add_lone_active_employee():
    """Insert an active CT employee assigned to no node (a true 'Neatribuit').

    Cleaned up by org_fixture teardown (DELETE ... WHERE company_name = _MARK).
    """
    from database import get_db, get_cursor, release_db
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO sincron_employees
                 (sincron_employee_id, company_name, mapped_jarvis_user_id, is_active)
               VALUES ('ORG_LONE', %s, NULL, TRUE)""",
            (_MARK,),
        )
        conn.commit()
    finally:
        release_db(conn)


def test_organigram_tree_mirrors_nodes_and_neatribuit(org_fixture):
    _add_lone_active_employee()

    tree = SincronOrgNodeRepository().get_organigram_tree()
    ct = next(c for c in tree if c['company_name'] == _MARK)

    # ── Hierarchy: root P (L1) with child Ch (L2) ──
    roots = ct['nodes']
    assert [n['name'] for n in roots] == ['Org P']
    p = roots[0]
    assert p['level'] == 1
    assert [c['name'] for c in p['children']] == ['Org Ch']
    ch = p['children'][0]
    assert ch['level'] == 2

    # ── Members resolved from sincron_org_members, split by role ──
    assert {e['sincron_employee_id'] for e in p['responsables']} == {'ORG_M'}
    assert {e['sincron_employee_id'] for e in p['members']} == {'ORG_D'}
    assert {e['sincron_employee_id'] for e in ch['members']} == {'ORG_A', 'ORG_B', 'ORG_U'}

    # Unmapped member surfaces with a null mapped_user_name (not dropped)
    u = next(e for e in ch['members'] if e['sincron_employee_id'] == 'ORG_U')
    assert u['mapped_user_name'] is None

    # ── 'Neatribuit' = active employees in NO node — only ORG_LONE ──
    assert {e['sincron_employee_id'] for e in ct['unassigned']} == {'ORG_LONE'}

    # ── Counts: 6 active (M,A,B,D,U,LONE); 4 mapped (M,A,B,D) ──
    assert ct['count'] == 6
    assert ct['mapped_count'] == 4
