"""Tests for core.organization.hr_utils — cache delegation layer.

hr_utils wraps core.organization.manager_utils with a 60-second TTL cache.
Tests patch the module-level callables (_is_manager, _get_managed, _get_visible_tree)
that hr_utils imports at startup, so no real DB is exercised.
"""
import sys
import os
import importlib.util

# ── path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from unittest.mock import MagicMock

_hr_db_mock = MagicMock()
_hr_db_mock.is_manager.return_value = False
_hr_db_mock.get_managed_employee_ids.return_value = []
_hr_db_mock.get_visible_tree.return_value = {}

# ── Load hr_utils.py directly, bypassing package __init__.py ─────────────────
_JARVIS_ROOT = os.path.join(os.path.dirname(__file__), '..', 'jarvis')
_hr_utils_path = os.path.join(_JARVIS_ROOT, 'core', 'organization', 'hr_utils.py')

spec = importlib.util.spec_from_file_location('core.organization.hr_utils', _hr_utils_path)
hr_utils = importlib.util.module_from_spec(spec)
sys.modules['core.organization.hr_utils'] = hr_utils
spec.loader.exec_module(hr_utils)

import pytest

is_manager = hr_utils.is_manager
get_managed_employee_ids = hr_utils.get_managed_employee_ids
get_visible_tree = hr_utils.get_visible_tree


def _clear_cache():
    with hr_utils._cache_lock:
        hr_utils._cache.clear()


@pytest.fixture(autouse=True)
def _stub_manager_utils():
    """Patch hr_utils' imported callables for each test, then restore."""
    orig_is_manager = hr_utils._is_manager
    orig_get_managed = hr_utils._get_managed
    orig_get_visible_tree = hr_utils._get_visible_tree
    hr_utils._is_manager = _hr_db_mock.is_manager
    hr_utils._get_managed = _hr_db_mock.get_managed_employee_ids
    hr_utils._get_visible_tree = _hr_db_mock.get_visible_tree
    yield
    hr_utils._is_manager = orig_is_manager
    hr_utils._get_managed = orig_get_managed
    hr_utils._get_visible_tree = orig_get_visible_tree


# ==============================================================================

class TestIsManager:
    def setup_method(self):
        _clear_cache()

    def test_returns_false_for_non_manager(self):
        _hr_db_mock.is_manager.return_value = False
        assert is_manager(999) is False
        _hr_db_mock.is_manager.assert_called_with(999)

    def test_returns_true_for_manager(self):
        _hr_db_mock.is_manager.return_value = True
        assert is_manager(1) is True

    def test_caches_result_second_call_no_db_hit(self):
        _hr_db_mock.is_manager.reset_mock()
        _hr_db_mock.is_manager.return_value = True
        is_manager(42)
        is_manager(42)  # served from cache
        assert _hr_db_mock.is_manager.call_count == 1

    def test_different_user_ids_cached_separately(self):
        _hr_db_mock.is_manager.reset_mock()
        _hr_db_mock.is_manager.side_effect = [True, False]
        r1 = is_manager(1)
        r2 = is_manager(2)
        assert r1 is True
        assert r2 is False
        assert _hr_db_mock.is_manager.call_count == 2
        _hr_db_mock.is_manager.side_effect = None


class TestGetManagedEmployeeIds:
    def setup_method(self):
        _clear_cache()

    def test_returns_list_of_ids(self):
        _hr_db_mock.get_managed_employee_ids.return_value = [10, 20, 30]
        result = get_managed_employee_ids(1)
        assert result == [10, 20, 30]

    def test_caches_result(self):
        _hr_db_mock.get_managed_employee_ids.reset_mock()
        _hr_db_mock.get_managed_employee_ids.return_value = [5, 6]
        get_managed_employee_ids(7)
        get_managed_employee_ids(7)
        assert _hr_db_mock.get_managed_employee_ids.call_count == 1

    def test_different_node_ids_cached_separately(self):
        _hr_db_mock.get_managed_employee_ids.reset_mock()
        _hr_db_mock.get_managed_employee_ids.side_effect = [[1, 2], [3, 4]]
        r1 = get_managed_employee_ids(5, node_id=10)
        r2 = get_managed_employee_ids(5, node_id=20)
        assert r1 == [1, 2]
        assert r2 == [3, 4]
        assert _hr_db_mock.get_managed_employee_ids.call_count == 2
        _hr_db_mock.get_managed_employee_ids.side_effect = None


class TestGetVisibleTree:
    def setup_method(self):
        _clear_cache()

    def test_returns_tree_structure(self):
        expected = {'id': 1, 'children': [{'id': 2}]}
        _hr_db_mock.get_visible_tree.return_value = expected
        assert get_visible_tree(1) == expected

    def test_caches_tree(self):
        _hr_db_mock.get_visible_tree.reset_mock()
        _hr_db_mock.get_visible_tree.return_value = {'id': 99}
        get_visible_tree(1)
        get_visible_tree(1)
        assert _hr_db_mock.get_visible_tree.call_count == 1

    def test_cache_isolates_per_user(self):
        _hr_db_mock.get_visible_tree.reset_mock()
        _hr_db_mock.get_visible_tree.side_effect = [{'id': 1}, {'id': 2}]
        r1 = get_visible_tree(10)
        r2 = get_visible_tree(20)
        assert r1 == {'id': 1}
        assert r2 == {'id': 2}
        assert _hr_db_mock.get_visible_tree.call_count == 2
        _hr_db_mock.get_visible_tree.side_effect = None


class TestCacheInvalidation:
    def setup_method(self):
        _clear_cache()

    def test_invalidate_user_cache_clears_all_keys_for_user(self):
        _hr_db_mock.is_manager.return_value = True
        _hr_db_mock.get_managed_employee_ids.return_value = [1, 2]
        is_manager(5)
        get_managed_employee_ids(5)
        # Verify cache has entries for user 5
        with hr_utils._cache_lock:
            keys = list(hr_utils._cache.keys())
        assert any('5' in k for k in keys)
        # Invalidate
        hr_utils.invalidate_user_cache(5)
        with hr_utils._cache_lock:
            remaining = [k for k in hr_utils._cache if '5' in k]
        assert remaining == []
