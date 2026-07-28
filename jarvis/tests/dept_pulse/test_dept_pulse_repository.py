"""DeptPulseRepository — resolution & eligibility (Task 2). localhost/defaultdb."""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
import psycopg2  # noqa: F401
from core.profile.repositories.dept_pulse_repository import DeptPulseRepository

from .conftest import REAL_DB_AVAILABLE

repo = DeptPulseRepository()


@pytest.fixture(autouse=True)
def _require_real_db():
    """Most tests below take the `pulse_org` fixture, which already skips
    when REAL_DB_AVAILABLE is False. `test_unmapped_user_resolves_to_none`
    doesn't (it needs no seeded org), but it still calls the repository
    directly and would otherwise hit a mocked cursor in a no-DB run — so
    guard the whole module here too.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping dept_pulse repository tests'
        )


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


import pytest
from psycopg2.errors import CheckViolation


def test_rolling_upsert_updates_same_row(pulse_org):
    a, node = pulse_org['user_A'], pulse_org['node_C']
    repo.upsert_vote(a, node, 'self', 'communication', 4)
    repo.upsert_vote(a, node, 'self', 'communication', 2)  # re-vote
    mine = repo.get_my_votes(a, node)
    cells = [(v['perspective'], v['competency_key'], v['rating']) for v in mine]
    assert cells == [('self', 'communication', 2)]  # one row, latest value


def test_delete_on_zero_removes_vote(pulse_org):
    a, node = pulse_org['user_A'], pulse_org['node_C']
    repo.upsert_vote(a, node, 'peer', 'teamwork', 5)
    repo.delete_vote(a, node, 'peer', 'teamwork')
    assert repo.get_my_votes(a, node) == []


def test_aggregate_average_and_distinct_voters(pulse_org):
    node = pulse_org['node_C']
    repo.upsert_vote(pulse_org['user_A'], node, 'peer', 'communication', 4)
    repo.upsert_vote(pulse_org['user_B'], node, 'peer', 'communication', 5)
    repo.upsert_vote(pulse_org['user_C'], node, 'peer', 'communication', 3)
    agg = {(r['perspective'], r['competency_key']): r for r in repo.get_aggregate(node)}
    cell = agg[('peer', 'communication')]
    assert cell['avg'] == 4.0
    assert cell['voters'] == 3
    assert repo.get_voter_count(node) == 3


def test_voter_count_below_floor(pulse_org):
    node = pulse_org['node_C']
    repo.upsert_vote(pulse_org['user_A'], node, 'manager', 'initiative', 4)
    repo.upsert_vote(pulse_org['user_B'], node, 'manager', 'initiative', 2)
    assert repo.get_voter_count(node) == 2  # < MIN_VOTERS — route will blank aggregate


def test_upsert_rejects_out_of_range_rating(pulse_org):
    with pytest.raises(CheckViolation):
        repo.upsert_vote(pulse_org['user_A'], pulse_org['node_C'], 'self', 'communication', 6)
