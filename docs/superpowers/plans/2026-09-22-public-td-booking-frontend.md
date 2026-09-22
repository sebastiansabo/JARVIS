# Public Test-Drive Booking — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the public booking page (`/td/:slug`), the email confirm/cancel landing pages, and the staff admin UI (in the Driving Hub) on top of the green backend API from the backend plan.

**Architecture:** React 19 SPA (Vite + TS + Tailwind 4 + shadcn/ui), served same-origin by Flask. Public pages live OUTSIDE the `/app` auth shell (siblings of `/f/:slug`). All calls use the shared `api` client (relative `BASE_URL`, `credentials:'same-origin'`); public endpoints return 200/404/409/410/429 (never 401). Phone entry uses the existing `composePhone` E.164 helper.

**Tech Stack:** React 19, react-router-dom, @tanstack/react-query, shadcn/ui, the shared `@/api/client` `api` object.

**Spec:** `docs/superpowers/specs/2026-09-22-public-test-drive-booking-design.md`
**Depends on:** `docs/superpowers/plans/2026-09-22-public-td-booking-backend.md` (must be merged & green first).

## Global Constraints

- Target `jarvis/frontend/src/` (React), never Jinja. (`CLAUDE.md`)
- No env-var base URL: `BASE_URL=''`, same-origin. Public methods hit the backend paths directly (`/api/td/...`). (`api/client.ts`)
- The shared client hard-redirects to `/login` on **401** — public pages must never trigger a 401 (backend already guarantees this; don't add auth headers on public calls).
- Response envelopes are unwrapped per-call via the TS generic on each `api.get/post<...>()` — declare the shape and read the named key.
- Phone → E.164 via `composePhone(dialCode, rawNumber)` from `pages/FoiParcurs/phoneFormat.ts`; validate before enabling submit.
- **Verification (AUTHORITATIVE — overrides task-step mentions of Playwright):** (1) HARD gate `cd jarvis/frontend && npm run build` (`tsc -b && vite build`) must exit 0 with zero TS errors; (2) **vitest IS configured** (jsdom + @testing-library/react, 62 existing tests) — write real unit/component tests as `*.test.ts`/`*.test.tsx` next to the source (mirror existing `src/api/*.test.ts` and `src/lib/*.test.ts`), run with `npm run test -- <file>`. **NO Playwright** (not installed) and the full app **cannot boot locally** (pre-existing `init_db`/schema_hr bug), so there is NO end-to-end run — rely on build + vitest + review. (3) Commit **SOURCE only** (`jarvis/frontend/src/**`); `jarvis/static/react/` is the gitignored build output — never `git add` it. Run `npm ci` once if `node_modules` is missing (already installed in this worktree).

---

### Task 1: Typed API client `api/td.ts`

**Files:**
- Create: `jarvis/frontend/src/api/td.ts`

**Interfaces:**
- Produces:
  - `tdApi.getPage(slug): Promise<TdPublicPage>` → `GET /api/td/pages/${slug}`
  - `tdApi.submitBooking(slug, body): Promise<{booking_id:number; status:string}>` → `POST /api/td/pages/${slug}/bookings`
  - `tdApi.confirm(token): Promise<{status:string; fp_id?:number}>` → `POST /api/td/bookings/confirm`
  - `tdApi.cancel(token): Promise<{status:string}>` → `POST /api/td/bookings/cancel`
  - Types `TdSlot`, `TdCar`, `TdPublicPage`.

- [ ] **Step 1: Write the module** (mirror `api/forms.ts:84-100`)

```ts
// jarvis/frontend/src/api/td.ts
import { api } from './client'

export interface TdSlot { id: number; car_id: number; vin: string; starts_at: string; ends_at: string }
export interface TdCar { id: number; vin: string }
export interface TdPublicPage {
  page: { title?: string; intro?: string; thank_you?: string }
  cars: TdCar[]
  slots: TdSlot[]
}

export const tdApi = {
  getPage: (slug: string) => api.get<TdPublicPage>(`/api/td/pages/${slug}`),

  submitBooking: (slug: string, body: {
    slot_id: number; name: string; phone: string; email: string
    utm?: Record<string, string>
  }) => api.post<{ booking_id: number; status: string }>(`/api/td/pages/${slug}/bookings`, body),

  confirm: (token: string) =>
    api.post<{ status: string; fp_id?: number }>(`/api/td/bookings/confirm`, { token }),

  cancel: (token: string) =>
    api.post<{ status: string }>(`/api/td/bookings/cancel`, { token }),
}
```

- [ ] **Step 2: Typecheck** — `cd jarvis/frontend && npm run build` → 0 errors.
- [ ] **Step 3: Commit** — `git commit -m "feat(td): frontend api client"`

---

### Task 2: Public routes in `App.tsx`

**Files:**
- Modify: `jarvis/frontend/src/App.tsx` (lazy imports + 3 public routes outside `/app`)

**Interfaces:**
- Consumes: `PublicTdBooking`, `TdConfirm`, `TdCancel` (Tasks 3–4).
- Produces routes: `/td/confirm`, `/td/cancel` (declared **before** `/td/:slug` so they don't get captured), `/td/:slug`.

- [ ] **Step 1: Add lazy imports** (near `App.tsx:46`)

```tsx
const PublicTdBooking = lazy(() => import('./pages/Public/PublicTdBooking'))
const TdConfirm = lazy(() => import('./pages/Public/TdConfirm'))
const TdCancel = lazy(() => import('./pages/Public/TdCancel'))
```

- [ ] **Step 2: Add the routes** as siblings before the `/app` element (next to the `/f/:slug` route at `App.tsx:175`)

```tsx
      {/* Public test-drive booking — no auth, no layout. Specific routes first. */}
      <Route path="/td/confirm" element={<SuspensePage><TdConfirm /></SuspensePage>} />
      <Route path="/td/cancel" element={<SuspensePage><TdCancel /></SuspensePage>} />
      <Route path="/td/:slug" element={<SuspensePage><PublicTdBooking /></SuspensePage>} />
```

- [ ] **Step 3: Typecheck** — `npm run build` → 0 errors (will still fail import until Tasks 3–4 exist; do this task's build after Task 4, or stub the pages first).
- [ ] **Step 4: Commit** — `git commit -m "feat(td): public routes in App.tsx"`

---

### Task 3: `PublicTdBooking.tsx` (the booking page)

**Files:**
- Create: `jarvis/frontend/src/pages/Public/PublicTdBooking.tsx`

**Interfaces:**
- Consumes: `tdApi` (Task 1), `composePhone` + `COUNTRY_DIAL_CODES` (`pages/FoiParcurs/phoneFormat.ts`).
- Produces: default-exported page component reading `:slug`.

Behavior: fetch page config; render intro; group `slots` by `car_id` (label each car by `vin` — the public copy can map to a friendlier name later); let the user pick a car + slot, enter name / phone (dial-code + number → `composePhone`) / email; submit → on success show a "check your email to confirm" state; handle 409 (slot taken → refetch slots), 429 (rate limited), 403 (closed).

- [ ] **Step 1: Write the component** (mirror `pages/Public/PublicForm.tsx` structure)

```tsx
// jarvis/frontend/src/pages/Public/PublicTdBooking.tsx
import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { tdApi, type TdSlot } from '@/api/td'
import { composePhone, COUNTRY_DIAL_CODES } from '@/pages/FoiParcurs/phoneFormat'
import { ApiError } from '@/api/client'

export default function PublicTdBooking() {
  const { slug } = useParams<{ slug: string }>()
  const [selected, setSelected] = useState<TdSlot | null>(null)
  const [name, setName] = useState('')
  const [dialCode, setDialCode] = useState('+40')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [done, setDone] = useState(false)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['td-page', slug],
    queryFn: () => tdApi.getPage(slug!),
    enabled: !!slug,
  })

  const { full: phoneFull, valid: phoneValid } = composePhone(dialCode, phone)
  const carsById = useMemo(() => Object.fromEntries((data?.cars || []).map(c => [c.id, c])), [data])
  const slotsByCar = useMemo(() => {
    const m: Record<number, TdSlot[]> = {}
    for (const s of data?.slots || []) (m[s.car_id] ||= []).push(s)
    return m
  }, [data])

  const submit = useMutation({
    mutationFn: () => tdApi.submitBooking(slug!, {
      slot_id: selected!.id, name, phone: phoneFull, email,
    }),
    onSuccess: () => setDone(true),
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) { refetch(); setSelected(null) }
    },
  })

  if (isLoading) return <CenteredMessage title="Se încarcă…" />
  if (isError || !data) return <CenteredMessage title="Pagina nu este disponibilă" />
  if (done) return <CenteredMessage title="Verifică emailul"
    body={data.page.thank_you || 'Ți-am trimis un link de confirmare pe email.'} />

  const canSubmit = !!selected && name.trim() && phoneValid && /.+@.+\..+/.test(email) && !submit.isPending

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-2xl mx-auto space-y-6">
        <header>
          <h1 className="text-2xl font-bold">{data.page.title || 'Programează un test drive'}</h1>
          {data.page.intro && <p className="text-muted-foreground">{data.page.intro}</p>}
        </header>

        {data.cars.map(car => (
          <section key={car.id} className="rounded-lg border bg-white p-4">
            <h2 className="font-semibold mb-2">{car.vin}</h2>
            <div className="flex flex-wrap gap-2">
              {(slotsByCar[car.id] || []).map(s => (
                <button key={s.id}
                  onClick={() => setSelected(s)}
                  className={`px-3 py-1 rounded border text-sm ${selected?.id === s.id ? 'bg-black text-white' : 'bg-white'}`}>
                  {new Date(s.starts_at).toLocaleString('ro-RO', { dateStyle: 'short', timeStyle: 'short' })}
                </button>
              ))}
              {!(slotsByCar[car.id] || []).length && <span className="text-sm text-muted-foreground">Niciun interval liber</span>}
            </div>
          </section>
        ))}

        <section className="rounded-lg border bg-white p-4 space-y-3">
          <input className="w-full border rounded px-3 py-2" placeholder="Nume complet"
                 value={name} onChange={e => setName(e.target.value)} />
          <div className="flex gap-2">
            <select className="border rounded px-2" value={dialCode} onChange={e => setDialCode(e.target.value)}>
              {COUNTRY_DIAL_CODES.map(c => <option key={c.code} value={c.code}>{c.flag} {c.code}</option>)}
            </select>
            <input className="flex-1 border rounded px-3 py-2" placeholder="Telefon"
                   value={phone} onChange={e => setPhone(e.target.value)} />
          </div>
          <input className="w-full border rounded px-3 py-2" placeholder="Email" type="email"
                 value={email} onChange={e => setEmail(e.target.value)} />
          {submit.isError && <p className="text-sm text-red-600">{errText(submit.error)}</p>}
          <button disabled={!canSubmit} onClick={() => submit.mutate()}
                  className="w-full bg-black text-white rounded py-2 disabled:opacity-40">
            {selected ? 'Trimite programarea' : 'Alege un interval'}
          </button>
        </section>
      </div>
    </div>
  )
}

function CenteredMessage({ title, body }: { title: string; body?: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 text-center">
      <div><h1 className="text-2xl font-bold">{title}</h1>{body && <p className="text-muted-foreground mt-2">{body}</p>}</div>
    </div>
  )
}

function errText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 429) return 'Ai atins limita de programări. Încearcă mai târziu.'
    if (e.status === 403) return 'Programările sunt închise.'
    if (e.status === 409) return 'Intervalul tocmai a fost ocupat. Alege altul.'
  }
  return 'A apărut o eroare. Încearcă din nou.'
}
```

> Verify `ApiError` is exported from `@/api/client` (it is — `client.ts` throws `new ApiError(...)`); import the actual exported name. Confirm `phoneFormat.ts` exports `COUNTRY_DIAL_CODES` with `{code,country,flag}` (it does, `:4-50`).

- [ ] **Step 2: Typecheck** — `npm run build` → 0 errors.
- [ ] **Step 3: Playwright smoke** (webapp-testing skill): load `/td/<seeded-slug>`, pick a slot, fill the form, submit, assert the "check your email" state renders.
- [ ] **Step 4: Commit** — `git commit -m "feat(td): public booking page"`

---

### Task 4: `TdConfirm.tsx` + `TdCancel.tsx` (email landing pages)

**Files:**
- Create: `jarvis/frontend/src/pages/Public/TdConfirm.tsx`
- Create: `jarvis/frontend/src/pages/Public/TdCancel.tsx`

**Interfaces:**
- Consumes: `tdApi.confirm/cancel`, `useSearchParams`.
- Behavior: read `?token=`, POST on a button click (GET just renders the page — no auto-mutation, mirroring the deeplink safety contract). Show success/expired/conflict states.

- [ ] **Step 1: Write `TdConfirm.tsx`**

```tsx
// jarvis/frontend/src/pages/Public/TdConfirm.tsx
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { tdApi } from '@/api/td'
import { ApiError } from '@/api/client'

export default function TdConfirm() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [state, setState] = useState<'idle' | 'ok' | 'gone' | 'conflict' | 'err'>('idle')
  const m = useMutation({
    mutationFn: () => tdApi.confirm(token),
    onSuccess: () => setState('ok'),
    onError: (e) => setState(e instanceof ApiError && e.status === 409 ? 'conflict'
      : e instanceof ApiError && e.status === 410 ? 'gone' : 'err'),
  })
  return (
    <Centered>
      {state === 'idle' && <>
        <h1 className="text-2xl font-bold">Confirmă programarea</h1>
        <button className="mt-4 bg-black text-white rounded px-6 py-2"
                disabled={!token || m.isPending} onClick={() => m.mutate()}>Confirmă test drive</button>
      </>}
      {state === 'ok' && <h1 className="text-2xl font-bold text-green-600">Programare confirmată! Ne vedem la eveniment.</h1>}
      {state === 'gone' && <h1 className="text-2xl font-bold">Linkul a expirat sau a fost deja folosit.</h1>}
      {state === 'conflict' && <h1 className="text-2xl font-bold">Ne pare rău, mașina nu mai este disponibilă pentru acest interval.</h1>}
      {state === 'err' && <h1 className="text-2xl font-bold">A apărut o eroare. Încearcă din nou.</h1>}
    </Centered>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 text-center"><div>{children}</div></div>
}
```

- [ ] **Step 2: Write `TdCancel.tsx`** — identical structure, `tdApi.cancel(token)`, success copy "Programare anulată." (Repeat the component; don't import-share to keep each page self-contained and copy-obvious.)

```tsx
// jarvis/frontend/src/pages/Public/TdCancel.tsx
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { tdApi } from '@/api/td'
import { ApiError } from '@/api/client'

export default function TdCancel() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [state, setState] = useState<'idle' | 'ok' | 'gone' | 'err'>('idle')
  const m = useMutation({
    mutationFn: () => tdApi.cancel(token),
    onSuccess: () => setState('ok'),
    onError: (e) => setState(e instanceof ApiError && e.status === 410 ? 'gone' : 'err'),
  })
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4 text-center"><div>
      {state === 'idle' && <>
        <h1 className="text-2xl font-bold">Anulează programarea</h1>
        <button className="mt-4 bg-black text-white rounded px-6 py-2"
                disabled={!token || m.isPending} onClick={() => m.mutate()}>Anulează test drive</button>
      </>}
      {state === 'ok' && <h1 className="text-2xl font-bold">Programare anulată.</h1>}
      {state === 'gone' && <h1 className="text-2xl font-bold">Linkul a expirat.</h1>}
      {state === 'err' && <h1 className="text-2xl font-bold">A apărut o eroare.</h1>}
    </div></div>
  )
}
```

- [ ] **Step 3: Typecheck** — `npm run build` → 0 errors (now App.tsx Task 2 imports resolve).
- [ ] **Step 4: Playwright smoke** — visit `/td/confirm?token=<real>` from a booking, click confirm, assert success; repeat cancel.
- [ ] **Step 5: Commit** — `git commit -m "feat(td): confirm/cancel email landing pages"`

---

### Task 5: Staff admin UI (Driving Hub)

**Files:**
- Create: `jarvis/frontend/src/api/tdAdmin.ts`
- Create: `jarvis/frontend/src/pages/FoiParcurs/TdBookingAdmin.tsx`
- Modify: the Driving Hub nav/tab registry (find where FoiParcurs tabs are declared — e.g. a `CalendarTab`/hub index — and add a "Programări TD" entry) + `App.tsx` authed route if the hub uses routes rather than tabs.

**Interfaces:**
- Consumes authed endpoints from backend Task 11.
- Produces `tdAdminApi` (create/list/patch page, add car, add window, materialize, set status, list bookings, reassign advisor) and a management page: list pages → create page (company, slug, event_id, title, hours) → add cars (vin + advisor select) → add windows → Materialize → Open → view bookings → reassign advisor.

- [ ] **Step 1: `tdAdmin.ts`**

```ts
// jarvis/frontend/src/api/tdAdmin.ts
import { api } from './client'
const B = '/marketing/api/td'
export const tdAdminApi = {
  listPages: (companyId?: number) => api.get<{ pages: any[] }>(`${B}/pages${companyId ? `?company_id=${companyId}` : ''}`),
  createPage: (body: Record<string, unknown>) => api.post<{ id: number }>(`${B}/pages`, body),
  updatePage: (id: number, body: Record<string, unknown>) => api.patch(`${B}/pages/${id}`, body),
  setStatus: (id: number, status: string) => api.post(`${B}/pages/${id}/status`, { status }),
  addCar: (id: number, body: Record<string, unknown>) => api.post<{ id: number }>(`${B}/pages/${id}/cars`, body),
  removeCar: (cid: number) => api.delete(`${B}/cars/${cid}`),
  addWindow: (id: number, body: Record<string, unknown>) => api.post<{ id: number }>(`${B}/pages/${id}/windows`, body),
  materialize: (id: number) => api.post<{ inserted: number }>(`${B}/pages/${id}/materialize`, {}),
  listBookings: (id: number, status?: string) => api.get<{ bookings: any[] }>(`${B}/pages/${id}/bookings${status ? `?status=${status}` : ''}`),
  reassignAdvisor: (bid: number, advisor_user_id: number) => api.patch(`${B}/bookings/${bid}/advisor`, { advisor_user_id }),
}
```

> Confirm the shared `api` object exposes `patch` and `delete` (grep `api/client.ts`); if not, add them there (thin wrappers over the existing `request`), matching `get`/`post`.

- [ ] **Step 2: Build `TdBookingAdmin.tsx`** — a page using `useQuery`/`useMutation` and shadcn primitives already used elsewhere in FoiParcurs (Table, Dialog, Select, Button, Input). Pull the advisor list from the existing users/advisor endpoint the TD form already uses (grep `TestDriveForm.tsx` for its advisor/user source and reuse it, so the advisor `<Select>` matches the rest of the module). Sections: pages table (+ Create dialog) → selected page detail (Cars sub-table with an advisor Select per car; Windows sub-table; Materialize + Open/Close buttons) → Bookings table with a per-row advisor reassign Select. Keep it one focused file; if it grows past a few hundred lines, split the Cars/Windows/Bookings panels into sibling components in the same folder.

- [ ] **Step 3: Wire it into the Driving Hub** — add the tab/route where the other FoiParcurs tabs live. Match the existing gating (the Driving Hub is already permission-gated for staff).

- [ ] **Step 4: Typecheck + Playwright** — `npm run build` → 0 errors; then drive the full staff flow (create page → add car+advisor → window → materialize → open) and confirm a public `/td/<slug>` then shows slots.

- [ ] **Step 5: Commit** — `git commit -m "feat(td): staff booking-page admin in Driving Hub"`

---

## Frontend self-check

- [ ] `cd jarvis/frontend && npm run build` → 0 TypeScript errors.
- [ ] End-to-end via Playwright: staff creates+opens an event page with a car (advisor set) and a window, materializes → public `/td/:slug` shows slots → book → confirm email link → staff sees a `confirmed` booking with a PLANNED `foi_de_parcurs` row → cancel link frees the slot.
- [ ] Public pages never bounce to `/login` (confirm no 401 on any `/api/td/*` call while logged out).

## Spec coverage map (frontend)

- §3 public route outside auth shell → Task 2
- §5 confirm/cancel landing (GET renders, POST mutates) → Task 4
- §7 phone E.164 on the client → Task 3 (`composePhone`)
- §8 endpoints (public + admin) → Tasks 1, 5
- §13 admin home = Driving Hub → Task 5
