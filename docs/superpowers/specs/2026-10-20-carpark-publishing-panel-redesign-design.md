# CarPark Publishing Panel Redesign + Auto-Update for Both Marketplaces

**Date:** 2026-10-20
**Status:** Design — awaiting approval (gate before plan/implementation)
**Area:** CarPark vehicle Detail → "Publicare directă" card (Autovit.ro + Autoworld.ro/Shopify)

---

## 1. Intent & why

The vehicle Detail page's **"Publicare directă"** card lets a user push a car to two
marketplaces: **Autovit.ro** and the **Autoworld.ro** online store (a Shopify
storefront). Today the two rows are visually and behaviourally inconsistent and
cluttered: each exposes a *different* set of 5–6 always-visible buttons in different
positions (Autovit: Publică/Actualizează, Verifică status, mute, delete; Shopify:
Actualizează, Verifică, Retrage, a refresh icon, and an "Actualizare automată" dropdown).
It is hard to tell, at a glance, whether a listing is current.

Two things the user wants:

1. **A cleaner, consistent panel** where the **listing state is the hero** and rare
   actions are tucked away — approved via an interactive mockup (see §9).
2. **Auto-update ON by default for every published car, on BOTH platforms** — the system
   keeps listings in sync so the user rarely touches "Update" by hand. Explicitly
   **NOT instant/on-save**: a periodic sweep (~1 hour) detects a stale listing (car
   edited after its last push) and re-pushes it. A manual "Update now" stays as the only
   immediate-push path.

**Why now:** the user is actively publishing cars (e.g. the Cadillac Lyriq) and the manual,
asymmetric flow is error-prone; Autovit in particular has *no* freshness signal, so a car
edited after publishing silently shows a stale ad with no indication.

## 2. Current implementation (ground truth, with citations)

Two independent stacks, both rendered in the "Publicare directă" card at
`jarvis/frontend/src/pages/CarPark/Detail.tsx:3058-3101`:

- **Autovit** — blueprint `autovit_bp` prefix `/autovit`
  (`jarvis/carpark/connectors/autovit/__init__.py:4`); frontend `autovitApi`
  (`jarvis/frontend/src/api/autovit.ts`). Control: `AutovitPublishAction`
  (`Detail.tsx:2605-2920+`, rendered at `Detail.tsx:3082`).
- **Shopify / Autoworld.ro** — blueprint `shopify_bp` prefix `/shopify`
  (`jarvis/carpark/connectors/shopify/__init__.py:4`); frontend `shopifyApi`
  (`jarvis/frontend/src/api/shopify.ts`). Control: `ShopifyPublishControl`
  (`jarvis/frontend/src/pages/CarPark/Detail/ShopifyPublishControl.tsx`), plus the
  `ListingScheduleSelect` auto dropdown (`Detail/ListingScheduleSelect.tsx`, rendered at
  `Detail.tsx:3100`).

### Backend routes
- **Autovit** (`jarvis/carpark/connectors/autovit/routes.py`): publish/update
  `POST /autovit/api/accounts/<acct>/publish` (`:751-924`); unpublish→`status='inactive'`
  (`:997-1014`); delete-advert→`status='removed_by_user'` (`:1018-1038`); verify-status
  `POST /autovit/api/vehicles/<id>/verify-status` (`:278-320`, bumps `last_sync`); status
  read `:236-255`. Status is free-text (`draft/unpaid/active/inactive/removed_by_user`
  + remote-reported `moderation/expired/disabled/removed_by_moderator/error`).
- **Shopify** (`jarvis/carpark/connectors/shopify/routes.py`): publish/update `:372-392`
  (writes `status='published'`, `last_sync=now`, `published_at=now` —
  `shopify/connector.py:178-185`); preview `:395-427`; unpublish→`archived` `:430-448`;
  verify-status `:451-490`; status read `:493-511`.

### Freshness (Shopify only)
`compute_listing_freshness(listing, vehicle_updated_at, now)`
(`jarvis/carpark/connectors/listing_freshness.py:30-48`) → one of
`not_published / error / inactive / expired / stale / up_to_date`. Rule: status must be
`published`; then `last_sync is None` OR `vehicle_updated_at > last_sync` ⇒ **stale**, else
**up_to_date**. UI maps `up_to_date`→green "La zi", `stale`→amber "Necesită actualizare"
(`ListingFreshness.tsx:5-12`). Returned by the Shopify status + verify endpoints.
**Autovit has NO staleness comparison** — it only shows the stored advert status + a literal
"verificat <last_sync>" (`Detail.tsx:2796`), and its `last_sync` is overloaded (bumped by
BOTH publish and verify-status), so it is not a reliable "last pushed" marker.

### Auto-push today (Shopify only, dormant)
- Job `jarvis/tasks/listing_autosync.py`, `listing_autosync_tick()` (`:112-138`), hard-coded
  `PLATFORM_TYPE='shopify'` (`:31`). Registered as an **interval job every 4h**
  (`jarvis/tasks/cleanup.py:770-777`).
- Pulls due rows via `ListingScheduleRepository.list_due('shopify', now)`
  (`listing_schedule_repository.py:24-30`: `enabled AND cadence NOT IN ('manual','instant')
  AND next_run_at <= now`), re-pushes each **stale** vehicle (`resync_shopify_vehicle`,
  `:78-86`, gated on `compute_listing_freshness == 'stale'`), reschedules `next_run_at`.
- `maybe_instant_resync(vehicle_id)` (`:103-109`) fires on every vehicle save
  (`jarvis/carpark/routes/vehicles.py:476-477`) but only when cadence == `'instant'`.
- **Two gates, fail-closed** (`autosync_enabled()`, `:38-59`): env
  `ENABLE_LISTING_AUTOSYNC=true` (off by default) AND account-level `config.autosync_enabled`
  in the Shopify connector row (set via `POST /shopify/api/autosync`, `shopify/routes.py:204`).

### Data model
| Platform | Table | Key columns | DDL |
|---|---|---|---|
| Shopify | `carpark_vehicle_listings` | `external_listing_id, status(draft), published_at, expires_at, external_url, last_sync, error_message` | `schema_carpark.py:629-645` |
| Autovit | `carpark_autovit_listings` | `external_advert_id, external_url, status(TEXT,draft), last_sync, last_error`; UNIQUE(vehicle_id, account_id) | `schema_incremental.py:2388-2403` |
| Auto schedule | `carpark_listing_schedules` | `platform_type, cadence(manual), enabled, next_run_at, last_run_at, last_result`; UNIQUE(vehicle_id, platform_type) | `schema_carpark.py:652-666` |

`carpark_listing_schedules` is keyed by `(vehicle_id, platform_type)` and is therefore
**already able to hold `platform_type='autovit'` rows** — no schema change needed to extend
the cadence/schedule mechanism to Autovit. Autovit account-level autosync flag does not exist
yet.

## 3. Goals

- **G1 — Unified, state-driven panel.** Both platform rows share one layout: platform
  identity, a single prominent **state badge**, a sync line, an **auto** indicator, one
  **primary action** (state-dependent), and a **"⋯" overflow menu** for everything rare.
- **G2 — Honest freshness for BOTH platforms.** Autovit gets a real
  stale/up-to-date/inactive/error/not-published signal computed the same way Shopify's is
  (car `updated_at` vs last *push*), surfaced in its status endpoints.
- **G3 — Auto-update ON by default for every published car, both platforms**, via a
  **periodic ~1h sweep** (not instant). Stale published listings are re-pushed automatically;
  a per-car toggle (in the ⋯ menu) can turn it off.
- **G4 — Manual "Update now"** remains on every row as the immediate-push escape hatch, and
  "Verifică status", "Dezactivează", and (Autovit-only) "Șterge definitiv" move into the ⋯
  menu.
- **G5 — Reuse, don't rebuild.** Extend the existing Shopify freshness + schedule + sweep
  machinery to Autovit rather than inventing a parallel system.

## 4. Non-goals

- Not touching the **legacy generic** platforms/listings system (`carpark_bp`
  `/api/carpark` publishing routes and the generic listing cards at `Detail.tsx:3058+`
  lower on the page) beyond what the schedule endpoints already provide.
- Not changing the **publish eligibility / dry-run preview** flows (Autovit publish dialog,
  Shopify preview modal) — only how they're surfaced/triggered.
- Not building instant/on-save push (explicitly dropped by the user). The existing
  `maybe_instant_resync` 'instant' cadence path may remain in code but is **not** the default
  and not surfaced in the new UI.
- Not changing the Autovit↔JARVIS **taxonomy mapping** behaviour
  (`project_carpark_autovit_taxonomy_mapping`) — but auto-push must respect it (§6).

## 5. Anti-goals (what makes this a failure even if it "works")

- **A1 — Hammering Autovit.** Auto-republishing must not blow past Autovit rate limits or
  incur runaway cost. A burst of edits to one car must collapse into at most one push per
  sweep, and the sweep must be bounded.
- **A2 — Silent failure.** An auto-push that fails (rate limit, Autovit rejection, unmapped
  required taxonomy) must be recorded (`last_result`/`last_error`) and reflected in the badge
  (→ "Eroare" / stays "Necesită actualizare"), never swallowed.
- **A3 — Clobbering taxonomy or publishing an invalid ad.** Auto-push must use the same
  422-guard as manual publish (block on unmapped REQUIRED dims) — it must **skip and log**,
  not strip data or spam retries.
- **A4 — Turning auto-update on globally without a kill switch.** Must stay gateable
  (env + account flag) and per-car disable-able.

## 6. Decisions already made (the "how", as decided)

These are settled; a builder should treat them as fixed.

- **D1 Layout.** One shared row component for both platforms (approved mockup §9):
  `logo + name` · `state badge + sync line + Auto pill + external link` · `primary CTA + ⋯`.
- **D2 State → primary action map** (identical for both platforms):
  | State | Badge | Primary action |
  |---|---|---|
  | Nepublicat | gray "Nepublicat" | **Publică** (opens existing preview/dry-run) |
  | Publicat · La zi | green "La zi" | ghost **Actualizează** (de-emphasised) |
  | Publicat · Necesită actualizare | amber "Necesită actualizare" + "se actualizează automat" | **Actualizează acum** |
  | Inactiv | gray "Inactiv" | **Reactivează** |
  | Eroare | red "Eroare" (+ details link) | **Reîncearcă** |
- **D3 ⋯ menu** holds: *Verifică status acum*, *Auto-actualizare* (per-car on/off toggle,
  default ON), *Dezactivează anunțul*, and **Autovit-only** *Șterge definitiv* (red, keeps the
  existing `confirm()` + delete-advert route). Shopify/Autoworld.ro has **no hard-delete**
  (unchanged from today).
- **D4 Auto-update model.** Default ON for every published car on both platforms; a
  **periodic sweep** re-pushes stale listings. **Default cadence ≈ 1 hour for BOTH** platforms
  (Autovit updates are free — §8 Q-cost). Not instant.
- **D5 Autovit freshness.** Add a dedicated **`last_published_at`** timestamp to
  `carpark_autovit_listings`, set on publish/update only (NOT on verify-status), and compute
  Autovit freshness with the same `compute_listing_freshness` shape
  (`updated_at > last_published_at` ⇒ stale) so badge + sweep share one definition. (Reusing
  the overloaded `last_sync` would make verify-status falsely mark ads fresh — hence a new
  column.)
- **D6 Extend, don't fork.** Reuse `carpark_listing_schedules` for
  `platform_type='autovit'`; generalise `listing_autosync.py` to loop BOTH platforms
  (`resync_autovit_vehicle` alongside `resync_shopify_vehicle`); add an Autovit
  account-level autosync flag mirroring Shopify's `config.autosync_enabled`.
- **D7 Auto-push safety for Autovit.** `resync_autovit_vehicle` must run the **same required-
  dimension 422 guard** as manual publish; if a car would 422 (unmapped required taxonomy),
  **skip + record `last_result='skipped: unmapped <dim>'`**, do not retry-spam, and leave the
  badge "Necesită actualizare" (optionally surface a one-line reason). Respect Autovit rate
  limits (bounded batch per sweep).
- **D8 Relabel.** The Shopify row is labelled **"Autoworld.ro · magazin online"** (the
  customer-facing store name; the connector stays Shopify). **Settled (builder's call).**
- **D9 Default-on MECHANISM (revised after builder-check).** `carpark_listing_schedules` rows
  exist today only when a user explicitly picks a cadence; the publish paths create none and
  `list_due` returns only existing non-manual rows — so "default the PUT cadence" alone is a
  **no-op**. Real mechanism (builder's call): **(a)** upsert an auto-cadence schedule row at
  **publish time** in BOTH publish paths (`shopify/routes.py` publish, `autovit/routes.py`
  publish); **(b)** a one-time **backfill** of auto rows for **all** currently-published cars on both
  platforms, **skipping cars with an explicit `'manual'` row** (§8 Q-backfill); **(c)** the
  per-car Auto toggle (D3) writes `enabled`/`cadence` on that
  same row (off ⇒ `enabled=false`). Plus flip the gates: `ENABLE_LISTING_AUTOSYNC=true`
  (staging→prod) and account `autosync_enabled` ON for both connectors.
- **D10 Autovit status → state model (revised after builder-check).** Autovit statuses don't
  include `published`; a JARVIS-created ad lands in **`unpaid`** (a draft until paid), and
  there are `moderation`/`expired` states today. The approved 5 badges are **extended for the
  Autovit row** with: **"Draft (neplătit)"** (unpaid), **"În moderare"** (moderation),
  **"Expirat"** (expired). Mapping: `active`→La zi/Necesită actualizare, `inactive`/
  `removed_by_user`→Inactiv, `error`→Eroare, `unpaid`→Draft, `moderation`→În moderare,
  `expired`→Expirat, none→Nepublicat. The **sweep targets `active` AND `unpaid` (draft)** ads
  (§8 Q-draft: yes); it skips `inactive/moderation/expired/error`. (Autoworld.ro keeps the
  original 5.) **Settled.**

## 7. Constraints

- **Isolation / public repo:** no secrets in code; this is the public JARVIS repo.
- **Deploy discipline:** staging-first → wait DO ACTIVE → prod after 2 confirmations; check
  in-flight DO builds first; staging/main diverged (cherry-pick vs FF as appropriate). DB
  schema change (D5) ships via the normal `schema_*.py` init path (idempotent `ADD COLUMN IF
  NOT EXISTS`); **never** touch prod DB by hand for the migration.
- **Autovit taxonomy precondition:** imported cars whose equipment/models aren't mapped still
  report-unmapped; auto-push must not fight this (D7, A3).
- **Tests:** DB-gated tests require explicit `DATABASE_URL` (`reference_database_init_on_import`,
  conftest). Follow TDD; add freshness + sweep tests for Autovit mirroring the Shopify ones.

## 8. User decisions — RESOLVED (2026-10-20)

The single builder-check round, answered by the user:

- **Q-multiaccount → ONE account.** Scope auto-update + the single state badge to the
  **primary Autovit account** (today's effective behaviour). **No schema change** to
  `carpark_listing_schedules`; `resync_autovit_vehicle` targets the single account like the
  Shopify sweep's `_get_single_account()`. Multi-account aggregation is explicitly out of scope.
- **Q-cost → FREE.** Autovit updates are free, so **Autovit auto-refreshes on the same ~1h
  sweep** as Autoworld.ro (no separate slower cadence).
- **Q-draft → keep drafts in sync.** The sweep re-pushes **`unpaid` (draft)** ads too, not
  just `active`, so the draft stays current until paid. (`resync_autovit_vehicle` treats both
  `active` and `unpaid` as sweepable-live; still skips `inactive/moderation/expired/error`.)
- **Q-backfill → on for all, respect Manual.** Backfill an auto-cadence schedule row for
  **every currently-published car** on both platforms, **except** cars with an explicit
  `'manual'` schedule row today (those stay Manual). Q-label settled earlier (D8).

## 9. The approved mockup

Interactive before/after mockup shown and approved ("perfect"). Key approved elements: state
badge as the hero; one state-dependent primary action; ⋯ menu for Verifică status / Auto toggle
/ Dezactivează / Șterge definitiv (Autovit only); Auto pill (green when on); stale rows show
"se actualizează automat în ~1h" so they don't nag. (Source HTML preserved in the session
scratchpad brainstorm dir.)

## 10. What's left to the builder

- Exact component factoring (a shared `PlatformPublishRow` consumed by both, vs. a config-driven
  `PublishPanel`) — builder's call, as long as both rows are truly identical in layout.
- Precise sweep cadence reconciliation (keep the 4h APScheduler interval and let per-vehicle
  cadence gate to ~1h, vs. lower the interval) — builder's call within D4's "~1h default".
- Error-copy wording and the stale "se actualizează automat" microcopy.
- Test structure, naming, and which existing fixtures to reuse.
- Whether to add a small `last_published_at` backfill for existing Autovit listings or let it
  populate on next push.

---

### Implementation note (post-approval)
After approval, the next step is the plan (superpowers:writing-plans), then subagent/TDD
implementation on a fresh `feat/carpark-publishing-panel` branch off current prod `main`,
shipped staging-first. Related memory: `project_carpark_autovit_taxonomy_mapping`,
`project_carpark_listing_freshness_scheduler`, `project_carpark_all_companies_tenant`.
