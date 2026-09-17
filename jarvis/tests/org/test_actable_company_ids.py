import os
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

_MU = 'core.organization.manager_utils'


def test_unions_own_l0_and_subtree():
    with patch(f'{_MU}.get_db') as gdb, patch(f'{_MU}.get_cursor') as gc, \
         patch(f'{_MU}.release_db'), \
         patch(f'{_MU}.get_visible_tree') as gvt:
        cur = MagicMock()
        gc.return_value = cur
        cur.fetchone.return_value = {'company_id': 1}          # own company
        gvt.return_value = {'companies': [{'company_id': 3}],   # L0
                            'nodes': [{'company_id': 5}, {'company_id': 3}]}  # subtree
        from core.organization.manager_utils import get_actable_company_ids
        assert get_actable_company_ids(42) == {1, 3, 5}


def test_user_without_company_still_gets_tree():
    with patch(f'{_MU}.get_db'), patch(f'{_MU}.get_cursor') as gc, \
         patch(f'{_MU}.release_db'), \
         patch(f'{_MU}.get_visible_tree') as gvt:
        cur = MagicMock()
        gc.return_value = cur
        cur.fetchone.return_value = None                        # no own company
        gvt.return_value = {'companies': [{'company_id': 7}], 'nodes': []}
        from core.organization.manager_utils import get_actable_company_ids
        assert get_actable_company_ids(42) == {7}
