# Field Sales Calendar Scheduling (Outlook-style) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let a KAM schedule visits directly on the Hub Field Sales calendar — click a day (month view) to add, and in Day/Week time-grid views drag to create/move/resize meetings that have a start and end time.

**Architecture:** Add one nullable `planned_end_time` column to `kam_visit_plans` (idempotent startup ALTER). Backend reuses existing POST/PUT visit routes. Frontend adds a view switcher + a pointer-event-driven time-grid to `FieldSalesCalendar`, and an end-time field to `AddVisitForm`. Move/resize persist via the existing `fieldSalesApi.updateVisit` with optimistic cache updates.

**Tech Stack:** Python/Flask + psycopg2; React 18 + TypeScript + TanStack React Query + Tailwind; Vitest + @testing-library/react (pointer events).

## Global Constraints
- Work on `dev`. Frontend + ONE additive backend column only. No new endpoints.
- Column: `kam_visit_plans.planned_end_time TIME` NULL, added via `ADD COLUMN IF NOT EXISTS`.
- Grid: hours **07:00–21:00**, **30-min snap**, default new-meeting duration **1h**, week starts **Monday**.
- Time strings are `HH:MM` (24h). Dates `YYYY-MM-DD`.
- Romanian UI copy; iOS sizing (`h-11 rounded-xl`); reuse `STATUS_CONFIG`/`VISIT_TYPE_LABELS` from `HubFieldSalesPanel.tsx`.
- Errors surface via `err?.data?.error`. Test output PRISTINE (no `act()` warnings) — use RTL `waitFor` for async settle.
- Run from `jarvis/frontend`: `npx vitest run <path>`, `npx tsc --noEmit`. Backend parse: `cd jarvis && venv/bin/python -c "import ast; ast.parse(open('field_sales/routes/visits.py').read())"`. Do NOT run `npm run build` in task commits (it regenerates `static/react`/`tsconfig.tsbuildinfo` — never commit those; commit source with explicit paths).
- Commit hook prints a repo-wide Python validation report — its pre-existing failures are unrelated; ignore.

---

## File Structure
- `jarvis/migrations/domains/schema_field_sales.py` — add column.
- `jarvis/field_sales/repositories/visit_repository.py` — `create()` + `update_visit()`.
- `jarvis/field_sales/routes/visits.py` — POST/PUT accept+validate `planned_end_time`.
- `jarvis/frontend/src/api/fieldSales.ts` — types.
- `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx` — AddVisitForm end field + `add` overlay + `onAdd`.
- `jarvis/frontend/src/pages/Hub/FieldSalesCalendar.tsx` — view switcher, time-grid, drag.
- test files alongside each.

---

## Task 1: Backend — `planned_end_time` column + create/update + routes

**Files:** Modify `schema_field_sales.py`, `visit_repository.py`, `routes/visits.py`. Apply column to localhost DB.

**Interfaces produced:** `kam_visit_plans.planned_end_time TIME`; `create()`/`update_visit()` persist it; `POST /visits` + `PUT /visits/:id` accept `planned_end_time` (`HH:MM` or `HH:MM:SS`, optional).

- [ ] **Step 1 — column.** In `schema_field_sales.py`, in `create_schema_field_sales`, after the `kam_visit_plans` block's other `ALTER TABLE kam_visit_plans ADD COLUMN IF NOT EXISTS ...` lines, add:
```python
cursor.execute("ALTER TABLE kam_visit_plans ADD COLUMN IF NOT EXISTS planned_end_time TIME")
```
- [ ] **Step 2 — apply to localhost** (so the running app + tests see it):
```bash
psql "postgresql://localhost/defaultdb" -c "ALTER TABLE kam_visit_plans ADD COLUMN IF NOT EXISTS planned_end_time TIME"
```
Expected: `ALTER TABLE`.
- [ ] **Step 3 — repo create.** In `visit_repository.py` `create()`, add `planned_end_time` to the INSERT column list, values placeholders, and params (from `data.get('planned_end_time')`):
```python
INSERT INTO kam_visit_plans
    (kam_id, client_id, planned_date, planned_time, planned_end_time, visit_type, goals)
VALUES (%s, %s, %s, %s, %s, %s, %s)
RETURNING *
```
params add `data.get('planned_end_time')` in the matching position (after `planned_time`).
- [ ] **Step 4 — repo update.** In `update_visit()`, add `'planned_end_time'` to the plain-field tuple that currently reads `('planned_date', 'planned_time', 'visit_type', 'goals', 'status', 'outcome', 'contact_person')`.
- [ ] **Step 5 — routes.** In `routes/visits.py`:
  - `api_create_visit`: add `'planned_end_time': data.get('planned_end_time'),` to the `visit_data` dict (after `planned_time`).
  - `api_update_visit`: it already copies request fields into an `update` dict for `planned_date`/`planned_time`/etc. Add `planned_end_time` to that handling (same pattern as `planned_time`: `if 'planned_end_time' in data: update['planned_end_time'] = data['planned_end_time']`). Accept `null` to clear.
  - (Optional light validation: if present and non-null, ensure it matches `HH:MM`; mirror how `planned_time` is treated — if `planned_time` is passed through unvalidated, do the same for symmetry.)
- [ ] **Step 6 — verify parse + restart localhost backend** so the running app has the new insert/route:
```bash
cd jarvis && venv/bin/python -c "import ast; ast.parse(open('field_sales/routes/visits.py').read()); ast.parse(open('field_sales/repositories/visit_repository.py').read())" && echo PARSE_OK
```
(The controller will restart the :5001 backend after this task.)
- [ ] **Step 7 — commit** source only:
```bash
git add jarvis/migrations/domains/schema_field_sales.py jarvis/field_sales/repositories/visit_repository.py jarvis/field_sales/routes/visits.py
git commit -m "feat(field-sales): planned_end_time column + create/update wiring"
```

---

## Task 2: Web API types — `planned_end_time`

**Files:** Modify `api/fieldSales.ts`; extend `api/fieldSales.fs.test.ts`.

**Interfaces produced:** `FSVisit.planned_end_time?: string`; `CreateVisitPayload.planned_end_time?: string`; `VisitUpdatePayload` includes `'planned_end_time'`.

- [ ] **Step 1 — failing test.** Add to `fieldSales.fs.test.ts`:
```ts
it('createVisit forwards planned_end_time', async () => {
  await fieldSalesApi.createVisit({ client_id: 1, planned_date: '2026-08-05', planned_time: '09:00', planned_end_time: '10:00' })
  expect(post).toHaveBeenCalledWith('/api/field-sales/visits', { client_id: 1, planned_date: '2026-08-05', planned_time: '09:00', planned_end_time: '10:00' })
})
it('updateVisit forwards planned_end_time', async () => {
  await fieldSalesApi.updateVisit(9, { planned_time: '09:00', planned_end_time: '11:00' })
  expect(put).toHaveBeenCalledWith('/api/field-sales/visits/9', { planned_time: '09:00', planned_end_time: '11:00' })
})
```
(Ensure the test's `./client` mock exposes `put` like it does `get`/`post`.)
- [ ] **Step 2 — run RED:** `cd jarvis/frontend && npx vitest run src/api/fieldSales.fs.test.ts` → FAIL (type error / missing field).
- [ ] **Step 3 — implement.** In `fieldSales.ts`: add `planned_end_time?: string` to `interface FSVisit` (near `planned_time`) and to `interface CreateVisitPayload`; add `'planned_end_time'` to the `VisitUpdatePayload` `Pick<FSVisit, ...>` union.
- [ ] **Step 4 — GREEN + tsc:** `npx vitest run src/api/fieldSales.fs.test.ts` PASS; `npx tsc --noEmit` clean.
- [ ] **Step 5 — commit:** `git add jarvis/frontend/src/api/fieldSales.ts jarvis/frontend/src/api/fieldSales.fs.test.ts && git commit -m "feat(field-sales): planned_end_time on FSVisit + create/update payloads"`

---

## Task 3: AddVisitForm end-time field + prefill props

**Files:** Modify `HubFieldSalesPanel.tsx`; extend `HubFieldSalesPanel.test.tsx`.

**Interfaces produced:** `AddVisitForm` accepts `initialDate?`, `initialTime?`, `initialEndTime?`; submits `planned_end_time`. Panel `Overlay` `add` kind → `{ kind: 'add'; date?: string; time?: string; endTime?: string }`; `add` overlay passes these as initial props.

- [ ] **Step 1 — failing test.** In `HubFieldSalesPanel.test.tsx`, extend the add-visit test (or add one): open add overlay, select a client, and assert `createVisit` is called with a `planned_end_time`. If prefill is exercised, render the panel with an `add` overlay pre-opened via a slot/day click in a later task — for THIS task assert: when the end field is left default after choosing a start `09:00`, submit sends `planned_end_time: '10:00'` (start+1h default). Use RTL `waitFor`.
```ts
// after selecting client + setting start time to 09:00:
fireEvent.change(screen.getByLabelText(/Or[aă]/i), { target: { value: '09:00' } })
fireEvent.click(screen.getByRole('button', { name: /salveaz[aă] vizit[aă]/i }))
await waitFor(() => expect(mod.fieldSalesApi.createVisit).toHaveBeenCalledWith(expect.objectContaining({ planned_time: '09:00', planned_end_time: '10:00' })))
```
- [ ] **Step 2 — run RED.**
- [ ] **Step 3 — implement.** In `AddVisitForm`: add state `endTime` (init from `initialEndTime`); add a **Sfârșit** `<input type="time">` (iOS classes) next to the existing time field. Default logic: when the start time changes and end is empty or ≤ start, set end = start + 1h (`addHour(start)` helper). Include `planned_end_time: endTime || undefined` in the `createVisit` payload. Add props `initialDate`/`initialTime`/`initialEndTime` and initialize `date`/`time`/`endTime` from them (fallback: date→today, time→'', end→''). Extend the panel `Overlay` union `add` kind and pass the initials in the `add` overlay render.
- [ ] **Step 4 — GREEN + tsc.**
- [ ] **Step 5 — commit:** `git add jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx && git commit -m "feat(field-sales): end-time field + prefill in AddVisitForm"`

---

## Task 4: Calendar view switcher + month click-to-add

**Files:** Modify `FieldSalesCalendar.tsx`; extend `FieldSalesCalendar.test.tsx`. Wire `onAdd` in `HubFieldSalesPanel.tsx`.

**Interfaces produced:** `FieldSalesCalendar` prop `onAdd(date: string, time?: string, endTime?: string)`; view state `'month'|'week'|'day'` via `usePersistedState('hub-fs-cal-view','month')`.

- [ ] **Step 1 — failing test.** In `FieldSalesCalendar.test.tsx`: render with `onAdd` spy in month view; click a day cell's add affordance (button `+ Adaug[aă]` in the selected-day section, or a cell `+`); assert `onAdd` called with that day's `YYYY-MM-DD`. Also assert the view switcher renders three tabs (Lună/Săptămână/Zi).
- [ ] **Step 2 — run RED.**
- [ ] **Step 3 — implement.** Add the view switcher (Radix Tabs or simple buttons, matching DrivingCalendar's `[['month','Lună'],['week','Săptămână'],['day','Zi']]` style) persisted via `usePersistedState`. In month view keep the existing grid + selected-day list; add a `+ Adaugă vizită` button in the selected-day section header → `onAdd(selectedDayKey)`, and a hover `+` on each day cell → `onAdd(cellKey)` (stopPropagation so it doesn't also select). Week/Day render a placeholder for now ("time-grid" comes in Task 5) — or gate so only month is interactive; keep it compiling. Wire panel: `<FieldSalesCalendar onOpen={id => setOverlay({kind:'detail',id})} onAdd={(date,time,endTime) => setOverlay({kind:'add',date,time,endTime})} />`.
- [ ] **Step 4 — GREEN + tsc.**
- [ ] **Step 5 — commit:** `git add jarvis/frontend/src/pages/Hub/FieldSalesCalendar.tsx jarvis/frontend/src/pages/Hub/FieldSalesCalendar.test.tsx jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx && git commit -m "feat(field-sales): calendar view switcher + month click-to-add"`

---

## Task 5: Week/Day time-grid rendering (no drag yet)

**Files:** Modify `FieldSalesCalendar.tsx`; extend its test.

**Interfaces produced:** week/day time-grid; geometry helpers `timeToY`, `yToTime`, block layout. Plain slot click → `onAdd(dayKey, "HH:00", "HH+1:00")`. Block click → `onOpen(visitId)`.

Constants + helpers to add:
```ts
const HOUR_START = 7, HOUR_END = 21, PX_PER_HOUR = 48, SNAP_MIN = 30
const pad2 = (n: number) => String(n).padStart(2, '0')
const toMin = (t?: string | null) => { if (!t) return null; const [h, m] = t.split(':').map(Number); return h * 60 + m }
const minToTime = (min: number) => `${pad2(Math.floor(min / 60))}:${pad2(min % 60)}`
const snap = (min: number) => Math.round(min / SNAP_MIN) * SNAP_MIN
const yToMin = (y: number) => snap(HOUR_START * 60 + (y / PX_PER_HOUR) * 60)
const minToY = (min: number) => ((min - HOUR_START * 60) / 60) * PX_PER_HOUR
const addHour = (t: string) => minToTime(Math.min(toMin(t)! + 60, HOUR_END * 60))
```

- [ ] **Step 1 — failing test.** In `FieldSalesCalendar.test.tsx`: mock `getMyVisits` to return one visit `{planned_date: <a day in the week>, planned_time:'09:00', planned_end_time:'10:30', ...}`; switch to week view (mousedown the Săptămână tab); assert the block renders and its inline height style corresponds to 1.5h (`minToY(630)-minToY(540)` px); assert a block click calls `onOpen`; assert clicking an empty slot at ~11:00 calls `onAdd(day, '11:00', '12:00')`.
- [ ] **Step 2 — run RED.**
- [ ] **Step 3 — implement.** Build the grid: a left hour-gutter (labels 07:00…21:00) and N day columns (`week`=7 from `startOfWeek(anchor)`, `day`=1). Each column: an hour-lined background (height `(HOUR_END-HOUR_START)*PX_PER_HOUR`), an untimed **"Fără oră"** strip at top for visits with no `planned_time`, and absolutely-positioned blocks for timed visits: `top = minToY(toMin(start))`, `height = max(minToY(toMin(end ?? addHour(start))) - top, 18)`, colored via `STATUS_CONFIG[status]`. Block `onClick` (no drag) → `onOpen(v.id)`. Empty-column `onClick` → compute minutes from `e.nativeEvent.offsetY`/rect → `onAdd(dayKey, minToTime(startMin), minToTime(startMin+60))`. Data: `getMyVisits(rangeStart, rangeEnd)` for the visible range, key `['field-sales-cal', view, rangeStartKey]`.
- [ ] **Step 4 — GREEN + tsc.**
- [ ] **Step 5 — commit:** `git add jarvis/frontend/src/pages/Hub/FieldSalesCalendar.tsx jarvis/frontend/src/pages/Hub/FieldSalesCalendar.test.tsx && git commit -m "feat(field-sales): week/day time-grid with slot-click add"`

---

## Task 6: Drag-to-create

**Files:** Modify `FieldSalesCalendar.tsx`; extend its test.

**Interfaces produced:** pointer-drag on empty grid produces a live selection rectangle and, on release, calls `onAdd(dayKey, startHHMM, endHHMM)` snapped to 30 min.

- [ ] **Step 1 — failing test.** Simulate on a day column (mock its `getBoundingClientRect` to a known top/height): `pointerDown` at y for 09:00, `pointerMove` to y for 10:30, `pointerUp`; assert `onAdd(day, '09:00', '10:30')`. A `pointerDown`+`pointerUp` with no move at 08:00 → `onAdd(day, '08:00', '09:00')`.
- [ ] **Step 2 — run RED.**
- [ ] **Step 3 — implement.** Add drag state `useState<{col:string; y0:number; y1:number} | null>`. On column `onPointerDown` (only when target is the column background, not a block): capture pointer (`setPointerCapture`), record `y0` from `offsetY`. `onPointerMove`: update `y1`. Render a translucent selection rect between `minToY(snap)` of y0/y1. `onPointerUp`: compute `a=yToMin(min(y0,y1))`, `b=yToMin(max(y0,y1))`; if `b-a < SNAP_MIN` treat as click → `b=a+60`; call `onAdd(col, minToTime(a), minToTime(b))`; clear drag state. Guard: ignore drags that start on a block (blocks stop propagation).
- [ ] **Step 4 — GREEN + tsc.**
- [ ] **Step 5 — commit:** `git add ... && git commit -m "feat(field-sales): drag-to-create on time-grid"`

---

## Task 7: Drag-move + drag-resize (persist via updateVisit, optimistic)

**Files:** Modify `FieldSalesCalendar.tsx`; extend its test.

**Interfaces produced:** dragging a block body moves it (new day+start, duration kept); dragging its bottom edge resizes (new end); both call `fieldSalesApi.updateVisit` and optimistically update the `['field-sales-cal', ...]` cache.

- [ ] **Step 1 — failing test.** Mock `fieldSalesApi.updateVisit`. Render week view with one 09:00–10:00 block (mock column rects). (a) Move: pointerDown on the block body, move down 1h (to 10:00), pointerUp → `updateVisit(id, { planned_date: sameDay, planned_time: '10:00', planned_end_time: '11:00' })`. (b) Resize: pointerDown on the block's bottom-edge handle, move down 30 min, pointerUp → `updateVisit(id, { planned_end_time: '10:30' })`. Use RTL `waitFor`; assert pristine.
- [ ] **Step 2 — run RED.**
- [ ] **Step 3 — implement.** Extend drag state with `mode: 'create'|'move'|'resize'` and the target visit. Block body `onPointerDown` → mode `move` (record grab offset within block + origin day index). A bottom **resize handle** (a thin div at block bottom, `cursor-ns-resize`, stopPropagation) `onPointerDown` → mode `resize`. `onPointerMove` updates a live preview (offset the block visually). `onPointerUp`:
  - move → new start = `yToMin(top+dy)`, duration preserved, new day = column under pointer x (week) → `updateVisit(id, {planned_date, planned_time, planned_end_time})`.
  - resize → new end = `max(start+SNAP_MIN, yToMin(bottom+dy))` → `updateVisit(id, {planned_end_time})`.
  Add a `useMutation` with `onMutate` writing the moved/resized fields into the cached `getMyVisits` result for the active key (so the block stays put), `onError` rollback + `err?.data?.error` inline message, `onSettled` invalidate `['field-sales-visits']`,`['field-sales-mine']`,`['field-sales-cal']`. Distinguish click vs drag by a movement threshold (e.g. >4px) so a plain click still fires `onOpen`.
- [ ] **Step 4 — GREEN + tsc.**
- [ ] **Step 5 — commit:** `git add ... && git commit -m "feat(field-sales): drag-move + drag-resize with optimistic persist"`

---

## Task 8: Full verification

- [ ] **Step 1 — tsc:** `cd jarvis/frontend && npx tsc --noEmit` → clean.
- [ ] **Step 2 — feature tests:** `npx vitest run src/api/fieldSales.fs.test.ts src/pages/Hub/HubFieldSalesPanel.test.tsx src/pages/Hub/FieldSalesCalendar.test.tsx` → all PASS, pristine.
- [ ] **Step 3 — full suite (no regressions):** `npx vitest run` → all PASS.
- [ ] **Step 4 — build:** `npm run build` → succeeds. Then restore build artifacts: `cd /Users/sebastiansabo/Documents/Git/JARVIS && git checkout -- jarvis/static/react jarvis/frontend/tsconfig.tsbuildinfo` (do not commit them).
- [ ] **Step 5 — manual smoke (localhost):** backend restarted with the column; open week view, drag-create a meeting, move it, resize it, click a day in month view to add. Confirm no console errors.

## Self-Review
- Spec §data-model → Task 1; §backend → Task 1; §API types → Task 2; §AddVisitForm → Task 3; §views + month add → Task 4; §time-grid → Task 5; §drag create → Task 6; §drag move/resize + optimistic → Task 7; §testing → each task + Task 8.
- Types consistent: `planned_end_time` string `HH:MM` across FSVisit/create/update; helpers (`toMin`/`minToTime`/`snap`/`yToMin`/`minToY`/`addHour`) defined in Task 5 and reused in 6–7; `onAdd(date,time?,endTime?)` defined Task 4, consumed 5–6; view keys `['field-sales-cal', view, rangeStartKey]` consistent 5–7.
- No placeholders; every step has concrete code or exact commands.
