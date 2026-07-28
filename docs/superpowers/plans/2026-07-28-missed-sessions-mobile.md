# Missed Sessions — Mobile Implementation Plan (jarvis-mobile-2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the `late`/`missed` session states in the mobile Test Drive UI, route missed sessions to the archived view, and let a consilier reschedule/revive a late or missed session from a quick bottom-sheet.

**Architecture:** `deriveTdStatus` gains `late`/`missed`, agreeing with the backend's `td_status` and falling back to device-clock grace math. A `RescheduleSheet` (built on the shared `BottomSheet`) collects a new departure/return, reuses the existing VIN soft-block (`useVehicleConflicts` + `ConflictSheet`), and calls a new `useRescheduleTestDrive` hook → `PUT …/reschedule`. The list's active-vs-archived split treats `missed` as archived; the detail page exposes the mode-appropriate actions.

**Tech Stack:** React + TypeScript + Vite + Capacitor 6, `@tanstack/react-query`, `zustand`, Tailwind, `lucide-react`, vitest.

## Global Constraints

- Repo `jarvis-mobile-2`, work on `dev`. After the code changes run `npm run build && npx cap sync android` (mandatory).
- **This ships only after the JARVIS backend half is live** (reschedule endpoint + `td_status` late/missed). The client-side grace math means badges/filtering render correctly even before backend `td_status` deploys, but reschedule needs the endpoint.
- Grace window is **8 hours**; client constant `const GRACE_MS = 8 * 60 * 60 * 1000;`.
- Romanian copy: badges `Întârziat` (late) / `Ratată` (missed); sheet title `Reprogramează sesiunea`; primary button `Reprogramează`.
- Do NOT hold `2.0.35` for the license-plan fix separately — per the sequencing decision this feature ships **together** with that fix in one build.
- Design spec: `docs/superpowers/specs/2026-07-28-missed-sessions-design.md` (in the JARVIS repo).

---

## File Structure

- Modify `src/hooks/useApi.ts` — `TdStatus`, `deriveTdStatus`, `tdStatusBadge`, `td_status` union; add `RescheduleTestDrivePayload` + `useRescheduleTestDrive`.
- Create `src/pages/Sales/TestDrive/RescheduleSheet.tsx` — the bottom-sheet + a pure `rescheduleError()` validation helper (exported for tests).
- Create `src/pages/Sales/TestDrive/RescheduleSheet.test.ts` — unit tests for `rescheduleError`.
- Modify `src/hooks/useApi.test.ts` — `deriveTdStatus`/`tdStatusBadge` cases for late/missed.
- Modify `src/pages/Sales/TestDrive/index.tsx` — archived filter includes `missed`; wire `RescheduleSheet` + a `Reprogramează` row action for late/missed.
- Modify `src/pages/Sales/TestDrive/Detail.tsx` — late → Activate + Reschedule + Discard; missed → Reschedule + read-only.

---

### Task 1: `late`/`missed` statuses + badges

**Files:**
- Modify: `src/hooks/useApi.ts` (`TdStatus` ~946, `deriveTdStatus` ~958, `tdStatusBadge` ~972, `td_status` field ~699)
- Modify: `src/hooks/useApi.test.ts`

**Interfaces:**
- Produces: `TdStatus = 'planned' | 'late' | 'driving' | 'incomplete' | 'complete' | 'missed'`; `deriveTdStatus(c) -> TdStatus`; `tdStatusBadge(status)` returns amber for `late`, gray for `missed`.

- [ ] **Step 1: Extend the failing tests**

Add to `src/hooks/useApi.test.ts`:

```typescript
const HOUR = 3600_000;

describe('deriveTdStatus — late/missed', () => {
  it('is late for a PLANNED draft past departure within 8h', () => {
    const dep = new Date(Date.now() - HOUR).toISOString();
    expect(deriveTdStatus(contract({ status: 'PLANNED', departure_datetime: dep }))).toBe('late');
  });

  it('is missed for a PLANNED draft past departure + 8h', () => {
    const dep = new Date(Date.now() - 9 * HOUR).toISOString();
    expect(deriveTdStatus(contract({ status: 'PLANNED', departure_datetime: dep }))).toBe('missed');
  });

  it('is missed for an archived MISSED row', () => {
    expect(deriveTdStatus(contract({ status: 'MISSED' }))).toBe('missed');
  });

  it('prefers backend td_status late/missed over planned', () => {
    expect(deriveTdStatus(contract({ status: 'PLANNED', td_status: 'late' }))).toBe('late');
    expect(deriveTdStatus(contract({ status: 'PLANNED', td_status: 'missed' }))).toBe('missed');
  });

  it('stays planned for a future PLANNED draft', () => {
    const dep = new Date(Date.now() + HOUR).toISOString();
    expect(deriveTdStatus(contract({ status: 'PLANNED', departure_datetime: dep }))).toBe('planned');
  });
});

describe('tdStatusBadge — late/missed', () => {
  it('labels late as Întârziat (amber) and missed as Ratată (gray)', () => {
    expect(tdStatusBadge('late')).toEqual({ label: 'Întârziat', className: 'bg-amber-500/15 text-amber-600' });
    expect(tdStatusBadge('missed')).toEqual({ label: 'Ratată', className: 'bg-muted text-muted-foreground' });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npx vitest run src/hooks/useApi.test.ts`
Expected: FAIL (late/missed unhandled; badge returns default "În curs").

- [ ] **Step 3: Update the type + derivation + badge**

In `useApi.ts`, widen the field union (~line 699):

```typescript
  td_status?: 'driving' | 'incomplete' | 'complete' | 'late' | 'missed' | string | null;
```

Replace `TdStatus` (~line 946):

```typescript
export type TdStatus = 'planned' | 'late' | 'driving' | 'incomplete' | 'complete' | 'missed';

const GRACE_MS = 8 * 60 * 60 * 1000;
```

Replace `deriveTdStatus` (~line 958):

```typescript
export function deriveTdStatus(c: TestDriveContract): TdStatus {
  if (c.status === 'MISSED') return 'missed';
  // Prefer the backend-derived value once it resolves the planned sub-states.
  if (c.td_status === 'missed' || c.td_status === 'late') return c.td_status;
  if (c.status === 'PLANNED') {
    const dep = c.departure_datetime ? new Date(c.departure_datetime).getTime() : NaN;
    if (!Number.isNaN(dep)) {
      if (dep + GRACE_MS < Date.now()) return 'missed';
      if (dep < Date.now()) return 'late';
    }
    return 'planned';
  }
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
```

Add two cases to `tdStatusBadge` (before `default:`):

```typescript
    case 'late':
      return { label: 'Întârziat', className: 'bg-amber-500/15 text-amber-600' };
    case 'missed':
      return { label: 'Ratată', className: 'bg-muted text-muted-foreground' };
```

- [ ] **Step 4: Run to verify all deriveTdStatus/badge tests pass**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npx vitest run src/hooks/useApi.test.ts`
Expected: PASS (existing planned/driving cases + the new late/missed cases).

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useApi.ts src/hooks/useApi.test.ts
git commit -m "feat(test-drive): derive late/missed session statuses + badges"
```

---

### Task 2: `useRescheduleTestDrive` hook

**Files:**
- Modify: `src/hooks/useApi.ts` (near `useUpdatePlan` / `useActivateTestDrive`, ~line 1055-1087)

**Interfaces:**
- Consumes: `apiFetch`, `TestDriveSubmitResponse` (existing).
- Produces: `RescheduleTestDrivePayload { departure_datetime: string; return_datetime?: string }`; `useRescheduleTestDrive(id)` mutation.

- [ ] **Step 1: Add the payload type + hook**

```typescript
/** Reschedule/revive a PLANNED (late) or MISSED session to a new future time. */
export interface RescheduleTestDrivePayload {
  departure_datetime: string;
  return_datetime?: string;
}

export function useRescheduleTestDrive(id: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RescheduleTestDrivePayload) =>
      apiFetch<TestDriveSubmitResponse>(`/api/foi-parcurs/test-drive/${id}/reschedule`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-drives'] });
      qc.invalidateQueries({ queryKey: ['test-drive', id] });
    },
  });
}
```

- [ ] **Step 2: Typecheck**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add src/hooks/useApi.ts
git commit -m "feat(test-drive): useRescheduleTestDrive mutation hook"
```

---

### Task 3: `RescheduleSheet` component + validation helper

**Files:**
- Create: `src/pages/Sales/TestDrive/RescheduleSheet.tsx`
- Create: `src/pages/Sales/TestDrive/RescheduleSheet.test.ts`

**Interfaces:**
- Consumes: `BottomSheet` (default export, `{open, onClose, title, children}`), `useRescheduleTestDrive`, `useVehicleConflicts` + `ConflictSheet` (existing soft-block), `ApiError`.
- Produces:
  - `rescheduleError(departure: string, ret: string, todayStr: string) -> 'departure_required' | 'departure_past' | 'return_before_departure' | null` (pure).
  - `RescheduleSheet({ open, onClose, contractId, vin, onDone })` — bottom-sheet with two `datetime-local` inputs; VIN soft-block; calls the hook.

- [ ] **Step 1: Write the failing validation test**

`src/pages/Sales/TestDrive/RescheduleSheet.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { rescheduleError } from './RescheduleSheet';

const TODAY = '2026-07-28';

describe('rescheduleError', () => {
  it('requires a departure', () => {
    expect(rescheduleError('', '', TODAY)).toBe('departure_required');
  });
  it('rejects a past departure date', () => {
    expect(rescheduleError('2026-07-27T10:00', '', TODAY)).toBe('departure_past');
  });
  it('rejects a return before departure', () => {
    expect(rescheduleError('2026-07-29T10:00', '2026-07-29T09:00', TODAY)).toBe('return_before_departure');
  });
  it('accepts a valid future departure with later return', () => {
    expect(rescheduleError('2026-07-29T10:00', '2026-07-29T11:00', TODAY)).toBeNull();
  });
  it('accepts a valid departure with no return', () => {
    expect(rescheduleError('2026-07-29T10:00', '', TODAY)).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npx vitest run src/pages/Sales/TestDrive/RescheduleSheet.test.ts`
Expected: FAIL (module/export missing).

- [ ] **Step 3: Implement `RescheduleSheet.tsx`**

```tsx
import { useState } from 'react';
import { CalendarClock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ApiError } from '@/services/api';
import BottomSheet from '@/components/shared/BottomSheet';
import { useRescheduleTestDrive, useVehicleConflicts, type VehicleConflict } from '@/hooks/useApi';
import { ConflictSheet } from './ConflictSheet';

const inputClass =
  'w-full h-11 rounded-xl bg-secondary px-3.5 text-base text-foreground outline-none focus:ring-2 focus:ring-jarvis/40 transition-all';

function pad(n: number) { return String(n).padStart(2, '0'); }
function localValue(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Pure validation for the reschedule inputs. `todayStr` is 'YYYY-MM-DD' local. */
export function rescheduleError(
  departure: string, ret: string, todayStr: string,
): 'departure_required' | 'departure_past' | 'return_before_departure' | null {
  if (!departure) return 'departure_required';
  if (departure.slice(0, 10) < todayStr) return 'departure_past';
  if (ret && ret < departure) return 'return_before_departure';
  return null;
}

const MESSAGES: Record<string, string> = {
  departure_required: 'Alege data plecării.',
  departure_past: 'Nu poți reprograma în trecut.',
  return_before_departure: 'Data sosirii nu poate fi înainte de plecare.',
};

export function RescheduleSheet({
  open, onClose, contractId, vin, onDone,
}: {
  open: boolean;
  onClose: () => void;
  contractId: string;
  vin: string | null;
  onDone?: () => void;
}) {
  const now = new Date();
  const [departure, setDeparture] = useState(() => localValue(new Date(now.getTime() + 60 * 60 * 1000)));
  const [ret, setRet] = useState(() => localValue(new Date(now.getTime() + 2 * 60 * 60 * 1000)));
  const [error, setError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<VehicleConflict[]>([]);
  const [showConflicts, setShowConflicts] = useState(false);

  const reschedule = useRescheduleTestDrive(contractId);
  const { checking, check } = useVehicleConflicts();

  const todayStr = localValue(new Date()).slice(0, 10);

  const run = () => {
    reschedule.mutate(
      { departure_datetime: departure, ...(ret ? { return_datetime: ret } : {}) },
      {
        onSuccess: () => { onDone?.(); onClose(); },
        onError: (e) => setError(e instanceof ApiError ? e.message : 'Reprogramarea a eșuat. Încearcă din nou.'),
      },
    );
  };

  const submit = async () => {
    const err = rescheduleError(departure, ret, todayStr);
    if (err) { setError(MESSAGES[err]); return; }
    setError(null);
    if (vin) {
      const hits = await check(vin, departure, ret || departure, Number(contractId));
      if (hits.length) { setConflicts(hits); setShowConflicts(true); return; }
    }
    run();
  };

  return (
    <>
      <BottomSheet open={open} onClose={onClose} title="Reprogramează sesiunea">
        <div className="space-y-3 px-1 pb-2">
          <label className="block space-y-1">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Data plecării</span>
            <input type="datetime-local" value={departure} min={`${todayStr}T00:00`}
              onChange={(e) => setDeparture(e.target.value)} className={inputClass} />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Data sosirii</span>
            <input type="datetime-local" value={ret} min={departure || undefined}
              onChange={(e) => setRet(e.target.value)} className={inputClass} />
          </label>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <button type="button" onClick={submit} disabled={reschedule.isPending || checking}
            className={cn('w-full h-11 rounded-xl bg-jarvis text-white font-semibold text-sm',
              'flex items-center justify-center gap-1.5 active:scale-[0.98] transition-transform disabled:opacity-50 touch-target')}>
            <CalendarClock className="h-4 w-4" />
            {reschedule.isPending ? 'Se reprogramează...' : 'Reprogramează'}
          </button>
        </div>
      </BottomSheet>
      <ConflictSheet
        open={showConflicts}
        conflicts={conflicts}
        onCancel={() => setShowConflicts(false)}
        onContinue={() => { setShowConflicts(false); run(); }}
      />
    </>
  );
}
```

(Confirm `useVehicleConflicts` returns `{ checking, check }` and `check(vin, from, to, excludeId)` — it does, per `New.tsx`'s `withConflictCheck`. If the property is named `conflictsChecking`, alias accordingly.)

- [ ] **Step 4: Run the validation test to verify it passes**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && npx vitest run src/pages/Sales/TestDrive/RescheduleSheet.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Typecheck**

Run: `npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/pages/Sales/TestDrive/RescheduleSheet.tsx src/pages/Sales/TestDrive/RescheduleSheet.test.ts
git commit -m "feat(test-drive): RescheduleSheet + reschedule validation helper"
```

---

### Task 4: List — route `missed` to archived + `Reprogramează` row action

**Files:**
- Modify: `src/pages/Sales/TestDrive/index.tsx` (filter ~line 70-77; `SessionRow` ~line 220-301)

**Interfaces:**
- Consumes: `deriveTdStatus`, `RescheduleSheet`.
- Produces: archived view shows `complete || missed`; late/missed rows show a `Reprogramează` action opening `RescheduleSheet`.

- [ ] **Step 1: Include `missed` in the archived split**

Replace (lines ~74-75):

```typescript
      const isComplete = deriveTdStatus(c) === 'complete';
      return showArchived ? isComplete : !isComplete;
```
with:

```typescript
      const st = deriveTdStatus(c);
      const isArchived = st === 'complete' || st === 'missed';
      return showArchived ? isArchived : !isArchived;
```

- [ ] **Step 2: Add reschedule sheet state + handler to the list component**

Near the other `open*` handlers (~line 79-97):

```typescript
  const [rescheduleFor, setRescheduleFor] = useState<TestDriveContract | null>(null);
```
and render, before the closing tag of the list container:

```tsx
      {rescheduleFor && (
        <RescheduleSheet
          open={!!rescheduleFor}
          onClose={() => setRescheduleFor(null)}
          contractId={String(rescheduleFor.id)}
          vin={rescheduleFor.vin ?? null}
          onDone={() => setRescheduleFor(null)}
        />
      )}
```
Import at top: `import { RescheduleSheet } from './RescheduleSheet';` and ensure `useState` is imported.

- [ ] **Step 3: Wire a `Reprogramează` action on late/missed rows**

Pass an `onReschedule` prop into `SessionRow` (alongside `onReturn`), and in the row render a `CalendarClock` button when `status === 'late' || status === 'missed'` (mirroring the existing `Retur` shortcut button ~line 285-296):

```tsx
        {(status === 'late' || status === 'missed') && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onReschedule(contract); }}
            className="flex flex-col items-center justify-center gap-0.5 px-2 text-jarvis"
          >
            <CalendarClock className="h-5 w-5" />
            <span className="text-[10px] font-semibold uppercase tracking-wide">Reprog.</span>
          </button>
        )}
```
Wire `onReschedule={setRescheduleFor}` where `SessionRow` is rendered (~line 213). Import `CalendarClock` from `lucide-react`.

- [ ] **Step 4: Typecheck + tests + build**

Run: `npx tsc --noEmit && npx vitest run`
Expected: exit 0, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pages/Sales/TestDrive/index.tsx
git commit -m "feat(test-drive): archive missed sessions + reschedule action in the list"
```

---

### Task 5: Detail — late/missed actions

**Files:**
- Modify: `src/pages/Sales/TestDrive/Detail.tsx`

**Interfaces:**
- Consumes: `deriveTdStatus`, `RescheduleSheet`, existing activate/discard navigation.
- Produces: on the detail page — `late` shows Activează + Reprogramează + Renunță; `missed` shows Reprogramează (revive); both keep the session data read-only.

- [ ] **Step 1: Read the current action block**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && grep -n "deriveTdStatus\|activate\|Discard\|Renunță\|Activează\|status ===" src/pages/Sales/TestDrive/Detail.tsx`
Identify where planned-draft actions (Activează / Renunță) render.

- [ ] **Step 2: Add reschedule state + gate the actions by derived status**

Add near the top of the component:

```tsx
  const st = deriveTdStatus(contract);
  const [rescheduling, setRescheduling] = useState(false);
```
Render the Reschedule button when `st === 'late' || st === 'missed'`:

```tsx
      {(st === 'late' || st === 'missed') && (
        <button
          type="button"
          onClick={() => setRescheduling(true)}
          className="w-full h-11 rounded-xl bg-secondary text-foreground font-semibold text-sm flex items-center justify-center gap-1.5 active:scale-[0.98] transition-transform touch-target"
        >
          <CalendarClock className="h-4 w-4" /> Reprogramează
        </button>
      )}
      {rescheduling && (
        <RescheduleSheet
          open={rescheduling}
          onClose={() => setRescheduling(false)}
          contractId={String(contract.id)}
          vin={contract.vin ?? null}
          onDone={() => setRescheduling(false)}
        />
      )}
```
Keep the existing **Activează** and **Renunță** buttons visible for `planned` **and** `late` (both are still `PLANNED` server-side); hide them for `missed` (revive-only). Import `CalendarClock`, `RescheduleSheet`, and `deriveTdStatus`.

- [ ] **Step 3: Typecheck + build**

Run: `npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add src/pages/Sales/TestDrive/Detail.tsx
git commit -m "feat(test-drive): late/missed actions on the session detail page"
```

---

### Task 6: Deep-link, build, sync, verify

**Files:**
- Verify: `src/services/deepLinks.ts` (push tap → route), `src/services/pushNotifications.ts`

**Interfaces:** none new.

- [ ] **Step 1: Confirm the push deep-link routes to the session**

Run: `cd /Users/sebastiansabo/Documents/Git/jarvis-mobile-2 && grep -n "sales/test-drive\|link\|url\|navigate\|appUrlOpen" src/services/deepLinks.ts src/services/pushNotifications.ts`
The backend sends `link: "/sales/test-drive/{id}"`. Confirm the deep-link handler navigates to that path (the Approvals deep-link, commit `57c7bfb`, is the working pattern). If the handler only whitelists specific prefixes, add `/sales/test-drive/` to the allowed set. If it already routes any in-app path, no change.

- [ ] **Step 2: Full test suite**

Run: `npx vitest run`
Expected: all pass (existing 72 + the new deriveTdStatus/badge/reschedule cases).

- [ ] **Step 3: Production build + Capacitor sync (mandatory)**

Run: `npm run build && npx cap sync android`
Expected: build exit 0; `cap sync` finishes.

- [ ] **Step 4: Manual verification (against the live backend once deployed)**

- A PLANNED session whose start passed shows **Întârziat** (amber) in the active list and offers **Reprog.**
- Rescheduling it to a future time moves it back to **Planificat** and out of the late state.
- A session left >8h shows **Ratată** (gray) in the **archived** view and can be revived via reschedule.
- Tapping the "Sesiune ratată la start" push opens `/sales/test-drive/{id}`.

- [ ] **Step 5: Commit any deep-link change**

```bash
git add -A
git commit -m "chore(test-drive): route missed-session push deep-link to the session"
```

---

## Self-Review

- **Spec coverage:** `late`/`missed` statuses + badges (M1) ✓; reschedule hook (M2) ✓; `RescheduleSheet` with VIN soft-block (M3) ✓; archived-view includes missed + row reschedule action (M4) ✓; detail late→Activate/Reschedule/Discard, missed→Reschedule (M5) ✓; push deep-link (M6) ✓.
- **Placeholder scan:** none; every step has concrete code/tests. The two "confirm the existing hook/handler" notes are checks against current code, not deferred work.
- **Type consistency:** `TdStatus` (six states), `deriveTdStatus`, `tdStatusBadge`, `RescheduleTestDrivePayload`, `useRescheduleTestDrive(id)`, `RescheduleSheet({open,onClose,contractId,vin,onDone})`, and `rescheduleError(departure, ret, todayStr)` are used identically across tasks. Grace = `GRACE_MS` (8h) matches the backend's `GRACE_HOURS`.

## Handoff

Ship this **after** the backend plan (`2026-07-28-missed-sessions-backend.md`) is live. This build carries both the missed-sessions feature and the already-completed "license optional when planning" fix, released together as the next mobile version (supersedes the held `2.0.35`).
