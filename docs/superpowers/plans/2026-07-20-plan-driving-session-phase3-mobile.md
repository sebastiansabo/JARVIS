# Plan a Driving Session — Phase 3 (Mobile) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend jarvis-mobile-2's Driving Sessions mini-app (`src/pages/Sales/TestDrive/`) to consume the already-deployed Phase 1 backend (`PLANNED` draft status, activate, discard, VIN conflicts): a "Planificat" 4th state on the existing three-state TD badge, a "Planifică (draft)" action + activation flow on the departure form, a soft-block conflict sheet, and a new list-grouped-by-day Calendar screen.

**Architecture:** Pure mobile frontend (Capacitor 6 + React 18 + TypeScript + Vite). No new backend work — all four Phase 1 endpoints (`POST /test-drive` with `status:'PLANNED'`, `PUT /test-drive/{id}/activate`, `DELETE /test-drive/{id}`, `GET /vehicles/{vin}/conflicts`) are live. `New.tsx` gains a second identity: mounted at `/sales/test-drive/new` it creates (live or draft); mounted at the new `/sales/test-drive/:id/activate` route it reads `id` via `useParams` and switches into activation mode (prefills from the `PLANNED` contract, requires the client signature, calls `PUT .../activate` instead of `POST /test-drive`). `deriveTdStatus`/`tdStatusBadge` in `useApi.ts` gain a `'planned'` state checked **before** the `td_status` mapping, exactly mirroring the web `sessionStatus()` PLANNED-first guard.

**Tech Stack:** Capacitor 6, React 18, TypeScript 5.6 (strict, `noUnusedLocals`/`noUnusedParameters` on), Tailwind 4, TanStack Query v5, react-router-dom v6, lucide-react, Vitest 2 (this repo — unlike `jarvis/frontend` — **does** have a unit-test runner: `npm run test` / `vitest run`, `include: ['src/**/*.test.ts']`, `environment: 'node'`; existing precedent `src/lib/conditionsMarkup.test.ts`, `src/services/api.test.ts`). Design spec: `docs/superpowers/specs/2026-07-20-plan-driving-session-design.md` ("Phase 3 — Mobile"). Backend contract: `docs/superpowers/plans/2026-07-20-plan-driving-session-phase1-backend.md` (LIVE + deployed). Web reference (same flows, shipped): `docs/superpowers/plans/2026-07-20-plan-driving-session-phase2-web.md`.

## Global Constraints

- **Mobile-only** (this phase). Touch only `jarvis-mobile-2/src/**` (repo root `/Users/sebastiansabo/Documents/Git/jarvis-mobile-2`). Do not touch JARVIS backend or `jarvis/frontend/**` (Phases 1/2, already shipped).
- **Deploy gate — MANDATORY after every committed task** (per that repo's `CLAUDE.md`):
  ```bash
  cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run build && npx cap sync android
  ```
  `npm run build` is `tsc && vite build` — strict TS (`noUnusedLocals`, `noUnusedParameters`) is the authoritative typecheck gate. `npx cap sync android` is never skipped (per repo policy), even though these are web-only changes.
- **No `eslint.config.js` in this checkout** (same known condition as the web Phase 2 plan) — `npm run lint` / `npx eslint <file>` fails immediately with "couldn't find an eslint.config.(js|mjs|cjs) file", unrelated to this work. `tsc` (via `npm run build`) is the authoritative gate; don't block on lint.
- **Unlike the web repo, this one has Vitest** (`npm run test` = `vitest run`, config `vitest.config.ts`, `environment: 'node'`, `include: ['src/**/*.test.ts']`). Task 1 adds `src/hooks/useApi.test.ts` for the new pure functions (`deriveTdStatus`/`tdStatusBadge`), following the existing `.test.ts`-next-to-source convention (e.g. `src/lib/conditionsMarkup.test.ts`). This is the one task with an actual red→green gate; the rest are typecheck + manual verification only (no component test harness exists — `vitest.config.ts` only includes `.test.ts`, not `.test.tsx`).
- **Work on the mobile repo's `main` branch directly** (per its workflow — no `dev`/`staging` split there). Commit per task. Do **NOT** push — pushing `main` triggers the APK CI (`.github/workflows/build-apk.yml`), which is a separate, explicitly-gated step.
- Conventional commits, scope matching this repo's actual convention (`git log` shows `feat(test-drive): ...` for every prior Driving Sessions change — use that scope, not `feat(sales)`), with the trailer:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  ```
- **Reuse existing mobile patterns** — do not introduce new UI primitives or libraries:
  - `apiFetch`/`ApiError` (`src/services/api.ts`) for all HTTP.
  - TanStack Query hooks colocated in `src/hooks/useApi.ts` (the only hooks file — there is no per-feature hooks module in this repo).
  - `useSignaturePad` (`src/hooks/useSignaturePad.ts`) — already used by `New.tsx`'s client-signature pad and by `AdvisorSignature.tsx`; not touched by this plan (activation reuses the same `SignaturePadField`/`AdvisorSignature` components already in `New.tsx`).
  - `GeneralConditionsModal` / `GdprNoticeModal` — already gate the live submit in `New.tsx`; reused as-is for activation (same `conditionsRequired`/`gdprRequired` derivation, same modals).
  - `BottomSheet` (`src/components/shared/BottomSheet.tsx`) — the app's only modal/sheet primitive (no `confirm()`/`alert()` anywhere in this codebase, verified via `grep -rn "confirm(\|window.confirm" src`, zero hits). Used for both the new Discard confirmation and the Conflict soft-block sheet.
  - `toDamagePayload`/`fromDamagePayload` (`src/pages/Sales/TestDrive/damage.tsx`) for the activation prefill's damage report.
  - `secureStore` advisor-signature reuse is untouched — `AdvisorSignature.tsx` already handles it and is reused unmodified on the activation form.
- **Backend contract** (verified against Phase 1, `jarvis/foi_parcurs/routes/test_drive.py` / `vehicles.py`):
  - Draft create: `POST /api/foi-parcurs/test-drive` with `status:'PLANNED'` — `client_signature`/`gdpr_consent` optional, future `departure_datetime` allowed, no PDF.
  - Activate: `PUT /api/foi-parcurs/test-drive/{id}/activate` — body `{ client_signature (required), advisor_signature?, gdpr_consent?, general_conditions_accepted?, odometer_start?, fuel_gauge_start_level?, fuel_tank_capacity_liters?, departure_datetime?, return_datetime?, departure_damage? }` → `{success, contract}`; 400 if `client_signature` missing; 409 on a race (row no longer `PLANNED`).
  - Discard: `DELETE /api/foi-parcurs/test-drive/{id}` — 200 on a `PLANNED` row, 409 otherwise.
  - Conflicts: `GET /api/foi-parcurs/vehicles/{vin}/conflicts?from=&to=&exclude_id=` → `{success, conflicts: [{id, contract_id, status, departure_datetime, return_datetime, client_name, advisor_name}]}` — **no `td_status` field** (the backend query doesn't select it; mirrors the same finding already verified and documented in the Phase 2 web plan).
- **Deliberate deviations from the web plan / design spec**, called out so they aren't mistaken for oversights:
  - **Driver-license photo stays required for a draft.** The scope instruction relaxes only "client signature/GDPR/general-conditions" for a draft; `driver_license_photo` is a mobile-only field (not part of the backend's `required` list at all, draft or live) governed purely by this app's own validation. This plan does **not** relax it for `Planifică (draft)` — `missing.license` stays in `draftMissing`. This is a judgment call, not a backend constraint; flagged in Self-Review for the user to confirm, since a consilier planning a session for a client who hasn't arrived yet won't have their license scanned.
  - **Activation is a path route, not a query param.** The web plan reopens the form via `?activate={id}`; mobile's existing routing convention is exclusively path-based (`/sales/test-drive/:id`, `/sales/test-drive/:id/return`), so this plan adds `/sales/test-drive/:id/activate` instead, read via `useParams` in the same `New.tsx` component.
  - **Discard lives on the Detail page only, not the list row.** The web plan puts a discard icon directly on the Sesiuni Driving row; this plan keeps the list row's shortcut icon a single non-destructive action (`PlayCircle` → "Începe", replacing the existing `RotateCcw` → "Retur" shortcut for `PLANNED` rows) and puts the destructive Discard behind a `BottomSheet` confirmation on the Detail page. The scope's "detail (and/or list row)" phrasing permits this.
  - **Calendar reuses `useTestDrives()`** (`GET /api/foi-parcurs/contracts?per_page=100`, client-side filtered/sorted) rather than a dedicated range query — there is no lighter/paginated endpoint yet (Phase 1 explicitly reuses `GET /contracts`), and the existing list screen already accepts this same `per_page=100` ceiling.

## File Structure

**Created:**
- `src/hooks/useApi.test.ts` — Vitest coverage for `deriveTdStatus`/`tdStatusBadge`'s new `'planned'` branch (Task 1).
- `src/pages/Sales/TestDrive/ConflictSheet.tsx` — reusable VIN-conflict soft-block `BottomSheet` (Task 2).
- `src/pages/Sales/TestDrive/Calendar.tsx` — new list-grouped-by-day agenda screen (Task 7).

**Modified:**
- `src/hooks/useApi.ts` — `TdStatus`/`deriveTdStatus`/`tdStatusBadge` widen to 4 states; add `PlanTestDrivePayload`, `ActivateTestDrivePayload`, `VehicleConflict` types + `usePlanTestDrive`, `useActivateTestDrive`, `useDiscardTestDrive`, `useVehicleConflicts` hooks (Task 1).
- `src/pages/Sales/TestDrive/New.tsx` — "Planifică (draft)" action + relaxed draft validation + conflict check (Task 3); activation mode via `useParams` (Task 4).
- `src/pages/Sales/TestDrive/Detail.tsx` — "Începe sesiunea"/"Renunță la planificare" actions for a `PLANNED` contract, hide the PDF section until activated (Task 5).
- `src/pages/Sales/TestDrive/index.tsx` — list-row "Începe" shortcut replacing "Retur" for `PLANNED` rows; Calendar entry-point icon (Task 6, Task 7).
- `src/App.tsx` — register `/sales/test-drive/:id/activate` (Task 4) and `/sales/test-drive/calendar` (Task 7) routes.

---

### Task 1: `useApi.ts` — PLANNED status types, hooks, and the 4-state badge

**Files:**
- Modify: `src/hooks/useApi.ts`
- Create: `src/hooks/useApi.test.ts`

**Interfaces produced:** `PlanTestDrivePayload`, `ActivateTestDrivePayload`, `VehicleConflict` types; `usePlanTestDrive`, `useActivateTestDrive`, `useDiscardTestDrive`, `useVehicleConflicts` hooks; `TdStatus` widened to include `'planned'`. Consumed by Tasks 2–7.

- [ ] **Step 1: Add `useState`/`useCallback` to the React import**

Current (line 1):

```ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/services/api';
import type { Approval, SignatureRequest } from '@/types';
```

Replace with:

```ts
import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/services/api';
import type { Approval, SignatureRequest } from '@/types';
```

- [ ] **Step 2: Widen `TdStatus`/`deriveTdStatus`/`tdStatusBadge` to a 4th `'planned'` state**

Current:

```ts
export type TdStatus = 'driving' | 'incomplete' | 'complete';

/** Resolves the three-state Test Drive status for a contract. Prefers the
 *  backend-derived `td_status`; falls back to deriving it client-side (return
 *  submitted → complete; expected arrival passed → incomplete; else driving)
 *  so the UI is correct even before the backend surfacing has deployed. */
export function deriveTdStatus(c: TestDriveContract): TdStatus {
  if (c.td_status === 'complete' || c.td_status === 'incomplete' || c.td_status === 'driving') {
    return c.td_status;
  }
  if (c.status === 'COMPLETED') return 'complete';
  if (c.return_datetime) {
    const t = new Date(c.return_datetime).getTime();
    if (!Number.isNaN(t) && t < Date.now()) return 'incomplete';
  }
  return 'driving';
}

/** UI descriptor (Romanian label + badge classes) for a three-state status. */
export function tdStatusBadge(status: TdStatus): { label: string; className: string } {
  switch (status) {
    case 'complete':
      return { label: 'Complet', className: 'bg-success/15 text-success' };
    case 'incomplete':
      return { label: 'Incomplet', className: 'bg-red-500/15 text-red-600' };
    default:
      return { label: 'În curs', className: 'bg-blue-500/15 text-blue-600' };
  }
}
```

Replace with:

```ts
export type TdStatus = 'planned' | 'driving' | 'incomplete' | 'complete';

/** Resolves the four-state Test Drive status for a contract. `PLANNED` is
 *  checked FIRST, before td_status — the backend's `_TD_STATUS_SQL` ELSE
 *  branch returns 'driving' for any non-COMPLETED row, which would otherwise
 *  mislabel a still-unactivated draft as "driving" (Plan a Driving Session
 *  design spec: "PLANNED must be evaluated before td_status everywhere status
 *  is derived", mirrored from the web Sesiuni Driving tab's `sessionStatus()`).
 *  Below that, prefers the backend-derived `td_status`; falls back to
 *  deriving it client-side (return submitted → complete; expected arrival
 *  passed → incomplete; else driving) so the UI is correct even before the
 *  backend surfacing has deployed. */
export function deriveTdStatus(c: TestDriveContract): TdStatus {
  if (c.status === 'PLANNED') return 'planned';
  if (c.td_status === 'complete' || c.td_status === 'incomplete' || c.td_status === 'driving') {
    return c.td_status;
  }
  if (c.status === 'COMPLETED') return 'complete';
  if (c.return_datetime) {
    const t = new Date(c.return_datetime).getTime();
    if (!Number.isNaN(t) && t < Date.now()) return 'incomplete';
  }
  return 'driving';
}

/** UI descriptor (Romanian label + badge classes) for a four-state status. */
export function tdStatusBadge(status: TdStatus): { label: string; className: string } {
  switch (status) {
    case 'planned':
      return { label: 'Planificat', className: 'bg-indigo-500/15 text-indigo-600' };
    case 'complete':
      return { label: 'Complet', className: 'bg-success/15 text-success' };
    case 'incomplete':
      return { label: 'Incomplet', className: 'bg-red-500/15 text-red-600' };
    default:
      return { label: 'În curs', className: 'bg-blue-500/15 text-blue-600' };
  }
}
```

- [ ] **Step 3: Add the plan/activate/discard/conflicts hooks after `useSubmitTestDrive`**

Current (the end of the `useSubmitTestDrive` function, immediately followed by the pickers section comment):

```ts
export function useSubmitTestDrive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TestDriveSubmitPayload) =>
      apiFetch<TestDriveSubmitResponse>('/api/foi-parcurs/test-drive', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-drives'] });
    },
  });
}

// ============== Foi de Parcurs — pickers (company/vehicle) ==============
```

Replace with:

```ts
export function useSubmitTestDrive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TestDriveSubmitPayload) =>
      apiFetch<TestDriveSubmitResponse>('/api/foi-parcurs/test-drive', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-drives'] });
    },
  });
}

// ============== Sales / Test Drive — Plan (draft) / Activate / Discard / Conflicts ==============
// Phase 1 backend (docs/superpowers/plans/2026-07-20-plan-driving-session-phase1-backend.md,
// LIVE + deployed): POST /api/foi-parcurs/test-drive with status:'PLANNED' creates
// a draft (no signature/GDPR/PDF required, future departure_datetime allowed);
// PUT .../test-drive/{id}/activate turns it into a live FILLED contract
// (client_signature required); DELETE .../test-drive/{id} discards a
// PLANNED-only draft; GET .../vehicles/{vin}/conflicts?from=&to=&exclude_id=
// returns overlapping PLANNED/live sessions for the soft-block sheet.

/** Same shape as TestDriveSubmitPayload except client_signature/gdpr_consent
 *  are optional — the backend only requires them when status is absent or
 *  'FILLED' (api_submit_test_drive's `is_draft` branch). */
export type PlanTestDrivePayload = Omit<TestDriveSubmitPayload, 'client_signature' | 'gdpr_consent'> & {
  status: 'PLANNED';
  client_signature?: string;
  gdpr_consent?: boolean;
};

export function usePlanTestDrive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PlanTestDrivePayload) =>
      apiFetch<TestDriveSubmitResponse>('/api/foi-parcurs/test-drive', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-drives'] });
    },
  });
}

/** PUT /test-drive/{id}/activate body — only client_signature is required by
 *  the backend; everything else is an optional handover edit (unset fields
 *  keep the PLANNED row's existing values). */
export interface ActivateTestDrivePayload {
  client_signature: string;
  advisor_signature?: string;
  gdpr_consent?: boolean;
  general_conditions_accepted?: boolean;
  odometer_start?: number;
  fuel_gauge_start_level?: '1' | '2/3' | '1/2' | '1/4';
  fuel_tank_capacity_liters?: number;
  departure_datetime?: string;
  return_datetime?: string;
  departure_damage?: TestDriveReturnDamageItem[];
}

/** Activates a PLANNED draft into a live FILLED contract (client signature
 *  required; captures/edits the handover fields; generates the PDFs
 *  server-side). `id` is undefined while `/sales/test-drive/new` (plain
 *  create) is mounted — mutate() is only ever called from activation mode,
 *  where the route guarantees a resolved id. */
export function useActivateTestDrive(id: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ActivateTestDrivePayload) =>
      apiFetch<TestDriveSubmitResponse>(`/api/foi-parcurs/test-drive/${id}/activate`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-drives'] });
      qc.invalidateQueries({ queryKey: ['test-drive', id] });
    },
  });
}

interface DiscardTestDriveResponse {
  success?: boolean;
}

/** Discards a PLANNED draft (DELETE /test-drive/{id}; 409 if it's no longer
 *  PLANNED — any TD user may discard, same gate as create). */
export function useDiscardTestDrive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number | string) =>
      apiFetch<DiscardTestDriveResponse>(`/api/foi-parcurs/test-drive/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-drives'] });
    },
  });
}

/** GET /vehicles/{vin}/conflicts response row. Matches
 *  FoiParcursRepository.find_conflicts()'s SELECT list exactly — no
 *  td_status field (the backend query doesn't derive/select it). */
export interface VehicleConflict {
  id: number;
  contract_id: string;
  status: 'PLANNED' | 'FILLED' | 'COMPLETED';
  departure_datetime: string | null;
  return_datetime: string | null;
  client_name: string | null;
  advisor_name: string | null;
}

interface VehicleConflictsResponse {
  success?: boolean;
  conflicts?: VehicleConflict[];
}

/** Imperative VIN-conflict check for the "Plan a Driving Session" soft-block:
 *  call `check(vin, from, to, excludeId)` right before creating/planning/
 *  activating a TD. Resolves with the overlapping PLANNED/live sessions
 *  (empty array = clear). Never throws — a failed lookup is treated as "no
 *  conflicts" so it can never hard-block the actual submit (mirrors
 *  jarvis/frontend's useVehicleConflicts). */
export function useVehicleConflicts() {
  const [checking, setChecking] = useState(false);

  const check = useCallback(
    async (vin: string, from: string, to: string, excludeId?: number | string): Promise<VehicleConflict[]> => {
      setChecking(true);
      try {
        const params = new URLSearchParams({ from, to });
        if (excludeId != null) params.set('exclude_id', String(excludeId));
        const res = await apiFetch<VehicleConflictsResponse>(
          `/api/foi-parcurs/vehicles/${encodeURIComponent(vin)}/conflicts?${params}`,
        );
        return res?.conflicts ?? [];
      } catch {
        return [];
      } finally {
        setChecking(false);
      }
    },
    [],
  );

  return { checking, check };
}

// ============== Foi de Parcurs — pickers (company/vehicle) ==============
```

- [ ] **Step 4: Create `src/hooks/useApi.test.ts`**

New file:

```ts
import { describe, it, expect } from 'vitest';
import { deriveTdStatus, tdStatusBadge, type TestDriveContract } from './useApi';

function contract(overrides: Partial<TestDriveContract>): TestDriveContract {
  return { id: 1, ...overrides };
}

describe('deriveTdStatus', () => {
  it('is planned for a PLANNED draft, regardless of td_status', () => {
    expect(deriveTdStatus(contract({ status: 'PLANNED', td_status: 'driving' }))).toBe('planned');
    expect(deriveTdStatus(contract({ status: 'PLANNED' }))).toBe('planned');
  });

  it('prefers the backend-derived td_status once activated', () => {
    expect(deriveTdStatus(contract({ status: 'FILLED', td_status: 'driving' }))).toBe('driving');
    expect(deriveTdStatus(contract({ status: 'FILLED', td_status: 'incomplete' }))).toBe('incomplete');
    expect(deriveTdStatus(contract({ status: 'FILLED', td_status: 'complete' }))).toBe('complete');
  });

  it('falls back to status/return_datetime when td_status is absent', () => {
    expect(deriveTdStatus(contract({ status: 'COMPLETED' }))).toBe('complete');
    expect(deriveTdStatus(contract({ status: 'FILLED', return_datetime: '2000-01-01T00:00:00Z' }))).toBe('incomplete');
    expect(deriveTdStatus(contract({ status: 'FILLED', return_datetime: '2999-01-01T00:00:00Z' }))).toBe('driving');
    expect(deriveTdStatus(contract({ status: 'FILLED' }))).toBe('driving');
  });
});

describe('tdStatusBadge', () => {
  it('labels planned as Planificat', () => {
    expect(tdStatusBadge('planned')).toEqual({ label: 'Planificat', className: 'bg-indigo-500/15 text-indigo-600' });
  });

  it('labels the other three states as before', () => {
    expect(tdStatusBadge('complete').label).toBe('Complet');
    expect(tdStatusBadge('incomplete').label).toBe('Incomplet');
    expect(tdStatusBadge('driving').label).toBe('În curs');
  });
});
```

- [ ] **Step 5: Run the test, then the build gate**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run test -- src/hooks/useApi.test.ts`
Expected: all assertions pass (this exercises real, already-written logic — not TDD-red-first, since Step 2/3 land in the same commit; the point is to catch a typo before committing).

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run build && npx cap sync android`
Expected: `tsc` exits 0 (no other file references the new types/hooks yet, so nothing else should break), `vite build` succeeds, `cap sync android` completes.

- [ ] **Step 6: Manual verification**

Open `src/hooks/useApi.ts` and confirm the 4 new hooks hit the exact paths verified against the backend (`POST /api/foi-parcurs/test-drive`, `PUT /api/foi-parcurs/test-drive/{id}/activate`, `DELETE /api/foi-parcurs/test-drive/{id}`, `GET /api/foi-parcurs/vehicles/{vin}/conflicts`), and `VehicleConflict` has no `td_status` field.

- [ ] **Step 7: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/hooks/useApi.ts src/hooks/useApi.test.ts
git commit -m "$(cat <<'EOF'
feat(test-drive): add plan/activate/discard/conflicts hooks + Planificat status

Wires the Phase 1 backend contract (POST .../test-drive status=PLANNED,
PUT .../activate, DELETE .../test-drive/{id}, GET .../conflicts) into
useApi.ts, and widens deriveTdStatus/tdStatusBadge to a 4th 'planned' state
checked before td_status (mirrors the web Sesiuni Driving tab).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `ConflictSheet.tsx` — reusable VIN-conflict soft-block sheet

**Files:**
- Create: `src/pages/Sales/TestDrive/ConflictSheet.tsx`

**Interfaces:**
- Consumes: `VehicleConflict` type (Task 1), `BottomSheet` (`src/components/shared/BottomSheet.tsx`, unmodified).
- Produces: `<ConflictSheet>` — consumed by Task 3 (create/plan), Task 4 (activate).

- [ ] **Step 1: Create the component**

```tsx
import BottomSheet from '@/components/shared/BottomSheet';
import { AlertTriangle } from 'lucide-react';
import type { VehicleConflict } from '@/hooks/useApi';

const STATUS_LABEL: Record<string, string> = {
  PLANNED: 'Planificat',
  FILLED: 'În desfășurare',
  COMPLETED: 'Finalizat',
};

/** Soft-block warning shown when the selected vehicle has overlapping
 *  PLANNED/live sessions in the chosen window. Never hard-blocks — "Continuă
 *  oricum" always lets the consilier proceed with the pending action
 *  (mirrors jarvis/frontend's ConflictDialog, as a BottomSheet instead of a
 *  Dialog — this app has no Dialog primitive). */
export function ConflictSheet({
  open,
  conflicts,
  onContinue,
  onCancel,
}: {
  open: boolean;
  conflicts: VehicleConflict[];
  onContinue: () => void;
  onCancel: () => void;
}) {
  return (
    <BottomSheet open={open} onClose={onCancel} title="Mașina este deja rezervată">
      <div className="space-y-3 pb-2">
        <p className="text-sm text-muted-foreground flex items-start gap-1.5">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-500" />
          {conflicts.length === 1
            ? 'Există o sesiune care se suprapune cu intervalul ales:'
            : `Există ${conflicts.length} sesiuni care se suprapun cu intervalul ales:`}
        </p>
        <div className="space-y-2">
          {conflicts.map((c) => (
            <div key={c.id} className="rounded-xl bg-secondary p-3 text-sm space-y-0.5">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium truncate">{c.client_name || '—'}</span>
                <span className="shrink-0 rounded-full bg-card px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
                  {STATUS_LABEL[c.status] ?? c.status}
                </span>
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
        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 h-11 rounded-xl bg-secondary text-sm font-medium text-muted-foreground touch-target"
          >
            Anulează
          </button>
          <button
            type="button"
            onClick={onContinue}
            className="flex-1 h-11 rounded-xl bg-jarvis text-white text-sm font-semibold active:scale-[0.98] transition-transform touch-target"
          >
            Continuă oricum
          </button>
        </div>
      </div>
    </BottomSheet>
  );
}
```

- [ ] **Step 2: Build gate**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run build && npx cap sync android`
Expected: exits 0. (Nothing imports `ConflictSheet` yet — this task is code-inspection only for the compiled output.)

- [ ] **Step 3: Manual verification**

Read the file back: confirm it imports `BottomSheet` from the shared component (not a new primitive) and `VehicleConflict` from `useApi`, and that "Continuă oricum" never disables/blocks — it's always clickable once the sheet is open.

- [ ] **Step 4: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/pages/Sales/TestDrive/ConflictSheet.tsx
git commit -m "$(cat <<'EOF'
feat(test-drive): add VIN-conflict soft-block sheet

ConflictSheet renders the overlap list (client/consilier/window/status) with
a "Continuă oricum" override, built on the existing BottomSheet primitive.
Not wired into any flow yet — consumed by the departure form's plan/submit/
activate paths next.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `New.tsx` — "Planifică (draft)" action + conflict check for create/plan

**Files:**
- Modify: `src/pages/Sales/TestDrive/New.tsx`

**Interfaces:**
- Consumes: `usePlanTestDrive`, `useVehicleConflicts`, `PlanTestDrivePayload`, `VehicleConflict` (Task 1); `ConflictSheet` (Task 2).
- Produces: a `PLANNED` draft contract on "Planifică (draft)" tap, gated by the same soft-block sheet as the live "Trimite" submit. Does not yet touch activation (Task 4).

- [ ] **Step 1: Imports — `CalendarPlus`, the new hooks/types, `ConflictSheet`**

Current (line 4):

```ts
import { ChevronLeft, CheckCircle2, UserPlus, ChevronDown } from 'lucide-react';
```

Replace with:

```ts
import { ChevronLeft, CheckCircle2, UserPlus, ChevronDown, CalendarPlus } from 'lucide-react';
```

Current (lines 10–20):

```ts
import {
  useFpCompanies,
  useFpVehicles,
  useCrmClientSearch,
  useSubmitTestDrive,
  useLastTestDriveByVin,
  useGeneralConditions,
  useCompanyGdpr,
  type FpVehicle,
  type CrmClient,
} from '@/hooks/useApi';
```

Replace with:

```ts
import {
  useFpCompanies,
  useFpVehicles,
  useCrmClientSearch,
  useSubmitTestDrive,
  usePlanTestDrive,
  useVehicleConflicts,
  useLastTestDriveByVin,
  useGeneralConditions,
  useCompanyGdpr,
  type FpVehicle,
  type CrmClient,
  type PlanTestDrivePayload,
  type VehicleConflict,
} from '@/hooks/useApi';
```

Current (lines 21–26):

```ts
import { DamageReport, initialDamageState, fromDamagePayload, toDamagePayload, type DamageState } from './damage';
import { GdprNoticeModal } from './GdprNoticeModal';
import { GeneralConditionsModal } from './GeneralConditionsModal';
import { AdvisorSignature } from './AdvisorSignature';
import { DriverLicenseSection, CreateClientPanel } from './DriverLicenseSection';
import { OdometerHistory } from './OdometerHistory';
```

Replace with:

```ts
import { DamageReport, initialDamageState, fromDamagePayload, toDamagePayload, type DamageState } from './damage';
import { GdprNoticeModal } from './GdprNoticeModal';
import { GeneralConditionsModal } from './GeneralConditionsModal';
import { AdvisorSignature } from './AdvisorSignature';
import { DriverLicenseSection, CreateClientPanel } from './DriverLicenseSection';
import { OdometerHistory } from './OdometerHistory';
import { ConflictSheet } from './ConflictSheet';
```

- [ ] **Step 2: `planMutation` + conflict-check state**

Current (lines 64–70):

```ts
export default function NewTestDrive() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const submitMutation = useSubmitTestDrive();

  const { data: companies, isLoading: companiesLoading } = useFpCompanies();
```

Replace with:

```ts
export default function NewTestDrive() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const submitMutation = useSubmitTestDrive();
  const planMutation = usePlanTestDrive();

  // ── VIN-conflict soft-block (shared by Trimite + Planifică; Activează
  //    wires into the same check in the activation task) ──
  const { check: checkConflicts } = useVehicleConflicts();
  const [conflictList, setConflictList] = useState<VehicleConflict[]>([]);
  const [showConflicts, setShowConflicts] = useState(false);
  const [pendingRun, setPendingRun] = useState<(() => void) | null>(null);

  const { data: companies, isLoading: companiesLoading } = useFpCompanies();
```

- [ ] **Step 3: `draftMissing`/`draftValid` — the relaxed validation subset**

Current (lines 189–204):

```ts
  const missing = {
    company: !companyId,
    vehicle: !selectedVehicle?.vin,
    client: !selectedClient,
    departure: !departureDatetime,
    odometer: Number.isNaN(odometerStartNum) || odometerStartNum < 0 || odometerBelowCurrent,
    estimated: Number.isNaN(estimatedKmNum) || estimatedKmNum <= 0,
    fuel: !fuelLevel,
    advisor: advisorName.trim() === '',
    clientSig: !clientSignature,
    license: !driverLicensePhoto,
    gdpr: gdprRequired && !gdprConsent,
    conditions: conditionsRequired && !conditionsAccepted,
  };
  const formValid = !Object.values(missing).some(Boolean);
  const canSubmit = formValid && !submitMutation.isPending;
```

Replace with:

```ts
  const missing = {
    company: !companyId,
    vehicle: !selectedVehicle?.vin,
    client: !selectedClient,
    departure: !departureDatetime,
    odometer: Number.isNaN(odometerStartNum) || odometerStartNum < 0 || odometerBelowCurrent,
    estimated: Number.isNaN(estimatedKmNum) || estimatedKmNum <= 0,
    fuel: !fuelLevel,
    advisor: advisorName.trim() === '',
    clientSig: !clientSignature,
    license: !driverLicensePhoto,
    gdpr: gdprRequired && !gdprConsent,
    conditions: conditionsRequired && !conditionsAccepted,
  };
  const formValid = !Object.values(missing).some(Boolean);
  const canSubmit = formValid && !submitMutation.isPending;
  // A PLANNED draft defers client_signature/gdpr_consent/general_conditions_
  // accepted to activation — mirrors the backend's relaxed `required` list
  // for status:'PLANNED' (jarvis/foi_parcurs/routes/test_drive.py). Everything
  // else (company/vehicle/client/dates/odometer/fuel/advisor/license) is still
  // needed to save a draft — driver_license_photo is a mobile-only field with
  // no backend relaxation, kept required here too (see Global Constraints).
  const draftMissing = {
    company: missing.company,
    vehicle: missing.vehicle,
    client: missing.client,
    departure: missing.departure,
    odometer: missing.odometer,
    estimated: missing.estimated,
    fuel: missing.fuel,
    advisor: missing.advisor,
    license: missing.license,
  };
  const draftValid = !Object.values(draftMissing).some(Boolean);
```

- [ ] **Step 4: Replace `handleSubmit` with `withConflictCheck` + `buildBasePayload` + `handleSubmit` + `handlePlan`**

Current (lines 211–262):

```ts
  const handleSubmit = () => {
    if (submitMutation.isPending) return;
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelLevel || !clientSignature) {
      setAttempted(true);
      Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
      return;
    }
    setSubmitError(null);

    const clientIdNum = typeof selectedClient.id === 'string' ? Number(selectedClient.id) : selectedClient.id;
    const departureDamagePayload = toDamagePayload(departureDamage);

    submitMutation.mutate(
      {
        company_id: Number(companyId),
        vin: selectedVehicle.vin,
        client_id: clientIdNum,
        odometer_start: odometerStartNum,
        estimated_km: estimatedKmNum,
        fuel_gauge_start_level: fuelLevel,
        departure_datetime: departureDatetime,
        advisor_name: advisorName.trim(),
        ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
        client_signature: clientSignature,
        gdpr_consent: gdprConsent,
        ...(conditionsRequired ? { general_conditions_accepted: conditionsAccepted } : {}),
        ...(selectedVehicle.fuel_tank_capacity_liters != null
          ? { fuel_tank_capacity_liters: selectedVehicle.fuel_tank_capacity_liters }
          : {}),
        ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
        ...(inspectionAcceptance ? { inspection_acceptance: inspectionAcceptance } : {}),
        ...(departureDamagePayload.length ? { departure_damage: departureDamagePayload } : {}),
        ...(driverLicensePhoto ? { driver_license_photo: driverLicensePhoto } : {}),
        ...(driverLicenseNumber.trim() ? { driver_license_number: driverLicenseNumber.trim() } : {}),
        ...(driverLicenseExpiry.trim() ? { driver_license_expiry: driverLicenseExpiry.trim() } : {}),
      },
      {
        onSuccess: (data) => {
          Haptics.impact({ style: ImpactStyle.Medium }).catch(() => {});
          qc.invalidateQueries({ queryKey: ['test-drives'] });
          if (data?.contract?.id != null) {
            navigate(`/sales/test-drive/${data.contract.id}`);
          } else {
            backToList();
          }
        },
        onError: (err) => {
          setSubmitError(err instanceof ApiError ? err.message : 'Trimiterea a eșuat. Încearcă din nou.');
        },
      },
    );
  };
```

Replace with:

```ts
  /** Runs the VIN-conflict check for the chosen window; if clear, calls
   *  `run()` immediately, else stashes it and opens the soft-block sheet. */
  const withConflictCheck = async (vin: string, run: () => void, excludeId?: number | string) => {
    const conflicts = await checkConflicts(vin, departureDatetime, returnDatetime || departureDatetime, excludeId);
    if (conflicts.length) {
      setConflictList(conflicts);
      setPendingRun(() => run);
      setShowConflicts(true);
    } else {
      run();
    }
  };

  /** Fields shared by the live submit and the draft (Planifică) payloads —
   *  everything except client_signature/gdpr_consent/general_conditions_
   *  accepted, which the draft defers to activation. Takes vehicle/client as
   *  params (not selectedVehicle/selectedClient state directly) so the
   *  null-check narrowing each caller already did before calling this
   *  carries over — reading the state closure here would lose that narrowing
   *  across the function boundary. */
  function buildBasePayload(vehicle: FpVehicle, client: CrmClient) {
    const clientIdNum = typeof client.id === 'string' ? Number(client.id) : client.id;
    const departureDamagePayload = toDamagePayload(departureDamage);
    return {
      company_id: Number(companyId),
      vin: vehicle.vin!,
      client_id: clientIdNum,
      odometer_start: odometerStartNum,
      estimated_km: estimatedKmNum,
      fuel_gauge_start_level: fuelLevel!,
      departure_datetime: departureDatetime,
      advisor_name: advisorName.trim(),
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(vehicle.fuel_tank_capacity_liters != null ? { fuel_tank_capacity_liters: vehicle.fuel_tank_capacity_liters } : {}),
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      ...(inspectionAcceptance ? { inspection_acceptance: inspectionAcceptance } : {}),
      ...(departureDamagePayload.length ? { departure_damage: departureDamagePayload } : {}),
      ...(driverLicensePhoto ? { driver_license_photo: driverLicensePhoto } : {}),
      ...(driverLicenseNumber.trim() ? { driver_license_number: driverLicenseNumber.trim() } : {}),
      ...(driverLicenseExpiry.trim() ? { driver_license_expiry: driverLicenseExpiry.trim() } : {}),
    };
  }

  const handleSubmit = () => {
    if (submitMutation.isPending) return;
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelLevel || !clientSignature) {
      setAttempted(true);
      Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
      return;
    }
    setSubmitError(null);

    const payload = {
      ...buildBasePayload(selectedVehicle, selectedClient),
      client_signature: clientSignature,
      gdpr_consent: gdprConsent,
      ...(conditionsRequired ? { general_conditions_accepted: conditionsAccepted } : {}),
    };

    withConflictCheck(selectedVehicle.vin, () =>
      submitMutation.mutate(payload, {
        onSuccess: (data) => {
          Haptics.impact({ style: ImpactStyle.Medium }).catch(() => {});
          qc.invalidateQueries({ queryKey: ['test-drives'] });
          if (data?.contract?.id != null) {
            navigate(`/sales/test-drive/${data.contract.id}`);
          } else {
            backToList();
          }
        },
        onError: (err) => {
          setSubmitError(err instanceof ApiError ? err.message : 'Trimiterea a eșuat. Încearcă din nou.');
        },
      }),
    );
  };

  const handlePlan = () => {
    if (planMutation.isPending) return;
    if (!draftValid || !selectedVehicle?.vin || !selectedClient || !fuelLevel) {
      setAttempted(true);
      Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
      return;
    }
    setSubmitError(null);

    const payload: PlanTestDrivePayload = {
      ...buildBasePayload(selectedVehicle, selectedClient),
      status: 'PLANNED',
      ...(clientSignature ? { client_signature: clientSignature } : {}),
      ...(gdprConsent ? { gdpr_consent: gdprConsent } : {}),
    };

    withConflictCheck(selectedVehicle.vin, () =>
      planMutation.mutate(payload, {
        onSuccess: (data) => {
          Haptics.impact({ style: ImpactStyle.Medium }).catch(() => {});
          qc.invalidateQueries({ queryKey: ['test-drives'] });
          if (data?.contract?.id != null) {
            navigate(`/sales/test-drive/${data.contract.id}`);
          } else {
            backToList();
          }
        },
        onError: (err) => {
          setSubmitError(err instanceof ApiError ? err.message : 'Salvarea draftului a eșuat. Încearcă din nou.');
        },
      }),
    );
  };
```

- [ ] **Step 5: Submit area — "Planifică (draft)" button + `ConflictSheet`**

Current (lines 502–537, the tail of the component's JSX):

```tsx
        <div className="pt-2">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitMutation.isPending}
            className={cn(
              'w-full h-11 py-3.5 rounded-xl text-white font-semibold text-sm active:scale-[0.98] transition-transform disabled:opacity-50 touch-target',
              canSubmit || !attempted ? 'bg-jarvis' : 'bg-destructive',
            )}
          >
            {submitMutation.isPending ? 'Se trimite...' : 'Trimite'}
          </button>
          {attempted && !formValid && !submitMutation.isPending && (
            <p className="text-xs text-destructive text-center mt-1.5">
              Completează câmpurile marcate cu roșu pentru a trimite.
            </p>
          )}
          {submitError && <p className="text-xs text-destructive text-center mt-1.5">{submitError}</p>}
        </div>
      </div>

      <GdprNoticeModal
        open={showGdprNotice}
        text={companyGdpr}
        onClose={() => setShowGdprNotice(false)}
        onAccept={() => setGdprConsent(true)}
      />
      <GeneralConditionsModal
        open={showConditions}
        text={generalConditions}
        onClose={() => setShowConditions(false)}
        onAccept={() => setConditionsAccepted(true)}
      />
    </div>
  );
}
```

Replace with:

```tsx
        <div className="pt-2 space-y-2">
          <button
            type="button"
            onClick={handlePlan}
            disabled={planMutation.isPending || submitMutation.isPending}
            className="w-full h-11 py-3.5 rounded-xl bg-secondary text-foreground font-semibold text-sm active:scale-[0.98] transition-transform disabled:opacity-50 touch-target flex items-center justify-center gap-1.5"
          >
            {planMutation.isPending ? (
              'Se salvează...'
            ) : (
              <>
                <CalendarPlus className="h-4 w-4" />
                Planifică (draft)
              </>
            )}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitMutation.isPending || planMutation.isPending}
            className={cn(
              'w-full h-11 py-3.5 rounded-xl text-white font-semibold text-sm active:scale-[0.98] transition-transform disabled:opacity-50 touch-target',
              canSubmit || !attempted ? 'bg-jarvis' : 'bg-destructive',
            )}
          >
            {submitMutation.isPending ? 'Se trimite...' : 'Trimite'}
          </button>
          {attempted && !formValid && !submitMutation.isPending && (
            <p className="text-xs text-destructive text-center mt-1.5">
              Completează câmpurile marcate cu roșu pentru a trimite.
            </p>
          )}
          {submitError && <p className="text-xs text-destructive text-center mt-1.5">{submitError}</p>}
        </div>
      </div>

      <GdprNoticeModal
        open={showGdprNotice}
        text={companyGdpr}
        onClose={() => setShowGdprNotice(false)}
        onAccept={() => setGdprConsent(true)}
      />
      <GeneralConditionsModal
        open={showConditions}
        text={generalConditions}
        onClose={() => setShowConditions(false)}
        onAccept={() => setConditionsAccepted(true)}
      />
      <ConflictSheet
        open={showConflicts}
        conflicts={conflictList}
        onCancel={() => { setShowConflicts(false); setPendingRun(null); }}
        onContinue={() => {
          setShowConflicts(false);
          pendingRun?.();
          setPendingRun(null);
        }}
      />
    </div>
  );
}
```

- [ ] **Step 6: Build gate**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run build && npx cap sync android`
Expected: exits 0.

- [ ] **Step 7: Manual verification**

`npm run dev`, navigate to `/sales/test-drive/new`. Fill Companie/Vehicul/Client/Permis/date/KM/combustibil/consilier (skip client signature — GDPR/condiții only appear if configured, skip those too if shown) → "Planifică (draft)" is enabled and, on tap, creates a `PLANNED` contract and navigates to its detail (`/sales/test-drive/{id}`). Fill the rest (client signature + any required GDPR/condiții) → "Trimite" still creates a live `FILLED` contract, unchanged from before. If a second draft/live TD is created for the same VIN with an overlapping departure/arrival window, `ConflictSheet` opens on either button before the mutation fires; "Continuă oricum" proceeds, "Anulează" aborts without submitting.

- [ ] **Step 8: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/pages/Sales/TestDrive/New.tsx
git commit -m "$(cat <<'EOF'
feat(test-drive): add Planifică (draft) action + VIN-conflict soft-block

"Planifică (draft)" posts status:'PLANNED' via the new draft-validity subset
(no client signature/GDPR/general-conditions required, matching the
backend's relaxed `required` list — driver license stays required). Both
Planifică and the existing Trimite now run the VIN-conflict check first and
show ConflictSheet on overlap; live-submit behavior is otherwise unchanged.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `New.tsx` — Activation mode (`/sales/test-drive/:id/activate`) + route

**Files:**
- Modify: `src/pages/Sales/TestDrive/New.tsx`
- Modify: `src/App.tsx`

**Interfaces:**
- Consumes: `useTestDrive`, `useActivateTestDrive`, `ActivateTestDrivePayload` (Task 1); `withConflictCheck` (Task 3).
- Produces: navigating to `/sales/test-drive/{id}/activate` (from Task 5's "Începe sesiunea" and Task 6's list shortcut) reopens `New.tsx` pre-filled from the `PLANNED` contract; submitting calls `PUT .../activate` instead of `POST /test-drive`.

- [ ] **Step 1: Imports — `useParams`, `PlayCircle`, `useTestDrive`/`useActivateTestDrive`/`ActivateTestDrivePayload`**

Current (line 2):

```ts
import { useNavigate } from 'react-router-dom';
```

Replace with:

```ts
import { useNavigate, useParams } from 'react-router-dom';
```

Current (post-Task-3, line 4):

```ts
import { ChevronLeft, CheckCircle2, UserPlus, ChevronDown, CalendarPlus } from 'lucide-react';
```

Replace with:

```ts
import { ChevronLeft, CheckCircle2, UserPlus, ChevronDown, CalendarPlus, PlayCircle } from 'lucide-react';
```

Current (post-Task-3 useApi import block):

```ts
import {
  useFpCompanies,
  useFpVehicles,
  useCrmClientSearch,
  useSubmitTestDrive,
  usePlanTestDrive,
  useVehicleConflicts,
  useLastTestDriveByVin,
  useGeneralConditions,
  useCompanyGdpr,
  type FpVehicle,
  type CrmClient,
  type PlanTestDrivePayload,
  type VehicleConflict,
} from '@/hooks/useApi';
```

Replace with:

```ts
import {
  useFpCompanies,
  useFpVehicles,
  useCrmClientSearch,
  useSubmitTestDrive,
  usePlanTestDrive,
  useActivateTestDrive,
  useVehicleConflicts,
  useLastTestDriveByVin,
  useTestDrive,
  useGeneralConditions,
  useCompanyGdpr,
  type FpVehicle,
  type CrmClient,
  type PlanTestDrivePayload,
  type ActivateTestDrivePayload,
  type VehicleConflict,
} from '@/hooks/useApi';
```

- [ ] **Step 2: Activation state + draft query + `activateMutation`**

Current (post-Task-3, top of the component):

```ts
export default function NewTestDrive() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const submitMutation = useSubmitTestDrive();
  const planMutation = usePlanTestDrive();

  // ── VIN-conflict soft-block (shared by Trimite + Planifică; Activează
  //    wires into the same check in the activation task) ──
  const { check: checkConflicts } = useVehicleConflicts();
  const [conflictList, setConflictList] = useState<VehicleConflict[]>([]);
  const [showConflicts, setShowConflicts] = useState(false);
  const [pendingRun, setPendingRun] = useState<(() => void) | null>(null);

  const { data: companies, isLoading: companiesLoading } = useFpCompanies();
  const { data: vehicles, isLoading: vehiclesLoading } = useFpVehicles();
```

Replace with:

```ts
export default function NewTestDrive() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);

  // ── Activation mode — /sales/test-drive/:id/activate reopens this form
  //    pre-filled from a PLANNED draft; plain /sales/test-drive/new has no
  //    :id param, so activateId is undefined there. ──
  const { id: activateId } = useParams<{ id: string }>();
  const isActivating = activateId != null;
  const { data: draftContract } = useTestDrive(activateId);

  const submitMutation = useSubmitTestDrive();
  const planMutation = usePlanTestDrive();
  const activateMutation = useActivateTestDrive(activateId);

  // ── VIN-conflict soft-block (shared by Trimite + Planifică + Activează) ──
  const { check: checkConflicts } = useVehicleConflicts();
  const [conflictList, setConflictList] = useState<VehicleConflict[]>([]);
  const [showConflicts, setShowConflicts] = useState(false);
  const [pendingRun, setPendingRun] = useState<(() => void) | null>(null);

  const { data: companies, isLoading: companiesLoading } = useFpCompanies();
  const { data: vehicles, isLoading: vehiclesLoading } = useFpVehicles();
```

- [ ] **Step 3: Prefill effects — insert after the auto-select-company effect**

Current (lines 102–109, unmodified by Task 3):

```ts
  useEffect(() => {
    if (companyId || !user?.company || !companies?.length) return;
    const target = user.company.trim().toLowerCase();
    const match = companies.find((c) => c.company.trim().toLowerCase() === target);
    if (match) setCompanyId(String(match.id));
  }, [companies, user?.company, companyId]);

  const vehiclesForCompany = useMemo(
```

Replace with:

```ts
  useEffect(() => {
    if (companyId || !user?.company || !companies?.length) return;
    const target = user.company.trim().toLowerCase();
    const match = companies.find((c) => c.company.trim().toLowerCase() === target);
    if (match) setCompanyId(String(match.id));
  }, [companies, user?.company, companyId]);

  // ── Prefill from the PLANNED draft being activated ──
  useEffect(() => {
    if (!draftContract || draftContract.status !== 'PLANNED') return;
    if (draftContract.company_id != null) setCompanyId(String(draftContract.company_id));
    if (draftContract.departure_datetime) setDepartureDatetime(draftContract.departure_datetime.slice(0, 16));
    if (draftContract.return_datetime) setReturnDatetime(draftContract.return_datetime.slice(0, 16));
    if (draftContract.km_start != null) setOdometerStart(String(draftContract.km_start));
    if (draftContract.distance_km != null) setEstimatedKm(String(draftContract.distance_km));
    if (draftContract.fuel_gauge_start_level) setFuelLevel(draftContract.fuel_gauge_start_level as FuelStartLevel);
    if (draftContract.advisor_name) setAdvisorName(draftContract.advisor_name);
    setDepartureDamage(fromDamagePayload(draftContract.departure_damage));
    if (draftContract.client_id != null && draftContract.client_name) {
      setSelectedClient({ id: draftContract.client_id, display_name: draftContract.client_name, phone: draftContract.client_phone ?? null });
    }
    if (draftContract.driver_license_number) setDriverLicenseNumber(draftContract.driver_license_number);
    if (draftContract.driver_license_photo) setDriverLicensePhoto(draftContract.driver_license_photo);
    // Runs once per draft load; the setters above are stable (useState) and
    // intentionally not listed to keep this a single "hydrate on load" effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftContract]);

  // Match the draft's VIN against the loaded vehicles list once both are ready.
  useEffect(() => {
    if (!draftContract || draftContract.status !== 'PLANNED' || !vehicles?.length) return;
    const v = vehicles.find((x) => x.vin === draftContract.vin);
    if (v) setSelectedVehicle(v);
  }, [draftContract, vehicles]);

  const vehiclesForCompany = useMemo(
```

- [ ] **Step 4: `handleActivate` — insert between `handlePlan` and the JSX `return`**

Current (post-Task-3, the tail of `handlePlan` followed by `return (`):

```ts
    withConflictCheck(selectedVehicle.vin, () =>
      planMutation.mutate(payload, {
        onSuccess: (data) => {
          Haptics.impact({ style: ImpactStyle.Medium }).catch(() => {});
          qc.invalidateQueries({ queryKey: ['test-drives'] });
          if (data?.contract?.id != null) {
            navigate(`/sales/test-drive/${data.contract.id}`);
          } else {
            backToList();
          }
        },
        onError: (err) => {
          setSubmitError(err instanceof ApiError ? err.message : 'Salvarea draftului a eșuat. Încearcă din nou.');
        },
      }),
    );
  };

  return (
```

Replace with:

```ts
    withConflictCheck(selectedVehicle.vin, () =>
      planMutation.mutate(payload, {
        onSuccess: (data) => {
          Haptics.impact({ style: ImpactStyle.Medium }).catch(() => {});
          qc.invalidateQueries({ queryKey: ['test-drives'] });
          if (data?.contract?.id != null) {
            navigate(`/sales/test-drive/${data.contract.id}`);
          } else {
            backToList();
          }
        },
        onError: (err) => {
          setSubmitError(err instanceof ApiError ? err.message : 'Salvarea draftului a eșuat. Încearcă din nou.');
        },
      }),
    );
  };

  const handleActivate = () => {
    if (activateMutation.isPending || activateId == null) return;
    if (!formValid || !selectedVehicle?.vin || !selectedClient || !fuelLevel || !clientSignature) {
      setAttempted(true);
      Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
      return;
    }
    setSubmitError(null);

    const departureDamagePayload = toDamagePayload(departureDamage);
    const payload: ActivateTestDrivePayload = {
      client_signature: clientSignature,
      ...(advisorSignature ? { advisor_signature: advisorSignature } : {}),
      gdpr_consent: gdprConsent,
      ...(conditionsRequired ? { general_conditions_accepted: conditionsAccepted } : {}),
      odometer_start: odometerStartNum,
      fuel_gauge_start_level: fuelLevel,
      ...(selectedVehicle.fuel_tank_capacity_liters != null
        ? { fuel_tank_capacity_liters: selectedVehicle.fuel_tank_capacity_liters }
        : {}),
      departure_datetime: departureDatetime,
      ...(returnDatetime ? { return_datetime: returnDatetime } : {}),
      ...(departureDamagePayload.length ? { departure_damage: departureDamagePayload } : {}),
    };

    withConflictCheck(
      selectedVehicle.vin,
      () =>
        activateMutation.mutate(payload, {
          onSuccess: (data) => {
            Haptics.impact({ style: ImpactStyle.Medium }).catch(() => {});
            qc.invalidateQueries({ queryKey: ['test-drives'] });
            navigate(`/sales/test-drive/${data?.contract?.id ?? activateId}`);
          },
          onError: (err) => {
            setSubmitError(err instanceof ApiError ? err.message : 'Activarea sesiunii a eșuat. Încearcă din nou.');
          },
        }),
      activateId,
    );
  };

  return (
```

- [ ] **Step 5: Header — activation-mode title**

Current (in the JSX, `<NewHeader onBack={backToList} />`):

```tsx
      <NewHeader onBack={backToList} />
```

Replace with:

```tsx
      <NewHeader onBack={backToList} title={isActivating ? 'Activează Sesiunea' : 'Driving Session Nou'} />
```

Current `NewHeader` definition (near the bottom of the file):

```tsx
function NewHeader({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex items-center gap-3 px-4 pt-3 pb-2">
      <button
        onClick={onBack}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary touch-target"
      >
        <ChevronLeft className="h-5 w-5" />
      </button>
      <h1 className="text-lg font-bold flex-1 truncate">Driving Session Nou</h1>
    </div>
  );
}
```

Replace with:

```tsx
function NewHeader({ onBack, title }: { onBack: () => void; title: string }) {
  return (
    <div className="flex items-center gap-3 px-4 pt-3 pb-2">
      <button
        onClick={onBack}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary touch-target"
      >
        <ChevronLeft className="h-5 w-5" />
      </button>
      <h1 className="text-lg font-bold flex-1 truncate">{title}</h1>
    </div>
  );
}
```

- [ ] **Step 6: Submit area — branch on `isActivating`**

Current (post-Task-3):

```tsx
        <div className="pt-2 space-y-2">
          <button
            type="button"
            onClick={handlePlan}
            disabled={planMutation.isPending || submitMutation.isPending}
            className="w-full h-11 py-3.5 rounded-xl bg-secondary text-foreground font-semibold text-sm active:scale-[0.98] transition-transform disabled:opacity-50 touch-target flex items-center justify-center gap-1.5"
          >
            {planMutation.isPending ? (
              'Se salvează...'
            ) : (
              <>
                <CalendarPlus className="h-4 w-4" />
                Planifică (draft)
              </>
            )}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitMutation.isPending || planMutation.isPending}
            className={cn(
              'w-full h-11 py-3.5 rounded-xl text-white font-semibold text-sm active:scale-[0.98] transition-transform disabled:opacity-50 touch-target',
              canSubmit || !attempted ? 'bg-jarvis' : 'bg-destructive',
            )}
          >
            {submitMutation.isPending ? 'Se trimite...' : 'Trimite'}
          </button>
          {attempted && !formValid && !submitMutation.isPending && (
            <p className="text-xs text-destructive text-center mt-1.5">
              Completează câmpurile marcate cu roșu pentru a trimite.
            </p>
          )}
          {submitError && <p className="text-xs text-destructive text-center mt-1.5">{submitError}</p>}
        </div>
```

Replace with:

```tsx
        <div className="pt-2 space-y-2">
          {!isActivating && (
            <button
              type="button"
              onClick={handlePlan}
              disabled={planMutation.isPending || submitMutation.isPending}
              className="w-full h-11 py-3.5 rounded-xl bg-secondary text-foreground font-semibold text-sm active:scale-[0.98] transition-transform disabled:opacity-50 touch-target flex items-center justify-center gap-1.5"
            >
              {planMutation.isPending ? (
                'Se salvează...'
              ) : (
                <>
                  <CalendarPlus className="h-4 w-4" />
                  Planifică (draft)
                </>
              )}
            </button>
          )}
          <button
            type="button"
            onClick={isActivating ? handleActivate : handleSubmit}
            disabled={submitMutation.isPending || planMutation.isPending || activateMutation.isPending}
            className={cn(
              'w-full h-11 py-3.5 rounded-xl text-white font-semibold text-sm active:scale-[0.98] transition-transform disabled:opacity-50 touch-target flex items-center justify-center gap-1.5',
              canSubmit || !attempted ? 'bg-jarvis' : 'bg-destructive',
            )}
          >
            {isActivating ? (
              activateMutation.isPending ? (
                'Se activează...'
              ) : (
                <>
                  <PlayCircle className="h-4 w-4" />
                  Activează
                </>
              )
            ) : submitMutation.isPending ? (
              'Se trimite...'
            ) : (
              'Trimite'
            )}
          </button>
          {attempted && !formValid && !submitMutation.isPending && !activateMutation.isPending && (
            <p className="text-xs text-destructive text-center mt-1.5">
              Completează câmpurile marcate cu roșu pentru a trimite.
            </p>
          )}
          {submitError && <p className="text-xs text-destructive text-center mt-1.5">{submitError}</p>}
        </div>
```

- [ ] **Step 7: Register the activation route in `App.tsx`**

Current (`src/App.tsx`, route list):

```tsx
          <Route path="/sales" element={<ErrorBoundary section="Sales"><Sales /></ErrorBoundary>} />
          <Route path="/sales/test-drive" element={<ErrorBoundary section="Sales"><TestDriveList /></ErrorBoundary>} />
          {/* Static "new" route declared before the dynamic ":id" route below
              so it can't be shadowed by it (matched first regardless of
              React Router's own specificity scoring). */}
          <Route path="/sales/test-drive/new" element={<ErrorBoundary section="Sales"><NewTestDrive /></ErrorBoundary>} />
          <Route path="/sales/test-drive/:id" element={<ErrorBoundary section="Sales"><TestDriveDetail /></ErrorBoundary>} />
          <Route path="/sales/test-drive/:id/return" element={<ErrorBoundary section="Sales"><TestDriveReturn /></ErrorBoundary>} />
```

Replace with:

```tsx
          <Route path="/sales" element={<ErrorBoundary section="Sales"><Sales /></ErrorBoundary>} />
          <Route path="/sales/test-drive" element={<ErrorBoundary section="Sales"><TestDriveList /></ErrorBoundary>} />
          {/* Static "new" route declared before the dynamic ":id" route below
              so it can't be shadowed by it (matched first regardless of
              React Router's own specificity scoring). */}
          <Route path="/sales/test-drive/new" element={<ErrorBoundary section="Sales"><NewTestDrive /></ErrorBoundary>} />
          <Route path="/sales/test-drive/:id" element={<ErrorBoundary section="Sales"><TestDriveDetail /></ErrorBoundary>} />
          <Route path="/sales/test-drive/:id/return" element={<ErrorBoundary section="Sales"><TestDriveReturn /></ErrorBoundary>} />
          {/* Activation route — reopens NewTestDrive pre-filled from a PLANNED
              draft; NewTestDrive reads the `id` param via useParams to switch
              into activation mode. */}
          <Route path="/sales/test-drive/:id/activate" element={<ErrorBoundary section="Sales"><NewTestDrive /></ErrorBoundary>} />
```

- [ ] **Step 8: Build gate**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run build && npx cap sync android`
Expected: exits 0.

- [ ] **Step 9: Manual verification**

Create a `PLANNED` draft (Task 3's flow), then manually navigate to `/sales/test-drive/{id}/activate`. Confirm: header reads "Activează Sesiunea"; company/vehicle/client/dates/km/fuel/advisor/damage are pre-filled from the draft; "Planifică (draft)" is hidden; the primary button reads "Activează" and requires client signature (+ GDPR/condiții if configured for that company/brand) before it's enabled; on tap it calls `PUT /api/foi-parcurs/test-drive/{id}/activate` and navigates to `/sales/test-drive/{id}`, where the contract now shows `status: 'FILLED'` and a live badge.

- [ ] **Step 10: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/pages/Sales/TestDrive/New.tsx src/App.tsx
git commit -m "$(cat <<'EOF'
feat(test-drive): add activation flow for PLANNED drafts

/sales/test-drive/:id/activate reopens NewTestDrive pre-filled from a
PLANNED contract (company/vehicle/client/dates/km/fuel/advisor/damage);
submitting calls PUT .../test-drive/{id}/activate (client signature
required, same VIN-conflict soft-block as create/plan) instead of
POST /test-drive.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `Detail.tsx` — "Începe sesiunea" / "Renunță la planificare" for a PLANNED contract

**Files:**
- Modify: `src/pages/Sales/TestDrive/Detail.tsx`

**Interfaces:**
- Consumes: `useDiscardTestDrive` (Task 1); the `/sales/test-drive/:id/activate` route (Task 4); `BottomSheet` (unmodified shared component).
- Produces: a `PLANNED` contract's detail page shows "Începe sesiunea" (→ activation route) and "Renunță la planificare" (→ confirm sheet → `DELETE /test-drive/{id}` → back to list); the "Contract PDF" section is hidden until activated (no PDF exists yet). The `tdStatusBadge`/`deriveTdStatus` badge already renders "Planificat" automatically once Task 1 lands — no change needed there.

- [ ] **Step 1: Imports — `PlayCircle`/`Trash2`, `useDiscardTestDrive`, `BottomSheet`**

Current (lines 1–6):

```tsx
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronLeft, CheckCircle2, Mail, Loader2, Send } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ApiError } from '@/services/api';
import { useTestDrive, useEmailTestDriveContract, deriveTdStatus, tdStatusBadge, type TestDriveContract } from '@/hooks/useApi';
```

Replace with:

```tsx
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronLeft, CheckCircle2, Mail, Loader2, Send, PlayCircle, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ApiError } from '@/services/api';
import {
  useTestDrive,
  useEmailTestDriveContract,
  useDiscardTestDrive,
  deriveTdStatus,
  tdStatusBadge,
  type TestDriveContract,
} from '@/hooks/useApi';
import BottomSheet from '@/components/shared/BottomSheet';
```

- [ ] **Step 2: Hooks + discard state at the top of the component (before the early returns — Rules of Hooks)**

Current (lines 27–32):

```ts
export default function TestDriveDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: contract, isLoading, isError } = useTestDrive(id);

  const goBack = () => navigate('/sales/test-drive');
```

Replace with:

```ts
export default function TestDriveDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: contract, isLoading, isError } = useTestDrive(id);
  const discardMutation = useDiscardTestDrive();
  const [showDiscard, setShowDiscard] = useState(false);

  const goBack = () => navigate('/sales/test-drive');
```

- [ ] **Step 3: `isPlanned` + `handleDiscard`**

Current (lines 54–57):

```ts
  const badge = tdStatusBadge(deriveTdStatus(contract));
  const isCompleted = contract.status === 'COMPLETED';

  return (
```

Replace with:

```ts
  const badge = tdStatusBadge(deriveTdStatus(contract));
  const isCompleted = contract.status === 'COMPLETED';
  const isPlanned = contract.status === 'PLANNED';

  const handleDiscard = () => {
    if (discardMutation.isPending || !id) return;
    discardMutation.mutate(id, {
      onSuccess: () => {
        setShowDiscard(false);
        navigate('/sales/test-drive');
      },
    });
  };

  return (
```

- [ ] **Step 4: Hide "Contract PDF" until activated**

Current (lines 149–151):

```tsx
        <Section title="Contract PDF">
          <EmailContractPanel id={id} defaultEmail={contract.client_email} />
        </Section>
```

Replace with:

```tsx
        {/* No PDF exists yet for a PLANNED draft — generated at activation. */}
        {!isPlanned && (
          <Section title="Contract PDF">
            <EmailContractPanel id={id} defaultEmail={contract.client_email} />
          </Section>
        )}
```

- [ ] **Step 5: Bottom action area — Începe sesiunea / Renunță, + the discard confirm sheet**

Current (lines 153–173):

```tsx
        {isCompleted ? (
          <button
            type="button"
            disabled
            className="w-full mt-2 py-3.5 rounded-xl bg-secondary text-muted-foreground font-semibold text-sm opacity-60 touch-target"
          >
            Retur finalizat
          </button>
        ) : (
          <button
            type="button"
            onClick={() => navigate(`/sales/test-drive/${id}/return`)}
            className="w-full mt-2 py-3.5 rounded-xl bg-jarvis text-white font-semibold text-sm active:scale-[0.98] transition-transform touch-target"
          >
            Completează retur
          </button>
        )}
      </div>
    </div>
  );
}
```

Replace with:

```tsx
        {isPlanned ? (
          <div className="mt-2 space-y-2">
            <button
              type="button"
              onClick={() => navigate(`/sales/test-drive/${id}/activate`)}
              className="w-full py-3.5 rounded-xl bg-jarvis text-white font-semibold text-sm active:scale-[0.98] transition-transform touch-target flex items-center justify-center gap-1.5"
            >
              <PlayCircle className="h-4 w-4" />
              Începe sesiunea
            </button>
            <button
              type="button"
              onClick={() => setShowDiscard(true)}
              className="w-full py-3.5 rounded-xl bg-destructive/10 text-destructive font-semibold text-sm active:scale-[0.98] transition-transform touch-target flex items-center justify-center gap-1.5"
            >
              <Trash2 className="h-4 w-4" />
              Renunță la planificare
            </button>
          </div>
        ) : isCompleted ? (
          <button
            type="button"
            disabled
            className="w-full mt-2 py-3.5 rounded-xl bg-secondary text-muted-foreground font-semibold text-sm opacity-60 touch-target"
          >
            Retur finalizat
          </button>
        ) : (
          <button
            type="button"
            onClick={() => navigate(`/sales/test-drive/${id}/return`)}
            className="w-full mt-2 py-3.5 rounded-xl bg-jarvis text-white font-semibold text-sm active:scale-[0.98] transition-transform touch-target"
          >
            Completează retur
          </button>
        )}
      </div>

      <BottomSheet open={showDiscard} onClose={() => setShowDiscard(false)} title="Renunți la planificare?">
        <div className="space-y-3 pb-2">
          <p className="text-sm text-muted-foreground">
            Sesiunea planificată va fi ștearsă definitiv. Acțiunea nu poate fi anulată.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowDiscard(false)}
              className="flex-1 h-11 rounded-xl bg-secondary text-sm font-medium text-muted-foreground touch-target"
            >
              Anulează
            </button>
            <button
              type="button"
              onClick={handleDiscard}
              disabled={discardMutation.isPending}
              className="flex-1 h-11 rounded-xl bg-destructive text-white text-sm font-semibold disabled:opacity-50 touch-target active:scale-[0.98] transition-transform"
            >
              {discardMutation.isPending ? 'Se șterge...' : 'Renunță'}
            </button>
          </div>
        </div>
      </BottomSheet>
    </div>
  );
}
```

- [ ] **Step 6: Build gate**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run build && npx cap sync android`
Expected: exits 0.

- [ ] **Step 7: Manual verification**

Open a `PLANNED` contract's detail page. Confirm: Status section shows the indigo "Planificat" badge; "Contract PDF" section is absent; below the read-only sections there's "Începe sesiunea" (→ `/sales/test-drive/{id}/activate`, pre-filled per Task 4) and "Renunță la planificare" (→ opens the confirm sheet; confirming calls `DELETE /api/foi-parcurs/test-drive/{id}` and returns to the list, where the row is gone).

- [ ] **Step 8: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/pages/Sales/TestDrive/Detail.tsx
git commit -m "$(cat <<'EOF'
feat(test-drive): add Începe sesiunea / discard actions to a PLANNED detail

A PLANNED contract's detail page hides the (nonexistent) Contract PDF
section and gets two actions: Începe sesiunea → the activation route, and
Renunță la planificare → a BottomSheet confirm → DELETE .../test-drive/{id}.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `index.tsx` — list-row "Începe" shortcut for PLANNED rows

**Files:**
- Modify: `src/pages/Sales/TestDrive/index.tsx`

**Interfaces:**
- Consumes: `deriveTdStatus`/`tdStatusBadge`'s `'planned'` state (Task 1); the `/sales/test-drive/:id/activate` route (Task 4).
- Produces: a `PLANNED` row shows the indigo "Planificat" badge (automatic, via Task 1) and, in place of the existing "Retur" shortcut icon, a "Începe" shortcut (`PlayCircle`) that navigates straight to activation.

- [ ] **Step 1: Import `PlayCircle`**

Current (line 3):

```ts
import { ChevronLeft, Plus, Car, User2, Gauge, RotateCcw } from 'lucide-react';
```

Replace with:

```ts
import { ChevronLeft, Plus, Car, User2, Gauge, RotateCcw, PlayCircle } from 'lucide-react';
```

- [ ] **Step 2: `openActivate` handler**

Current (lines 87–90):

```ts
  const openReturn = (contract: TestDriveContract) => {
    Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
    navigate(`/sales/test-drive/${contract.id}/return`);
  };
```

Replace with:

```ts
  const openReturn = (contract: TestDriveContract) => {
    Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
    navigate(`/sales/test-drive/${contract.id}/return`);
  };

  const openActivate = (contract: TestDriveContract) => {
    Haptics.impact({ style: ImpactStyle.Light }).catch(() => {});
    navigate(`/sales/test-drive/${contract.id}/activate`);
  };
```

- [ ] **Step 3: Pass `onActivate` down to `TestDriveCard`**

Current (lines 185–189):

```tsx
        {!isLoading &&
          !isError &&
          items.map((contract) => (
            <TestDriveCard key={contract.id} contract={contract} onOpen={openTestDrive} onReturn={openReturn} />
          ))}
```

Replace with:

```tsx
        {!isLoading &&
          !isError &&
          items.map((contract) => (
            <TestDriveCard
              key={contract.id}
              contract={contract}
              onOpen={openTestDrive}
              onReturn={openReturn}
              onActivate={openActivate}
            />
          ))}
```

- [ ] **Step 4: `TestDriveCard` — swap the Retur shortcut for Începe on PLANNED rows**

Current (lines 195–259):

```tsx
function TestDriveCard({
  contract,
  onOpen,
  onReturn,
}: {
  contract: TestDriveContract;
  onOpen: (contract: TestDriveContract) => void;
  onReturn: (contract: TestDriveContract) => void;
}) {
  const tester = contract.client_name || (contract.client_id != null ? `Client #${contract.client_id}` : '—');
  const vehicle = contract.registration_number || contract.vin || '—';
  const status = deriveTdStatus(contract);
  const badge = tdStatusBadge(status);
  // The return isn't done unless the contract is COMPLETED — show the Retur
  // shortcut for both 'driving' and 'incomplete'.
  const returnDone = status === 'complete';

  return (
    <div className="flex items-stretch gap-1 w-full rounded-2xl bg-card">
      <button
        onClick={() => onOpen(contract)}
        className="flex min-w-0 flex-1 items-center gap-3 p-4 text-left active:scale-[0.98] transition-transform touch-target"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-100">
          <Car className="h-4 w-4 text-blue-600" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold truncate">{tester}</span>
            <span
              className={cn(
                'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide',
                badge.className,
              )}
            >
              {badge.label}
            </span>
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5 truncate">
            <Gauge className="h-3 w-3 shrink-0" />
            <span className="truncate">{vehicle}</span>
          </div>
          <div className="flex items-center justify-between gap-2 mt-1">
            <span className="flex items-center gap-1 text-xs text-muted-foreground truncate">
              <User2 className="h-3 w-3 shrink-0" />
              {contract.advisor_name || '—'}
            </span>
            <span className="text-xs text-muted-foreground shrink-0">{formatDateTime(contract.departure_datetime)}</span>
          </div>
        </div>
      </button>

      {!returnDone && (
        <button
          onClick={() => onReturn(contract)}
          aria-label="Completează retur"
          className="flex shrink-0 flex-col items-center justify-center gap-0.5 rounded-r-2xl pr-4 pl-2 text-jarvis active:scale-95 transition-transform touch-target"
        >
          <RotateCcw className="h-5 w-5" />
          <span className="text-[10px] font-semibold uppercase tracking-wide">Retur</span>
        </button>
      )}
    </div>
  );
}
```

Replace with:

```tsx
function TestDriveCard({
  contract,
  onOpen,
  onReturn,
  onActivate,
}: {
  contract: TestDriveContract;
  onOpen: (contract: TestDriveContract) => void;
  onReturn: (contract: TestDriveContract) => void;
  onActivate: (contract: TestDriveContract) => void;
}) {
  const tester = contract.client_name || (contract.client_id != null ? `Client #${contract.client_id}` : '—');
  const vehicle = contract.registration_number || contract.vin || '—';
  const status = deriveTdStatus(contract);
  const badge = tdStatusBadge(status);
  const isPlanned = status === 'planned';
  // The return isn't done unless the contract is COMPLETED — show the Retur
  // shortcut for both 'driving' and 'incomplete' (not for 'planned', which
  // gets the "Începe" shortcut instead).
  const returnDone = status === 'complete';

  return (
    <div className="flex items-stretch gap-1 w-full rounded-2xl bg-card">
      <button
        onClick={() => onOpen(contract)}
        className="flex min-w-0 flex-1 items-center gap-3 p-4 text-left active:scale-[0.98] transition-transform touch-target"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-100">
          <Car className="h-4 w-4 text-blue-600" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold truncate">{tester}</span>
            <span
              className={cn(
                'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide',
                badge.className,
              )}
            >
              {badge.label}
            </span>
          </div>
          <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5 truncate">
            <Gauge className="h-3 w-3 shrink-0" />
            <span className="truncate">{vehicle}</span>
          </div>
          <div className="flex items-center justify-between gap-2 mt-1">
            <span className="flex items-center gap-1 text-xs text-muted-foreground truncate">
              <User2 className="h-3 w-3 shrink-0" />
              {contract.advisor_name || '—'}
            </span>
            <span className="text-xs text-muted-foreground shrink-0">{formatDateTime(contract.departure_datetime)}</span>
          </div>
        </div>
      </button>

      {isPlanned ? (
        <button
          onClick={() => onActivate(contract)}
          aria-label="Începe sesiunea"
          className="flex shrink-0 flex-col items-center justify-center gap-0.5 rounded-r-2xl pr-4 pl-2 text-indigo-600 active:scale-95 transition-transform touch-target"
        >
          <PlayCircle className="h-5 w-5" />
          <span className="text-[10px] font-semibold uppercase tracking-wide">Începe</span>
        </button>
      ) : (
        !returnDone && (
          <button
            onClick={() => onReturn(contract)}
            aria-label="Completează retur"
            className="flex shrink-0 flex-col items-center justify-center gap-0.5 rounded-r-2xl pr-4 pl-2 text-jarvis active:scale-95 transition-transform touch-target"
          >
            <RotateCcw className="h-5 w-5" />
            <span className="text-[10px] font-semibold uppercase tracking-wide">Retur</span>
          </button>
        )
      )}
    </div>
  );
}
```

- [ ] **Step 5: Build gate**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run build && npx cap sync android`
Expected: exits 0.

- [ ] **Step 6: Manual verification**

Open `/sales/test-drive` with at least one `PLANNED` draft in the "Active" list. Confirm the row shows the indigo "Planificat" badge and an indigo "Începe" shortcut (not "Retur") on the right edge; tapping it navigates to `/sales/test-drive/{id}/activate`. Rows in `driving`/`incomplete` still show "Retur" as before; `complete` rows show neither shortcut.

- [ ] **Step 7: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/pages/Sales/TestDrive/index.tsx
git commit -m "$(cat <<'EOF'
feat(test-drive): list-row Începe shortcut for PLANNED sessions

Replaces the Retur shortcut with an indigo "Începe" shortcut (PlayCircle) on
PLANNED rows, navigating straight to the activation route. The Planificat
badge itself is automatic via useApi's deriveTdStatus/tdStatusBadge.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `Calendar.tsx` — list-grouped-by-day agenda screen

**Files:**
- Create: `src/pages/Sales/TestDrive/Calendar.tsx`
- Modify: `src/App.tsx`
- Modify: `src/pages/Sales/TestDrive/index.tsx`

**Interfaces:**
- Consumes: `useTestDrives`, `deriveTdStatus`, `tdStatusBadge` (existing + Task 1's `'planned'` state).
- Produces: `/sales/test-drive/calendar` — planned + live (excludes finalized) TD sessions grouped by departure day, ascending; a header icon on the list screen navigates there.

- [ ] **Step 1: Create `Calendar.tsx`**

```tsx
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, CalendarDays, Car } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTestDrives, deriveTdStatus, tdStatusBadge, type TestDriveContract } from '@/hooks/useApi';

/** Groups by the departure date (YYYY-MM-DD, UTC-based — grouping only,
 *  display uses the browser's local timezone via toLocaleDateString/Time). */
function dayKey(iso: string | null | undefined): string {
  if (!iso) return 'unknown';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'unknown';
  return d.toISOString().slice(0, 10);
}

function dayLabel(key: string): string {
  if (key === 'unknown') return 'Fără dată';
  const d = new Date(`${key}T00:00:00`);
  return d.toLocaleDateString('ro-RO', { weekday: 'long', day: '2-digit', month: 'long' });
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' });
}

/** Calendar/agenda screen for the Driving Sessions app: planned + live TD
 *  sessions (excludes finalized ones), grouped by departure day, ascending —
 *  the simplest mobile shape for "Plan a Driving Session"'s calendar (design
 *  spec: list-grouped-by-day). Reuses the same contracts query as the main
 *  list (`useTestDrives`, per_page=100, client-side filtered) — there's no
 *  dedicated range endpoint (Phase 1 backend reuses GET /contracts).
 *  Nested under the Sales mini-app launcher at /sales/test-drive/calendar. */
export default function TestDriveCalendar() {
  const navigate = useNavigate();
  const { data: testDrives, isLoading, isError } = useTestDrives();

  const groups = useMemo(() => {
    const upcoming = (testDrives ?? []).filter((c) => {
      const status = deriveTdStatus(c);
      return status === 'planned' || status === 'driving' || status === 'incomplete';
    });
    const byDay = new Map<string, TestDriveContract[]>();
    for (const c of upcoming) {
      const key = dayKey(c.departure_datetime);
      const list = byDay.get(key) ?? [];
      list.push(c);
      byDay.set(key, list);
    }
    for (const list of byDay.values()) {
      list.sort((a, b) => (a.departure_datetime || '').localeCompare(b.departure_datetime || ''));
    }
    return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [testDrives]);

  return (
    <div className="flex flex-col pb-28">
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <button
          onClick={() => navigate('/sales/test-drive')}
          className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary touch-target"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-bold flex-1">Calendar Sesiuni</h1>
      </div>

      <div className="space-y-4 px-4">
        {isLoading && (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-16 rounded-2xl bg-card animate-pulse" />
            ))}
          </div>
        )}

        {!isLoading && isError && (
          <p className="text-sm text-destructive px-1 py-8 text-center">Nu s-a putut încărca calendarul.</p>
        )}

        {!isLoading && !isError && groups.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-secondary">
              <CalendarDays className="h-8 w-8 text-muted-foreground/40" />
            </div>
            <p className="text-sm text-muted-foreground">Nicio sesiune planificată sau în desfășurare</p>
          </div>
        )}

        {!isLoading &&
          !isError &&
          groups.map(([key, items]) => (
            <div key={key} className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide px-1">{dayLabel(key)}</p>
              <div className="space-y-2">
                {items.map((c) => (
                  <CalendarRow key={c.id} contract={c} onOpen={() => navigate(`/sales/test-drive/${c.id}`)} />
                ))}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}

function CalendarRow({ contract, onOpen }: { contract: TestDriveContract; onOpen: () => void }) {
  const badge = tdStatusBadge(deriveTdStatus(contract));
  const vehicle = contract.registration_number || contract.vin || '—';
  const tester = contract.client_name || (contract.client_id != null ? `Client #${contract.client_id}` : '—');

  return (
    <button
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-2xl bg-card p-3.5 text-left active:scale-[0.98] transition-transform touch-target"
    >
      <div className="flex h-9 w-9 shrink-0 flex-col items-center justify-center rounded-xl bg-secondary">
        <span className="text-xs font-bold leading-none">{formatTime(contract.departure_datetime)}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold truncate">{tester}</span>
          <span
            className={cn(
              'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide',
              badge.className,
            )}
          >
            {badge.label}
          </span>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5 truncate">
          <Car className="h-3 w-3 shrink-0" />
          <span className="truncate">{vehicle}</span>
        </div>
      </div>
    </button>
  );
}
```

- [ ] **Step 2: Register the route in `App.tsx`**

Current (post-Task-4):

```tsx
import Sales from '@/pages/Sales';
import TestDriveList from '@/pages/Sales/TestDrive';
import NewTestDrive from '@/pages/Sales/TestDrive/New';
import TestDriveDetail from '@/pages/Sales/TestDrive/Detail';
import TestDriveReturn from '@/pages/Sales/TestDrive/Return';
```

Replace with:

```tsx
import Sales from '@/pages/Sales';
import TestDriveList from '@/pages/Sales/TestDrive';
import NewTestDrive from '@/pages/Sales/TestDrive/New';
import TestDriveDetail from '@/pages/Sales/TestDrive/Detail';
import TestDriveReturn from '@/pages/Sales/TestDrive/Return';
import TestDriveCalendar from '@/pages/Sales/TestDrive/Calendar';
```

Current (post-Task-4 route list):

```tsx
          <Route path="/sales" element={<ErrorBoundary section="Sales"><Sales /></ErrorBoundary>} />
          <Route path="/sales/test-drive" element={<ErrorBoundary section="Sales"><TestDriveList /></ErrorBoundary>} />
          {/* Static "new" route declared before the dynamic ":id" route below
              so it can't be shadowed by it (matched first regardless of
              React Router's own specificity scoring). */}
          <Route path="/sales/test-drive/new" element={<ErrorBoundary section="Sales"><NewTestDrive /></ErrorBoundary>} />
          <Route path="/sales/test-drive/:id" element={<ErrorBoundary section="Sales"><TestDriveDetail /></ErrorBoundary>} />
          <Route path="/sales/test-drive/:id/return" element={<ErrorBoundary section="Sales"><TestDriveReturn /></ErrorBoundary>} />
          {/* Activation route — reopens NewTestDrive pre-filled from a PLANNED
              draft; NewTestDrive reads the `id` param via useParams to switch
              into activation mode. */}
          <Route path="/sales/test-drive/:id/activate" element={<ErrorBoundary section="Sales"><NewTestDrive /></ErrorBoundary>} />
```

Replace with:

```tsx
          <Route path="/sales" element={<ErrorBoundary section="Sales"><Sales /></ErrorBoundary>} />
          <Route path="/sales/test-drive" element={<ErrorBoundary section="Sales"><TestDriveList /></ErrorBoundary>} />
          {/* Static "new"/"calendar" routes declared before the dynamic ":id"
              route below so they can't be shadowed by it (matched first
              regardless of React Router's own specificity scoring). */}
          <Route path="/sales/test-drive/new" element={<ErrorBoundary section="Sales"><NewTestDrive /></ErrorBoundary>} />
          <Route path="/sales/test-drive/calendar" element={<ErrorBoundary section="Sales"><TestDriveCalendar /></ErrorBoundary>} />
          <Route path="/sales/test-drive/:id" element={<ErrorBoundary section="Sales"><TestDriveDetail /></ErrorBoundary>} />
          <Route path="/sales/test-drive/:id/return" element={<ErrorBoundary section="Sales"><TestDriveReturn /></ErrorBoundary>} />
          {/* Activation route — reopens NewTestDrive pre-filled from a PLANNED
              draft; NewTestDrive reads the `id` param via useParams to switch
              into activation mode. */}
          <Route path="/sales/test-drive/:id/activate" element={<ErrorBoundary section="Sales"><NewTestDrive /></ErrorBoundary>} />
```

- [ ] **Step 3: Entry-point icon on the list header**

Current (`src/pages/Sales/TestDrive/index.tsx`, post-Task-6 import line):

```ts
import { ChevronLeft, Plus, Car, User2, Gauge, RotateCcw, PlayCircle } from 'lucide-react';
```

Replace with:

```ts
import { ChevronLeft, Plus, Car, User2, Gauge, RotateCcw, PlayCircle, CalendarDays } from 'lucide-react';
```

Current (`index.tsx`, list header block):

```tsx
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <button
          onClick={() => navigate('/sales')}
          className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary touch-target"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-bold flex-1">Driving Sessions</h1>
      </div>
```

Replace with:

```tsx
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <button
          onClick={() => navigate('/sales')}
          className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary touch-target"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-bold flex-1">Driving Sessions</h1>
        <button
          onClick={() => navigate('/sales/test-drive/calendar')}
          aria-label="Calendar sesiuni"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary touch-target"
        >
          <CalendarDays className="h-5 w-5" />
        </button>
      </div>
```

- [ ] **Step 4: Build gate**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npm run build && npx cap sync android`
Expected: exits 0.

- [ ] **Step 5: Manual verification**

`npm run dev`, open `/sales/test-drive`, tap the new calendar icon in the header → lands on `/sales/test-drive/calendar`. Confirm sessions are grouped under Romanian day headers ("luni, 21 iulie" etc.), sorted ascending by day then by departure time within the day; each row shows time / client / status badge / vehicle; `complete` sessions are absent; tapping a row opens its detail page; the back chevron returns to the list.

- [ ] **Step 6: Commit**

```bash
cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2
git add src/pages/Sales/TestDrive/Calendar.tsx src/App.tsx src/pages/Sales/TestDrive/index.tsx
git commit -m "$(cat <<'EOF'
feat(test-drive): add list-grouped-by-day Calendar screen

New /sales/test-drive/calendar agenda: planned + live TD sessions (excludes
finalized), grouped by departure day ascending, reusing the same contracts
query as the main list. Reachable via a header icon on the Driving Sessions
list.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage (Phase 3 items from the design spec + controller scope):**
- Draft create ("Planifică (draft)" beside "Trimite", relaxed signature/GDPR/general-conditions, future date allowed) → Task 3. ✔
- Activation ("Începe sesiunea" → reopens prefilled → capture signature → `PUT .../activate`) → Task 4 (form), Task 5 (detail entry point), Task 6 (list entry point). ✔
- Discard (confirm → delete) → Task 5. ✔
- Status badge — "Planificat" checked before `td_status` mapping → Task 1 (`deriveTdStatus`/`tdStatusBadge`), surfaced automatically in Task 5 (detail) and Task 6 (list). ✔
- Calendar/agenda, list-grouped-by-day, planned + live sessions → Task 7. ✔
- Conflict soft-block before planning/submitting/activating → Task 1 (`useVehicleConflicts`), Task 2 (`ConflictSheet`), wired in Task 3 (create/plan) and Task 4 (activate). ✔
- Mobile deploy rule (`npm run build && npx cap sync android` after each committed change) → present as an explicit gate step in every task. ✔

**Placeholder scan:** No TBD/TODO in any code block; every task shows full code for new files and exact quoted current/replacement pairs for edits — no elisions except explicitly-labeled "post-Task-N" context blocks that quote the *actual* resulting text of the prior task's edit (not a placeholder, a real intermediate state). ✔

**Type/name consistency:** `usePlanTestDrive`/`useActivateTestDrive`/`useDiscardTestDrive`/`useVehicleConflicts`, `PlanTestDrivePayload`/`ActivateTestDrivePayload`/`VehicleConflict`, `ConflictSheet`, `TestDriveCalendar`, `deriveTdStatus`/`tdStatusBadge`'s `'planned'` case, and the `/sales/test-drive/:id/activate` + `/sales/test-drive/calendar` routes are referenced identically everywhere they're used across all 7 tasks. `draftMissing`/`draftValid` vs `missing`/`formValid` naming mirrors the existing codebase's `missing`/`formValid` convention rather than inventing new terminology. ✔

**Risks / assumptions for the controller to verify before executing:**
1. **Driver-license requirement kept for drafts** (Global Constraints, Task 3) — the scope text relaxes only signature/GDPR/general-conditions; `driver_license_photo` stays required to save a draft. If the real-world workflow is "plan a session before the client is even identified," this needs relaxing too (straightforward: move `license` out of `draftMissing` in Task 3 Step 3).
2. **Code was authored by careful reading of the real files, not compiled** — no `tsc`/`vitest` run was executed while writing this plan (only source was read, per the read-only mandate). Each task's Step "Build gate" is the actual verification; minor TS friction (e.g. an exact literal-type mismatch) is plausible on first run and should be fixed in place during execution, not treated as a plan defect.
3. **Discard is Detail-only, not on the list row** (deviation from the web plan, called out in Global Constraints) — confirm this matches user expectations; adding a second discard entry point on the list row (mirroring web) is a small follow-up if wanted.
4. **Activation route is path-based** (`/sales/test-drive/:id/activate`), diverging from the web plan's `?activate={id}` query param — intentional, to match this repo's exclusively path-based routing convention; flagging in case cross-platform URL parity is desired later.
