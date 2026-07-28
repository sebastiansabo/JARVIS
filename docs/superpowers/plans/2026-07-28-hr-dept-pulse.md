# HR Department Pulse (slice 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the device-local "Evaluare 360 calitativă" card with a backend-aggregated, anonymous **department pulse** scoped to the Sincron organigram — votes persist, roll up per department, and everyone in the department (members + their manager chain) sees the live aggregate.

**Architecture:** New `hr_dept_pulse_votes` table (rolling upsert keyed by voter × department node × perspective × competency). A thin `DeptPulseRepository` owns **all** SQL (department resolution, eligibility via recursive CTE over `sincron_org_nodes.parent_id`, anonymous aggregate, upsert/delete) — the arch validator forbids SQL in routes. Two endpoints on the existing **profile** blueprint (`GET`/`POST /profile/api/dept-pulse`) enforce eligibility server-side and apply the 3-voter anonymity floor. Mobile reworks the card into a two-tab widget (Evaluează / Statistici departament) driven by the endpoints, relabels `Coleg → Colegi`, and retires the Zustand store.

**Tech Stack:** Python 3 / Flask (blueprint + `BaseRepository`), PostgreSQL (idempotent incremental migration), pytest against localhost/defaultdb. React 19 + TypeScript + Vite + Tailwind + TanStack Query + Capacitor (Android); Vitest.

## Global Constraints

- **Two repos, both on branch `dev`:** `JARVIS` (backend) and `jarvis-mobile-2` (mobile). Backend ships first (staging → prod), then mobile consumes the live endpoints in the next `2.0.x` APK.
- **Git workflow (STRICT):** develop on `dev`; push to `staging` only with user confirmation; merge `staging → main` **only after 2 explicit user confirmations**; never push directly to `main`. When deploying both: push **staging FIRST, then main LAST**, ≥30s apart; after the main merge, WAIT for the main deploy to reach **ACTIVE** before realigning staging.
- **No SDD docs on staging/main:** this plan + the spec stay on `dev` (or scratch); drop `docs/superpowers/**` commits before any staging/main merge.
- **Backend tests run on localhost/defaultdb ONLY** (`postgresql://localhost/defaultdb`). NEVER touch staging or production DB.
- **No SQL in routes** — the arch validator rejects it. All SQL lives in `DeptPulseRepository`, which extends `core.base_repository.BaseRepository` (`query_one` / `query_all` / `execute(..., returning=)` / `execute_many`). `dict_from_row` auto-coerces `Decimal → float`, so `AVG(...)` serializes cleanly.
- **Fixed allow-lists (verbatim):** perspectives `self | peer | manager` (rater-role keys, unchanged); competency keys `communication | teamwork | initiative | problemSolving | professionalism`.
- **Anonymity floor:** `min_voters = 3`. When `voter_count < 3`, the endpoint returns `aggregate: []` (never the underlying rows). `my_votes` is always returned. `min_voters` is surfaced to the client so copy stays in sync.
- **Card title stays "Evaluare 360 calitativă".** Peer label becomes **`Colegi`** (plural). `Autoevaluare` and `Manager` unchanged.
- **Mobile deploy step is MANDATORY** after any committed mobile change: `cd jarvis-mobile-2 && npm run build && npx cap sync android`.
- **Mobile CORS:** `app.py` `_mobile_cors` already allows `GET, POST, PUT, PATCH, DELETE, OPTIONS` — GET/POST need no change (verified). Do not edit `_mobile_cors`.

---

## File Structure

**JARVIS (backend):**
- `jarvis/migrations/domains/schema_incremental.py` — **modify**: append `hr_dept_pulse_votes` DDL before the final `conn.commit()`.
- `jarvis/core/profile/repositories/dept_pulse_repository.py` — **create**: `DeptPulseRepository` (all SQL).
- `jarvis/core/profile/repositories/__init__.py` — **modify**: export `DeptPulseRepository`.
- `jarvis/core/profile/routes.py` — **modify**: two `/api/dept-pulse` endpoints + constants.
- `jarvis/tests/dept_pulse/__init__.py` — **create** (empty package marker).
- `jarvis/tests/dept_pulse/conftest.py` — **create**: `pulse_org` seeded-fixture + pulse-table bootstrap.
- `jarvis/tests/dept_pulse/test_dept_pulse_repository.py` — **create**: resolution, eligibility, votes, aggregate.
- `jarvis/tests/dept_pulse/test_dept_pulse_routes.py` — **create**: endpoint gating / validation / shape / floor.

**jarvis-mobile-2 (mobile):**
- `src/lib/evaluation.ts` — **modify**: add relocated `COMPETENCIES`, `RATER_ROLES` (peer = `Colegi`), `CompetencyKey`, `RaterKey`.
- `src/lib/deptPulse.ts` — **create**: payload types + `toDeptPulseViewModel` + `myRating` (pure).
- `src/lib/deptPulse.test.ts` — **create**: Vitest for the pure module + relabel assertion.
- `src/stores/evaluationStore.ts` — **modify** (Task 5: re-export relocated constants) then **delete** (Task 7).
- `src/hooks/useApi.ts` — **modify**: `useDeptPulse` + `useSubmitDeptPulseVote`.
- `src/pages/HR/DeptPulseCard.tsx` — **create**: the two-tab card.
- `src/pages/HR/Evaluation360Tab.tsx` — **modify**: mount `DeptPulseCard` in the self view, remove `RatingsSection`, update copy, drop store imports.

---

## Task 1: Migration — `hr_dept_pulse_votes` table

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py` (append before the final `conn.commit()` at end of `create_schema_incremental`)
- Test: `jarvis/tests/dept_pulse/__init__.py` (create empty), `jarvis/tests/dept_pulse/test_dept_pulse_schema.py`

**Interfaces:**
- Produces: table `hr_dept_pulse_votes(id, voter_user_id, department_node_id, perspective, competency_key, rating, updated_at)` with `CHECK (rating BETWEEN 1 AND 5)`, `UNIQUE (voter_user_id, department_node_id, perspective, competency_key)`, `ON DELETE CASCADE` from `users(id)` and `sincron_org_nodes(id)`, and index `idx_hr_dept_pulse_votes_node_perspective (department_node_id, perspective)`.

- [ ] **Step 1: Create the test package marker**

Create `jarvis/tests/dept_pulse/__init__.py` (empty file).

- [ ] **Step 2: Write the failing schema test**

Create `jarvis/tests/dept_pulse/test_dept_pulse_schema.py`:

```python
"""Task 1 — hr_dept_pulse_votes schema. Runs against localhost/defaultdb only."""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import psycopg2  # noqa: F401  (pre-import so conftest's psycopg2 mock, if any, is bypassed)
import pytest
from database import get_db, get_cursor, release_db


def _run_migration():
    """Apply the incremental migration (idempotent) so the table exists."""
    from migrations.domains.schema_incremental import create_schema_incremental
    conn = get_db()
    try:
        conn.autocommit = False
        cur = get_cursor(conn)
        create_schema_incremental(conn, cur)
        conn.commit()
    finally:
        release_db(conn)


@pytest.fixture(scope='module', autouse=True)
def ensure_migrated():
    _run_migration()


def test_table_and_columns_exist():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'hr_dept_pulse_votes'
        """)
        cols = {r['column_name'] for r in cur.fetchall()}
        assert {'id', 'voter_user_id', 'department_node_id',
                'perspective', 'competency_key', 'rating', 'updated_at'} <= cols
    finally:
        release_db(conn)


def test_rating_check_rejects_out_of_range():
    """The CHECK (rating BETWEEN 1 AND 5) must reject 6."""
    from psycopg2.errors import CheckViolation
    conn = get_db()
    try:
        cur = get_cursor(conn)
        # Need a valid FK pair — reuse any existing user + org node, else skip.
        cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
        u = cur.fetchone()
        cur.execute("SELECT id FROM sincron_org_nodes ORDER BY id LIMIT 1")
        n = cur.fetchone()
        if not u or not n:
            pytest.skip('no seed user/org node available on this DB')
        with pytest.raises(CheckViolation):
            cur.execute("""
                INSERT INTO hr_dept_pulse_votes
                    (voter_user_id, department_node_id, perspective, competency_key, rating)
                VALUES (%s, %s, 'self', 'communication', 6)
            """, (u['id'], n['id']))
        conn.rollback()
    finally:
        release_db(conn)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/test_dept_pulse_schema.py -v`
Expected: FAIL — `test_table_and_columns_exist` shows the column set is empty (table not created).

- [ ] **Step 4: Add the migration DDL**

In `jarvis/migrations/domains/schema_incremental.py`, immediately **before** the final `conn.commit()` at the end of `create_schema_incremental`, insert:

```python
    # ── HR Department Pulse — backend-aggregated 360 qualitative votes ──
    # Rolling per-voter × department-node × perspective × competency vote scoped
    # to a Sincron org node. Re-voting UPDATEs the same row (the UNIQUE upsert
    # key) so a voter's latest vote always counts and there is no month history.
    # ON DELETE CASCADE from both FKs cleans up when a user or node is removed.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr_dept_pulse_votes (
            id SERIAL PRIMARY KEY,
            voter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            department_node_id INTEGER NOT NULL REFERENCES sincron_org_nodes(id) ON DELETE CASCADE,
            perspective VARCHAR(20) NOT NULL,
            competency_key VARCHAR(40) NOT NULL,
            rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (voter_user_id, department_node_id, perspective, competency_key)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_hr_dept_pulse_votes_node_perspective
        ON hr_dept_pulse_votes(department_node_id, perspective)
    ''')
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/test_dept_pulse_schema.py -v`
Expected: PASS (2 passed; the CHECK test may `skip` if the DB has no users/nodes — acceptable).

- [ ] **Step 6: Verify imports compile**

Run: `cd jarvis && python -m py_compile migrations/domains/schema_incremental.py`
Expected: no output (success).

- [ ] **Step 7: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/migrations/domains/schema_incremental.py jarvis/tests/dept_pulse/__init__.py jarvis/tests/dept_pulse/test_dept_pulse_schema.py
git commit -m "feat(profile): add hr_dept_pulse_votes table for department pulse"
```

---

## Task 2: `DeptPulseRepository` — resolution & eligibility

**Files:**
- Create: `jarvis/core/profile/repositories/dept_pulse_repository.py`
- Modify: `jarvis/core/profile/repositories/__init__.py`
- Create: `jarvis/tests/dept_pulse/conftest.py` (the `pulse_org` fixture, reused by Tasks 2–3)
- Test: `jarvis/tests/dept_pulse/test_dept_pulse_repository.py` (resolution + eligibility cases)

**Interfaces:**
- Consumes: `core.base_repository.BaseRepository` (`query_one`, `query_all`, `execute`, `execute_many`); tables `sincron_employees` (`sincron_employee_id`, `company_name`, `mapped_jarvis_user_id`, `is_active`), `sincron_org_members` (`node_id`, `sincron_employee_id`, `company_name`, `role`), `sincron_org_nodes` (`id`, `parent_id`, `name`, `company_id`, `level`).
- Produces (relied on by Tasks 3–4):
  - `MIN_VOTERS: int = 3` (class attribute)
  - `resolve_department(user_id: int) -> dict | None` → `{'node_id': int, 'name': str, 'company_id': int}` or `None`
  - `get_department(node_id: int) -> dict | None` → `{'node_id', 'name', 'company_id'}`
  - `eligible_node_ids(user_id: int) -> set[int]`
  - `available_departments(user_id: int) -> list[dict]` → `[{'node_id': int, 'name': str}, ...]` ordered by `level, name`
  - `is_eligible(user_id: int, node_id: int) -> bool`

- [ ] **Step 1: Create the seeded `pulse_org` fixture**

Create `jarvis/tests/dept_pulse/conftest.py`:

```python
"""Seeded Sincron-org fixture for department-pulse tests. localhost/defaultdb only.

Topology:
    Node P (level 1)  ── responsable: user M
      └─ Node C (level 2, parent=P) ── members: users A, B, C

Eligibility consequences the tests rely on:
  - M (responsable of P) is eligible for P and its descendant C.
  - A/B/C (members of C) are eligible for C only — NOT for parent P.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import psycopg2  # noqa: F401
import pytest
from database import get_db, get_cursor, release_db

_MARK = 'PULSE_TEST_CO'  # sincron_employees.company_name marker for cleanup


def _ensure_table(cur):
    """Idempotent bootstrap so tests run even on a fresh DB (matches migration)."""
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hr_dept_pulse_votes (
            id SERIAL PRIMARY KEY,
            voter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            department_node_id INTEGER NOT NULL REFERENCES sincron_org_nodes(id) ON DELETE CASCADE,
            perspective VARCHAR(20) NOT NULL,
            competency_key VARCHAR(40) NOT NULL,
            rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (voter_user_id, department_node_id, perspective, competency_key)
        )
    ''')


@pytest.fixture
def pulse_org():
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    _ensure_table(cur)

    cur.execute("SELECT id FROM companies ORDER BY id LIMIT 1")
    company_id = cur.fetchone()['id']

    ids = {}
    try:
        # 4 throwaway users (users requires only name + unique email)
        for key in ('M', 'A', 'B', 'C'):
            cur.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
                (f'Pulse {key}', f'pulse_{key.lower()}@example.invalid'),
            )
            ids[f'user_{key}'] = cur.fetchone()['id']

        # sincron_employees mapping each user (company_name = marker)
        for key in ('M', 'A', 'B', 'C'):
            cur.execute(
                """INSERT INTO sincron_employees
                       (sincron_employee_id, company_name, mapped_jarvis_user_id, is_active)
                   VALUES (%s, %s, %s, TRUE)""",
                (f'PT_{key}', _MARK, ids[f'user_{key}']),
            )

        # org nodes P (level 1) and C (level 2, child of P)
        cur.execute(
            """INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
               VALUES (%s, NULL, 'Pulse P', 'department', 1) RETURNING id""",
            (company_id,),
        )
        ids['node_P'] = cur.fetchone()['id']
        cur.execute(
            """INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
               VALUES (%s, %s, 'Pulse C', 'team', 2) RETURNING id""",
            (company_id, ids['node_P']),
        )
        ids['node_C'] = cur.fetchone()['id']

        # members: M responsable of P; A,B,C members of C
        cur.execute(
            """INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
               VALUES (%s, 'PT_M', %s, 'responsable')""",
            (ids['node_P'], _MARK),
        )
        for key in ('A', 'B', 'C'):
            cur.execute(
                """INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
                   VALUES (%s, %s, %s, 'member')""",
                (ids['node_C'], f'PT_{key}', _MARK),
            )
        conn.commit()
        yield ids
    finally:
        # Teardown — nodes/users cascade to members+votes, but be explicit.
        cur.execute("DELETE FROM hr_dept_pulse_votes WHERE department_node_id IN (%s, %s)",
                    (ids.get('node_C'), ids.get('node_P')))
        cur.execute("DELETE FROM sincron_org_nodes WHERE id IN (%s, %s)",
                    (ids.get('node_C'), ids.get('node_P')))
        cur.execute("DELETE FROM sincron_employees WHERE company_name = %s", (_MARK,))
        cur.execute("DELETE FROM users WHERE id = ANY(%s)",
                    ([v for k, v in ids.items() if k.startswith('user_')],))
        conn.commit()
        release_db(conn)
```

- [ ] **Step 2: Write the failing resolution/eligibility test**

Create `jarvis/tests/dept_pulse/test_dept_pulse_repository.py`:

```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/test_dept_pulse_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: core.profile.repositories.dept_pulse_repository`.

- [ ] **Step 4: Create the repository (resolution + eligibility methods)**

Create `jarvis/core/profile/repositories/dept_pulse_repository.py`:

```python
"""HR Department Pulse repository — all SQL for the backend-aggregated 360.

Owns Sincron-org department resolution, eligibility (recursive CTE over
sincron_org_nodes.parent_id), the anonymous aggregate, and vote upsert/delete.
Routes hold NO SQL (arch validator).
"""
from typing import Optional

from core.base_repository import BaseRepository

# A user's eligible-node set is: their own member/responsable nodes, plus every
# descendant of any node where they are a responsable (manager-sees-down).
_ELIGIBLE_SQL = """
    WITH my_nodes AS (
        SELECT som.node_id, som.role
        FROM sincron_org_members som
        JOIN sincron_employees se
          ON se.sincron_employee_id = som.sincron_employee_id
         AND se.company_name = som.company_name
        WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
    ),
    resp_tree AS (
        SELECT node_id AS id FROM my_nodes WHERE role = 'responsable'
        UNION
        SELECT n.id
        FROM sincron_org_nodes n
        JOIN resp_tree rt ON n.parent_id = rt.id
    ),
    eligible AS (
        SELECT node_id AS id FROM my_nodes
        UNION
        SELECT id FROM resp_tree
    )
"""


class DeptPulseRepository(BaseRepository):
    """All SQL behind /profile/api/dept-pulse."""

    MIN_VOTERS = 3

    # ── Resolution ──

    def resolve_department(self, user_id: int) -> Optional[dict]:
        """The caller's default department node: prefer a node where they are a
        member, else one where they are a responsable; ties broken by level, id."""
        return self.query_one(
            """
            SELECT n.id AS node_id, n.name, n.company_id
            FROM sincron_org_members som
            JOIN sincron_org_nodes n ON n.id = som.node_id
            JOIN sincron_employees se
              ON se.sincron_employee_id = som.sincron_employee_id
             AND se.company_name = som.company_name
            WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
            ORDER BY (som.role = 'member') DESC, n.level ASC, n.id ASC
            LIMIT 1
            """,
            (user_id,),
        )

    def get_department(self, node_id: int) -> Optional[dict]:
        return self.query_one(
            "SELECT id AS node_id, name, company_id FROM sincron_org_nodes WHERE id = %s",
            (node_id,),
        )

    # ── Eligibility ──

    def eligible_node_ids(self, user_id: int) -> set[int]:
        rows = self.query_all(_ELIGIBLE_SQL + " SELECT id FROM eligible", (user_id,))
        return {r['id'] for r in rows}

    def available_departments(self, user_id: int) -> list[dict]:
        return self.query_all(
            _ELIGIBLE_SQL + """
            SELECT n.id AS node_id, n.name
            FROM sincron_org_nodes n
            JOIN eligible e ON e.id = n.id
            ORDER BY n.level, n.name
            """,
            (user_id,),
        )

    def is_eligible(self, user_id: int, node_id: int) -> bool:
        return node_id in self.eligible_node_ids(user_id)
```

- [ ] **Step 5: Export the repository**

In `jarvis/core/profile/repositories/__init__.py`, add the export. Read the file first; it currently exports `ProfileRepository`. Add:

```python
from .dept_pulse_repository import DeptPulseRepository  # noqa: F401
```

(Keep the existing `ProfileRepository` export and any `__all__` list in sync — append `'DeptPulseRepository'` if an `__all__` exists.)

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/test_dept_pulse_repository.py -v`
Expected: PASS (6 passed).

- [ ] **Step 7: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/core/profile/repositories/dept_pulse_repository.py jarvis/core/profile/repositories/__init__.py jarvis/tests/dept_pulse/conftest.py jarvis/tests/dept_pulse/test_dept_pulse_repository.py
git commit -m "feat(profile): DeptPulseRepository department resolution + Sincron-org eligibility"
```

---

## Task 3: `DeptPulseRepository` — votes & aggregate

**Files:**
- Modify: `jarvis/core/profile/repositories/dept_pulse_repository.py` (add vote/aggregate methods)
- Test: `jarvis/tests/dept_pulse/test_dept_pulse_repository.py` (append vote/aggregate cases)

**Interfaces:**
- Produces (relied on by Task 4):
  - `get_voter_count(node_id: int) -> int`
  - `get_aggregate(node_id: int) -> list[dict]` → `[{'perspective': str, 'competency_key': str, 'avg': float, 'voters': int}, ...]`
  - `get_my_votes(user_id: int, node_id: int) -> list[dict]` → `[{'perspective', 'competency_key', 'rating'}, ...]`
  - `upsert_vote(user_id: int, node_id: int, perspective: str, competency_key: str, rating: int) -> None`
  - `delete_vote(user_id: int, node_id: int, perspective: str, competency_key: str) -> None`

- [ ] **Step 1: Write the failing votes/aggregate tests**

Append to `jarvis/tests/dept_pulse/test_dept_pulse_repository.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/test_dept_pulse_repository.py -k "upsert or aggregate or voter or delete" -v`
Expected: FAIL with `AttributeError: 'DeptPulseRepository' object has no attribute 'upsert_vote'`.

- [ ] **Step 3: Add the vote/aggregate methods**

Append to the `DeptPulseRepository` class in `jarvis/core/profile/repositories/dept_pulse_repository.py`:

```python
    # ── Aggregate (anonymous) ──

    def get_voter_count(self, node_id: int) -> int:
        row = self.query_one(
            "SELECT COUNT(DISTINCT voter_user_id) AS n FROM hr_dept_pulse_votes WHERE department_node_id = %s",
            (node_id,),
        )
        return int(row['n']) if row else 0

    def get_aggregate(self, node_id: int) -> list[dict]:
        """Anonymous per-perspective × competency average + distinct voter count.
        voter_user_id never leaves the server. avg comes back as float via
        dict_from_row's Decimal coercion."""
        return self.query_all(
            """
            SELECT perspective, competency_key,
                   ROUND(AVG(rating)::numeric, 2) AS avg,
                   COUNT(DISTINCT voter_user_id)  AS voters
            FROM hr_dept_pulse_votes
            WHERE department_node_id = %s
            GROUP BY perspective, competency_key
            """,
            (node_id,),
        )

    # ── Caller's own votes ──

    def get_my_votes(self, user_id: int, node_id: int) -> list[dict]:
        return self.query_all(
            """
            SELECT perspective, competency_key, rating
            FROM hr_dept_pulse_votes
            WHERE voter_user_id = %s AND department_node_id = %s
            ORDER BY perspective, competency_key
            """,
            (user_id, node_id),
        )

    # ── Write ──

    def upsert_vote(self, user_id: int, node_id: int, perspective: str,
                    competency_key: str, rating: int) -> None:
        self.execute(
            """
            INSERT INTO hr_dept_pulse_votes
                (voter_user_id, department_node_id, perspective, competency_key, rating, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (voter_user_id, department_node_id, perspective, competency_key)
            DO UPDATE SET rating = EXCLUDED.rating, updated_at = NOW()
            """,
            (user_id, node_id, perspective, competency_key, rating),
        )

    def delete_vote(self, user_id: int, node_id: int, perspective: str,
                    competency_key: str) -> None:
        self.execute(
            """
            DELETE FROM hr_dept_pulse_votes
            WHERE voter_user_id = %s AND department_node_id = %s
              AND perspective = %s AND competency_key = %s
            """,
            (user_id, node_id, perspective, competency_key),
        )
```

- [ ] **Step 4: Run the full repository test file**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/test_dept_pulse_repository.py -v`
Expected: PASS (11 passed — 6 from Task 2 + 5 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/core/profile/repositories/dept_pulse_repository.py jarvis/tests/dept_pulse/test_dept_pulse_repository.py
git commit -m "feat(profile): DeptPulseRepository rolling upsert, delete-on-zero, anonymous aggregate"
```

---

## Task 4: Endpoints — `GET`/`POST /profile/api/dept-pulse`

**Files:**
- Modify: `jarvis/core/profile/routes.py` (add constants + two endpoints)
- Test: `jarvis/tests/dept_pulse/test_dept_pulse_routes.py`

**Interfaces:**
- Consumes: `DeptPulseRepository` (Tasks 2–3), `flask_login.current_user`, `core.utils.api_helpers.safe_error_response`.
- Produces: `GET /profile/api/dept-pulse[?department=<node_id>]` and `POST /profile/api/dept-pulse`. GET returns `{department, available_departments, voter_count, min_voters, aggregate, my_votes}`; POST body `{department_node_id, perspective, competency_key, rating}` returns `{ok: true}` (403 ineligible, 400 invalid).

- [ ] **Step 1: Write the failing route tests**

Create `jarvis/tests/dept_pulse/test_dept_pulse_routes.py`:

```python
"""GET/POST /profile/api/dept-pulse — gating, validation, shape, floor (Task 4)."""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

import core.profile.routes as routes
from core.profile import profile_bp


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.is_authenticated = True


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(profile_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    monkeypatch.setattr(routes, 'current_user', FakeUser(42))
    return app.test_client()


def test_get_returns_shape_and_floor_blanks_aggregate(client, monkeypatch):
    r = routes._dept_pulse_repo
    monkeypatch.setattr(r, 'resolve_department', lambda uid: {'node_id': 7, 'name': 'Vânzări', 'company_id': 11})
    monkeypatch.setattr(r, 'available_departments', lambda uid: [{'node_id': 7, 'name': 'Vânzări'}])
    monkeypatch.setattr(r, 'get_voter_count', lambda nid: 2)  # below floor
    monkeypatch.setattr(r, 'get_aggregate', lambda nid: [{'perspective': 'peer', 'competency_key': 'communication', 'avg': 4.0, 'voters': 2}])
    monkeypatch.setattr(r, 'get_my_votes', lambda uid, nid: [{'perspective': 'self', 'competency_key': 'communication', 'rating': 4}])

    resp = client.get('/profile/api/dept-pulse')
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['department']['node_id'] == 7
    assert body['min_voters'] == 3
    assert body['voter_count'] == 2
    assert body['aggregate'] == []          # blanked: voter_count < min_voters
    assert body['my_votes'][0]['rating'] == 4


def test_get_returns_aggregate_at_floor(client, monkeypatch):
    r = routes._dept_pulse_repo
    monkeypatch.setattr(r, 'resolve_department', lambda uid: {'node_id': 7, 'name': 'Vânzări', 'company_id': 11})
    monkeypatch.setattr(r, 'available_departments', lambda uid: [{'node_id': 7, 'name': 'Vânzări'}])
    monkeypatch.setattr(r, 'get_voter_count', lambda nid: 3)
    monkeypatch.setattr(r, 'get_aggregate', lambda nid: [{'perspective': 'peer', 'competency_key': 'communication', 'avg': 4.0, 'voters': 3}])
    monkeypatch.setattr(r, 'get_my_votes', lambda uid, nid: [])
    resp = client.get('/profile/api/dept-pulse')
    assert resp.get_json()['aggregate'][0]['voters'] == 3


def test_get_no_department_returns_null(client, monkeypatch):
    r = routes._dept_pulse_repo
    monkeypatch.setattr(r, 'resolve_department', lambda uid: None)
    monkeypatch.setattr(r, 'available_departments', lambda uid: [])
    resp = client.get('/profile/api/dept-pulse')
    body = resp.get_json()
    assert body['department'] is None
    assert body['aggregate'] == []
    assert body['my_votes'] == []


def test_get_ineligible_department_403(client, monkeypatch):
    r = routes._dept_pulse_repo
    monkeypatch.setattr(r, 'is_eligible', lambda uid, nid: False)
    monkeypatch.setattr(r, 'available_departments', lambda uid: [])
    resp = client.get('/profile/api/dept-pulse?department=999')
    assert resp.status_code == 403


def test_post_upserts_when_eligible(client, monkeypatch):
    r = routes._dept_pulse_repo
    calls = {}
    monkeypatch.setattr(r, 'is_eligible', lambda uid, nid: True)
    monkeypatch.setattr(r, 'upsert_vote', lambda *a: calls.setdefault('upsert', a))
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'peer',
        'competency_key': 'communication', 'rating': 4})
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True
    assert calls['upsert'] == (42, 7, 'peer', 'communication', 4)


def test_post_zero_rating_deletes(client, monkeypatch):
    r = routes._dept_pulse_repo
    calls = {}
    monkeypatch.setattr(r, 'is_eligible', lambda uid, nid: True)
    monkeypatch.setattr(r, 'delete_vote', lambda *a: calls.setdefault('delete', a))
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'peer',
        'competency_key': 'communication', 'rating': 0})
    assert resp.status_code == 200
    assert calls['delete'] == (42, 7, 'peer', 'communication')


def test_post_ineligible_403(client, monkeypatch):
    monkeypatch.setattr(routes._dept_pulse_repo, 'is_eligible', lambda uid, nid: False)
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'peer',
        'competency_key': 'communication', 'rating': 4})
    assert resp.status_code == 403


def test_post_invalid_perspective_400(client):
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'boss',
        'competency_key': 'communication', 'rating': 4})
    assert resp.status_code == 400


def test_post_invalid_rating_400(client, monkeypatch):
    monkeypatch.setattr(routes._dept_pulse_repo, 'is_eligible', lambda uid, nid: True)
    resp = client.post('/profile/api/dept-pulse', json={
        'department_node_id': 7, 'perspective': 'peer',
        'competency_key': 'communication', 'rating': 9})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/test_dept_pulse_routes.py -v`
Expected: FAIL — 404 on the routes (endpoints not defined yet).

- [ ] **Step 3: Add constants + endpoints to `routes.py`**

In `jarvis/core/profile/routes.py`, update the import of the repositories package (line 10) to also bring in `DeptPulseRepository`:

```python
from core.profile.repositories import ProfileRepository, DeptPulseRepository
```

Below the existing `_user_repo = UserRepository()` (line 15), add:

```python
_dept_pulse_repo = DeptPulseRepository()

# Fixed allow-lists — the rater-role keys are unchanged (peer stays 'peer';
# only its mobile label becomes 'Colegi'). Competency keys match the mobile card.
_VALID_DP_PERSPECTIVES = {'self', 'peer', 'manager'}
_VALID_DP_COMPETENCIES = {
    'communication', 'teamwork', 'initiative', 'problemSolving', 'professionalism',
}
```

Then add the two endpoints (place them near the other Sincron/HR profile endpoints, e.g. after `api_profile_sincron_timesheet`):

```python
@profile_bp.route('/api/dept-pulse')
@login_required
def api_profile_dept_pulse():
    """Anonymous department-pulse aggregate + the caller's own votes.

    Resolves the caller's Sincron department when ?department is omitted; when
    present, requires eligibility (else 403). Aggregate is blanked below the
    3-voter anonymity floor; my_votes is always returned.
    """
    try:
        uid = current_user.id
        requested = request.args.get('department', type=int)
        available = _dept_pulse_repo.available_departments(uid)

        if requested is not None:
            if not _dept_pulse_repo.is_eligible(uid, requested):
                return jsonify({'error': 'Not eligible for this department'}), 403
            dept = _dept_pulse_repo.get_department(requested)
        else:
            dept = _dept_pulse_repo.resolve_department(uid)

        min_voters = DeptPulseRepository.MIN_VOTERS
        if not dept:
            return jsonify({
                'department': None,
                'available_departments': available,
                'voter_count': 0,
                'min_voters': min_voters,
                'aggregate': [],
                'my_votes': [],
            })

        node_id = dept['node_id']
        voter_count = _dept_pulse_repo.get_voter_count(node_id)
        aggregate = _dept_pulse_repo.get_aggregate(node_id) if voter_count >= min_voters else []
        my_votes = _dept_pulse_repo.get_my_votes(uid, node_id)

        return jsonify({
            'department': {
                'node_id': node_id,
                'name': dept['name'],
                'company_id': dept.get('company_id'),
            },
            'available_departments': available,
            'voter_count': voter_count,
            'min_voters': min_voters,
            'aggregate': aggregate,
            'my_votes': my_votes,
        })
    except Exception as e:
        return safe_error_response(e)


@profile_bp.route('/api/dept-pulse', methods=['POST'])
@login_required
def api_profile_dept_pulse_vote():
    """Upsert (or clear, on rating 0/null) one of the caller's votes."""
    try:
        uid = current_user.id
        data = request.get_json(silent=True) or {}
        node_id = data.get('department_node_id')
        perspective = data.get('perspective')
        competency = data.get('competency_key')
        rating = data.get('rating')

        if not isinstance(node_id, int):
            return jsonify({'error': 'department_node_id required'}), 400
        if perspective not in _VALID_DP_PERSPECTIVES:
            return jsonify({'error': 'invalid perspective'}), 400
        if competency not in _VALID_DP_COMPETENCIES:
            return jsonify({'error': 'invalid competency_key'}), 400
        if not _dept_pulse_repo.is_eligible(uid, node_id):
            return jsonify({'error': 'Not eligible for this department'}), 403

        if rating in (0, None):
            _dept_pulse_repo.delete_vote(uid, node_id, perspective, competency)
        elif isinstance(rating, int) and 1 <= rating <= 5:
            _dept_pulse_repo.upsert_vote(uid, node_id, perspective, competency, rating)
        else:
            return jsonify({'error': 'rating must be an integer 0-5'}), 400

        return jsonify({'ok': True})
    except Exception as e:
        return safe_error_response(e)
```

- [ ] **Step 4: Run the route tests to verify they pass**

Run: `cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/test_dept_pulse_routes.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Verify the CORS allow-methods needs no change**

Run: `cd jarvis && grep -n "Access-Control-Allow-Methods" app.py`
Expected: shows `'GET, POST, PUT, PATCH, DELETE, OPTIONS'` — GET/POST already allowed. **No edit.** (Confirms the known mobile-CORS-methods gotcha does not bite.)

- [ ] **Step 6: Verify imports + run the whole dept_pulse suite**

Run:
```bash
cd jarvis && python -m py_compile core/profile/routes.py core/profile/repositories/dept_pulse_repository.py
DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/dept_pulse/ -v
```
Expected: compile clean; whole suite PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
git add jarvis/core/profile/routes.py jarvis/tests/dept_pulse/test_dept_pulse_routes.py
git commit -m "feat(profile): GET/POST /profile/api/dept-pulse endpoints with eligibility + anonymity floor"
```

- [ ] **Step 8: Backend deploy readiness (report, do NOT push without confirmation)**

Run the pre-deploy gates and report results to the user; deployment to staging/main requires explicit confirmation per the git workflow.
```bash
cd jarvis && DATABASE_URL='postgresql://localhost/defaultdb' python -m pytest tests/ -x -q
python -m py_compile app.py
```
Then STOP and ask the user before any `git push origin staging` (backend must be live before the mobile card is useful).

---

## Task 5: Mobile — relocate constants (+ relabel) & pure `deptPulse` view-model

**Files:**
- Modify: `jarvis-mobile-2/src/lib/evaluation.ts` (add relocated `COMPETENCIES`/`RATER_ROLES` + types)
- Modify: `jarvis-mobile-2/src/stores/evaluationStore.ts` (re-export relocated constants; keep everything else compiling)
- Create: `jarvis-mobile-2/src/lib/deptPulse.ts`
- Create: `jarvis-mobile-2/src/lib/deptPulse.test.ts`

**Interfaces:**
- Produces (relied on by Tasks 6–7):
  - `evaluation.ts`: `COMPETENCIES` (5 `{key,label}`), `RATER_ROLES` (`self`=`Autoevaluare`, `peer`=`Colegi`, `manager`=`Manager`), `type CompetencyKey`, `type RaterKey`.
  - `deptPulse.ts`: types `DeptPulseAggregateCell`, `DeptPulseMyVote`, `DeptPulseDepartment`, `DeptPulseResponse`, `DeptPulseStatCell`, `DeptPulseStatRow`, `DeptPulseViewModel`; functions `toDeptPulseViewModel(res) -> DeptPulseViewModel`, `myRating(votes, perspective, competencyKey) -> number`.

- [ ] **Step 1: Add relocated constants to `evaluation.ts`**

At the end of `jarvis-mobile-2/src/lib/evaluation.ts` (it already owns `qualitativeScore`, `scoreBand`), append:

```typescript
// ── 360 competency + rater-perspective vocabulary (relocated from the retired
//    device-local store). Keys are stable API contract; labels are RO display. ──

/** Soft-skill competencies assessed in the 360 (stable keys, RO labels). */
export const COMPETENCIES = [
  { key: 'communication', label: 'Comunicare' },
  { key: 'teamwork', label: 'Colaborare' },
  { key: 'initiative', label: 'Inițiativă' },
  { key: 'problemSolving', label: 'Rezolvare probleme' },
  { key: 'professionalism', label: 'Profesionalism' },
] as const;

/** The three 360 rater perspectives. `peer` is labelled "Colegi" (plural). */
export const RATER_ROLES = [
  { key: 'self', label: 'Autoevaluare' },
  { key: 'peer', label: 'Colegi' },
  { key: 'manager', label: 'Manager' },
] as const;

export type CompetencyKey = (typeof COMPETENCIES)[number]['key'];
export type RaterKey = (typeof RATER_ROLES)[number]['key'];
```

- [ ] **Step 2: Re-export from the store to keep current card compiling**

In `jarvis-mobile-2/src/stores/evaluationStore.ts`, **delete** its own `COMPETENCIES`, `RATER_ROLES`, `CompetencyKey`, `RaterKey` definitions (lines defining them) and replace with a re-export so existing importers (`Evaluation360Tab.tsx`) still resolve them — now with the `Colegi` label:

```typescript
export { COMPETENCIES, RATER_ROLES, type CompetencyKey, type RaterKey } from '@/lib/evaluation';
```

Keep `ratingKey`, `subjectKey`, `useEvaluationStore`, `getRating`, `ratedValues` intact (they are removed with the whole file in Task 7). `ratingKey`/`getRating`/`setRating` reference `CompetencyKey`/`RaterKey` — now imported — so the file still type-checks.

- [ ] **Step 3: Write the failing pure-module test**

Create `jarvis-mobile-2/src/lib/deptPulse.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { RATER_ROLES } from './evaluation';
import { toDeptPulseViewModel, myRating, type DeptPulseResponse } from './deptPulse';

const base: DeptPulseResponse = {
  department: { node_id: 7, name: 'Vânzări', company_id: 11 },
  available_departments: [{ node_id: 7, name: 'Vânzări' }],
  voter_count: 3,
  min_voters: 3,
  aggregate: [
    { perspective: 'peer', competency_key: 'communication', avg: 4.2, voters: 3 },
    { perspective: 'self', competency_key: 'teamwork', avg: 3, voters: 2 },
  ],
  my_votes: [{ perspective: 'self', competency_key: 'communication', rating: 4 }],
};

describe('peer relabel', () => {
  it('labels peer as "Colegi"', () => {
    expect(RATER_ROLES.find((r) => r.key === 'peer')?.label).toBe('Colegi');
  });
});

describe('toDeptPulseViewModel', () => {
  it('maps aggregate cells into per-competency rows with per-perspective avgs', () => {
    const vm = toDeptPulseViewModel(base);
    expect(vm.floorMet).toBe(true);
    const comm = vm.rows.find((r) => r.competencyKey === 'communication')!;
    expect(comm.cells.peer.avg).toBe(4.2);
    expect(comm.cells.peer.voters).toBe(3);
    expect(comm.cells.self.avg).toBeNull(); // no self/communication cell in aggregate
  });

  it('reports floor not met and no rows when below min_voters', () => {
    const vm = toDeptPulseViewModel({ ...base, voter_count: 2, aggregate: [] });
    expect(vm.floorMet).toBe(false);
    expect(vm.rows.every((r) => Object.values(r.cells).every((c) => c.avg === null))).toBe(true);
  });
});

describe('myRating', () => {
  it('returns the caller rating for a cell, 0 when absent', () => {
    expect(myRating(base.my_votes, 'self', 'communication')).toBe(4);
    expect(myRating(base.my_votes, 'peer', 'communication')).toBe(0);
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd jarvis-mobile-2 && npx vitest run src/lib/deptPulse.test.ts`
Expected: FAIL — cannot resolve `./deptPulse`.

- [ ] **Step 5: Create the pure module**

Create `jarvis-mobile-2/src/lib/deptPulse.ts`:

```typescript
import { COMPETENCIES, RATER_ROLES, type CompetencyKey, type RaterKey } from './evaluation';

// ── Backend payload types (mirror GET /profile/api/dept-pulse) ──

export interface DeptPulseAggregateCell {
  perspective: RaterKey;
  competency_key: CompetencyKey;
  avg: number;
  voters: number;
}
export interface DeptPulseMyVote {
  perspective: RaterKey;
  competency_key: CompetencyKey;
  rating: number;
}
export interface DeptPulseDepartment {
  node_id: number;
  name: string;
  company_id?: number | null;
}
export interface DeptPulseResponse {
  department: DeptPulseDepartment | null;
  available_departments: { node_id: number; name: string }[];
  voter_count: number;
  min_voters: number;
  aggregate: DeptPulseAggregateCell[];
  my_votes: DeptPulseMyVote[];
}

// ── View-model for the "Statistici departament" tab ──

export interface DeptPulseStatCell {
  avg: number | null;
  voters: number;
}
export interface DeptPulseStatRow {
  competencyKey: CompetencyKey;
  label: string;
  /** One cell per rater perspective (avg null when the department has no such vote). */
  cells: Record<RaterKey, DeptPulseStatCell>;
}
export interface DeptPulseViewModel {
  rows: DeptPulseStatRow[];
  voterCount: number;
  minVoters: number;
  /** True when the anonymity floor is met (aggregate is renderable). */
  floorMet: boolean;
}

const emptyCell = (): DeptPulseStatCell => ({ avg: null, voters: 0 });

/** Shape a GET payload into a stable competency × perspective grid. */
export function toDeptPulseViewModel(res: DeptPulseResponse): DeptPulseViewModel {
  const byKey = new Map<string, DeptPulseAggregateCell>();
  for (const c of res.aggregate) byKey.set(`${c.competency_key}.${c.perspective}`, c);

  const rows: DeptPulseStatRow[] = COMPETENCIES.map((comp) => {
    const cells = Object.fromEntries(
      RATER_ROLES.map((r) => {
        const hit = byKey.get(`${comp.key}.${r.key}`);
        return [r.key, hit ? { avg: hit.avg, voters: hit.voters } : emptyCell()];
      }),
    ) as Record<RaterKey, DeptPulseStatCell>;
    return { competencyKey: comp.key, label: comp.label, cells };
  });

  return {
    rows,
    voterCount: res.voter_count,
    minVoters: res.min_voters,
    floorMet: res.voter_count >= res.min_voters,
  };
}

/** The caller's own rating for a (perspective, competency) cell; 0 when unset. */
export function myRating(
  votes: DeptPulseMyVote[],
  perspective: RaterKey,
  competencyKey: CompetencyKey,
): number {
  return votes.find((v) => v.perspective === perspective && v.competency_key === competencyKey)?.rating ?? 0;
}
```

- [ ] **Step 6: Run the test + typecheck**

Run:
```bash
cd jarvis-mobile-2
npx vitest run src/lib/deptPulse.test.ts src/lib/evaluation.test.ts
npx tsc --noEmit
```
Expected: deptPulse + evaluation tests PASS; `tsc` clean (the store re-export keeps `Evaluation360Tab.tsx` compiling).

- [ ] **Step 7: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/lib/evaluation.ts src/stores/evaluationStore.ts src/lib/deptPulse.ts src/lib/deptPulse.test.ts
git commit -m "feat(hr): relocate 360 vocab to lib/evaluation (Coleg→Colegi) + deptPulse view-model"
```

---

## Task 6: Mobile — API hooks + `DeptPulseCard` component

**Files:**
- Modify: `jarvis-mobile-2/src/hooks/useApi.ts` (add `useDeptPulse` + `useSubmitDeptPulseVote`)
- Create: `jarvis-mobile-2/src/pages/HR/DeptPulseCard.tsx`

**Interfaces:**
- Consumes: `apiFetch` from `@/services/api`; `useQuery`/`useMutation`/`useQueryClient` (already imported in `useApi.ts`); `DeptPulseResponse` from `@/lib/deptPulse`; `toDeptPulseViewModel`, `myRating`; `COMPETENCIES`, `RATER_ROLES`, `qualitativeScore`, `scoreBand` from `@/lib/*`.
- Produces (relied on by Task 7):
  - `useDeptPulse(department?: number)` → `useQuery<DeptPulseResponse>`
  - `useSubmitDeptPulseVote()` → `useMutation` that POSTs `{department_node_id, perspective, competency_key, rating}` and invalidates `['dept-pulse']` on success.
  - `default export DeptPulseCard()` — self-contained two-tab card, no props.

- [ ] **Step 1: Add the two hooks to `useApi.ts`**

Append to `jarvis-mobile-2/src/hooks/useApi.ts` (imports `useQuery`, `useMutation`, `useQueryClient`, `apiFetch` already present at top):

```typescript
// ============== HR Department Pulse ==============

import type { DeptPulseResponse } from '@/lib/deptPulse';

/** Anonymous department pulse + the caller's own votes.
 *  `department` narrows to a specific eligible node (managers with descendants). */
export function useDeptPulse(department?: number) {
  return useQuery<DeptPulseResponse>({
    queryKey: ['dept-pulse', department ?? 'self'],
    queryFn: () =>
      apiFetch(`/profile/api/dept-pulse${department != null ? `?department=${department}` : ''}`),
    staleTime: 30_000,
  });
}

/** Upsert (rating 1–5) or clear (rating 0) one of the caller's votes. */
export function useSubmitDeptPulseVote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { department_node_id: number; perspective: string; competency_key: string; rating: number }) =>
      apiFetch('/profile/api/dept-pulse', { method: 'POST', body: JSON.stringify(v) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dept-pulse'] }),
  });
}
```

> Note: if `useApi.ts` keeps all imports at the top of the file, move the `import type { DeptPulseResponse }` line up beside the existing `import type { RangeSummaryEntry } from '@/lib/evaluation';` rather than mid-file. Either resolves under TS; top is tidier.

- [ ] **Step 2: Create `DeptPulseCard.tsx`**

Create `jarvis-mobile-2/src/pages/HR/DeptPulseCard.tsx`:

```tsx
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useDeptPulse, useSubmitDeptPulseVote } from '@/hooks/useApi';
import { COMPETENCIES, RATER_ROLES, qualitativeScore, scoreBand, type RaterKey, type ScoreBand } from '@/lib/evaluation';
import { toDeptPulseViewModel, myRating } from '@/lib/deptPulse';

/** Band → Tailwind classes (mirrors the BAND map in Evaluation360Tab). */
const BAND: Record<ScoreBand, { text: string }> = {
  green: { text: 'text-green-600' },
  amber: { text: 'text-amber-600' },
  red: { text: 'text-red-600' },
};

/** Average (1–5) → band via the 0–100 rescale the qualitative score uses. */
function avgBand(avg: number): ScoreBand {
  return scoreBand((avg / 5) * 100);
}

export default function DeptPulseCard() {
  const [tab, setTab] = useState<'vote' | 'stats'>('vote');
  const [dept, setDept] = useState<number | undefined>(undefined);
  const { data, isLoading } = useDeptPulse(dept);
  const submit = useSubmitDeptPulseVote();
  const [role, setRole] = useState<RaterKey>('self');

  const qual = useMemo(
    () => (data ? qualitativeScore(data.my_votes.map((v) => v.rating)) : null),
    [data],
  );

  if (isLoading || !data) {
    return <section className="rounded-2xl bg-card p-4 h-40 animate-pulse" />;
  }

  const noDept = data.department == null;
  const vm = toDeptPulseViewModel(data);

  return (
    <section className="rounded-2xl bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Evaluare 360 calitativă
        </p>
        {tab === 'vote' && qual != null && (
          <span className={cn('text-sm font-bold tabular-nums', BAND[scoreBand(qual)].text)}>{qual}/100</span>
        )}
      </div>

      {/* Tab switch */}
      <div className="flex rounded-lg bg-secondary p-0.5 mb-3">
        {([
          { key: 'vote', label: 'Evaluează' },
          { key: 'stats', label: 'Statistici departament' },
        ] as const).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'flex-1 rounded-md py-1 text-[11px] font-medium transition-all',
              tab === t.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Department name / picker (only shown when >1 eligible department) */}
      {!noDept && data.available_departments.length > 1 ? (
        <select
          value={data.department!.node_id}
          onChange={(e) => setDept(Number(e.target.value))}
          className="w-full mb-3 rounded-lg border border-border bg-transparent px-2 py-1.5 text-sm"
        >
          {data.available_departments.map((d) => (
            <option key={d.node_id} value={d.node_id}>{d.name}</option>
          ))}
        </select>
      ) : !noDept ? (
        <p className="text-xs text-muted-foreground mb-3">{data.department!.name}</p>
      ) : null}

      {noDept ? (
        <p className="text-center text-sm text-muted-foreground py-8">
          Nu ești asociat unui departament Sincron.
        </p>
      ) : tab === 'vote' ? (
        <VoteTab
          role={role}
          setRole={setRole}
          nodeId={data.department!.node_id}
          myVotes={data.my_votes}
          submitting={submit.isPending}
          onVote={(perspective, competency_key, rating) =>
            submit.mutate({ department_node_id: data.department!.node_id, perspective, competency_key, rating })
          }
        />
      ) : (
        <StatsTab vm={vm} />
      )}

      <p className="text-[10px] text-muted-foreground mt-3">
        Evaluare calitativă la nivel de departament — anonimă, agregată din Autoevaluare, Colegi și Manager. Poți actualiza oricând.
      </p>
    </section>
  );
}

// ── "Evaluează" tab: the caller's own dial ──

function VoteTab({
  role,
  setRole,
  myVotes,
  onVote,
  submitting,
}: {
  role: RaterKey;
  setRole: (r: RaterKey) => void;
  nodeId: number;
  myVotes: { perspective: RaterKey; competency_key: string; rating: number }[];
  onVote: (perspective: RaterKey, competency: string, rating: number) => void;
  submitting: boolean;
}) {
  return (
    <>
      <div className="flex rounded-lg bg-secondary p-0.5 mb-3">
        {RATER_ROLES.map((r) => (
          <button
            key={r.key}
            onClick={() => setRole(r.key)}
            className={cn(
              'flex-1 rounded-md py-1 text-[11px] font-medium transition-all',
              role === r.key ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground',
            )}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {COMPETENCIES.map((c) => {
          const value = myRating(myVotes as never, role, c.key);
          return (
            <div key={c.key} className="flex items-center justify-between gap-2">
              <span className="text-sm min-w-0 truncate">{c.label}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    disabled={submitting}
                    aria-label={`${c.label} ${n}`}
                    onClick={() => onVote(role, c.key, n === value ? 0 : n)}
                    className={cn(
                      'h-6 w-6 rounded-full border transition-colors active:scale-95 disabled:opacity-50',
                      n <= value ? 'bg-jarvis border-jarvis' : 'border-border bg-transparent',
                    )}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

// ── "Statistici departament" tab: the anonymous aggregate ──

function StatsTab({ vm }: { vm: ReturnType<typeof toDeptPulseViewModel> }) {
  if (!vm.floorMet) {
    return (
      <p className="text-center text-sm text-muted-foreground py-8">
        Statistici disponibile de la {vm.minVoters} voturi (acum: {vm.voterCount}).
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-[10px] text-muted-foreground">{vm.voterCount} persoane au votat</p>
      {vm.rows.map((row) => (
        <div key={row.competencyKey}>
          <p className="text-sm font-medium mb-1">{row.label}</p>
          <div className="grid grid-cols-3 gap-2">
            {RATER_ROLES.map((r) => {
              const cell = row.cells[r.key];
              return (
                <div key={r.key} className="rounded-xl bg-secondary/60 px-2 py-2 text-center">
                  <p className="text-[10px] text-muted-foreground truncate">{r.label}</p>
                  <p
                    className={cn(
                      'text-base font-bold tabular-nums leading-tight',
                      cell.avg != null ? BAND[avgBand(cell.avg)].text : 'text-muted-foreground',
                    )}
                  >
                    {cell.avg != null ? cell.avg.toFixed(1) : '—'}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {cell.voters > 0 ? `din ${cell.voters}` : ''}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Typecheck + build**

Run:
```bash
cd jarvis-mobile-2
npx tsc --noEmit
npm run build
```
Expected: no TypeScript errors; build succeeds. (`DeptPulseCard` compiles even though it is not yet mounted.)

- [ ] **Step 4: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/hooks/useApi.ts src/pages/HR/DeptPulseCard.tsx
git commit -m "feat(hr): DeptPulseCard two-tab component + useDeptPulse/useSubmitDeptPulseVote hooks"
```

---

## Task 7: Mobile — wire the card in, retire the device-local store

**Files:**
- Modify: `jarvis-mobile-2/src/pages/HR/Evaluation360Tab.tsx` (mount `DeptPulseCard` in self view, remove `RatingsSection`, update copy, drop store imports)
- Delete: `jarvis-mobile-2/src/stores/evaluationStore.ts`

**Interfaces:**
- Consumes: `DeptPulseCard` (Task 6 default export).
- Produces: the department pulse renders **once** in the self ("Eu"/"Rezultatele mele") view; team-member drill-down no longer shows a qualitative card; `evaluationStore.ts` no longer exists.

- [ ] **Step 1: Remove `RatingsSection` and its store dependency from `EmployeeEvaluation`**

In `jarvis-mobile-2/src/pages/HR/Evaluation360Tab.tsx`:
- Delete the entire `RatingsSection` function (currently lines ~355–416).
- In `EmployeeEvaluation`, delete the `{/* Qualitative 360 */}` block that renders `<RatingsSection subject={subject} />` (line ~207–208). `EmployeeEvaluation` no longer needs its `subject` prop — remove `subject` from its props type and its two call sites (self view line ~137, team-detail line ~123), and drop the now-unused `subjectKey(...)` calls.
- Remove the store import block (lines ~20–28: `useEvaluationStore, COMPETENCIES, RATER_ROLES, subjectKey, getRating, ratedValues, type RaterKey`) and the `qualitativeScore` import if it is now unused in this file (it moves into `DeptPulseCard`). Keep `scoreBand`, `scoreVerdict`, `presenceBand`, `varianceBand`, `FACTOR_META`, and the type imports still used by the objective UI.

- [ ] **Step 2: Import and mount `DeptPulseCard` once in the self view**

Add the import near the top:

```tsx
import DeptPulseCard from './DeptPulseCard';
```

In the main `Evaluation360Tab` return, the self branch currently renders:

```tsx
<>
  <EmployeeEvaluation
    score={selfScore}
    subject={subjectKey(userId, year, month)}
    title={userName || 'Evaluarea mea'}
    periodLabel={monthLabel(year, month)}
  />
  <InfoCards isManager={isManager} />
</>
```

Change it to (drop `subject`, add the card between the objective evaluation and the info cards):

```tsx
<>
  <EmployeeEvaluation
    score={selfScore}
    title={userName || 'Evaluarea mea'}
    periodLabel={monthLabel(year, month)}
  />
  <DeptPulseCard />
  <InfoCards isManager={isManager} />
</>
```

And the team-detail branch drops `subject` too:

```tsx
<EmployeeEvaluation
  score={selected.score}
  title={selected.name}
  periodLabel={monthLabel(year, month)}
/>
```

- [ ] **Step 3: Update the "Cine vede ce" info copy**

In `InfoCards`, replace the trailing sentence "Evaluările calitative rămân locale, pe dispozitiv." with copy reflecting the new department-level, anonymous model, e.g.:

```tsx
Evaluarea 360 calitativă e agregată anonim la nivel de departament — o vezi și o poți actualiza oricând.
```

- [ ] **Step 4: Delete the store**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git rm src/stores/evaluationStore.ts
```

- [ ] **Step 5: Verify no dangling references to the store**

Run: `cd jarvis-mobile-2 && grep -rn "evaluationStore\|useEvaluationStore\|subjectKey\|jarvis2-evaluation-360" src/`
Expected: **no matches** (the localStorage key and every store symbol are gone).

- [ ] **Step 6: Typecheck, test, build, Capacitor sync**

Run:
```bash
cd jarvis-mobile-2
npx tsc --noEmit
npx vitest run
npm run build && npx cap sync android
```
Expected: `tsc` clean; all Vitest suites PASS; build succeeds; `cap sync android` completes. (MANDATORY per project convention — never skip `cap sync`.)

- [ ] **Step 7: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add -A
git commit -m "feat(hr): mount DeptPulseCard in self 360 view, retire device-local evaluationStore"
```

- [ ] **Step 8: Manual device verification (report to user)**

Confirm on-device (or in the built web preview) and report results:
- Own department: rate under each perspective → `POST` fires; the tap-lit-dot-again clears (rating 0).
- "Statistici departament" tab shows the floor copy until ≥3 voters, then the aggregate grid.
- Unmapped user → "Nu ești asociat unui departament Sincron." empty state.
- Manager with descendant departments → the picker appears; selecting one refetches.
- The peer perspective reads **Colegi**; the card title stays **Evaluare 360 calitativă**.

---

## Deploy Sequencing (after all tasks pass — requires user confirmation)

1. **Backend first.** On `dev`: full suite green (`pytest tests/ -x -q` on localhost). Drop `docs/superpowers/**` from the staging/main merge. With user confirmation, push `staging`; verify staging health; then with **2 confirmations** merge `staging → main`, push **main LAST**, and WAIT for the main deploy to reach **ACTIVE** before realigning staging.
2. **Mobile second**, once the backend endpoints are live in production: merge `dev → main` on `jarvis-mobile-2` per its workflow so CI builds `jarvis2.apk`; then merge JARVIS `staging → main` to publish the updated APK download.

---

## Self-Review

**1. Spec coverage**
- Relabel `Coleg → Colegi` → Task 5 (`evaluation.ts` `RATER_ROLES`), asserted in `deptPulse.test.ts`. ✅
- Persist votes to backend, rolling upsert, no month history → Task 1 (UNIQUE key) + Task 3 (`upsert_vote` ON CONFLICT), tested. ✅
- "Statistici departament" tab, anonymous aggregate, live → Task 6 (`StatsTab`) + `useDeptPulse` invalidation on vote. ✅
- Eligibility = members + manager chain (walk `parent_id` up-tree for managers) → Task 2 recursive CTE + tests. ✅
- Data model `hr_dept_pulse_votes` with exact columns/constraints/index → Task 1. ✅
- Hierarchy resolution via `sincron_employees.mapped_jarvis_user_id` → `sincron_org_members` → node → Task 2 `resolve_department`. ✅
- GET payload shape + POST body + 403/400 + anonymity floor (empty aggregate, my_votes always) → Task 4, tested. ✅
- `min_voters` backend constant surfaced to client → `DeptPulseRepository.MIN_VOTERS` in GET payload; client copy uses `vm.minVoters`. ✅
- Card renders once in self view, not per team member → Task 7 mounts `<DeptPulseCard/>` only in self branch; `RatingsSection` removed from `EmployeeEvaluation`. ✅
- Footnote + "Cine vede ce" copy updated → Task 6 footnote, Task 7 Step 3. ✅
- Two hooks in `useApi.ts` (`useDeptPulse`, `useSubmitDeptPulseVote`) → Task 6. ✅
- Retire `evaluationStore.ts`; relocate `COMPETENCIES`/`RATER_ROLES` to `lib/evaluation.ts`; card computes `X/100` from `my_votes` via `qualitativeScore` → Tasks 5–7. ✅
- Edge cases: unmapped (`department: null`, empty state) — Task 4/6; multiple nodes → default first by level,id + picker — Task 2 `resolve_department` ORDER BY + Task 6 picker; clear-on-zero — Task 3/4/6; manager on descendant — Task 2 eligibility; ineligible → 403 banner — Task 4 + client (`ApiError` surfaced by the shared api layer); stale membership tolerated (live per-request resolution, old votes stay) — inherent to the rolling model. ✅
- Testing: backend pytest on localhost only (fixtures never touch staging/prod) — every test hard-codes `postgresql://localhost/defaultdb`; mobile Vitest for `deptPulse.ts` + `tsc`/`build`/`cap sync`. ✅
- Out of scope respected: no change to objective score, 360 cycle backend, scoring formulas, web HUB, or the Sincron organigram (consumed read-only). ✅

**2. Placeholder scan:** No `TBD`/"add error handling"/"similar to Task N" — every code step carries full content; error handling is the concrete `safe_error_response(e)` wrapper used across the profile blueprint. ✅

**3. Type consistency:** `resolve_department`/`get_department` return `{node_id, name, company_id}` — GET reads `dept['node_id']`, `dept['name']`, `dept.get('company_id')`. `get_aggregate` rows `{perspective, competency_key, avg, voters}` match `DeptPulseAggregateCell`. `get_my_votes` rows `{perspective, competency_key, rating}` match `DeptPulseMyVote`. `MIN_VOTERS` referenced as `DeptPulseRepository.MIN_VOTERS` in the route. Mobile `toDeptPulseViewModel`/`myRating`/`DeptPulseResponse` names are identical across `deptPulse.ts`, its test, `useApi.ts`, and `DeptPulseCard.tsx`. POST field names (`department_node_id`, `perspective`, `competency_key`, `rating`) match between `useSubmitDeptPulseVote`, the route validators, and the tests. ✅
