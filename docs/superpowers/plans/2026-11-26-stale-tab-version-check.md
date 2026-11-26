# Stale-Tab "New Version Available" Detector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any open SPA tab detects a newer frontend build and offers a manual reload via a dismissible banner, so stale tabs self-heal without losing unsaved work.

**Architecture:** Vite stamps a build id into the bundle (`__APP_BUILD__`) and emits a matching `version.json`; a no-store Flask route serves it; a React hook polls it and compares; a banner in the App root prompts a manual `window.location.reload()`. Frontend-owned id so baked and served values can't drift. Complements the existing reactive `chunkReload` (which only fires on navigation to a missing chunk).

**Tech Stack:** Vite 7, React 18 + react-router, TanStack Query, sonner, Tailwind; Flask (Python) backend.

**Spec:** `docs/superpowers/specs/2026-11-26-stale-tab-version-check-design.md`

## Global Constraints
- **Never auto-reload.** Reload happens only on the user clicking the banner button. Verbatim from spec.
- **No false positives:** any non-OK / non-JSON / missing-`build` response from `version.json` must be treated as "no update" — never surface the banner.
- Work on a feature branch off `main` (branches are currently aligned); do not commit to `main` directly.
- Frontend tests run with `npx vitest run <path>` from `jarvis/frontend/`.
- Romanian UI copy: banner text `Versiune nouă disponibilă`, button `Reîncarcă`.

## Review Focus
- **Expired session / auth redirect returns HTML, not JSON** → banner must NOT appear (parse returns null). Pinned in Task 3 `parseVersionPayload` tests.
- **Offline / network error during poll** → no banner, no unhandled rejection. Pinned in Task 3 `fetchServerBuild` behavior (returns null on throw) + Task 4 hook swallows.
- **Dev / `version.json` missing (404 or SPA fallback)** → no banner, no console spam. Pinned in Task 3 null-handling tests; Task 2 route returns `{"build": null}` when the file is absent.
- **Equal build id (steady state, every poll)** → never flips the banner on. Pinned in Task 3 `isNewerBuild` test.
- **Server build id present but tab's baked id somehow empty** → treat as no update (don't nag on a malformed baked value). Pinned in Task 3 `isNewerBuild('', 'x')` test → false.

---

### Task 1: Build-id stamp + `version.json` emission (Vite)

**Files:**
- Modify: `jarvis/frontend/vite.config.ts`
- Modify: `jarvis/frontend/src/vite-env.d.ts`

**Interfaces:**
- Produces: a global constant `__APP_BUILD__: string` (replaced at build by Vite `define`), and a built artifact `<outDir>/version.json` = `{"build": "<same id>"}`. Build id = a build-time millisecond timestamp string.

- [ ] **Step 1: Add build id + emit plugin to `vite.config.ts`**

At module top compute one id and reuse it for both the define and the emitted file:
```ts
const BUILD_ID = String(Date.now())
```
Add to the config: `define: { __APP_BUILD__: JSON.stringify(BUILD_ID) }`, and an inline plugin whose `closeBundle` hook writes `version.json` into the resolved `outDir`:
```ts
{
  name: 'emit-version-json',
  apply: 'build',
  closeBundle() {
    const out = path.resolve(__dirname, '../static/react/version.json')
    fs.writeFileSync(out, JSON.stringify({ build: BUILD_ID }))
  },
}
```
(Import `fs` from `node:fs`. `emptyOutDir` runs before `closeBundle`, so the file survives.)

- [ ] **Step 2: Declare the global in `src/vite-env.d.ts`**

Add: `declare const __APP_BUILD__: string`

- [ ] **Step 3: Build and verify the artifact + header plumbing is sound**

Run: `cd jarvis/frontend && npm run build`
Expected: build succeeds; `cat ../static/react/version.json` prints `{"build":"<digits>"}`.

- [ ] **Step 4: Commit**

```bash
git add jarvis/frontend/vite.config.ts jarvis/frontend/src/vite-env.d.ts
git commit -m "build(frontend): stamp __APP_BUILD__ and emit version.json"
```

---

### Task 2: Backend `GET /version.json` route (no-store, no auth)

**Files:**
- Modify: `jarvis/app.py` (add a route alongside the react routes, ~line 525, BEFORE `/assets/<path>`)

**Interfaces:**
- Produces: `GET /version.json` → `200 {"build": "<id>"}` (from `<react_dir>/version.json` when present) or `200 {"build": null}` when the file is absent; `Cache-Control: no-store`; no `@login_required`.

- [ ] **Step 1: Add the route**

Serve the built file with no-store when it exists; otherwise return a null build (dev/test). Use the existing `_react_dir`:
```python
@flask_app.route('/version.json')
def version_json():
    f = os.path.join(_react_dir, 'version.json')
    if os.path.exists(f):
        resp = send_from_directory(_react_dir, 'version.json')
    else:
        resp = jsonify({'build': None})
    resp.headers['Cache-Control'] = 'no-store'
    return resp
```
No `@login_required` (public so expired sessions get JSON, not a login redirect).

- [ ] **Step 2: Verify the route and header locally**

Run (backend running on :5001, per the local launch command):
`curl -si http://localhost:5001/version.json | grep -iE "HTTP/|cache-control|build"`
Expected: `200`, `Cache-Control: no-store`, and a JSON body with a `build` key (value `null` if no build artifact present locally).

- [ ] **Step 3: Commit**

```bash
git add jarvis/app.py
git commit -m "feat(app): serve /version.json no-store for stale-tab detection"
```

---

### Task 3: Version-compare logic + unit tests (pure)

**Files:**
- Create: `jarvis/frontend/src/lib/versionCheck.ts`
- Test: `jarvis/frontend/src/lib/versionCheck.test.ts`

**Interfaces:**
- Consumes: global `__APP_BUILD__` (Task 1).
- Produces:
  - `CURRENT_BUILD: string` (= `__APP_BUILD__`)
  - `parseVersionPayload(body: unknown): string | null` — returns `body.build` when it's a non-empty string, else `null`.
  - `isNewerBuild(current: string, server: string | null): boolean` — `true` iff `current` is non-empty, `server` is non-empty, and they differ.
  - `fetchServerBuild(): Promise<string | null>` — `fetch('/version.json', { cache: 'no-store' })`; on non-OK or any throw or parse failure returns `null`, else `parseVersionPayload(json)`.

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, it, expect } from 'vitest'
import { parseVersionPayload, isNewerBuild } from './versionCheck'

describe('parseVersionPayload', () => {
  it('extracts a string build', () => expect(parseVersionPayload({ build: '123' })).toBe('123'))
  it('null for missing field', () => expect(parseVersionPayload({})).toBeNull())
  it('null for non-object (HTML/text body)', () => expect(parseVersionPayload('<html>')).toBeNull())
  it('null for null/undefined', () => expect(parseVersionPayload(null)).toBeNull())
  it('null for empty-string build', () => expect(parseVersionPayload({ build: '' })).toBeNull())
})

describe('isNewerBuild', () => {
  it('true when server differs', () => expect(isNewerBuild('100', '200')).toBe(true))
  it('false when equal', () => expect(isNewerBuild('100', '100')).toBe(false))
  it('false when server null', () => expect(isNewerBuild('100', null)).toBe(false))
  it('false when current empty', () => expect(isNewerBuild('', '200')).toBe(false))
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis/frontend && npx vitest run src/lib/versionCheck.test.ts`
Expected: FAIL (module/exports not found).

- [ ] **Step 3: Implement `versionCheck.ts`**

Implement the four exports per the Interfaces block. `fetchServerBuild` wraps fetch in try/catch and guards `res.ok`; it needs no test (thin I/O), the two pure functions it composes are tested.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jarvis/frontend && npx vitest run src/lib/versionCheck.test.ts`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/frontend/src/lib/versionCheck.ts jarvis/frontend/src/lib/versionCheck.test.ts
git commit -m "feat(frontend): version-compare logic for stale-tab detection"
```

---

### Task 4: `useVersionCheck` hook + `UpdateBanner` + wire into App

**Files:**
- Create: `jarvis/frontend/src/hooks/useVersionCheck.ts`
- Create: `jarvis/frontend/src/components/UpdateBanner.tsx`
- Modify: `jarvis/frontend/src/App.tsx` (render `<UpdateBanner />` as a sibling above `<Routes>`)

**Interfaces:**
- Consumes: `CURRENT_BUILD`, `fetchServerBuild`, `isNewerBuild` (Task 3).
- Produces: `useVersionCheck(): boolean` (returns `updateAvailable`); `<UpdateBanner />` (self-contained, no props).

- [ ] **Step 1: Implement `useVersionCheck`**

A hook that: on mount and on every `visibilitychange` where `document.visibilityState === 'visible'`, plus a `setInterval` (~120000 ms), calls `fetchServerBuild()` and, if `isNewerBuild(CURRENT_BUILD, server)`, sets state `updateAvailable = true` (latching — never set back to false). Clears interval + listener on unmount. Swallows all fetch errors (relies on `fetchServerBuild` returning null).

- [ ] **Step 2: Implement `UpdateBanner`**

Uses `useVersionCheck()`. Local `dismissed` state. Renders nothing unless `updateAvailable && !dismissed`. When shown: a slim fixed top bar (reuse `components/ui/button.tsx` for the actions) reading `Versiune nouă disponibilă` with a `Reîncarcă` button → `window.location.reload()` and a `×` dismiss button → `setDismissed(true)`. Reset `dismissed` to `false` whenever the tab becomes visible again (so an ignored update re-surfaces on refocus).

- [ ] **Step 3: Wire into `App.tsx`**

Wrap the returned `<Routes>` in a fragment and render `<UpdateBanner />` before it:
```tsx
return (
  <>
    <UpdateBanner />
    <Routes>
      {/* …existing routes unchanged… */}
    </Routes>
  </>
)
```

- [ ] **Step 4: Verify build + typecheck**

Run: `cd jarvis/frontend && npm run build`
Expected: build + typecheck succeed; no unused-symbol or TS errors.

- [ ] **Step 5: Manual e2e verification**

Run the app locally (backend :5001 + `npm run dev` :5173). Load the app, then edit the served `../static/react/version.json` to a different `build` value (or rebuild). On tab refocus the banner appears; clicking `Reîncarcă` reloads and the banner is gone; dismissing hides it and refocus re-shows it while still stale. Confirm no banner when `version.json` is unreachable.

- [ ] **Step 6: Commit**

```bash
git add jarvis/frontend/src/hooks/useVersionCheck.ts jarvis/frontend/src/components/UpdateBanner.tsx jarvis/frontend/src/App.tsx
git commit -m "feat(frontend): new-version banner (manual reload) in App root"
```

---

## Self-Review notes
- **Spec coverage:** build id (T1), version.json served no-store (T1+T2), poll+compare (T3+T4), banner manual-reload-only (T4), no-false-positive on HTML/offline/dev (T3 tests + T2 null route). All spec points mapped.
- **Type consistency:** `parseVersionPayload`/`isNewerBuild`/`fetchServerBuild`/`CURRENT_BUILD` names identical across T3 definition and T4 consumption; `__APP_BUILD__` declared (T1) and consumed (T3).
- **Proportion:** plan carries only the decisions (signatures, exact route, test assertions, copy); bodies left to the implementer except the two Vite snippets and the route, which fix exact integration points.
