# HR Divisions — Design Spec

**Date:** 2026-09-07
**Status:** Draft for review
**Author:** brainstorming session

## Problem

The Sincron organigram is **per-company** (`sincron_org_nodes`, levels L1–L5). Some
employees report to a **division manager** who is responsible for a function (e.g.
Aftersales) **across multiple companies**. `get_direct_manager`
([manager_utils.py:171](../../../jarvis/core/organization/manager_utils.py)) walks
**up** the employee's per-company node chain looking for the nearest ancestor node
that has a `responsable`. When the real boss is a cross-company division manager who
sits outside that per-company branch, the walk finds nobody and returns `None`.

Consequences:
- The bilet/leave approver resolves to no one → the request routes to nobody and
  auto-approves after 24h with no oversight; the UI shows **"Fără aprobator"**.
- The division manager has no team visibility in organigram / 360 / pontaje.

**Confirmed example (prod):** `form_submissions.id = 163`, Duca Călin Cornel
(Autoworld PREMIUM), `pending_approval`, `context_snapshot.approver_user_id` empty,
`stakeholder_approver_ids = []`.

## Goals

- Model cross-company **Divisions**: a JARVIS-owned grouping of Sincron departments
  with one or more **responsables** (division managers).
- A division responsable becomes the **effective manager (fallback)** for division
  members: bilet approver + team visibility (organigram / 360 / pontaje) + counts as
  `is_manager`.
- New HR **Divisions tab** to create/manage them.
- **Sync-safe**: never mutate the Sincron-synced tables.

## Non-goals (YAGNI)

- No nested divisions (flat list).
- No overriding existing managers — division applies **only as a fallback**.
- Departments and department managers still come from Sincron; not editable here.
- No backfill; HR creates divisions manually.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| When does the division responsable approve? | **Fallback only** — only when the employee has no manager above them in Sincron. |
| Scope of the division responsable | **Full manager** — approver + team visibility + `is_manager`. |
| Responsables per division | **One or more** (any can approve → `stakeholder_approver_ids`). |
| Departments across companies | **Yes**, any company; a department belongs to **at most one** division. |

## Data model

Three JARVIS-owned tables (idempotent DDL in `migrations/domains/schema_*.py`).
`node_id` → `sincron_org_nodes.id` is safe: that repo does incremental
INSERT/UPDATE/DELETE (ids are stable), and `sincron_org_members` / `event_bonus_days`
already FK to it.

```sql
CREATE TABLE IF NOT EXISTS hr_divisions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hr_division_departments (
    id SERIAL PRIMARY KEY,
    division_id INTEGER NOT NULL REFERENCES hr_divisions(id) ON DELETE CASCADE,
    node_id     INTEGER NOT NULL REFERENCES sincron_org_nodes(id) ON DELETE CASCADE,
    UNIQUE (node_id)               -- a department lives in at most one division
);

CREATE TABLE IF NOT EXISTS hr_division_responsables (
    id SERIAL PRIMARY KEY,
    division_id INTEGER NOT NULL REFERENCES hr_divisions(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (division_id, user_id)
);
```

"Division members" = every `sincron_org_members.role='member'` on a division's
department nodes **and their descendants** (reusing the existing recursive descent).

## Resolution integration

A division behaves as a **virtual parent** above its member department nodes. One
shared helper keeps the four call sites consistent; all live in
`core/organization/manager_utils.py`.

**Shared helper**
```
division_responsable_ids_for_user(user_id) -> [user_id, ...]
    # divisions whose department node is an ancestor-or-self of any of the user's
    # nodes; return that division's responsable ids, excluding the user themselves.
```

1. **`get_direct_manager(user_id)`** — run the existing Sincron walk first. Only if it
   returns `None`, call the helper and return the **primary** division responsable
   (lowest user_id for determinism), or `None`. → fixes Duca, and makes department
   managers (who top out in Sincron) report up to the division manager. Employees who
   already have a manager are **unchanged**.

2. **Leave stakeholders** — `_resolve_form_approver` already calls
   `get_direct_manager`, so the primary flows through automatically. Extend
   `form_service._build_stakeholder_ids` so that when the approver came from a division
   fallback, **all** the division's responsables become `stakeholder_approver_ids`
   (any can approve), matching the existing multi-approver behaviour.

3. **`get_managed_employee_ids(manager_user_id, node_id=None)`** — union in the
   members (+descendants) of every department node of the divisions this user is a
   responsable of.

4. **`get_visible_tree(manager_user_id)`** — append a synthetic division node
   (`id = 'division-<id>'`, level 0) with its department nodes + descendants for each
   division the caller is responsable of.

5. **`is_manager(user_id)`** — also `True` when the user is in
   `hr_division_responsables`.

6. **`_node_in_scope`** — a division responsable's scope also covers their division's
   department nodes (+descendants), so node-scoped team queries work.

## API

New blueprint under `core/organization` (or `hr`), guarded by the existing HR/org-admin
permission used by the organigram tab.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/divisions` | list: name, responsables, departments, counts |
| POST | `/api/divisions` | create `{name}` |
| PATCH | `/api/divisions/<id>` | rename |
| DELETE | `/api/divisions/<id>` | delete (cascades membership) |
| PUT | `/api/divisions/<id>/departments` | set `{node_ids: [...]}` |
| PUT | `/api/divisions/<id>/responsables` | set `{user_ids: [...]}` |
| GET | `/api/divisions/available-departments` | Sincron nodes grouped by company, for the picker (flags nodes already taken by another division) |

Repository subclasses `core.base_repository.BaseRepository`; raw SQL, `%s` params.

## Frontend

New `DivisionsTab.tsx` (React/TS/shadcn), added to the HR tab bar next to Organigram.

- **List:** divisions with name · responsable chip(s) · department count.
- **Editor (dialog or side panel):** name; responsable picker (users search);
  department picker — Sincron departments grouped by company, fed from
  `available-departments`, with already-assigned nodes disabled/annotated.
- Create / edit / delete. React Query; unwrap the API envelope.

## Testing

Backend unit tests (`tests/org/`), extending the existing Sincron fixtures:
- employee with **no** Sincron manager but in a division → division responsable;
- employee **with** a Sincron manager, node also in a division → manager wins (no
  override);
- department manager (tops out in Sincron) → division responsable (subordination);
- `get_managed_employee_ids` / `get_visible_tree` include division members for the
  responsable; `is_manager` true for a division responsable;
- employee in no division → all functions unchanged.

API CRUD tests: create/rename/delete, set departments (uniqueness enforced —
assigning a node already in another division is rejected), set responsables.

## Rollout

- Idempotent DDL added to `schema_*.py` + `init_schema.py`.
- No data backfill.
- Ship dev → staging → main via the standard cherry-pick promotion. (This design doc
  stays on `dev`/scratch, not promoted.)

## Risks / open items

- **Performance:** the division fallback adds one indexed query per
  `get_direct_manager` call. The bilete list already resolves approvers per-row; keep
  the helper a single recursive query and index `hr_division_departments(node_id)`.
- **Ambiguity:** if an employee's node is covered by more than one division (should be
  prevented by `UNIQUE(node_id)`, but ancestor overlap is possible if a parent and
  child node are in different divisions) — resolve to the **nearest** division node on
  the walk up.
- **Deactivated responsables:** exclude responsables whose user/`sincron_employees`
  row is inactive, mirroring the existing `is_active` filters.
