# Design — Field Sales ("Teren") panel inside the Hub

**Date:** 2026-08-04
**Status:** Approved (design), pending spec review
**Scope:** JARVIS web frontend only (`jarvis/frontend`). No backend, DB, or migration changes.
**Branch:** `dev`

## Problem

The KAM / Field Sales module is reachable in the web app only via the left Sidebar
(**Sales → Field Sales**, a manager-oriented week overview) and, separately, as a
full module in the mobile app (`jarvis-mobile` v1). The **Hub** — the mobile-style
personal launcher landing page — has no Field Sales presence at all. A KAM using the
Hub cannot see or act on their day's visits.

We want a **KAM daily-driver** version of the module embedded in the Hub, mirroring
the mobile "Vizite" UX, using the same shared backend.

## Goal

Add a Hub tile + in-page panel that lets a KAM, from the Hub:

- See today's visits with quick stats (Planificate / În curs / Finalizate).
- Add a new visit (client search → date / time / type / goals).
- One-tap **check-in** (best-effort geolocation) and **check-out** (with outcome).
- Open a visit's detail (Info / Pre / Post / Task-uri) and capture notes
  (raw → AI-structured).
- Jump from the detail to the full **360° client card** (ANAF fiscal, fleet,
  visit history).

## Non-goals (YAGNI)

- Manager / team overview tab (stays on the desktop page).
- Route Planner (stays on the desktop page).
- Any mobile-app or backend changes. The `/api/field-sales/*` routes already exist
  and are exercised by the mobile app.

## Existing pieces we build on

**Backend (already live, shared with mobile):**
`GET /api/field-sales/visits/today?date=`, `POST /api/field-sales/visits`,
`POST /api/field-sales/visits/:id/checkin`, `.../checkout`, `.../note`,
`GET /api/field-sales/visits/:id`, `GET /api/field-sales/clients/:id/360`,
`GET /api/field-sales/clients/search`, `POST /api/field-sales/clients/:id/refresh-fiscal`.

**Web frontend (reuse):**
- `fieldSalesApi` client — `jarvis/frontend/src/api/fieldSales.ts`
- `VisitDetailDialog` (Info / Pre / Post / Task-uri tabs + edit-to-change-status) —
  `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx`
- `PreVisitForm`, `PostVisitForm`, `TaskList`
- Hub embedding pattern — `jarvis/frontend/src/pages/Hub/HubDrivingPanel.tsx`
  (self-contained panel + iOS-style overlay sheet; tile in `appTiles`).

**Mobile reference to port (do not import — mobile is a separate app):**
`jarvis-mobile/src/pages/FieldSales/` — `index.tsx` (Vizite + AddVisitSheet +
VisitCard), `VisitNoteModal.tsx`, `ClientCard360.tsx`.

## Design

### 1. Entry point & gating (`Hub/index.tsx`)

- Add to `appTiles`:
  `{ key: 'field_sales', label: 'Field Sales', shortLabel: 'Teren', icon: MapPin, bg: 'bg-teal-600', fg: 'text-white' }`.
- Add `'field_sales'` to the `ActiveModule` union.
- Render `<HubFieldSalesPanel />` when `activeModule === 'field_sales'`.
- Visibility: shown when `authUser?.can_access_field_sales` (the same flag the Sidebar
  `Guard` uses). It **stays visible at 0 visits** (like Approvals/Vouchers) — a KAM with
  access must be able to add the first visit. Implement by treating `field_sales` like
  `approvals`/`vouchers` in the `visibleTiles` filter (not auto-hidden on empty count).

### 2. `HubFieldSalesPanel.tsx` (new, `pages/Hub/`)

Mirrors `HubDrivingPanel` structure. Sections:

- **Header:** "Vizite" + today's Romanian date; **Adaugă** button (opens Add-visit overlay).
- **Quick stats:** three tiles — Planificate / În curs / Finalizate — computed from the list.
- **Visit list:** today's visits mapped to `HubVisitCard` (ported). Each card shows client
  name, visit-type label, planned time, renewal badge when `renewal_score > 60`, goals
  preview, and a status-driven action:
  - `planned` → **CHECK-IN** button
  - `in_progress` → check-in time + **Finalizează** (check-out) action
  - `completed` → "Vizită finalizată"
  - Tapping the card body opens the visit-detail overlay.
- **States:** loading spinner, error with retry, empty state ("Nicio vizită planificată" +
  Adaugă), matching the mobile screen.
- **Overlay sheet** (reuse `HubDrivingPanel`'s fixed-inset sheet markup) hosts, one at a time:
  `add` (AddVisitForm), `detail` (VisitDetailDialog), `note` (NoteCaptureModal),
  `client360` (ClientCard360).

Panel-local state: `overlay: null | {kind:'add'} | {kind:'detail',id} | {kind:'note',id} | {kind:'client360',clientId}`.
React Query key: `['field-sales-visits', date]`; mutations invalidate it.

### 3. Components

| Component | Source | Notes |
|---|---|---|
| `HubVisitCard` | port `VisitCard` from mobile `index.tsx` | web classes, no Capacitor Haptics; status → action mapping |
| `AddVisitForm` | port `AddVisitSheet` | client search via `searchClients`, then `createVisit`; renders inside the overlay sheet (not a native BottomSheet) |
| `NoteCaptureModal` | port `VisitNoteModal` (lightweight) | textarea → `addNote` → show returned AI `structured_note`; also invokable via a new "Adaugă notă" button in `VisitDetailDialog`'s Info tab |
| `ClientCard360` | port mobile `ClientCard360` → `pages/FieldSales/ClientCard360.tsx` | ANAF fiscal + fleet + visit history; `getClient360` + `refreshFiscal`; opened from a button in `VisitDetailDialog` and rendered in the Hub overlay |
| `VisitDetailDialog` | **reuse as-is**, plus: a "Vezi client 360" link and an "Adaugă notă" button | small additive edits only |

### 4. API wrappers (add to `fieldSalesApi`)

Thin wrappers over existing routes (no backend change):

```
getTodayVisits(date)      → GET  /api/field-sales/visits/today?date=
checkin(id, {lat,lng})    → POST /api/field-sales/visits/:id/checkin
checkout(id, {outcome})   → POST /api/field-sales/visits/:id/checkout
addNote(id, raw_note)     → POST /api/field-sales/visits/:id/note
getClient360(clientId)    → GET  /api/field-sales/clients/:id/360
refreshFiscal(clientId)   → POST /api/field-sales/clients/:id/refresh-fiscal
```

### 5. Data flow — visit lifecycle from the Hub

1. **Add:** AddVisitForm → `createVisit` → invalidate `['field-sales-visits']`.
2. **Check-in:** card button → best-effort `navigator.geolocation.getCurrentPosition`
   (proceed without coords if unavailable/denied) → `checkin(id,{lat,lng})` → invalidate.
3. **During visit:** open detail → "Adaugă notă" → `addNote` → AI `structured_note`
   returned and shown; Pre/Post/Tasks edited via the existing dialog.
4. **Check-out:** `in_progress` card action → pick outcome
   (`completed | no_show | rescheduled | partial`) → `checkout(id,{outcome})` → invalidate.
5. **360:** from the detail, open ClientCard360 for fiscal/fleet/history; optional
   `refreshFiscal`.

### 6. Geolocation

Best-effort and optional. On check-in, request the browser location with a short
timeout; on success pass `{lat,lng}`, on error/denial call `checkin` with no coords.
Never blocks the check-in. (The Hub can run in a desktop browser where GPS is absent.)

### 7. Error handling

All mutations surface errors via the existing `ApiError` shape (`err?.data?.error`
Romanian string) with an inline message in the overlay, matching current field-sales
components. Failed geolocation is swallowed (see §6).

### 8. Testing

Vitest component tests, following `HubDrivingPanel.test.tsx` / `hubDrivingTile.test.tsx`:

- Tile renders in the grid when `can_access_field_sales` is true; hidden when false.
- Panel lists today's visits and computes the three quick-stat counts.
- Check-in button fires the `checkin` mutation (geolocation mocked/absent path).
- AddVisitForm disables submit until a client is selected; submit calls `createVisit`.
- "Adaugă notă" posts the raw note and renders the returned structured note.

## Files touched

- `jarvis/frontend/src/pages/Hub/index.tsx` — tile + ActiveModule + panel render + visibility.
- `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.tsx` — new.
- `jarvis/frontend/src/pages/Hub/HubFieldSalesPanel.test.tsx` — new.
- `jarvis/frontend/src/pages/FieldSales/ClientCard360.tsx` — new (ported).
- `jarvis/frontend/src/pages/FieldSales/NoteCaptureModal.tsx` — new (ported).
- `jarvis/frontend/src/pages/FieldSales/VisitDetailDialog.tsx` — additive: 360 link + note button.
- `jarvis/frontend/src/api/fieldSales.ts` — 6 wrappers.

## Rollout

Dev only for build + verification (`tsc`, `vitest`, `npm run build`). Deploy later via the
standard surgical cherry-pick of the frontend commits (staging first, then main, 2
confirmations) — out of scope for this spec.
