"""DB-free unit tests for the company-scope WHERE-fragment builder shared by the
catalog / status-count / filter-option queries. Locks the 'Toate Companiile'
semantics: a multi-company scope of None means "every company" (Admin), [] means
"no company" (match nothing), and [ids] means an IN-list; a single company_id
keeps the original '= %s' behavior."""
from carpark.repositories.vehicle_repository import _company_scope_clause


def test_single_company_id():
    clause, params = _company_scope_clause('v.company_id', company_id='11')
    assert clause == 'v.company_id = %s'
    assert params == [11]


def test_no_scope_means_no_filter():
    assert _company_scope_clause('v.company_id') == (None, [])
    assert _company_scope_clause('v.company_id', company_id=None) == (None, [])


def test_company_ids_none_is_every_company():
    assert _company_scope_clause('company_id', company_ids=None) == (None, [])


def test_company_ids_empty_matches_nothing():
    assert _company_scope_clause('company_id', company_ids=[]) == ('1 = 0', [])


def test_company_ids_list_builds_in_clause():
    clause, params = _company_scope_clause('v.company_id', company_ids=[1, 4, 11])
    assert clause == 'v.company_id IN (%s, %s, %s)'
    assert params == [1, 4, 11]


def test_company_ids_takes_precedence_over_single():
    # When both are given, the multi-company scope wins.
    clause, params = _company_scope_clause('company_id', company_id=99, company_ids=[1, 2])
    assert clause == 'company_id IN (%s, %s)'
    assert params == [1, 2]
