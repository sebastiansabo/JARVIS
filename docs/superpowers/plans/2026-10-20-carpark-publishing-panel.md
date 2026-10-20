# CarPark Publishing Panel Redesign + Auto-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the two vehicle-Detail publishing controls (Autovit.ro + Autoworld.ro) into one state-driven panel, and make auto-update ON by default for every published car on both platforms via a periodic ~1h sweep.

**Architecture:** Reuse the existing Shopify freshness + `carpark_listing_schedules` + `listing_autosync` machinery and extend it to Autovit (single account). Backend adds a dedicated `last_published_at` for Autovit, an Autovit freshness classifier, a shared Autovit republish service that both the publish route and the sweep call, schedule-row creation at publish time + a backfill, and a default-on rollout. Frontend replaces the two bespoke controls with one `PlatformPublishRow` fed by per-platform adapters.

**Tech Stack:** Python/Flask + psycopg2 (backend), APScheduler (sweep), React + TypeScript + Vite + shadcn/ui + @tanstack/react-query (frontend). Backend tests: pytest (mostly no-DB, mock-based). Frontend tests: Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-20-carpark-publishing-panel-redesign-design.md`

## Global Constraints

- **Single Autovit account** — scope auto-update + the badge to the primary account `_repo.get_all_by_type('autovit')[0]`; no `account_id` on `carpark_listing_schedules`. (§8 Q-multiaccount)
- **Autovit updates are free** — both platforms sweep at **~1h** default cadence. (§8 Q-cost)
- **Drafts stay in sync** — the Autovit sweep re-pushes `active` AND `unpaid` listings. (§8 Q-draft)
- **Backfill = all currently-published cars, skipping rows with explicit `cadence='manual'`.** (§8 Q-backfill)
- **Auto-push must respect the 422 required-dim guard** — `REQUIRED_DIMENSIONS = {'make','model','body_type','fuel_type','color'}` (`jarvis/carpark/connectors/autovit/taxonomy_map.py:41`); a car with unmapped required dims is **skipped + logged**, never raw-sent, never crashes the sweep. (Anti-goal A3)
- **Kill switch stays** — env `ENABLE_LISTING_AUTOSYNC` gates registration + runtime; per-car toggle writes `enabled` on the schedule row. (A4)
- **Shopify row relabeled** "Autoworld.ro · magazin online"; connector unchanged.
- **Schema change via idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`** in `schema_incremental.py`; never hand-touch prod DB.
- **Ship on `feat/carpark-publishing-panel`** (design doc already committed `4fd10a0ee`), staging-first.
- Frontend `Freshness` enum is the single source of state strings shared by both platforms; extend it rather than duplicating.

## Review Focus

- **Unmapped-required Autovit car in the sweep** → `resync_autovit_vehicle` must return a `skipped: unmapped <dim>` result and `mark_run` records it; the sweep continues to the next car. (Task 7)
- **Edit burst within one cadence window** → `list_due` returns the row only when `next_run_at <= now`; after a push `next_run_at = now + ~1h`, so N edits collapse to ≤1 push/window. (Task 7)
- **Auto-push failure (Autovit reject / rate limit / exception)** → result string carries `error: ...`, `mark_run` persists it, and the badge shows `Eroare`/stays `Necesită actualizare`; never swallowed. (Task 7)
- **Backfill must not flip an explicit Manual car** → backfill upserts only for published vehicles lacking a row OR whose row cadence ≠ `'manual'`. (Task 8)
- **Env kill switch off** → `autosync_enabled()` False ⇒ tick + instant + (new) autovit sweep all no-op even if schedule rows are due. (Task 9)

---

## Task 1: `last_published_at` column + Autovit repo write

**Files:**
- Modify: `jarvis/migrations/domains/schema_incremental.py` (near the `carpark_autovit_listings` block ~2388-2403)
- Modify: `jarvis/carpark/repositories/autovit_listing_repository.py:15` (`_UPDATABLE`)
- Test: `jarvis/tests/carpark/test_autovit_listing_repository.py` (create if absent)

**Interfaces:**
- Produces: `carpark_autovit_listings.last_published_at TIMESTAMP` (nullable); `AutovitListingRepository.upsert(...)` now accepts `last_published_at` as an updatable field.

- [ ] **Step 1** — Add an idempotent migration line after the autovit listings `CREATE TABLE`:
  `cursor.execute("ALTER TABLE carpark_autovit_listings ADD COLUMN IF NOT EXISTS last_published_at TIMESTAMP")`
  (follow the one-liner idiom at `schema_incremental.py:2689`).
- [ ] **Step 2** — Write failing test `test_upsert_persists_last_published_at`: with a mocked cursor, `upsert(1, 2, status='active', last_published_at=NOW)` includes `last_published_at` in the generated column list. (Mirror the no-DB mock style; assert on the SQL/params the repo builds.)
- [ ] **Step 3** — Run it; expect FAIL (`last_published_at` dropped by `_UPDATABLE` filter).
- [ ] **Step 4** — Add `"last_published_at"` to `_UPDATABLE` (`autovit_listing_repository.py:15`). (Note: `last_sync`/`updated_at` still always bump; `last_published_at` only when passed.)
- [ ] **Step 5** — Run test; expect PASS.
- [ ] **Step 6** — Commit: `feat(carpark): add last_published_at to carpark_autovit_listings`.

## Task 2: Autovit freshness classifier

**Files:**
- Create: `jarvis/carpark/connectors/autovit/freshness.py`
- Test: `jarvis/tests/carpark/test_autovit_freshness.py`

**Interfaces:**
- Produces:
  - `compute_autovit_freshness(listing, vehicle_updated_at, now: datetime) -> str` returning one of
    `'not_published' | 'draft' | 'up_to_date' | 'stale' | 'moderation' | 'expired' | 'inactive' | 'error'`.
  - `autovit_sweep_stale(listing, vehicle_updated_at, now: datetime) -> bool` — True iff status in `('active','unpaid')` and (`last_published_at is None` or `vehicle_updated_at > last_published_at`).
- Reuse the `_aware()` datetime coercion pattern from `listing_freshness.py:6-27` (import or duplicate the tiny helper — builder's call; prefer importing `_aware`).

**Mapping (display):** no listing / no `external_advert_id` → `not_published`; `error`→`error`; `removed_by_user`/`removed_by_moderator`/`disabled`/`inactive`→`inactive`; `expired`→`expired`; `moderation`→`moderation`; `unpaid`→`draft`; `active`→ stale if `last_published_at is None` or `updated_at > last_published_at` else `up_to_date`; anything else→`not_published`.

- [ ] **Step 1** — Write failing tests (mirror `test_listing_freshness.py` factory style; module `NOW`, a `L(**kw)` builder defaulting `external_advert_id='x', status='active', last_published_at=NOW-1h`):
  - `test_no_listing_not_published`, `test_unpaid_is_draft`, `test_active_edited_after_publish_is_stale`, `test_active_fresh_is_up_to_date`, `test_moderation`, `test_expired`, `test_removed_is_inactive`, `test_error_wins`, `test_active_never_published_is_stale` (last_published_at None).
  - `test_sweep_stale_true_for_active_edited`, `test_sweep_stale_true_for_unpaid_edited`, `test_sweep_stale_false_when_fresh`, `test_sweep_stale_false_for_inactive`.
- [ ] **Step 2** — Run; expect FAIL (module missing).
- [ ] **Step 3** — Implement `freshness.py` per the mapping + predicate.
- [ ] **Step 4** — Run; expect PASS.
- [ ] **Step 5** — Commit: `feat(carpark): Autovit listing freshness classifier`.

## Task 3: Autovit publish sets `last_published_at`; status routes return `freshness`

**Files:**
- Modify: `jarvis/carpark/connectors/autovit/routes.py` — publish persistence (~898-902), status route (236-255), verify-status route (278-320)
- Test: `jarvis/tests/carpark/test_autovit_routes_freshness.py`

**Interfaces:**
- Consumes: `compute_autovit_freshness` (Task 2), `_vehicle_repo.get_by_id` (`vehicle['updated_at']`).
- Produces: `GET /autovit/api/vehicles/<id>/status` and `POST .../verify-status` each serialized listing gains a `freshness` field; publish writes `last_published_at=now`.

- [ ] **Step 1** — In publish persistence, add `last_published_at=datetime.now(timezone.utc)` to the `_listing_repo.upsert(...)` call (both create + update land here; verify-status must NOT set it).
- [ ] **Step 2** — Write failing test `test_status_route_includes_freshness`: mock `_listing_repo.list_by_vehicle` → one active listing with `last_published_at` in the past and `_vehicle_repo.get_by_id` → `{'updated_at': <newer>}`; assert the JSON `listings[0]['freshness'] == 'stale'`. (Use the app test client + auth-bypass pattern from `test_autovit_routes_auth.py`.)
- [ ] **Step 3** — Run; expect FAIL.
- [ ] **Step 4** — In the status + verify-status routes, load `vehicle = _vehicle_repo.get_by_id(vehicle_id)`, and for each listing set `d['freshness'] = compute_autovit_freshness(d, vehicle.get('updated_at') if vehicle else None, now)` before `_serialize`.
- [ ] **Step 5** — Run; expect PASS.
- [ ] **Step 6** — Commit: `feat(carpark): Autovit status endpoints return freshness + stamp last_published_at`.

## Task 4: Shared Autovit republish service (extract publish core)

**Files:**
- Create: `jarvis/carpark/connectors/autovit/service.py`
- Modify: `jarvis/carpark/connectors/autovit/routes.py` publish() to call the service (DRY)
- Test: `jarvis/tests/carpark/test_autovit_service.py`

**Interfaces:**
- Produces: `republish_vehicle(account, vehicle, photos, taxonomy_map, *, dry_run=False, now) -> dict` returning
  `{'success': bool, 'skipped'?: str, 'status'?: str, 'external_id'?: str, 'external_url'?: str, 'unmapped_required'?: list, 'error'?: str}`.
  It performs: `taxonomy.vehicle_to_advert` → **422-guard** (if `unmapped_required` → return `{'success': False, 'unmapped_required': [...]}` WITHOUT calling Autovit) → (if not dry_run) build client + push + `_verify_advert` → `_listing_repo.upsert(..., last_published_at=now)`.
- Consumes: existing helpers in `routes.py` (`taxonomy.vehicle_to_advert`, `taxonomy_map.REQUIRED_DIMENSIONS`, client build, `_listing_repo`). Move the minimal shared core into `service.py`; the route keeps HTTP concerns (auth, request parsing, response codes) and delegates the push core.

- [ ] **Step 1** — Write failing tests:
  - `test_republish_skips_when_required_unmapped`: taxonomy map missing `fuel_type` → returns `{'success': False, 'unmapped_required': ['fuel_type:Benzina']}`, and the Autovit client is **never** called (assert mock not called).
  - `test_republish_pushes_and_stamps_last_published_at`: all mapped → client push mocked success → `_listing_repo.upsert` called with `last_published_at` set and `status` from result.
- [ ] **Step 2** — Run; expect FAIL (module missing).
- [ ] **Step 3** — Implement `service.py` by extracting the publish core from `routes.py:777-911`; refactor publish() to call `republish_vehicle(...)` and translate its dict → the existing HTTP responses (422 on `unmapped_required`, 502 on exception, success JSON unchanged).
- [ ] **Step 4** — Run new tests + existing `test_autovit_push.py`; expect PASS (no regression in publish behavior).
- [ ] **Step 5** — Commit: `refactor(carpark): extract Autovit republish service shared by route + sweep`.

## Task 5: `resync_autovit_vehicle` + generalize the sweep to both platforms

**Files:**
- Modify: `jarvis/tasks/listing_autosync.py`
- Test: `jarvis/tests/carpark/test_listing_autosync.py` (extend)

**Interfaces:**
- Consumes: `republish_vehicle` (Task 4), `autovit_sweep_stale` (Task 2), `ListingScheduleRepository.list_due`, `AutovitListingRepository`, `AutovitTaxonomyRepository.get_map`, primary account `_repo.get_all_by_type('autovit')[0]`, `VehicleRepository`, `VehiclePhotoRepository`.
- Produces: `resync_autovit_vehicle(account, vehicle, taxonomy_map, now) -> str` (`'pushed' | 'skipped (<freshness>)' | 'skipped: unmapped <dim>' | 'error: ...'`); `listing_autosync_tick` now processes `'autovit'` due rows too.

- [ ] **Step 1** — Write failing tests (mirror `test_listing_autosync.py` monkeypatch style):
  - `test_resync_autovit_skips_when_not_stale` (fresh listing → `skipped`).
  - `test_resync_autovit_skips_unmapped_required` (`republish_vehicle` returns `unmapped_required` → result `skipped: unmapped fuel_type`, no exception).
  - `test_resync_autovit_pushes_when_stale` (stale → `republish_vehicle` called → `pushed`).
  - `test_tick_processes_autovit_due` (`list_due('autovit', now)` returns a row → `resync_autovit_vehicle` invoked, `mark_run` called with `next_run_at ≈ now+cadence`).
  - `test_tick_autovit_no_account_skips` (no autovit connector → due rows marked skipped, no crash).
- [ ] **Step 2** — Run; expect FAIL.
- [ ] **Step 3** — Implement `resync_autovit_vehicle` (load listing via `AutovitListingRepository().get(vehicle['id'], account['id'])`; if `autovit_sweep_stale` → `photos=VehiclePhotoRepository().get_by_vehicle`; `res = republish_vehicle(account, vehicle, photos, taxo_map, now=now)`; map `res` → result string). In `listing_autosync_tick`, after the Shopify loop, add an Autovit loop over `srepo.list_due('autovit', now)` resolving the primary account once and `get_map()` once. Keep `autosync_enabled()` gate at the top (shared).
- [ ] **Step 4** — Run new + existing autosync tests; expect PASS.
- [ ] **Step 5** — Commit: `feat(carpark): auto-resync stale Autovit listings in the sweep`.

## Task 6: `1h` cadence + sweep interval + default-on gates

**Files:**
- Modify: `jarvis/carpark/connectors/cadence.py` (add `'1h': 60`)
- Modify: `jarvis/tasks/cleanup.py:770-777` (`hours=4` → `hours=1`)
- Modify: `jarvis/carpark/connectors/autovit/routes.py` + `shopify/routes.py` — account-level `autosync_enabled` default True for both (confirm `_config_autosync_enabled` default already True; ensure Autovit has an equivalent read or that the sweep's gate uses the Shopify-style default-True). Env `ENABLE_LISTING_AUTOSYNC=true` set in DO (ops step, see §Deploy).
- Test: `jarvis/tests/carpark/test_cadence.py`, `test_carpark_scheduler.py`

**Interfaces:**
- Produces: `cadence_to_minutes('1h') == 60`; sweep interval `hours=1`; `'1h'` is a valid cadence string used as the default for auto rows.

- [ ] **Step 1** — Write failing tests: `test_cadence_1h_is_60`; `test_scheduler_interval_is_1h` (assert the registered job's interval is 1h — mirror the scheduler-registration test at `test_listing_autosync.py:153-170`).
- [ ] **Step 2** — Run; expect FAIL.
- [ ] **Step 3** — Add `'1h': 60` to `cadence.py` `_MIN`; change `cleanup.py` interval to `hours=1` and log text.
- [ ] **Step 4** — Run; expect PASS.
- [ ] **Step 5** — Commit: `feat(carpark): 1h auto-update cadence + hourly sweep interval`.

## Task 7: Create auto schedule rows at publish time (both platforms)

**Files:**
- Modify: `jarvis/carpark/connectors/shopify/routes.py` publish (372-392)
- Modify: `jarvis/carpark/connectors/autovit/routes.py` publish (after successful upsert)
- Test: `jarvis/tests/carpark/test_publishing_schedule_autocreate.py`

**Interfaces:**
- Consumes: `ListingScheduleRepository.get/upsert`.
- Produces: on a **successful** publish, if no schedule row exists for `(vehicle_id, platform_type)`, upsert one with `cadence='1h', enabled=True, next_run_at=now+1h`. If a row exists, leave it untouched (respects a user's explicit Manual/other choice).

- [ ] **Step 1** — Write failing tests: `test_shopify_publish_creates_auto_schedule` (no row → row created `cadence='1h'`); `test_publish_does_not_override_existing_manual` (existing `manual` row → unchanged); `test_autovit_publish_creates_auto_schedule`.
- [ ] **Step 2** — Run; expect FAIL.
- [ ] **Step 3** — Add a small shared helper `ensure_auto_schedule(vehicle_id, platform_type, now)` (place in `jarvis/carpark/connectors/cadence.py` or a `schedule_defaults.py`) that `get`s then `upsert`s only when absent; call it from both publish paths on success.
- [ ] **Step 4** — Run; expect PASS.
- [ ] **Step 5** — Commit: `feat(carpark): default cars to 1h auto-update on publish`.

## Task 8: Backfill existing published cars

**Files:**
- Create: `jarvis/scripts/backfill_listing_schedules.py` (standalone; guard against app-import `init_db` side effects per `reference_database_init_on_import` — do NOT import the Flask app; use the repositories directly with an explicit DB connection)
- Test: `jarvis/tests/carpark/test_backfill_listing_schedules.py`

**Interfaces:**
- Produces: `backfill(now) -> dict` counts. For each published Shopify listing (`carpark_vehicle_listings.status='published'`) and each live Autovit listing (`carpark_autovit_listings.status IN ('active','unpaid')`), ensure a `1h` schedule row **unless** a row already exists with `cadence='manual'` (skip those) — reuse `ensure_auto_schedule`.

- [ ] **Step 1** — Write failing tests: `test_backfill_creates_rows_for_published`; `test_backfill_skips_explicit_manual`; `test_backfill_covers_both_platforms`.
- [ ] **Step 2** — Run; expect FAIL.
- [ ] **Step 3** — Implement the query of published/live listings + loop calling `ensure_auto_schedule`, skipping explicit-manual rows. Make it idempotent + re-runnable.
- [ ] **Step 4** — Run; expect PASS.
- [ ] **Step 5** — Commit: `feat(carpark): backfill 1h auto-update for already-published cars`.

## Task 9: Extend frontend `Freshness` enum (`draft` + `moderation`)

**Files:**
- Modify: `jarvis/frontend/src/pages/CarPark/Detail/ListingFreshness.tsx:3,5-12`
- Test: `jarvis/frontend/src/pages/CarPark/Detail/ListingFreshness.test.tsx` (extend)

**Interfaces:**
- Produces: `Freshness` adds `'draft' | 'moderation'`; `LABELS` adds `draft→{text:'Draft (neplătit)', cls: amber/secondary}`, `moderation→{text:'În moderare', cls: gray}`.

- [ ] **Step 1** — Write failing tests: renders "Draft (neplătit)" for `freshness='draft'`; "În moderare" for `'moderation'`.
- [ ] **Step 2** — Run `npm run test -- ListingFreshness`; expect FAIL.
- [ ] **Step 3** — Extend the type + `LABELS` map.
- [ ] **Step 4** — Run; expect PASS.
- [ ] **Step 5** — Commit: `feat(carpark-ui): draft + moderation freshness states`.

## Task 10: Shared `PlatformPublishRow` component

**Files:**
- Create: `jarvis/frontend/src/pages/CarPark/Detail/PlatformPublishRow.tsx`
- Create: `jarvis/frontend/src/pages/CarPark/Detail/publishState.ts` (pure state→action helper)
- Test: `jarvis/frontend/src/pages/CarPark/Detail/PlatformPublishRow.test.tsx`, `publishState.test.ts`

**Interfaces:**
- Produces:
  - `publishPrimaryAction(state: Freshness): { label: string; variant: 'default'|'secondary'|'ghost'; tone: 'blue'|'amber'|'muted' } | null` — `not_published`→Publică(blue); `stale`→Actualizează acum(amber); `up_to_date`→Actualizează(ghost/muted); `inactive`→Reactivează(blue); `error`→Reîncearcă(amber); `draft`→Actualizează(ghost); `moderation`/`expired`→null (no primary).
  - `PlatformPublishRow(props: PublishRowProps)` where
    ```ts
    type PublishRowProps = {
      logo: React.ReactNode; name: string; subtitle?: string
      freshness: Freshness; lastSync?: string | null; externalUrl?: string | null
      externalLinkLabel: string               // "Vezi anunțul" | "Vezi în magazin"
      autoEnabled: boolean; busy: boolean; canEdit: boolean
      onPrimary: () => void; onVerify: () => void
      onToggleAuto: (on: boolean) => void; onDeactivate: () => void
      onDelete?: () => void                    // present ⇒ shows "Șterge definitiv"
    }
    ```
  - Renders: logo+name+subtitle · `<ListingFreshness>` + "Auto" pill (green when `autoEnabled`, with "se actualizează automat" helper when `freshness==='stale'`) + external link · primary `<Button>` (from `publishPrimaryAction`) · `<DropdownMenu>` ("⋯") containing *Verifică status acum*, a `<Switch>` row *Auto-actualizare*, *Dezactivează anunțul*, and (if `onDelete`) a red *Șterge definitiv* with a confirm.
- Uses: `DropdownMenu*` `@/components/ui/dropdown-menu`, `Switch` `@/components/ui/switch`, `Button`, `ListingFreshness`.

- [ ] **Step 1** — Write failing tests:
  - `publishState.test.ts`: the state→action table above (one assert per state).
  - `PlatformPublishRow.test.tsx`: renders primary "Actualizează acum" for `stale`; shows "Șterge definitiv" only when `onDelete` given; ⋯ menu toggling the Switch calls `onToggleAuto(false)`; hides edit actions when `canEdit=false`.
- [ ] **Step 2** — Run; expect FAIL.
- [ ] **Step 3** — Implement `publishState.ts` then `PlatformPublishRow.tsx`.
- [ ] **Step 4** — Run; expect PASS.
- [ ] **Step 5** — Commit: `feat(carpark-ui): shared state-driven PlatformPublishRow + publishState`.

## Task 11: Platform adapters + swap into the panel

**Files:**
- Create: `jarvis/frontend/src/pages/CarPark/Detail/AutovitPublishRow.tsx` (wraps `AutovitPublishAction`'s data hooks → `PlatformPublishRow`)
- Create: `jarvis/frontend/src/pages/CarPark/Detail/AutoworldPublishRow.tsx` (wraps `ShopifyPublishControl`'s data hooks → `PlatformPublishRow`)
- Modify: `jarvis/frontend/src/pages/CarPark/Detail.tsx` "Publicare directă" card (~3056-3104) to render the two new rows; relabel Shopify→"Autoworld.ro · magazin online"; keep the publish/preview dialogs (reuse from the existing components or lift them).
- Test: `AutovitPublishRow.test.tsx`, `AutoworldPublishRow.test.tsx`

**Interfaces:**
- Consumes: `autovitApi.getVehicleStatus` (→ `listings[0]`, now with `freshness`), `autovitApi.publish/verifyStatus/unpublish/deleteAdvert`; `shopifyApi.vehicleStatus` (`freshness`), `shopifyApi.previewVehicle/publishVehicle/verifyStatus/unpublishVehicle`; `carparkApi.getListingSchedule/setListingSchedule` for the per-car auto toggle (platform `'autovit'` / `'shopify'`).
- Each adapter computes `freshness`, `autoEnabled = schedule?.enabled && schedule?.cadence !== 'manual'`, wires `onToggleAuto(on)` → `setListingSchedule(vid, { platform, cadence: on ? '1h' : 'manual', enabled: on })`, and passes `onDelete` only for Autovit. The Autovit publish flow keeps its 4-step account/preview dialog; `onPrimary` opens it (publish or update).

- [ ] **Step 1** — Write failing tests (mock the api modules per `CarBackgroundSettings.test.tsx`): `AutoworldPublishRow` shows "La zi" when status returns `freshness='up_to_date'` and toggling auto calls `setListingSchedule` with `{platform:'shopify', cadence:'manual', enabled:false}`; `AutovitPublishRow` renders "Draft (neplătit)" for an `unpaid`+`freshness='draft'` listing and shows the ⋯ "Șterge definitiv".
- [ ] **Step 2** — Run; expect FAIL.
- [ ] **Step 3** — Implement adapters; swap them into the card; remove the now-unused `ListingScheduleSelect` dropdown (replaced by the ⋯ toggle) from the card. Relabel the Shopify row header.
- [ ] **Step 4** — Run the two tests + `npm run build`; expect PASS + clean build.
- [ ] **Step 5** — Commit: `feat(carpark-ui): unified publishing panel for Autovit + Autoworld.ro`.

## Task 12: Full verification + deploy

- [ ] **Step 1** — Backend: `cd jarvis && DATABASE_URL=postgresql://localhost/defaultdb python -m pytest tests/carpark -q` (expect green; pre-existing DB-dependent skips OK). Frontend: `cd jarvis/frontend && npm run test && npm run build` (green + clean build).
- [ ] **Step 2** — `/code-review` the branch diff (user rule: review before commit/merge); address findings.
- [ ] **Step 3** — Run the backfill against **staging** first, verify schedule rows; set `ENABLE_LISTING_AUTOSYNC=true` on staging; confirm one sweep tick re-syncs a deliberately-stale car (Autovit + Shopify) and records `last_result`.
- [ ] **Step 4** — Deploy staging-first: check in-flight DO builds → push `feat/carpark-publishing-panel` to `staging` (cherry-pick if diverged) → WAIT ACTIVE + health 200 → ask user for 2 prod confirmations → FF/cherry-pick to `main` → poll ACTIVE + health. Set `ENABLE_LISTING_AUTOSYNC=true` on prod and run the prod backfill (standalone script, no app import).
- [ ] **Step 5** — Update memory + the What's-New if applicable.

---

### Self-review notes
- **Spec coverage:** G1→T9-T11; G2→T2,T3; G3→T5,T6,T7,T8; G4→T10,T11; G5→T4,T5 (reuse). D5→T1,T2; D7→T4,T5; D8→T11; D9→T7,T8; D10→T2,T3,T9. Non-goals respected (legacy generic listings untouched; publish/preview dialogs reused).
- **Review Focus** each pinned: unmapped-required→T5 tests; edit-burst→T7 (next_run_at) + list_due (existing); failure-recorded→T5; backfill-skips-manual→T8; kill-switch→existing `autosync_enabled` gate exercised in T5 `test_tick_*`.
- **Type consistency:** `Freshness` strings shared FE/BE; `compute_autovit_freshness` output ⊆ extended `Freshness` (adds draft, moderation — covered T9). `ensure_auto_schedule` used by T7 + T8. `republish_vehicle` signature used by route (T4) + sweep (T5).
