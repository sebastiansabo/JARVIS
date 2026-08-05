# Driving Sessions HUB Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-page "Driving Sessions" panel to the JARVIS web HUB (gated on `can_access_carpark`) reusing the existing FoiParcurs components, and build the missing vehicle **Return/completion** flow into the shared FoiParcurs module.

**Architecture:** The Return flow is a new shared component (`TestDriveReturn`) + one API method over the already-existing backend `PUT /api/foi-parcurs/test-drive/:id/return`. A new `HubDrivingPanel` renders the existing `SessionsTab`/`CalendarTab` inline with its own company/brand selector, and opens the plan/activate/return forms as full-screen overlays *inside* the Hub (never leaving `/app/hub`). `TestDriveForm` gets a light, backward-compatible embeddable refactor. No backend changes.

**Tech Stack:** React 18 + TypeScript + Vite; TanStack Query; shadcn/ui (`@/components/ui/*`); Vitest 3 + @testing-library/react; lucide-react icons.

## Global Constraints

- Work on the `dev` branch only (JARVIS git workflow). Do NOT push to staging/main.
- API client lives in `@/api/foiParcurs` (`foiParcursApi`); domain types in `@/types/foiParcurs`.
- Reuse the existing **7-zone** damage model (`pages/FoiParcurs/testDriveDamage.tsx`). Do NOT port mobile's 9 zones.
- Return fuel levels are `Gol | 1/4 | 1/2 | 3/4 | Plin` (`ReturnFuelLevel`) — distinct from the departure `FuelGaugeLevel` (`1 | 1/2 | 2/3 | 1/4`).
- Datetimes use the web module's existing convention (`.slice(0,16)` on ISO strings) — do NOT introduce mobile's `naiveDate`.
- All user-facing copy is Romanian.
- Backend return endpoint requires `advisor_signature` + `client_signature` + `km_end` (≥ `km_start`); optional `fuel_gauge_end_level`, `return_datetime`, `return_damage` (list), `return_notes`.
- Contracts list cache key is `['foi-contracts-all', companyId]` — invalidate `['foi-contracts-all']` after any return/activate/discard.
- Tests are colocated `*.test.ts(x)`; run with `npx vitest run <path>`; full suite `npm test`.
- Access gate flag: `can_access_carpark` on the auth user (`@/types` `User.can_access_carpark`).

---

### Task 1: Return API method + payload types

**Files:**
- Modify: `jarvis/frontend/src/types/foiParcurs.ts` (add `ReturnFuelLevel`, `ReturnTestDrivePayload` near the other payload types, ~line 350)
- Modify: `jarvis/frontend/src/api/foiParcurs.ts` (add `submitTestDriveReturn` after `getTestDrive`, ~line 229)
- Test: `jarvis/frontend/src/api/foiParcurs.return.test.ts`

**Interfaces:**
- Produces: `ReturnFuelLevel`, `ReturnTestDrivePayload` (types); `foiParcursApi.submitTestDriveReturn(id: number, data: ReturnTestDrivePayload): Promise<{ success: boolean; contract: FoiContract }>`

- [ ] **Step 1: Write the failing test**

```ts
// jarvis/frontend/src/api/foiParcurs.return.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

const put = vi.fn().mockResolvedValue({ success: true, contract: { id: 7 } })
vi.mock('./client', () => ({ api: { put, get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

import { foiParcursApi } from './foiParcurs'
import type { ReturnTestDrivePayload } from '@/types/foiParcurs'

describe('foiParcursApi.submitTestDriveReturn', () => {
  beforeEach(() => put.mockClear())

  it('PUTs to the return endpoint with the payload', async () => {
    const payload: ReturnTestDrivePayload = {
      km_end: 12500,
      fuel_gauge_end_level: '1/2',
      return_damage: [],
      advisor_signature: 'data:image/png;base64,AAA',
      client_signature: 'data:image/png;base64,BBB',
    }
    await foiParcursApi.submitTestDriveReturn(7, payload)
    expect(put).toHaveBeenCalledWith('/api/foi-parcurs/test-drive/7/return', payload)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/api/foiParcurs.return.test.ts`
Expected: FAIL — `submitTestDriveReturn is not a function` (and/or `ReturnTestDrivePayload` type missing).

- [ ] **Step 3: Add the types**

In `jarvis/frontend/src/types/foiParcurs.ts`, immediately after the `ActivateTestDrivePayload` interface (near line 350), add:

```ts
// ── Return (completion) Test Drive Payload — PUT /test-drive/:id/return.
// Fuel level uses the return gauge set (Gol…Plin), distinct from departure. ──
export type ReturnFuelLevel = 'Gol' | '1/4' | '1/2' | '3/4' | 'Plin'

export interface ReturnTestDrivePayload {
  km_end: number
  fuel_gauge_end_level: ReturnFuelLevel
  return_damage: TdDamageItem[]
  return_notes?: string
  advisor_signature: string
  client_signature: string
  return_datetime?: string
}
```

- [ ] **Step 4: Add the API method**

In `jarvis/frontend/src/api/foiParcurs.ts`, add the import to the existing type import block (the line importing `FoiContract`, `TdDamageItem`, etc.) `ReturnTestDrivePayload`, then after `getTestDrive` (~line 229) add:

```ts
  // ── Record vehicle return → complete a test drive (PLANNED/FILLED → COMPLETED) ──
  submitTestDriveReturn: (id: number, data: ReturnTestDrivePayload) =>
    api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/return`, data),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/api/foiParcurs.return.test.ts`
Expected: PASS (1 test).

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/types/foiParcurs.ts jarvis/frontend/src/api/foiParcurs.ts jarvis/frontend/src/api/foiParcurs.return.test.ts
git commit -m "feat(foi-parcurs): add submitTestDriveReturn API + return payload types"
```

---

### Task 2: Pure return-form logic (`returnLogic.ts`)

Extract the return form's testable logic into pure functions so validation/payload/seeding are unit-tested without rendering.

**Files:**
- Create: `jarvis/frontend/src/pages/FoiParcurs/returnLogic.ts`
- Test: `jarvis/frontend/src/pages/FoiParcurs/returnLogic.test.ts`

**Interfaces:**
- Consumes: `testDriveDamage` (`DamageState`, `fromDamagePayload`, `toDamagePayload`, `makeEmptyDamageState`); types from Task 1.
- Produces:
  - `type ReturnFormState = { kmEnd: string; fuel: ReturnFuelLevel | null; damage: DamageState; notes: string; advisorSignature: string; clientSignature: string }`
  - `seedReturnDamage(contract): { damage: DamageState; seeded: boolean }`
  - `kmEndError(kmEnd: string, kmStart?: number | null): string | null`
  - `returnMissing(s, kmStart?): { km: boolean; fuel: boolean; advisorSig: boolean; clientSig: boolean }`
  - `isReturnValid(s, kmStart?): boolean`
  - `buildReturnPayload(s): ReturnTestDrivePayload`

- [ ] **Step 1: Write the failing test**

```ts
// jarvis/frontend/src/pages/FoiParcurs/returnLogic.test.ts
import { describe, it, expect } from 'vitest'
import {
  seedReturnDamage, kmEndError, returnMissing, isReturnValid, buildReturnPayload,
  type ReturnFormState,
} from './returnLogic'
import { makeEmptyDamageState } from './testDriveDamage'

const base: ReturnFormState = {
  kmEnd: '', fuel: null, damage: makeEmptyDamageState(),
  notes: '', advisorSignature: '', clientSignature: '',
}

describe('kmEndError', () => {
  it('no error when empty (untouched)', () => expect(kmEndError('', 100)).toBeNull())
  it('errors when below km_start', () => expect(kmEndError('90', 100)).toMatch(/≥ km plecare/))
  it('ok when >= km_start', () => expect(kmEndError('120', 100)).toBeNull())
  it('errors on non-numeric', () => expect(kmEndError('abc', 100)).toMatch(/invalid/))
})

describe('returnMissing / isReturnValid', () => {
  it('everything missing on a blank form', () => {
    const m = returnMissing(base, 100)
    expect(m).toEqual({ km: true, fuel: true, advisorSig: true, clientSig: true })
    expect(isReturnValid(base, 100)).toBe(false)
  })
  it('valid once km/fuel/both sigs present', () => {
    const s: ReturnFormState = { ...base, kmEnd: '150', fuel: '1/2', advisorSignature: 'a', clientSignature: 'b' }
    expect(isReturnValid(s, 100)).toBe(true)
  })
  it('km below start keeps it invalid', () => {
    const s: ReturnFormState = { ...base, kmEnd: '50', fuel: '1/2', advisorSignature: 'a', clientSignature: 'b' }
    expect(isReturnValid(s, 100)).toBe(false)
  })
})

describe('seedReturnDamage', () => {
  it('seeds from departure_damage when present', () => {
    const { damage, seeded } = seedReturnDamage({ departure_damage: [{ zone: 'Față', severity: 'minor', note: 'zgârietură' }] })
    expect(seeded).toBe(true)
    expect(damage['Față'].severity).toBe('Minor')
  })
  it('empty state when no departure damage', () => {
    const { seeded } = seedReturnDamage({ departure_damage: null })
    expect(seeded).toBe(false)
  })
})

describe('buildReturnPayload', () => {
  it('builds the API payload, omitting empty notes', () => {
    const s: ReturnFormState = { ...base, kmEnd: '150', fuel: 'Plin', advisorSignature: 'a', clientSignature: 'b', notes: '  ' }
    const p = buildReturnPayload(s)
    expect(p).toEqual({ km_end: 150, fuel_gauge_end_level: 'Plin', return_damage: [], advisor_signature: 'a', client_signature: 'b' })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/returnLogic.test.ts`
Expected: FAIL — module `./returnLogic` not found.

- [ ] **Step 3: Implement `returnLogic.ts`**

```ts
// jarvis/frontend/src/pages/FoiParcurs/returnLogic.ts
import type { FoiContract, ReturnFuelLevel, ReturnTestDrivePayload } from '@/types/foiParcurs'
import { type DamageState, fromDamagePayload, toDamagePayload, makeEmptyDamageState } from './testDriveDamage'

export interface ReturnFormState {
  kmEnd: string
  fuel: ReturnFuelLevel | null
  damage: DamageState
  notes: string
  advisorSignature: string
  clientSignature: string
}

/** Seed the return damage from what was recorded at handover so the advisor
 *  confirms + adds, instead of starting blank (which hides departure damage). */
export function seedReturnDamage(contract: Pick<FoiContract, 'departure_damage'>): { damage: DamageState; seeded: boolean } {
  const items = contract.departure_damage
  if (Array.isArray(items) && items.length > 0) {
    return { damage: fromDamagePayload(items), seeded: true }
  }
  return { damage: makeEmptyDamageState(), seeded: false }
}

/** Inline error for the km_end field — null while untouched or valid. */
export function kmEndError(kmEnd: string, kmStart?: number | null): string | null {
  if (kmEnd.trim() === '') return null
  const n = Number(kmEnd)
  if (Number.isNaN(n)) return 'Km retur invalid.'
  const start = kmStart == null ? NaN : Number(kmStart)
  if (!Number.isNaN(start) && n < start) return `Km retur trebuie să fie ≥ km plecare (${kmStart}).`
  return null
}

export function returnMissing(s: ReturnFormState, kmStart?: number | null) {
  const n = Number(s.kmEnd)
  const start = kmStart == null ? NaN : Number(kmStart)
  const kmValid = s.kmEnd.trim() !== '' && !Number.isNaN(n) && (Number.isNaN(start) || n >= start)
  return { km: !kmValid, fuel: !s.fuel, advisorSig: !s.advisorSignature, clientSig: !s.clientSignature }
}

export function isReturnValid(s: ReturnFormState, kmStart?: number | null): boolean {
  return !Object.values(returnMissing(s, kmStart)).some(Boolean)
}

export function buildReturnPayload(s: ReturnFormState): ReturnTestDrivePayload {
  const notes = s.notes.trim()
  return {
    km_end: Number(s.kmEnd),
    fuel_gauge_end_level: s.fuel!,
    return_damage: toDamagePayload(s.damage),
    ...(notes ? { return_notes: notes } : {}),
    advisor_signature: s.advisorSignature,
    client_signature: s.clientSignature,
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/returnLogic.test.ts`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/returnLogic.ts jarvis/frontend/src/pages/FoiParcurs/returnLogic.test.ts
git commit -m "feat(foi-parcurs): pure return-form logic (validation, seeding, payload)"
```

---

### Task 3: `TestDriveReturn` component (shared, dual route/embedded mode)

**Files:**
- Create: `jarvis/frontend/src/pages/FoiParcurs/TestDriveReturn.tsx`
- Test: `jarvis/frontend/src/pages/FoiParcurs/TestDriveReturn.test.tsx`

**Interfaces:**
- Consumes: `foiParcursApi.getTestDrive`, `foiParcursApi.submitTestDriveReturn`; `returnLogic` (all); `testDriveDamage.DamageReport`; `@/components/shared/SignatureCanvas` (default export, props `{ onSave, onClear, width, height }`).
- Produces: `default TestDriveReturn({ id?, embedded?, onDone?, onCancel? })`. In route mode (`id` omitted), reads `:id` from `useParams` and navigates back on done. In embedded mode, uses the `id` prop and calls `onDone(contract)` / `onCancel()`.

- [ ] **Step 1: Write the failing test**

```tsx
// jarvis/frontend/src/pages/FoiParcurs/TestDriveReturn.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getTestDrive = vi.fn()
const submitTestDriveReturn = vi.fn().mockResolvedValue({ success: true, contract: { id: 5, status: 'COMPLETED' } })
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getTestDrive, submitTestDriveReturn } }))
// SignatureCanvas is a lazy canvas widget — stub it to a button that emits a signature.
vi.mock('@/components/shared/SignatureCanvas', () => ({
  default: ({ onSave }: { onSave: (s: string) => void }) => (
    <button onClick={() => onSave('data:sig')}>sign</button>
  ),
}))

import TestDriveReturn from './TestDriveReturn'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('TestDriveReturn (embedded)', () => {
  beforeEach(() => { getTestDrive.mockReset(); submitTestDriveReturn.mockClear() })

  it('blocks an already-completed drive', async () => {
    getTestDrive.mockResolvedValue({ contract: { id: 5, status: 'COMPLETED', km_start: 100 } })
    wrap(<TestDriveReturn id={5} embedded onDone={vi.fn()} />)
    expect(await screen.findByText(/deja finalizat/i)).toBeInTheDocument()
  })

  it('submits a valid return and calls onDone', async () => {
    getTestDrive.mockResolvedValue({ contract: { id: 5, status: 'FILLED', km_start: 100, departure_damage: [] } })
    const onDone = vi.fn()
    wrap(<TestDriveReturn id={5} embedded onDone={onDone} />)
    // fill km, fuel, both signatures
    fireEvent.change(await screen.findByLabelText(/km retur/i), { target: { value: '150' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plin' }))
    const signBtns = screen.getAllByRole('button', { name: 'sign' })
    fireEvent.click(signBtns[0]); fireEvent.click(signBtns[1])
    fireEvent.click(screen.getByRole('button', { name: /finalizează/i }))
    await waitFor(() => expect(submitTestDriveReturn).toHaveBeenCalledWith(5, expect.objectContaining({ km_end: 150, fuel_gauge_end_level: 'Plin' })))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/TestDriveReturn.test.tsx`
Expected: FAIL — module `./TestDriveReturn` not found.

- [ ] **Step 3: Implement `TestDriveReturn.tsx`**

```tsx
// jarvis/frontend/src/pages/FoiParcurs/TestDriveReturn.tsx
import { useEffect, useRef, useState, Suspense, lazy } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ChevronLeft } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { foiParcursApi } from '@/api/foiParcurs'
import type { ReturnFuelLevel } from '@/types/foiParcurs'
import { DamageReport } from './testDriveDamage'
import {
  seedReturnDamage, kmEndError, returnMissing, isReturnValid, buildReturnPayload,
  type ReturnFormState,
} from './returnLogic'

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))
const ADVISOR_SIG_KEY = 'fp_advisor_signature'
const FUEL_OPTIONS: ReturnFuelLevel[] = ['Gol', '1/4', '1/2', '3/4', 'Plin']

interface Props {
  id?: number
  embedded?: boolean
  onDone?: (contract: unknown) => void
  onCancel?: () => void
}

export default function TestDriveReturn({ id: idProp, embedded, onDone, onCancel }: Props) {
  const params = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const id = idProp ?? (params.id ? Number(params.id) : undefined)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['fp-test-drive', id],
    queryFn: () => foiParcursApi.getTestDrive(id!),
    enabled: id != null,
  })
  const contract = data?.contract
  const kmStart = contract?.km_start != null ? Number(contract.km_start) : undefined

  const [form, setForm] = useState<ReturnFormState>({
    kmEnd: '', fuel: null, damage: seedReturnDamage({ departure_damage: null }).damage,
    notes: '', advisorSignature: '', clientSignature: '',
  })
  const [showDamage, setShowDamage] = useState(false)
  const [attempted, setAttempted] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Seed advisor signature (reused across submissions) once.
  useEffect(() => {
    try { const s = localStorage.getItem(ADVISOR_SIG_KEY); if (s) setForm((f) => ({ ...f, advisorSignature: s })) } catch { /* ignore */ }
  }, [])

  // Seed damage from departure once the contract loads.
  const seededRef = useRef(false)
  useEffect(() => {
    if (seededRef.current || !contract) return
    seededRef.current = true
    const { damage, seeded } = seedReturnDamage(contract)
    if (seeded) { setForm((f) => ({ ...f, damage })); setShowDamage(true) }
  }, [contract])

  const mutation = useMutation({
    mutationFn: () => foiParcursApi.submitTestDriveReturn(id!, buildReturnPayload(form)),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
      queryClient.invalidateQueries({ queryKey: ['fp-test-drive', id] })
      queryClient.invalidateQueries({ queryKey: ['odometer-history'] })
      if (embedded) onDone?.(res.contract)
      else navigate(`/app/foi-parcurs?tab=parcurs`)
    },
    onError: (e: unknown) => setSubmitError(e instanceof Error ? e.message : 'Trimiterea a eșuat.'),
  })

  const goBack = () => { if (embedded) onCancel?.(); else navigate('/app/foi-parcurs') }
  const kmErr = kmEndError(form.kmEnd, kmStart)
  const missing = returnMissing(form, kmStart)
  const err = (bad: boolean) => attempted && bad
  const set = (patch: Partial<ReturnFormState>) => setForm((f) => ({ ...f, ...patch }))

  const handleSubmit = () => {
    if (mutation.isPending) return
    if (!isReturnValid(form, kmStart)) { setAttempted(true); return }
    setSubmitError(null)
    mutation.mutate()
  }

  const Header = (
    <div className="flex items-center gap-2 mb-4">
      <Button variant="ghost" size="icon" onClick={goBack}><ChevronLeft className="h-4 w-4" /></Button>
      <h2 className="text-lg font-semibold">Retur test drive</h2>
    </div>
  )

  if (id == null) return <div className="p-4">{Header}<p className="text-sm text-destructive">Lipsă id.</p></div>
  if (isLoading) return <div className="p-4">{Header}<Skeleton className="h-48 w-full" /></div>
  if (isError || !contract) return <div className="p-4">{Header}<p className="text-sm text-destructive">Nu s-a putut încărca test drive-ul.</p></div>
  if (contract.status === 'COMPLETED') return <div className="p-4">{Header}<p className="text-sm text-muted-foreground py-8 text-center">Acest test drive a fost deja finalizat.</p></div>

  return (
    <div className="p-4 max-w-2xl mx-auto">
      {Header}
      <div className="space-y-4">
        {/* KM retur */}
        <div className="space-y-1.5">
          <Label htmlFor="km-retur" className="text-xs">Km retur</Label>
          <Input id="km-retur" inputMode="numeric" value={form.kmEnd}
            onChange={(e) => set({ kmEnd: e.target.value })}
            className={cn(err(missing.km) && 'ring-2 ring-destructive')} />
          {kmErr && <p className="text-xs text-destructive">{kmErr}</p>}
        </div>

        {/* Combustibil */}
        <div className="space-y-1.5">
          <Label className="text-xs">Nivel combustibil</Label>
          <div className={cn('flex gap-1', err(missing.fuel) && 'ring-2 ring-destructive rounded-md p-0.5')}>
            {FUEL_OPTIONS.map((f) => (
              <Button key={f} type="button" variant={form.fuel === f ? 'default' : 'outline'} size="sm"
                className="flex-1" onClick={() => set({ fuel: f })}>{f}</Button>
            ))}
          </div>
        </div>

        {/* Raport avarii (seeded from departure) */}
        <div className="space-y-1.5">
          <Button type="button" variant="outline" size="sm" onClick={() => setShowDamage((s) => !s)}>
            {showDamage ? 'Ascunde' : 'Arată'} raport avarii
          </Button>
          {showDamage && <DamageReport value={form.damage} onChange={(damage) => set({ damage })} />}
        </div>

        {/* Observații */}
        <div className="space-y-1.5">
          <Label htmlFor="notes" className="text-xs">Observații (opțional)</Label>
          <Textarea id="notes" value={form.notes} onChange={(e) => set({ notes: e.target.value })} />
        </div>

        {/* Semnătură consilier (reused) */}
        <div className="space-y-1.5">
          <Label className={cn('text-xs', err(missing.advisorSig) && 'text-destructive')}>Semnătură consilier</Label>
          {form.advisorSignature ? (
            <div className="flex items-center justify-between rounded-md border bg-muted/40 p-2">
              <span className="text-sm text-green-600 flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" />Semnătură salvată</span>
              <Button type="button" variant="ghost" size="sm" onClick={() => set({ advisorSignature: '' })}>Schimbă</Button>
            </div>
          ) : (
            <Suspense fallback={<Skeleton className="h-[200px] w-full" />}>
              <SignatureCanvas onSave={(sig) => { set({ advisorSignature: sig }); try { localStorage.setItem(ADVISOR_SIG_KEY, sig) } catch { /* ignore */ } }} onClear={() => set({ advisorSignature: '' })} width={500} height={200} />
            </Suspense>
          )}
        </div>

        {/* Semnătură client (fresh) */}
        <div className="space-y-1.5">
          <Label className={cn('text-xs', err(missing.clientSig) && 'text-destructive')}>Semnătură client</Label>
          {form.clientSignature ? (
            <div className="flex items-center justify-between rounded-md border bg-muted/40 p-2">
              <span className="text-sm text-green-600 flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" />Semnat</span>
              <Button type="button" variant="ghost" size="sm" onClick={() => set({ clientSignature: '' })}>Șterge</Button>
            </div>
          ) : (
            <Suspense fallback={<Skeleton className="h-[200px] w-full" />}>
              <SignatureCanvas onSave={(sig) => set({ clientSignature: sig })} onClear={() => set({ clientSignature: '' })} width={500} height={200} />
            </Suspense>
          )}
        </div>

        {submitError && <p className="text-sm text-destructive">{submitError}</p>}
        {attempted && !isReturnValid(form, kmStart) && <p className="text-sm text-destructive">Completează câmpurile marcate cu roșu.</p>}

        <Button className={cn('w-full', attempted && !isReturnValid(form, kmStart) && 'bg-destructive hover:bg-destructive')}
          onClick={handleSubmit} disabled={mutation.isPending}>
          {mutation.isPending ? 'Se trimite…' : 'Finalizează retur'}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/TestDriveReturn.test.tsx`
Expected: PASS (2 tests). If `Textarea` import path differs, confirm with `ls src/components/ui/textarea.tsx`.

- [ ] **Step 5: Typecheck**

Run: `cd jarvis/frontend && npx tsc -b --noEmit` (or `npm run build`)
Expected: no new type errors.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/TestDriveReturn.tsx jarvis/frontend/src/pages/FoiParcurs/TestDriveReturn.test.tsx
git commit -m "feat(foi-parcurs): TestDriveReturn component (dual route/embedded)"
```

---

### Task 4: Return route + `SessionsTab` export + "Retur" row action (closes standalone gap)

**Files:**
- Modify: `jarvis/frontend/src/App.tsx` (lazy import + one route, near line 60 + 242)
- Modify: `jarvis/frontend/src/pages/FoiParcurs/index.tsx` (`export` `SessionsTab` at line 1012; add a "Retur" action in the session row)
- Test: `jarvis/frontend/src/pages/FoiParcurs/SessionsTab.retur.test.tsx`

**Interfaces:**
- Consumes: `TestDriveReturn` (Task 3); `sessionStatus` (existing).
- Produces: `export function SessionsTab({ companyId, brand })`; route `/app/foi-parcurs/test-drive/:id/return`.

- [ ] **Step 1: Export `SessionsTab`**

In `jarvis/frontend/src/pages/FoiParcurs/index.tsx` line 1012, change:
`function SessionsTab({ companyId, brand }: { companyId: number; brand: string }) {`
→ `export function SessionsTab({ companyId, brand }: { companyId: number; brand: string }) {`

- [ ] **Step 2: Add the route**

In `jarvis/frontend/src/App.tsx`, add the lazy import next to the existing FoiParcurs imports (~line 61):

```tsx
const TestDriveReturn = lazy(() => import('./pages/FoiParcurs/TestDriveReturn'))
```

Then add the route immediately after the `foi-parcurs/test-drive` route (line 242):

```tsx
        <Route path="foi-parcurs/test-drive/:id/return" element={<Guard flag="can_access_carpark"><SuspensePage><TestDriveReturn /></SuspensePage></Guard>} />
```

- [ ] **Step 3: Write the failing test for the row action**

```tsx
// jarvis/frontend/src/pages/FoiParcurs/SessionsTab.retur.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const getContracts = vi.fn().mockResolvedValue({
  contracts: [
    { id: 11, status: 'FILLED', td_status: 'driving', vin: 'VF1', client_name: 'Ion', departure_datetime: '2026-07-27T10:00', km_start: 100 },
    { id: 12, status: 'COMPLETED', td_status: 'complete', vin: 'VF2', client_name: 'Ana', departure_datetime: '2026-07-20T10:00', km_start: 200 },
  ], total: 2, page: 1, per_page: 1000,
})
vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: { getContracts, getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }) } }))

import { SessionsTab } from './index'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('SessionsTab Retur action', () => {
  it('shows a Retur link for a driving session, not for a completed one', async () => {
    wrap(<SessionsTab companyId={11} brand="" />)
    const returLinks = await screen.findAllByRole('link', { name: /retur/i })
    // exactly one Retur (for the driving row #11), pointing at its return route
    expect(returLinks).toHaveLength(1)
    expect(returLinks[0]).toHaveAttribute('href', '/app/foi-parcurs/test-drive/11/return')
  })
})
```

> Note: if `SessionsTab` renders rows differently (e.g. no `<a>` element), adapt the assertion to the actual element once Step 4 lands, keeping the intent: one Retur affordance for driving/intarziat rows, none for finalizat.

- [ ] **Step 4: Add the Retur action to the row**

In `SessionsTab`'s row rendering (inside the `.map` over filtered sessions), where row actions live, add — for sessions whose status key is `driving` or `intarziat` — a link to the return route. Use the existing `sessionStatus(c)` and React Router's `Link`:

```tsx
{(sessionStatus(c).key === 'driving' || sessionStatus(c).key === 'intarziat') && (
  <Link
    to={`/app/foi-parcurs/test-drive/${c.id}/return`}
    className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
    onClick={(e) => e.stopPropagation()}
  >
    <RotateCcw className="h-3.5 w-3.5" /> Retur
  </Link>
)}
```

Add imports at the top of `index.tsx` if missing: `import { Link } from 'react-router-dom'` and `RotateCcw` to the existing `lucide-react` import.

- [ ] **Step 5: Run tests**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/SessionsTab.retur.test.tsx`
Expected: PASS (1 test). Then `npx tsc -b --noEmit` — clean.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/App.tsx jarvis/frontend/src/pages/FoiParcurs/index.tsx jarvis/frontend/src/pages/FoiParcurs/SessionsTab.retur.test.tsx
git commit -m "feat(foi-parcurs): return route + Retur row action; export SessionsTab"
```

---

### Task 5: Make `TestDriveForm` embeddable (backward-compatible)

**Files:**
- Modify: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx`
- Test: `jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.embedded.test.tsx`

**Interfaces:**
- Produces: `default TestDriveForm(props?: { embedded?: boolean; activateId?: number; initialCompanyId?: number; onDone?: (contract: FoiContract) => void; onCancel?: () => void })`. With no props → unchanged route behavior.

- [ ] **Step 1: Write the failing test**

```tsx
// jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.embedded.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 11, company: 'PREMIUM' }] }),
  getVehicles: vi.fn().mockResolvedValue({ vehicles: [] }),
  getTestDrive: vi.fn(), getGeneralConditions: vi.fn().mockResolvedValue({ text: '', brand: '' }),
} }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (sel: (s: unknown) => unknown) => sel({ user: { name: 'Test Advisor' } }) }))

import TestDriveForm from './TestDriveForm'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('TestDriveForm embedded mode', () => {
  it('renders a Cancel affordance wired to onCancel when embedded', async () => {
    const onCancel = vi.fn()
    wrap(<TestDriveForm embedded onCancel={onCancel} onDone={vi.fn()} />)
    // In embedded mode the "back to Driving Hub" nav is replaced by an onCancel-driven control.
    const cancel = await screen.findByRole('button', { name: /închide|anulează|înapoi/i })
    cancel.click()
    expect(onCancel).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/TestDriveForm.embedded.test.tsx`
Expected: FAIL — `TestDriveForm` ignores props / no onCancel control.

- [ ] **Step 3: Add props + reroute navigation through callbacks**

In `TestDriveForm.tsx`:
1. Change the signature (line 92) to accept props:

```tsx
interface TestDriveFormProps {
  embedded?: boolean
  activateId?: number
  initialCompanyId?: number
  onDone?: (contract: FoiContract) => void
  onCancel?: () => void
}

export default function TestDriveForm({ embedded, activateId: activateIdProp, initialCompanyId, onDone, onCancel }: TestDriveFormProps = {}) {
```

2. Replace the search-param activate id (lines 97-99) with a prop-first resolution:

```tsx
  const [searchParams] = useSearchParams()
  const activateId = activateIdProp ?? (searchParams.get('activate') ? Number(searchParams.get('activate')) : null)
  const isActivating = activateId != null
```

3. Seed the initial company when embedded (after the `companyId` state, ~line 102):

```tsx
  useEffect(() => { if (initialCompanyId && companyId == null) setCompanyId(initialCompanyId) }, [initialCompanyId]) // eslint-disable-line react-hooks/exhaustive-deps
```

4. Route the three success handlers through `onDone` when embedded. Change `onSuccess: (data) => setSubmittedContract(data.contract)` in all three mutations (lines 290, 294, 375) to:

```tsx
    onSuccess: (data) => { if (embedded) onDone?.(data.contract); else setSubmittedContract(data.contract) },
```

5. Replace the two hard `navigate('/app/foi-parcurs')` header/back controls (lines ~447, 460) and the activate redirect (line 414) with callback-aware versions:

```tsx
  const handleBack = () => { if (embedded) onCancel?.(); else navigate('/app/foi-parcurs') }
```
- line 414: `if (isActivating) { if (embedded) onCancel?.(); else navigate('/app/foi-parcurs/test-drive', { replace: true }) }`
- the header back button (~460) and success-screen back button (~447) call `handleBack` instead of `navigate('/app/foi-parcurs')`. Ensure at least one always-visible control (the header back button) renders in embedded mode so `onCancel` is reachable, with an accessible name matching `/închide|anulează|înapoi/i` (e.g. keep the existing "Înapoi" label).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis/frontend && npx vitest run src/pages/FoiParcurs/TestDriveForm.embedded.test.tsx`
Expected: PASS. Then re-run the standalone route smoke: `npx vitest run src/pages/FoiParcurs` — no regressions.

- [ ] **Step 5: Typecheck**

Run: `cd jarvis/frontend && npx tsc -b --noEmit`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.tsx jarvis/frontend/src/pages/FoiParcurs/TestDriveForm.embedded.test.tsx
git commit -m "refactor(foi-parcurs): make TestDriveForm embeddable (props, callbacks)"
```

---

### Task 6: `HubDrivingPanel` (in-page panel with overlay forms)

**Files:**
- Create: `jarvis/frontend/src/pages/Hub/HubDrivingPanel.tsx`
- Test: `jarvis/frontend/src/pages/Hub/HubDrivingPanel.test.tsx`

**Interfaces:**
- Consumes: `SessionsTab`, `CalendarTab` (both from `@/pages/FoiParcurs/index` — `CalendarTab` re-exported there or imported from `./CalendarTab`); `TestDriveForm` + `TestDriveReturn` (embedded); `foiParcursApi.getCompanies/getBrands`; `usePersistedState` (`@/lib/utils`).
- Produces: `default HubDrivingPanel()`.

- [ ] **Step 1: Write the failing test**

```tsx
// jarvis/frontend/src/pages/Hub/HubDrivingPanel.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/foiParcurs', () => ({ foiParcursApi: {
  getCompanies: vi.fn().mockResolvedValue({ companies: [{ id: 11, company: 'PREMIUM' }] }),
  getBrands: vi.fn().mockResolvedValue({ brands: [] }),
} }))
vi.mock('@/pages/FoiParcurs/index', () => ({
  SessionsTab: ({ companyId }: { companyId: number }) => <div>sessions:{companyId}</div>,
  CalendarTab: ({ companyId }: { companyId: number }) => <div>calendar:{companyId}</div>,
}))
vi.mock('@/pages/FoiParcurs/TestDriveForm', () => ({ default: ({ onCancel }: { onCancel: () => void }) => <div>form<button onClick={onCancel}>x</button></div> }))
vi.mock('@/pages/FoiParcurs/TestDriveReturn', () => ({ default: () => <div>return</div> }))

import HubDrivingPanel from './HubDrivingPanel'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>)
}

describe('HubDrivingPanel', () => {
  it('renders the Sessions tab by default and can open the New overlay', async () => {
    wrap(<HubDrivingPanel />)
    expect(await screen.findByText(/sessions:11/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /driving session nou/i }))
    expect(screen.getByText('form')).toBeInTheDocument()
  })

  it('switches to the Calendar tab', async () => {
    wrap(<HubDrivingPanel />)
    fireEvent.click(await screen.findByRole('tab', { name: /calendar/i }))
    expect(await screen.findByText(/calendar:11/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/HubDrivingPanel.test.tsx`
Expected: FAIL — module `./HubDrivingPanel` not found.

- [ ] **Step 3: Implement `HubDrivingPanel.tsx`**

```tsx
// jarvis/frontend/src/pages/Hub/HubDrivingPanel.tsx
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePersistedState } from '@/lib/utils'
import { foiParcursApi } from '@/api/foiParcurs'
import { SessionsTab, CalendarTab } from '@/pages/FoiParcurs/index'
import TestDriveForm from '@/pages/FoiParcurs/TestDriveForm'
import TestDriveReturn from '@/pages/FoiParcurs/TestDriveReturn'

type Overlay = null | { kind: 'new' } | { kind: 'activate'; id: number } | { kind: 'return'; id: number }
type PanelTab = 'sessions' | 'calendar'

export default function HubDrivingPanel() {
  const [tab, setTab] = usePersistedState<PanelTab>('hub-driving-tab', 'sessions')
  const [companyId, setCompanyId] = usePersistedState<number>('hub-driving-company', 0)
  const [brand, setBrand] = usePersistedState<string>('hub-driving-brand', '')
  const [overlay, setOverlay] = useState<Overlay>(null)

  const { data: companiesData } = useQuery({ queryKey: ['fp-companies'], queryFn: () => foiParcursApi.getCompanies() })
  const companies = companiesData?.companies ?? []
  useEffect(() => { if (companyId === 0 && companies.length) setCompanyId(companies[0].id) }, [companies]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data: brandsData } = useQuery({ queryKey: ['fp-brands', companyId], queryFn: () => foiParcursApi.getBrands(companyId), enabled: companyId > 0 })
  const brands = brandsData?.brands ?? []
  useEffect(() => {
    const list = brandsData?.brands ?? []
    if (!list.length) { if (brand !== '') setBrand('') }
    else if (!list.includes(brand)) setBrand(list[0])
  }, [brandsData]) // eslint-disable-line react-hooks/exhaustive-deps

  const closeOverlay = () => setOverlay(null)

  return (
    <div className="space-y-4">
      {/* Selector + primary action */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={String(companyId)} onValueChange={(v) => setCompanyId(Number(v))}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Selectează compania" /></SelectTrigger>
          <SelectContent>{companies.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>)}</SelectContent>
        </Select>
        {brands.length > 0 && (
          <Select value={brand} onValueChange={setBrand}>
            <SelectTrigger className="w-44"><SelectValue placeholder="Brand" /></SelectTrigger>
            <SelectContent>{brands.map((b) => <SelectItem key={b} value={b}>{b}</SelectItem>)}</SelectContent>
          </Select>
        )}
        <Button className="ml-auto" onClick={() => setOverlay({ kind: 'new' })}>
          <Plus className="h-4 w-4 mr-1.5" /> Driving Session nou
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as PanelTab)}>
        <TabsList>
          <TabsTrigger value="sessions">Sesiuni</TabsTrigger>
          <TabsTrigger value="calendar">Calendar</TabsTrigger>
        </TabsList>
      </Tabs>

      {companyId > 0 && tab === 'sessions' && <SessionsTab companyId={companyId} brand={brand} />}
      {companyId > 0 && tab === 'calendar' && <CalendarTab companyId={companyId} brand={brand} />}

      {/* Full-screen overlay inside the Hub */}
      {overlay && (
        <div className="fixed inset-0 z-50 bg-background overflow-y-auto">
          <div className="sticky top-0 z-10 flex items-center justify-end border-b bg-background p-2">
            <Button variant="ghost" size="icon" onClick={closeOverlay}><X className="h-5 w-5" /></Button>
          </div>
          {overlay.kind === 'new' && (
            <TestDriveForm embedded initialCompanyId={companyId || undefined} onDone={closeOverlay} onCancel={closeOverlay} />
          )}
          {overlay.kind === 'activate' && (
            <TestDriveForm embedded activateId={overlay.id} onDone={closeOverlay} onCancel={closeOverlay} />
          )}
          {overlay.kind === 'return' && (
            <TestDriveReturn embedded id={overlay.id} onDone={closeOverlay} onCancel={closeOverlay} />
          )}
        </div>
      )}
    </div>
  )
}
```

> If `CalendarTab` is not re-exported from `pages/FoiParcurs/index`, import it directly: `import { CalendarTab } from '@/pages/FoiParcurs/CalendarTab'` (it is exported there) and only `SessionsTab` from the index.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/HubDrivingPanel.test.tsx`
Expected: PASS (2 tests). Adjust the `CalendarTab` import in the mock/source to match the real export location if the first run flags a missing export.

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/pages/Hub/HubDrivingPanel.tsx jarvis/frontend/src/pages/Hub/HubDrivingPanel.test.tsx
git commit -m "feat(hub): HubDrivingPanel — Sessions/Calendar + overlay forms"
```

---

### Task 7: Wire the Driving Sessions tile into the Hub

**Files:**
- Modify: `jarvis/frontend/src/pages/Hub/index.tsx` (`ActiveModule` line 80; `appTiles` line 94; `visibleTiles` gate line 218; render switch line 323; lazy import near line 69)
- Test: `jarvis/frontend/src/pages/Hub/hubDrivingTile.test.tsx`

**Interfaces:**
- Consumes: `HubDrivingPanel` (Task 6); `authUser.can_access_carpark`.

- [ ] **Step 1: Add the lazy import + union + tile + gate + render**

1. Near the other lazy imports (~line 69):

```tsx
const HubDrivingPanel = lazy(() => import('@/pages/Hub/HubDrivingPanel'))
```

2. Extend the `ActiveModule` union (line 80): add `| 'driving'`.

3. Add to `appTiles` (line 94 array). `Car` is already imported:

```tsx
  { key: 'driving', label: 'Driving Sessions', shortLabel: 'Driving', icon: Car, bg: 'bg-teal-600', fg: 'text-white' },
```

4. In `tileCounts` (line 209) add `driving: -1` (always show when allowed).

5. In `visibleTiles` filter (line 218-225), add a gate before the generic count check:

```tsx
      if (t.key === 'driving' && !authUser?.can_access_carpark) return false
```

6. In the render switch (line 323-336) add:

```tsx
          {activeModule === 'driving' && (
            <Suspense fallback={<div className="py-8 text-center text-muted-foreground text-sm">Loading...</div>}>
              <HubDrivingPanel />
            </Suspense>
          )}
```

- [ ] **Step 2: Write the test**

```tsx
// jarvis/frontend/src/pages/Hub/hubDrivingTile.test.tsx
import { describe, it, expect } from 'vitest'
import { appTiles } from './index' // if appTiles is not exported, export it (const appTiles) for testability

describe('Driving Sessions tile', () => {
  it('is registered in appTiles as an in-page panel (no route)', () => {
    const tile = appTiles.find((t) => t.key === 'driving')
    expect(tile).toBeDefined()
    expect(tile?.route).toBeUndefined()
    expect(tile?.label).toBe('Driving Sessions')
  })
})
```

To make this importable, add `export` to the `appTiles` declaration (line 94): `export const appTiles: AppTile[] = [`.

- [ ] **Step 3: Run test to verify it passes**

Run: `cd jarvis/frontend && npx vitest run src/pages/Hub/hubDrivingTile.test.tsx`
Expected: PASS.

- [ ] **Step 4: Full typecheck + build**

Run: `cd jarvis/frontend && npm run build`
Expected: build succeeds, no type errors.

- [ ] **Step 5: Manual smoke (webapp-testing or dev server)**

- Log in as a user with `can_access_carpark` → the Hub shows a **Driving Sessions** tile; open it → Sesiuni list + Calendar tabs + "Driving Session nou".
- A user without `can_access_carpark` → tile is absent.
- Open a driving session's **Retur** → fill km/fuel/signatures → Finalizează → session flips to **Finalizat**; list refreshes.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/pages/Hub/index.tsx jarvis/frontend/src/pages/Hub/hubDrivingTile.test.tsx
git commit -m "feat(hub): add Driving Sessions tile (gated on can_access_carpark)"
```

---

## Self-Review

**Spec coverage:**
- Return API + types → Task 1. ✓
- Return component (km≥start, fuel Gol…Plin, damage seeded from departure, dual signatures, COMPLETED guard) → Tasks 2–3. ✓
- Return route + standalone SessionsTab entry (gap closed for standalone module) → Task 4. ✓
- Reuse SessionsTab/CalendarTab + embeddable TestDriveForm → Tasks 4–5. ✓
- In-page HubDrivingPanel with overlay forms → Task 6. ✓
- Hub tile gated on `can_access_carpark` → Task 7. ✓
- Cache invalidation `['foi-contracts-all']` → Task 3 (mutation onSuccess). ✓
- Datetime convention / 7-zone damage / return-fuel type → Global Constraints + Tasks 1–3. ✓
- Testing (vitest) → every task. ✓
- No backend changes → confirmed; the return endpoint already exists. ✓

**Placeholder scan:** No TBD/TODO. Every code step shows real code; the two "adapt to actual export/row markup" notes are bounded fallbacks with the exact intent stated, not open-ended placeholders.

**Type consistency:** `ReturnFuelLevel`/`ReturnTestDrivePayload` defined in Task 1 and used identically in Tasks 2–3; `ReturnFormState` shape identical across `returnLogic.ts` and `TestDriveReturn.tsx`; `submitTestDriveReturn(id, payload)` signature consistent; `SessionsTab({companyId, brand})` export matches its consumers in Tasks 4 & 6; `TestDriveForm` embedded prop names (`embedded`, `activateId`, `initialCompanyId`, `onDone`, `onCancel`) consistent across Tasks 5 & 6.

## Risks / notes for the implementer
- `TestDriveForm` (Task 5) is an 818-line production component — keep the default (no-props) path byte-for-byte behaviorally unchanged; the callback branches are `if (embedded) … else <existing>`.
- Confirm `usePersistedState` is exported from `@/lib/utils` (Hub already imports it). If the FoiParcurs shell's helper is named `usePersistentState` from a different module, the panel still uses `@/lib/utils`'s `usePersistedState`.
- If `CalendarTab` needs a `brand` value it currently expects as non-empty, pass `brand` as-is (empty string is already handled by the standalone shell).
