# Design — Driving Sessions in the JARVIS HUB

**Date:** 2026-07-27
**Status:** Design — awaiting review
**Branch:** `dev` (JARVIS web)

## Overview

Replicate the mobile "Driving Sessions" mini-app (jarvis-mobile-2 `src/pages/Sales/TestDrive/`)
into the JARVIS web **HUB** as an in-page panel, and close the one functional gap between the
existing web module and the mobile flow: the **vehicle Return / completion** step.

The mobile module is a full test-drive lifecycle: plan a draft → activate (client signs) →
drive → **return the car** → completed, plus a calendar and a VIN conflict soft-block. The web
already has a near-complete equivalent at `pages/FoiParcurs/` (route `/app/foi-parcurs`,
"Driving Hub"), but two things are missing relative to the mobile app:

1. **Return flow** — no web UI and no API client method, even though the backend
   `PUT /api/foi-parcurs/test-drive/:id/return` endpoint already exists and is tested.
2. **Not surfaced in the employee HUB** — the Hub tile-launcher has no Driving tile.

This design adds an in-page `HubDrivingPanel`, wires the Return flow into the shared module
(benefiting both the panel and the standalone module), and gates the tile on `can_access_carpark`.

## Goals

- Employees with `can_access_carpark` get a **Driving Sessions** tile in the Hub that opens an
  in-page panel with the full lifecycle: list, calendar, plan, activate, **return**, discard, detail.
- Build the **Return** flow once, in the shared FoiParcurs module, reachable from both the Hub
  panel and the standalone `/app/foi-parcurs` module.
- **Reuse** existing web components (`SessionsTab`, `CalendarTab`, `TestDriveForm`,
  `testDriveDamage`, `SignatureCanvas`, `ConflictDialog`) — no parallel/duplicated module.
- No backend changes.

## Non-goals

- No changes to back-office tabs (Driving Park stock, monthly route-sheets "Foi de Parcurs",
  Settings) — they stay in the standalone module, out of the Hub panel.
- No new backend endpoints (the return endpoint already exists).
- No mobile-app changes.
- No porting of mobile's `naiveDate` convention or 9-zone damage model — the web keeps its own
  datetime handling and 7-zone damage model for departure/return symmetry.

## Current state (verified 2026-07-27)

**Backend** — blueprint mounts prefix-less, so paths are literal `/api/foi-parcurs/*`, all
`@login_required`. The return endpoint exists:

- `PUT /api/foi-parcurs/test-drive/<id>/return` (`routes/test_drive.py:367`) — requires
  `advisor_signature` + `client_signature` + `km_end` (int, must be ≥ `km_start`); optional
  `fuel_gauge_end_level`, `return_datetime`, `return_damage` (list), `return_notes`. Maps
  signatures to DB columns `return_advisor_signature` / `return_client_signature`, advances the
  vehicle odometer, auto-emails the completed contract, returns `{ success, contract }`. Tested at
  `jarvis/tests/foi_parcurs/test_drive_return`.

**Web frontend** — `pages/FoiParcurs/`:

- `index.tsx` (~2500 lines): tab shell with `stock` / `parcurs` / `calendar` / `contracts` /
  `settings`. `SessionsTab({companyId, brand})` (line 1012, **private** — needs `export`),
  `CalendarTab({companyId, brand})` (already `export`ed in `CalendarTab.tsx:45`). The shell owns
  `companyId`/`brand` state + a company/brand selector.
- `TestDriveForm.tsx` (818 lines): one component for submit/plan/activate. Reads `?activate=<id>`
  from search params; on activate-success it `navigate('/app/foi-parcurs/test-drive')` (line 414);
  otherwise shows a success screen with "Înapoi la Driving Hub". Route-coupled but shallowly.
- `api/foiParcurs.ts`: has `submitTestDrive` / `planTestDrive` / `activateTestDrive` /
  `discardTestDrive` / `getTestDrive` / `getVehicleConflicts` / `getGeneralConditions` etc.
  **No return method** — this is the API gap.
- `sessionStatus.ts`: 5-state derivation (planificat / nealocat / driving / intarziat / finalizat)
  already matching mobile + a PENDING state. Reuse as-is.
- `types/foiParcurs.ts`: `FoiContract` (has `status`, `td_status?`, `km_start`, `departure_damage?`,
  `return_datetime?`, `mileage_floor`), `TdDamageItem`, `TestDriveFormPayload`,
  `PlanTestDrivePayload`, `ActivateTestDrivePayload`, `VehicleConflict`. **No `ReturnTestDrivePayload`.**
  `FuelGaugeLevel = '1'|'1/2'|'2/3'|'1/4'` is the **departure** gauge — return uses a different set.

**Hub** — `pages/Hub/index.tsx`: `ActiveModule` union (line 80), `appTiles` array (94), `AppTile`
type (83, `route?` = launcher vs in-page panel), `visibleTiles` gate (218, e.g. vouchers-perm
pattern), render switch (323), mobile bottom tab-bar (418). `Car` icon already imported.
`authUser` from `useAuthStore`; `User.can_access_carpark: boolean` (`types/index.ts:39`).

## Architecture

```
Hub tile "Driving Sessions" (gated: can_access_carpark)
   → activeModule = 'driving'
   → <HubDrivingPanel>            (new file: pages/Hub/HubDrivingPanel.tsx)
       ├─ company/brand selector  (own lightweight state; foiParcursApi.getCompanies/getBrands)
       ├─ sub-tabs: [Sesiuni] [Calendar]
       │     ├─ <SessionsTab companyId brand>   (reused — export from index.tsx)
       │     └─ <CalendarTab companyId brand>   (reused — already exported)
       ├─ "Driving Session nou" → opens inline overlay
       └─ row/detail quick-actions:
             Începe (activate) · Retur · Renunță (discard) · open detail
   → inline full-screen overlay INSIDE the Hub (never leaves /app/hub):
       ├─ <TestDriveForm embedded onDone onCancel activateId? initialCompanyId?>   (refactored)
       └─ <TestDriveReturn embedded onDone onCancel returnId>                       (new)
```

The panel is the in-page "home" (list + calendar + detail); the heavy forms open as full-screen
overlays rendered within the Hub, so the user never leaves the Hub route.

## Components

### New: `pages/FoiParcurs/TestDriveReturn.tsx` (shared — the only net-new UI)
- **Purpose:** record vehicle return → complete a test drive. Web mirror of mobile `Return.tsx`.
- **Interface (embeddable from day one):**
  `TestDriveReturn({ id, embedded?, onDone?(contract), onCancel? })`. Standalone route mode reads
  `:id` from params and navigates on done; embedded mode takes `id` prop + callbacks.
- **Fields / rules:**
  - `km_end` — number, validated **≥ `contract.km_start`** (inline error mirroring mobile).
  - `fuel_gauge_end_level` — segmented control `Gol | 1/4 | 1/2 | 3/4 | Plin`
    (`ReturnFuelLevel` type — distinct from the departure `FuelGaugeLevel`).
  - Return **damage seeded from `contract.departure_damage`** (reuse `testDriveDamage.tsx`
    `fromDamagePayload`/`toDamagePayload`, 7 zones); section auto-opens when seeded.
  - `return_notes` — optional textarea.
  - **advisor signature** (reuse `SignatureCanvas` + existing `ADVISOR_SIG_KEY` localStorage reuse
    pattern) + **client signature** (fresh).
  - `attempted`-flag red validation; guard when `contract.status === 'COMPLETED'`.
- **Depends on:** `foiParcursApi.submitTestDriveReturn`, `getTestDrive`, `testDriveDamage`,
  `SignatureCanvas`, react-query.
- **On success:** invalidate `['fp-contracts', …]`; embedded → `onDone(contract)`, standalone →
  navigate back to detail/list.

### New: `pages/Hub/HubDrivingPanel.tsx`
- **Purpose:** in-page Hub home for Driving Sessions.
- **Interface:** `HubDrivingPanel()` (self-contained; reads `authUser` for advisor prefill only).
- **Contents:** own company/brand selector state, `[Sesiuni] [Calendar]` sub-tabs rendering the
  reused `SessionsTab`/`CalendarTab`, a primary "Driving Session nou" button, and quick actions on
  rows/detail (Începe → activate overlay, Retur → return overlay, Renunță → discard confirm).
- **Overlay host:** manages an `overlay` state (`{ kind: 'new'|'activate'|'return', id? }`) and
  renders `<TestDriveForm embedded …>` / `<TestDriveReturn embedded …>` in a full-screen
  `Dialog`/sheet; `onDone` closes the overlay and refetches.
- **Depends on:** `SessionsTab`, `CalendarTab`, `TestDriveForm`, `TestDriveReturn`, `foiParcursApi`.

### Refactor: `TestDriveForm.tsx` → embeddable
- Add optional props `{ embedded?, activateId?, initialCompanyId?, onDone?(contract), onCancel? }`.
- When `embedded`: suppress the page header/back-nav; use `activateId` prop instead of
  `useSearchParams`; call `onDone(contract)` instead of `navigate()` on success/activate.
- Default (no props) behavior is unchanged → the standalone `/app/foi-parcurs/test-drive` route
  keeps working exactly as today. Low-risk: the route/nav calls become the `else` branch.

### Refactor: `pages/FoiParcurs/index.tsx`
- `export` `SessionsTab` (currently private) so the Hub panel can import it. No behavior change.

## API additions (`api/foiParcurs.ts`)

```ts
submitTestDriveReturn: (id: number, data: ReturnTestDrivePayload) =>
  api.put<{ success: boolean; contract: FoiContract }>(`${BASE}/test-drive/${id}/return`, data),
```

## Type additions (`types/foiParcurs.ts`)

```ts
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

## Hub integration (`pages/Hub/index.tsx`)

1. `type ActiveModule = … | 'driving'` (line 80).
2. `appTiles` += `{ key: 'driving', label: 'Driving Sessions', shortLabel: 'Driving', icon: Car,
   bg: 'bg-teal-600', fg: 'text-white' }` (line 94; `Car` already imported).
3. `visibleTiles` gate (line 218): hide the `driving` tile unless `authUser?.can_access_carpark`
   (same shape as the `hasVouchersPerm` gate). `tileCounts.driving = -1` (always show when allowed).
4. Render switch (line 323): `{activeModule === 'driving' && <HubDrivingPanel />}`
   (lazy-imported to keep `Hub/index.tsx` lean). Bottom tab-bar + section title pick it up
   automatically from `visibleTiles`.

## Data flow (return)

1. Panel row "Retur" (session with `td_status` driving/incomplete) → overlay `TestDriveReturn`.
2. `getTestDrive(id)` loads the contract → seed damage from `departure_damage`, show `km_start`.
3. Advisor confirms damage + adds new, enters `km_end`/fuel/notes, both signatures.
4. `submitTestDriveReturn(id, payload)` → backend sets COMPLETED, advances odometer, auto-emails.
5. On success: invalidate `['fp-contracts', …]`; overlay closes; list badge flips to **Finalizat**.

## Gotchas honored (from analysis)

- **Datetime:** use the web module's existing convention (`localDatetimeValue`, `.slice(0,16)`),
  **not** mobile's `naiveDate`. Return `return_datetime` display matches the rest of web.
- **Damage:** reuse the web **7-zone** `testDriveDamage.tsx` (not mobile's 9) for departure/return
  symmetry; **seed return damage from departure**.
- **km_end** shown only when session is complete; PLANNED rows show live `mileage_floor`.
- **General-conditions scroll-gate** preserved (already in web `TestDriveForm`).
- **Return fuel** uses `Gol/1/4/1/2/3/4/Plin`, not the departure gauge union.
- React-Query invalidation after return/activate/discard so the panel + standalone stay in sync.

## Error handling

- Backend validation errors (missing signature, `km_end < km_start`, not-a-TD) surface as inline
  Romanian messages; the submit button stays enabled and turns red on a failed attempt.
- `getTestDrive` load failure → error state in the overlay; overlay is cancelable.
- Odometer-advance / auto-email failures are backend best-effort (already swallowed server-side);
  the frontend treats a `{ success: true }` return as complete.

## Testing

- Vitest unit tests (following the tsconfig-excluded test pattern from the 360 work):
  - `submitTestDriveReturn` builds the correct `PUT` path + payload.
  - `TestDriveReturn`: km≥start validation, COMPLETED guard, damage seeding from departure,
    payload shape (signatures + fuel + damage), success invalidation.
- Manual/`webapp-testing` smoke: Hub tile visibility by `can_access_carpark`; full lifecycle
  (plan → activate → return → finalizat) inside the panel via overlays.
- `npm run build` / tsc clean; no regressions to the standalone `/app/foi-parcurs` routes.

## Rollout

- All work on `dev`. Standard JARVIS flow: dev → staging (on confirmation) → main (2 confirmations).
- Additive + gated: the tile only appears for `can_access_carpark` users; standalone module
  behavior is unchanged.

## Open questions

- None blocking. (Confirmed: return endpoint contract, `can_access_carpark` flag, component
  coupling, return-signature column names.)
