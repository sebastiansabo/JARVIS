# Pontaje Export Filter Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline Pontaje export date pickers with an Export button that opens a modal to pick Year+Month and filter by All / Group / Employees, always intersected with the caller's permission scope.

**Architecture:** Backend adds two optional query params (`group`, `employee_ids`) to the existing `GET /biostar/api/attendance/export`, resolves them into a final `jarvis_user_ids` list via a pure, unit-tested helper intersected with `_resolve_manager_filter()`, and passes it to the unchanged `generate()`. Frontend adds a `PontajeExportModal` that reuses `getGroups()`/`getEmployees()` and the extended `exportPontaje` client.

**Tech Stack:** Python (Flask, psycopg2, openpyxl), pytest; React 19 + TypeScript + Vite + Tailwind.

## Global Constraints

- Routes must not contain SQL — group→id lookup lives in `BioStarRepository` (repository layer). (Copied from existing architecture rule enforced by validation hooks.)
- Permission scope from `_resolve_manager_filter()` is authoritative: `None` = see all, `list[int]` = allowed ids, `[-1]` = deny. A requested filter must never widen visibility.
- Date params stay `YYYY-MM-DD`; existing validation (ISO parse, `start <= end`, max 366 days) is unchanged.
- Frontend blob download uses `credentials: 'same-origin'` (cookie auth), no bearer token.
- Work happens on the `dev` branch. Commit after each task.

---

### Task 1: Pure export-scope resolver + tests

**Files:**
- Modify: `jarvis/core/connectors/biostar/services/pontaje_export_service.py`
- Test: `jarvis/tests/biostar/test_pontaje_export.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `resolve_export_ids(allowed, group_ids=None, employee_ids=None) -> list[int] | None`
  - `allowed`: `None | list[int]` (may be `[-1]`).
  - `group_ids`, `employee_ids`: `list[int] | None`.
  - Returns the id list to pass to `generate()`, or `None` when no filter is requested and `allowed is None` (means "all"). `employee_ids` takes precedence over `group_ids`.

- [ ] **Step 1: Write the failing tests**

Add to `jarvis/tests/biostar/test_pontaje_export.py`:

```python
def test_resolve_export_ids_no_filter_passthrough():
    assert pes.resolve_export_ids(None) is None
    assert pes.resolve_export_ids([1, 2]) == [1, 2]

def test_resolve_export_ids_see_all_honours_request():
    assert pes.resolve_export_ids(None, employee_ids=[2, 9]) == [2, 9]

def test_resolve_export_ids_intersects_with_scope():
    assert pes.resolve_export_ids([1, 2, 3], employee_ids=[2, 9]) == [2]

def test_resolve_export_ids_deny_strips_everything():
    assert pes.resolve_export_ids([-1], employee_ids=[2, 3]) == []

def test_resolve_export_ids_group_path():
    assert pes.resolve_export_ids([1, 2, 3], group_ids=[2, 3, 7]) == [2, 3]

def test_resolve_export_ids_employee_beats_group():
    # both supplied -> employee_ids wins
    assert pes.resolve_export_ids([1, 2, 3], group_ids=[3], employee_ids=[2]) == [2]

def test_resolve_export_ids_dedupes_and_casts():
    assert pes.resolve_export_ids(None, employee_ids=['2', 2, '5']) == [2, 5]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS && python -m pytest jarvis/tests/biostar/test_pontaje_export.py -q -k resolve_export_ids`
Expected: FAIL with `AttributeError: module ... has no attribute 'resolve_export_ids'`

- [ ] **Step 3: Implement the helper**

Add to `jarvis/core/connectors/biostar/services/pontaje_export_service.py` (near `generate`):

```python
def resolve_export_ids(allowed, group_ids=None, employee_ids=None):
    """Intersect a requested group/employee filter with the caller's permission scope.

    allowed:      None (see all) | list[int] of permitted jarvis_user_ids | [-1] (deny).
    group_ids:    list[int] | None — jarvis ids belonging to a chosen group.
    employee_ids: list[int] | None — explicitly chosen jarvis ids (takes precedence).

    Returns the id list to hand to generate(), or None when no filter is requested and
    the scope is see-all. An empty list means "filter requested but nothing in scope".
    """
    requested = None
    if employee_ids:
        requested = list(dict.fromkeys(int(x) for x in employee_ids))
    elif group_ids:
        requested = list(dict.fromkeys(int(x) for x in group_ids))

    if requested is None:
        return allowed  # unchanged behaviour: None=all, [ids], [-1]=deny

    if allowed is None:
        return requested  # see-all: honour the request as-is
    allowed_set = set(allowed)
    return [uid for uid in requested if uid in allowed_set]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest jarvis/tests/biostar/test_pontaje_export.py -q -k resolve_export_ids`
Expected: PASS (7 passed)

- [ ] **Step 5: Run the full export test file (no regressions)**

Run: `python -m pytest jarvis/tests/biostar/test_pontaje_export.py -q`
Expected: PASS (all existing + 7 new)

- [ ] **Step 6: Commit**

```bash
git add jarvis/core/connectors/biostar/services/pontaje_export_service.py jarvis/tests/biostar/test_pontaje_export.py
git commit -m "feat(hr): resolve_export_ids — intersect export filter with permission scope"
```

---

### Task 2: Group→jarvis-ids repository method

**Files:**
- Modify: `jarvis/core/connectors/biostar/repositories/biostar_repository.py`

**Interfaces:**
- Consumes: `BaseRepository.query_all` (already inherited; returns list of dict rows).
- Produces: `BioStarRepository.get_jarvis_ids_for_group(group_name: str) -> list[int]`

- [ ] **Step 1: Add the method**

Add to `class BioStarRepository` in `jarvis/core/connectors/biostar/repositories/biostar_repository.py` (place beside the other pontaje query methods such as `get_pontaje_rows`):

```python
def get_jarvis_ids_for_group(self, group_name):
    """Return distinct mapped JARVIS user ids belonging to a BioStar user group."""
    rows = self.query_all(
        '''SELECT DISTINCT mapped_jarvis_user_id AS uid
           FROM biostar_employees
           WHERE user_group_name = %s
             AND mapped_jarvis_user_id IS NOT NULL''',
        (group_name,),
    )
    return [r['uid'] for r in rows]
```

- [ ] **Step 2: Verify against the local DB**

Run (pick a real group name that exists locally):

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis && DATABASE_URL="postgresql://localhost/defaultdb" FLASK_SECRET_KEY="dev-key" python3 -c "
from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
repo = BioStarRepository()
name = None
for r in repo.query_all(\"SELECT user_group_name, COUNT(*) c FROM biostar_employees WHERE user_group_name IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 1\"):
    name = r['user_group_name']
ids = repo.get_jarvis_ids_for_group(name)
print('group:', name, '-> ids:', len(ids), ids[:8])
" 2>&1 | grep -vE "INFO|WARNING|pool|Migrat|schema|hooks|scheduler|startup|Serving|Debug|Running|CTRL"
```

Expected: prints a real group name and a non-empty list of integer ids.

- [ ] **Step 3: Commit**

```bash
git add jarvis/core/connectors/biostar/repositories/biostar_repository.py
git commit -m "feat(hr): get_jarvis_ids_for_group — biostar group to jarvis user ids"
```

---

### Task 3: Wire route params + resolution + empty-filter guard

**Files:**
- Modify: `jarvis/core/connectors/biostar/routes.py` (function `export_pontaje`, currently ~line 438)

**Interfaces:**
- Consumes: `pontaje_export_service.resolve_export_ids` (Task 1), `BioStarRepository.get_jarvis_ids_for_group` (Task 2), existing `_resolve_manager_filter()`.
- Produces: HTTP behaviour — `group` / `employee_ids` query params honoured; 400 when a filter resolves to no in-scope employees.

- [ ] **Step 1: Replace the filter/generate block in `export_pontaje`**

In `jarvis/core/connectors/biostar/routes.py`, replace these two lines:

```python
    jarvis_user_ids = _resolve_manager_filter()
    xlsx, filename = pontaje_export_service.generate(start, end, jarvis_user_ids)
```

with:

```python
    from core.connectors.biostar.repositories.biostar_repository import BioStarRepository

    emp_raw = request.args.get('employee_ids')
    employee_ids = [int(x) for x in emp_raw.split(',') if x.strip().isdigit()] if emp_raw else None
    group = request.args.get('group')
    group_ids = None
    if not employee_ids and group:
        group_ids = BioStarRepository().get_jarvis_ids_for_group(group)

    allowed = _resolve_manager_filter()
    jarvis_user_ids = pontaje_export_service.resolve_export_ids(allowed, group_ids, employee_ids)
    if jarvis_user_ids is not None and len(jarvis_user_ids) == 0:
        return jsonify({'success': False, 'error': 'no employees match the selected filter'}), 400

    xlsx, filename = pontaje_export_service.generate(start, end, jarvis_user_ids)
```

- [ ] **Step 2: Restart the local server**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS
PID=$(lsof -tiTCP:5001 -sTCP:LISTEN 2>/dev/null); [ -n "$PID" ] && kill $PID; sleep 1
PORT=5001 DATABASE_URL="postgresql://localhost/defaultdb" FLASK_SECRET_KEY="dev-key" nohup python3 jarvis/app.py > /tmp/jarvis_server.log 2>&1 &
sleep 8
```

- [ ] **Step 3: Verify unauthenticated route still gates (params accepted, no 500)**

Run:
```bash
curl -s -o /dev/null -w "with group -> %{http_code}\n" "http://localhost:5001/biostar/api/attendance/export?start=2026-06-01&end=2026-06-30&group=AW%20ONE"
curl -s -o /dev/null -w "with employee_ids -> %{http_code}\n" "http://localhost:5001/biostar/api/attendance/export?start=2026-06-01&end=2026-06-30&employee_ids=1,2,3"
```
Expected: both `-> 401` (auth gate fires before work; no 400/500 from param parsing).

- [ ] **Step 4: Verify resolution end-to-end (authenticated service call)**

Run:
```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis && DATABASE_URL="postgresql://localhost/defaultdb" FLASK_SECRET_KEY="dev-key" python3 -c "
from core.connectors.biostar.services import pontaje_export_service as pes
from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
repo = BioStarRepository()
name = repo.query_all(\"SELECT user_group_name FROM biostar_employees WHERE user_group_name IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1\")[0]['user_group_name']
gids = repo.get_jarvis_ids_for_group(name)
final = pes.resolve_export_ids(None, gids, None)   # see-all caller
xlsx, fn = pes.generate('2026-06-01','2026-06-30', final)
print('group', name, 'ids', len(gids), 'file', fn, 'bytes', len(xlsx))
" 2>&1 | grep -vE "INFO|WARNING|pool|Migrat|schema|hooks|scheduler|startup|Serving|Debug|Running|CTRL"
```
Expected: a non-zero byte count for a workbook scoped to that group.

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/connectors/biostar/routes.py
git commit -m "feat(hr): export route honours group/employee_ids filters (scope-intersected)"
```

---

### Task 4: Extend the `exportPontaje` API client

**Files:**
- Modify: `jarvis/frontend/src/api/biostar.ts` (function `exportPontaje`, ~line 195)

**Interfaces:**
- Consumes: nothing new.
- Produces: `exportPontaje(start: string, end: string, filters?: { group?: string; employeeIds?: number[] }) => Promise<boolean>`

- [ ] **Step 1: Replace the function**

Replace the current `exportPontaje` in `jarvis/frontend/src/api/biostar.ts` with:

```typescript
  exportPontaje: async (
    start: string,
    end: string,
    filters?: { group?: string; employeeIds?: number[] },
  ): Promise<boolean> => {
    const params = new URLSearchParams({ start, end })
    if (filters?.employeeIds?.length) params.set('employee_ids', filters.employeeIds.join(','))
    else if (filters?.group) params.set('group', filters.group)
    const res = await fetch(`${BASE}/attendance/export?${params.toString()}`, {
      credentials: 'same-origin',
    })
    if (!res.ok) return false
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download =
      res.headers.get('content-disposition')?.match(/filename="?(.+?)"?$/)?.[1] ||
      `pontaje_${start}_${end}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return true
  },
```

- [ ] **Step 2: Type-check**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis/frontend && npx tsc --noEmit`
Expected: no new errors referencing `biostar.ts` (existing callers pass 2 args — still valid since `filters` is optional).

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/api/biostar.ts
git commit -m "feat(hr): exportPontaje client accepts optional group/employee filters"
```

---

### Task 5: `PontajeExportModal` component

**Files:**
- Create: `jarvis/frontend/src/pages/Hr/PontajeExportModal.tsx`

**Interfaces:**
- Consumes: `biostarApi.getGroups()` → `{ groups: { group_name: string }[] }`; `biostarApi.getEmployees(true)` → `BioStarEmployee[]` (fields used: `mapped_jarvis_user_id: number|null`, `name: string`, `user_group_name: string|null`); `biostarApi.exportPontaje(start, end, filters)`.
- Produces: `export default function PontajeExportModal({ open, onClose }: { open: boolean; onClose: () => void })`

- [ ] **Step 1: Create the component**

Create `jarvis/frontend/src/pages/Hr/PontajeExportModal.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { biostarApi } from '../../api/biostar'

type Mode = 'all' | 'group' | 'employee'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

const pad = (n: number) => String(n).padStart(2, '0')

export default function PontajeExportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1) // 1-12
  const [mode, setMode] = useState<Mode>('all')
  const [group, setGroup] = useState('')
  const [empIds, setEmpIds] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const [groups, setGroups] = useState<string[]>([])
  const [employees, setEmployees] = useState<{ id: number; name: string; group: string }[]>([])
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    if (!open) return
    biostarApi.getGroups()
      .then(r => setGroups((r.groups ?? []).map(g => g.group_name).sort()))
      .catch(() => setGroups([]))
    biostarApi.getEmployees(true)
      .then(list => setEmployees(
        list
          .filter(e => e.mapped_jarvis_user_id != null)
          .map(e => ({ id: e.mapped_jarvis_user_id as number, name: e.name, group: e.user_group_name ?? '' }))
          .sort((a, b) => a.name.localeCompare(b.name)),
      ))
      .catch(() => setEmployees([]))
  }, [open])

  const filteredEmployees = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q ? employees.filter(e => e.name.toLowerCase().includes(q)) : employees
  }, [employees, search])

  const yearOptions = [now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2]

  const toggleEmp = (id: number) => setEmpIds(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const canExport = mode === 'all'
    || (mode === 'group' && group)
    || (mode === 'employee' && empIds.size > 0)

  const handleExport = async () => {
    const start = `${year}-${pad(month)}-01`
    const lastDay = new Date(year, month, 0).getDate()
    const end = `${year}-${pad(month)}-${pad(lastDay)}`
    const filters = mode === 'group' ? { group }
      : mode === 'employee' ? { employeeIds: [...empIds] }
      : undefined
    setExporting(true)
    const toastId = toast.loading('Exporting pontaje…')
    try {
      const ok = await biostarApi.exportPontaje(start, end, filters)
      if (ok) { toast.success('Export complete', { id: toastId }); onClose() }
      else toast.error('Export failed', { id: toastId })
    } finally {
      setExporting(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-[520px] max-w-[92vw] max-h-[88vh] overflow-y-auto rounded-lg bg-white p-6 shadow-xl dark:bg-neutral-900"
        onClick={e => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Export Pontaje</h2>

        <div className="mb-4 flex gap-3">
          <label className="flex-1 text-sm">
            Year
            <select className="mt-1 w-full rounded border px-2 py-1 dark:bg-neutral-800"
              value={year} onChange={e => setYear(Number(e.target.value))}>
              {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label className="flex-1 text-sm">
            Month
            <select className="mt-1 w-full rounded border px-2 py-1 dark:bg-neutral-800"
              value={month} onChange={e => setMonth(Number(e.target.value))}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </label>
        </div>

        <div className="mb-3 flex gap-4 text-sm">
          {(['all', 'group', 'employee'] as Mode[]).map(m => (
            <label key={m} className="flex items-center gap-1">
              <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />
              {m === 'all' ? 'All (my scope)' : m === 'group' ? 'By group' : 'By employee'}
            </label>
          ))}
        </div>

        {mode === 'group' && (
          <select className="mb-4 w-full rounded border px-2 py-1 dark:bg-neutral-800"
            value={group} onChange={e => setGroup(e.target.value)}>
            <option value="">Select a group…</option>
            {groups.map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        )}

        {mode === 'employee' && (
          <div className="mb-4">
            <input
              className="mb-2 w-full rounded border px-2 py-1 dark:bg-neutral-800"
              placeholder="Search employees…"
              value={search} onChange={e => setSearch(e.target.value)}
            />
            <div className="max-h-52 overflow-y-auto rounded border p-2 text-sm dark:border-neutral-700">
              {filteredEmployees.map(e => (
                <label key={e.id} className="flex items-center gap-2 py-0.5">
                  <input type="checkbox" checked={empIds.has(e.id)} onChange={() => toggleEmp(e.id)} />
                  <span>{e.name}</span>
                  {e.group && <span className="text-xs text-neutral-500">· {e.group}</span>}
                </label>
              ))}
              {filteredEmployees.length === 0 && <div className="text-neutral-500">No employees</div>}
            </div>
            <div className="mt-1 text-xs text-neutral-500">{empIds.size} selected</div>
          </div>
        )}

        <div className="mt-2 flex justify-end gap-2">
          <button className="rounded px-4 py-1.5 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
            onClick={onClose} disabled={exporting}>Cancel</button>
          <button
            className="rounded bg-[#0F6D63] px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            onClick={handleExport} disabled={!canExport || exporting}>
            {exporting ? 'Exporting…' : 'Export'}
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis/frontend && npx tsc --noEmit`
Expected: no errors in `PontajeExportModal.tsx`.

- [ ] **Step 3: Commit**

```bash
git add jarvis/frontend/src/pages/Hr/PontajeExportModal.tsx
git commit -m "feat(hr): PontajeExportModal — year/month + group/employee filters"
```

---

### Task 6: Open the modal from PontajeTab's Export button

**Files:**
- Modify: `jarvis/frontend/src/pages/Hr/PontajeTab.tsx`

**Interfaces:**
- Consumes: `PontajeExportModal` (Task 5).
- Produces: an Export button that opens the modal; the old inline `exportStart`/`exportEnd`/`handleExportPontaje` monthly-export wiring is removed.

- [ ] **Step 1: Import the modal**

At the top of `jarvis/frontend/src/pages/Hr/PontajeTab.tsx`, add with the other imports:

```tsx
import PontajeExportModal from './PontajeExportModal'
```

- [ ] **Step 2: Replace inline export state with modal state**

Replace:

```tsx
  const [exporting, setExporting] = useState(false)

  const [exportStart, setExportStart] = useState(date.slice(0, 8) + '01')
  const [exportEnd, setExportEnd] = useState(date)

  const handleExportPontaje = useCallback(async () => {
    setExporting(true)
    const toastId = toast.loading('Exporting pontaje…')
    try {
      const ok = await biostarApi.exportPontaje(exportStart, exportEnd)
      if (ok) toast.success('Export complete', { id: toastId })
      else toast.error('Export failed', { id: toastId })
    } finally {
      setExporting(false)
    }
  }, [exportStart, exportEnd])
```

with:

```tsx
  const [exportOpen, setExportOpen] = useState(false)
```

- [ ] **Step 3: Render the button + modal**

Locate the JSX that renders the inline export controls (the block using `exportStart`, `exportEnd`, `handleExportPontaje`, and the `exporting` spinner for the monthly period export) and replace that block with:

```tsx
        <button
          className="rounded bg-[#0F6D63] px-3 py-1.5 text-sm font-medium text-white"
          onClick={() => setExportOpen(true)}
        >
          Export
        </button>
        <PontajeExportModal open={exportOpen} onClose={() => setExportOpen(false)} />
```

Note: if other export buttons in this file reuse the shared `exporting` state for the per-day/monthly quick actions, leave those untouched — only remove the period-range export that the modal replaces. If `exportStart`/`exportEnd`/`handleExportPontaje` are now unused elsewhere, remove their remaining references so `tsc` is clean.

- [ ] **Step 4: Type-check**

Run: `cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis/frontend && npx tsc --noEmit`
Expected: no errors; no "declared but never used" for `exportStart`/`exportEnd`/`handleExportPontaje`.

- [ ] **Step 5: Build the frontend and restart server**

```bash
cd /Users/sebastiansabo/Documents/Git/JARVIS/jarvis/frontend && npm run build
cd /Users/sebastiansabo/Documents/Git/JARVIS
PID=$(lsof -tiTCP:5001 -sTCP:LISTEN 2>/dev/null); [ -n "$PID" ] && kill $PID; sleep 1
PORT=5001 DATABASE_URL="postgresql://localhost/defaultdb" FLASK_SECRET_KEY="dev-key" nohup python3 jarvis/app.py > /tmp/jarvis_server.log 2>&1 &
sleep 8
```

- [ ] **Step 6: Manual verification**

Open `http://localhost:5001`, log in, go to `/app/settings/pontaje`. Click **Export**:
- Modal opens; Year defaults to current year, Month to current month.
- Selecting **By group** shows the group dropdown; **By employee** shows a searchable checklist; **All** shows neither.
- Export with each mode downloads `pontaje_<start>_<end>.xlsx`; the group/employee export contains only matching rows.

- [ ] **Step 7: Commit**

```bash
git add jarvis/frontend/src/pages/Hr/PontajeTab.tsx
git commit -m "feat(hr): Export button opens PontajeExportModal; drop inline period pickers"
```

---

## Notes for the implementer

- The frontend is rebuilt fresh in Docker (`npm run build`), so committing `jarvis/static/react/**` build artifacts is unnecessary — do not stage them.
- Keep everything on `dev`. Deployment (dev→staging→main) is a separate, user-driven step and is out of scope for this plan.
- `_resolve_manager_filter()` may return `None` (see-all). `resolve_export_ids` preserves that as "all" only when no filter is requested; with a filter, a see-all caller gets exactly the requested ids.
