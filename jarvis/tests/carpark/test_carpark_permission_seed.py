"""Unit tests for _seed_carpark_permissions_v2 — verifies the explicit
per-role grants (critically, that User/Viewer never receive carpark.finance.view)
and that the boolean backfill UPDATE is emitted. Uses a mocked cursor
(mirrors tests/test_permissions.py)."""
import os
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')


def _params(cursor):
    """All parameter tuples passed to cursor.execute (2nd positional arg)."""
    return [c.args[1] for c in cursor.execute.call_args_list if len(c.args) > 1]


def test_seed_grants_finance_deny_to_user_and_viewer():
    from migrations.domains.schema_roles import _seed_carpark_permissions_v2
    cursor, conn = MagicMock(), MagicMock()
    _seed_carpark_permissions_v2(cursor, conn)
    params = _params(cursor)
    # role_permissions_v2 grants are (scope, granted, role_name, entity, action)
    assert ('deny', False, 'User', 'finance', 'view') in params
    assert ('deny', False, 'Viewer', 'finance', 'view') in params
    # User must NEVER get an 'own'/granted finance grant
    assert ('own', True, 'User', 'finance', 'view') not in params
    assert ('all', True, 'User', 'finance', 'view') not in params


def test_seed_grants_edit_all_to_admin_and_manager():
    from migrations.domains.schema_roles import _seed_carpark_permissions_v2
    cursor, conn = MagicMock(), MagicMock()
    _seed_carpark_permissions_v2(cursor, conn)
    params = _params(cursor)
    assert ('all', True, 'Admin', 'vehicles', 'edit') in params
    assert ('all', True, 'Manager', 'vehicles', 'edit') in params
    assert ('all', True, 'Manager', 'vehicles', 'delete') in params


def test_seed_emits_boolean_backfill_update():
    from migrations.domains.schema_roles import _seed_carpark_permissions_v2
    cursor, conn = MagicMock(), MagicMock()
    _seed_carpark_permissions_v2(cursor, conn)
    sqls = [c.args[0] for c in cursor.execute.call_args_list]
    assert any('UPDATE roles' in s and 'can_edit_carpark' in s for s in sqls)
    conn.commit.assert_called()
