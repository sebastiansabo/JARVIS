# Autovit Taxonomy Mapping — Design

**Date:** 2026-10-19 · **Status:** awaiting approval · **Branch:** `feat/autovit-taxonomy-mapping`

## Intent & why

Autovit silently **drops** any value JARVIS sends that isn't an exact Autovit code, so ads
publish wrong or incomplete:

- **Equipment (dotări):** JARVIS sends hyphenated abbreviations (`carplay`, `android-auto`,
  `360-camera`, `abs`, `climatronic`). Autovit's codes are underscored full keys
  (`apple_carplay`, `android_auto`, `360_view_camera`, `antilock_brake_system`,
  `air_conditioning_type`). Zero overlap → **every piece of equipment is dropped** (confirmed
  live: vehicle 19 advert 7060927827, `params_dropped: 360-camera, abs, carplay, …` — 30+ items).
- **Model:** naive slugification of "A6 e-tron Sportback" → `a6-e-tron-sportback`, but Autovit's
  real slug is `a6-sportback-e-tron` → **400 `params.model: Valoare incorectă`**, surfaced to the
  user as an opaque **504**.

**Principle (user decision): Autovit is the source of truth — JARVIS must send exactly the
codes/values Autovit uses, for every dimension.** The mechanism already exists for Shopify
(`carpark_shopify_taxonomy_map` + `ShopifyTaxonomy.tsx` in Settings); this project builds the
Autovit equivalent.

## Goals

1. A DB-backed **Autovit taxonomy-mapping layer** mirroring the Shopify one: for each
   **dimension**, map each CarPark `source_value` → the exact **Autovit target code/slug/enum value**.
2. Cover **all dimensions** (user decision): `make`, `model` (make-dependent), `body_type`,
   `fuel_type`, `gearbox`, `transmission` (drive), `color`, the **equipment** codes, and the
   **select-enum** params that need a specific value (e.g. `air_conditioning_type`,
   `alloy_wheels_type`, `pollution_standard`).
3. A **Settings UI** (mirror `ShopifyTaxonomy.tsx`, user decision): pulls Autovit's live taxonomy
   per dimension, lists each CarPark value, **auto-suggests** the best Autovit match, and lets an
   admin confirm / override / clear. Unmapped values are surfaced prominently.
4. A **taxonomy sync**: fetch + cache Autovit's live taxonomy (code + RO label + type
   checkbox/select + value dicts for selects) from the API, refreshable on demand.
5. **Publish uses the map** (`vehicle_to_advert`): resolve every dimension through the map; send
   only Autovit codes; **omit AND report** unmapped values instead of sending raw.
6. **Clear publish errors**: parse Autovit's 400 body (`error.details.params.X`) into an actionable
   Romanian message ("Model «A6 e-tron Sportback» nu e acceptat de Autovit — … "), and surface
   which equipment/dimensions were dropped or unmapped (extends the existing `params_dropped`
   verify path). Replaces the opaque 504/502.

## Non-goals / anti-goals

- **Not** changing how equipment is *stored* on the vehicle (keep `equipment_options TEXT[]` +
  `equipment` JSONB). The map translates at publish time → no data migration, form unchanged.
- **HARD RULE — Shopify mappings stay untouched.** This work is fully isolated: brand-new tables
  (`carpark_autovit_taxonomy_map` / `_cache`), a new repo/service/routes, and a new Settings page.
  The Shopify files (`carpark_shopify_taxonomy_map`/`_value_map`/`_field_map`,
  `shopify/taxonomy*.py`, `ShopifyTaxonomy.tsx`/`ShopifySchema.tsx`) are **read-only references**
  for the pattern — never edited, never reused as shared storage. No migration alters a
  `carpark_shopify_*` table. A test asserts the Shopify taxonomy path is unchanged.
- **Not** touching the publish/auto-update scheduler.
- **Not** fetching Autovit's taxonomy live *during publish* (publish already flirts with the ~60s
  gateway limit) — the taxonomy must be cached in the DB and synced out-of-band.
- **Anti-goal:** silently sending unmapped values (today's bug). Unmapped values must be visible in
  the UI and in the publish result — never raw-sent.

## Constraints

- **Autovit API** (confirmed live, OAuth password-grant per account; taxonomy is account-independent
  so any valid account can sync):
  - `GET /categories/29` → `parameters[]`, each `{code, type: checkbox|select, labels.ro, options}`
    (equipment flags + select enums; 220 params).
  - `GET /categories/29/makes` → `{options: {slug: {ro,en}}}`.
  - `GET /categories/29/models/{make}` → `{options: {slug: {ro,en}}}` (e.g. `a6-sportback-e-tron`).
- Stack: Flask + raw psycopg2 (`%s`), React 19 + Vite + TS + shadcn. Mirror the existing Shopify
  taxonomy repo/service/routes/UI structure.
- DB-safety: the sync job must **not** app-import in a standalone script (`init_db()` runs on
  import — [[reference_database_init_on_import]]); run it inside the app (route/service) or guard.
- Prod promotion: staging → WAIT ACTIVE → main, 2 confirmations for prod (existing workflow).

## Decided (the how)

- **Tables** (mirror `carpark_shopify_taxonomy_map`):
  - `carpark_autovit_taxonomy_map(id, dimension, source_value, target_code, target_label,
    is_active, updated_at, updated_by, UNIQUE(dimension, source_value))` — the mapping.
  - A **taxonomy cache** holding Autovit's synced vocabulary per dimension (code, RO label, type,
    options for selects, and `make` for models) — powers the UI pick-lists and auto-suggest. Exact
    shape left to builder (one row per code, or per-dimension JSON blob).
- **Repo** `AutovitTaxonomyRepository` with `get_map()` → `{dimension: {source_value: {target…}}}`,
  `resolve(dimension, source_value)`, `upsert(...)` — mirrors `shopify/taxonomy_repository.py`.
- **Publish** (`autovit/taxonomy.py::vehicle_to_advert`): replace `_label_to_slug` (make/model),
  `_norm_enum` (fuel/body/gearbox/drive/color) and the raw equipment loop with
  `map.resolve(dimension, value)`; accumulate unmapped values and return them in the publish
  response + `last_error`.
- **Settings**: new `AutovitTaxonomy.tsx` (mirrors `ShopifyTaxonomy.tsx`) with a "Sync taxonomy"
  action, per-dimension tables, auto-suggest + confirm/override; `model` is make-scoped.
- **Error UX**: publish route parses the Autovit error body `details` → friendly RO field messages;
  frontend shows them instead of a generic toast.

## Resolved after builder-check (my calls)

- **Emit semantics per dimension** — a **hardcoded dimension registry** in `autovit/taxonomy.py`
  declares each dimension's emit kind: `param` → `params[<param>] = target_code`
  (make, model, fuel_type, gearbox, transmission, body_type, color, pollution_standard);
  `flag` → `params[<target_code>] = "1"` (equipment); `select` → `params[<param>] = <option>`
  (air_conditioning_type, alloy_wheels_type). The cache table also stores Autovit's `param_type`
  (checkbox/select) for validation/UI, but the registry is the authority for *where* a dimension writes.
- **Model make-dependency** — add a nullable **`make`** column to both the map and the cache;
  `UNIQUE(dimension, source_value, make)` (make NULL for non-model dims); resolver signature becomes
  `resolve(dimension, source_value, make=None)`. The Settings UI scopes the model dimension by make.
  (A deliberate, documented departure from the exact Shopify key — Shopify models aren't make-scoped.)
- **Equipment enumeration** — **one** `equipment` dimension; its CarPark source values are enumerated
  from `UNNEST(equipment_options)` ∪ truthy keys of the `equipment` JSONB (not the scalar-column
  `SELECT DISTINCT` the Shopify helper uses).
- **No regression of curated aliases** — the initial migration **seeds** `carpark_autovit_taxonomy_map`
  from the existing alias tables in `autovit/taxonomy.py` (`_FUEL_SLUGS/_FUEL_ALIASES`, `_GEARBOX*`,
  `_DRIVE*`, `_BODY*`, `_COLOR*` incl. the gray/bej wire quirks, `_EURO*` for pollution_standard) +
  the known equipment codes, so today's working coverage (benzină→petrol, 4x4→…, euro aliases) is
  preserved, with auto-suggest only filling the gaps. `_norm_enum`/`_label_to_slug` are removed from
  the publish path **only after** the seed covers their cases.
- **Taxonomy GET reads the cache**, not Autovit live (deliberate divergence from Shopify's
  per-request `allowed_values` fetch — the caching non-goal wins). A separate **Sync** action
  refreshes the cache; it takes `account_id` like every other autovit route (taxonomy is global, so
  any connected account works).
- **Required vs optional unmapped** — unmapped values are never raw-sent. For **required** dimensions
  (make, model, body_type, fuel_type, color, …) an unmapped value **blocks** the publish pre-flight
  with a clear RO message naming the field+value (no doomed 400 round-trip); for **optional**
  equipment, unmapped slugs are **omitted + reported** in the result.
- **`vehicle_to_advert` stays pure** — the route preloads the map and passes it in
  (`vehicle_to_advert(vehicle, account, taxonomy_map)`), and the function returns `(advert, unmapped)`;
  callers updated. New client methods `get_makes()` / `get_models(make)` sit beside `get_category`.
- **Perms** — `@carpark_required` for GET taxonomy/map; `@admin_required` for save + sync (matches
  existing autovit routes).

## Left to the builder

- **Cache table shape** (default): `carpark_autovit_taxonomy_cache(id, dimension, code, ro_label,
  param_type /*checkbox|select*/, make /*nullable, for models*/, options JSONB /*for selects*/,
  synced_at)`. Map table: `carpark_autovit_taxonomy_map(id, dimension, source_value, make /*nullable*/,
  target_code, target_label, is_active, updated_at, updated_by, UNIQUE(dimension, source_value, make))`.
- **Auto-suggest algorithm** — diacritic-fold + token-set similarity over RO labels **and** code
  tokens; present top-N for confirm. Must beat naive token-overlap (it mismatched *heated*→*ventilated*
  seats, *360°*→*rear* camera, *LED*→*fog* LED in testing).
- **Error-body parsing** — handle `error.details.params.*` generically; capture a couple more real
  rejection shapes during staging to round out the RO messages.
- **Tests**: resolver (mapped / unmapped / make-scoped model), publish integration (required-unmapped
  blocks, optional-unmapped omitted+reported), route auth, DB-free resolver + registry unit tests.

## Rollout

Build on `feat/autovit-taxonomy-mapping`; staging first, validate the Settings UI + a real publish
of vehicle 19 (equipment should now stick), then promote to prod with the standard 2-confirmation
flow. Related: [[project_carpark_shopify_connector]], [[project_carpark_equipment_slug_labels]],
[[project_carpark_reservations_location_seed]].
