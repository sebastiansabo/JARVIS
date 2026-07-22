# Sesiuni Driving Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe the Foi de Parcurs "Parcurs" tab into "Sesiuni Driving" — a historical record of test-drive sessions with a correct 4-state session status, session-relevant columns, and working PDF access.

**Architecture:** Frontend-only change. All logic lives in the `ParcursTab` component (to be renamed `SessionsTab`) inside `jarvis/frontend/src/pages/FoiParcurs/index.tsx`. Session status is derived on the client from the `status` field plus the backend's existing `td_status` (already returned by `get_contracts`). Vehicle brand/model/plate come from the already-fetched vehicles list (the contracts list endpoint does not join `fp_vehicles`), looked up by VIN. No routes, repository, or schema changes.

**Tech Stack:** React + TypeScript, TanStack Query, shadcn/ui (`Badge`, `Table`, `Select`), Vite. Design spec: `docs/superpowers/specs/2026-07-20-sesiuni-driving-tab-design.md`.

## Global Constraints

- **Frontend-only.** No edits to `jarvis/foi_parcurs/**` (routes/repos/services), no schema changes.
- **No test runner** in the frontend (no vitest/jest). Verification gate per task = `npx tsc -b` (typecheck, from `jarvis/frontend`) passing + `npx eslint src/pages/FoiParcurs/index.tsx` clean on touched files, plus the manual check named in the task.
- Internal tab value/key stays `parcurs` (do NOT rename `TabsTrigger value` or the `activeTab === 'parcurs'` check) — only the visible label changes.
- Column **headers stay English**; the tab label and status badges are **Romanian**.
- Backend `td_status` values are exactly `'complete' | 'incomplete' | 'driving'` (from `_TD_STATUS_SQL` in `foi_parcurs_repository.py`).
- Follow the existing file's style: module-level `const` maps (like `STATUS_ROW_BG`), inline Tailwind classes, `foiParcursApi` for data.
- Existing Python suite `jarvis/tests/foi_parcurs/` (21 tests) must remain green (it will — no backend touch).
- JARVIS git workflow: work on `dev`. Commit per task. Do NOT push to staging/main.

---

### Task 1: Extend `FoiContract` type and add the session-status helper

**Files:**
- Modify: `jarvis/frontend/src/types/foiParcurs.ts:146-175`
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx:424-427` (near `STATUS_ROW_BG`)

**Interfaces:**
- Produces: `sessionStatus(c: FoiContract): { key: 'nealocat' | 'driving' | 'intarziat' | 'finalizat'; label: string; badgeClass: string; rowClass: string }` — consumed by Tasks 3, 4, 5.
- Produces: extended `FoiContract` fields `td_status?`, `departure_datetime?`, `return_datetime?`, `returned_at?` — consumed by Tasks 3, 4, 5.

- [ ] **Step 1: Add the missing fields to `FoiContract`**

In `jarvis/frontend/src/types/foiParcurs.ts`, inside `export interface FoiContract { ... }`, add these fields just before the closing `}` (after `updated_at: string`):

```typescript
  // Returned by get_contracts (fp.* + _TD_STATUS_SQL) but previously undeclared:
  td_status?: 'complete' | 'incomplete' | 'driving'
  departure_datetime?: string | null
  return_datetime?: string | null
  returned_at?: string | null
```

- [ ] **Step 2: Add the `sessionStatus` helper next to `STATUS_ROW_BG`**

In `jarvis/frontend/src/pages/FoiParcurs/index.tsx`, replace the existing block at lines 424-427:

```typescript
const STATUS_ROW_BG: Record<string, string> = {
  pending: 'bg-orange-500/5 border-l-4 border-l-orange-500/50',
  filled: 'bg-green-500/5 border-l-4 border-l-green-500/50',
}
```

with:

```typescript
// Derived 4-state session status for the Sesiuni Driving tab. Combines the raw
// `status` column with the backend-derived `td_status` (complete/incomplete/driving).
// PENDING must be checked first: td_status' ELSE branch returns 'driving' even for
// un-allocated PENDING batch slots that were never driven.
type SessionStatusKey = 'nealocat' | 'driving' | 'intarziat' | 'finalizat'

function sessionStatus(c: FoiContract): {
  key: SessionStatusKey
  label: string
  badgeClass: string
  rowClass: string
} {
  if (c.status === 'PENDING') {
    return { key: 'nealocat', label: 'Nealocat', badgeClass: 'bg-muted text-muted-foreground', rowClass: '' }
  }
  if (c.td_status === 'complete' || c.status === 'COMPLETED') {
    return { key: 'finalizat', label: 'Finalizat', badgeClass: 'bg-green-600 text-white', rowClass: 'bg-green-500/5 border-l-4 border-l-green-500/40' }
  }
  if (c.td_status === 'incomplete') {
    return { key: 'intarziat', label: 'Întârziat', badgeClass: 'bg-red-600 text-white', rowClass: 'bg-red-500/10 border-l-4 border-l-red-500/60' }
  }
  return { key: 'driving', label: 'În desfășurare', badgeClass: 'bg-blue-600 text-white', rowClass: 'bg-blue-500/5 border-l-4 border-l-blue-500/40' }
}
```

Confirm `FoiContract` is already imported in `index.tsx` (it is used throughout, e.g. the `allocatingContract` state at line 533). If a type-only import is needed, it is already present.

- [ ] **Step 3: Typecheck**

Run (from `jarvis/frontend`): `npx tsc -b`
Expected: PASS (no errors). `sessionStatus` is defined-but-unused for now — that is fine; it is not exported so TS `noUnusedLocals` may flag it. If `tsc` reports `'sessionStatus' is declared but its value is never read`, proceed to Task 3 immediately in the same commit is NOT allowed (tasks commit independently). Instead, add a temporary `void sessionStatus` is NOT needed — module-level function declarations are not flagged by `noUnusedLocals` (only locals are). Verify no error; if one appears, it means the tsconfig flags module functions — in that case leave the helper and continue; Task 3 consumes it.

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/src/types/foiParcurs.ts jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): session-status type + helper for Sesiuni Driving

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Rename the tab to "Sesiuni Driving", rename the component, hide Comodat

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx:179` (tab label)
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx:185` (component usage)
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx:529` (component definition)
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx:582-594` (row filter — add TD-only)

**Interfaces:**
- Consumes: nothing new.
- Produces: `SessionsTab` component (was `ParcursTab`), consumed at the tab render site.

- [ ] **Step 1: Rename the visible tab label (keep the value)**

At line 179, change:

```tsx
<TabsTrigger value="parcurs">Parcurs</TabsTrigger>
```

to:

```tsx
<TabsTrigger value="parcurs">Sesiuni Driving</TabsTrigger>
```

Leave `value="parcurs"` unchanged.

- [ ] **Step 2: Rename the component at its definition and usage**

At line 529, change `function ParcursTab({ companyId, brand }: { companyId: number; brand: string }) {` to `function SessionsTab({ companyId, brand }: { companyId: number; brand: string }) {`.

At line 185, change `{activeTab === 'parcurs' && <ParcursTab companyId={companyId} brand={brand} />}` to `{activeTab === 'parcurs' && <SessionsTab companyId={companyId} brand={brand} />}`.

Keep the `activeTab === 'parcurs'` check unchanged.

- [ ] **Step 3: Add the TD-only filter**

In the `filtered` array's `.filter((c) => { ... })` body (starts at line 582), add this as the FIRST guard inside the callback, before the `brand` check:

```typescript
    if (c.route_type !== 'TD') return false
```

- [ ] **Step 4: Typecheck + verify tab loads**

Run (from `jarvis/frontend`): `npx tsc -b`
Expected: PASS.
Manual: run the dev server (`npm run dev`), open Foi de Parcurs — the second tab now reads "Sesiuni Driving"; clicking it lists TD rows only (no Comodat rows).

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): rename Parcurs tab to Sesiuni Driving, TD-only

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Session status — badge, row tint, status filter, summary badges

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — status filter `Select` (lines 636-648), summary badges (lines 609-610 and 703-708), row `className` + status `TableCell` (lines 744-755), filter logic (line 585).

**Interfaces:**
- Consumes: `sessionStatus` from Task 1.

- [ ] **Step 1: Replace the status filter options**

Replace the `SelectContent` of the Status filter (lines 642-647) which currently is:

```tsx
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="PENDING">Pending</SelectItem>
              <SelectItem value="FILLED">Filled</SelectItem>
            </SelectContent>
```

with the 4 session states (values are the `sessionStatus` keys):

```tsx
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="finalizat">Finalizat</SelectItem>
              <SelectItem value="driving">În desfășurare</SelectItem>
              <SelectItem value="intarziat">Întârziat</SelectItem>
              <SelectItem value="nealocat">Nealocat</SelectItem>
            </SelectContent>
```

- [ ] **Step 2: Update the status filter logic**

At line 585, the current filter is:

```typescript
    if (filterStatus !== 'all' && c.status !== filterStatus) return false
```

Replace with a match on the derived key:

```typescript
    if (filterStatus !== 'all' && sessionStatus(c).key !== filterStatus) return false
```

- [ ] **Step 3: Replace the summary counts**

Replace lines 609-610:

```typescript
  const pendingCount = filtered.filter((c) => c.status === 'PENDING').length
  const filledCount = filtered.filter((c) => c.status === 'FILLED').length
```

with per-state counts:

```typescript
  const countBy = (k: SessionStatusKey) => filtered.filter((c) => sessionStatus(c).key === k).length
  const finalizatCount = countBy('finalizat')
  const drivingCount = countBy('driving')
  const intarziatCount = countBy('intarziat')
  const nealocatCount = countBy('nealocat')
```

- [ ] **Step 4: Replace the summary badge row**

Replace the summary badges block (lines 704-708) which is:

```tsx
        <Badge variant="outline">{filtered.length} contracts</Badge>
        {pendingCount > 0 && <Badge variant="destructive">{pendingCount} pending</Badge>}
        {filledCount > 0 && <Badge className="bg-green-600">{filledCount} filled</Badge>}
```

with:

```tsx
        <Badge variant="outline">{filtered.length} sesiuni</Badge>
        {finalizatCount > 0 && <Badge className="bg-green-600">{finalizatCount} finalizate</Badge>}
        {drivingCount > 0 && <Badge className="bg-blue-600">{drivingCount} în desfășurare</Badge>}
        {intarziatCount > 0 && <Badge className="bg-red-600">{intarziatCount} întârziate</Badge>}
        {nealocatCount > 0 && <Badge variant="outline">{nealocatCount} nealocate</Badge>}
```

- [ ] **Step 5: Replace the row tint and the status cell**

The row `<TableRow>` at line 744 currently uses `STATUS_ROW_BG[c.status?.toLowerCase()]`. Replace the whole `<TableRow ...>` opening tag (lines 743-746):

```tsx
                    <TableRow
                      className={`cursor-pointer hover:bg-muted/40 ${STATUS_ROW_BG[c.status?.toLowerCase()] || ''}`}
                      onClick={() => setExpandedRow(isExpanded ? null : c.id)}
                    >
```

with (compute `ss` once at the top of the `.map` callback — see next step for where):

```tsx
                    <TableRow
                      className={`cursor-pointer hover:bg-muted/40 ${ss.rowClass}`}
                      onClick={() => setExpandedRow(isExpanded ? null : c.id)}
                    >
```

Then replace the status `TableCell` (lines 748-755):

```tsx
                      <TableCell>
                        <Badge
                          variant={c.status === 'FILLED' ? 'default' : 'destructive'}
                          className="text-xs"
                        >
                          {c.status}
                        </Badge>
                      </TableCell>
```

with:

```tsx
                      <TableCell>
                        <Badge className={`text-xs ${ss.badgeClass}`}>{ss.label}</Badge>
                      </TableCell>
```

- [ ] **Step 6: Compute `ss` inside the row map**

The `.map((c) => { ... })` at line 738 opens with:

```tsx
              {sorted.map((c) => {
                const isExpanded = expandedRow === c.id
                const u = fuelUnit(c.fuel_tank_capacity_liters > 100 ? 'Electric' : undefined)
```

Add the `ss` line right after `const isExpanded`:

```tsx
              {sorted.map((c) => {
                const isExpanded = expandedRow === c.id
                const ss = sessionStatus(c)
                const u = fuelUnit(c.fuel_tank_capacity_liters > 100 ? 'Electric' : undefined)
```

`STATUS_ROW_BG` is now unused — it was fully replaced by the helper in Task 1, so no reference remains. (The const no longer exists after Task 1's Step 2 replaced it.)

- [ ] **Step 7: Typecheck + verify**

Run: `npx tsc -b`
Expected: PASS.
Manual: completed sessions show a green "Finalizat" badge; the summary row shows "N finalizate"; the Status filter dropdown lists the four Romanian states and filters correctly.

- [ ] **Step 8: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): 4-state session status badges, filter, and counts

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Reframe columns — Date, Vehicle, Return; drop #/Type/Itinerary/Distance; default sort by date

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — default sort state (line 540), vin→vehicle map (line 577), sort comparator (lines 597-602), table header (lines 722-736), table body cells (lines 747-773).

**Interfaces:**
- Consumes: extended `FoiContract` (`departure_datetime`, `return_datetime`) from Task 1; `FpVehicle` (`mark`, `brand?`, `model`, `registration_number?`) from `src/types/foiParcurs.ts`.

- [ ] **Step 1: Change the default sort to newest session first**

At line 540-541:

```typescript
  const [sortBy, setSortBy] = useState('slot_number')
  const [sortDir, setSortDir] = useState('ASC')
```

Replace with:

```typescript
  const [sortBy, setSortBy] = useState('departure_datetime')
  const [sortDir, setSortDir] = useState('DESC')
```

- [ ] **Step 2: Build a vin→vehicle map (extend the existing vinBrand map)**

At line 577:

```typescript
  const vinBrand = new Map((vehiclesData?.vehicles ?? []).map((v) => [v.vin, v.brand]))
```

Replace with (keep `vinBrand` for the existing brand filter at line 583, add `vinVehicle`):

```typescript
  const vehiclesList = vehiclesData?.vehicles ?? []
  const vinBrand = new Map(vehiclesList.map((v) => [v.vin, v.brand]))
  const vinVehicle = new Map(vehiclesList.map((v) => [v.vin, v]))
```

- [ ] **Step 3: Make the sort comparator date-aware with a created_at fallback**

The sort at lines 597-602:

```typescript
  const sorted = [...filtered].sort((a, b) => {
    const aVal = (a as any)[sortBy] ?? ''
    const bVal = (b as any)[sortBy] ?? ''
    const cmp = typeof aVal === 'number' ? aVal - bVal : String(aVal).localeCompare(String(bVal))
    return sortDir === 'ASC' ? cmp : -cmp
  })
```

Replace with (departure_datetime falls back to created_at so PENDING rows still order sanely):

```typescript
  const sortVal = (c: FoiContract): string | number => {
    if (sortBy === 'departure_datetime') return c.departure_datetime || c.created_at || ''
    return ((c as any)[sortBy] ?? '') as string | number
  }
  const sorted = [...filtered].sort((a, b) => {
    const aVal = sortVal(a)
    const bVal = sortVal(b)
    const cmp = typeof aVal === 'number' && typeof bVal === 'number'
      ? aVal - bVal
      : String(aVal).localeCompare(String(bVal))
    return sortDir === 'ASC' ? cmp : -cmp
  })
```

- [ ] **Step 4: Replace the table header row**

The header (lines 722-736):

```tsx
              <TableRow>
                <SortableHeader col="slot_number" label="#" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <SortableHeader col="status" label="Status" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <TableHead>Company</TableHead>
                <SortableHeader col="vin" label="VIN" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <SortableHeader col="route_type" label="Type" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <SortableHeader col="distance_km" label="Distance" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <TableHead>KM</TableHead>
                <TableHead>Client</TableHead>
                <TableHead>Itinerary</TableHead>
                <TableHead>Advisor</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
```

Replace with:

```tsx
              <TableRow>
                <SortableHeader col="departure_datetime" label="Date" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <SortableHeader col="status" label="Status" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <TableHead>Company</TableHead>
                <SortableHeader col="vin" label="Vehicle" current={sortBy} dir={sortDir} toggle={toggleSort} />
                <TableHead>Client</TableHead>
                <TableHead>Consilier</TableHead>
                <TableHead>KM</TableHead>
                <TableHead>Return</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
```

Note: the expanded-row `TableCell colSpan={11}` (line 823) must become `colSpan={9}` — handled in Task 5.

- [ ] **Step 5: Replace the body cells (Date, keep Status, Company, Vehicle, Client, Consilier, KM, Return)**

Replace the sequence of cells from line 747 (`<TableCell className="text-xs">{c.slot_number || '—'}</TableCell>`) through line 773 (the Advisor cell `<TableCell className="text-xs">{c.advisor_name || '—'}</TableCell>`). The Status `TableCell` in that range was already set in Task 3 — keep it. The full replacement for that cell sequence is:

```tsx
                      <TableCell className="text-xs whitespace-nowrap">
                        {c.departure_datetime
                          ? new Date(c.departure_datetime).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
                          : new Date(c.created_at).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })}
                      </TableCell>
                      <TableCell>
                        <Badge className={`text-xs ${ss.badgeClass}`}>{ss.label}</Badge>
                      </TableCell>
                      <TableCell className="text-xs">{c.company_name || '—'}</TableCell>
                      <TableCell className="text-xs">
                        {(() => {
                          const v = vinVehicle.get(c.vin)
                          const name = v ? [v.brand || v.mark, v.model].filter(Boolean).join(' ') : ''
                          return (
                            <div className="leading-tight">
                              <div className="font-medium">{name || `${c.vin.slice(0, 12)}...`}</div>
                              {v?.registration_number && <div className="text-muted-foreground font-mono text-[11px]">{v.registration_number}</div>}
                            </div>
                          )
                        })()}
                      </TableCell>
                      <TableCell>
                        {c.client_name ? (
                          <span className="font-medium text-sm">{c.client_name}</span>
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs">{c.advisor_name || '—'}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">{c.km_start} - {c.km_end}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">
                        {c.return_datetime
                          ? new Date(c.return_datetime).toLocaleString('ro-RO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
                          : '—'}
                      </TableCell>
```

This drops the `#`, `Type`, `Itinerary`, and standalone `Distance` cells and merges VIN into the Vehicle cell.

- [ ] **Step 6: Typecheck + verify**

Run: `npx tsc -b`
Expected: PASS.
Manual: columns read Date · Status · Company · Vehicle · Client · Consilier · KM · Return · Actions; the Vehicle cell shows "Brand Model" + plate; rows are sorted newest-first by date; completed rows show a return timestamp.

- [ ] **Step 7: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): session-oriented columns (Date, Vehicle, Return) + date sort

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Actions cleanup, PDF access for completed sessions, expanded-row detail

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — Actions cell (lines 774-819), expanded-row `colSpan` (line 823), expanded Route block (add timestamps + VIN, lines 863-878), PDF gate (line 881).

**Interfaces:**
- Consumes: `sessionStatus`/`ss` from Tasks 1/3; `foiParcursApi.getContractPdfUrl(id, 'legal' | 'custom')` (existing).

- [ ] **Step 1: Fix the expanded-row colSpan (11 → 9)**

At line 823, change `<TableCell colSpan={11} className="px-6 py-4">` to `<TableCell colSpan={9} className="px-6 py-4">`.

- [ ] **Step 2: Rework the Actions cell — drop the duplicate client name, add PDF quick-link**

Replace the Actions cell inner `<div className="flex items-center gap-1"> ... </div>` (lines 775-818). The current content branches on `c.status === 'PENDING'` (Allocate button) else a green ✓ client-name, then the admin Reset and Delete. Replace the whole div with:

```tsx
                        <div className="flex items-center gap-1">
                          {c.status === 'PENDING' && (
                            <Button variant="outline" size="sm" onClick={() => setAllocatingContract(c)}>
                              <UserPlus className="mr-1 h-3.5 w-3.5" />
                              Allocate
                            </Button>
                          )}
                          {c.status !== 'PENDING' && (
                            <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank" rel="noopener" title="Descarcă PDF">
                              <Button variant="ghost" size="sm">
                                <FileText className="h-4 w-4" />
                              </Button>
                            </a>
                          )}
                          {isAdmin && c.route_type === 'TD' && ss.key !== 'nealocat' && (
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Reset la 'driving' (re-testare retur)"
                              onClick={() => {
                                if (confirm('Resetezi acest test drive la „driving”? Datele de retur se șterg.')) {
                                  resetContractMutation.mutate(c.id)
                                }
                              }}
                              disabled={resetContractMutation.isPending}
                            >
                              <RotateCcw className="h-4 w-4" />
                            </Button>
                          )}
                          {isAdmin && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive hover:text-destructive"
                              title="Șterge înregistrarea (permanent)"
                              onClick={() => {
                                if (confirm('Ștergi definitiv această înregistrare? Acțiunea nu poate fi anulată.')) {
                                  deleteContractMutation.mutate(c.id)
                                }
                              }}
                              disabled={deleteContractMutation.isPending}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
```

(The reset visibility broadens from `c.status === 'COMPLETED'` to any non-`nealocat` TD row, so a driving/overdue session can also be reset. `Check` is no longer used in this cell — see Step 4 for the unused-import check.)

- [ ] **Step 3: Add departure/return timestamps + VIN to the expanded Route block, and open PDFs for non-PENDING**

In the expanded Route block (lines 866-877), after the existing `Itinerary` / `Contract` / `Batch` / `Period` / `Created` rows, add VIN and the session timestamps. Replace the Route `<div className="grid ...">` inner content:

```tsx
                              <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                                <span className="text-muted-foreground">Itinerary</span>
                                <span>{c.itinerary || '—'}</span>
                                <span className="text-muted-foreground">Contract</span>
                                <span className="font-mono">{c.contract_id}</span>
                                <span className="text-muted-foreground">Batch</span>
                                <span className="font-mono">{c.batch_id || '—'}</span>
                                <span className="text-muted-foreground">Period</span>
                                <span>{c.month && c.year ? `${String(c.month).padStart(2, '0')}/${c.year}` : '—'}</span>
                                <span className="text-muted-foreground">Created</span>
                                <span>{new Date(c.created_at).toLocaleString('ro-RO')}</span>
                              </div>
```

with the VIN + timestamps added:

```tsx
                              <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                                <span className="text-muted-foreground">VIN</span>
                                <span className="font-mono">{c.vin}</span>
                                <span className="text-muted-foreground">Plecare</span>
                                <span>{c.departure_datetime ? new Date(c.departure_datetime).toLocaleString('ro-RO') : '—'}</span>
                                <span className="text-muted-foreground">Retur</span>
                                <span>{c.return_datetime ? new Date(c.return_datetime).toLocaleString('ro-RO') : '—'}</span>
                                <span className="text-muted-foreground">Itinerary</span>
                                <span>{c.itinerary || '—'}</span>
                                <span className="text-muted-foreground">Contract</span>
                                <span className="font-mono">{c.contract_id}</span>
                                <span className="text-muted-foreground">Batch</span>
                                <span className="font-mono">{c.batch_id || '—'}</span>
                                <span className="text-muted-foreground">Period</span>
                                <span>{c.month && c.year ? `${String(c.month).padStart(2, '0')}/${c.year}` : '—'}</span>
                                <span className="text-muted-foreground">Created</span>
                                <span>{new Date(c.created_at).toLocaleString('ro-RO')}</span>
                              </div>
```

Then fix the PDF-downloads gate at line 881: change `{c.status === 'FILLED' && (` to `{c.status !== 'PENDING' && (` so completed sessions expose the Legal/Custom PDF buttons.

- [ ] **Step 4: Confirm no unused-import fallout**

Removing the green ✓ client-name drops one `Check` usage, but `Check` is still used elsewhere in this file (the batch-saved confirmation and other tabs). Do NOT remove the import. Verify:

Run: `grep -nw "Check" jarvis/frontend/src/pages/FoiParcurs/index.tsx`
Expected: multiple matches remain (import line plus ~3 usages) → leave the `lucide-react` import unchanged. No other imports become unused (`UserPlus`, `RotateCcw`, `Trash2`, `FileText` are all still used).

- [ ] **Step 5: Typecheck + lint + verify**

Run (from `jarvis/frontend`): `npx tsc -b`
Expected: PASS.
Run: `npx eslint src/pages/FoiParcurs/index.tsx`
Expected: no errors on the file (pre-existing warnings elsewhere are out of scope).
Manual: expand a completed session — Legal PDF and Custom PDF buttons appear; the expanded panel shows VIN + Plecare/Retur timestamps; the Actions column no longer duplicates the client name and shows a PDF icon; admin Reset appears on driving/overdue/completed TD rows.

- [ ] **Step 6: Full build + Python regression + commit**

Run (from `jarvis/frontend`): `npm run build`
Expected: build succeeds.
Run (from repo root, venv active): `python -m pytest jarvis/tests/foi_parcurs/ -q`
Expected: 21 passed.

```bash
git add jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "feat(foi-parcurs): PDF access for completed sessions, cleaner actions + detail

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Status model (4-state, correct colors) → Task 1 (helper) + Task 3 (badge/tint). ✔
- Columns reframe (Date/Vehicle/Return, drop #/Type/Itinerary/Distance) → Task 4. ✔
- Default sort by date DESC → Task 4 Step 1/3. ✔
- Status filter (4 states) → Task 3 Step 1/2. ✔
- Summary badges recount → Task 3 Step 3/4. ✔
- Row tint by state → Task 3 Step 5/6. ✔
- PDF access fixed + quick-link → Task 5 Step 2/3. ✔
- Remove redundant green client name → Task 5 Step 2. ✔
- Expanded row gains timestamps + VIN → Task 5 Step 3. ✔
- Rename label → "Sesiuni Driving", keep value `parcurs`, rename component → Task 2. ✔
- Comodat hidden (route_type = 'TD') → Task 2 Step 3. ✔
- Frontend-only, no backend → Global Constraints; every task touches only frontend files. ✔

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✔

**Type consistency:** `sessionStatus` returns `{ key, label, badgeClass, rowClass }` in Task 1 and is consumed with those exact property names in Tasks 3–5. `SessionStatusKey` union `'nealocat' | 'driving' | 'intarziat' | 'finalizat'` used consistently in filter values, `countBy`, and reset visibility. `vinVehicle` map (Task 4) yields `FpVehicle` with `mark`/`brand`/`model`/`registration_number` — all present in the type. `colSpan` corrected 11 → 9 to match the new 9-column header. ✔
