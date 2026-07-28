"""DeptPulseRepository — resolution & eligibility (Task 2). localhost/defaultdb."""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import psycopg2  # noqa: F401
from core.profile.repositories.dept_pulse_repository import DeptPulseRepository

repo = DeptPulseRepository()


def test_member_resolves_own_department(pulse_org):
    dept = repo.resolve_department(pulse_org['user_A'])
    assert dept is not None
    assert dept['node_id'] == pulse_org['node_C']
    assert dept['name'] == 'Pulse C'


def test_unmapped_user_resolves_to_none():
    # A user id that maps to no active sincron employee.
    assert repo.resolve_department(-1) is None


def test_manager_eligible_for_own_and_descendant(pulse_org):
    m = pulse_org['user_M']
    assert repo.is_eligible(m, pulse_org['node_P']) is True
    assert repo.is_eligible(m, pulse_org['node_C']) is True  # descendant of P


def test_member_not_eligible_for_parent(pulse_org):
    a = pulse_org['user_A']
    assert repo.is_eligible(a, pulse_org['node_C']) is True
    assert repo.is_eligible(a, pulse_org['node_P']) is False  # members don't see up


def test_available_departments_for_manager(pulse_org):
    names = {d['node_id'] for d in repo.available_departments(pulse_org['user_M'])}
    assert names == {pulse_org['node_P'], pulse_org['node_C']}


def test_available_departments_for_member(pulse_org):
    depts = repo.available_departments(pulse_org['user_A'])
    assert [d['node_id'] for d in depts] == [pulse_org['node_C']]
