# Mobile HR — Sales-style launcher + 360 consolidation + "De aprobat"

**Date:** 2026-07-28
**Status:** Approved (design)
**Scope:** `jarvis-mobile-2` only (mobile UI + API-client hooks). **No backend
changes** — the new "De aprobat" tile consumes existing
`/connecteam/api/leave-approvals/*` endpoints.

## Problem

The mobile HR section ([HR/index.tsx](../../..)) is a single tabbed page with a
shared month selector and four inline sub-tabs (Pontaje / Bonusuri / Învoiri /
360). Separately, **360 is also a standalone top-level "Evaluări" launcher tile**
(`/evaluations`, [registry.ts](../../..)), so 360 appears **twice**. And there is
no manager leave-approvals surface on mobile, though the web HUB has a "De
aprobat" tab.

## Goal

1. Turn HR into a **Sales-style tile launcher** (`/hr` → grid of tiles).
2. **Consolidate all 360 under HR** in one "360" tile; **remove the duplicate
   standalone "Evaluări" tile**.
3. Add a manager **"De aprobat"** leave-approvals tile (existing backend).

## Design

### HR launcher (`/hr`)

Replace the tabbed page with a launcher grid that mirrors
[Sales/index.tsx](../../..) (reuse its `SalesAppTile` look — colored rounded tile
+ label). Gated by `canHr` (unchanged). Tiles, each its own **routed page**
(separate routes, deep-linkable — the approved approach):

| Tile | Route | Manager-only |
|---|---|---|
| Pontaje | `/hr/pontaje` | no |
| Bonusuri | `/hr/bonusuri` | no |
| Învoiri | `/hr/invoiri` | no |
| 360 | `/hr/360` | no |
| De aprobat | `/hr/de-aprobat` | **yes** |

New routes registered in `App.tsx` under `/hr/*`, and added to
`src/lib/mobileRoutes.ts` so notification/deep-links to them resolve in-app.

### Pontaje / Bonusuri / Învoiri pages

Extract each current sub-tab from `HR/index.tsx` into its own page component,
each owning its **own month selector** (prev/next, default = current month).
Behavior is unchanged, just relocated:

- **Pontaje** — `PunchCard` at top (always) + monthly punch history (net hours
  via `getNetEntryHours`), using `useProfilePontaje(start, end)`.
- **Bonusuri** — month bonuses list (`useHrBonuses(year, month)`).
- **Învoiri** — month leave-permits list (`useLeavePermits(userId, year, month)`),
  including the pending-approver display already built.

Each page has a back affordance to `/hr`.

### 360 page (`/hr/360`) — merged & reconciled

One screen, two segmented views (top toggle):

1. **De completat** — the reviewer inbox (`useMyReviewAssignments`); each item →
   the existing `/evaluations/:id` fill route (kept). Empty state until the user
   is assigned as a reviewer.
2. **Rezultatele mele** — a **unified results view** combining the two
   complementary facets of the user's evaluation, top-to-bottom:
   - **Scor de performanță** — the objective score (ring + verdict + scoring
     formula; self, and a team switch for managers) — the current
     `Evaluation360Tab` UI, extracted into a shared component.
   - **Raport 360** — the qualitative multi-rater report (competency aggregates
     + Johari windows) from `useMyEvalReports` / the `Reports` detail — shown per
     published cycle, with acknowledge. Empty note when no report is published.

   Rationale ("reconcile the overlap"): objective score and qualitative 360 are
   different measures of the same thing — the user's evaluation — so they belong
   in one "Rezultatele mele" view rather than a standalone tile + a separate HR
   tab. The objective score is always available; the qualitative report appears
   once a cycle is released.

The standalone **"Evaluări" launcher tile is removed** (`registry.ts` →
`inLauncher: false`). The `/evaluations` + `/evaluations/:id` routes remain (the
fill flow), reached from the HR 360 inbox.

### De aprobat page (`/hr/de-aprobat`) — new (mobile-only)

New hooks in `useApi.ts`:

- `usePendingLeaveApprovals()` → `GET /connecteam/api/leave-approvals/pending`.
- `useDecideLeaveApproval()` → `POST /connecteam/api/leave-approvals/{id}/decide`
  (body `{decision, comment?}`), invalidating the pending query + the bell/HR
  counts on success.

UI mirrors the [Approvals page](../../..) pattern: a list of pending leave
requests (employee, date range, reason, requested-at) with **Aprobă / Respinge**
actions and haptics; empty state when none. POST to `/connecteam/...` is already
in the mobile CORS allow-list (the app posts leave permits), so no backend/CORS
change is needed — **confirm during implementation**.

**Gating:** the De aprobat tile is shown only to managers. Reuse the
`is_manager` signal already returned by `useTeamPontajeRange` / team-pontaje (the
same signal the 360 team view uses). Non-managers don't see the tile; if they
reach the route directly, it shows the empty state.

### Removals / refactor

- `registry.ts`: `evaluations` entry → `inLauncher: false` (keep the route for
  the fill flow; drop the launcher tile).
- `HR/index.tsx`: rewritten from a tabbed page into the launcher grid.
- `Evaluation360Tab.tsx`: its objective-score UI is extracted into a shared
  component consumed by `/hr/360`'s "Rezultatele mele"; the file is removed or
  reduced to that shared piece.

## Edge cases

- **Deep-links:** `/hr/pontaje|bonusuri|invoiri|360|de-aprobat` added to
  `mobileRoutes.ts` known routes, so a notification linking to one resolves
  instead of bouncing to home.
- **Non-manager** → no De aprobat tile; empty state if routed directly.
- **360 empty** — no assignments / no published report → clear empty states.
- **Month boundaries** — each page's selector rolls year at Jan/Dec (existing
  logic, copied per page).

## Testing

- Pure logic (`src/lib/evaluation.ts`) already tested — unchanged.
- Add known-route entries for `/hr/*` to `mobileRoutes.ts` and extend
  `mobileRoutes.test.ts`.
- Pages verified via `tsc` + `vitest` (existing suite) + `npm run build` +
  `npx cap sync android` (repo convention — pages aren't component-tested).
- Manual device verification: launcher renders 5/4 tiles by role; each tile
  opens its page; 360 shows inbox + unified results; De aprobat lists + decides.

## Out of scope

- No backend changes; no change to the 360 cycle/report backend or the scoring
  formulas; no change to the web HUB.

## Sequencing

Mobile-only → ships in the next `jarvis-mobile-2` release (the same `2.0.x` line
that already carries the detail tweaks + notifications fixes on `dev`). Design
doc stays on `dev`, dropped before any staging/main merge.
