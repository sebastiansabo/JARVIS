# CarPark Permissions Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the permissions matrix actually drive CarPark access/edit/delete/finance, scope the company switcher to own + org-responsable companies, and close the finance-data leak.

**Architecture:** Sync-bridge — keep the legacy `can_*_carpark` boolean columns that every CarPark decorator/Guard reads, but seed new `permissions_v2` rows (`carpark.vehicles.edit`, `carpark.vehicles.delete`, `carpark.finance.view`) and wire them into `_sync_v2_permissions_to_booleans` so any matrix save writes the booleans. A one-time seed backfill re-derives the booleans for all roles. Company selection is scoped via a new `get_actable_company_ids()` org-hierarchy helper, and `_acting_company_id()` stops trusting client input. Finance endpoints get a `carpark_finance_required` gate plus shared field-stripping.

**Tech Stack:** Python/Flask, psycopg2 raw SQL (`%s` params, no ORM), pytest (unittest.mock cursor mocking), React 19 + TypeScript + Tailwind + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-09-17-carpark-permissions-design.md`

## Global Constraints

- **Repo permission convention:** route checks normally use `@v2_permission_required`, but CarPark deliberately keeps its own boolean-backed decorators (`carpark_required`, `carpark_edit_required`, `carpark_delete_required`) — do NOT convert them.
- **Raw SQL only:** parameterise everything with `%s`; never f-string a user value into SQL. Repos subclass `core.base_repository.BaseRepository`.
- **Idempotent DDL/seed:** `INSERT ... ON CONFLICT DO NOTHING`; seeds safe to re-run on every boot.
- **DB tests:** force `os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')` at top of every test module (repo gotcha — DB-backed tests silently skip otherwise). Route tests use the real app with `psycopg2` mocked by the top-level conftest; mock the service/repo layer, never hit a real DB.
- **Admin flag:** there is no `is_admin` on the User model; `can_access_settings` is the de-facto admin flag.
- **No new columns:** the four `can_*_carpark` columns already exist on `roles`. Do not add or drop columns.
- **Pre-push checklist:** `cd jarvis/frontend && npm run build` (0 TS errors); `python -m pytest tests/ -x -q`; `python3 -m py_compile jarvis/app.py`; clean `git status`.
- **Line numbers** below are staging anchors (worktree `feature/carpark-permissions-matrix`); re-grep the symbol if a line has drifted.

---

### Task 1: Seed CarPark v2 entity permissions + explicit role defaults + boolean backfill

**Files:**
- Modify: `jarvis/migrations/domains/schema_roles.py` (add `_seed_carpark_permissions_v2`, near `_seed_business_control_permissions_v2` at :1108)
- Modify: `jarvis/migrations/domains/schema_marketing.py:429-430` (invoke it AFTER `_seed_sidebar_permissions_v2`)
- Test: `jarvis/tests/carpark/test_carpark_permission_seed.py` (new)

**Interfaces:**
- Produces: `_seed_carpark_permissions_v2(cursor, conn)` — inserts 3 `permissions_v2` rows (`carpark.vehicles.edit`, `carpark.vehicles.delete`, `carpark.finance.view`, all `is_scope_based=False`), explicit `role_permissions_v2` grants (Admin/Manager=all, User/Viewer=deny for every one), and a boolean backfill `UPDATE roles`. Called after the sidebar sweep so `carpark.module.access` grants already exist.

**Why after the sweep (not before, like business_control):** `finance.view` is a brand-new entity permission this function creates; the generic module.access sweep in `_seed_sidebar_permissions_v2` only ever touches `*.module.access` rows, so it cannot widen `finance.view`. Running after guarantees `carpark.module.access` grants exist for the backfill.

- [ ] **Step 1: Write the failing test**

```python
# jarvis/tests/carpark/test_carpark_permission_seed.py
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
    from jarvis.migrations.domains.schema_roles import _seed_carpark_permissions_v2
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
    from jarvis.migrations.domains.schema_roles import _seed_carpark_permissions_v2
    cursor, conn = MagicMock(), MagicMock()
    _seed_carpark_permissions_v2(cursor, conn)
    params = _params(cursor)
    assert ('all', True, 'Admin', 'vehicles', 'edit') in params
    assert ('all', True, 'Manager', 'vehicles', 'edit') in params
    assert ('all', True, 'Manager', 'vehicles', 'delete') in params


def test_seed_emits_boolean_backfill_update():
    from jarvis.migrations.domains.schema_roles import _seed_carpark_permissions_v2
    cursor, conn = MagicMock(), MagicMock()
    _seed_carpark_permissions_v2(cursor, conn)
    sqls = [c.args[0] for c in cursor.execute.call_args_list]
    assert any('UPDATE roles' in s and 'can_edit_carpark' in s for s in sqls)
    conn.commit.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_carpark_permission_seed.py -v`
Expected: FAIL with `ImportError: cannot import name '_seed_carpark_permissions_v2'`

- [ ] **Step 3: Add `_seed_carpark_permissions_v2` to `schema_roles.py`**

Insert immediately after `_seed_business_control_permissions_v2` (before `def _seed_sidebar_permissions_v2` at :1159):

```python
def _seed_carpark_permissions_v2(cursor, conn):
    """Seed CarPark entity permissions (edit/delete/finance) into permissions_v2
    and grant EXPLICIT per-role defaults, so the permissions matrix drives the
    can_*_carpark boolean columns via _sync_v2_permissions_to_booleans.

    carpark.module.access is seeded by _seed_sidebar_permissions_v2; this adds
    vehicles.edit, vehicles.delete and finance.view. Defaults: Admin/Manager = all,
    User/Viewer = deny (User must NOT get finance.view — hence explicit deny rows
    rather than relying on any generic view/access sweep).

    MUST run AFTER _seed_sidebar_permissions_v2 so carpark.module.access grants
    already exist for the boolean backfill below. Idempotent (ON CONFLICT DO NOTHING).
    """
    perms = [
        # entity,     entity_label,      action,   action_label, description,                               sort
        ('vehicles',  'Vehicles',        'edit',   'Edit',   'Create and edit vehicles',                     1),
        ('vehicles',  'Vehicles',        'delete', 'Delete', 'Delete vehicles',                              2),
        ('finance',   'Financial Data',  'view',   'View',   'View acquisition price, costs and margins',    3),
    ]
    for entity, entity_label, action, action_label, desc, sort in perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label,
                                        action_key, action_label, description, is_scope_based, sort_order)
            VALUES ('carpark', 'CarPark', 'bi-car-front', %s, %s, %s, %s, %s, FALSE, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', (entity, entity_label, action, action_label, desc, sort))

    # Explicit per-(perm, role) grants for ALL roles.
    role_scopes = [('Admin', 'all', True), ('Manager', 'all', True),
                   ('User', 'deny', False), ('Viewer', 'deny', False)]
    for entity, _el, action, _al, _d, _s in perms:
        for role_name, scope, granted in role_scopes:
            cursor.execute('''
                INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                SELECT r.id, p.id, %s, %s
                FROM roles r CROSS JOIN permissions_v2 p
                WHERE r.name = %s AND p.module_key = 'carpark'
                  AND p.entity_key = %s AND p.action_key = %s
                ON CONFLICT (role_id, permission_id) DO NOTHING
            ''', (scope, granted, role_name, entity, action))

    # One-time backfill: derive the boolean columns from current v2 grants for
    # every role that has carpark rows (seeding does not trigger the write-time
    # sync). Idempotent — re-affirms the same values on each boot.
    cursor.execute('''
        UPDATE roles r SET
          can_access_carpark       = x.access,
          can_edit_carpark         = x.edit,
          can_delete_carpark       = x.del_,
          can_view_carpark_finance = x.fin
        FROM (
          SELECT rp.role_id,
            bool_or(p.entity_key='module'   AND p.action_key='access' AND rp.scope <> 'deny') AS access,
            bool_or(p.entity_key='vehicles' AND p.action_key='edit'   AND rp.scope <> 'deny') AS edit,
            bool_or(p.entity_key='vehicles' AND p.action_key='delete' AND rp.scope <> 'deny') AS del_,
            bool_or(p.entity_key='finance'  AND p.action_key='view'   AND rp.scope <> 'deny') AS fin
          FROM role_permissions_v2 rp
          JOIN permissions_v2 p ON p.id = rp.permission_id
          WHERE p.module_key = 'carpark'
          GROUP BY rp.role_id
        ) x
        WHERE x.role_id = r.id
    ''')
    conn.commit()
```

- [ ] **Step 4: Wire the invocation in `schema_marketing.py`**

At `schema_marketing.py:423` add the import, and after line 429 (`_seed_sidebar_permissions_v2(cursor, conn)`) add the call:

```python
    from .schema_roles import (_seed_missing_permissions_v2, _seed_mobile_permissions_v2,
                               _seed_checkin_bypass_permission, _seed_business_control_permissions_v2,
                               _seed_sidebar_permissions_v2, _seed_carpark_permissions_v2)
    _seed_missing_permissions_v2(cursor, conn)
    _seed_mobile_permissions_v2(cursor, conn)
    _seed_checkin_bypass_permission(cursor, conn)
    _seed_business_control_permissions_v2(cursor, conn)
    _seed_sidebar_permissions_v2(cursor, conn)
    # Must run AFTER the sidebar sweep so carpark.module.access grants exist for
    # the boolean backfill, and so finance.view is created too late for the sweep.
    _seed_carpark_permissions_v2(cursor, conn)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_carpark_permission_seed.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Verify the migration runs clean against localhost defaultdb**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -c "from migrations.init_schema import init_db; init_db(); print('OK')"`
Expected: prints `OK`, no exception. Then confirm the rows:
Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -c "from core.base_repository import BaseRepository as B; r=B(); print(r.query_all(\"SELECT entity_key, action_key FROM permissions_v2 WHERE module_key='carpark' ORDER BY sort_order\"))"`
Expected: rows for `module/access`, `vehicles/edit`, `vehicles/delete`, `finance/view`.

- [ ] **Step 7: Commit**

```bash
git add jarvis/migrations/domains/schema_roles.py jarvis/migrations/domains/schema_marketing.py jarvis/tests/carpark/test_carpark_permission_seed.py
git commit -m "feat(carpark): seed v2 edit/delete/finance permissions + boolean backfill"
```

---

### Task 2: Wire CarPark keys into the v2→boolean sync

**Files:**
- Modify: `jarvis/core/roles/repositories/permission_repository.py:329-348` (`_sync_v2_permissions_to_booleans` `bool_updates`)
- Modify: `jarvis/core/roles/routes.py:191-198` (`MODULE_ACCESS_COLUMNS`)
- Test: `jarvis/tests/test_permissions.py` (add to `TestPermissionRepository`)

**Interfaces:**
- Consumes: the v2 keys `carpark.module.access`, `carpark.vehicles.edit`, `carpark.vehicles.delete`, `carpark.finance.view` (Task 1).
- Produces: on any `set_role_permission_v2` / `set_role_permissions_v2_bulk`, the four `can_*_carpark` booleans are written from the role's carpark v2 grants.

- [ ] **Step 1: Write the failing test**

```python
# append to jarvis/tests/test_permissions.py, inside class TestPermissionRepository
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_sync_writes_carpark_booleans(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'module_key': 'carpark', 'entity_key': 'module',   'action_key': 'access', 'scope': 'all',  'granted': True},
            {'module_key': 'carpark', 'entity_key': 'vehicles', 'action_key': 'edit',   'scope': 'all',  'granted': True},
            {'module_key': 'carpark', 'entity_key': 'vehicles', 'action_key': 'delete', 'scope': 'deny', 'granted': False},
            {'module_key': 'carpark', 'entity_key': 'finance',  'action_key': 'view',   'scope': 'deny', 'granted': False},
        ]
        from core.roles.repositories.permission_repository import PermissionRepository
        PermissionRepository()._sync_v2_permissions_to_booleans(mock_cursor, role_id=5)

        sql, values = mock_cursor.execute.call_args.args  # last call = the UPDATE
        cols = [c.split('=')[0].strip() for c in sql.split('SET', 1)[1].split('WHERE')[0].split(',')]
        mapping = dict(zip(cols, values[:-1]))
        assert mapping['can_access_carpark'] is True
        assert mapping['can_edit_carpark'] is True
        assert mapping['can_delete_carpark'] is False
        assert mapping['can_view_carpark_finance'] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/test_permissions.py::TestPermissionRepository::test_sync_writes_carpark_booleans -v`
Expected: FAIL with `KeyError: 'can_access_carpark'` (column not in the UPDATE)

- [ ] **Step 3: Add the four keys to `bool_updates`**

In `_sync_v2_permissions_to_booleans`, append inside the `bool_updates = { ... }` dict (after `'can_access_digest'` at :347):

```python
            'can_access_carpark':       perms.get('carpark.module.access', False),
            'can_edit_carpark':         perms.get('carpark.vehicles.edit', False),
            'can_delete_carpark':       perms.get('carpark.vehicles.delete', False),
            'can_view_carpark_finance': perms.get('carpark.finance.view', False),
```

- [ ] **Step 4: Add carpark to `MODULE_ACCESS_COLUMNS`**

In `routes.py` `MODULE_ACCESS_COLUMNS` (:191), add:

```python
        'carpark':    'can_access_carpark',
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/test_permissions.py::TestPermissionRepository::test_sync_writes_carpark_booleans -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add jarvis/core/roles/repositories/permission_repository.py jarvis/core/roles/routes.py jarvis/tests/test_permissions.py
git commit -m "feat(carpark): sync carpark v2 permissions to boolean columns on matrix save"
```

---

### Task 3: `get_actable_company_ids` org-hierarchy helper

**Files:**
- Modify: `jarvis/core/organization/manager_utils.py` (add function near `get_visible_tree` at :147)
- Test: `jarvis/tests/org/test_actable_company_ids.py` (new)

**Interfaces:**
- Consumes: `get_visible_tree(user_id)` (returns `{'companies': [{'company_id': int}], 'nodes': [{'company_id': int}]}`).
- Produces: `get_actable_company_ids(user_id: int) -> set[int]` — own `users.company_id` ∪ L0 company_responsables ∪ Sincron responsable subtree company ids. Callers apply the Admin (`can_access_settings`) bypass themselves.

- [ ] **Step 1: Write the failing test**

```python
# jarvis/tests/org/test_actable_company_ids.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/org/test_actable_company_ids.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_actable_company_ids'`

- [ ] **Step 3: Implement the helper**

Add to `manager_utils.py` after `get_visible_tree` (:197):

```python
def get_actable_company_ids(user_id):
    """Set of company ids a user may act on in CarPark: own company +
    L0 company_responsables + companies under their Sincron responsable subtree.

    Admin bypass (can_access_settings -> all companies) is the caller's
    responsibility; this returns only the user's scoped set.
    """
    ids = set()
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute(
            'SELECT company_id FROM users WHERE id = %s AND company_id IS NOT NULL',
            (user_id,))
        row = cursor.fetchone()
        if row and row.get('company_id'):
            ids.add(row['company_id'])
    finally:
        release_db(conn)

    # get_visible_tree already returns L0 companies + the Sincron responsable subtree,
    # each element carrying a company_id.
    tree = get_visible_tree(user_id)
    ids |= {c['company_id'] for c in tree.get('companies', []) if c.get('company_id')}
    ids |= {n['company_id'] for n in tree.get('nodes', []) if n.get('company_id')}
    return ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/org/test_actable_company_ids.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/organization/manager_utils.py jarvis/tests/org/test_actable_company_ids.py
git commit -m "feat(org): add get_actable_company_ids (own + responsable companies)"
```

---

### Task 4: Scope the company switcher list

**Files:**
- Modify: `jarvis/carpark/repositories/vehicle_repository.py:496-498` (`list_companies`)
- Modify: `jarvis/carpark/services/vehicle_service.py:284-286` (`get_companies`)
- Modify: `jarvis/carpark/routes/vehicles.py:541-544` (`list_companies` route)
- Test: `jarvis/tests/carpark/test_company_scope.py` (new)

**Interfaces:**
- Consumes: `get_actable_company_ids` (Task 3), `current_user.can_access_settings`, `current_user.id`.
- Produces: `VehicleRepository.list_companies(company_ids: set|None)`, `VehicleService.get_companies(company_ids=None)`; route returns only the user's scoped companies (Admin → all).

- [ ] **Step 1: Write the failing test**

```python
# jarvis/tests/carpark/test_company_scope.py
"""Company-switcher scoping: /api/carpark/companies returns only the
companies a non-Admin may act on; Admin gets all. Real app + mocked service,
mirrors tests/carpark/test_acting_company.py."""
import os
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
import app as app_module
from app import app as flask_app
from carpark.routes import vehicles as vehicles_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, company_id=1, **overrides):
    user = {'id': uid, 'email': f't{uid}@x.com', 'name': 'T', 'company_id': company_id,
            'can_access_carpark': True, 'can_edit_carpark': True}
    user.update(overrides)
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _u: user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


def test_non_admin_gets_scoped_companies(client, monkeypatch):
    _login(client, monkeypatch, uid=92001, company_id=1)
    monkeypatch.setattr(vehicles_module, 'get_actable_company_ids', lambda _u: {1, 4})
    with mock.patch.object(vehicles_module._vehicle_service, 'get_companies',
                            return_value=[{'id': 1, 'name': 'A'}, {'id': 4, 'name': 'D'}]) as gc:
        r = client.get('/api/carpark/companies')
    assert r.status_code == 200
    assert gc.call_args.kwargs.get('company_ids') == {1, 4} or gc.call_args.args[0] == {1, 4}


def test_admin_gets_all_companies(client, monkeypatch):
    _login(client, monkeypatch, uid=92002, company_id=1, can_access_settings=True)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_companies',
                            return_value=[{'id': 1, 'name': 'A'}]) as gc:
        r = client.get('/api/carpark/companies')
    assert r.status_code == 200
    passed = gc.call_args.kwargs.get('company_ids', gc.call_args.args[0] if gc.call_args.args else None)
    assert passed is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_company_scope.py -v`
Expected: FAIL (get_companies called with no args / AttributeError on get_actable_company_ids)

- [ ] **Step 3: Add the repo filter**

Replace `list_companies` in `vehicle_repository.py`:

```python
    def list_companies(self, company_ids=None) -> List[Dict[str, Any]]:
        """Companies for the tenant-switcher selector. company_ids=None returns
        all (Admin); an empty/other set restricts to those ids."""
        if company_ids is None:
            return self.query_all('SELECT id, company AS name FROM companies ORDER BY company')
        if not company_ids:
            return []
        return self.query_all(
            'SELECT id, company AS name FROM companies WHERE id = ANY(%s) ORDER BY company',
            (list(company_ids),))
```

- [ ] **Step 4: Thread it through the service**

Replace `get_companies` in `vehicle_service.py`:

```python
    def get_companies(self, company_ids=None) -> List[Dict[str, Any]]:
        """Companies for the tenant-switcher selector (None = all)."""
        return self._repo.list_companies(company_ids)
```

- [ ] **Step 5: Scope the route + import the helper**

In `vehicles.py`, add the import near the top (after the existing carpark imports, ~:10):

```python
from core.organization.manager_utils import get_actable_company_ids
```

Replace the `list_companies` route body (:541):

```python
@carpark_bp.route('/companies', methods=['GET'])
@login_required
@carpark_required
def list_companies():
    """Companies for the tenant-switcher, scoped to the caller's own +
    org-responsable companies (Admin sees all)."""
    if getattr(current_user, 'can_access_settings', False):
        company_ids = None
    else:
        company_ids = get_actable_company_ids(current_user.id)
    companies = _vehicle_service.get_companies(company_ids=company_ids)
    return jsonify({'companies': _serialize(companies)})
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_company_scope.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add jarvis/carpark/repositories/vehicle_repository.py jarvis/carpark/services/vehicle_service.py jarvis/carpark/routes/vehicles.py jarvis/tests/carpark/test_company_scope.py
git commit -m "feat(carpark): scope company switcher to own + responsable companies"
```

---

### Task 5: Authorize `_acting_company_id` (stop trusting client input)

**Files:**
- Modify: `jarvis/carpark/routes/vehicles.py:70-84` (`_acting_company_id`) + flask imports (:5)
- Modify: `jarvis/tests/carpark/test_acting_company.py` (rewrite the permissive-behavior tests)

**Interfaces:**
- Consumes: `get_actable_company_ids` (Task 3), `current_user.can_access_settings`.
- Produces: `_acting_company_id()` returns the requested company id only if the caller may act on it, else aborts **403** (JSON `{'success': False, 'error': 'Company not permitted'}`); absent → own company. Admin bypasses. All existing callers (list/create/analytics/pricing/publishing) inherit the check.

- [ ] **Step 1: Rewrite the affected tests to the new authorization model**

Replace the three permissive tests in `test_acting_company.py` (`test_list_vehicles_uses_requested_company_id`, `test_create_vehicle_uses_requested_company_id`, `test_analytics_summary_uses_requested_company_id`) and add authorization tests. Keep the two `_verify_vehicle_ownership` tests (behavior unchanged). Also extend `_login` callers to control the allowed set via monkeypatching `get_actable_company_ids`:

```python
def test_list_vehicles_allows_permitted_company(client, monkeypatch):
    """?company_id=11 honored when the caller may act on company 11."""
    _login(client, monkeypatch, uid=91001, company_id=1)
    monkeypatch.setattr(vehicles_module, 'get_actable_company_ids', lambda _u: {1, 11})
    with mock.patch.object(vehicles_module._vehicle_service, 'get_catalog',
                            return_value={'vehicles': [], 'total': 0}) as get_catalog:
        r = client.get('/api/carpark/vehicles?company_id=11')
    assert r.status_code == 200
    assert get_catalog.call_args.args[0]['company_id'] == '11'


def test_list_vehicles_forbids_unpermitted_company(client, monkeypatch):
    """?company_id=11 rejected with 403 when the caller may not act on it."""
    _login(client, monkeypatch, uid=91011, company_id=1)
    monkeypatch.setattr(vehicles_module, 'get_actable_company_ids', lambda _u: {1})
    r = client.get('/api/carpark/vehicles?company_id=11')
    assert r.status_code == 403


def test_admin_may_act_on_any_company(client, monkeypatch):
    _login(client, monkeypatch, uid=91012, company_id=1, can_access_settings=True)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_catalog',
                            return_value={'vehicles': [], 'total': 0}) as get_catalog:
        r = client.get('/api/carpark/vehicles?company_id=999')
    assert r.status_code == 200
    assert get_catalog.call_args.args[0]['company_id'] == '999'


def test_create_vehicle_allows_permitted_company(client, monkeypatch):
    _login(client, monkeypatch, uid=91003, company_id=1)
    monkeypatch.setattr(vehicles_module, 'get_actable_company_ids', lambda _u: {1, 11})
    with mock.patch.object(vehicles_module._vehicle_service, 'create_vehicle',
                            return_value={'id': 55, 'vin': 'X' * 17, 'company_id': 11}) as create:
        r = client.post('/api/carpark/vehicles',
                        json={'vin': 'X' * 17, 'brand': 'BMW', 'model': 'X5', 'company_id': 11})
    assert r.status_code == 201
    assert create.call_args.args[0]['company_id'] == 11


def test_analytics_summary_forbids_unpermitted_company(client, monkeypatch):
    _login(client, monkeypatch, uid=91004, company_id=1)
    monkeypatch.setattr(vehicles_module, 'get_actable_company_ids', lambda _u: {1})
    r = client.get('/api/carpark/analytics/summary?company_id=11')
    assert r.status_code == 403
```

Update the module docstring's "NO authorization" wording to reflect the new authorized behavior.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_acting_company.py -v`
Expected: FAIL — `test_list_vehicles_forbids_unpermitted_company` and `test_analytics_summary_forbids_unpermitted_company` return 200 not 403 (no authorization yet).

- [ ] **Step 3: Add the flask imports**

In `vehicles.py:5`, extend the flask import:

```python
from flask import request, jsonify, abort, make_response
```

- [ ] **Step 4: Enforce authorization in `_acting_company_id`**

Replace `_acting_company_id` (:70):

```python
def _acting_company_id():
    """Company the caller is acting as: a request-provided company_id if the
    caller may act on it (own + org-responsable companies; Admin = any), else
    aborts 403. Absent company_id falls back to the user's own company."""
    if request.method == 'GET':
        cid = request.args.get('company_id')
    else:
        body = request.get_json(silent=True) or request.form
        cid = body.get('company_id') if body else None

    if cid not in (None, ''):
        try:
            cid_int = int(cid)
        except (TypeError, ValueError):
            cid_int = None
        if cid_int is not None:
            is_admin = getattr(current_user, 'can_access_settings', False)
            if not is_admin and cid_int not in get_actable_company_ids(current_user.id):
                abort(make_response(
                    jsonify({'success': False, 'error': 'Company not permitted'}), 403))
            return cid_int
    return getattr(current_user, 'company_id', None)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_acting_company.py -v`
Expected: PASS (all, including the two retained ownership tests)

- [ ] **Step 6: Commit**

```bash
git add jarvis/carpark/routes/vehicles.py jarvis/tests/carpark/test_acting_company.py
git commit -m "feat(carpark): authorize acting company_id against actable set (was permissive)"
```

---

### Task 6: `carpark_finance_required` gate on purely-financial endpoints

**Files:**
- Modify: `jarvis/carpark/routes/vehicles.py` (add `carpark_finance_required` after `carpark_delete_required` at :60)
- Modify: `jarvis/carpark/routes/costs.py` (import + decorate cost/cost-line/revenue GETs + `/profitability`)
- Modify: `jarvis/carpark/routes/pricing.py` (decorate `/floor-price`, `/pricing-history`)
- Modify: `jarvis/carpark/routes/analytics.py` (decorate `/analytics/costs`)
- Test: `jarvis/tests/carpark/test_finance_gate.py` (new)

**Interfaces:**
- Consumes: `current_user.can_view_carpark_finance`.
- Produces: `carpark_finance_required` decorator (stacks after `carpark_required`; 403 without the flag). Applied to all read endpoints whose entire payload is financial.

- [ ] **Step 1: Write the failing test**

```python
# jarvis/tests/carpark/test_finance_gate.py
"""carpark_finance_required blocks purely-financial reads for users without
can_view_carpark_finance. Real app + mocked service (mirrors test_acting_company.py)."""
import os
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
import app as app_module
from app import app as flask_app
from carpark.routes import costs as costs_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, finance=False):
    user = {'id': uid, 'email': f't{uid}@x.com', 'name': 'T', 'company_id': 1,
            'can_access_carpark': True, 'can_edit_carpark': True,
            'can_view_carpark_finance': finance}
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _u: user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


def test_profitability_forbidden_without_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=93001, finance=False)
    r = client.get('/api/carpark/vehicles/1/profitability')
    assert r.status_code == 403


def test_profitability_allowed_with_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=93002, finance=True)
    with mock.patch.object(costs_module._vehicle_service, 'get_profitability',
                            return_value={'profit': 0}):
        r = client.get('/api/carpark/vehicles/1/profitability')
    assert r.status_code == 200
```

> Note: confirm the exact service attribute/method names in `costs.py` (`_vehicle_service.get_profitability` or similar) when writing Step 1; adjust the mock target to match.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_finance_gate.py -v`
Expected: FAIL — profitability returns 200 without finance.

- [ ] **Step 3: Add the decorator**

In `vehicles.py` after `carpark_delete_required` (:60):

```python
def carpark_finance_required(f):
    """Require can_view_carpark_finance for endpoints whose entire payload is
    financial (costs, revenues, margins, profitability)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not getattr(current_user, 'can_access_carpark', False):
            return jsonify({'success': False, 'error': 'CarPark access denied'}), 403
        if not getattr(current_user, 'can_view_carpark_finance', False):
            return jsonify({'success': False, 'error': 'CarPark finance permission denied'}), 403
        return f(*args, **kwargs)
    return decorated
```

- [ ] **Step 4: Apply the decorator to purely-financial GET routes**

In `costs.py`, import it (`from carpark.routes.vehicles import carpark_finance_required`) and swap `@carpark_required` → `@carpark_finance_required` on the GET routes for `/costs`, `/costs/totals`, `/cost-lines*`, `/revenues`, `/revenues/totals`, `/profitability`. Do the same in `pricing.py` for `/floor-price` and `/pricing-history`, and in `analytics.py` for `/analytics/costs`. Leave the write (`@carpark_edit_required`) routes as-is.

> For each file: `grep -n "@carpark_required" jarvis/carpark/routes/costs.py` to enumerate, then change only the GET read routes listed above.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_finance_gate.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add jarvis/carpark/routes/vehicles.py jarvis/carpark/routes/costs.py jarvis/carpark/routes/pricing.py jarvis/carpark/routes/analytics.py jarvis/tests/carpark/test_finance_gate.py
git commit -m "feat(carpark): gate purely-financial endpoints behind carpark_finance_required"
```

---

### Task 7: Shared finance field-stripping on mixed endpoints + write payloads

**Files:**
- Create: `jarvis/carpark/finance_guard.py`
- Modify: `jarvis/carpark/routes/dispo.py:36-79` (use the shared helper)
- Modify: `jarvis/carpark/routes/vehicles.py` (`GET /vehicles/<id>` strip; `PUT /vehicles/<id>` drop finance fields from body for non-finance users)
- Modify: `jarvis/carpark/routes/analytics.py` (`/analytics/dashboard`, `/analytics/kpis` strip)
- Test: `jarvis/tests/carpark/test_finance_strip.py` (new)

**Interfaces:**
- Produces: `finance_guard.FINANCE_VEHICLE_FIELDS: tuple`, `finance_guard.strip_finance_fields(payload: dict, fields) -> dict` (mutates + returns). Dispo keeps `_FINANCE_ROW_FIELDS`/`_FINANCE_KPI_FIELDS` but sources them from `finance_guard`.

- [ ] **Step 1: Write the failing test**

```python
# jarvis/tests/carpark/test_finance_strip.py
import os
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
import app as app_module
from app import app as flask_app
from carpark.routes import vehicles as vehicles_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, finance=False):
    user = {'id': uid, 'email': f't{uid}@x.com', 'name': 'T', 'company_id': 1,
            'can_access_carpark': True, 'can_edit_carpark': True,
            'can_view_carpark_finance': finance}
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _u: user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


def test_get_vehicle_strips_acquisition_price_without_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=94001, finance=False)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_vehicle',
                            return_value={'id': 1, 'vin': 'X'*17, 'acquisition_price': 12345,
                                          'total_costs': 500, 'gross_margin': 800}):
        r = client.get('/api/carpark/vehicles/1')
    assert r.status_code == 200
    body = r.get_json()
    assert 'acquisition_price' not in body and 'gross_margin' not in body


def test_get_vehicle_keeps_finance_with_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=94002, finance=True)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_vehicle',
                            return_value={'id': 1, 'vin': 'X'*17, 'acquisition_price': 12345}):
        r = client.get('/api/carpark/vehicles/1')
    assert r.get_json().get('acquisition_price') == 12345
```

> Adjust the assertion to the real envelope shape of `GET /vehicles/<id>` (it may wrap the vehicle under a key) when writing Step 1.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_finance_strip.py -v`
Expected: FAIL — `acquisition_price` still present.

- [ ] **Step 3: Create the shared guard**

```python
# jarvis/carpark/finance_guard.py
"""Single source of truth for CarPark finance fields hidden from users
without can_view_carpark_finance. Used by the Dispo board, the vehicle
detail payload and analytics so JSON/xlsx paths can never drift."""

# Money fields on a vehicle / dispo row.
FINANCE_VEHICLE_FIELDS = ('acquisition_price', 'total_costs', 'gross_margin',
                          'margin_pct', 'bonus_leasing')
# Money fields on analytics KPI blocks.
FINANCE_KPI_FIELDS = ('gross_margin_mtd',)


def strip_finance_fields(payload, fields=FINANCE_VEHICLE_FIELDS):
    """Remove `fields` from a dict in place; returns it. No-op if not a dict."""
    if isinstance(payload, dict):
        for f in fields:
            payload.pop(f, None)
    return payload
```

- [ ] **Step 4: Point dispo at the shared constants**

In `dispo.py`, replace the local field tuples (:39-41) with imports and keep the existing `_strip_finance` working:

```python
from carpark.finance_guard import FINANCE_VEHICLE_FIELDS as _FINANCE_ROW_FIELDS, \
    FINANCE_KPI_FIELDS as _FINANCE_KPI_FIELDS
```
(Delete the two literal tuple definitions; the rest of `dispo.py` keeps using `_FINANCE_ROW_FIELDS`/`_FINANCE_KPI_FIELDS` unchanged.)

- [ ] **Step 5: Strip in `GET /vehicles/<id>` and analytics**

In `vehicles.py` `get_vehicle` route, after fetching the vehicle and before serializing, add:

```python
    from carpark.finance_guard import strip_finance_fields
    if not getattr(current_user, 'can_view_carpark_finance', False):
        strip_finance_fields(vehicle)
```

In `PUT /vehicles/<id>`, alongside the existing `company_id` stripping, drop finance fields from the request body when the user lacks finance (so a non-finance editor can't set/overwrite acquisition price):

```python
    from carpark.finance_guard import strip_finance_fields
    if not getattr(current_user, 'can_view_carpark_finance', False):
        strip_finance_fields(data)  # data = the incoming update dict
```

In `analytics.py` `/analytics/dashboard` and `/analytics/kpis`, strip `FINANCE_VEHICLE_FIELDS` + `FINANCE_KPI_FIELDS` from the result dict when the flag is absent (mirror the dispo pattern).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark/test_finance_strip.py tests/carpark/test_dispo_routes.py -v`
Expected: PASS (new strip tests + existing dispo tests still green after the refactor)

- [ ] **Step 7: Commit**

```bash
git add jarvis/carpark/finance_guard.py jarvis/carpark/routes/dispo.py jarvis/carpark/routes/vehicles.py jarvis/carpark/routes/analytics.py jarvis/tests/carpark/test_finance_strip.py
git commit -m "feat(carpark): centralize finance field-stripping; apply to vehicle detail, PUT, analytics"
```

---

### Task 8: Frontend — gate finance tabs + tidy the switcher

**Files:**
- Modify: `jarvis/frontend/src/pages/CarPark/Detail.tsx:404-407,618-619,648-655`
- Modify: `jarvis/frontend/src/pages/CarPark/index.tsx:356`

**Interfaces:**
- Consumes: `user.can_view_carpark_finance` from `useAuthStore`.
- Produces: Costuri/Venituri tabs + content hidden without finance; company `<Select>` hidden when ≤1 company.

- [ ] **Step 1: Derive `canViewFinance` in Detail.tsx**

After line 406 (`const canDelete = user?.can_delete_carpark ?? false`), add:

```tsx
  const canViewFinance = user?.can_view_carpark_finance ?? false
```

- [ ] **Step 2: Gate the finance tabs and their content**

Wrap the two `TabsTrigger` (:618-619) and their `TabsContent` (`value="costs"` :648 and `value="revenues"` :655) in `{canViewFinance && ( ... )}`:

```tsx
          {canViewFinance && (
            <TabsTrigger value="costs">Costuri ({parseCostLines(vehicle.cost_lines).length})</TabsTrigger>
          )}
          {canViewFinance && (
            <TabsTrigger value="revenues">Venituri ({revenues.length})</TabsTrigger>
          )}
```
and likewise wrap each of the two `<TabsContent value="costs">…</TabsContent>` / `<TabsContent value="revenues">…</TabsContent>` blocks.

- [ ] **Step 3: Hide the switcher when only one company**

In `index.tsx:356`, change the render guard:

```tsx
            {companies.length > 1 && effectiveCompanyId != null && (
```

- [ ] **Step 4: Verify the build**

Run: `cd jarvis/frontend && npm run build`
Expected: exit 0, zero TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/CarPark/Detail.tsx jarvis/frontend/src/pages/CarPark/index.tsx
git commit -m "feat(carpark): hide finance tabs without permission; hide single-company switcher"
```

---

### Task 9: Full verification + pre-promotion cleanup

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/ -x -q`
Expected: green. Investigate any failure before proceeding.

- [ ] **Step 2: Compile check**

Run: `cd jarvis && python3 -m py_compile app.py`
Expected: no output (success).

- [ ] **Step 3: Frontend build**

Run: `cd jarvis/frontend && npm run build`
Expected: exit 0, zero TS errors.

- [ ] **Step 4: Manual smoke (local, against localhost defaultdb)**

Start the app (`/run` skill or the repo's dev command). Verify:
- A Manager (matrix CarPark = access/edit/finance) sees the CarPark sidebar entry, the company switcher populated with their own + responsable companies, and can select their own company.
- A user without finance sees no Costuri/Venituri tabs and gets 403 on `/api/carpark/vehicles/<id>/profitability`.
- Requesting `?company_id=<foreign>` returns 403 for a non-admin.

- [ ] **Step 5: Confirm the plan/spec docs are excluded before FF-promotion**

The spec + this plan live under `docs/superpowers/`. Per the "no plan docs on staging/prod" preference, remove them from the branch tip before `git push origin feature/...:staging`:

```bash
git rm docs/superpowers/specs/2026-09-17-carpark-permissions-design.md docs/superpowers/plans/2026-09-17-carpark-permissions-matrix.md
git commit -m "chore: drop planning docs before promotion"
```
(Do this only at promotion time; keep them while implementing.)

- [ ] **Step 6: Push to staging, then main after double confirmation**

Follow the repo workflow: `git push origin feature/carpark-permissions-matrix:staging`, verify `/health` + a Manager login on staging, then promote to main **only after explicit double confirmation** from the user.

---

## Self-Review

**Spec coverage:**
- §3.1 new v2 catalog → Task 1. §3.2 seed/sync/backfill → Task 1 (seed+backfill) + Task 2 (sync). §3.3 company scoping → Task 3 (helper) + Task 4 (list) + Task 5 (`_acting_company_id`). §3.4 finance leak → Task 6 (gate) + Task 7 (strip). §3.5 frontend → Task 8. §5 testing → per-task tests + Task 9. §6 rollout → Task 9. All spec sections mapped.
- Deviation from spec: `_seed_carpark_permissions_v2` runs AFTER the sidebar sweep (spec loosely implied "before", mirroring business_control) — justified in Task 1 (finance.view is created too late for the sweep to widen; module.access grants exist for the backfill). Spec §3.3's optional `_require_acting_company_id` companion was folded into `_acting_company_id` itself (centralized 403) — fewer route edits.

**Placeholder scan:** Two steps (Task 6 Step 1, Task 7 Step 1) flag "confirm exact service method / envelope shape when writing the test" — these are verification instructions, not placeholders; the surrounding code is concrete. No TBD/TODO left in implementation code.

**Type consistency:** `get_actable_company_ids(user_id) -> set[int]` used identically in Tasks 3/4/5. `strip_finance_fields`/`FINANCE_VEHICLE_FIELDS`/`FINANCE_KPI_FIELDS` names consistent across Task 7 and dispo refactor. `get_companies(company_ids=...)` / `list_companies(company_ids=...)` keyword consistent across repo/service/route in Task 4. `canViewFinance` consistent in Task 8.
