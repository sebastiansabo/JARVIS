"""Division-overlay resolution tests for manager_utils.

A Division groups Sincron departments across companies with responsable(s). The
division responsable is a FALLBACK manager: used only when a person has no
manager above them in the Sincron tree. See
docs/superpowers/specs/2026-09-07-hr-divisions-design.md.

Builds on the `org_fixture` topology (see conftest):
    CT: P(l1) -> Ch(l2); M responsable@P; A,B member@Ch; D member@P
    DZ: Z(l1); E member@Z   (E has NO responsable above -> the "Duca" case)
"""
import pytest

from tests.org.conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db
from core.organization.manager_utils import (
    get_direct_manager, is_manager, get_managed_employee_ids,
    get_division_responsable_ids,
)

pytestmark = pytest.mark.skipif(not REAL_DB_AVAILABLE, reason='no real DB available (CI)')


def _make_division(name, node_ids, responsable_user_ids):
    """Insert a division with departments + responsables; return its id."""
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("INSERT INTO hr_divisions (name) VALUES (%s) RETURNING id", (name,))
        did = cur.fetchone()['id']
        for nid in node_ids:
            cur.execute(
                "INSERT INTO hr_division_departments (division_id, node_id) VALUES (%s, %s)",
                (did, nid),
            )
        for uid in responsable_user_ids:
            cur.execute(
                "INSERT INTO hr_division_responsables (division_id, user_id) VALUES (%s, %s)",
                (did, uid),
            )
        conn.commit()
        return did
    finally:
        release_db(conn)


def _drop_division(did):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("DELETE FROM hr_divisions WHERE id = %s", (did,))  # cascades children
        conn.commit()
    finally:
        release_db(conn)


def test_division_responsable_is_fallback_manager_for_unmanaged_employee(org_fixture):
    """E sits under node Z with no responsable above -> today get_direct_manager
    is None. Put Z in a division whose responsable is M -> E's manager is M."""
    assert get_direct_manager(org_fixture['user_E']) is None  # baseline
    did = _make_division('ZZ Div Aftersales', [org_fixture['node_Z']], [org_fixture['user_M']])
    try:
        mgr = get_direct_manager(org_fixture['user_E'])
        assert mgr is not None
        assert mgr['id'] == org_fixture['user_M']
    finally:
        _drop_division(did)


def test_division_does_not_override_existing_manager(org_fixture):
    """A already reports to M (responsable@P). Even if A's branch is in a
    division with a different responsable, A still routes to M (fallback only)."""
    did = _make_division('ZZ Div Override', [org_fixture['node_Ch']], [org_fixture['user_D']])
    try:
        mgr = get_direct_manager(org_fixture['user_A'])
        assert mgr is not None
        assert mgr['id'] == org_fixture['user_M']  # NOT user_D
    finally:
        _drop_division(did)


def test_department_manager_subordinated_to_division_manager(org_fixture):
    """M is responsable@P with nobody above -> today no manager. Put P in a
    division whose responsable is E -> M reports up to E."""
    assert get_direct_manager(org_fixture['user_M']) is None  # baseline
    did = _make_division('ZZ Div Subord', [org_fixture['node_P']], [org_fixture['user_E']])
    try:
        mgr = get_direct_manager(org_fixture['user_M'])
        assert mgr is not None
        assert mgr['id'] == org_fixture['user_E']
    finally:
        _drop_division(did)


def test_division_responsable_counts_as_manager(org_fixture):
    """A division responsable is a manager even if they hold no Sincron
    responsable role."""
    # user_B is only a member@Ch -> not a manager today.
    assert is_manager(org_fixture['user_B']) is False
    did = _make_division('ZZ Div IsMgr', [org_fixture['node_Z']], [org_fixture['user_B']])
    try:
        assert is_manager(org_fixture['user_B']) is True
    finally:
        _drop_division(did)


def test_division_responsable_manages_division_members(org_fixture):
    """A division responsable sees the division's members as their team."""
    did = _make_division('ZZ Div Team', [org_fixture['node_Z']], [org_fixture['user_B']])
    try:
        managed = get_managed_employee_ids(org_fixture['user_B'])
        assert org_fixture['user_E'] in managed  # E is member@Z, Z in the division
    finally:
        _drop_division(did)


def test_all_division_responsables_can_approve(org_fixture):
    """get_division_responsable_ids returns EVERY responsable of the nearest
    division (any can approve), excluding the requester."""
    did = _make_division('ZZ Div Multi', [org_fixture['node_Z']],
                         [org_fixture['user_A'], org_fixture['user_B']])
    try:
        ids = get_division_responsable_ids(org_fixture['user_E'])
        assert set(ids) == {org_fixture['user_A'], org_fixture['user_B']}
        # A non-division user's nearest manager is Sincron -> no division ids.
        assert get_division_responsable_ids(org_fixture['user_A']) == []
    finally:
        _drop_division(did)
