# Mobile HR Launcher — Implementation Plan (jarvis-mobile-2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the mobile HR section into a Sales-style tile launcher (Pontaje, Bonusuri, Învoiri, 360, De aprobat), consolidate all 360 under HR (removing the duplicate standalone "Evaluări" tile), and add a manager "De aprobat" leave-approvals page over existing backend endpoints.

**Architecture:** `/hr` becomes a launcher grid; each tile is its own routed page. The already-componentized sub-tabs (`PontajeTab`/`BonusesTab`/`LeavePermitsTab` in `HR/index.tsx`) are extracted into per-tile pages that each own a month selector. `/hr/360` merges the reviewer inbox (`Evaluations/index`) + a unified "Rezultatele mele" view combining the objective score (`Evaluation360Tab`) and the qualitative report (`Evaluations/Reports`). `/hr/de-aprobat` is new: two hooks over `/connecteam/api/leave-approvals/*` + an Approvals-style list.

**Tech Stack:** React + TS + Vite + Capacitor 6, `@tanstack/react-query`, `react-router-dom` v6, Tailwind, `lucide-react`, `@capacitor/haptics`, vitest.

## Global Constraints

- Repo `jarvis-mobile-2`, branch `dev`. After code changes run `npm run build && npx cap sync android` (mandatory) at the end.
- **Mobile-only** — no backend changes. `/hr/de-aprobat` consumes existing `GET /connecteam/api/leave-approvals/pending` (`{success, data:[...]}`) and `POST /connecteam/api/leave-approvals/{id}/decide` (`{decision:'approved'|'rejected', comment?}` → `{success}`).
- Each new page has a slim in-page title row with a back button to `/hr` (mirror `Sales/index.tsx` / `HR/index.tsx` header) — the global JARVIS bar in `MobileLayout` is the single app header; do not duplicate a logo/brand.
- Romanian labels: tiles `Pontaje` · `Bonusuri` · `Învoiri` · `360` · `De aprobat`; 360 views `De completat` / `Rezultatele mele`; approve/reject `Aprobă` / `Respinge`.
- Verify each task with `npx tsc --noEmit` (clean) + `npx vitest run` (green). Run tests with `npx`, from the repo root.
- Design spec: `docs/superpowers/specs/2026-07-28-mobile-hr-launcher-design.md`.

## File Structure

- Create `src/components/shared/LauncherTile.tsx` — shared tile (extracted from `Sales/index.tsx`), used by HR (and Sales).
- Create `src/pages/HR/Launcher.tsx` — the `/hr` grid (tile defs + grid). Replaces the tabbed shell.
- Create `src/pages/HR/PontajePage.tsx`, `BonusuriPage.tsx`, `InvoiriPage.tsx` — extracted per-tile pages (each: month selector + data hook + existing sub-tab component).
- Create `src/pages/HR/Evaluare360Page.tsx` — merged 360 (inbox + unified results).
- Create `src/pages/HR/DeAprobatPage.tsx` — manager leave-approvals list.
- Create `src/pages/HR/MonthSelector.tsx` — shared month prev/next header (extracted from `HR/index.tsx`).
- Modify `src/hooks/useApi.ts` — add `usePendingLeaveApprovals` + `useDecideLeaveApproval` (+ types).
- Modify `src/App.tsx` — add `/hr/pontaje|bonusuri|invoiri|360|de-aprobat` routes.
- Modify `src/lib/mobileRoutes.ts` (+ test) — add the `/hr/*` routes.
- Modify `src/modules/registry.ts` — `evaluations` tile `inLauncher: false`.
- Modify `src/pages/HR/index.tsx` — becomes the `Launcher` (or re-exports it).
- Reduce `src/pages/HR/Evaluation360Tab.tsx` to an embeddable objective-score component consumed by `Evaluare360Page`.

---

### Task 1: Shared launcher tile + HR launcher grid + routes + registry

**Files:**
- Create: `src/components/shared/LauncherTile.tsx`
- Create: `src/pages/HR/Launcher.tsx`
- Modify: `src/pages/HR/index.tsx` (re-export the launcher)
- Modify: `src/App.tsx` (add the 5 `/hr/*` routes)
- Modify: `src/lib/mobileRoutes.ts` + `src/lib/mobileRoutes.test.ts`
- Modify: `src/modules/registry.ts`
- Modify: `src/pages/Sales/index.tsx` (use the shared tile)

**Interfaces:**
- Produces: `LauncherTile` ({ label, icon, tileClass, onOpen }); `HrLauncher` at `/hr`; routes `/hr/{pontaje,bonusuri,invoiri,360,de-aprobat}` (targets are placeholder stubs until later tasks).

- [ ] **Step 1: Extract the shared tile**

`src/components/shared/LauncherTile.tsx` (lifted from `Sales/index.tsx`'s `SalesAppTile`):

```tsx
import type { LucideIcon } from 'lucide-react';

export interface LauncherTileDef {
  key: string;
  label: string;
  icon: LucideIcon;
  route: string;
  /** Literal Tailwind bg class (not interpolated) so the scanner keeps it. */
  tileClass: string;
}

export function LauncherTile({ def, onOpen }: { def: LauncherTileDef; onOpen: (d: LauncherTileDef) => void }) {
  const Icon = def.icon;
  return (
    <button onClick={() => onOpen(def)} className="flex flex-col items-center gap-2 w-20">
      <div className={`flex h-16 w-16 items-center justify-center rounded-xl shadow-sm active:scale-95 transition-transform text-white ${def.tileClass}`}>
        <Icon className="h-8 w-8" />
      </div>
      <span className="text-[11px] font-medium text-center leading-tight">{def.label}</span>
    </button>
  );
}
```

- [ ] **Step 2: HR launcher grid**

`src/pages/HR/Launcher.tsx`:

```tsx
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Fingerprint, Gift, ClipboardList, Target, CheckSquare, type LucideIcon } from 'lucide-react';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { useTeamPontajeRange } from '@/hooks/useApi';
import { LauncherTile, type LauncherTileDef } from '@/components/shared/LauncherTile';

const BASE_TILES: LauncherTileDef[] = [
  { key: 'pontaje', label: 'Pontaje', icon: Fingerprint, route: '/hr/pontaje', tileClass: 'bg-blue-600' },
  { key: 'bonusuri', label: 'Bonusuri', icon: Gift, route: '/hr/bonusuri', tileClass: 'bg-amber-600' },
  { key: 'invoiri', label: 'Învoiri', icon: ClipboardList, route: '/hr/invoiri', tileClass: 'bg-violet-600' },
  { key: '360', label: '360', icon: Target, route: '/hr/360', tileClass: 'bg-emerald-600' },
];
const MANAGER_TILE: LauncherTileDef = { key: 'de-aprobat', label: 'De aprobat', icon: CheckSquare, route: '/hr/de-aprobat', tileClass: 'bg-rose-600' };

export default function HrLauncher() {
  const navigate = useNavigate();
  // is_manager drives the De aprobat tile — same signal the 360 team view uses.
  const now = new Date();
  const start = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
  const { data: team } = useTeamPontajeRange(start, start);
  const isManager = team?.is_manager ?? false;
  const tiles = isManager ? [...BASE_TILES, MANAGER_TILE] : BASE_TILES;

  const open = (d: LauncherTileDef) => {
    Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
    navigate(d.route);
  };

  return (
    <div className="flex flex-col pb-28">
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <button onClick={() => navigate('/')} className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary touch-target">
          <ChevronLeft className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-bold flex-1">HR</h1>
      </div>
      <div className="px-4">
        <div className="rounded-2xl border bg-card p-4">
          <div className="flex flex-wrap gap-6">
            {tiles.map((t) => <LauncherTile key={t.key} def={t} onOpen={open} />)}
          </div>
        </div>
      </div>
    </div>
  );
}
```

(Confirm `useTeamPontajeRange` returns `{ is_manager }` — it does per `Evaluation360Tab.tsx:62-63`. If a lighter is-manager signal exists, prefer it; the range args here are only used to fetch that flag.)

- [ ] **Step 3: Point `HR/index.tsx` at the launcher**

Replace the entire contents of `src/pages/HR/index.tsx` with a re-export:

```tsx
export { default } from './Launcher';
```
(Its old `PontajeTab`/`BonusesTab`/`LeavePermitsTab` helpers move to the pages in Tasks 2-4 — copy them out before deleting.)

- [ ] **Step 4: Add routes**

In `src/App.tsx`, next to the existing `/hr` route, add (keep `/hr` → the launcher):

```tsx
          <Route path="/hr/pontaje" element={<ErrorBoundary section="HR"><HrPontaje /></ErrorBoundary>} />
          <Route path="/hr/bonusuri" element={<ErrorBoundary section="HR"><HrBonusuri /></ErrorBoundary>} />
          <Route path="/hr/invoiri" element={<ErrorBoundary section="HR"><HrInvoiri /></ErrorBoundary>} />
          <Route path="/hr/360" element={<ErrorBoundary section="HR"><HrEvaluare360 /></ErrorBoundary>} />
          <Route path="/hr/de-aprobat" element={<ErrorBoundary section="HR"><HrDeAprobat /></ErrorBoundary>} />
```
Add imports at the top (create thin stub pages now — replaced in later tasks — so the app compiles):
```tsx
import HrPontaje from '@/pages/HR/PontajePage';
import HrBonusuri from '@/pages/HR/BonusuriPage';
import HrInvoiri from '@/pages/HR/InvoiriPage';
import HrEvaluare360 from '@/pages/HR/Evaluare360Page';
import HrDeAprobat from '@/pages/HR/DeAprobatPage';
```
For each of the 5 page files, create a placeholder default export now (`export default function X(){ return null; }`) so Task 1 compiles; Tasks 2-6 fill them in.

- [ ] **Step 5: Register the deep-link routes + drop the Evaluări tile**

In `src/lib/mobileRoutes.ts` `MOBILE_ROUTE_PATTERNS`, add: `'/hr/pontaje'`, `'/hr/bonusuri'`, `'/hr/invoiri'`, `'/hr/360'`, `'/hr/de-aprobat'`. In `src/lib/mobileRoutes.test.ts`, add an assertion `expect(isKnownMobileRoute('/hr/invoiri')).toBe(true)`.
In `src/modules/registry.ts`, set the `evaluations` entry's `inLauncher: false` (leave the route intact for the fill flow).

- [ ] **Step 6: Point Sales at the shared tile**

In `src/pages/Sales/index.tsx`, replace the local `SalesAppTile` with the shared `LauncherTile` (map `SALES_APPS` → `LauncherTile def={app}`); delete the now-unused local component. Keeps one tile implementation.

- [ ] **Step 7: Verify + commit**

Run: `npx tsc --noEmit && npx vitest run`
Expected: clean; tests green (incl. the new `/hr/invoiri` route assertion).
```bash
git add src/components/shared/LauncherTile.tsx src/pages/HR/Launcher.tsx src/pages/HR/index.tsx src/App.tsx src/lib/mobileRoutes.ts src/lib/mobileRoutes.test.ts src/modules/registry.ts src/pages/Sales/index.tsx src/pages/HR/PontajePage.tsx src/pages/HR/BonusuriPage.tsx src/pages/HR/InvoiriPage.tsx src/pages/HR/Evaluare360Page.tsx src/pages/HR/DeAprobatPage.tsx
git commit -m "feat(hr): Sales-style launcher grid + routes; drop standalone Evaluări tile"
```

---

### Task 2: Shared MonthSelector + Pontaje page

**Files:**
- Create: `src/pages/HR/MonthSelector.tsx`
- Modify: `src/pages/HR/PontajePage.tsx` (fill the stub)

**Interfaces:**
- Consumes: `useProfilePontaje(start, end)`, `getNetEntryHours`, `PunchCard`, the extracted `PontajeTab` body.
- Produces: `MonthSelector` ({ year, month, onPrev, onNext }); `HrPontaje` page.

- [ ] **Step 1: Extract the month selector**

`src/pages/HR/MonthSelector.tsx` — lift the month prev/next header from the current `HR/index.tsx` return (the `ChevronLeft`/`ChevronRight` + `MONTHS_RO[month-1] year` row), as a component:

```tsx
import { ChevronLeft, ChevronRight } from 'lucide-react';

const MONTHS_RO = ['Ianuarie','Februarie','Martie','Aprilie','Mai','Iunie','Iulie','August','Septembrie','Octombrie','Noiembrie','Decembrie'];

export function MonthSelector({ year, month, onPrev, onNext }: { year: number; month: number; onPrev: () => void; onNext: () => void }) {
  return (
    <div className="flex items-center justify-between px-4 py-2">
      <button onClick={onPrev} className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary touch-target"><ChevronLeft className="h-4 w-4" /></button>
      <span className="flex-1 text-center text-sm font-medium">{MONTHS_RO[month - 1]} {year}</span>
      <button onClick={onNext} className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary touch-target"><ChevronRight className="h-4 w-4" /></button>
    </div>
  );
}

/** month/year state + prev/next helpers (rolls the year at Jan/Dec). */
export function useMonth() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const prev = () => (month === 1 ? (setMonth(12), setYear((y) => y - 1)) : setMonth((m) => m - 1));
  const next = () => (month === 12 ? (setMonth(1), setYear((y) => y + 1)) : setMonth((m) => m + 1));
  const start = `${year}-${String(month).padStart(2, '0')}-01`;
  const end = `${year}-${String(month).padStart(2, '0')}-${String(new Date(year, month, 0).getDate()).padStart(2, '0')}`;
  return { year, month, prev, next, start, end };
}
```
(Add `import { useState } from 'react'`.)

- [ ] **Step 2: Fill the Pontaje page**

`src/pages/HR/PontajePage.tsx` — page shell (back to `/hr` + title "Pontaje") + `MonthSelector` + `useMonth` + `useProfilePontaje(start, end)`, rendering the **exact** `PontajeTab` body copied from the old `HR/index.tsx` (PunchCard at top + net-hours history list). Keep `getNetEntryHours`/`PontajeHistoryEntry` usage identical. Header pattern mirrors `Launcher.tsx` (back → `navigate('/hr')`).

- [ ] **Step 3: Verify + commit**

Run: `npx tsc --noEmit && npx vitest run` → clean/green.
```bash
git add src/pages/HR/MonthSelector.tsx src/pages/HR/PontajePage.tsx
git commit -m "feat(hr): Pontaje page (extracted, own month selector)"
```

---

### Task 3: Bonusuri page

**Files:** Modify `src/pages/HR/BonusuriPage.tsx`.
**Interfaces:** Consumes `useHrBonuses(year, month)`, the extracted `BonusesTab` body, `MonthSelector`/`useMonth`.

- [ ] **Step 1:** Fill `BonusuriPage.tsx`: page shell (back to `/hr`, title "Bonusuri") + `MonthSelector`/`useMonth` + `useHrBonuses(year, month)` → render the **exact** `BonusesTab` body (expandable bonus rows) copied from old `HR/index.tsx`, with its empty state (`Niciun bonus în această lună.`).
- [ ] **Step 2:** `npx tsc --noEmit && npx vitest run` → clean/green.
- [ ] **Step 3:** Commit `git add src/pages/HR/BonusuriPage.tsx && git commit -m "feat(hr): Bonusuri page (extracted)"`.

---

### Task 4: Învoiri page

**Files:** Modify `src/pages/HR/InvoiriPage.tsx`.
**Interfaces:** Consumes `useLeavePermits(userId, year, month)` (userId from `authStore`), the extracted `LeavePermitsTab` body, `MonthSelector`/`useMonth`.

- [ ] **Step 1:** Fill `InvoiriPage.tsx`: page shell (back to `/hr`, title "Învoiri") + `MonthSelector`/`useMonth` + `useLeavePermits(userId, year, month)` → render the **exact** `LeavePermitsTab` body (expandable permit rows + status pills + pending-approver display) copied from old `HR/index.tsx`, with its empty state (`Nicio învoire în această lună.`). `userId` via `useAuthStore((s) => s.user?.id)`.
- [ ] **Step 2:** `npx tsc --noEmit && npx vitest run` → clean/green.
- [ ] **Step 3:** Commit `git add src/pages/HR/InvoiriPage.tsx && git commit -m "feat(hr): Învoiri page (extracted)"`.

---

### Task 5: Merged 360 page

**Files:**
- Modify: `src/pages/HR/Evaluare360Page.tsx` (fill the stub)
- Modify: `src/pages/HR/Evaluation360Tab.tsx` (make it an embeddable objective-score component — drop its own page chrome if any; keep the score UI + self/team switch, accept the props it already takes)

**Interfaces:**
- Consumes: `useMyReviewAssignments` (inbox), `Evaluation360Tab` (objective score, self/team), `useMyEvalReports` + the `Reports` detail (qualitative report), `MonthSelector`/`useMonth` for the objective score's period, `authStore` for userId/name.
- Produces: `HrEvaluare360` page with two segmented views.

- [ ] **Step 1: Two-view shell**

`Evaluare360Page.tsx`: page header (back to `/hr`, title "360") + a segmented control `De completat` / `Rezultatele mele` (mirror the toggle in `Evaluations/index.tsx`).
- **De completat**: render the inbox list from `Evaluations/index.tsx` (the `useMyReviewAssignments` list; each item → `navigate('/evaluations/:id')`). Reuse/move that list markup.
- **Rezultatele mele**: stack, top-to-bottom:
  1. **Scor de performanță** — `<Evaluation360Tab ... />` with the props it needs (`userId`, `userName`, `year`, `month`, `start`, `end`, `history`, `leavePermits`, `workingHoursPerDay`) sourced via `useMonth()` + `useProfilePontaje(start,end)` + `useLeavePermits(...)` (same wiring the old `HR/index.tsx` gave it) + `authStore`.
  2. **Raport 360** — the `MyResults` (`Evaluations/Reports.tsx`) content (published-cycle list → detail with competencies + Johari + acknowledge). Reuse `Reports` as a component here.

- [ ] **Step 2: Reuse, don't duplicate**

Import and reuse `MyResults` from `Evaluations/Reports` and the inbox rendering from `Evaluations/index` directly where possible (extract the inbox list into a small exported component if `Evaluations/index` doesn't already expose it). Do NOT re-implement the report/inbox logic.

- [ ] **Step 3: Verify + commit**

Run: `npx tsc --noEmit && npx vitest run` → clean/green (the `evaluation.ts` lib tests still pass).
```bash
git add src/pages/HR/Evaluare360Page.tsx src/pages/HR/Evaluation360Tab.tsx src/pages/Evaluations/index.tsx src/pages/Evaluations/Reports.tsx
git commit -m "feat(hr): merged 360 page — inbox + unified results (score + qualitative report)"
```

---

### Task 6: De aprobat — hooks + page

**Files:**
- Modify: `src/hooks/useApi.ts` (2 hooks + type)
- Modify: `src/pages/HR/DeAprobatPage.tsx` (fill the stub)

**Interfaces:**
- Produces: `PendingLeaveApproval` type; `usePendingLeaveApprovals()` → `PendingLeaveApproval[]`; `useDecideLeaveApproval()` mutation ({ id, decision, comment? }); `HrDeAprobat` page.

- [ ] **Step 1: Hooks**

In `useApi.ts` (near the other connecteam/leave hooks):

```ts
export interface PendingLeaveApproval {
  id: number;
  employee_name?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  reason?: string | null;
  submitted_at?: string | null;
  [k: string]: unknown; // tolerate extra fields; confirm exact shape from a live response
}

export function usePendingLeaveApprovals() {
  return useQuery<PendingLeaveApproval[]>({
    queryKey: ['leave-approvals-pending'],
    queryFn: async () => {
      const r = await apiFetch<{ data?: PendingLeaveApproval[] }>('/connecteam/api/leave-approvals/pending');
      return Array.isArray(r?.data) ? r.data : [];
    },
    staleTime: 30_000,
  });
}

export function useDecideLeaveApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, comment }: { id: number; decision: 'approved' | 'rejected'; comment?: string }) =>
      apiFetch(`/connecteam/api/leave-approvals/${id}/decide`, {
        method: 'POST',
        body: JSON.stringify({ decision, ...(comment ? { comment } : {}) }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leave-approvals-pending'] }),
  });
}
```
(Confirm the item fields against a real response / the web `HubLeaveApprovalsContent`; render defensively regardless.)

- [ ] **Step 2: Page**

`DeAprobatPage.tsx`: page header (back to `/hr`, title "De aprobat") + `usePendingLeaveApprovals()` list. Each row: employee name + date range + reason + submitted-at, with **Aprobă** / **Respinge** buttons calling `useDecideLeaveApproval().mutate({ id, decision })` (haptics; a rejected default comment like the Approvals page sends). Loading / error / empty (`Nimic de aprobat.`) states — mirror `src/pages/Approvals/index.tsx`.

- [ ] **Step 3: Verify + commit**

Run: `npx tsc --noEmit && npx vitest run` → clean/green.
```bash
git add src/hooks/useApi.ts src/pages/HR/DeAprobatPage.tsx
git commit -m "feat(hr): De aprobat — manager leave-approvals list over connecteam endpoints"
```

---

### Task 7: Cleanup + full build/sync + suite green

**Files:** none new (verification + any leftover removal).

- [ ] **Step 1:** Confirm no dead references to the removed HR tabbed shell / old `Evaluation360Tab` page usage; `grep -rn "subTab\|HrSubTab" src` returns nothing stale.
- [ ] **Step 2:** Run `npx tsc --noEmit && npx vitest run` → clean/green.
- [ ] **Step 3:** Mandatory `npm run build && npx cap sync android` → build exit 0, sync finishes.
- [ ] **Step 4:** Manual verification checklist (against the live prod backend): `/hr` shows 4 tiles (non-manager) / 5 (manager); each tile opens its page; Pontaje/Bonusuri/Învoiri month selectors work; 360 shows De completat inbox + Rezultatele mele (score + report); De aprobat lists pending + Aprobă/Respinge work; the old standalone "Evaluări" tile is gone from the Command Center.
- [ ] **Step 5:** No commit (verification task).

---

## Self-Review

- **Spec coverage:** launcher + routes (T1) ✓; drop Evaluări tile (T1) ✓; Pontaje/Bonusuri/Învoiri extracted pages w/ own month selector (T2-4) ✓; merged 360 = inbox + unified results (score + qualitative report) (T5) ✓; De aprobat hooks + page + manager gating (T1 gate + T6) ✓; deep-link routes (T1) ✓; mobile-only, no backend (T6 uses existing endpoints) ✓.
- **Placeholder scan:** none — new code is shown; extraction steps reference the exact existing components (`PontajeTab`/`BonusesTab`/`LeavePermitsTab`/`Evaluation360Tab`/`MyResults`) to move, which is transcription-of-existing, not deferred work. The "confirm exact shape/field" notes are verify-against-real-response steps.
- **Type consistency:** `LauncherTileDef`, `useMonth`/`MonthSelector`, `PendingLeaveApproval`, `usePendingLeaveApprovals`, `useDecideLeaveApproval({id,decision,comment?})`, and the 5 page default-exports are used identically across tasks and `App.tsx`.

## Handoff

Mobile-only. Ships in the next `jarvis-mobile-2` release alongside the detail tweaks + notifications fixes already on `dev`. Design/plan docs stay on `dev`, dropped before any staging/main merge.
