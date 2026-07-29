# Repoint manager/team visibility to the Sincron organigram — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the 3 functions in `jarvis/core/organization/manager_utils.py` so the L1–L5 manager/team tree is sourced from the **Sincron organigram** (`sincron_org_nodes`/`sincron_org_members`) instead of `structure_nodes`; L0 (`company_responsables`) unchanged; signatures/return-shapes identical so the ~10 consumers need no edits.

**Architecture:** The three functions keep their exact contracts. Each recursive descent moves from `structure_nodes` to `sincron_org_nodes` (over `parent_id`), `role 'team' → 'member'`, and the member→user link goes through `sincron_employees.mapped_jarvis_user_id` (one extra join). The L0 branch (`company_responsables` → whole company) is copied through unchanged. Rewrite stays in the file's existing raw-`get_db()`/cursor style (no new repository).

**Tech Stack:** Python 3 / Flask, PostgreSQL (recursive CTEs), pytest against localhost/defaultdb.

## Global Constraints

- **Backend repo:** `/Users/sebastiansabo/Documents/Git/JARVIS`, branch **`dev`** (dev is clear; build here). No pushes during implementation.
- **Backend tests run on localhost/defaultdb ONLY** (`postgresql://localhost/defaultdb`). NEVER staging/prod. Reuse the CI-safe DB-test pattern (real-psycopg2 bypass + skip when no DB) so `pytest tests/` stays green in CI (no Postgres there).
- **L0 is unchanged** — every `company_responsables` query is copied verbatim from the current code.
- **Contracts are frozen** — `is_manager(user_id) -> bool`; `get_managed_employee_ids(user_id, node_id=None) -> list[int]`; `get_visible_tree(user_id) -> {'companies': [...], 'nodes': [...]}` with node dicts `{'id','name','level','parent_id','company_id'}` and company dicts `{'id':'company-<id>','name','level':0,'parent_id':None,'company_id'}`.
- **Sincron member→user hop (verbatim):** `JOIN sincron_employees se ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name` with `se.mapped_jarvis_user_id IS NOT NULL AND se.is_active = TRUE`.
- **Parameterized SQL only** (`%s`), no f-strings in queries.
- **Accounting is out of scope** — do not touch `core/utils/org_scope.py` or anything under `jarvis/accounting/`.
- **Deploy is later** — via surgical cherry-pick to staging→main (not this plan). Spec: `docs/superpowers/specs/2026-07-29-team-sincron-organigram-design.md`; drop docs before staging/main.
- **Commit convention:** `type(scope): desc`, scope `organization`.

---

## File Structure

- `jarvis/core/organization/manager_utils.py` — **modify**: rewrite the 3 functions (Tasks 2–4).
- `jarvis/tests/org/__init__.py` — **create** (empty package marker).
- `jarvis/tests/org/conftest.py` — **create**: CI-safe psycopg2 bypass + `REAL_DB_AVAILABLE` probe + `org_fixture` seeded topology + cleanup.
- `jarvis/tests/org/test_manager_utils_sincron.py` — **create**: fixture-sanity + all three functions' tests.

---

## Task 1: Test package + CI-safe seeded `org_fixture`

**Files:**
- Create: `jarvis/tests/org/__init__.py` (empty)
- Create: `jarvis/tests/org/conftest.py`
- Create: `jarvis/tests/org/test_manager_utils_sincron.py` (fixture-sanity test only in this task)

**Interfaces:**
- Produces: pytest fixture `org_fixture` yielding an `ids` dict with keys: `company_id`, `user_L0`, `user_M`, `user_A`, `user_B`, `user_D`, `user_X`, `node_P`, `node_Ch`. Topology: company `CT`; users all with `company_id=CT`; `company_responsables(user_L0, CT)`; Sincron nodes `P`(level 1) and `Ch`(level 2, parent P); `M` responsable on P; `A`,`B` members on Ch; `D` member on P; one **unmapped** member `U` on Ch (its `sincron_employees.mapped_jarvis_user_id IS NULL`); `X` is in company CT but in no Sincron node. Also produces `REAL_DB_AVAILABLE` (module attr) so DB tests skip when no real DB.

- [ ] **Step 1: Create the empty package marker**

Create `jarvis/tests/org/__init__.py` (empty file).

- [ ] **Step 2: Create the conftest with CI-safe bypass + fixture**

Create `jarvis/tests/org/conftest.py`. The psycopg2-bypass/probe block mirrors `jarvis/tests/dept_pulse/conftest.py` (real driver locally; skip when no DB in CI):

```python
"""Seeded Sincron-org fixture for manager_utils tests. localhost/defaultdb only.

Topology:
    company CT (isolated test company)
      users (all company_id=CT): L0, M, A, B, D, X
      company_responsables: (L0, CT)          # L0 sees whole company
      sincron_org_nodes: P (level 1) -> Ch (level 2)
      sincron_org_members: M responsable@P; A,B member@Ch; D member@P;
                           U(unmapped) member@Ch
      X: in company CT but in NO sincron node
"""
import os
import sys
import importlib
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

# ── CI-safe real-psycopg2 bypass + probe (mirrors tests/dept_pulse/conftest.py) ──
_SAVED = {}
REAL_DB_AVAILABLE = False


def _restore():
    for name, mod in _SAVED.items():
        if mod is not None:
            sys.modules[name] = mod


def _probe_real_db():
    global REAL_DB_AVAILABLE
    names = ('psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'psycopg2.errors')
    for n in names:
        _SAVED[n] = sys.modules.get(n)
        if isinstance(sys.modules.get(n), MagicMock):
            del sys.modules[n]
    try:
        import psycopg2  # noqa: F401  real driver
        import psycopg2.pool, psycopg2.extras, psycopg2.errors  # noqa: F401
        import database as _db
        if isinstance(getattr(_db, 'psycopg2', None), MagicMock) or isinstance(getattr(_db, 'pool', None), MagicMock):
            _db.psycopg2 = sys.modules['psycopg2']
            _db.pool = sys.modules['psycopg2.pool']
            _db._connection_pool = None
        from database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('SELECT 1')
            cur.fetchone()
            REAL_DB_AVAILABLE = True
        finally:
            release_db(conn)
    except Exception:
        REAL_DB_AVAILABLE = False
        _restore()


_probe_real_db()

import pytest
from database import get_db, get_cursor, release_db

_MARK = 'ZZ_ORG_TEST_CO'


@pytest.fixture
def org_fixture():
    if not REAL_DB_AVAILABLE:
        pytest.skip('no real DB available (CI)')
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    ids = {}
    try:
        cur.execute("INSERT INTO companies (company, vat) VALUES (%s, %s) RETURNING id",
                    (_MARK, 'ZZORGTESTVAT'))
        ids['company_id'] = cur.fetchone()['id']
        cid = ids['company_id']

        for key in ('L0', 'M', 'A', 'B', 'D', 'X'):
            cur.execute(
                "INSERT INTO users (name, email, company_id, is_active) VALUES (%s, %s, %s, TRUE) RETURNING id",
                (f'Org {key}', f'org_{key.lower()}@example.invalid', cid),
            )
            ids[f'user_{key}'] = cur.fetchone()['id']

        cur.execute("INSERT INTO company_responsables (user_id, company_id) VALUES (%s, %s)",
                    (ids['user_L0'], cid))

        cur.execute("""INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
                       VALUES (%s, NULL, 'Org P', 'department', 1) RETURNING id""", (cid,))
        ids['node_P'] = cur.fetchone()['id']
        cur.execute("""INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
                       VALUES (%s, %s, 'Org Ch', 'team', 2) RETURNING id""", (cid, ids['node_P']))
        ids['node_Ch'] = cur.fetchone()['id']

        # sincron_employees mapping (M,A,B,D mapped; U unmapped) + org members
        def emp(se_id, mapped):
            cur.execute("""INSERT INTO sincron_employees
                             (sincron_employee_id, company_name, mapped_jarvis_user_id, is_active)
                           VALUES (%s, %s, %s, TRUE)""", (se_id, _MARK, mapped))

        emp('ORG_M', ids['user_M']); emp('ORG_A', ids['user_A'])
        emp('ORG_B', ids['user_B']); emp('ORG_D', ids['user_D'])
        emp('ORG_U', None)  # unmapped

        def mem(node, se_id, role):
            cur.execute("""INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
                           VALUES (%s, %s, %s, %s)""", (node, se_id, _MARK, role))

        mem(ids['node_P'], 'ORG_M', 'responsable')
        mem(ids['node_Ch'], 'ORG_A', 'member')
        mem(ids['node_Ch'], 'ORG_B', 'member')
        mem(ids['node_P'], 'ORG_D', 'member')
        mem(ids['node_Ch'], 'ORG_U', 'member')  # unmapped
        conn.commit()
        yield ids
    finally:
        cur.execute("DELETE FROM sincron_org_nodes WHERE id IN (%s, %s)",
                    (ids.get('node_Ch'), ids.get('node_P')))  # cascades to members
        cur.execute("DELETE FROM sincron_employees WHERE company_name = %s", (_MARK,))
        cur.execute("DELETE FROM company_responsables WHERE company_id = %s", (ids.get('company_id'),))
        cur.execute("DELETE FROM users WHERE id = ANY(%s)",
                    ([v for k, v in ids.items() if k.startswith('user_')],))
        cur.execute("DELETE FROM companies WHERE id = %s", (ids.get('company_id'),))
        conn.commit()
        release_db(conn)
```

- [ ] **Step 3: Write the fixture-sanity test**

Create `jarvis/tests/org/test_manager_utils_sincron.py` with just:

```python
"""manager_utils Sincron repoint — tests. localhost/defaultdb only."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import psycopg2  # noqa: F401


def test_fixture_seeds_expected_topology(org_fixture):
    from database import get_db, get_cursor, release_db
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT count(*) AS n FROM sincron_org_members WHERE company_name = 'ZZ_ORG_TEST_CO'")
        assert cur.fetchone()['n'] == 5
        cur.execute("SELECT count(*) AS n FROM users WHERE company_id = %s", (org_fixture['company_id'],))
        assert cur.fetchone()['n'] == 6
    finally:
        release_db(conn)
```

- [ ] **Step 4: Run the sanity test**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/org/test_manager_utils_sincron.py -v`
Expected: PASS (1 passed). If `companies` requires more NOT NULL columns than `company, vat`, add them to the fixture INSERT and re-run.

- [ ] **Step 5: Leak check + commit**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -c "import psycopg2,os; c=psycopg2.connect(os.environ['DATABASE_URL']); cur=c.cursor(); cur.execute(\"SELECT count(*) FROM users WHERE email LIKE 'org_%@example.invalid'\"); print('leaked users:', cur.fetchone()[0])"`
Expected: `leaked users: 0`.

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/tests/org/__init__.py jarvis/tests/org/conftest.py jarvis/tests/org/test_manager_utils_sincron.py
git commit -m "test(organization): CI-safe seeded Sincron-org fixture for manager_utils"
```

---

## Task 2: `is_manager` → Sincron

**Files:**
- Modify: `jarvis/core/organization/manager_utils.py` (`is_manager`)
- Test: `jarvis/tests/org/test_manager_utils_sincron.py` (append)

**Interfaces:**
- Consumes: `org_fixture`. Produces: `is_manager(user_id) -> bool` — `True` for a Sincron `responsable` (via mapped user) or a `company_responsables` L0 user.

- [ ] **Step 1: Write the failing tests**

Append to `jarvis/tests/org/test_manager_utils_sincron.py`:

```python
from core.organization.manager_utils import is_manager, get_managed_employee_ids, get_visible_tree


def test_is_manager_sincron_responsable(org_fixture):
    assert is_manager(org_fixture['user_M']) is True   # responsable @ P


def test_is_manager_l0(org_fixture):
    assert is_manager(org_fixture['user_L0']) is True   # company_responsables


def test_is_manager_plain_member_false(org_fixture):
    assert is_manager(org_fixture['user_A']) is False   # only a member
    assert is_manager(org_fixture['user_X']) is False   # in company, no org node
```

- [ ] **Step 2: Run to verify failure**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/org/test_manager_utils_sincron.py -k is_manager -v`
Expected: FAIL — `test_is_manager_plain_member_false` fails because the current `is_manager` checks `structure_node_members` (member A is not a structure responsable, but the seeded fixture has no structure rows, so today it returns False for M too → `test_is_manager_sincron_responsable` fails). Confirm at least one Sincron-based assertion fails.

- [ ] **Step 3: Rewrite `is_manager`**

Replace the body of `is_manager` in `manager_utils.py` with:

```python
def is_manager(user_id):
    """True if the user is a Sincron organigram responsable or a company_responsables (L0)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        # (a) Sincron responsable via mapped user
        cursor.execute("""
            SELECT 1
            FROM sincron_org_members som
            JOIN sincron_employees se
              ON se.sincron_employee_id = som.sincron_employee_id
             AND se.company_name = som.company_name
            WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
              AND som.role = 'responsable'
            LIMIT 1
        """, (user_id,))
        if cursor.fetchone():
            return True
        # (b) L0 (unchanged)
        try:
            cursor.execute("SELECT 1 FROM company_responsables WHERE user_id = %s LIMIT 1", (user_id,))
            return cursor.fetchone() is not None
        except Exception:
            conn.rollback()
            return False
    finally:
        release_db(conn)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/org/test_manager_utils_sincron.py -k is_manager -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/core/organization/manager_utils.py jarvis/tests/org/test_manager_utils_sincron.py
git commit -m "feat(organization): is_manager reads Sincron organigram responsables (+ L0)"
```

---

## Task 3: `get_managed_employee_ids` → Sincron

**Files:**
- Modify: `jarvis/core/organization/manager_utils.py` (`get_managed_employee_ids`)
- Test: `jarvis/tests/org/test_manager_utils_sincron.py` (append)

**Interfaces:**
- Produces: `get_managed_employee_ids(user_id, node_id=None) -> list[int]` — L0 = whole company; else Sincron responsable-node + descendants → `member`s → mapped user_ids; `node_id` filters to that Sincron node + descendants; excludes self; unmapped members excluded.

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_managed_sincron_descent(org_fixture):
    got = set(get_managed_employee_ids(org_fixture['user_M']))
    # M responsable @ P -> members of P (D) + descendant Ch (A,B); U unmapped excluded; X not in org
    assert got == {org_fixture['user_A'], org_fixture['user_B'], org_fixture['user_D']}
    assert org_fixture['user_X'] not in got
    assert org_fixture['user_M'] not in got  # excludes self


def test_managed_node_filter(org_fixture):
    got = set(get_managed_employee_ids(org_fixture['user_M'], node_id=org_fixture['node_Ch']))
    assert got == {org_fixture['user_A'], org_fixture['user_B']}  # Ch + descendants only


def test_managed_l0_whole_company(org_fixture):
    got = set(get_managed_employee_ids(org_fixture['user_L0']))
    # L0 sees all active company users except self
    assert got == {org_fixture['user_M'], org_fixture['user_A'], org_fixture['user_B'],
                   org_fixture['user_D'], org_fixture['user_X']}


def test_managed_non_manager_empty(org_fixture):
    assert get_managed_employee_ids(org_fixture['user_A']) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/org/test_manager_utils_sincron.py -k managed -v`
Expected: FAIL (`test_managed_sincron_descent` returns empty — current code reads `structure_node_members`, of which the fixture has none).

- [ ] **Step 3: Rewrite `get_managed_employee_ids`**

Replace the body with:

```python
def get_managed_employee_ids(manager_user_id, node_id=None):
    """User IDs of team members under this user in the SINCRON organigram.

    L0 (company_responsables) sees the whole company; a Sincron responsable
    sees `member`s on their node + all descendants (via mapped_jarvis_user_id).
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        if node_id:
            cursor.execute("""
                WITH RECURSIVE descendants AS (
                    SELECT id FROM sincron_org_nodes WHERE id = %s
                    UNION ALL
                    SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
                )
                SELECT DISTINCT se.mapped_jarvis_user_id AS user_id
                FROM descendants d
                JOIN sincron_org_members m ON m.node_id = d.id AND m.role = 'member'
                JOIN sincron_employees se
                  ON se.sincron_employee_id = m.sincron_employee_id AND se.company_name = m.company_name
                WHERE se.mapped_jarvis_user_id IS NOT NULL AND se.is_active = TRUE
                  AND se.mapped_jarvis_user_id <> %s
            """, (node_id, manager_user_id))
            return [r['user_id'] for r in cursor.fetchall()]

        # 1) L0 (unchanged): whole company
        l0_ids = []
        try:
            cursor.execute("""
                SELECT DISTINCT u.id AS user_id
                FROM company_responsables cr
                JOIN users u ON u.company_id = cr.company_id AND u.is_active = TRUE
                WHERE cr.user_id = %s AND u.id <> %s
            """, (manager_user_id, manager_user_id))
            l0_ids = [r['user_id'] for r in cursor.fetchall()]
        except Exception:
            conn.rollback()

        # 2) Sincron tree descent from the caller's responsable nodes
        cursor.execute("""
            WITH RECURSIVE resp_nodes AS (
                SELECT som.node_id AS id
                FROM sincron_org_members som
                JOIN sincron_employees se
                  ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name
                WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE AND som.role = 'responsable'
            ),
            descendants AS (
                SELECT id FROM resp_nodes
                UNION ALL
                SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
            )
            SELECT DISTINCT se.mapped_jarvis_user_id AS user_id
            FROM descendants d
            JOIN sincron_org_members m ON m.node_id = d.id AND m.role = 'member'
            JOIN sincron_employees se
              ON se.sincron_employee_id = m.sincron_employee_id AND se.company_name = m.company_name
            WHERE se.mapped_jarvis_user_id IS NOT NULL AND se.is_active = TRUE
              AND se.mapped_jarvis_user_id <> %s
        """, (manager_user_id, manager_user_id))
        tree_ids = [r['user_id'] for r in cursor.fetchall()]

        return list(set(l0_ids + tree_ids))
    finally:
        release_db(conn)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/org/test_manager_utils_sincron.py -k managed -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/core/organization/manager_utils.py jarvis/tests/org/test_manager_utils_sincron.py
git commit -m "feat(organization): get_managed_employee_ids descends the Sincron organigram (+ L0)"
```

---

## Task 4: `get_visible_tree` → Sincron

**Files:**
- Modify: `jarvis/core/organization/manager_utils.py` (`get_visible_tree`)
- Test: `jarvis/tests/org/test_manager_utils_sincron.py` (append)

**Interfaces:**
- Produces: `get_visible_tree(user_id) -> {'companies': [...], 'nodes': [...]}` — `companies` from L0 (unchanged); `nodes` from the caller's Sincron responsable-node + descendants, each `{'id','name','level','parent_id','company_id'}` (id is a `sincron_org_nodes.id`).

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_visible_tree_sincron_nodes(org_fixture):
    tree = get_visible_tree(org_fixture['user_M'])
    node_ids = {n['id'] for n in tree['nodes']}
    assert node_ids == {org_fixture['node_P'], org_fixture['node_Ch']}
    assert tree['companies'] == []  # M is not L0
    ch = next(n for n in tree['nodes'] if n['id'] == org_fixture['node_Ch'])
    assert ch['parent_id'] == org_fixture['node_P'] and ch['level'] == 2


def test_visible_tree_l0_company(org_fixture):
    tree = get_visible_tree(org_fixture['user_L0'])
    assert [c['company_id'] for c in tree['companies']] == [org_fixture['company_id']]
    assert tree['companies'][0]['id'] == f"company-{org_fixture['company_id']}"
    assert tree['nodes'] == []  # L0 is not a Sincron responsable here
```

- [ ] **Step 2: Run to verify failure**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/org/test_manager_utils_sincron.py -k visible_tree -v`
Expected: FAIL (`test_visible_tree_sincron_nodes` returns empty nodes — current code reads `structure_nodes`).

- [ ] **Step 3: Rewrite `get_visible_tree`**

Replace the body with:

```python
def get_visible_tree(manager_user_id):
    """Organigram tree visible to this manager (for filtering), from the Sincron organigram.

    Returns L0 companies (company_responsables, unchanged) + the caller's Sincron
    responsable node(s) and their descendants as a flat node list.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # L0 companies (UNCHANGED)
        l0_companies = []
        try:
            cursor.execute("""
                SELECT c.id, c.company AS name, 0 AS level
                FROM company_responsables cr
                JOIN companies c ON c.id = cr.company_id
                WHERE cr.user_id = %s
            """, (manager_user_id,))
            l0_companies = [{'id': f'company-{r["id"]}', 'name': r['name'], 'level': 0,
                             'parent_id': None, 'company_id': r['id']}
                            for r in cursor.fetchall()]
        except Exception:
            conn.rollback()

        # Sincron nodes: caller's responsable node(s) + descendants
        cursor.execute("""
            WITH RECURSIVE resp_nodes AS (
                SELECT som.node_id AS id
                FROM sincron_org_members som
                JOIN sincron_employees se
                  ON se.sincron_employee_id = som.sincron_employee_id AND se.company_name = som.company_name
                WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE AND som.role = 'responsable'
            ),
            descendants AS (
                SELECT id FROM resp_nodes
                UNION ALL
                SELECT sn.id FROM sincron_org_nodes sn JOIN descendants d ON sn.parent_id = d.id
            )
            SELECT DISTINCT n.id, n.name, n.level, n.parent_id, n.company_id
            FROM descendants d JOIN sincron_org_nodes n ON n.id = d.id
            ORDER BY n.level, n.name
        """, (manager_user_id,))
        nodes = [{'id': r['id'], 'name': r['name'], 'level': r['level'],
                  'parent_id': r['parent_id'], 'company_id': r['company_id']}
                 for r in cursor.fetchall()]

        return {'companies': l0_companies, 'nodes': nodes}
    finally:
        release_db(conn)
```

- [ ] **Step 4: Run to verify pass + whole file green**

Run:
```bash
cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/org/ -v
python -m py_compile core/organization/manager_utils.py
```
Expected: all org tests PASS; py_compile clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/core/organization/manager_utils.py jarvis/tests/org/test_manager_utils_sincron.py
git commit -m "feat(organization): get_visible_tree renders the Sincron organigram (+ L0 companies)"
```

---

## Task 5: Verification — no persisted node-ids + full suite CI-safe

**Files:** none (verification only; may add a note to the spec/plan).

- [ ] **Step 1: Confirm node-ids are not persisted as `structure_nodes.id`**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS && grep -rn "node_id" jarvis --include="*.py" | grep -iE "preset|filter|save|INSERT|persist" | grep -v tests`
Expected: no result that stores an org `node_id` into a table. If any is found, report it — a saved filter holding a `structure_nodes.id` would now point at a Sincron node-id namespace and must be handled (surface to the human; do not silently proceed).

- [ ] **Step 2: Full backend suite stays green (CI-safe)**

Run:
```bash
cd jarvis
DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/ -q --ignore=tests/accounting/test_invoice_state_machine.py
DATABASE_URL='postgresql://localhost:5433/nope' python -m pytest tests/org/ -q
```
Expected: full run green (org tests pass inside it); the no-DB run **skips** the org DB tests (not errors), proving CI-safety. (The `--ignore` is the known pre-existing unrelated ImportError.)

- [ ] **Step 3: Confirm no consumer signatures changed**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS && git diff --stat <plan-base>..HEAD -- jarvis`
Expected: only `jarvis/core/organization/manager_utils.py` + `jarvis/tests/org/*` changed. No consumer file (profile/routes, evaluation360, time_bank, field_sales, events, biostar, connecteam, sincron routes) touched — confirms the contracts held.

- [ ] **Step 4: Report readiness (do NOT deploy without confirmation)**

Report suite results to the user. Deployment to staging/main is a **separate, gated** step (surgical cherry-pick of the Task 2–4 commits, per the spec) requiring explicit confirmation and the 2-confirmation main gate — not part of this plan.

---

## Self-Review

**1. Spec coverage:**
- `is_manager` → Sincron + L0 → Task 2. ✅
- `get_managed_employee_ids` → L0 unchanged + Sincron descent + node filter + unmapped excluded + excludes self → Task 3. ✅
- `get_visible_tree` → L0 companies unchanged + Sincron nodes → Task 4. ✅
- Member→user hop via `sincron_employees.mapped_jarvis_user_id` (active) → all three tasks' SQL. ✅
- Contracts frozen / consumers untouched → Task 5 Step 3. ✅
- Accounting untouched → no `accounting/` or `org_scope.py` in any task. ✅
- Node-id namespace / no persisted structure_node ids → Task 5 Step 1. ✅
- CI-safe localhost-only tests (skip when no DB) → Task 1 conftest + Task 5 Step 2. ✅
- Edge cases (unmapped member, non-manager empty, L0 whole company, node filter) → Tasks 2–4 tests. ✅

**2. Placeholder scan:** Every step has concrete code/commands; no TBD/"handle edge cases"/"similar to". ✅

**3. Type consistency:** `is_manager -> bool`; `get_managed_employee_ids -> list[int]` (rows aliased `AS user_id`); `get_visible_tree -> {'companies','nodes'}` with the exact dict keys the current code and consumers expect. Fixture `ids` keys (`user_M`, `node_P`, …) are used identically across Tasks 1–4. The member→user join clause is copied verbatim in all three functions. ✅
