import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
import pytest


def test_resolve_stop_companies_tags_in_set_and_drops_companyless():
    from field_sales.routes.visits import _resolve_stop_companies
    stops = [{'client_id': 10, 'company_id': 999}, {'client_id': 11}]
    lookup = {10: 20, 11: None}.get
    forbidden = _resolve_stop_companies(stops, False, {20}, lookup)
    assert forbidden is None
    assert stops[0]['company_id'] == 20          # client's company overrides the request's 999
    assert 'company_id' not in stops[1]          # companyless client → key dropped


def test_resolve_stop_companies_blocks_forbidden_client():
    from field_sales.routes.visits import _resolve_stop_companies
    stops = [{'client_id': 10}, {'client_id': 11}]
    lookup = {10: 20, 11: 77}.get
    assert _resolve_stop_companies(stops, False, {20}, lookup) == 1   # stop index 1 is out-of-tenant


def test_resolve_stop_companies_admin_bypasses_gate():
    from field_sales.routes.visits import _resolve_stop_companies
    stops = [{'client_id': 10}]
    lookup = {10: 77}.get
    assert _resolve_stop_companies(stops, True, set(), lookup) is None
    assert stops[0]['company_id'] == 77
