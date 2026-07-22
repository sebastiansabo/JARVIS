# Plan a Driving Session — Phase 2 (Web) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan is TDD-free (no frontend unit-test runner exists in this repo) — each task's gate is typecheck + scoped lint + manual verification, not a red/green test cycle.

**Goal:** Extend the Foi de Parcurs web module (`jarvis/frontend/src/pages/FoiParcurs/`) to consume the already-deployed Phase 1 backend (`PLANNED` draft status, activate, discard, VIN conflicts): a 5th "Planificat" session state in Sesiuni Driving, a "Planifică (draft)" action + activation flow on the Test Drive form, a soft-block conflict dialog, and a new from-scratch Calendar tab.

**Architecture:** Pure frontend (React 19 + TypeScript + Tailwind 4 + shadcn/ui + TanStack Query). No new backend work — all four new endpoints (`POST /test-drive` with `status:'PLANNED'`, `PUT /test-drive/{id}/activate`, `DELETE /test-drive/{id}`, `GET /vehicles/{vin}/conflicts`) are live. `sessionStatus`/`SessionStatusKey` move out of `index.tsx` into a standalone `sessionStatus.ts` module so the new `CalendarTab` can import it without creating a circular import (`index.tsx` → `CalendarTab.tsx` → `index.tsx`).

**Tech Stack:** React 19, TypeScript 5.8 (strict, `noUnusedLocals`/`noUnusedParameters` on), Tailwind 4, shadcn/ui (Dialog, Badge, Button, Select, Table, Tabs — Popover exists but is unused here, Dialog is the codebase's established click-to-detail pattern), TanStack Query v5, react-router-dom v7. Design spec: `docs/superpowers/specs/2026-07-20-plan-driving-session-design.md`. Backend contract: `docs/superpowers/plans/2026-07-20-plan-driving-session-phase1-backend.md` (verified against the actual deployed code in `jarvis/foi_parcurs/routes/test_drive.py`, `jarvis/foi_parcurs/routes/vehicles.py`, `jarvis/foi_parcurs/repositories/foi_parcurs_repository.py`).

## Global Constraints

- **Web-only** (this phase). Touch only `jarvis/frontend/src/**`. Do not touch backend (`jarvis/foi_parcurs/**`) or jarvis-mobile-2 (Phase 3, separate repo/plan).
- **No calendar/date library is installed** (no `date-fns`, `react-day-picker`, `FullCalendar`, no `src/components/ui/calendar.tsx`) — verified via `grep -rn "date-fns|react-day-picker|FullCalendar" package.json src/components/ui/` (no hits). The Calendar tab is built from scratch with plain JS `Date` math + a CSS grid. Do not add a new dependency.
- **No frontend unit-test runner exists** (no vitest/jest in `package.json`). Verification gate per task is:
  1. `cd jarvis/frontend && npx tsc -b` — must exit 0 (strict mode: `noUnusedLocals`, `noUnusedParameters`, `strict` are all on — dead imports/vars fail the build).
  2. `cd jarvis/frontend && npx eslint <touched files>` — **known repo condition**: this checkout has no `eslint.config.js` (verified: `npx eslint <file>` currently fails immediately with "ESLint couldn't find an eslint.config.(js|mjs|cjs) file", unrelated to any change in this plan). Run it anyway per convention; if it fails *only* with that missing-config message (not a per-file lint error), `tsc -b` is the authoritative gate for that task — do not block on it.
  3. A manual verification line (code-path reasoning / where to click in `npm run dev` — there is no automated E2E harness here either).
- **`GET /api/foi-parcurs/contracts` does not support `date_from`/`date_to`/`status`/`route_type` server-side** — verified against `jarvis/foi_parcurs/routes/contracts.py:api_list_contracts` (only reads `vin`, `company_id`, `page`, `per_page`, `sort_by`, `sort_dir`). `SessionsTab` already works around this by fetching up to `per_page: 1000` rows for the company and filtering/sorting client-side — `CalendarTab` follows the exact same pattern (same query key `['foi-contracts-all', companyId]`, so TanStack Query dedupes the request against `SessionsTab`/`ContractsTab`). Do not invent server-side date filtering.
- **`GET /vehicles/{vin}/conflicts` response has no `td_status` field** — verified against `FoiParcursRepository.find_conflicts()`: it selects `id, contract_id, status, departure_datetime, return_datetime, client_name, advisor_name` only. The design spec's response shape (which lists `td_status`) is aspirational; the `VehicleConflict` type in this plan matches the real SQL exactly.
- **General conditions acceptance is out of scope.** The backend now conditionally requires `general_conditions_accepted` on both live-submit and activate (when the company+brand has `general_conditions` text configured), but the *current* web `TestDriveForm.tsx` never sends this field and has no UI for it — this is a pre-existing gap, not introduced by Phase 1/2. This plan does not add general-conditions UI; it only wires the fields the current form already handles (GDPR checkbox, signature). Noted as a risk in the Self-Review.
- **Status union widens, not narrows.** `FoiContract.status` gains `'PLANNED'` as a 4th member (`'PENDING' | 'PLANNED' | 'FILLED' | 'COMPLETED'`). This is backward-compatible for every existing `===` check in the codebase; nothing needs updating outside `FoiParcurs/`.
- Existing live-submit behavior (`POST /test-drive` without `status`, or `status:'FILLED'`) must remain untouched — Task 4/5 only *add* new call paths (`planTestDrive`, `activateTestDrive`), never modify what `submitTestDrive` sends.
- JARVIS git workflow: work on `dev`, commit per task, do **not** push (per repo policy, docs/plans on `dev`/scratch only — this plan file itself stays off staging/main per `feedback_no_plans_to_staging_prod`).

## File Structure

**Created:**
- `jarvis/frontend/src/pages/FoiParcurs/sessionStatus.ts` — `sessionStatus()` / `SessionStatusKey`, extracted from `index.tsx` (Task 2) so `CalendarTab.tsx` can import it without a circular dependency.
- `jarvis/frontend/src/hooks/useVehicleConflicts.ts` — imperative conflict-check hook (Task 3).
- `jarvis/frontend/src/pages/FoiParcurs/ConflictDialog.tsx` — reusable soft-block dialog (Task 3).
- `jarvis/frontend/src/pages/FoiParcurs/CalendarTab.tsx` — new "Calendar" tab, from-scratch month grid (Task 6).

**Modified:**
- `jarvis/frontend/src/types/foiParcurs.ts` — widen `FoiContract.status`, add `departure_damage`, add `PlanTestDrivePayload` / `ActivateTestDrivePayload` / `VehicleConflict` (Task 1).
- `jarvis/frontend/src/api/foiParcurs.ts` — add `planTestDrive`, `activateTestDrive`, `discardTestDrive`, `getVehicleConflicts` (Task 1).
- `jarvis/frontend/src/pages/FoiParcurs/index.tsx` — `SessionsTab`: 5th status, filter, summary, PLANNED row actions; register the Calendar tab (Task 2, Task 6).
- `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx` — "Planifică (draft)" action, activation mode (`?activate={id}`), conflict-check wiring (Task 4, Task 5).

---

### Task 1: API client + types — plan/activate/discard/conflicts

**Files:**
- Modify: `jarvis/frontend/src/types/foiParcurs.ts`
- Modify: `jarvis/frontend/src/api/foiParcurs.ts`

**Interfaces produced:** `PlanTestDrivePayload`, `ActivateTestDrivePayload`, `VehicleConflict` types; `foiParcursApi.planTestDrive`, `.activateTestDrive`, `.discardTestDrive`, `.getVehicleConflicts` — consumed by Tasks 2, 3, 4, 5, 6.

- [ ] **Step 1: Widen `FoiContract` in `types/foiParcurs.ts`**

Current (lines 145–180):

```ts
// ── Contract ──
export interface FoiContract {
  id: number
  contract_id: string
  batch_id?: string
  vin: string
  client_id: number | null
  client_name?: string
  client_phone?: string
  company_id: number
  company_name?: string
  year?: number
  month?: number
  route_type: RouteType
  slot_number: number
  km_start: number
  km_end: number
  distance_km: number
  fuel_tank_capacity_liters: number
  fuel_gauge_start_level: FuelGaugeLevel
  fuel_gauge_end_level: FuelGaugeLevel
  fuel_start_liters: number
  fuel_end_liters: number
  fuel_consumed_liters: number
  itinerary: string
  advisor_name: string
  signature_ai_generated: string
  status: 'PENDING' | 'FILLED' | 'COMPLETED'
  created_at: string
  updated_at: string
  // Returned by get_contracts (fp.* + _TD_STATUS_SQL) but previously undeclared:
  td_status?: 'complete' | 'incomplete' | 'driving'
  departure_datetime?: string | null
  return_datetime?: string | null
  returned_at?: string | null
}
```

Replace with:

```ts
// ── Contract ──
export interface FoiContract {
  id: number
  contract_id: string
  batch_id?: string
  vin: string
  client_id: number | null
  client_name?: string
  client_phone?: string
  company_id: number
  company_name?: string
  year?: number
  month?: number
  route_type: RouteType
  slot_number: number
  km_start: number
  km_end: number
  distance_km: number
  fuel_tank_capacity_liters: number
  fuel_gauge_start_level: FuelGaugeLevel
  fuel_gauge_end_level: FuelGaugeLevel
  fuel_start_liters: number
  fuel_end_liters: number
  fuel_consumed_liters: number
  itinerary: string
  advisor_name: string
  signature_ai_generated: string
  // 'PLANNED' — draft session created ahead of time (Plan a Driving Session,
  // Phase 1 backend). Signature/GDPR/PDF are deferred; activated into
  // 'FILLED' when the client arrives (PUT /test-drive/{id}/activate).
  status: 'PENDING' | 'PLANNED' | 'FILLED' | 'COMPLETED'
  created_at: string
  updated_at: string
  // Returned by get_contracts (fp.* + _TD_STATUS_SQL) but previously undeclared:
  td_status?: 'complete' | 'incomplete' | 'driving'
  departure_datetime?: string | null
  return_datetime?: string | null
  returned_at?: string | null
  departure_damage?: TdDamageItem[] | null
}
```

- [ ] **Step 2: Append the new payload/response types at the end of `types/foiParcurs.ts`**

Current end of file (the `TestDriveFormPayload` interface, last block in the file):

```ts
// ── Test Drive Form Payload ──
export interface TestDriveFormPayload {
  company_id: number
  vin: string
  registration_number: string
  client_id: number
  odometer_start: number
  odometer_end?: number
  estimated_km: number
  fuel_tank_capacity_liters?: number
  fuel_gauge_start_level: FuelGaugeLevel
  fuel_gauge_end_level?: FuelGaugeLevel
  fuel_start_liters?: number
  fuel_end_liters?: number
  fuel_consumed_liters?: number
  itinerary?: string
  departure_datetime: string
  return_datetime?: string
  advisor_name: string
  advisor_signature?: string
  client_signature: string
  gdpr_consent: boolean
  inspection_acceptance?: boolean
  inspection_id?: number
  departure_damage?: TdDamageItem[]
  driver_license_photo?: string
  driver_license_number?: string
  driver_license_expiry?: string
}
```

Append immediately after it:

```ts

// ── Plan (draft) Test Drive Payload — POST /test-drive with status:'PLANNED'.
// Same shape as TestDriveFormPayload except client_signature/gdpr_consent are
// deferred to activation (backend only requires them when status is
// absent/'FILLED' — see api_submit_test_drive's `is_draft` branch). ──
export type PlanTestDrivePayload = Omit<TestDriveFormPayload, 'client_signature' | 'gdpr_consent'> & {
  status: 'PLANNED'
  client_signature?: string
  gdpr_consent?: boolean
}

// ── Activate a PLANNED draft — PUT /test-drive/{id}/activate. Only
// client_signature is required by the backend; everything else is an
// optional handover edit (unset fields keep the PLANNED row's existing
// values). ──
export interface ActivateTestDrivePayload {
  client_signature: string
  advisor_signature?: string
  gdpr_consent?: boolean
  general_conditions_accepted?: boolean
  odometer_start?: number
  fuel_gauge_start_level?: FuelGaugeLevel
  fuel_tank_capacity_liters?: number
  departure_datetime?: string
  return_datetime?: string
  departure_damage?: TdDamageItem[]
}

// ── Vehicle conflict — GET /vehicles/{vin}/conflicts response row. Matches
// FoiParcursRepository.find_conflicts()'s SELECT list exactly (no td_status —
// the backend query doesn't derive/select it). ──
export interface VehicleConflict {
  id: number
  contract_id: string
  status: 'PLANNED' | 'FILLED' | 'COMPLETED'
  departure_datetime: string | null
  return_datetime: string | null
  client_name: string | null
  advisor_name: string
}
```

- [ ] **Step 3: Add the 4 API methods in `api/foiParcurs.ts`**

Current import block (lines 1–15):

```ts
import { api } from './client'
import type {
  BatchConfig,
  PreviewResponse,
  CreateContractPayload,
  FoiContract,
  FoiClient,
  CreateClientPayload,
  FpVehicle,
  FpVehicleInspection,
  TestDriveFormPayload,
  CrmClient,
  CreateCrmClientPayload,
  DriverLicenseOcrData,
} from '../types/foiParcurs'
```

Replace with:

```ts
import { api } from './client'
import type {
  BatchConfig,
  PreviewResponse,
  CreateContractPayload,
  FoiContract,
  FoiClient,
  CreateClientPayload,
  FpVehicle,
  FpVehicleInspection,
  TestDriveFormPayload,
  PlanTestDrivePayload,
  ActivateTestDrivePayload,
  VehicleConflict,
  CrmClient,
  CreateCrmClientPayload,
  DriverLicenseOcrData,
} from '../types/foiParcurs'
```

Current (the Test Drive Form section):

```ts
  // ── Test Drive Form ──
  submitTestDrive: (data: TestDriveFormPayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),
```

Replace with:

```ts
  // ── Test Drive Form ──
  submitTestDrive: (data: TestDriveFormPayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  // ── Plan a draft TD (status: 'PLANNED') — same endpoint, signature/GDPR/PDF
  //    deferred to activation ──
  planTestDrive: (data: PlanTestDrivePayload) =>
    api.post<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive`, data),

  // ── Activate a PLANNED draft → FILLED (client signature required) ──
  activateTestDrive: (id: number, data: ActivateTestDrivePayload) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/activate`, data),

  // ── Discard a PLANNED draft (PLANNED-only; 409 otherwise) ──
  discardTestDrive: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/test-drive/${id}`),

  // ── Overlapping PLANNED/live sessions for a VIN in [from, to] — soft-block
  //    double-booking a car (never hard-blocks) ──
  getVehicleConflicts: (vin: string, params: { from: string; to: string; exclude_id?: number }) =>
    api.get<{ success: boolean; conflicts: VehicleConflict[] }>(`${BASE}/vehicles/${vin}/conflicts${qs(params)}`),
```

- [ ] **Step 4: Typecheck + lint**

Run: `cd jarvis/frontend && npx tsc -b`
Expected: exits 0 (no other file references the new types yet, so nothing else should break).

Run: `cd jarvis/frontend && npx eslint src/types/foiParcurs.ts src/api/foiParcurs.ts`
Expected: 0 findings, or the pre-existing "couldn't find eslint.config" message (see Global Constraints) — not a per-file error.

- [ ] **Step 5: Manual verification**

Open `jarvis/frontend/src/api/foiParcurs.ts` and `jarvis/frontend/src/types/foiParcurs.ts` and confirm: the 4 new methods hit the exact paths verified against the backend (`POST /api/foi-parcurs/test-drive`, `PUT /api/foi-parcurs/test-drive/{id}/activate`, `DELETE /api/foi-parcurs/test-drive/{id}`, `GET /api/foi-parcurs/vehicles/{vin}/conflicts`), and `VehicleConflict` has no `td_status` field.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/types/foiParcurs.ts jarvis/frontend/src/api/foiParcurs.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add plan/activate/discard/conflicts API client + types

Wires the Phase 1 backend contract (POST .../test-drive status=PLANNED,
PUT .../activate, DELETE .../test-drive/{id}, GET .../conflicts) into the
foiParcursApi client ahead of the Sesiuni Driving / Test Drive form / Calendar
UI work.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Sesiuni Driving — 5th state (`planificat`), filter, summary, row actions

**Files:**
- Create: `jarvis/frontend/src/pages/FoiParcurs/sessionStatus.ts`
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx`

**Interfaces:**
- Produces: `sessionStatus()` / `SessionStatusKey` (now 5 states) in a standalone module, importable by `CalendarTab.tsx` (Task 6) without a circular dependency on `index.tsx`.
- Consumes: `foiParcursApi.discardTestDrive` (Task 1).

- [ ] **Step 1: Create `sessionStatus.ts`**

This is the exact logic currently inline in `index.tsx` (lines 425–447), moved out and extended with the `PLANNED` branch checked first (per the design spec: "PLANNED must be evaluated before td_status everywhere status is derived"):

```ts
import type { FoiContract } from '@/types/foiParcurs'

// Derived 5-state session status for the Sesiuni Driving tab (+ Calendar tab).
// Combines the raw `status` column with the backend-derived `td_status`
// (complete/incomplete/driving). PLANNED is checked FIRST — a draft session
// (Plan a Driving Session) with deferred signature/GDPR/PDF. PENDING is
// checked next: td_status' ELSE branch returns 'driving' even for
// un-allocated PENDING batch slots that were never driven.
export type SessionStatusKey = 'planificat' | 'nealocat' | 'driving' | 'intarziat' | 'finalizat'

export function sessionStatus(c: FoiContract): {
  key: SessionStatusKey
  label: string
  badgeClass: string
  rowClass: string
} {
  if (c.status === 'PLANNED') {
    return { key: 'planificat', label: 'Planificat', badgeClass: 'bg-indigo-600 text-white', rowClass: 'bg-indigo-500/5 border-l-4 border-l-indigo-500/40' }
  }
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

- [ ] **Step 2: Import `sessionStatus`/`SessionStatusKey` + `PlayCircle` icon**

(Done before Step 3's re-export, so the re-export line has something in scope to re-export — both land in the same commit, but this keeps the file valid at every intermediate step.)

Current top-of-file imports (lines 1–30, the lucide-react block):

```ts
import React, { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Plus,
  Eye,
  ChevronLeft,
  Fuel,
  Route,
  Search,
  UserPlus,
  Check,
  ArrowUpDown,
  Trash2,
  RotateCcw,
  Archive,
  Car,
  Pencil,
  XIcon,
  SlidersHorizontal,
  Settings,
  Save,
  Sparkles,
  MapPin,
  ChevronDown,
  ChevronUp,
  Download,
  FileSpreadsheet,
} from 'lucide-react'
```

Replace with:

```ts
import React, { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Plus,
  Eye,
  ChevronLeft,
  Fuel,
  Route,
  Search,
  UserPlus,
  Check,
  ArrowUpDown,
  Trash2,
  RotateCcw,
  Archive,
  Car,
  Pencil,
  XIcon,
  SlidersHorizontal,
  Settings,
  Save,
  Sparkles,
  MapPin,
  ChevronDown,
  ChevronUp,
  Download,
  FileSpreadsheet,
  PlayCircle,
} from 'lucide-react'
```

Current relative import (line 78):

```ts
import { VehicleOdometerHistory } from './VehicleOdometerHistory'
```

Replace with:

```ts
import { VehicleOdometerHistory } from './VehicleOdometerHistory'
import { sessionStatus, type SessionStatusKey } from './sessionStatus'
```

(`CalendarTab` import is added separately in Task 6, since it doesn't exist yet at this point in the plan.)

- [ ] **Step 3: Replace the inline `sessionStatus`/`SessionStatusKey` definition with a re-export**

Current (lines 423–447 — now that Step 2 imports the same names from `./sessionStatus`, this local definition is a duplicate and must go):

```ts
// ── Sesiuni Driving Tab — TD sessions (historical record) ──

// Derived 4-state session status for the Sesiuni Driving tab. Combines the raw
// `status` column with the backend-derived `td_status` (complete/incomplete/driving).
// PENDING must be checked first: td_status' ELSE branch returns 'driving' even for
// un-allocated PENDING batch slots that were never driven.
export type SessionStatusKey = 'nealocat' | 'driving' | 'intarziat' | 'finalizat'

export function sessionStatus(c: FoiContract): {
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

Replace with:

```ts
// ── Sesiuni Driving Tab — TD sessions (historical record) ──
// sessionStatus/SessionStatusKey now live in ./sessionStatus.ts (shared with
// CalendarTab — keeping them here would make index.tsx → CalendarTab.tsx →
// index.tsx a circular import).
export { sessionStatus, type SessionStatusKey }
```

- [ ] **Step 4: `SessionsTab` — add `navigate` + `discardMutation`**

Current (lines 549–589):

```ts
function SessionsTab({ companyId, brand }: { companyId: number; brand: string }) {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const now = new Date()
  const [allocatingContract, setAllocatingContract] = useState<FoiContract | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [filterVin, setFilterVin] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [filterMonth, setFilterMonth] = useState<string>('all')
  const [filterYear, setFilterYear] = useState<string>('all')
  const [sortBy, setSortBy] = useState('departure_datetime')
  const [sortDir, setSortDir] = useState('DESC')

  // ── Export modal ──
  const [exportOpen, setExportOpen] = useState(false)
  const [expFrom, setExpFrom] = useState('')
  const [expTo, setExpTo] = useState('')
  const [expVin, setExpVin] = useState('all')

  const isAdmin = ['admin', 'superadmin'].includes((user?.role_name ?? '').toLowerCase())

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () =>
      foiParcursApi.getContracts({ company_id: companyId || undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })

  // Admin-only registration cleanup (delete) + reset a completed TD to 'driving'.
  const deleteContractMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.deleteContract(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] }),
  })
  const resetContractMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.resetContract(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      queryClient.invalidateQueries({ queryKey: ['odometer-history'] })
    },
  })
```

Replace with:

```ts
function SessionsTab({ companyId, brand }: { companyId: number; brand: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const now = new Date()
  const [allocatingContract, setAllocatingContract] = useState<FoiContract | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [filterVin, setFilterVin] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [filterMonth, setFilterMonth] = useState<string>('all')
  const [filterYear, setFilterYear] = useState<string>('all')
  const [sortBy, setSortBy] = useState('departure_datetime')
  const [sortDir, setSortDir] = useState('DESC')

  // ── Export modal ──
  const [exportOpen, setExportOpen] = useState(false)
  const [expFrom, setExpFrom] = useState('')
  const [expTo, setExpTo] = useState('')
  const [expVin, setExpVin] = useState('all')

  const isAdmin = ['admin', 'superadmin'].includes((user?.role_name ?? '').toLowerCase())

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () =>
      foiParcursApi.getContracts({ company_id: companyId || undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })

  // Admin-only registration cleanup (delete) + reset a completed TD to 'driving'.
  const deleteContractMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.deleteContract(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] }),
  })
  const resetContractMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.resetContract(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      queryClient.invalidateQueries({ queryKey: ['odometer-history'] })
    },
  })
  // Discard a PLANNED draft (any TD user — same gate as create). Only PLANNED
  // rows are eligible; the backend 409s otherwise.
  const discardMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.discardTestDrive(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] }),
  })
```

- [ ] **Step 5: Status filter dropdown — add "Planificat"**

Current (lines 670–681):

```tsx
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="h-8 min-w-[120px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="finalizat">Finalizat</SelectItem>
              <SelectItem value="driving">În desfășurare</SelectItem>
              <SelectItem value="intarziat">Întârziat</SelectItem>
              <SelectItem value="nealocat">Nealocat</SelectItem>
            </SelectContent>
          </Select>
```

Replace with:

```tsx
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="h-8 min-w-[120px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="planificat">Planificat</SelectItem>
              <SelectItem value="finalizat">Finalizat</SelectItem>
              <SelectItem value="driving">În desfășurare</SelectItem>
              <SelectItem value="intarziat">Întârziat</SelectItem>
              <SelectItem value="nealocat">Nealocat</SelectItem>
            </SelectContent>
          </Select>
```

- [ ] **Step 6: Summary counts + badges**

Current (lines 638–644):

```ts
  const countBy = (k: SessionStatusKey) => filtered.filter((c) => sessionStatus(c).key === k).length
  const finalizatCount = countBy('finalizat')
  const drivingCount = countBy('driving')
  const intarziatCount = countBy('intarziat')
  const nealocatCount = countBy('nealocat')
```

Replace with:

```ts
  const countBy = (k: SessionStatusKey) => filtered.filter((c) => sessionStatus(c).key === k).length
  const planificatCount = countBy('planificat')
  const finalizatCount = countBy('finalizat')
  const drivingCount = countBy('driving')
  const intarziatCount = countBy('intarziat')
  const nealocatCount = countBy('nealocat')
```

Current (lines 738–744):

```tsx
      <div className="flex gap-2 text-sm">
        <Badge variant="outline">{filtered.length} sesiuni</Badge>
        {finalizatCount > 0 && <Badge className="bg-green-600">{finalizatCount} finalizate</Badge>}
        {drivingCount > 0 && <Badge className="bg-blue-600">{drivingCount} în desfășurare</Badge>}
        {intarziatCount > 0 && <Badge className="bg-red-600">{intarziatCount} întârziate</Badge>}
        {nealocatCount > 0 && <Badge variant="outline">{nealocatCount} nealocate</Badge>}
      </div>
```

Replace with:

```tsx
      <div className="flex gap-2 text-sm">
        <Badge variant="outline">{filtered.length} sesiuni</Badge>
        {planificatCount > 0 && <Badge className="bg-indigo-600">{planificatCount} planificate</Badge>}
        {finalizatCount > 0 && <Badge className="bg-green-600">{finalizatCount} finalizate</Badge>}
        {drivingCount > 0 && <Badge className="bg-blue-600">{drivingCount} în desfășurare</Badge>}
        {intarziatCount > 0 && <Badge className="bg-red-600">{intarziatCount} întârziate</Badge>}
        {nealocatCount > 0 && <Badge variant="outline">{nealocatCount} nealocate</Badge>}
      </div>
```

- [ ] **Step 7: Row actions — Activate/Discard for PLANNED, exclude PLANNED from the PDF link**

Current (lines 817–864):

```tsx
                      <TableCell onClick={(e) => e.stopPropagation()}>
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
                      </TableCell>
```

Replace with:

```tsx
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          {c.status === 'PENDING' && (
                            <Button variant="outline" size="sm" onClick={() => setAllocatingContract(c)}>
                              <UserPlus className="mr-1 h-3.5 w-3.5" />
                              Allocate
                            </Button>
                          )}
                          {c.status === 'PLANNED' && (
                            <>
                              <Button variant="outline" size="sm" onClick={() => navigate(`/app/foi-parcurs/test-drive?activate=${c.id}`)}>
                                <PlayCircle className="mr-1 h-3.5 w-3.5" />
                                Începe sesiunea
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive hover:text-destructive"
                                title="Renunță la planificare"
                                onClick={() => {
                                  if (confirm('Renunți la această sesiune planificată? Acțiunea nu poate fi anulată.')) {
                                    discardMutation.mutate(c.id)
                                  }
                                }}
                                disabled={discardMutation.isPending}
                              >
                                <XIcon className="h-4 w-4" />
                              </Button>
                            </>
                          )}
                          {c.status !== 'PENDING' && c.status !== 'PLANNED' && (
                            <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank" rel="noopener" title="Descarcă PDF">
                              <Button variant="ghost" size="sm">
                                <FileText className="h-4 w-4" />
                              </Button>
                            </a>
                          )}
                          {isAdmin && c.route_type === 'TD' && ss.key !== 'nealocat' && ss.key !== 'planificat' && (
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
                      </TableCell>
```

Note: "Editează" from the design spec's 3-action list (Începe sesiunea / Editează / Discard) folds into "Începe sesiunea" — Phase 1 has no edit-without-activate route, only activate (which already reopens the form pre-filled for confirm/adjust) and discard. Following current code per the Global Constraints instruction.

- [ ] **Step 8: Expanded row — exclude PLANNED from the PDF Downloads section**

Current (lines 931–947):

```tsx
                          {/* PDF Downloads */}
                          {c.status !== 'PENDING' && (
                            <div className="flex gap-2 mt-3 pt-3 border-t">
                              <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank" rel="noopener">
                                <Button variant="outline" size="sm">
                                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                                  Legal PDF
                                </Button>
                              </a>
                              <a href={foiParcursApi.getContractPdfUrl(c.id, 'custom')} target="_blank" rel="noopener">
                                <Button variant="outline" size="sm">
                                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                                  Custom PDF
                                </Button>
                              </a>
                            </div>
                          )}
```

Replace with:

```tsx
                          {/* PDF Downloads — none yet for a PLANNED draft (generated at activation) */}
                          {c.status !== 'PENDING' && c.status !== 'PLANNED' && (
                            <div className="flex gap-2 mt-3 pt-3 border-t">
                              <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank" rel="noopener">
                                <Button variant="outline" size="sm">
                                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                                  Legal PDF
                                </Button>
                              </a>
                              <a href={foiParcursApi.getContractPdfUrl(c.id, 'custom')} target="_blank" rel="noopener">
                                <Button variant="outline" size="sm">
                                  <FileText className="mr-1.5 h-3.5 w-3.5" />
                                  Custom PDF
                                </Button>
                              </a>
                            </div>
                          )}
```

- [ ] **Step 9: Typecheck + lint**

Run: `cd jarvis/frontend && npx tsc -b`
Expected: exits 0.

Run: `cd jarvis/frontend && npx eslint src/pages/FoiParcurs/sessionStatus.ts src/pages/FoiParcurs/index.tsx`
Expected: 0 findings (or the pre-existing missing-config message).

- [ ] **Step 10: Manual verification**

`npm run dev` in `jarvis/frontend`, open `/app/foi-parcurs`, Sesiuni Driving tab. Confirm: Status filter has "Planificat"; if any `PLANNED` row exists it shows an indigo badge, indigo-tinted row, "Începe sesiunea" + a red X (discard) button and no PDF icon; clicking discard shows the RO confirm and removes the row on confirm.

- [ ] **Step 11: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/sessionStatus.ts jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add Planificat 5th state to Sesiuni Driving

Extracts sessionStatus/SessionStatusKey into sessionStatus.ts (avoids a
circular import with the upcoming Calendar tab), adds the PLANNED branch
(checked first), the filter option, summary count, and PLANNED-row actions
(Începe sesiunea / Discard).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Conflict soft-block — `useVehicleConflicts` hook + `ConflictDialog`

**Files:**
- Create: `jarvis/frontend/src/hooks/useVehicleConflicts.ts`
- Create: `jarvis/frontend/src/pages/FoiParcurs/ConflictDialog.tsx`

**Interfaces:**
- Consumes: `foiParcursApi.getVehicleConflicts` (Task 1).
- Produces: `useVehicleConflicts()` (imperative `check(vin, from, to, excludeId?)`) and `<ConflictDialog>` — consumed by Task 4 (plan/live-submit) and Task 5 (activate).

- [ ] **Step 1: Create the hook**

```ts
import { useState, useCallback } from 'react'
import { foiParcursApi } from '@/api/foiParcurs'
import type { VehicleConflict } from '@/types/foiParcurs'

/** Imperative VIN-conflict check for the "Plan a Driving Session" soft-block:
 *  call `check(vin, from, to, excludeId)` right before creating/planning/
 *  activating a TD. Resolves with the overlapping PLANNED/live sessions
 *  (empty array = clear). Never throws — a failed lookup is treated as "no
 *  conflicts" so it can never hard-block the actual submit. */
export function useVehicleConflicts() {
  const [checking, setChecking] = useState(false)

  const check = useCallback(
    async (vin: string, from: string, to: string, excludeId?: number): Promise<VehicleConflict[]> => {
      setChecking(true)
      try {
        const res = await foiParcursApi.getVehicleConflicts(vin, { from, to, exclude_id: excludeId })
        return res.conflicts ?? []
      } catch {
        return []
      } finally {
        setChecking(false)
      }
    },
    [],
  )

  return { checking, check }
}
```

- [ ] **Step 2: Create the dialog**

```tsx
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle } from 'lucide-react'
import type { VehicleConflict } from '@/types/foiParcurs'

const STATUS_LABEL: Record<string, string> = {
  PLANNED: 'Planificat',
  FILLED: 'În desfășurare',
  COMPLETED: 'Finalizat',
}

/** Soft-block warning shown when a VIN has overlapping PLANNED/live TD
 *  sessions in the chosen window. Never hard-blocks — "Continuă oricum"
 *  always lets the user proceed with the pending action. */
export function ConflictDialog({
  open,
  conflicts,
  onContinue,
  onCancel,
}: {
  open: boolean
  conflicts: VehicleConflict[]
  onContinue: () => void
  onCancel: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            Mașina este deja rezervată
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            {conflicts.length === 1
              ? 'Există o sesiune care se suprapune cu intervalul ales:'
              : `Există ${conflicts.length} sesiuni care se suprapun cu intervalul ales:`}
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {conflicts.map((c) => (
              <div key={c.id} className="rounded-md border p-2 text-sm space-y-0.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{c.client_name || '—'}</span>
                  <Badge variant="outline" className="text-xs">{STATUS_LABEL[c.status] ?? c.status}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">Consilier: {c.advisor_name || '—'}</p>
                <p className="text-xs text-muted-foreground">
                  {c.departure_datetime ? new Date(c.departure_datetime).toLocaleString('ro-RO') : '—'}
                  {' → '}
                  {c.return_datetime ? new Date(c.return_datetime).toLocaleString('ro-RO') : '—'}
                </p>
              </div>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>Anulează</Button>
          <Button onClick={onContinue}>Continuă oricum</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 3: Typecheck + lint**

Run: `cd jarvis/frontend && npx tsc -b`
Expected: exits 0.

Run: `cd jarvis/frontend && npx eslint src/hooks/useVehicleConflicts.ts src/pages/FoiParcurs/ConflictDialog.tsx`
Expected: 0 findings (or the pre-existing missing-config message).

- [ ] **Step 4: Manual verification**

Nothing renders yet (neither module is imported anywhere) — this task is code-inspection only: confirm `useVehicleConflicts().check(...)` resolves `[]` on a thrown error (read the `try/catch/finally`), and `ConflictDialog` compiles standalone. Wiring + visual verification happens in Tasks 4/5.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/hooks/useVehicleConflicts.ts jarvis/frontend/src/pages/FoiParcurs/ConflictDialog.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add reusable VIN-conflict check hook + soft-block dialog

useVehicleConflicts wraps GET /vehicles/{vin}/conflicts as an imperative,
never-throwing check; ConflictDialog renders the overlap list with a
"Continuă oricum" override. Not wired into any flow yet — consumed by the
Test Drive form's plan/submit/activate paths next.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Test Drive form — "Planifică (draft)" action + conflict check

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx`

**Interfaces:**
- Consumes: `foiParcursApi.planTestDrive` (Task 1), `useVehicleConflicts`/`ConflictDialog` (Task 3).
- Produces: a `PLANNED` draft contract on "Planifică (draft)" click, gated by the same soft-block dialog as the live "Trimite" submit.

- [ ] **Step 1: Imports**

Current (lines 1–56):

```ts
import { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { foiParcursApi } from '@/api/foiParcurs'
import { useAuthStore } from '@/stores/authStore'
import { cn } from '@/lib/utils'
import {
  usesFuelTank,
  usesBattery,
  type FuelGaugeLevel,
  type CrmClient,
  type FpVehicle,
  type FpVehicleInspection,
  type TestDriveFormPayload,
  type FoiContract,
} from '@/types/foiParcurs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Car,
  Search,
  IdCard,
  Fuel,
  ShieldCheck,
  PenLine,
  CheckCircle2,
  ArrowLeft,
  Plus,
  ClipboardCheck,
  Loader2,
  X,
  UserPlus,
  ChevronDown,
  FileText,
  AlertTriangle,
} from 'lucide-react'
import { CreateClientPanel, DriverLicenseSection } from './CreateClientPanel'
import {
  DamageReport,
  makeEmptyDamageState,
  toDamagePayload,
  type DamageState,
} from './testDriveDamage'

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))
```

Replace with:

```ts
import { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { foiParcursApi } from '@/api/foiParcurs'
import { useAuthStore } from '@/stores/authStore'
import { cn } from '@/lib/utils'
import { useVehicleConflicts } from '@/hooks/useVehicleConflicts'
import {
  usesFuelTank,
  usesBattery,
  type FuelGaugeLevel,
  type CrmClient,
  type FpVehicle,
  type FpVehicleInspection,
  type TestDriveFormPayload,
  type PlanTestDrivePayload,
  type VehicleConflict,
  type FoiContract,
} from '@/types/foiParcurs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Car,
  Search,
  IdCard,
  Fuel,
  ShieldCheck,
  PenLine,
  CheckCircle2,
  ArrowLeft,
  Plus,
  ClipboardCheck,
  Loader2,
  X,
  UserPlus,
  ChevronDown,
  FileText,
  AlertTriangle,
  CalendarPlus,
} from 'lucide-react'
import { CreateClientPanel, DriverLicenseSection } from './CreateClientPanel'
import {
  DamageReport,
  makeEmptyDamageState,
  toDamagePayload,
  type DamageState,
} from './testDriveDamage'
import { ConflictDialog } from './ConflictDialog'

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))
```

- [ ] **Step 2: Draft validity subset + conflict/plan state**

Current (lines 190–214):

```ts
  // ── Per-field validity (drives red highlight after a submit attempt) ──
  const odometerNum = odometerStart.trim() === '' ? NaN : Number(odometerStart)
  const estimatedNum = estimatedKm.trim() === '' ? NaN : Number(estimatedKm)
  const missing = {
    company: !companyId,
    vehicle: !selectedVehicle?.vin,
    client: !selectedClient,
    license: !driverLicensePhoto,
    departure: !departureDatetime,
    odometer: Number.isNaN(odometerNum) || odometerNum < 0,
    estimated: Number.isNaN(estimatedNum) || estimatedNum <= 0,
    fuel: !fuelGaugeStart,
    advisor: advisorName.trim() === '',
    clientSig: !clientSignature,
    gdpr: !gdprConsent,
  }
  const formValid = !Object.values(missing).some(Boolean)
  const err = (bad: boolean) => attempted && bad

  const damagedZoneCount = toDamagePayload(departureDamage).length

  const submitMutation = useMutation({
    mutationFn: (payload: TestDriveFormPayload) => foiParcursApi.submitTestDrive(payload),
    onSuccess: (data) => setSubmittedContract(data.contract),
  })
```

Replace with:

```ts
  // ── Per-field validity (drives red highlight after a submit attempt) ──
  const odometerNum = odometerStart.trim() === '' ? NaN : Number(odometerStart)
  const estimatedNum = estimatedKm.trim() === '' ? NaN : Number(estimatedKm)
  const missing = {
    company: !companyId,
    vehicle: !selectedVehicle?.vin,
    client: !selectedClient,
    license: !driverLicensePhoto,
    departure: !departureDatetime,
    odometer: Number.isNaN(odometerNum) || odometerNum < 0,
    estimated: Number.isNaN(estimatedNum) || estimatedNum <= 0,
    fuel: !fuelGaugeStart,
    advisor: advisorName.trim() === '',
    clientSig: !clientSignature,
    gdpr: !gdprConsent,
  }
  const formValid = !Object.values(missing).some(Boolean)
  // A PLANNED draft defers signature/GDPR/license to activation — mirrors the
  // backend's `required` list for status:'PLANNED' (no client_signature/gdpr_consent).
  const draftValid = !(
    missing.company || missing.vehicle || missing.client || missing.departure ||
    missing.odometer || missing.estimated || missing.fuel || missing.advisor
  )
  const err = (bad: boolean) => attempted && bad

  const damagedZoneCount = toDamagePayload(departureDamage).length

  const submitMutation = useMutation({
    mutationFn: (payload: TestDriveFormPayload) => foiParcursApi.submitTestDrive(payload),
    onSuccess: (data) => setSubmittedContract(data.contract),
  })
  const planMutation = useMutation({
    mutationFn: (payload: PlanTestDrivePayload) => foiParcursApi.planTestDrive(payload),
    onSuccess: (data) => setSubmittedContract(data.contract),
  })

  // ── VIN-conflict soft-block (shared by Trimite + Planifică) ──
  const { check: checkConflicts } = useVehicleConflicts()
  const [conflictList, setConflictList] = useState<VehicleConflict[]>([])
  const [showConflicts, setShowConflicts] = useState(false)
  const [pendingRun, setPendingRun] = useState<(() => void) | null>(null)

  /** Runs the VIN-conflict check for the chosen window; if clear, calls
   *  `run()` immediately, else stashes it and opens the soft-block dialog. */
  async function withConflictCheck(vin: string, run: () => void, excludeId?: number) {
    const conflicts = await checkConflicts(vin, departureDatetime, returnDatetime || departureDatetime, excludeId)
    if (conflicts.length) {
      setConflictList(conflicts)
      setPendingRun(() => run)
      setShowConflicts(true)
    } else {
      run()
    }
  }
```

- [ ] **Step 3: Replace `handleSubmit` with `buildBasePayload` + `handleSubmit` + `handlePlan`**

Current (lines 216–247):

```ts
  function handleSubmit() {
    if (submitMutation.isPending) return
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttempted(true)
      return
    }
    const damagePayload = toDamagePayload(departureDamage)
    const capacity = selectedVehicle.fuel_tank_capacity_liters ?? selectedVehicle.battery_capacity_kwh ?? undefined
    const payload: TestDriveFormPayload = {
      company_id: companyId!,
      vin: selectedVehicle.vin,
      registration_number: selectedVehicle.registration_number ?? '',
      client_id: Number(selectedClient.id),
      odometer_start: odometerNum,
      estimated_km: estimatedNum,
      fuel_gauge_start_level: fuelGaugeStart as FuelGaugeLevel,
      departure_datetime: departureDatetime,
      advisor_name: advisorName.trim(),
      client_signature: clientSignature,
      gdpr_consent: gdprConsent,
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(capacity != null ? { fuel_tank_capacity_liters: capacity } : {}),
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      ...(inspectionAcceptance ? { inspection_acceptance: inspectionAcceptance } : {}),
      ...(latestInspection?.id ? { inspection_id: latestInspection.id } : {}),
      ...(damagePayload.length ? { departure_damage: damagePayload } : {}),
      ...(driverLicensePhoto ? { driver_license_photo: driverLicensePhoto } : {}),
      ...(driverLicenseNumber.trim() ? { driver_license_number: driverLicenseNumber.trim() } : {}),
      ...(driverLicenseExpiry.trim() ? { driver_license_expiry: driverLicenseExpiry.trim() } : {}),
    }
    submitMutation.mutate(payload)
  }
```

Replace with:

```ts
  type BasePayload = Omit<TestDriveFormPayload, 'client_signature' | 'gdpr_consent'>

  function buildBasePayload(vehicle: FpVehicle, client: CrmClient): BasePayload {
    const damagePayload = toDamagePayload(departureDamage)
    const capacity = vehicle.fuel_tank_capacity_liters ?? vehicle.battery_capacity_kwh ?? undefined
    return {
      company_id: companyId!,
      vin: vehicle.vin,
      registration_number: vehicle.registration_number ?? '',
      client_id: Number(client.id),
      odometer_start: odometerNum,
      estimated_km: estimatedNum,
      fuel_gauge_start_level: fuelGaugeStart as FuelGaugeLevel,
      departure_datetime: departureDatetime,
      advisor_name: advisorName.trim(),
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(capacity != null ? { fuel_tank_capacity_liters: capacity } : {}),
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      ...(inspectionAcceptance ? { inspection_acceptance: inspectionAcceptance } : {}),
      ...(latestInspection?.id ? { inspection_id: latestInspection.id } : {}),
      ...(damagePayload.length ? { departure_damage: damagePayload } : {}),
      ...(driverLicensePhoto ? { driver_license_photo: driverLicensePhoto } : {}),
      ...(driverLicenseNumber.trim() ? { driver_license_number: driverLicenseNumber.trim() } : {}),
      ...(driverLicenseExpiry.trim() ? { driver_license_expiry: driverLicenseExpiry.trim() } : {}),
    }
  }

  function handleSubmit() {
    if (submitMutation.isPending) return
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttempted(true)
      return
    }
    const payload: TestDriveFormPayload = {
      ...buildBasePayload(selectedVehicle, selectedClient),
      client_signature: clientSignature,
      gdpr_consent: gdprConsent,
    }
    withConflictCheck(selectedVehicle.vin, () => submitMutation.mutate(payload))
  }

  function handlePlan() {
    if (planMutation.isPending) return
    if (!draftValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttempted(true)
      return
    }
    const payload: PlanTestDrivePayload = {
      ...buildBasePayload(selectedVehicle, selectedClient),
      status: 'PLANNED',
      ...(clientSignature ? { client_signature: clientSignature } : {}),
      ...(gdprConsent ? { gdpr_consent: gdprConsent } : {}),
    }
    withConflictCheck(selectedVehicle.vin, () => planMutation.mutate(payload))
  }
```

- [ ] **Step 4: `resetForm` — clear the new conflict state**

Current (lines 249–260):

```ts
  function resetForm() {
    setCompanyId(null); setVehicleId(null); setSelectedVehicle(null)
    setClientSearch(''); setSelectedClient(null); setShowManualCreate(false)
    setDriverLicensePhoto(null); setDriverLicenseNumber(''); setDriverLicenseExpiry('')
    setDepartureDatetime(localDatetimeValue(new Date()))
    setReturnDatetime(localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(''); setEstimatedKm(''); setFuelGaugeStart('')
    setClientSignature('')
    setShowDamage(false); setDepartureDamage(makeEmptyDamageState())
    setGdprConsent(false); setInspectionAcceptance(false)
    setSubmittedContract(null); setAttempted(false)
  }
```

Replace with:

```ts
  function resetForm() {
    setCompanyId(null); setVehicleId(null); setSelectedVehicle(null)
    setClientSearch(''); setSelectedClient(null); setShowManualCreate(false)
    setDriverLicensePhoto(null); setDriverLicenseNumber(''); setDriverLicenseExpiry('')
    setDepartureDatetime(localDatetimeValue(new Date()))
    setReturnDatetime(localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(''); setEstimatedKm(''); setFuelGaugeStart('')
    setClientSignature('')
    setShowDamage(false); setDepartureDamage(makeEmptyDamageState())
    setGdprConsent(false); setInspectionAcceptance(false)
    setSubmittedContract(null); setAttempted(false)
    setConflictList([]); setShowConflicts(false); setPendingRun(null)
  }
```

- [ ] **Step 5: Success screen — hide PDF links for a still-PLANNED contract**

Current (lines 262–291):

```tsx
  // ── Success Screen ──
  if (submittedContract) {
    return (
      <div className="max-w-lg mx-auto py-12 space-y-6">
        <Card>
          <CardContent className="pt-6 text-center space-y-4">
            <CheckCircle2 className="mx-auto h-16 w-16 text-green-500" />
            <h2 className="text-xl font-semibold">Test Drive Înregistrat</h2>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>Contract: <span className="font-medium text-foreground">{submittedContract.contract_id}</span></p>
              {submittedContract.vin && <p>VIN: <span className="font-medium text-foreground">{submittedContract.vin}</span></p>}
              {submittedContract.client_name && <p>Client: <span className="font-medium text-foreground">{submittedContract.client_name}</span></p>}
            </div>
            <div className="flex gap-2 justify-center flex-wrap">
              <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'legal')} target="_blank" rel="noopener">
                <Button variant="outline" size="sm"><FileText className="mr-1.5 h-3.5 w-3.5" />Download Legal PDF</Button>
              </a>
              <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'custom')} target="_blank" rel="noopener">
                <Button variant="outline" size="sm"><FileText className="mr-1.5 h-3.5 w-3.5" />Download Custom PDF</Button>
              </a>
            </div>
            <div className="flex gap-3 justify-center pt-2">
              <Button variant="outline" onClick={resetForm}><Plus className="h-4 w-4 mr-1" />Test Drive Nou</Button>
              <Button onClick={() => navigate('/app/foi-parcurs')}><ArrowLeft className="h-4 w-4 mr-1" />Înapoi la Driving Hub</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }
```

Replace with:

```tsx
  // ── Success Screen ──
  if (submittedContract) {
    const isPlanned = submittedContract.status === 'PLANNED'
    return (
      <div className="max-w-lg mx-auto py-12 space-y-6">
        <Card>
          <CardContent className="pt-6 text-center space-y-4">
            <CheckCircle2 className="mx-auto h-16 w-16 text-green-500" />
            <h2 className="text-xl font-semibold">{isPlanned ? 'Sesiune Planificată' : 'Test Drive Înregistrat'}</h2>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>Contract: <span className="font-medium text-foreground">{submittedContract.contract_id}</span></p>
              {submittedContract.vin && <p>VIN: <span className="font-medium text-foreground">{submittedContract.vin}</span></p>}
              {submittedContract.client_name && <p>Client: <span className="font-medium text-foreground">{submittedContract.client_name}</span></p>}
            </div>
            {isPlanned ? (
              <p className="text-xs text-muted-foreground">
                Draftul a fost salvat. Activează sesiunea din tab-ul <span className="font-medium">Sesiuni Driving</span> când clientul ajunge.
              </p>
            ) : (
              <div className="flex gap-2 justify-center flex-wrap">
                <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'legal')} target="_blank" rel="noopener">
                  <Button variant="outline" size="sm"><FileText className="mr-1.5 h-3.5 w-3.5" />Download Legal PDF</Button>
                </a>
                <a href={foiParcursApi.getContractPdfUrl(submittedContract.id, 'custom')} target="_blank" rel="noopener">
                  <Button variant="outline" size="sm"><FileText className="mr-1.5 h-3.5 w-3.5" />Download Custom PDF</Button>
                </a>
              </div>
            )}
            <div className="flex gap-3 justify-center pt-2">
              <Button variant="outline" onClick={resetForm}><Plus className="h-4 w-4 mr-1" />Test Drive Nou</Button>
              <Button onClick={() => navigate('/app/foi-parcurs')}><ArrowLeft className="h-4 w-4 mr-1" />Înapoi la Driving Hub</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }
```

- [ ] **Step 6: Submit area — "Planifică (draft)" button + `ConflictDialog`**

Current (lines 561–573, the tail of the component's JSX):

```tsx
      {/* ── Submit ── */}
      {submitMutation.isError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          Eroare la trimitere. Vă rugăm încercați din nou.
        </div>
      )}
      <Button className={cn('w-full', attempted && !formValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleSubmit} disabled={submitMutation.isPending}>
        {submitMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se trimite...</> : 'Trimite'}
      </Button>
      {attempted && !formValid && !submitMutation.isPending && (
        <p className="text-xs text-destructive text-center">Completează câmpurile marcate cu roșu pentru a trimite.</p>
      )}
    </div>
  )
}
```

Replace with:

```tsx
      {/* ── Submit ── */}
      {(submitMutation.isError || planMutation.isError) && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          Eroare la trimitere. Vă rugăm încercați din nou.
        </div>
      )}
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          className="flex-1"
          size="lg"
          onClick={handlePlan}
          disabled={planMutation.isPending || submitMutation.isPending}
        >
          {planMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se salvează...</> : <><CalendarPlus className="h-4 w-4 mr-2" />Planifică (draft)</>}
        </Button>
        <Button className={cn('flex-1', attempted && !formValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleSubmit} disabled={submitMutation.isPending || planMutation.isPending}>
          {submitMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se trimite...</> : 'Trimite'}
        </Button>
      </div>
      {attempted && !formValid && !submitMutation.isPending && (
        <p className="text-xs text-destructive text-center">Completează câmpurile marcate cu roșu pentru a trimite.</p>
      )}
      <ConflictDialog
        open={showConflicts}
        conflicts={conflictList}
        onCancel={() => { setShowConflicts(false); setPendingRun(null) }}
        onContinue={() => {
          setShowConflicts(false)
          pendingRun?.()
          setPendingRun(null)
        }}
      />
    </div>
  )
}
```

- [ ] **Step 7: Typecheck + lint**

Run: `cd jarvis/frontend && npx tsc -b`
Expected: exits 0.

Run: `cd jarvis/frontend && npx eslint src/pages/FoiParcurs/TestDriveForm.tsx`
Expected: 0 findings (or the pre-existing missing-config message).

- [ ] **Step 8: Manual verification**

`npm run dev`, open `/app/foi-parcurs/test-drive`. Fill company/vehicle/client/departure/odometer/estimated-km/fuel/advisor (skip signature/GDPR/license) → "Planifică (draft)" is enabled and, on click, creates a `PLANNED` contract and shows "Sesiune Planificată" (no PDF buttons). Fill the rest (signature + GDPR) → "Trimite" still creates a live `FILLED` contract with PDFs, unchanged from before. If a second draft/live TD is created for the same VIN with an overlapping window, the `ConflictDialog` appears on either button before the mutation fires; "Continuă oricum" proceeds, "Anulează" aborts without submitting.

- [ ] **Step 9: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add Planifică (draft) action + VIN-conflict soft-block

"Planifică (draft)" posts status:'PLANNED' via the new draft-validity subset
(no signature/GDPR/license required, matching the backend's relaxed
`required` list). Both Planifică and the existing Trimite now run the
VIN-conflict check first and show ConflictDialog on overlap; live-submit
behavior is otherwise unchanged.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Test Drive form — Activate flow (`?activate={id}`)

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx`

**Interfaces:**
- Consumes: `foiParcursApi.getTestDrive`, `foiParcursApi.activateTestDrive` (Task 1), `fromDamagePayload` (existing helper in `testDriveDamage.tsx`), `withConflictCheck` (Task 4).
- Produces: navigating to `/app/foi-parcurs/test-drive?activate={id}` (from Task 2's "Începe sesiunea" button and Task 6's Calendar dialog) reopens this form pre-filled from the `PLANNED` contract; submitting calls `PUT .../activate` instead of `POST .../test-drive`.

- [ ] **Step 1: Imports — `useSearchParams`, `PlayCircle`, `ActivateTestDrivePayload`, `fromDamagePayload`**

Current (post-Task-4) import lines:

```ts
import { useNavigate } from 'react-router-dom'
```

Replace with:

```ts
import { useNavigate, useSearchParams } from 'react-router-dom'
```

Current (post-Task-4) type import block:

```ts
import {
  usesFuelTank,
  usesBattery,
  type FuelGaugeLevel,
  type CrmClient,
  type FpVehicle,
  type FpVehicleInspection,
  type TestDriveFormPayload,
  type PlanTestDrivePayload,
  type VehicleConflict,
  type FoiContract,
} from '@/types/foiParcurs'
```

Replace with:

```ts
import {
  usesFuelTank,
  usesBattery,
  type FuelGaugeLevel,
  type CrmClient,
  type FpVehicle,
  type FpVehicleInspection,
  type TestDriveFormPayload,
  type PlanTestDrivePayload,
  type ActivateTestDrivePayload,
  type VehicleConflict,
  type FoiContract,
} from '@/types/foiParcurs'
```

Current lucide-react block's last entry (post-Task-4):

```ts
  AlertTriangle,
  CalendarPlus,
} from 'lucide-react'
```

Replace with:

```ts
  AlertTriangle,
  CalendarPlus,
  PlayCircle,
} from 'lucide-react'
```

Current `testDriveDamage` import:

```ts
import {
  DamageReport,
  makeEmptyDamageState,
  toDamagePayload,
  type DamageState,
} from './testDriveDamage'
```

Replace with:

```ts
import {
  DamageReport,
  makeEmptyDamageState,
  toDamagePayload,
  fromDamagePayload,
  type DamageState,
} from './testDriveDamage'
```

- [ ] **Step 2: Activation mode state + draft fetch + prefill**

Current (lines 84–90, the top of the component):

```ts
export default function TestDriveForm() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  // Company & vehicle
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [vehicleId, setVehicleId] = useState<number | null>(null)
  const [selectedVehicle, setSelectedVehicle] = useState<FpVehicle | null>(null)
```

Replace with:

```ts
export default function TestDriveForm() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  // ── Activation mode — reopens this form pre-filled from a PLANNED draft ──
  const [searchParams] = useSearchParams()
  const activateId = searchParams.get('activate') ? Number(searchParams.get('activate')) : null
  const isActivating = activateId != null

  // Company & vehicle
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [vehicleId, setVehicleId] = useState<number | null>(null)
  const [selectedVehicle, setSelectedVehicle] = useState<FpVehicle | null>(null)
```

Current (lines 145–150, the vehicles query — used as the anchor for the new draft query + prefill effects, inserted right after it):

```ts
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(true),
  })
  const allVehicles = vehiclesData?.vehicles ?? []
  const vehiclesForCompany = useMemo(
    () => (companyId ? allVehicles.filter((v) => v.company_id === companyId) : []),
    [allVehicles, companyId],
  )
```

Replace with:

```ts
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(true),
  })
  const allVehicles = vehiclesData?.vehicles ?? []
  const vehiclesForCompany = useMemo(
    () => (companyId ? allVehicles.filter((v) => v.company_id === companyId) : []),
    [allVehicles, companyId],
  )

  // ── Load + prefill the PLANNED draft being activated ──
  const { data: draftData, isLoading: loadingDraft } = useQuery({
    queryKey: ['fp-test-drive', activateId],
    queryFn: () => foiParcursApi.getTestDrive(activateId!),
    enabled: activateId != null,
  })

  useEffect(() => {
    const c = draftData?.contract
    if (!c || c.status !== 'PLANNED') return
    setCompanyId(c.company_id)
    setDepartureDatetime(c.departure_datetime ? c.departure_datetime.slice(0, 16) : localDatetimeValue(new Date()))
    setReturnDatetime(c.return_datetime ? c.return_datetime.slice(0, 16) : localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(String(c.km_start ?? ''))
    setEstimatedKm(String(c.distance_km ?? ''))
    setFuelGaugeStart((c.fuel_gauge_start_level as FuelGaugeLevel) || '')
    setAdvisorName(c.advisor_name || '')
    setDepartureDamage(fromDamagePayload(c.departure_damage))
    if (c.client_id && c.client_name) {
      setSelectedClient({ id: c.client_id, display_name: c.client_name, phone: c.client_phone ?? null })
    }
  }, [draftData]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const c = draftData?.contract
    if (!c || c.status !== 'PLANNED' || !allVehicles.length) return
    const v = allVehicles.find((x) => x.vin === c.vin)
    if (v) { setVehicleId(v.id); setSelectedVehicle(v) }
  }, [draftData, allVehicles])
```

- [ ] **Step 3: `handleActivate` + `activateMutation`**

Current (post-Task-4, right after `handlePlan`'s closing brace):

```ts
  function handlePlan() {
    if (planMutation.isPending) return
    if (!draftValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttempted(true)
      return
    }
    const payload: PlanTestDrivePayload = {
      ...buildBasePayload(selectedVehicle, selectedClient),
      status: 'PLANNED',
      ...(clientSignature ? { client_signature: clientSignature } : {}),
      ...(gdprConsent ? { gdpr_consent: gdprConsent } : {}),
    }
    withConflictCheck(selectedVehicle.vin, () => planMutation.mutate(payload))
  }
```

Add immediately after it:

```ts

  const activateMutation = useMutation({
    mutationFn: (payload: ActivateTestDrivePayload) => foiParcursApi.activateTestDrive(activateId!, payload),
    onSuccess: (data) => setSubmittedContract(data.contract),
  })

  function handleActivate() {
    if (activateMutation.isPending || activateId == null) return
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelGaugeStart) {
      setAttempted(true)
      return
    }
    const damagePayload = toDamagePayload(departureDamage)
    const capacity = selectedVehicle.fuel_tank_capacity_liters ?? selectedVehicle.battery_capacity_kwh ?? undefined
    const payload: ActivateTestDrivePayload = {
      client_signature: clientSignature,
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      gdpr_consent: gdprConsent,
      odometer_start: odometerNum,
      fuel_gauge_start_level: fuelGaugeStart as FuelGaugeLevel,
      ...(capacity != null ? { fuel_tank_capacity_liters: capacity } : {}),
      departure_datetime: departureDatetime,
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(damagePayload.length ? { departure_damage: damagePayload } : {}),
    }
    withConflictCheck(selectedVehicle.vin, () => activateMutation.mutate(payload), activateId)
  }
```

- [ ] **Step 4: `resetForm` — leave activation mode on reset**

Current (post-Task-4):

```ts
  function resetForm() {
    setCompanyId(null); setVehicleId(null); setSelectedVehicle(null)
    setClientSearch(''); setSelectedClient(null); setShowManualCreate(false)
    setDriverLicensePhoto(null); setDriverLicenseNumber(''); setDriverLicenseExpiry('')
    setDepartureDatetime(localDatetimeValue(new Date()))
    setReturnDatetime(localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(''); setEstimatedKm(''); setFuelGaugeStart('')
    setClientSignature('')
    setShowDamage(false); setDepartureDamage(makeEmptyDamageState())
    setGdprConsent(false); setInspectionAcceptance(false)
    setSubmittedContract(null); setAttempted(false)
    setConflictList([]); setShowConflicts(false); setPendingRun(null)
  }
```

Replace with:

```ts
  function resetForm() {
    setCompanyId(null); setVehicleId(null); setSelectedVehicle(null)
    setClientSearch(''); setSelectedClient(null); setShowManualCreate(false)
    setDriverLicensePhoto(null); setDriverLicenseNumber(''); setDriverLicenseExpiry('')
    setDepartureDatetime(localDatetimeValue(new Date()))
    setReturnDatetime(localDatetimeValue(new Date(Date.now() + 60 * 60 * 1000)))
    setOdometerStart(''); setEstimatedKm(''); setFuelGaugeStart('')
    setClientSignature('')
    setShowDamage(false); setDepartureDamage(makeEmptyDamageState())
    setGdprConsent(false); setInspectionAcceptance(false)
    setSubmittedContract(null); setAttempted(false)
    setConflictList([]); setShowConflicts(false); setPendingRun(null)
    if (isActivating) navigate('/app/foi-parcurs/test-drive', { replace: true })
  }
```

- [ ] **Step 5: Header — activation-mode title**

Current (post-Task-4, header block):

```tsx
        <div>
          <h1 className="text-lg font-semibold">Test Drive Nou</h1>
          <p className="text-sm text-muted-foreground">Completați datele pentru test drive</p>
        </div>
```

Replace with:

```tsx
        <div>
          <h1 className="text-lg font-semibold">{isActivating ? 'Activează Test Drive' : 'Test Drive Nou'}</h1>
          <p className="text-sm text-muted-foreground">
            {isActivating ? 'Confirmă/ajustează datele și capturează semnătura clientului' : 'Completați datele pentru test drive'}
          </p>
        </div>
```

- [ ] **Step 6: Submit area — branch on `isActivating`**

Current (from Task 4, Step 6's result):

```tsx
      {/* ── Submit ── */}
      {(submitMutation.isError || planMutation.isError) && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          Eroare la trimitere. Vă rugăm încercați din nou.
        </div>
      )}
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          className="flex-1"
          size="lg"
          onClick={handlePlan}
          disabled={planMutation.isPending || submitMutation.isPending}
        >
          {planMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se salvează...</> : <><CalendarPlus className="h-4 w-4 mr-2" />Planifică (draft)</>}
        </Button>
        <Button className={cn('flex-1', attempted && !formValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleSubmit} disabled={submitMutation.isPending || planMutation.isPending}>
          {submitMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se trimite...</> : 'Trimite'}
        </Button>
      </div>
      {attempted && !formValid && !submitMutation.isPending && (
        <p className="text-xs text-destructive text-center">Completează câmpurile marcate cu roșu pentru a trimite.</p>
      )}
```

Replace with:

```tsx
      {/* ── Submit ── */}
      {(submitMutation.isError || planMutation.isError || activateMutation.isError) && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          Eroare la trimitere. Vă rugăm încercați din nou.
        </div>
      )}
      {isActivating ? (
        <Button className={cn('w-full', attempted && !formValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleActivate} disabled={activateMutation.isPending || loadingDraft}>
          {activateMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se activează...</> : <><PlayCircle className="h-4 w-4 mr-2" />Începe sesiunea</>}
        </Button>
      ) : (
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="flex-1"
            size="lg"
            onClick={handlePlan}
            disabled={planMutation.isPending || submitMutation.isPending}
          >
            {planMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se salvează...</> : <><CalendarPlus className="h-4 w-4 mr-2" />Planifică (draft)</>}
          </Button>
          <Button className={cn('flex-1', attempted && !formValid && 'bg-destructive hover:bg-destructive/90')} size="lg" onClick={handleSubmit} disabled={submitMutation.isPending || planMutation.isPending}>
            {submitMutation.isPending ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Se trimite...</> : 'Trimite'}
          </Button>
        </div>
      )}
      {attempted && !formValid && !submitMutation.isPending && !activateMutation.isPending && (
        <p className="text-xs text-destructive text-center">Completează câmpurile marcate cu roșu pentru a trimite.</p>
      )}
```

- [ ] **Step 7: Typecheck + lint**

Run: `cd jarvis/frontend && npx tsc -b`
Expected: exits 0.

Run: `cd jarvis/frontend && npx eslint src/pages/FoiParcurs/TestDriveForm.tsx`
Expected: 0 findings (or the pre-existing missing-config message).

- [ ] **Step 8: Manual verification**

`npm run dev`. From Sesiuni Driving, click "Începe sesiunea" on a `PLANNED` row (or navigate to `/app/foi-parcurs/test-drive?activate=<id>` directly) → the form loads with company/vehicle/client/departure/odometer/estimated-km/fuel/advisor/damage pre-filled from the draft, title reads "Activează Test Drive", and only one button, "Începe sesiunea", is shown. Missing only the client signature → clicking is blocked (red highlight); sign → click activates, contract flips to `FILLED`, PDF buttons now appear (existing non-`isPlanned` branch), and the row disappears from the `PLANNED` filter in Sesiuni Driving. Trying to activate the same draft twice (e.g. two tabs) surfaces the backend's 409 as the existing generic error banner.

- [ ] **Step 9: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add PLANNED-draft activation flow to the Test Drive form

?activate={id} reopens the form pre-filled from the draft (company, vehicle,
client, trip fields, damage), requires the client signature, and calls
PUT /test-drive/{id}/activate instead of the create endpoint — same
VIN-conflict soft-block as create/plan.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Calendar tab — from-scratch month grid

**Files:**
- Create: `jarvis/frontend/src/pages/FoiParcurs/CalendarTab.tsx`
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx`

**Interfaces:**
- Consumes: `foiParcursApi.getContracts`, `foiParcursApi.getVehicles`, `foiParcursApi.discardTestDrive` (Task 1), `sessionStatus` (Task 2).
- Produces: a "Calendar" tab in Foi de Parcurs, registered in `index.tsx`.

- [ ] **Step 1: Create `CalendarTab.tsx`**

```tsx
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, PlayCircle, XIcon, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FoiContract } from '@/types/foiParcurs'
import { sessionStatus } from './sessionStatus'

const WEEKDAY_LABELS = ['Lun', 'Mar', 'Mie', 'Joi', 'Vin', 'Sâm', 'Dum']

function dayKey(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 6-week (42-day) Monday-first grid covering `cursor`'s month, padded with
 *  leading/trailing days from the adjacent months so every week row is full.
 *  Plain Date math — no calendar library is installed in this project. */
function monthGrid(cursor: Date): Date[] {
  const year = cursor.getFullYear()
  const month = cursor.getMonth()
  const firstOfMonth = new Date(year, month, 1)
  const startOffset = (firstOfMonth.getDay() + 6) % 7 // Mon=0 .. Sun=6
  const gridStart = new Date(year, month, 1 - startOffset)
  return Array.from({ length: 42 }, (_, i) => new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i))
}

/** Month-grid calendar of planned/live/finished TD sessions, keyed on
 *  departure_datetime. Data reuses the same ['foi-contracts-all', companyId]
 *  query as SessionsTab (per_page:1000, filtered client-side — the backend's
 *  GET /contracts has no date_from/date_to/route_type filter), so switching
 *  between Sesiuni Driving and Calendar doesn't refetch. */
export function CalendarTab({ companyId, brand }: { companyId: number; brand: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [cursor, setCursor] = useState(() => new Date())
  const [selected, setSelected] = useState<FoiContract | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['foi-contracts-all', companyId],
    queryFn: () =>
      foiParcursApi.getContracts({ company_id: companyId || undefined, per_page: 1000, sort_by: 'created_at', sort_dir: 'DESC' }),
    staleTime: 30_000,
  })
  const { data: vehiclesData } = useQuery({
    queryKey: ['fp-vehicles'],
    queryFn: () => foiParcursApi.getVehicles(),
    staleTime: 30_000,
  })
  const vehiclesList = vehiclesData?.vehicles ?? []
  const vinBrand = new Map(vehiclesList.map((v) => [v.vin, v.brand]))
  const vinVehicle = new Map(vehiclesList.map((v) => [v.vin, v]))

  const discardMutation = useMutation({
    mutationFn: (id: number) => foiParcursApi.discardTestDrive(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      setSelected(null)
    },
  })

  const tdContracts = (data?.contracts ?? []).filter(
    (c) => c.route_type === 'TD' && c.departure_datetime && (!brand || vinBrand.get(c.vin) === brand),
  )

  const byDay = useMemo(() => {
    const map = new Map<string, FoiContract[]>()
    for (const c of tdContracts) {
      const key = dayKey(new Date(c.departure_datetime!))
      const list = map.get(key) ?? []
      list.push(c)
      map.set(key, list)
    }
    return map
  }, [tdContracts])

  const grid = useMemo(() => monthGrid(cursor), [cursor])
  const currentMonth = cursor.getMonth()
  const todayKey = dayKey(new Date())
  const monthLabel = cursor.toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setCursor(new Date())}>Azi</Button>
          <Button variant="outline" size="icon" onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <h3 className="text-base font-semibold capitalize ml-2">{monthLabel}</h3>
        </div>
        {isLoading && <span className="text-xs text-muted-foreground">Se încarcă...</span>}
      </div>

      <Card className="overflow-hidden">
        <div className="grid grid-cols-7 border-b bg-muted/40">
          {WEEKDAY_LABELS.map((d) => (
            <div key={d} className="px-2 py-1.5 text-center text-xs font-medium text-muted-foreground">{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {grid.map((d) => {
            const key = dayKey(d)
            const inMonth = d.getMonth() === currentMonth
            const isToday = key === todayKey
            const events = byDay.get(key) ?? []
            return (
              <div
                key={key}
                className={cn('min-h-[104px] border-b border-r p-1.5 space-y-1', !inMonth && 'bg-muted/20 text-muted-foreground')}
              >
                <div className={cn('text-xs font-medium', isToday && 'inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground')}>
                  {d.getDate()}
                </div>
                <div className="space-y-1">
                  {events.slice(0, 3).map((c) => {
                    const ss = sessionStatus(c)
                    const v = vinVehicle.get(c.vin)
                    const carLabel = v ? [v.brand || v.mark, v.model].filter(Boolean).join(' ') : c.vin.slice(0, 8)
                    const time = c.departure_datetime
                      ? new Date(c.departure_datetime).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
                      : ''
                    return (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => setSelected(c)}
                        className={cn('w-full truncate rounded px-1.5 py-0.5 text-left text-[11px] font-medium text-white hover:opacity-90', ss.badgeClass)}
                        title={`${time} ${carLabel} — ${c.client_name || '—'}`}
                      >
                        {time} {carLabel}
                      </button>
                    )
                  })}
                  {events.length > 3 && (
                    <div className="text-[10px] text-muted-foreground px-1.5">+{events.length - 3} altele</div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {selected && (
        <Dialog open onOpenChange={(o) => { if (!o) setSelected(null) }}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                Detalii sesiune
                <Badge className={cn('text-xs', sessionStatus(selected).badgeClass)}>{sessionStatus(selected).label}</Badge>
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-1.5 text-sm">
              <p><span className="text-muted-foreground">Client:</span> {selected.client_name || '—'}</p>
              <p><span className="text-muted-foreground">Consilier:</span> {selected.advisor_name || '—'}</p>
              <p>
                <span className="text-muted-foreground">Mașină:</span>{' '}
                {(() => {
                  const v = vinVehicle.get(selected.vin)
                  return v ? `${[v.brand || v.mark, v.model].filter(Boolean).join(' ')} — ${v.registration_number || v.vin}` : selected.vin
                })()}
              </p>
              <p><span className="text-muted-foreground">Plecare:</span> {selected.departure_datetime ? new Date(selected.departure_datetime).toLocaleString('ro-RO') : '—'}</p>
              <p><span className="text-muted-foreground">Retur:</span> {selected.return_datetime ? new Date(selected.return_datetime).toLocaleString('ro-RO') : '—'}</p>
            </div>
            <DialogFooter className="flex-col sm:flex-row gap-2">
              {selected.status === 'PLANNED' && (
                <>
                  <Button
                    variant="outline"
                    className="w-full sm:w-auto"
                    onClick={() => {
                      if (confirm('Renunți la această sesiune planificată? Acțiunea nu poate fi anulată.')) {
                        discardMutation.mutate(selected.id)
                      }
                    }}
                    disabled={discardMutation.isPending}
                  >
                    <XIcon className="mr-1.5 h-4 w-4" />Discard
                  </Button>
                  <Button className="w-full sm:w-auto" onClick={() => navigate(`/app/foi-parcurs/test-drive?activate=${selected.id}`)}>
                    <PlayCircle className="mr-1.5 h-4 w-4" />Începe sesiunea
                  </Button>
                </>
              )}
              {selected.status !== 'PLANNED' && selected.status !== 'PENDING' && (
                <a href={foiParcursApi.getContractPdfUrl(selected.id, 'legal')} target="_blank" rel="noopener" className="w-full sm:w-auto">
                  <Button variant="outline" className="w-full"><FileText className="mr-1.5 h-4 w-4" />PDF</Button>
                </a>
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Register the tab in `index.tsx`**

Current relative import (post-Task-2):

```ts
import { VehicleOdometerHistory } from './VehicleOdometerHistory'
import { sessionStatus, type SessionStatusKey } from './sessionStatus'
```

Replace with:

```ts
import { VehicleOdometerHistory } from './VehicleOdometerHistory'
import { sessionStatus, type SessionStatusKey } from './sessionStatus'
import { CalendarTab } from './CalendarTab'
```

Current (line 104):

```ts
  const [activeTab, setActiveTab] = usePersistentState<'contracts' | 'parcurs' | 'stock' | 'settings'>('fp.activeTab', 'stock')
```

Replace with:

```ts
  const [activeTab, setActiveTab] = usePersistentState<'contracts' | 'parcurs' | 'stock' | 'calendar' | 'settings'>('fp.activeTab', 'stock')
```

Current (lines 175–187):

```tsx
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'contracts' | 'parcurs' | 'stock' | 'settings')}>
        <TabsList>
          <TabsTrigger value="stock">Driving Park</TabsTrigger>
          <TabsTrigger value="contracts">Contracts</TabsTrigger>
          <TabsTrigger value="parcurs">Sesiuni Driving</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>
      </Tabs>

      {activeTab === 'contracts' && <ContractsTab companyId={companyId} brand={brand} />}
      {activeTab === 'parcurs' && <SessionsTab companyId={companyId} brand={brand} />}
      {activeTab === 'stock' && <StockTab companyId={companyId} brand={brand} />}
      {activeTab === 'settings' && <SettingsTab />}
```

Replace with:

```tsx
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'contracts' | 'parcurs' | 'stock' | 'calendar' | 'settings')}>
        <TabsList>
          <TabsTrigger value="stock">Driving Park</TabsTrigger>
          <TabsTrigger value="contracts">Contracts</TabsTrigger>
          <TabsTrigger value="parcurs">Sesiuni Driving</TabsTrigger>
          <TabsTrigger value="calendar">Calendar</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>
      </Tabs>

      {activeTab === 'contracts' && <ContractsTab companyId={companyId} brand={brand} />}
      {activeTab === 'parcurs' && <SessionsTab companyId={companyId} brand={brand} />}
      {activeTab === 'stock' && <StockTab companyId={companyId} brand={brand} />}
      {activeTab === 'calendar' && <CalendarTab companyId={companyId} brand={brand} />}
      {activeTab === 'settings' && <SettingsTab />}
```

- [ ] **Step 3: Typecheck + lint**

Run: `cd jarvis/frontend && npx tsc -b`
Expected: exits 0.

Run: `cd jarvis/frontend && npx eslint src/pages/FoiParcurs/CalendarTab.tsx src/pages/FoiParcurs/index.tsx`
Expected: 0 findings (or the pre-existing missing-config message).

- [ ] **Step 4: Manual verification**

`npm run dev`, open `/app/foi-parcurs`, click the new "Calendar" tab. Confirm: a 6-week month grid renders with RO weekday headers (Lun…Dum), today is circled, TD sessions with a `departure_datetime` in the visible month appear as colored chips (color matches their Sesiuni Driving badge — indigo for Planificat, blue/red/green for driving/intarziat/finalizat), clicking a chip opens the detail dialog, and for a `PLANNED` session the dialog's "Începe sesiunea" navigates to the activation form (Task 5) while "Discard" removes it after confirm. Prev/Next/Azi navigate months without a full page reload.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/CalendarTab.tsx jarvis/frontend/src/pages/FoiParcurs/index.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add Calendar tab to Foi de Parcurs (from-scratch month grid)

No calendar library is installed in this project, so the month view is
plain Date math + CSS grid. Reuses the same ['foi-contracts-all', companyId]
query as Sesiuni Driving (the contracts list endpoint has no server-side
date filter), colors events by sessionStatus, and click-to-detail opens a
dialog with Activate/Discard for PLANNED sessions.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage (Phase 2 items from the design spec):**
- 5-state `sessionStatus` (add `planificat`, checked first) → Task 2. ✔
- Filter dropdown / summary counts / row tint for the new state → Task 2. ✔
- "Planifică (draft)" action on the TD create form → Task 4. ✔
- PLANNED row actions (Începe sesiunea / Discard; "Editează" folds into Începe sesiunea — no separate edit-only API in Phase 1, documented in Task 2 Step 7). → Task 2 (list actions) + Task 5 (the activation form itself). ✔
- Activate flow: reopen prefilled → confirm/adjust → capture client signature → `PUT .../activate` → Task 5. ✔
- Discard (PLANNED-only, confirm) → Task 2 (Sesiuni Driving row) + Task 6 (Calendar dialog). ✔
- Calendar tab: month grid keyed on `departure_datetime`, car/client/time/consilier, colored by status, click → detail/activate → Task 6. ✔
- Conflict soft-block on planning/starting a TD, dialog with "Continuă oricum" → Task 3 (component) wired in Task 4 (plan/live-submit) and Task 5 (activate). ✔
- Existing live TD/return flow unchanged → Task 4 only *adds* `handlePlan`/`buildBasePayload`; `handleSubmit`'s payload and `submitMutation` are untouched in shape/behavior. ✔

**Divergences from the design doc, and why (per the task brief: "follow current code"):**
- Conflicts response has no `td_status` (design doc's response shape includes it; the real `find_conflicts()` SQL doesn't select it) — `VehicleConflict` matches the real SQL.
- `GET /contracts` has no `date_from`/`date_to`/`route_type` filter (design doc's Phase 1 "Calendar range" section assumed it would) — `CalendarTab` filters client-side from the same full-list query `SessionsTab` already uses, per the same design doc's fallback ("No new endpoint required unless a lighter payload is wanted later").
- "Editează" (3rd PLANNED action in the design doc) has no backing route in Phase 1 — folded into "Începe sesiunea", which already reopens the form for "confirm/adjust" before activating.
- General-conditions acceptance (newly required conditionally by the deployed backend on both live-submit and activate) is not wired into any web UI — pre-existing gap on live-submit, out of scope here, called out in Global Constraints and not silently "fixed" as part of this plan.

**Placeholder scan:** No "TBD"/"add error handling"/"similar to above" anywhere in this plan — every task shows the complete replacement code, not a diff summary. Full new files (`sessionStatus.ts`, `useVehicleConflicts.ts`, `ConflictDialog.tsx`, `CalendarTab.tsx`) are shown whole.

**Type/name consistency across tasks:**
- `PlanTestDrivePayload`, `ActivateTestDrivePayload`, `VehicleConflict` (Task 1) are the exact names imported in Tasks 3–6.
- `sessionStatus` / `SessionStatusKey` (Task 2, in `sessionStatus.ts`) are imported identically by `index.tsx` (re-export) and `CalendarTab.tsx` (Task 6) — no duplicate definitions.
- `useVehicleConflicts` / `ConflictDialog` (Task 3) are imported with the same names and prop shapes in Task 4 (`TestDriveForm.tsx`, both `handleSubmit`/`handlePlan`) and Task 5 (`handleActivate`, via the same `withConflictCheck` helper — no second copy).
- Route `/app/foi-parcurs/test-drive?activate={id}` is the single navigation target used by Task 2's "Începe sesiunea" button, Task 6's dialog "Începe sesiunea" button, and is the query param Task 5's `TestDriveForm.tsx` reads — spelled identically (`?activate=`) in all three places.
- `foiParcursApi.discardTestDrive(id)` is called with the same signature from both Task 2 (`SessionsTab`) and Task 6 (`CalendarTab`) — no divergence in the mutation shape.

**Risks / things the controlling agent should verify before/while executing:**
1. **ESLint has no config in this checkout** (`npx eslint <file>` currently fails with "couldn't find eslint.config.(js|mjs|cjs)", verified independently of this plan). Every task's lint step will surface that message rather than a clean pass — this is expected and `tsc -b` is the real gate, not a regression to chase down.
2. **General-conditions acceptance is unhandled UI-side** (see Divergences above) — if a company/brand has `general_conditions` text configured in dealer config, both the pre-existing live "Trimite" *and* the new Task 5 "Începe sesiunea" activation will 400 from the backend. This was already true for live-submit before this plan; Task 5 inherits it rather than introduces it, but it's worth flagging to product/backend before rollout if any dealer actually has general conditions configured today.
3. **Task 5's client-side re-derivation of `missing`/`formValid` for activation** reuses the *same* validity object as the live-submit path (including `license`/`clientSig`/`gdpr`), which is stricter than the backend's actual activate requirement (only `client_signature`). This is a deliberate simplification (safer default, consistent UX with live-submit) — flag if product wants activation to allow skipping the license re-check.
4. **Calendar tab caps at 3 visible events/day** (`events.slice(0, 3)`, "+N altele" for the rest) with no expand-to-see-all — acceptable for a first cut per the design's "list-grouped/simple" bar, but verify with an actual busy VIN/company before shipping if any dealer regularly books 4+ TDs/day.
