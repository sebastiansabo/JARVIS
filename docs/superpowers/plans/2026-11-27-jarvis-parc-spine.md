# JARVIS Parc (Logistics) — Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task (a fresh implementer per task, a fresh reviewer before the next starts). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core of the JARVIS Parc logistics module — ingest jarvis-alpha events idempotently into a vehicle register and a Kanban task board, with the three enforced move-gates and a full audit history — satisfying the acceptance test in the design spec.

**Architecture:** A new **independent module inside the Flask JARVIS monolith** (`jarvis/logistics/`, mirroring `jarvis/carpark/`): own schema, repositories, services and a Flask blueprint; never writes other modules' tables. jarvis-alpha pushes events to `POST /api/logistics/intake/events`; editable mapping rules translate each event into create/update actions on `logistics_vehicles` / `logistics_tasks`. Physical stage (`etapa_parc`) and handover readiness (`predare`) are separate axes; human-confirmed fields are authoritative over later intake events. React frontend under `pages/Logistics/`.

**Tech Stack:** Python / Flask (blueprints) · Postgres (shared JARVIS DB, `company_id`-scoped) · repository pattern · pytest · React + Vite (fetch-client `ApiError`, react-query) · shadcn-style components.

**Spec:** `docs/superpowers/specs/2026-11-27-jarvis-parc-design.md`

## Global Constraints

- **Module home:** `jarvis/logistics/` (`repositories/`, `routes/`, `services/`, `__init__.py`). Schema: `jarvis/migrations/domains/schema_logistics.py`, registered in `jarvis/migrations/domains/__init__.py`, `CREATE TABLE IF NOT EXISTS`, `init_db()`-on-import — **never app-import to run it**. Blueprint registered where the other module blueprints register. Frontend: `jarvis/frontend/src/pages/Logistics/` + `jarvis/frontend/src/api/logistics.ts`.
- **No cross-module writes.** Logistics writes only `logistics_*` tables.
- **Tests run with the repo venv python**, never bare `python3`: `venv/bin/python -m pytest …` (bare python triggers a circular-import collection error).
- **Tenant scoping:** every table carries `company_id`; every query filters by it.
- **Romanian UI labels, verbatim:** Kanban columns `De făcut / În lucru / Blocat / Finalizat`; Parc columns `Vehicul · Comandă · Locație · Poziție · Destinație · Etapă Parc · Predare · VIN`.
- **Enums (exact):** `etapa_parc ∈ {În tranzit, În pregătire, În stoc, Expunere}`; `predare ∈ {În așteptare, Pregătit de predare, Blocat, Predat}`; `destinatie ∈ {Intern, AAP, Export, Expunere}`; `task.status ∈ {De făcut, În lucru, Blocat, Finalizat}`; `task.type ∈ {Recepție, Îngrijire, Programare, Documente, Predare}`.
- **Identity = `order_ref`** (`AW-####`). **Ordering = `event_ts`** (monotonic, stored per order as `last_event_ts`). VIN nullable until reception confirmed.
- **Confirmed > intake:** fields set by human confirmation are flagged in `confirmed_fields` (jsonb); intake never overwrites a confirmed field.
- **Frontend error shape:** fetch-client `ApiError = {status,data,message}` (no `.response`); surface `e?.data?.error || e?.message`.
- **TDD, DRY, YAGNI, frequent commits.** One deliverable per task.

## Review Focus

- **Malformed / unknown-field event** → logged to `logistics_intake_events` with `result='ignored'`, returns 200, never 500. (Task 5)
- **Out-of-order: ETA event for an unknown order** → upsert creates the vehicle+task with that ETA (first-seen wins). (Task 3)
- **Concurrent duplicate events** (same `order_ref`) → UNIQUE constraint on `order_ref` guarantees one vehicle. (Task 2)
- **Null VIN in Parc** → search/filter/sort treat null VIN as empty, never crash; row still selectable. (Task 6)
- **Blocat without a next action** → move rejected (`MoveError`), card stays put, clear message. (Task 8)

---

### Task 1: Schema & repositories

**Files:**
- Create: `jarvis/migrations/domains/schema_logistics.py`; `jarvis/logistics/__init__.py`; `jarvis/logistics/repositories/{vehicle_repository,task_repository,location_repository,history_repository,mapping_rule_repository}.py`
- Modify: `jarvis/migrations/domains/__init__.py` (register schema)
- Test: `jarvis/tests/logistics/test_schema.py`

**Interfaces:**
- Produces tables `logistics_vehicles` (order_ref UNIQUE NOT NULL, vin NULL, model, plate NULL, destinatie, location_id NULL, position_id NULL, etapa_parc, predare DEFAULT `În așteptare`, eta NULL, arrived_at NULL, confirmed_fields JSONB DEFAULT '{}', last_event_ts BIGINT NULL, company_id, created_at, updated_at), `logistics_tasks`, `logistics_locations`, `logistics_positions`, `logistics_intake_events`, `logistics_vehicle_history`, `logistics_mapping_rules` (columns per design §3).
- Repo functions (consumed by later tasks): `get_vehicle_by_order_ref(order_ref, company_id)`, `create_vehicle(data)`, `update_vehicle(id, patch)`, `create_task(data)`, `get_open_reception_task(vehicle_id)`, `update_task(id, patch)`, `record_history(vehicle_id, event_type, old, new, actor)`.

- [ ] **Step 1: Write the failing test** — `test_schema.py`: creates a vehicle + a task via repos and reads them back; asserts inserting a second vehicle with the same `order_ref` raises a unique-violation.
- [ ] **Step 2: Run to verify it fails** — `Run: venv/bin/python -m pytest jarvis/tests/logistics/test_schema.py -v` · Expected: FAIL (module/tables missing).
- [ ] **Step 3: Implement** the schema file + registration + the five repository modules (follow `jarvis/carpark/repositories/vehicle_repository.py` style).
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): schema + repositories`.

---

### Task 2: Intake — idempotent create

**Files:** Create `jarvis/logistics/services/intake.py`, `jarvis/logistics/services/rules.py` · Test: `jarvis/tests/logistics/test_intake_create.py`

**Interfaces:**
- Consumes Task 1 repos.
- Produces `apply_event(event: dict) -> dict` where `event = {"order_ref","code","event_ts","payload"}` and the return is `{"result": "created"|"updated"|"duplicate"|"ignored", "vehicle_id"?, "task_id"?}`. Default rule in `rules.py`: code `Transport in derulare` → create vehicle (`etapa_parc='În tranzit'`, `destinatie` from payload) + one `Recepție` task `Recepționează mașina`, `due_at = payload.eta`.

- [ ] **Step 1: Write the failing test** — `test_double_transport_event_creates_one_vehicle_one_reception`: call `apply_event` twice for `AW-2418`; assert one `logistics_vehicles` row, one `Recepție` task, second result `== 'duplicate'`.
- [ ] **Step 2: Run to verify it fails** — `Run: venv/bin/python -m pytest jarvis/tests/logistics/test_intake_create.py -v` · Expected: FAIL.
- [ ] **Step 3: Implement** `apply_event` + default create rule; dedup by `order_ref`; write `logistics_vehicle_history` `created`.
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): idempotent intake create`.

---

### Task 3: Intake — ETA update (+ first-seen upsert)

**Files:** Modify `jarvis/logistics/services/intake.py`, `rules.py` · Test: `jarvis/tests/logistics/test_intake_eta.py`

**Interfaces:** Consumes Task 2 `apply_event`. Rule: code `ETA actualizat` → update the order's open `Recepție` task `due_at`; unknown order → upsert (create vehicle+task with that ETA).

- [ ] **Step 1: Write the failing test** — (a) `test_eta_updates_same_card`: assert task count stays 1 and `due_at` changed; (b) `test_eta_for_unknown_order_upserts`.
- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.
- [ ] **Step 3: Implement** the ETA rule + update branch; history `eta_updated`.
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): intake ETA update + upsert`.

---

### Task 4: Intake — stale-event guard (confirmed > intake)

**Files:** Modify `jarvis/logistics/services/intake.py` · Test: `jarvis/tests/logistics/test_intake_stale.py`

**Interfaces:** Consumes Task 2/3. `apply_event` ignores events with `event_ts <= logistics_vehicles.last_event_ts` for that order (`result='ignored'`) and skips any field listed in `confirmed_fields`.

- [ ] **Step 1: Write the failing test** — `test_older_event_does_not_overwrite_confirmed_bay`: seed vehicle with `position_id` set + `confirmed_fields={"position_id":true}` + `last_event_ts=200`; apply a `Transport in derulare` with `event_ts=100` and a different position; assert `position_id` unchanged and result `'ignored'`.
- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.
- [ ] **Step 3: Implement** the ordering + confirmed-field guard; update `last_event_ts` on every applied event.
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): stale-event guard`.

---

### Task 5: Intake blueprint + mapping endpoint

**Files:** Create `jarvis/logistics/routes/__init__.py`, `jarvis/logistics/routes/intake.py` · Modify blueprint registry (where module blueprints register) · Test: `jarvis/tests/logistics/test_intake_api.py`

**Interfaces:** `POST /api/logistics/intake/events` validates the body → `apply_event` → 200 `{result}`. Invalid/unknown-field body → 200 `{result:'ignored'}` + a `logistics_intake_events` row (never 500). `GET /api/logistics/intake/mapping` → active rules.

- [ ] **Step 1: Write the failing test** — `test_post_twice_created_then_duplicate_one_vehicle` (Flask test client); `test_malformed_body_returns_ignored_and_logs_event` (asserts 200 + an `logistics_intake_events` row, no 500).
- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.
- [ ] **Step 3: Implement** the blueprint + validation + `logistics_intake_events` logging; register the blueprint.
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): intake blueprint + mapping`.

---

### Task 6: Parc register — query API + table UI

**Files:** Create `jarvis/logistics/routes/vehicles.py`; `jarvis/frontend/src/api/logistics.ts`; `jarvis/frontend/src/pages/Logistics/Parc.tsx` · Modify `jarvis/frontend/src/App.tsx` (route) + `Sidebar.tsx` (nav "Parc") · Test: `jarvis/tests/logistics/test_vehicle_query.py`

**Interfaces:** `list_vehicles(filters: dict) -> list[dict]` with `filters = {q?, location_id?, destinatie?, etapa?, predare?, sort?, dir?, company_id}`; rows carry the 8 display columns + ids; `q` matches VIN / order_ref / model / plate with null VIN treated as empty. `GET /api/logistics/vehicles` wraps it.

- [ ] **Step 1: Write the failing test** — `test_filter_by_etapa_and_search_by_order`; `test_null_vin_vehicle_matched_by_order_no_crash`; `test_sort_by_etapa_stable`.
- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.
- [ ] **Step 3: Implement** `list_vehicles` + route; then `Parc.tsx` table (Etapă Parc and Predare as **separate columns**; search + filters + Resetează; pinned `Vehicul` column on mobile; row → `/app/logistics/parc/:id` preserving query/sort), and `logistics.ts` client.
- [ ] **Step 4: Run to verify it passes** — Expected: PASS (plus manual UI check).
- [ ] **Step 5: Commit** — `feat(logistics): vehicle register query + table`.

---

### Task 7: Kanban — board API + board UI

**Files:** Create `jarvis/logistics/routes/tasks.py`; `jarvis/frontend/src/pages/Logistics/Kanban.tsx` · Modify `logistics.ts`, `App.tsx`, `Sidebar.tsx` · Test: `jarvis/tests/logistics/test_board.py`

**Interfaces:** `get_board(filters: dict) -> dict[str, list[dict]]` keyed by the four statuses in fixed order; `filters = {q?, location_id?, assignee?, company_id}`; card dict = `{id,title,type,vehicle_model,order_ref,location_name,position_code,assignee,due_at}`. `GET /api/logistics/board`.

- [ ] **Step 1: Write the failing test** — `test_groups_tasks_into_four_columns_with_counts`; `test_filter_by_assignee_and_search`.
- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.
- [ ] **Step 3: Implement** `get_board` (join tasks→vehicles/locations) + route; then `Kanban.tsx` (4 columns, card fields, desktop drag, mobile `Mută` menu — move wiring in Tasks 8–10).
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): kanban board`.

---

### Task 8: Move — Blocat gate + history

**Files:** Create `jarvis/logistics/services/moves.py`; `jarvis/logistics/routes/tasks.py` (add move route) · Test: `jarvis/tests/logistics/test_move_blocat.py`

**Interfaces:** `move_task(task_id: int, to_status: str, ctx: dict) -> dict`; moving to `Blocat` requires `ctx['block'] = {"responsible","next_action"}`, else raises `MoveError('block_requires_responsible_and_next_action')`. Every successful move calls `record_history`. `POST /api/logistics/tasks/<id>/move`.

- [ ] **Step 1: Write the failing test** — `test_block_without_next_action_rejected`; `test_block_with_responsible_and_next_action_succeeds_and_logs_history`.
- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.
- [ ] **Step 3: Implement** `move_task` + `MoveError` + the move route; wire board drag/`Mută` to it.
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): Blocat gate + history`.

---

### Task 9: Move — Recepție → Finalizat (Confirmă recepția)

**Files:** Modify `jarvis/logistics/services/moves.py` · Create `jarvis/frontend/src/pages/Logistics/components/ConfirmReceptionDialog.tsx` · Test: `jarvis/tests/logistics/test_move_reception.py`

**Interfaces:** Moving a `Recepție` task to `Finalizat` requires `ctx['reception'] = {"vin","location_id","position_id","keys","condition"}`. On success: set those on the vehicle, mark each `true` in `confirmed_fields`, move `etapa_parc` out of `În tranzit`, write history; any missing field → `MoveError('reception_incomplete')`.

- [ ] **Step 1: Write the failing test** — `test_confirm_reception_sets_and_confirms_vehicle_fields`; `test_older_intake_event_after_confirm_preserves_bay` (end-to-end with Task 4 guard).
- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.
- [ ] **Step 3: Implement** the reception branch in `move_task`; then `ConfirmReceptionDialog.tsx`.
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): confirm reception on finalize`.

---

### Task 10: Move — measured result for Îngrijire

**Files:** Modify `jarvis/logistics/services/moves.py` · Test: `jarvis/tests/logistics/test_move_measured.py`

**Interfaces:** Finalizing a `type='Îngrijire'` task requires `ctx['measured'] = {"value": number, "unit": str}`, stored on `logistics_tasks.measured_result` + history; missing → `MoveError('measured_result_required')`.

- [ ] **Step 1: Write the failing test** — `test_finalize_battery_without_measurement_rejected`; `test_finalize_battery_with_12v_reading_stores_measurement`.
- [ ] **Step 2: Run to verify it fails** — Expected: FAIL.
- [ ] **Step 3: Implement** the measured-result branch.
- [ ] **Step 4: Run to verify it passes** — Expected: PASS.
- [ ] **Step 5: Commit** — `feat(logistics): measured-result gate for care tasks`.

---

### Task 11: Acceptance test (end-to-end)

**Files:** Create `jarvis/tests/logistics/test_acceptance.py`

- [ ] **Step 1: Write the test** — one order: POST `Transport in derulare` **twice** → one vehicle + one card; POST `ETA actualizat` → same card new `due_at`; `move_task` to Finalizat via reception ctx → confirmed bay visible via `list_vehicles`; POST an **older** `Transport in derulare` → bay preserved; assert `predare` untouched throughout.
- [ ] **Step 2: Run** — `Run: venv/bin/python -m pytest jarvis/tests/logistics/test_acceptance.py -v` · Expected: PASS (fix any gap it reveals in Tasks 2–10).
- [ ] **Step 3: Commit** — `test(logistics): end-to-end acceptance`.
