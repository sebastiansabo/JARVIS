# Hub Field Sales ("Teren") Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a KAM daily-driver Field Sales panel to the JARVIS web Hub, mirroring the mobile "Vizite" UX and reusing the existing `/api/field-sales/*` backend + web `VisitDetailDialog`.

**Architecture:** A new self-contained `HubFieldSalesPanel` renders inside the Hub's in-page module area (same pattern as `HubDrivingPanel`), listing today's visits with check-in / finalize actions and an overlay sheet hosting Add-visit, Visit-detail, Note-capture, and a ported 360° client card. All data goes through thin wrappers added to the existing `fieldSalesApi` client — no backend, DB, or migration changes.

**Tech Stack:** React 18 + TypeScript, TanStack React Query, Tailwind, Radix UI, lucide-react, Vitest + @testing-library/react. Build/test from `jarvis/frontend`.

## Global Constraints

- Web frontend only. No backend, DB, or migration changes. All routes already exist.
- Work on the `dev` branch. Do not push to `staging`/`main`.
- Mobile-first / iOS sizing: inputs and primary buttons `h-11 rounded-xl text-base`; cards `rounded-2xl`. Match existing `HubDrivingPanel` styling.
- All user-facing copy in Romanian (no diacritics is acceptable — mirror existing field-sales strings).
- Reuse `VisitDetailDialog` as-is for the visit detail view; only additive edits allowed to it (a new optional prop + one button).
- Error surface: extract backend message via the `ApiError` shape `err?.data?.error` (Romanian string); show inline.
- Geolocation on check-in is best-effort and MUST NOT block: on error/denial/absence, call `checkin` with no coordinates.
- Allowed visit types: `fleet_review, renewal_discussion, test_drive_followup, service_followup, new_acquisition, contract_negotiation, prospecting, general`.
- Allowed outcomes: `completed, no_show, rescheduled, partial`.
- Backend behavior to respect: `POST /api/field-sales/visits/:id/note` saves the note, AI-structures it, **and completes the visit** (outcome defaults to `completed`). `POST .../checkout` completes without a note.
- Run from `jarvis/frontend`: tests `npx vitest run <path>`, typecheck `npx tsc --noEmit`, build `npm run build`.

---

## File Structure

- `jarvis/frontend/src/api/fieldSales.ts` — **modify**: add porting types (`FSStructuredNote`, `FSClient360` + sub-types) and 6 API wrappers.
- `jarvis/frontend/src/pages/Hub/index.tsx` — **modify**: register tile, extend `ActiveModule`, `tileCounts`, `visibleTiles` gate, render panel.
- `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx` — **create**: the panel (list, stats, actions, overlay).
- `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx` — **create**: panel behavior tests.
- `jarvis/frontend/src/pages/Hub/hubFieldSalesTile.test.tsx` — **create**: tile registration test.
- `jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.tsx` — **create**: ported note-capture / finalize flow.
- `jarvis/frontend/src/pages/FieldSales/ClientCard360.tsx` — **create**: ported 360° client card (web).
- `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx` — **modify**: optional `onOpenClient360` prop + "Vezi client 360" button.

Reference (port FROM, do not import — separate app): `jarvis-mobile/src/pages/FieldSales/{index.tsx,VisitNoteModal.tsx,ClientCard360.tsx}`, `jarvis-mobile/src/types/fieldSales.ts`.

---

## Task 1: API wrappers + porting types (`fieldSales.ts`)

**Files:**
- Modify: `jarvis/frontend/src/api/fieldSales.ts`
- Test: `jarvis/frontend/src/api/fieldSales.fs.test.ts` (create)

**Interfaces:**
- Consumes: `api` from `./client` (`api.get<T>(path, params?)`, `api.post<T>(path, body?)`).
- Produces (used by all later tasks):
  - `fieldSalesApi.getTodayVisits(date: string): Promise<{ success: boolean; visits: FSVisit[]; date: string }>`
  - `fieldSalesApi.checkin(visitId: number, coords: { lat?: number; lng?: number }): Promise<{ success: boolean; visit: FSVisit }>`
  - `fieldSalesApi.checkout(visitId: number, data: { outcome: string }): Promise<{ success: boolean; visit: FSVisit }>`
  - `fieldSalesApi.addNote(visitId: number, data: { raw_note: string }): Promise<{ success: boolean; note: FSVisitNote; structured_note: FSStructuredNote | null }>`
  - `fieldSalesApi.getClient360(clientId: number): Promise<FSClient360>`
  - `fieldSalesApi.refreshFiscal(clientId: number): Promise<{ success: boolean }>`
  - Types: `FSStructuredNote`, `FSClient360`, `FSClientProfile`, `FSClientFleetVehicle`, `FSSaleSummary`, `FSVisitSummary`, `FSAnafData`, `FSInventoryMatch`.

- [ ] **Step 1: Write the failing test**

Create `jarvis/frontend/src/api/fieldSales.fs.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
const post = vi.fn()
vi.mock('./client', () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }))

import { fieldSalesApi } from './fieldSales'

describe('fieldSalesApi daily-driver wrappers', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); get.mockResolvedValue({}); post.mockResolvedValue({}) })

  it('getTodayVisits hits the today route with the date param', async () => {
    await fieldSalesApi.getTodayVisits('2026-08-04')
    expect(get).toHaveBeenCalledWith('/api/field-sales/visits/today', { date: '2026-08-04' })
  })

  it('checkin posts coords to the checkin route', async () => {
    await fieldSalesApi.checkin(9, { lat: 46.7, lng: 23.6 })
    expect(post).toHaveBeenCalledWith('/api/field-sales/visits/9/checkin', { lat: 46.7, lng: 23.6 })
  })

  it('checkout posts the outcome', async () => {
    await fieldSalesApi.checkout(9, { outcome: 'completed' })
    expect(post).toHaveBeenCalledWith('/api/field-sales/visits/9/checkout', { outcome: 'completed' })
  })

  it('addNote posts the raw note', async () => {
    await fieldSalesApi.addNote(9, { raw_note: 'ok' })
    expect(post).toHaveBeenCalledWith('/api/field-sales/visits/9/note', { raw_note: 'ok' })
  })

  it('getClient360 fetches the 360 route', async () => {
    await fieldSalesApi.getClient360(760)
    expect(get).toHaveBeenCalledWith('/api/field-sales/clients/760/360')
  })

  it('refreshFiscal posts to the refresh-fiscal route', async () => {
    await fieldSalesApi.refreshFiscal(760)
    expect(post).toHaveBeenCalledWith('/api/field-sales/clients/760/refresh-fiscal')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/api/fieldSales.fs.test.ts`
Expected: FAIL (`getTodayVisits is not a function`, etc.).

- [ ] **Step 3: Add types + wrappers**

Append the porting types just before `export const fieldSalesApi = {` in `jarvis/frontend/src/api/fieldSales.ts`:

```ts
export interface FSStructuredNote {
  visit_summary: string
  contact_person: string | null
  vehicles_discussed: { action: string; current_vehicle: string | null; interested_in: string | null; budget_eur: number | null }[]
  commitments_made: string[]
  next_steps: { action: string; owner: string; deadline: string | null }[]
  opportunity_value_eur: number | null
  decision_timeline: string | null
  follow_up_date: string | null
  objections: string[]
  risk_flags: string[]
}

export interface FSClientProfile {
  id: number; client_id: number; client_type: string; industry: string | null
  country_code: string; legal_form: string | null; assigned_kam_id: number | null
  fleet_size: number; renewal_score: number; cui: string | null
  estimated_annual_value: number | null; priority: string
}
export interface FSClientFleetVehicle {
  id: number; client_id: number; vehicle_make: string; vehicle_model: string
  vehicle_year: number; vin: string | null; license_plate: string | null
  purchase_date: string | null; purchase_price: number | null; purchase_currency: string
  estimated_mileage: number | null; financing_type: string | null; financing_expiry: string | null
  warranty_expiry: string | null; status: string; renewal_candidate: boolean; renewal_reason: string | null
}
export interface FSSaleSummary {
  id: number; brand: string; model_name: string; contract_date: string | null
  sale_price_net: number | null; vin: string | null; source: string
}
export interface FSVisitSummary {
  id: number; planned_date: string; visit_type: string; status: string
  outcome: string | null; visit_summary: string | null; kam_name?: string; client_name?: string
}
export interface FSAnafData {
  company_name: string; address: string; is_vat_payer: boolean
  is_inactive: boolean; inactivation_date: string | null; fetched_at: string
}
export interface FSInventoryMatch {
  id: number; brand: string; model_name: string; model_year: number
  sale_price_net: number; vin: string | null
}
export interface FSClient360 {
  profile: FSClientProfile | null
  fleet: FSClientFleetVehicle[]
  last_purchases: FSSaleSummary[]
  last_interactions: FSVisitSummary[]
  visit_history: FSVisitSummary[]
  renewal_candidates: FSClientFleetVehicle[]
  inventory_matches: FSInventoryMatch[]
  fiscal: FSAnafData | null
}
```

Add these wrappers inside the `fieldSalesApi` object (after `getPendingTasks`):

```ts
  // ── Hub daily-driver ──
  getTodayVisits: (date: string) =>
    api.get<{ success: boolean; visits: FSVisit[]; date: string }>('/api/field-sales/visits/today', { date }),

  checkin: (visitId: number, coords: { lat?: number; lng?: number }) =>
    api.post<{ success: boolean; visit: FSVisit }>(`/api/field-sales/visits/${visitId}/checkin`, coords),

  checkout: (visitId: number, data: { outcome: string }) =>
    api.post<{ success: boolean; visit: FSVisit }>(`/api/field-sales/visits/${visitId}/checkout`, data),

  addNote: (visitId: number, data: { raw_note: string }) =>
    api.post<{ success: boolean; note: FSVisitNote; structured_note: FSStructuredNote | null }>(
      `/api/field-sales/visits/${visitId}/note`, data),

  getClient360: (clientId: number) => {
    // Backend returns { profile, fleet, purchases, interactions, visit_history,
    // renewal_candidates, inventory_matches, fiscal } — normalize to FSClient360.
    return api.get<Record<string, unknown>>(`/api/field-sales/clients/${clientId}/360`).then((res) => ({
      profile: (res.profile as FSClient360['profile']) ?? null,
      fleet: (res.fleet as FSClient360['fleet']) ?? [],
      last_purchases: (res.purchases as FSClient360['last_purchases']) ?? [],
      last_interactions: (res.interactions as FSClient360['last_interactions']) ?? [],
      visit_history: (res.visit_history as FSClient360['visit_history']) ?? [],
      renewal_candidates: (res.renewal_candidates as FSClient360['renewal_candidates']) ?? [],
      inventory_matches: (res.inventory_matches as FSClient360['inventory_matches']) ?? [],
      fiscal: (res.fiscal as FSClient360['fiscal']) ?? null,
    }))
  },

  refreshFiscal: (clientId: number) =>
    api.post<{ success: boolean }>(`/api/field-sales/clients/${clientId}/refresh-fiscal`),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/api/fieldSales.fs.test.ts`
Expected: PASS (6 tests). Note: `getClient360` normalizes to `{}` fields; the test only asserts the GET path.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/api/fieldSales.ts jarvis/frontend/src/api/fieldSales.fs.test.ts
git commit -m "feat(field-sales): add Hub daily-driver API wrappers + 360 types"
```

---

## Task 2: Register the Hub tile (`Hub/index.tsx`)

**Files:**
- Modify: `jarvis/frontend/src/pages/Hub/index.tsx`
- Test: `jarvis/frontend/src/pages/Hub/hubFieldSalesTile.test.tsx` (create)

**Interfaces:**
- Consumes: `appTiles`, `ActiveModule`, `authUser?.can_access_field_sales` (exists on the auth user type, `types/index.ts:27`).
- Produces: a `field_sales` tile (no `route`, label `Field Sales`) + `activeModule === 'field_sales'` renders `<HubFieldSalesPanel />` (created Task 3).

- [ ] **Step 1: Write the failing test**

Create `jarvis/frontend/src/pages/Hub/hubFieldSalesTile.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { appTiles } from './index'

describe('Field Sales tile', () => {
  it('is registered in appTiles as an in-page panel (no route)', () => {
    const tile = appTiles.find((t) => t.key === 'field_sales')
    expect(tile).toBeDefined()
    expect(tile?.route).toBeUndefined()
    expect(tile?.label).toBe('Field Sales')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/hubFieldSalesTile.test.tsx`
Expected: FAIL (`tile` is undefined).

- [ ] **Step 3: Wire the tile**

In `jarvis/frontend/src/pages/Hub/index.tsx`:

1. Ensure `MapPin` is imported from `lucide-react` (add to the existing import if absent).
2. Add to the `ActiveModule` union (line ~87):
   `type ActiveModule = null | 'invoices' | 'hr' | 'vouchers' | 'forms' | 'chat' | 'approvals' | 'driving' | 'field_sales'`
3. Add a lazy import near the other panel imports:
   `const HubFieldSalesPanel = lazy(() => import('@/pages/Hub/HubFieldSalesPanel'))`
   (If `lazy` is not imported from `react`, add it; `HubDrivingPanel` is imported eagerly, but lazy matches vouchers/chat/driving-in-Suspense usage.)
4. Append to `appTiles`:
   `{ key: 'field_sales', label: 'Field Sales', shortLabel: 'Teren', icon: MapPin, bg: 'bg-teal-600', fg: 'text-white' },`
5. Add to `tileCounts`: `field_sales: -1, // always show when allowed`
6. In `visibleTiles` filter, add before the empty-count check:
   `if (t.key === 'field_sales' && !authUser?.can_access_field_sales) return false`
   and add `authUser?.can_access_field_sales` to the `useMemo` dependency array.
7. In the module render area (after the `driving` block, ~line 375):

```tsx
{activeModule === 'field_sales' && (
  <Suspense fallback={<div className="py-8 text-center text-muted-foreground text-sm">Loading...</div>}>
    <HubFieldSalesPanel />
  </Suspense>
)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/hubFieldSalesTile.test.tsx`
Expected: PASS. (Panel file exists after Task 3; to compile now, create a stub `HubFieldSalesPanel.tsx` exporting `export default function HubFieldSalesPanel() { return null }` — replaced in Task 3.)

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/Hub/index.tsx jarvis/frontend/src/pages/Hub/hubFieldSalesTile.test.tsx jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx
git commit -m "feat(field-sales): register Field Sales tile in the Hub"
```

---

## Task 3: `HubFieldSalesPanel` core — list, stats, states

**Files:**
- Create/replace: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx`
- Test: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx` (create)

**Interfaces:**
- Consumes: `fieldSalesApi.getTodayVisits` (Task 1), `FSVisit`.
- Produces: default-exported `HubFieldSalesPanel`; internal `VISIT_TYPE_LABELS`, `STATUS_CONFIG`; renders a visit list keyed `['field-sales-visits', date]`.

Port `VisitCard`, `VISIT_TYPE_LABELS`, `STATUS_CONFIG`, `formatRomanianDate` from `jarvis-mobile/src/pages/FieldSales/index.tsx`, with these adaptations: remove `@capacitor/haptics` and `useNavigate`; card tap and CHECK-IN are wired via props (`onOpen`, `onCheckIn`) added in later tasks — in this task the actions can be present but no-op placeholders are NOT allowed, so include the buttons and wire `onOpen`/`onCheckIn`/`onFinalize` props now (Tasks 4–6 pass real handlers). Keep Tailwind classes (shared design system).

- [ ] **Step 1: Write the failing test**

Create `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getTodayVisits = vi.fn()
vi.mock('@/api/fieldSales', () => ({
  fieldSalesApi: {
    getTodayVisits: (...a: unknown[]) => getTodayVisits(...a),
    searchClients: vi.fn(), createVisit: vi.fn(),
    checkin: vi.fn(), checkout: vi.fn(), addNote: vi.fn(),
    getVisit: vi.fn(), getClient360: vi.fn(), refreshFiscal: vi.fn(),
  },
}))
// VisitDetailDialog is heavy; stub it for panel tests.
vi.mock('@/pages/FieldSales/VisitDetailDialog', () => ({
  VisitDetailDialog: ({ open, visitId }: { open: boolean; visitId: number | null }) =>
    open ? <div>detail:{visitId}</div> : null,
}))

import HubFieldSalesPanel from './HubFieldSalesPanel'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

const VISIT = {
  id: 9, kam_id: 3, client_id: 760, planned_date: '2026-08-04', planned_time: '13:30',
  visit_type: 'renewal_discussion', status: 'planned', client_name: 'DEMO Construct Grup SRL',
  kam_name: 'George Pop', renewal_score: 70, goals: 'Reinnoire',
}

describe('HubFieldSalesPanel', () => {
  beforeEach(() => { getTodayVisits.mockReset() })

  it('lists today visits and shows the quick-stat counts', async () => {
    getTodayVisits.mockResolvedValue({ success: true, visits: [VISIT], date: '2026-08-04' })
    wrap(<HubFieldSalesPanel />)
    expect(await screen.findByText('DEMO Construct Grup SRL')).toBeInTheDocument()
    // one planned visit -> "1" appears in the Planificate stat tile
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
  })

  it('shows the empty state when there are no visits', async () => {
    getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
    wrap(<HubFieldSalesPanel />)
    expect(await screen.findByText(/nicio vizit/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/HubFieldSalesPanel.test.tsx`
Expected: FAIL (stub panel renders `null`).

- [ ] **Step 3: Implement the panel core**

Replace `HubFieldSalesPanel.tsx` with the list/stats/states implementation. Key elements (port from mobile `index.tsx`):

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Clock, AlertTriangle, CalendarDays, ChevronRight, MapPin } from 'lucide-react'
import { cn } from '@/lib/utils'
import { fieldSalesApi, type FSVisit } from '@/api/fieldSales'
import { VisitDetailDialog } from '@/pages/FieldSales/VisitDetailDialog'

const VISIT_TYPE_LABELS: Record<string, string> = {
  fleet_review: 'Revizuire flota', renewal_discussion: 'Discutie reinnoire',
  test_drive_followup: 'Follow-up test drive', service_followup: 'Follow-up service',
  new_acquisition: 'Achizitie noua', contract_negotiation: 'Negociere contract',
  prospecting: 'Prospectare', general: 'General',
}
const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
  planned: { label: 'PLANIFICATA', bg: 'bg-blue-100 dark:bg-blue-900/40', text: 'text-blue-700 dark:text-blue-300' },
  in_progress: { label: 'IN CURS', bg: 'bg-orange-100 dark:bg-orange-900/40', text: 'text-orange-700 dark:text-orange-300' },
  completed: { label: 'FINALIZATA', bg: 'bg-green-100 dark:bg-green-900/40', text: 'text-green-700 dark:text-green-300' },
  no_show: { label: 'NEPREZENTAT', bg: 'bg-red-100 dark:bg-red-900/40', text: 'text-red-700 dark:text-red-300' },
  rescheduled: { label: 'REPROGRAMATA', bg: 'bg-purple-100 dark:bg-purple-900/40', text: 'text-purple-700 dark:text-purple-300' },
  partial: { label: 'PARTIALA', bg: 'bg-amber-100 dark:bg-amber-900/40', text: 'text-amber-700 dark:text-amber-300' },
}
const todayStr = () => new Date().toISOString().split('T')[0]

function VisitCard({ visit, onOpen, onCheckIn, onFinalize, actionPending }: {
  visit: FSVisit; onOpen: () => void; onCheckIn: () => void; onFinalize: () => void; actionPending: boolean
}) {
  const cfg = STATUS_CONFIG[visit.status] ?? STATUS_CONFIG.planned
  const showRenewal = (visit.renewal_score ?? 0) > 60
  return (
    <div onClick={onOpen} className="rounded-2xl bg-card border p-4 active:scale-[0.98] transition-transform cursor-pointer">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold truncate">{visit.client_name}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{VISIT_TYPE_LABELS[visit.visit_type] ?? visit.visit_type}</p>
        </div>
        <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide', cfg.bg, cfg.text)}>{cfg.label}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mb-3">
        {visit.planned_time && <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{visit.planned_time.slice(0,5)}</span>}
        {showRenewal && <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium"><AlertTriangle className="h-3.5 w-3.5" />Reinnoire {visit.renewal_score}%</span>}
      </div>
      {visit.goals && <p className="text-xs text-muted-foreground line-clamp-2 mb-3">{visit.goals}</p>}
      <div className="flex items-center justify-between">
        {visit.status === 'planned' && (
          <button onClick={(e) => { e.stopPropagation(); onCheckIn() }} disabled={actionPending}
            className="rounded-xl bg-teal-600 px-3 py-2.5 text-sm font-semibold text-white active:bg-teal-700 transition-colors disabled:opacity-50">
            <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4" />CHECK-IN</span>
          </button>
        )}
        {visit.status === 'in_progress' && (
          <button onClick={(e) => { e.stopPropagation(); onFinalize() }} disabled={actionPending}
            className="rounded-xl bg-orange-600 px-3 py-2.5 text-sm font-semibold text-white active:bg-orange-700 transition-colors disabled:opacity-50">
            Finalizeaza
          </button>
        )}
        {visit.status === 'completed' && <span className="text-xs text-green-600 dark:text-green-400 font-medium">Vizita finalizata</span>}
        <ChevronRight className="h-4 w-4 text-muted-foreground ml-auto" />
      </div>
    </div>
  )
}

type Overlay = null | { kind: 'add' } | { kind: 'detail'; id: number }
  | { kind: 'note'; id: number } | { kind: 'client360'; clientId: number }

export default function HubFieldSalesPanel() {
  const date = todayStr()
  const [overlay, setOverlay] = useState<Overlay>(null)
  const { data, isLoading, isError } = useQuery({
    queryKey: ['field-sales-visits', date],
    queryFn: () => fieldSalesApi.getTodayVisits(date),
  })
  const visits = data?.visits ?? []
  const planned = visits.filter(v => v.status === 'planned').length
  const inProgress = visits.filter(v => v.status === 'in_progress').length
  const completed = visits.filter(v => v.status === 'completed').length

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div><h2 className="text-xl font-bold">Vizite</h2><p className="text-sm text-muted-foreground">Azi</p></div>
        <button onClick={() => setOverlay({ kind: 'add' })} className="rounded-xl bg-teal-600 px-3 py-2.5 text-sm font-semibold text-white active:bg-teal-700">
          <span className="flex items-center gap-1"><Plus className="h-4 w-4" />Adauga</span>
        </button>
      </div>

      {visits.length > 0 && (
        <div className="flex gap-2">
          <div className="flex-1 rounded-xl bg-blue-50 dark:bg-blue-900/20 p-3 text-center"><p className="text-lg font-bold text-blue-700 dark:text-blue-300">{planned}</p><p className="text-[10px] font-medium uppercase text-blue-600/70">Planificate</p></div>
          <div className="flex-1 rounded-xl bg-orange-50 dark:bg-orange-900/20 p-3 text-center"><p className="text-lg font-bold text-orange-700 dark:text-orange-300">{inProgress}</p><p className="text-[10px] font-medium uppercase text-orange-600/70">In curs</p></div>
          <div className="flex-1 rounded-xl bg-green-50 dark:bg-green-900/20 p-3 text-center"><p className="text-lg font-bold text-green-700 dark:text-green-300">{completed}</p><p className="text-[10px] font-medium uppercase text-green-600/70">Finalizate</p></div>
        </div>
      )}

      {isLoading && <div className="flex justify-center py-16"><div className="h-5 w-5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" /></div>}
      {isError && <p className="py-16 text-center text-sm text-muted-foreground">Nu s-au putut incarca vizitele</p>}
      {!isLoading && !isError && visits.length === 0 && (
        <div className="flex flex-col items-center py-16">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted/50 mb-4"><CalendarDays className="h-8 w-8 text-muted-foreground" /></div>
          <p className="text-base font-semibold mb-1">Nicio vizita planificata</p>
          <p className="text-sm text-muted-foreground text-center max-w-[240px]">Adauga o vizita noua pentru a incepe planificarea zilei</p>
        </div>
      )}

      {!isLoading && !isError && visits.length > 0 && (
        <div className="space-y-3">
          {visits.map(v => (
            <VisitCard key={v.id} visit={v} actionPending={false}
              onOpen={() => setOverlay({ kind: 'detail', id: v.id })}
              onCheckIn={() => { /* Task 5 */ }}
              onFinalize={() => setOverlay({ kind: 'note', id: v.id })} />
          ))}
        </div>
      )}

      {/* Detail overlay (reuse existing dialog) */}
      <VisitDetailDialog
        visitId={overlay?.kind === 'detail' ? overlay.id : null}
        open={overlay?.kind === 'detail'}
        onOpenChange={(o) => { if (!o) setOverlay(null) }}
      />
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/HubFieldSalesPanel.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx
git commit -m "feat(field-sales): Hub panel core — today visits list, stats, states"
```

---

## Task 4: Add-visit overlay (client search → create)

**Files:**
- Modify: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx`
- Test: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx` (extend)

**Interfaces:**
- Consumes: `fieldSalesApi.searchClients` (existing), `fieldSalesApi.createVisit` (existing), `FSClientSearch`.
- Produces: an `AddVisitForm` rendered inside the overlay sheet; on success invalidates `['field-sales-visits', date]` and closes.

- [ ] **Step 1: Write the failing test**

Add to `HubFieldSalesPanel.test.tsx`:

```tsx
it('add-visit: submit is disabled until a client is selected, then calls createVisit', async () => {
  const { fireEvent } = await import('@testing-library/react')
  const mod = await import('@/api/fieldSales')
  ;(mod.fieldSalesApi.getTodayVisits as ReturnType<typeof vi.fn>).mockResolvedValue?.({ success: true, visits: [], date: todayStr() })
  getTodayVisits.mockResolvedValue({ success: true, visits: [], date: '2026-08-04' })
  ;(mod.fieldSalesApi.searchClients as ReturnType<typeof vi.fn>) = vi.fn().mockResolvedValue({ success: true, clients: [{ id: 760, display_name: 'ACME SRL', client_type: 'company' }], count: 1 })
  ;(mod.fieldSalesApi.createVisit as ReturnType<typeof vi.fn>) = vi.fn().mockResolvedValue({ success: true, visit: { id: 1 } })

  wrap(<HubFieldSalesPanel />)
  fireEvent.click(await screen.findByRole('button', { name: /adauga/i }))
  const submit = await screen.findByRole('button', { name: /salveaza vizita/i })
  expect(submit).toBeDisabled()
  fireEvent.change(screen.getByPlaceholderText(/cauta client/i), { target: { value: 'ACME' } })
  fireEvent.click(await screen.findByText('ACME SRL'))
  expect(screen.getByRole('button', { name: /salveaza vizita/i })).not.toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: /salveaza vizita/i }))
  await vi.waitFor(() => expect(mod.fieldSalesApi.createVisit).toHaveBeenCalled())
})
```

(Adjust the mock module shape so `searchClients`/`createVisit` are reassignable `vi.fn()`s; simplest is to define them as `vi.fn()` in the top `vi.mock` factory and import them in the test.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/HubFieldSalesPanel.test.tsx -t add-visit`
Expected: FAIL (no Adauga overlay / form yet).

- [ ] **Step 3: Implement AddVisitForm + overlay sheet**

Port `AddVisitSheet` from mobile `index.tsx` into a web `AddVisitForm` inside `HubFieldSalesPanel.tsx`. Adaptations: drop `@capacitor/haptics` and `BottomSheet`; render inside the shared overlay sheet markup copied from `HubDrivingPanel` (`fixed inset-0 z-50 ...` container with a sticky close button). Use `useQuery(['fs-client-search', q], () => fieldSalesApi.searchClients(q), { enabled: q.length >= 2 })` and `useMutation(fieldSalesApi.createVisit)`. Fields: client search (dropdown), date (default today), time, visit type `<select>` from `VISIT_TYPE_LABELS`, goals textarea. Submit disabled until a client is selected. On success: `queryClient.invalidateQueries({ queryKey: ['field-sales-visits', date] })` then `setOverlay(null)`. On error show `err?.data?.error`.

Render inside the panel's overlay region:

```tsx
{overlay?.kind === 'add' && (
  <OverlaySheet onClose={() => setOverlay(null)}>
    <AddVisitForm date={date} onDone={() => { queryClient.invalidateQueries({ queryKey: ['field-sales-visits', date] }); setOverlay(null) }} onCancel={() => setOverlay(null)} />
  </OverlaySheet>
)}
```

Add a small local `OverlaySheet` wrapper component (the fixed-inset sheet from `HubDrivingPanel`) reused by all overlays. Add `const queryClient = useQueryClient()` to the panel.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/HubFieldSalesPanel.test.tsx`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx
git commit -m "feat(field-sales): Hub add-visit overlay (client search + create)"
```

---

## Task 5: Check-in flow (best-effort geolocation)

**Files:**
- Modify: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx`
- Test: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx` (extend)

**Interfaces:**
- Consumes: `fieldSalesApi.checkin` (Task 1).
- Produces: `handleCheckIn(visit)` — resolves coords via `navigator.geolocation` best-effort, calls `checkin`, invalidates `['field-sales-visits', date]`, then opens the detail overlay for that visit.

- [ ] **Step 1: Write the failing test**

Add to `HubFieldSalesPanel.test.tsx`:

```tsx
it('check-in fires the checkin mutation even when geolocation is unavailable', async () => {
  const { fireEvent } = await import('@testing-library/react')
  const mod = await import('@/api/fieldSales')
  getTodayVisits.mockResolvedValue({ success: true, visits: [VISIT], date: '2026-08-04' })
  ;(mod.fieldSalesApi.checkin as ReturnType<typeof vi.fn>) = vi.fn().mockResolvedValue({ success: true, visit: { ...VISIT, status: 'in_progress' } })
  // no navigator.geolocation in jsdom -> best-effort path calls checkin with {}
  wrap(<HubFieldSalesPanel />)
  fireEvent.click(await screen.findByRole('button', { name: /check-in/i }))
  await vi.waitFor(() => expect(mod.fieldSalesApi.checkin).toHaveBeenCalledWith(9, {}))
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/HubFieldSalesPanel.test.tsx -t check-in`
Expected: FAIL (onCheckIn is a no-op).

- [ ] **Step 3: Implement handleCheckIn**

Add to the panel:

```tsx
const checkinMut = useMutation({
  mutationFn: ({ id, coords }: { id: number; coords: { lat?: number; lng?: number } }) => fieldSalesApi.checkin(id, coords),
  onSuccess: (_res, vars) => {
    queryClient.invalidateQueries({ queryKey: ['field-sales-visits', date] })
    setOverlay({ kind: 'detail', id: vars.id })
  },
})

function getCoords(): Promise<{ lat?: number; lng?: number }> {
  return new Promise((resolve) => {
    if (!('geolocation' in navigator)) return resolve({})
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => resolve({}),
      { timeout: 5000 },
    )
  })
}

const handleCheckIn = async (visit: FSVisit) => {
  const coords = await getCoords()
  checkinMut.mutate({ id: visit.id, coords })
}
```

Wire `onCheckIn={() => handleCheckIn(v)}` and `actionPending={checkinMut.isPending}` on `VisitCard`. Import `useMutation`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/HubFieldSalesPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx
git commit -m "feat(field-sales): Hub check-in with best-effort geolocation"
```

---

## Task 6: `NoteCaptureModal` (finalize with AI-structured note)

**Files:**
- Create: `jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.tsx`
- Modify: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx` (render for `overlay.kind === 'note'`)
- Test: `jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.test.tsx` (create)

**Interfaces:**
- Consumes: `fieldSalesApi.addNote` (Task 1), `FSStructuredNote`.
- Produces: `export default function NoteCaptureModal({ visitId, clientId, onDone, onCancel }: { visitId: number; clientId: number; onDone: () => void; onCancel: () => void })`.

Port the step machine from `jarvis-mobile/src/pages/FieldSales/VisitNoteModal.tsx` (`input → processing → review → saved`), dropping Capacitor Haptics. `handleProcess` calls `addNote(visitId, { raw_note })`, reads `res.structured_note` (fallback `res.note?.structured_note`), shows the review, then on save invalidates `['field-sales-visits']`, `['fs-visit-detail', visitId]`, `['field-sales-client360', clientId]` and calls `onDone`. Because `/note` finalizes the visit, this IS the finalize-with-note flow.

- [ ] **Step 1: Write the failing test**

Create `NoteCaptureModal.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const addNote = vi.fn()
vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: { addNote: (...a: unknown[]) => addNote(...a) } }))
import NoteCaptureModal from './NoteCaptureModal'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('NoteCaptureModal', () => {
  beforeEach(() => addNote.mockReset())
  it('submits the raw note and renders the AI summary', async () => {
    addNote.mockResolvedValue({ success: true, note: { id: 1, raw_note: 'x', created_at: '' }, structured_note: {
      visit_summary: 'Rezumat AI', contact_person: null, vehicles_discussed: [], commitments_made: [],
      next_steps: [], opportunity_value_eur: null, decision_timeline: null, follow_up_date: null, objections: [], risk_flags: [],
    } })
    wrap(<NoteCaptureModal visitId={9} clientId={760} onDone={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'discutie buna' } })
    fireEvent.click(screen.getByRole('button', { name: /proceseaz|finalizeaz|salveaz/i }))
    expect(await screen.findByText('Rezumat AI')).toBeInTheDocument()
    expect(addNote).toHaveBeenCalledWith(9, { raw_note: 'discutie buna' })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/FieldSales/NoteCaptureModal.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement NoteCaptureModal**

Create the component per the ported step machine above (input textarea + process button → processing spinner → review of `FSStructuredNote` sections → saved). Use `useMutation(({ raw_note }) => fieldSalesApi.addNote(visitId, { raw_note }))`. Show errors via `err?.data?.error`. Keep it self-contained (no overlay chrome — the panel wraps it in `OverlaySheet`).

- [ ] **Step 4: Wire into the panel**

In `HubFieldSalesPanel.tsx`, resolve the client for the note overlay from the loaded visits and render:

```tsx
{overlay?.kind === 'note' && (() => {
  const v = visits.find(x => x.id === overlay.id)
  return (
    <OverlaySheet onClose={() => setOverlay(null)}>
      <NoteCaptureModal visitId={overlay.id} clientId={v?.client_id ?? 0}
        onDone={() => { queryClient.invalidateQueries({ queryKey: ['field-sales-visits', date] }); setOverlay(null) }}
        onCancel={() => setOverlay(null)} />
    </OverlaySheet>
  )
})()}
```

- [ ] **Step 5: Run tests + commit**

Run: `cd jarvis/frontend && npx vitest run src/pages/FieldSales/NoteCaptureModal.test.tsx src/pages/Hub/HubFieldSalesPanel.test.tsx`
Expected: PASS.

```bash
git add jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.tsx jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.test.tsx jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx
git commit -m "feat(field-sales): Hub note-capture / finalize-with-note flow"
```

---

## Task 7: `ClientCard360` (web port)

**Files:**
- Create: `jarvis/frontend/src/pages/FieldSales/ClientCard360.tsx`
- Test: `jarvis/frontend/src/pages/FieldSales/ClientCard360.test.tsx` (create)

**Interfaces:**
- Consumes: `fieldSalesApi.getClient360`, `fieldSalesApi.refreshFiscal` (Task 1), `FSClient360`.
- Produces: `export default function ClientCard360({ clientId }: { clientId: number })`.

Port `jarvis-mobile/src/pages/FieldSales/ClientCard360.tsx`, adaptations: replace mobile `useClient360`/`useRefreshFiscal` hooks with `useQuery(['field-sales-client360', clientId], () => fieldSalesApi.getClient360(clientId))` and `useMutation(() => fieldSalesApi.refreshFiscal(clientId))`; drop Capacitor Haptics and native navigation. Render sections: header (name/priority/renewal), fiscal (ANAF) with a "Reimprospateaza" button, fleet list (renewal candidates highlighted), last purchases, visit history, inventory matches. Keep Tailwind classes.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getClient360 = vi.fn()
vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: { getClient360: (...a: unknown[]) => getClient360(...a), refreshFiscal: vi.fn() } }))
import ClientCard360 from './ClientCard360'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('ClientCard360', () => {
  beforeEach(() => getClient360.mockReset())
  it('renders fleet vehicles from the 360 payload', async () => {
    getClient360.mockResolvedValue({
      profile: { id: 1, client_id: 760, client_type: 'company', industry: 'Transport', country_code: 'RO', legal_form: 'SRL', assigned_kam_id: 3, fleet_size: 1, renewal_score: 78, cui: '40123456', estimated_annual_value: 450000, priority: 'high' },
      fleet: [{ id: 1, client_id: 760, vehicle_make: 'Audi', vehicle_model: 'A6', vehicle_year: 2021, vin: null, license_plate: 'CJ11DEM', purchase_date: null, purchase_price: null, purchase_currency: 'EUR', estimated_mileage: null, financing_type: null, financing_expiry: null, warranty_expiry: null, status: 'active', renewal_candidate: true, renewal_reason: 'garantie' }],
      last_purchases: [], last_interactions: [], visit_history: [], renewal_candidates: [], inventory_matches: [], fiscal: null,
    })
    wrap(<ClientCard360 clientId={760} />)
    expect(await screen.findByText(/Audi A6/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/FieldSales/ClientCard360.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the port.** Ensure a vehicle row renders `` `${vehicle_make} ${vehicle_model}` `` so the test's `/Audi A6/` matches.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/FieldSales/ClientCard360.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/FieldSales/ClientCard360.tsx jarvis/frontend/src/pages/FieldSales/ClientCard360.test.tsx
git commit -m "feat(field-sales): web ClientCard360 (360 client card port)"
```

---

## Task 8: Link the 360 card from `VisitDetailDialog` + Hub overlay

**Files:**
- Modify: `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx`
- Modify: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx`
- Test: `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.client360.test.tsx` (create)

**Interfaces:**
- Consumes: `FSVisit.client_id`.
- Produces: new **optional** prop `onOpenClient360?: (clientId: number) => void` on `VisitDetailDialog`; when provided, a "Vezi client 360" button appears in the Info tab's Client section and calls it with `visit.client_id`. Existing desktop usage (no prop) is unchanged.

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/fieldSales', () => ({ fieldSalesApi: {
  getVisit: vi.fn().mockResolvedValue({ success: true, visit: {
    id: 9, kam_id: 3, client_id: 760, planned_date: '2026-08-04', visit_type: 'general', status: 'planned',
    client_name: 'ACME SRL', kam_name: 'George Pop',
  } }),
  getVisitTasks: vi.fn().mockResolvedValue({ success: true, tasks: [] }),
  updateVisit: vi.fn(),
} }))
import { VisitDetailDialog } from './VisitDetailDialog'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('VisitDetailDialog client360 link', () => {
  it('calls onOpenClient360 with the client id', async () => {
    const spy = vi.fn()
    wrap(<VisitDetailDialog visitId={9} open onOpenChange={() => {}} onOpenClient360={spy} />)
    fireEvent.click(await screen.findByRole('button', { name: /client 360/i }))
    expect(spy).toHaveBeenCalledWith(760)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/FieldSales/VisitDetailDialog.client360.test.tsx`
Expected: FAIL (no such prop/button).

- [ ] **Step 3: Implement**

In `VisitDetailDialog.tsx`: extend `Props` with `onOpenClient360?: (clientId: number) => void`; in the Info tab's Client section (~line 335) add, when the prop exists:

```tsx
{onOpenClient360 && (
  <Button variant="outline" size="sm" className="mt-2" onClick={() => onOpenClient360(visit.client_id)}>
    Vezi client 360
  </Button>
)}
```

In `HubFieldSalesPanel.tsx`: pass `onOpenClient360={(clientId) => setOverlay({ kind: 'client360', clientId })}` to the `VisitDetailDialog`, and render the 360 overlay:

```tsx
{overlay?.kind === 'client360' && (
  <OverlaySheet onClose={() => setOverlay(null)}>
    <ClientCard360 clientId={overlay.clientId} />
  </OverlaySheet>
)}
```

Import `ClientCard360`. Note: opening the 360 overlay from the (modal) dialog replaces the panel overlay; that is acceptable — closing the 360 sheet returns to the list.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/FieldSales/VisitDetailDialog.client360.test.tsx src/pages/Hub/HubFieldSalesPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.client360.test.tsx
git commit -m "feat(field-sales): link ClientCard360 from visit detail + Hub overlay"
```

---

## Task 9: Full verification

**Files:** none (verification + fixups only).

- [ ] **Step 1: Typecheck**

Run: `cd jarvis/frontend && npx tsc --noEmit`
Expected: no errors. Fix any type issues (unused imports, `FSVisit` optional fields).

- [ ] **Step 2: Run the full field-sales + hub test set**

Run: `cd jarvis/frontend && npx vitest run src/api/fieldSales.fs.test.ts src/pages/Hub/HubFieldSalesPanel.test.tsx src/pages/Hub/hubFieldSalesTile.test.tsx src/pages/FieldSales/NoteCaptureModal.test.tsx src/pages/FieldSales/ClientCard360.test.tsx src/pages/FieldSales/VisitDetailDialog.client360.test.tsx`
Expected: all PASS.

- [ ] **Step 3: Production build**

Run: `cd jarvis/frontend && npm run build`
Expected: build succeeds (verifies the lazy import + Hub wiring compile).

- [ ] **Step 4: Manual smoke (optional, localhost)**

With the app running against localhost DB (KAM has `can_access_field_sales`): open the Hub → **Teren** tile → today's visits appear (the seeded DEMO route stops), check-in a planned visit, open detail, tap "Vezi client 360". Confirm no console errors.

- [ ] **Step 5: Commit any fixups**

```bash
git add -A jarvis/frontend
git commit -m "chore(field-sales): verification fixups for Hub panel" || echo "nothing to fix"
```

---

## Self-Review

**Spec coverage:**
- Tile + gating (spec §1) → Task 2 (tile, `can_access_field_sales`, stays-visible-at-0 via `tileCounts.field_sales = -1`).
- `HubFieldSalesPanel` list/stats/states/overlay (spec §2) → Task 3.
- Reuse `VisitDetailDialog` (spec §3) → Task 3 (detail overlay) + Task 8 (360 link).
- Add-visit (spec §3) → Task 4. Note capture (spec §3) → Task 6. ClientCard360 (spec §3) → Task 7.
- Check-in / check-out (spec §3, §5) → Task 5 (check-in), Task 6 (finalize-with-note; note endpoint completes the visit). Note-less checkout wrapper exists (Task 1) for future use; primary finalize path is the note flow, matching mobile.
- 6 API wrappers (spec §4) → Task 1.
- Geolocation best-effort (spec §6) → Task 5. Error handling (spec §7) → all mutation UIs use `err?.data?.error`.
- Testing (spec §8) → tile test (T2), panel list/stats/check-in/add (T3–T5), note (T6), 360 (T7), dialog link (T8), full verify (T9).
- Out of scope (manager tab, route planner, backend) → not present. ✓

**Placeholder scan:** No TBD/TODO. The only "future" note (`checkout` wrapper unused by primary flow) is intentional and documented, not a gap. VisitCard `onCheckIn` is a real handler by Task 5 (Task 3 leaves an explicit inline comment, replaced in Task 5 — acceptable as the card is not user-reachable for check-in until then since the panel is not yet routed; still, Task 5 wires it).

**Type consistency:** Wrapper names/signatures in Task 1 match their consumers (`getTodayVisits`, `checkin`, `checkout`, `addNote`, `getClient360`, `refreshFiscal`); `FSClient360`/`FSStructuredNote` used identically in Tasks 6–7; `VisitDetailDialog` prop `onOpenClient360` defined in Task 8 and used in the same task; query keys consistent (`['field-sales-visits', date]`, `['fs-visit-detail', visitId]`, `['field-sales-client360', clientId]`).

---

# ADDENDUM (2026-08-04) — user-requested enhancements

Added after mid-execution requests: (a) **Calendar** to see planned visits, (b) **Upcoming visits** in the Today view, (c) **responsive** page. These run AFTER Tasks 5–8; the final verification (Task 9) runs last, after Task 12.

Data note: the KAM daily-driver so far uses `getTodayVisits` (single day). Calendar + Upcoming need the current KAM's visits over a **date range**. The repo already has `VisitRepository.get_team_visits(date_from, date_to, kam_id)` (used by the manager overview). Task 10 exposes it via a new KAM-scoped route that forces `kam_id = current user` (a plain KAM sees only their own visits) — the one small backend addition in this feature.

## Task 10: KAM-scoped range endpoint + `getMyVisits` wrapper

**Files:**
- Modify: `jarvis/field_sales/routes/visits.py` (add `visits/mine` route)
- Modify: `jarvis/frontend/src/api/fieldSales.ts` (add `getMyVisits`)
- Test: `jarvis/frontend/src/api/fieldSales.fs.test.ts` (extend)

**Interfaces:**
- Produces: `GET /api/field-sales/visits/mine?date_from=&date_to=` → `{ success, visits: FSVisit[], date_from, date_to }`; web `fieldSalesApi.getMyVisits(dateFrom: string, dateTo: string): Promise<{ success: boolean; visits: FSVisit[]; date_from: string; date_to: string }>`.

- [ ] **Step 1 (backend):** In `jarvis/field_sales/routes/visits.py`, after `api_visits_today`, add (mirrors `api_visits_today` auth + the manager route's date validation, but forces the current user's id):

```python
@field_sales_bp.route('/api/field-sales/visits/mine', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_visits_mine():
    """Get the current KAM's own visits in a date range (calendar / upcoming)."""
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        if not date_from or not date_to:
            return jsonify({'success': False, 'error': 'date_from and date_to are required'}), 400
        try:
            datetime.strptime(date_from, '%Y-%m-%d')
            datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        visits = _visit_repo.get_team_visits(date_from, date_to, kam_id=_get_current_user().id)
        return jsonify({'success': True, 'visits': visits, 'date_from': date_from, 'date_to': date_to})
    except Exception as e:
        logger.exception('Error fetching my visits')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
```

Verify the backend still imports/boots: `cd jarvis && python -c "import app"` (or the project's usual smoke) — no import error. There is no pytest for these routes; the get_team_visits query is already exercised by the manager route.

- [ ] **Step 2 (frontend test, RED):** add to `fieldSales.fs.test.ts`:

```ts
it('getMyVisits hits the mine route with date range params', async () => {
  await fieldSalesApi.getMyVisits('2026-08-01', '2026-08-31')
  expect(get).toHaveBeenCalledWith('/api/field-sales/visits/mine', { date_from: '2026-08-01', date_to: '2026-08-31' })
})
```

- [ ] **Step 3 (frontend wrapper):** add to `fieldSalesApi` (next to `getTodayVisits`):

```ts
  getMyVisits: (dateFrom: string, dateTo: string) =>
    api.get<{ success: boolean; visits: FSVisit[]; date_from: string; date_to: string }>(
      '/api/field-sales/visits/mine', { date_from: dateFrom, date_to: dateTo }),
```

- [ ] **Step 4:** `cd jarvis/frontend && npx vitest run src/api/fieldSales.fs.test.ts` → PASS; `npx tsc --noEmit` → clean.
- [ ] **Step 5:** Commit `feat(field-sales): KAM-scoped visits/mine range endpoint + getMyVisits`.

## Task 11: Calendar tab + Upcoming section in Today view

**Files:**
- Modify: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx`
- Create: `jarvis/frontend/src/pages/Hub/FieldSalesCalendar.tsx`
- Test: `jarvis/frontend/src/pages/Hub/FieldSalesCalendar.test.tsx` (create) + extend `HubFieldSalesPanel.test.tsx`

**Interfaces:**
- Consumes: `fieldSalesApi.getMyVisits` (Task 10), `FSVisit`, the panel's `VISIT_TYPE_LABELS`/`STATUS_CONFIG`.
- Produces: `FieldSalesCalendar` (default export) `({ onOpen }: { onOpen: (visitId: number) => void })`.

- [ ] **Step 1 — Tabs in the panel.** Add a Radix `Tabs` switcher at the top of `HubFieldSalesPanel` (same components as `HubDrivingPanel`): `Azi` and `Calendar`, persisted via `usePersistedState<'today'|'calendar'>('hub-fs-tab','today')` (import `usePersistedState` from `@/lib/utils`). The existing header/stats/list render under `Azi`; `<FieldSalesCalendar onOpen={(id) => setOverlay({ kind: 'detail', id })} />` renders under `Calendar`. Overlays stay shared.

- [ ] **Step 2 — Upcoming section (Azi tab).** Below today's list add a "Vizite viitoare" section. Query: `useQuery(['field-sales-mine', from, to], () => fieldSalesApi.getMyVisits(from, to))` where `from = tomorrow (todayStr()+1d)` and `to = +30d`. Filter results to `status === 'planned' || status === 'in_progress'`. Render each with the existing `VisitCard` (which already shows client/type/time/renewal + a status action), wrapped so the planned date is visible — pass a small date label above each card (`new Date(v.planned_date+'T00:00:00').toLocaleDateString('ro-RO', { weekday:'short', day:'2-digit', month:'short' })`). Tapping opens the detail overlay. Empty upcoming → render nothing (no empty-state noise). Header: "Vizite viitoare (30 zile)".

- [ ] **Step 3 — Calendar component.** Create `FieldSalesCalendar.tsx`, a **month** view adapted from `jarvis/frontend/src/pages/Hub/DrivingCalendar.tsx` (reuse its `pad`/`keyOf`/`addDays`/`addMonths`/`startOfWeek`/`naiveDate` helpers and the 6-week / 42-cell month grid + prev/next navigation; drop the day/week views and the foiParcurs vehicle join). Data: `useQuery(['field-sales-cal', gridStartKey], () => fieldSalesApi.getMyVisits(keyOf(gridStart), keyOf(addDays(gridStart,41))))`. Group visits by `planned_date` (`dayKeyOf`). Each month cell shows the day number and, when it has visits, a count badge / up to 3 colored dots using `STATUS_CONFIG` colors. Selecting a day lists that day's visits below the grid via `VisitCard` (or a compact row) with `onClick={() => onOpen(v.id)}`. `STATUS_CONFIG`/`VISIT_TYPE_LABELS`: export them from `HubFieldSalesPanel.tsx` (add `export`) and import here, to avoid duplication.

- [ ] **Step 4 — Tests.**
  - `FieldSalesCalendar.test.tsx`: mock `getMyVisits` to return two visits on a known day; render; assert the month grid shows an indicator on that day and that selecting it lists the visit; assert `onOpen` fires with the visit id on click.
  - Extend `HubFieldSalesPanel.test.tsx`: with `getMyVisits` mocked to return one future planned visit, the Azi tab shows the "Vizite viitoare" header and the client; switching to the Calendar tab (fireEvent.mouseDown on the `Calendar` tab — Radix selects on mousedown) renders the calendar. Keep output pristine (await settled state).

- [ ] **Step 5:** `npx vitest run src/pages/Hub/FieldSalesCalendar.test.tsx src/pages/Hub/HubFieldSalesPanel.test.tsx` → PASS; `npx tsc --noEmit` → clean. Commit `feat(field-sales): Hub calendar tab + upcoming visits in today view`.

## Task 12: Responsive layout pass

**Files:**
- Modify: `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx`, `FieldSalesCalendar.tsx`, `jarvis/frontend/src/pages/FieldSales/ClientCard360.tsx`

**Goal:** the panel uses horizontal space on desktop and never overflows on mobile. The panel is already mobile-first (iOS control sizes, responsive overlay sheet); this pass adds desktop breakpoints.

- [ ] **Step 1:** Today list and Upcoming list: replace the single-column `space-y-3` wrapper with a responsive grid: `grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3`. Stats row: keep 3-across via `grid grid-cols-3 gap-2` (so it never wraps awkwardly). Header row: `flex-wrap gap-2` so the Adauga button wraps under the title on narrow widths.
- [ ] **Step 2:** Calendar: ensure the month grid is fluid (`grid grid-cols-7` cells with `min-w-0`, `aspect-square` or min-height cells, text truncation) and the whole calendar sits in an `overflow-x-auto` guard so it never forces body horizontal scroll; the selected-day list uses the same responsive grid as Step 1.
- [ ] **Step 3:** ClientCard360: section layout uses `grid grid-cols-1 md:grid-cols-2` for the info/fiscal/fleet blocks where it reads better on desktop; long tables/rows wrapped in `overflow-x-auto`; images/values `max-w-full`.
- [ ] **Step 4 — verify responsiveness.** Add/extend a test only where it adds value (e.g. assert the list wrapper has the `md:grid-cols-2` class), OR verify via build + manual breakpoints — layout classes aren't deeply unit-testable. Run `npx tsc --noEmit` and `npm run build`; then (optional, localhost) confirm at 375px and 1280px widths that the body has no horizontal scrollbar and cards reflow. Commit `feat(field-sales): responsive layout for Hub field-sales panel + 360 card`.

## Revised final task order

5 → 6 → 7 → 8 → 10 → 11 → 12 → 9 (Full verification runs LAST, after Task 12). The final whole-branch review covers the whole feature including the addendum.
