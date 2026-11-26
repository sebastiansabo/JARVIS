# Stale-Tab "New Version Available" Detector — Design

**Date:** 2026-11-26
**Status:** Approved (short design, small change)

## Intent / Why
Long-open SPA tabs keep running the JavaScript they loaded at tab-open time; a
deploy never touches them, so they silently run stale code. This caused the
"Tip stoc resets on Edit" report (the Oct-15 category fix was live in prod, but
a pre-fix tab never reloaded). This feature makes any open tab notice a newer
frontend build and offer a reload **on the user's terms**, so stale tabs
self-heal without losing unsaved work.

## Goals
- Detect a newer frontend build from any open tab (all users, all pages).
- Show a slim, **dismissible** banner with a manual "Reîncarcă" button.
- Frontend-owned version id so the baked value and the served value can never drift.
- Minimal backend surface (one route).

## Non-goals
- No auto-reload of any kind.
- No service worker / PWA.
- No backend-API version compatibility or mobile-app versioning.

## Anti-goals (failure even if it "works")
- Wiping unsaved form data (the exact thing we're protecting).
- A naggy / flickering banner.
- A false banner on auth redirects, offline, or network blips.

## Existing mechanisms (build on, don't duplicate)
- `src/lib/chunkReload.ts` + `main.tsx` already force a cache-busted reload when a
  stale tab tries to lazy-load a now-missing chunk (reactive, fires on
  navigation). This feature covers the complementary gap: a stale tab sitting on
  an already-loaded page that never navigates. The two do not overlap — chunkReload
  fires on dynamic-import failure; this fires on a version.json mismatch and only
  *prompts*.
- `main.tsx` already runs a 10-min `/health` keep-alive interval — same pattern the
  poll mirrors.
- UI: `sonner` toasts and `components/ui/button.tsx` exist; no generic banner component.

## Approaches considered
1. **Frontend-owned build id + polled `version.json` (CHOSEN).** Vite stamps a build
   id into the bundle and emits a matching `version.json`; the tab polls and compares.
   One build produces both, so they can't drift. ~One backend route.
2. Backend build id via Docker `ARG` → `/version` endpoint, compared to a baked id.
   Rejected: frontend and backend build in separate Docker stages, so keeping the two
   ids in sync is awkward; more moving parts for no benefit.
3. Re-fetch `index.html` and diff the entry `<script>` hash. Rejected: HTML parsing is
   fragile vs. a purpose-built JSON file.

## How it works
1. **Build id:** `vite.config.ts` computes `BUILD_ID` (a build-time timestamp) and
   exposes it via `define: { __APP_BUILD__: JSON.stringify(BUILD_ID) }`.
2. **Emit `version.json`:** a small inline Vite plugin writes `version.json`
   (`{"build": "<BUILD_ID>"}`) into the build `outDir` (`../static/react`), so the
   served file and the baked constant come from the same build.
3. **Serve it:** a new Flask route `GET /version.json` serves that file with
   `Cache-Control: no-store`, **no auth** (so public tabs and expired sessions get
   JSON, never a login redirect). Placed before the SPA routes.
4. **Compare:** `useVersionCheck` polls `version.json` (~every 2 min + on tab
   refocus/visibility regain), and compares the served `build` to `__APP_BUILD__`.
   Any non-OK / non-JSON / missing-field response is ignored (no false positive).
5. **Banner:** rendered in the `App` root when an update is pending:
   `🔄 Versiune nouă disponibilă — [Reîncarcă]` + dismiss (×). Reîncarcă calls
   `window.location.reload()`. Dismiss hides it; it reappears on the next refocus
   while still stale.

## Reload style (decided)
**Dismissible banner + manual reload only.** Never auto-reload — the user controls
timing so a half-filled form is never lost. (Chosen over auto-reload-on-navigation,
which leaves a long-open edit page stale, and immediate auto-reload, which wipes
unsaved edits.)

## Testing
- Unit-test the pure compare/parse logic: equal id → no banner; different id → banner;
  null/HTML/missing-field response → no banner.
- Build + `curl /version.json` to verify the emitted file and the no-store header.
- Manual e2e: load app, bump the served `version.json` build value, confirm the banner
  appears on refocus and that Reîncarcă reloads.

## Left to builder
- Exact banner styling (reuse `button.tsx` + Tailwind; match app surfaces).
- Precise dismiss/reappear timing.
