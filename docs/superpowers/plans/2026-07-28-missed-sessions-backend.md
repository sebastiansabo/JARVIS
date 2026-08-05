# Missed Sessions — Backend Implementation Plan (JARVIS)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a PLANNED Test Drive session a real end-of-life — an 8h grace window after a missed start, automatic archival to a `MISSED` status that frees the vehicle, a "missed at start" push to the consilier, and a reschedule/revive endpoint.

**Architecture:** A single source of truth for the lifecycle (`session_lifecycle.py`: `GRACE_HOURS`, a pure `derive_planned_substatus()` helper, and the `TD_STATUS_SQL` fragment) is consumed by the repository's derived-status SQL. A new `/reschedule` endpoint moves a `PLANNED`/`MISSED` row to a new future time. An APScheduler job (`tasks/foi_parcurs_sessions.py`) runs every 10 minutes to notify newly-late sessions once and archive sessions past `departure + 8h`. `find_conflicts` excludes archived/past-grace sessions so the vehicle is freed.

**Tech Stack:** Python, Flask blueprint (`foi_parcurs_bp`), psycopg2 via `BaseRepository`, APScheduler, `core.notifications.notify.notify_with_push`, pytest with the Flask test client + mocked repository.

## Global Constraints

- Work on the JARVIS `dev` branch only. NEVER touch the production DB; localhost `postgresql://localhost/defaultdb` is the default test/verify target.
- Grace window is exactly **8 hours** from `departure_datetime`. Define it **once** as `GRACE_HOURS = 8` and reference it everywhere (SQL interval + Python).
- New status value is the literal string `'MISSED'` (uppercase), alongside existing `'PLANNED' | 'FILLED' | 'COMPLETED' | 'PENDING'`.
- Routes must contain **no raw SQL** (architecture rule) — all SQL lives in `FoiParcursRepository`.
- Push copy is Romanian: title `"Sesiune ratată la start"`, body `"{client} — {vin} la {HH:MM}. Reprogramează sau activează."`, deep-link `"/sales/test-drive/{id}"`.
- Design spec: `docs/superpowers/specs/2026-07-28-missed-sessions-design.md`.

---

## File Structure

- Create `jarvis/foi_parcurs/session_lifecycle.py` — `GRACE_HOURS`, `derive_planned_substatus()`, `TD_STATUS_SQL`. Single source of truth for the lifecycle rule.
- Create `jarvis/tasks/foi_parcurs_sessions.py` — the APScheduler job (`run_session_lifecycle`).
- Create `jarvis/tests/foi_parcurs/test_session_lifecycle.py` — unit tests for the pure helper.
- Create `jarvis/tests/foi_parcurs/test_reschedule.py` — route tests for the reschedule endpoint.
- Create `jarvis/tests/tasks/test_foi_parcurs_sessions.py` — unit test for the sweeper job (mocked repo + notify).
- Modify `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py` — import `TD_STATUS_SQL`; add `find_conflicts` exclusion; add `reschedule_session`, `archive_missed_sessions`, `get_sessions_pending_late_notify`, `mark_late_notified`, `get_advisor_user_id`.
- Modify `jarvis/foi_parcurs/routes/test_drive.py` — add `api_reschedule_test_drive`.
- Modify `jarvis/tasks/cleanup.py` — register the 10-minute job.
- Modify `jarvis/migrations/domains/schema_incremental.py` — add the two columns + a partial index.

---

### Task 1: Migration — `missed_at`, `late_notified_at`, planned-departure index

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py` (the existing `foi_de_parcurs` `DO $$` block near line 2115–2152)

**Interfaces:**
- Produces: columns `foi_de_parcurs.missed_at TIMESTAMPTZ NULL`, `foi_de_parcurs.late_notified_at TIMESTAMPTZ NULL`; index `idx_fp_planned_departure`.

- [ ] **Step 1: Add the two columns to the existing idempotent block**

In the `foi_de_parcurs` `DO $$ BEGIN ... END $$;` block, add before its `END $$;`:

```sql
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='missed_at') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN missed_at TIMESTAMP WITH TIME ZONE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='foi_de_parcurs' AND column_name='late_notified_at') THEN
                ALTER TABLE foi_de_parcurs ADD COLUMN late_notified_at TIMESTAMP WITH TIME ZONE;
            END IF;
```

- [ ] **Step 2: Add a partial index for the sweeper/derivation (after that block's `''')`)**

```python
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fp_planned_departure ON foi_de_parcurs(departure_datetime) WHERE status = 'PLANNED'")
```

- [ ] **Step 3: Apply to localhost and verify**

Run (adjust to the project's migration entrypoint if different — this block runs on app startup; for an immediate check apply directly):

```bash
psql postgresql://localhost/defaultdb -c "ALTER TABLE foi_de_parcurs ADD COLUMN IF NOT EXISTS missed_at TIMESTAMPTZ; ALTER TABLE foi_de_parcurs ADD COLUMN IF NOT EXISTS late_notified_at TIMESTAMPTZ; CREATE INDEX IF NOT EXISTS idx_fp_planned_departure ON foi_de_parcurs(departure_datetime) WHERE status='PLANNED';"
psql postgresql://localhost/defaultdb -c "\d foi_de_parcurs" | grep -E "missed_at|late_notified_at"
```
Expected: both columns listed.

- [ ] **Step 4: Commit**

```bash
git add jarvis/migrations/domains/schema_incremental.py
git commit -m "feat(foi-parcurs): add missed_at/late_notified_at + planned-departure index"
```

---

### Task 2: Lifecycle single-source-of-truth + derived status SQL

**Files:**
- Create: `jarvis/foi_parcurs/session_lifecycle.py`
- Create: `jarvis/tests/foi_parcurs/test_session_lifecycle.py`
- Modify: `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py:16-22` (the `_TD_STATUS_SQL` constant)

**Interfaces:**
- Produces: `GRACE_HOURS: int`, `derive_planned_substatus(departure_dt, now) -> str` (`'planned'|'late'|'missed'`), `TD_STATUS_SQL: str` (a `CASE … END AS td_status` fragment referencing `fp.`).
- Consumes: nothing.

- [ ] **Step 1: Write the failing test**

`jarvis/tests/foi_parcurs/test_session_lifecycle.py`:

```python
from datetime import datetime, timedelta, timezone
from foi_parcurs.session_lifecycle import GRACE_HOURS, derive_planned_substatus, TD_STATUS_SQL

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)

def test_grace_is_eight_hours():
    assert GRACE_HOURS == 8

def test_future_departure_is_planned():
    assert derive_planned_substatus(NOW + timedelta(hours=1), NOW) == 'planned'

def test_just_past_departure_is_late():
    assert derive_planned_substatus(NOW - timedelta(minutes=1), NOW) == 'late'
    assert derive_planned_substatus(NOW - timedelta(hours=7, minutes=59), NOW) == 'late'

def test_at_or_past_grace_is_missed():
    assert derive_planned_substatus(NOW - timedelta(hours=8), NOW) == 'missed'
    assert derive_planned_substatus(NOW - timedelta(hours=9), NOW) == 'missed'

def test_none_departure_is_planned():
    assert derive_planned_substatus(None, NOW) == 'planned'

def test_sql_fragment_mentions_missed_and_late_and_interval():
    assert "'missed'" in TD_STATUS_SQL
    assert "'late'" in TD_STATUS_SQL
    assert "INTERVAL '8 hours'" in TD_STATUS_SQL
    assert 'AS td_status' in TD_STATUS_SQL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_session_lifecycle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'foi_parcurs.session_lifecycle'`.

- [ ] **Step 3: Implement `session_lifecycle.py`**

```python
"""Single source of truth for the Test Drive session lifecycle.

A PLANNED row is 'planned' until its departure; 'late' during the GRACE_HOURS
window after a missed start; 'missed' once GRACE_HOURS have elapsed. The same
rule is expressed as a SQL fragment (TD_STATUS_SQL) for the list/detail queries
and as a pure Python helper (derive_planned_substatus) for the sweeper job.
"""
from datetime import timedelta

GRACE_HOURS = 8


def derive_planned_substatus(departure_dt, now):
    """Sub-status of a PLANNED row: 'planned' | 'late' | 'missed'."""
    if departure_dt is None:
        return 'planned'
    if now >= departure_dt + timedelta(hours=GRACE_HOURS):
        return 'missed'
    if now >= departure_dt:
        return 'late'
    return 'planned'


# Derived status for Test Drive rows, evaluated missed → late → planned before
# the FILLED-era branches so an unactivated draft is never mislabeled 'driving'.
TD_STATUS_SQL = (
    "CASE "
    "WHEN fp.status = 'COMPLETED' THEN 'complete' "
    "WHEN fp.status = 'MISSED' THEN 'missed' "
    f"WHEN fp.status = 'PLANNED' AND fp.departure_datetime + INTERVAL '{GRACE_HOURS} hours' < NOW() THEN 'missed' "
    "WHEN fp.status = 'PLANNED' AND fp.departure_datetime < NOW() THEN 'late' "
    "WHEN fp.status = 'PLANNED' THEN 'planned' "
    "WHEN fp.return_datetime IS NOT NULL AND fp.return_datetime < NOW() THEN 'incomplete' "
    "ELSE 'driving' "
    "END AS td_status"
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_session_lifecycle.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Wire the repository to the shared fragment**

In `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py`, replace the local `_TD_STATUS_SQL = ( … )` definition (lines ~10-22) with an import and alias:

```python
from foi_parcurs.session_lifecycle import TD_STATUS_SQL as _TD_STATUS_SQL
```
Leave every existing `f'{_TD_STATUS_SQL} '` usage unchanged.

- [ ] **Step 6: Verify existing repo consumers still import cleanly**

Run: `cd jarvis && python -c "from foi_parcurs.repositories.foi_parcurs_repository import _TD_STATUS_SQL; print('missed' in _TD_STATUS_SQL)"`
Expected: prints `True`.

- [ ] **Step 7: Verify derivation on localhost (manual)**

```bash
psql postgresql://localhost/defaultdb -c "SELECT ($$SELECT CASE WHEN fp.status='PLANNED' AND fp.departure_datetime + INTERVAL '8 hours' < NOW() THEN 'missed' WHEN fp.status='PLANNED' AND fp.departure_datetime < NOW() THEN 'late' WHEN fp.status='PLANNED' THEN 'planned' END FROM (SELECT 'PLANNED'::text status, NOW() - INTERVAL '9 hours' departure_datetime) fp$$)"
```
Expected: `missed`.

- [ ] **Step 8: Commit**

```bash
git add jarvis/foi_parcurs/session_lifecycle.py jarvis/tests/foi_parcurs/test_session_lifecycle.py jarvis/foi_parcurs/repositories/foi_parcurs_repository.py
git commit -m "feat(foi-parcurs): derive late/missed td_status via shared session_lifecycle"
```

---

### Task 3: Free the vehicle — exclude missed/past-grace from `find_conflicts`

**Files:**
- Modify: `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py` (`find_conflicts`, the status filter ~line 324-325)

**Interfaces:**
- Consumes: `GRACE_HOURS` semantics (hard-coded `8 hours` interval, matching `TD_STATUS_SQL`).
- Produces: `find_conflicts` no longer returns MISSED or PLANNED-past-grace rows; still returns `late` (in-grace) rows.

- [ ] **Step 1: Edit the status filter**

Replace the open-session clause:

```python
            "AND ( fp.status = 'PLANNED' "
            "      OR (fp.status <> 'COMPLETED' AND fp.status <> 'PENDING') ) "
```
with:

```python
            "AND ( fp.status = 'PLANNED' "
            "      OR (fp.status <> 'COMPLETED' AND fp.status <> 'PENDING') ) "
            # A missed slot frees the vehicle: drop MISSED and PLANNED rows already
            # past the 8h grace (archived on the next sweeper pass). In-grace 'late'
            # rows still block — the client may yet show up.
            "AND fp.status <> 'MISSED' "
            "AND NOT (fp.status = 'PLANNED' AND fp.departure_datetime + INTERVAL '8 hours' < NOW()) "
```

- [ ] **Step 2: Verify on localhost — a past-grace planned row does not block**

```bash
psql postgresql://localhost/defaultdb -c "INSERT INTO foi_de_parcurs (vin, route_type, status, departure_datetime, return_datetime) VALUES ('TESTVIN_CONFLICT', 'TD', 'PLANNED', NOW() - INTERVAL '10 hours', NOW() - INTERVAL '9 hours');"
```
Then in a Python shell:
```bash
cd jarvis && python -c "
from datetime import datetime, timedelta, timezone
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
now = datetime.now(timezone.utc)
rows = FoiParcursRepository().find_conflicts('TESTVIN_CONFLICT', now - timedelta(hours=11), now)
print('conflicts:', len(rows))
"
```
Expected: `conflicts: 0` (past-grace planned row excluded). Clean up:
```bash
psql postgresql://localhost/defaultdb -c "DELETE FROM foi_de_parcurs WHERE vin='TESTVIN_CONFLICT';"
```

- [ ] **Step 3: Commit**

```bash
git add jarvis/foi_parcurs/repositories/foi_parcurs_repository.py
git commit -m "feat(foi-parcurs): free the vehicle from missed/past-grace sessions in conflict check"
```

---

### Task 4: Reschedule / revive endpoint

**Files:**
- Modify: `jarvis/foi_parcurs/routes/test_drive.py` (add `api_reschedule_test_drive` after `api_update_plan`, ~line 332)
- Modify: `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py` (add `reschedule_session` after `update_plan`)
- Create: `jarvis/tests/foi_parcurs/test_reschedule.py`

**Interfaces:**
- Consumes: `_fp_repo.get_contract_by_id`, `datetime`/`timezone` (already imported in `test_drive.py`).
- Produces:
  - Route `PUT /api/foi-parcurs/test-drive/<id>/reschedule`, body `{departure_datetime, return_datetime?}`, returns `{success, contract}`; `400` (missing/invalid/past departure), `404`, `409` (not PLANNED/MISSED).
  - `FoiParcursRepository.reschedule_session(contract_id, departure_datetime, return_datetime) -> dict`.

- [ ] **Step 1: Write the failing route tests**

`jarvis/tests/foi_parcurs/test_reschedule.py` (mirrors `test_test_drive_submit.py`'s app/client fixtures + module-level repo mock):

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from unittest.mock import MagicMock
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def repo(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr(td, '_fp_repo', m)
    return m


def _future():
    return '2999-01-01T10:00:00'


def test_reschedule_planned_ok(client, repo):
    repo.get_contract_by_id.return_value = {'id': 5, 'route_type': 'TD', 'status': 'PLANNED'}
    repo.reschedule_session.return_value = {'id': 5, 'status': 'PLANNED'}
    r = client.put('/api/foi-parcurs/test-drive/5/reschedule',
                   json={'departure_datetime': _future(), 'return_datetime': '2999-01-01T11:00:00'})
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    repo.reschedule_session.assert_called_once_with(5, _future(), '2999-01-01T11:00:00')


def test_reschedule_missed_revives(client, repo):
    repo.get_contract_by_id.return_value = {'id': 6, 'route_type': 'TD', 'status': 'MISSED'}
    repo.reschedule_session.return_value = {'id': 6, 'status': 'PLANNED'}
    r = client.put('/api/foi-parcurs/test-drive/6/reschedule', json={'departure_datetime': _future()})
    assert r.status_code == 200


def test_reschedule_rejects_live(client, repo):
    repo.get_contract_by_id.return_value = {'id': 7, 'route_type': 'TD', 'status': 'FILLED'}
    r = client.put('/api/foi-parcurs/test-drive/7/reschedule', json={'departure_datetime': _future()})
    assert r.status_code == 409
    repo.reschedule_session.assert_not_called()


def test_reschedule_requires_departure(client, repo):
    repo.get_contract_by_id.return_value = {'id': 8, 'route_type': 'TD', 'status': 'PLANNED'}
    r = client.put('/api/foi-parcurs/test-drive/8/reschedule', json={})
    assert r.status_code == 400


def test_reschedule_rejects_past(client, repo):
    repo.get_contract_by_id.return_value = {'id': 9, 'route_type': 'TD', 'status': 'PLANNED'}
    r = client.put('/api/foi-parcurs/test-drive/9/reschedule',
                   json={'departure_datetime': '2000-01-01T10:00:00'})
    assert r.status_code == 400
    repo.reschedule_session.assert_not_called()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_reschedule.py -v`
Expected: FAIL (404/405 — route not registered).

- [ ] **Step 3: Add the repository method**

In `foi_parcurs_repository.py`, after `update_plan`:

```python
    def reschedule_session(self, contract_id: int, departure_datetime, return_datetime) -> dict:
        """Move a PLANNED/MISSED session to a new time and revive it to PLANNED,
        clearing the missed/late-notify stamps. Guarded to those two statuses."""
        sql = (
            "UPDATE foi_de_parcurs SET departure_datetime = %s, return_datetime = %s, "
            "status = 'PLANNED', missed_at = NULL, late_notified_at = NULL, updated_at = NOW() "
            "WHERE id = %s AND route_type = 'TD' AND status IN ('PLANNED', 'MISSED') RETURNING *"
        )
        row = self.execute(sql, (departure_datetime, return_datetime, contract_id), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row
```

- [ ] **Step 4: Add the route**

In `test_drive.py`, after `api_update_plan` (before `_autosend_completed_contract`):

```python
@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>/reschedule', methods=['PUT'])
@login_required
def api_reschedule_test_drive(id):
    """Reschedule a PLANNED (late) or MISSED session to a new future time,
    reviving it to PLANNED. VIN conflicts are soft-checked client-side (the
    conflicts endpoint), mirroring plan/activate — this endpoint only moves it."""
    data = request.get_json(silent=True) or {}
    departure = data.get('departure_datetime')
    if not departure:
        return jsonify({'success': False, 'error': 'departure_datetime is required'}), 400
    try:
        contract = _fp_repo.get_contract_by_id(id)
        if not contract:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        if contract.get('route_type') != 'TD' or contract.get('status') not in ('PLANNED', 'MISSED'):
            return jsonify({'success': False, 'error': 'Only planned or missed sessions can be rescheduled'}), 409
        try:
            dep_dt = datetime.fromisoformat(str(departure).replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid departure_datetime'}), 400
        if dep_dt.date() < datetime.now(timezone.utc).date():
            return jsonify({'success': False, 'error': 'Cannot reschedule to a past date'}), 400
        updated = _fp_repo.reschedule_session(id, departure, data.get('return_datetime'))
        if not (updated and updated.get('id')):
            return jsonify({'success': False, 'error': 'Session is no longer reschedulable'}), 409
        return jsonify({'success': True, 'contract': updated})
    except Exception as e:
        logger.exception('Failed to reschedule test drive %s', id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500
```

Confirm `datetime`/`timezone` are imported at the top of `test_drive.py` (they are used by `api_activate_test_drive`); if not, add `from datetime import datetime, timezone`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd jarvis && python -m pytest tests/foi_parcurs/test_reschedule.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add jarvis/foi_parcurs/routes/test_drive.py jarvis/foi_parcurs/repositories/foi_parcurs_repository.py jarvis/tests/foi_parcurs/test_reschedule.py
git commit -m "feat(foi-parcurs): reschedule/revive endpoint for late + missed sessions"
```

---

### Task 5: Sweeper job — notify newly-late, archive past-grace

**Files:**
- Create: `jarvis/tasks/foi_parcurs_sessions.py`
- Create: `jarvis/tests/tasks/test_foi_parcurs_sessions.py`
- Modify: `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py` (add `get_sessions_pending_late_notify`, `mark_late_notified`, `archive_missed_sessions`, `get_advisor_user_id`)
- Modify: `jarvis/tasks/cleanup.py` (import + `add_job`)

**Interfaces:**
- Consumes: `notify_with_push(user_ids, title, message, link=, entity_type=, entity_id=, category=)`.
- Produces:
  - `FoiParcursRepository.get_sessions_pending_late_notify() -> list[dict]` (rows with `id, advisor_name, client_name, vin, departure_datetime`).
  - `FoiParcursRepository.mark_late_notified(contract_id) -> None`.
  - `FoiParcursRepository.archive_missed_sessions() -> int` (count archived).
  - `FoiParcursRepository.get_advisor_user_id(advisor_name) -> int | None`.
  - `tasks.foi_parcurs_sessions.run_session_lifecycle() -> None`.

- [ ] **Step 1: Write the failing job test (mocked repo + notify)**

`jarvis/tests/tasks/test_foi_parcurs_sessions.py`:

```python
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import tasks.foi_parcurs_sessions as job


def test_notifies_pending_and_marks_then_archives():
    repo = MagicMock()
    repo.get_sessions_pending_late_notify.return_value = [
        {'id': 11, 'advisor_name': 'Ana Pop', 'client_name': 'Ion Ilie',
         'vin': 'WVW1', 'departure_datetime': datetime(2026, 7, 28, 9, 30, tzinfo=timezone.utc)},
    ]
    repo.get_advisor_user_id.return_value = 42
    repo.archive_missed_sessions.return_value = 3

    with patch.object(job, 'FoiParcursRepository', return_value=repo), \
         patch.object(job, 'notify_with_push') as push:
        job.run_session_lifecycle()

    push.assert_called_once()
    args, kwargs = push.call_args
    assert args[0] == [42]
    assert args[1] == 'Sesiune ratată la start'
    assert kwargs['link'] == '/sales/test-drive/11'
    repo.mark_late_notified.assert_called_once_with(11)
    repo.archive_missed_sessions.assert_called_once()


def test_skips_push_when_advisor_unresolved_but_still_marks():
    repo = MagicMock()
    repo.get_sessions_pending_late_notify.return_value = [
        {'id': 12, 'advisor_name': 'Ghost', 'client_name': 'X', 'vin': 'V',
         'departure_datetime': datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)},
    ]
    repo.get_advisor_user_id.return_value = None
    repo.archive_missed_sessions.return_value = 0

    with patch.object(job, 'FoiParcursRepository', return_value=repo), \
         patch.object(job, 'notify_with_push') as push:
        job.run_session_lifecycle()

    push.assert_not_called()
    repo.mark_late_notified.assert_called_once_with(12)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd jarvis && python -m pytest tests/tasks/test_foi_parcurs_sessions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tasks.foi_parcurs_sessions'`.

- [ ] **Step 3: Add the repository methods**

In `foi_parcurs_repository.py`:

```python
    def get_sessions_pending_late_notify(self) -> list:
        """PLANNED TD rows whose start just passed (still in the 8h grace) and
        that haven't been late-notified yet."""
        sql = (
            "SELECT fp.id, fp.advisor_name, "
            "COALESCE(fp.client_name, c.name) AS client_name, fp.vin, fp.departure_datetime "
            "FROM foi_de_parcurs fp LEFT JOIN fp_clients c ON c.id = fp.client_id "
            "WHERE fp.route_type = 'TD' AND fp.status = 'PLANNED' "
            "AND fp.departure_datetime < NOW() "
            "AND fp.departure_datetime + INTERVAL '8 hours' >= NOW() "
            "AND fp.late_notified_at IS NULL"
        )
        return self.query_all(sql)

    def mark_late_notified(self, contract_id: int) -> None:
        self.execute('UPDATE foi_de_parcurs SET late_notified_at = NOW() WHERE id = %s', (contract_id,))

    def archive_missed_sessions(self) -> int:
        """Flip PLANNED TD rows past the 8h grace to MISSED. Returns the count.

        `BaseRepository.execute(..., returning=False)` commits and returns the
        rowcount — exactly the number archived — so no RETURNING is needed."""
        return self.execute(
            "UPDATE foi_de_parcurs SET status = 'MISSED', missed_at = NOW(), updated_at = NOW() "
            "WHERE route_type = 'TD' AND status = 'PLANNED' "
            "AND departure_datetime + INTERVAL '8 hours' < NOW()"
        ) or 0

    def get_advisor_user_id(self, advisor_name):
        """Resolve a session's advisor (by name) to a users.id, or None."""
        name = (advisor_name or '').strip()
        if not name:
            return None
        row = self.query_one(
            'SELECT id FROM users WHERE LOWER(name) = LOWER(%s) ORDER BY id LIMIT 1', (name,)
        )
        return row['id'] if row else None
```

Repo helper reference (confirmed on `BaseRepository`): `query_all(sql, params)` → list of dicts (SELECT); `query_one(sql, params)` → one dict; `execute(sql, params, returning=False)` → commits, returns rowcount; `execute(sql, params, returning=True)` → commits, returns one dict (`fetchone`). `get_sessions_pending_late_notify` uses `query_all` (SELECT); `mark_late_notified` uses `execute` (write, no return); `reschedule_session` uses `execute(returning=True)` (one updated row by id).

- [ ] **Step 4: Add the job module**

`jarvis/tasks/foi_parcurs_sessions.py`:

```python
"""Background job: Test Drive session lifecycle.

Every 10 minutes — (1) push the consilier once when a PLANNED session's start
hour is missed (still inside the 8h grace), (2) archive sessions past the grace
to MISSED (which frees the vehicle in conflict checks). Both passes idempotent.
"""
from core.utils.logging_config import get_logger
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
from core.notifications.notify import notify_with_push

logger = get_logger('jarvis.tasks.foi_parcurs_sessions')


def run_session_lifecycle():
    try:
        repo = FoiParcursRepository()
        for row in repo.get_sessions_pending_late_notify():
            try:
                uid = repo.get_advisor_user_id(row.get('advisor_name'))
                if uid:
                    dep = row.get('departure_datetime')
                    when = dep.strftime('%H:%M') if dep else ''
                    client = (row.get('client_name') or 'Client').strip()
                    veh = (row.get('vin') or '').strip()
                    notify_with_push(
                        [uid],
                        'Sesiune ratată la start',
                        f'{client} — {veh} la {when}. Reprogramează sau activează.',
                        link=f"/sales/test-drive/{row['id']}",
                        entity_type='foi_parcurs_td',
                        entity_id=row['id'],
                        category='system',
                    )
                repo.mark_late_notified(row['id'])
            except Exception:
                logger.warning('late-notify failed for session %s', row.get('id'), exc_info=True)

        count = repo.archive_missed_sessions()
        if count:
            logger.info('Archived %s missed TD session(s)', count)
    except Exception as e:
        logger.error('Session lifecycle job failed: %s', e, exc_info=True)
```

- [ ] **Step 5: Run the job test to verify it passes**

Run: `cd jarvis && python -m pytest tests/tasks/test_foi_parcurs_sessions.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Register the job in the scheduler**

In `jarvis/tasks/cleanup.py`, add to the imports block (near line 6-20):

```python
from tasks.foi_parcurs_sessions import run_session_lifecycle
```
and inside `start_scheduler()`, alongside the other `scheduler.add_job(...)` calls:

```python
    scheduler.add_job(
        run_session_lifecycle,
        'interval',
        minutes=10,
        id='foi_parcurs_sessions',
        replace_existing=True,
    )
```
(Match the exact keyword style of the surrounding `add_job` calls — copy `replace_existing`/`max_instances` if the neighbors use them.)

- [ ] **Step 7: Smoke-test end to end on localhost**

```bash
psql postgresql://localhost/defaultdb -c "INSERT INTO foi_de_parcurs (vin, route_type, status, advisor_name, departure_datetime) VALUES ('SWEEPVIN', 'TD', 'PLANNED', 'nobody', NOW() - INTERVAL '9 hours');"
cd jarvis && python -c "from tasks.foi_parcurs_sessions import run_session_lifecycle; run_session_lifecycle()"
psql postgresql://localhost/defaultdb -c "SELECT status, missed_at IS NOT NULL archived FROM foi_de_parcurs WHERE vin='SWEEPVIN';"
psql postgresql://localhost/defaultdb -c "DELETE FROM foi_de_parcurs WHERE vin='SWEEPVIN';"
```
Expected: one row, `status = MISSED`, `archived = t`.

- [ ] **Step 8: Commit**

```bash
git add jarvis/tasks/foi_parcurs_sessions.py jarvis/tests/tasks/test_foi_parcurs_sessions.py jarvis/foi_parcurs/repositories/foi_parcurs_repository.py jarvis/tasks/cleanup.py
git commit -m "feat(foi-parcurs): sweeper job — notify missed-at-start + archive past-grace to MISSED"
```

---

### Task 6: Full backend suite green + regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the foi_parcurs + tasks suites**

Run: `cd jarvis && python -m pytest tests/foi_parcurs tests/tasks -v`
Expected: PASS, including the existing `test_test_drive_submit.py` / `test_test_drive_return.py` (the `_TD_STATUS_SQL` import change must not break them).

- [ ] **Step 2: Confirm the derived-status list endpoint still serializes**

Run: `cd jarvis && python -c "from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository as R; print('ok')"`
Expected: prints `ok` (no import-time error from the fragment swap).

- [ ] **Step 3: No commit** (verification task).

---

## Self-Review

- **Spec coverage:** migration (B1) ✓; `_TD_STATUS_SQL` late/missed (B2) ✓; `find_conflicts` frees vehicle (B3) ✓; reschedule endpoint incl. MISSED-revive + past/live guards (B4) ✓; APScheduler notify + archive passes with dedupe (B5) ✓; push copy/link/target via advisor→user (B5) ✓; discard-in-grace unchanged (existing DELETE, no task needed — grace rows are still PLANNED) ✓.
- **Placeholder scan:** none; every step has concrete SQL/Python/tests. The two "confirm the neighboring helper" notes (B5 write-returning; B5 add_job kwargs) are verification-against-existing-code instructions, not deferred work.
- **Type consistency:** `reschedule_session(contract_id, departure_datetime, return_datetime)`, `get_advisor_user_id(advisor_name)`, `archive_missed_sessions() -> int`, `run_session_lifecycle()`, `TD_STATUS_SQL`, `GRACE_HOURS` are used identically across tasks and tests.

## Handoff

This is the **backend** half. It deploys through JARVIS dev → staging → main and must be **live before** the mobile build ships (per the spec's sequencing). The mobile half is `2026-07-28-missed-sessions-mobile.md`.
