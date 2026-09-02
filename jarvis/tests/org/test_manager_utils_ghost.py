from core.organization.manager_utils import get_managed_employee_ids
import core.organization.manager_utils as mu


def test_managed_excludes_ghosts(org_fixture, monkeypatch):
    monkeypatch.setattr(mu, 'hidden_ghost_ids', lambda viewer: {org_fixture['user_A']})
    got = set(get_managed_employee_ids(org_fixture['user_M']))
    assert org_fixture['user_A'] not in got     # ghost hidden
    assert org_fixture['user_B'] in got         # non-ghost still visible


def test_managed_includes_ghosts_for_superadmin(org_fixture, monkeypatch):
    monkeypatch.setattr(mu, 'hidden_ghost_ids', lambda viewer: set())  # super-admin path
    got = set(get_managed_employee_ids(org_fixture['user_M']))
    assert org_fixture['user_A'] in got
