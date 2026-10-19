# Autovit Taxonomy Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Map every CarPark vehicle field to the exact Autovit code (source of truth) via a DB-backed, Settings-managed taxonomy, so Autovit publishes stop silently dropping equipment and rejecting models.

**Architecture:** A new, isolated Autovit taxonomy layer mirroring the Shopify one: a synced cache of Autovit's live vocabulary + an editable CarPark→Autovit map. A hardcoded dimension registry says how each dimension is emitted (top-level param / boolean flag / select value). `vehicle_to_advert` resolves through the map (pure, map passed in) and returns `(advert, unmapped)`; the publish route blocks required-unmapped and reports optional-unmapped. Shopify code is reference-only.

**Tech Stack:** Flask, psycopg2 raw SQL, React 19 + Vite + TS + shadcn, requests (Autovit OAuth password-grant).

**Spec:** `docs/superpowers/specs/2026-10-19-autovit-taxonomy-mapping-design.md`

## Global Constraints

- **Shopify untouched (HARD):** never edit `carpark_shopify_*` tables or `shopify/taxonomy*.py` or `ShopifyTaxonomy.tsx`/`ShopifySchema.tsx`; no migration alters a `carpark_shopify_*` table. Mirror by copying the pattern into new `carpark_autovit_*` files only.
- **No live taxonomy fetch during publish** — publish reads only the DB map/cache.
- **Parameterise all SQL** (`%s`); DDL idempotent (`CREATE TABLE IF NOT EXISTS`, guarded `ALTER`).
- **No app-import in standalone scripts** (`init_db()` runs on import) — sync runs inside the app.
- **Autovit cars category id = 29.** Endpoints: `GET /categories/29` (params: `{code,type,labels.ro,options}`), `GET /categories/29/makes`, `GET /categories/29/models/{make}` (all `{options:{slug:{ro,en}}}`).
- **No vehicle data migration / form change** — translate at publish; seed the map from existing alias tables.
- Prod promotion: staging → WAIT ACTIVE → main, 2 confirmations.

## Review Focus

- **Unmapped required field (e.g. a new body_type)** → publish must block pre-flight with a clear RO message naming field+value, not a 400/504. (Task 6)
- **Unmapped equipment slug** → omitted from the advert and listed in the result's `unmapped`, never raw-sent. (Task 3)
- **Make-scoped model collision** (same model label under two makes, or make absent) → resolver keys on `(dimension, source_value, make)`; model with no make resolves to unmapped, not a wrong slug. (Task 2)
- **Seed must not regress curated aliases** (`benzină→petrol`, `4x4→all-wheel-permanent`, color `gray/bej`, euro `pollution_standard`) → seeded rows reproduce today's `_norm_enum` output for every alias. (Task 4)
- **Sync with a disconnected/one account** → sync picks a valid connected account (or 400s clearly), and re-sync is idempotent (upsert, no dup cache rows). (Task 5)

---

### Task 1: Schema — Autovit taxonomy cache + map tables

**Files:**
- Modify: `jarvis/migrations/domains/schema_carpark.py` (add two tables beside `carpark_shopify_taxonomy_map`, ~line 714)
- Test: `jarvis/tests/carpark/test_autovit_taxonomy_schema.py`

**Interfaces:**
- Produces tables:
  - `carpark_autovit_taxonomy_cache(id, dimension VARCHAR(40), code TEXT, ro_label TEXT, param_type VARCHAR(20), make VARCHAR(60) NULL, options JSONB NULL, synced_at TIMESTAMP, UNIQUE(dimension, code, make))`
  - `carpark_autovit_taxonomy_map(id, dimension VARCHAR(40), source_value TEXT, make VARCHAR(60) NULL, target_code TEXT, target_label TEXT, is_active BOOLEAN DEFAULT TRUE, updated_at TIMESTAMP, updated_by INTEGER, UNIQUE(dimension, source_value, make))`
  - indexes on `(dimension)` for both.

- [ ] **Step 1: Write the failing test** — `test_autovit_taxonomy_tables_exist` (gated on `REAL_DB_AVAILABLE`, mirror `test_carpark_schema_widths.py`): run the carpark schema init, then assert both tables and their UNIQUE constraints exist via `information_schema`.
- [ ] **Step 2: Run it** — `DATABASE_URL=… venv/bin/python -m pytest jarvis/tests/carpark/test_autovit_taxonomy_schema.py -v` → FAIL (tables missing).
- [ ] **Step 3: Add the two `CREATE TABLE IF NOT EXISTS` blocks + `CREATE INDEX IF NOT EXISTS`** in `schema_carpark.py`, copying the style of the adjacent `carpark_shopify_taxonomy_map` block. Do not touch any shopify block.
- [ ] **Step 4: Run it** → PASS.
- [ ] **Step 5: Commit** — `feat(carpark): autovit taxonomy cache + map tables`.

---

### Task 2: Dimension registry + resolver

**Files:**
- Create: `jarvis/carpark/connectors/autovit/taxonomy_map.py`
- Test: `jarvis/tests/carpark/test_autovit_taxonomy_map.py`

**Interfaces:**
- Produces:
  - `DIMENSIONS: dict[str, Emit]` where `Emit` is one of `('param', <autovit_param_name>)`, `('flag', None)`, `('select', <autovit_param_name>)`. Keys: `make→('param','make')`, `model→('param','model')`, `fuel_type→('param','fuel_type')`, `gearbox→('param','gearbox')`, `drive→('param','transmission')`, `body_type→('param','body_type')`, `color→('param','color')`, `pollution_standard→('param','pollution_standard')`, `air_conditioning_type→('select','air_conditioning_type')`, `alloy_wheels_type→('select','alloy_wheels_type')`, `equipment→('flag',None)`.
  - `REQUIRED_DIMENSIONS: set[str]` = `{make, model, body_type, fuel_type, color}` (unmapped → block).
  - `resolve(mapping: dict, dimension: str, source_value, make=None) -> Optional[dict]` — `mapping` is the `{dimension:{(source_value,make):{target_code,target_label}}}` shape from the repo; returns the target dict or None.
  - `emit(params: dict, dimension: str, target_code: str) -> None` — writes `target_code` into `params` per `DIMENSIONS[dimension]` (top-level param / `params[code]='1'` / select value).

- [ ] **Step 1: Write the failing tests** (DB-free): `test_resolve_hit`, `test_resolve_miss_returns_none`, `test_resolve_model_is_make_scoped` (same source_value, different make → different target; make=None → None), `test_emit_param` (`emit(p,'fuel_type','petrol')` → `p['fuel_type']=='petrol'`), `test_emit_flag` (`emit(p,'equipment','apple_carplay')` → `p['apple_carplay']=='1'`), `test_emit_select` (`emit(p,'air_conditioning_type','automatic')` → `p['air_conditioning_type']=='automatic'`).
- [ ] **Step 2: Run** — `venv/bin/python -m pytest jarvis/tests/carpark/test_autovit_taxonomy_map.py -v` → FAIL (module missing).
- [ ] **Step 3: Implement** `DIMENSIONS`, `REQUIRED_DIMENSIONS`, `resolve(...)`, `emit(...)` in `taxonomy_map.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat(carpark): autovit dimension registry + resolver`.

---

### Task 3: Repository + `vehicle_to_advert` rewrite

**Files:**
- Create: `jarvis/carpark/connectors/autovit/taxonomy_repository.py`
- Modify: `jarvis/carpark/connectors/autovit/taxonomy.py` (`vehicle_to_advert`; keep `_norm_enum`/`_label_to_slug` for Task 4 seeding, remove their use from the publish path)
- Test: `jarvis/tests/carpark/test_autovit_vehicle_to_advert.py`

**Interfaces:**
- Consumes: `taxonomy_map.resolve/emit/DIMENSIONS/REQUIRED_DIMENSIONS` (Task 2).
- Produces:
  - `AutovitTaxonomyRepository` with `get_map() -> dict` (`{dimension:{(source_value, make):{target_code,target_label}}}`), `resolve(dimension, source_value, make=None)`, `upsert(dimension, source_value, make, target_code, target_label, updated_by)`, `get_cache(dimension=None)`, `replace_cache(rows)`.
  - `vehicle_to_advert(vehicle: dict, account: dict, taxonomy_map: dict) -> tuple[dict, list[str]]` — returns `(advert, unmapped)` where `unmapped` is `["dimension:source_value", …]`. Equipment source values come from `UNNEST(equipment_options)` ∪ truthy `equipment` JSONB keys.

- [ ] **Step 1: Write the failing tests** (DB-free; pass a literal `taxonomy_map`): `test_v2a_maps_model_make_scoped` (A6 e-tron Sportback + make audi → `params['model']=='a6-sportback-e-tron'`), `test_v2a_equipment_flags` (equipment_options `['carplay']` mapped → `params['apple_carplay']=='1'`), `test_v2a_unmapped_equipment_reported_not_sent` (unknown slug → not in params, present in `unmapped`), `test_v2a_unmapped_required_in_list` (unmapped body_type appears in `unmapped`), `test_v2a_select_dimension` (ac type mapped → `params['air_conditioning_type']==<value>`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the repo (mirror `shopify/taxonomy_repository.py` shape) and rewrite `vehicle_to_advert` to resolve every dimension via the passed map + `emit`, collect `unmapped`, drop the `_norm_enum`/`_label_to_slug` calls and the raw equipment loop. Keep `_CORE_PARAMS` and the non-dimension fields (vin, year, mileage, price, booleans, `is_imported_car`) unchanged.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat(carpark): resolve autovit advert via taxonomy map`.

---

### Task 4: Seed the map from existing curated aliases

**Files:**
- Create: `jarvis/carpark/connectors/autovit/taxonomy_seed.py`
- Modify: `jarvis/migrations/domains/schema_carpark.py` (call the seed after the table DDL, guarded "only if map empty")
- Test: `jarvis/tests/carpark/test_autovit_taxonomy_seed.py`

**Interfaces:**
- Consumes: the alias tables still in `taxonomy.py` (`_FUEL_SLUGS/_FUEL_ALIASES`, `_GEARBOX*`, `_DRIVE*`, `_BODY*`, `_COLOR*`, `_EURO*`) and `_REVERSE`.
- Produces: `build_seed_rows() -> list[dict]` → map rows `{dimension, source_value, make, target_code, target_label}` reproducing today's `_norm_enum` output for every alias key (drive→`transmission` param, color via `_REVERSE['color']`). `seed_map(cursor)` inserts them `ON CONFLICT (dimension, source_value, make) DO NOTHING`.

- [ ] **Step 1: Write the failing tests** (DB-free over `build_seed_rows()`): `test_seed_fuel_benzina_to_petrol`, `test_seed_gearbox_automata_to_automatic`, `test_seed_drive_4x4` (dimension `drive`, target == `_norm_enum('4x4',_DRIVE_SLUGS,_DRIVE_ALIASES)`), `test_seed_color_reverse_quirk` (grey→gray / beige→bej), `test_seed_covers_every_alias_key` (every alias key in each table yields a row whose target == the old `_norm_enum` result).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `build_seed_rows()`/`seed_map()`; wire `seed_map` into schema init behind a `SELECT 1 FROM carpark_autovit_taxonomy_map LIMIT 1` empty-check.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat(carpark): seed autovit map from curated aliases (no regression)`.

---

### Task 5: Autovit client methods + taxonomy sync + auto-suggest

**Files:**
- Modify: `jarvis/carpark/connectors/autovit/client.py` (add `get_makes()`, `get_models(make)` beside `get_category`)
- Create: `jarvis/carpark/connectors/autovit/taxonomy_sync.py`
- Test: `jarvis/tests/carpark/test_autovit_taxonomy_sync.py`

**Interfaces:**
- Consumes: `AutovitClient.get_category(29)`, `get_makes()`, `get_models(make)`; `AutovitTaxonomyRepository.replace_cache` (Task 3).
- Produces:
  - `client.get_makes() -> dict` (`{slug: {ro,en}}`), `client.get_models(make: str) -> dict`.
  - `taxonomy_sync.pull_taxonomy(client) -> list[dict]` → cache rows (equipment+selects from `/categories/29` params: `code`, `labels.ro`, `type`→param_type, `options` for selects; models from `get_models` per make, `make` set).
  - `taxonomy_sync.suggest(cache_rows, dimension, source_value, make=None) -> list[tuple[code,label,score]]` — diacritic-fold + token-set similarity over ro_label AND code tokens, top-N.

- [ ] **Step 1: Write the failing tests**: client methods with `responses`/mocked `requests` (`test_get_models_audi` asserts path `/categories/29/models/audi` + parsed slugs); `test_suggest_beats_token_overlap` — `suggest(..., 'equipment', 'scaune incalzite fata')` ranks a *heated* code above *ventilated*; `test_suggest_360_not_rear` — 360 camera ranks `360_view_camera` above `rear_view_camera`; `test_pull_taxonomy_shapes_rows` (param_type checkbox vs select, model rows carry make).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** client methods + `pull_taxonomy` + `suggest`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat(carpark): autovit taxonomy sync + auto-suggest`.

---

### Task 6: Routes — taxonomy GET/sync/upsert + publish wiring + error messages

**Files:**
- Modify: `jarvis/carpark/connectors/autovit/routes.py`
- Test: `jarvis/tests/carpark/test_autovit_taxonomy_routes.py` (mirror `test_autovit_routes_auth.py` login/monkeypatch pattern)

**Interfaces:**
- Consumes: repo (Task 3), `taxonomy_sync` (Task 5), `taxonomy_map.REQUIRED_DIMENSIONS` (Task 2), `vehicle_to_advert` (Task 3).
- Produces routes:
  - `GET /api/autovit/taxonomy` (`@carpark_required`) → `{cache, map, dimensions}`.
  - `POST /api/autovit/taxonomy/sync` (`@admin_required`, body `{account_id}`) → pulls + `replace_cache`, returns counts.
  - `PUT /api/autovit/taxonomy/map` (`@admin_required`, body `{dimension, source_value, make, target_code, target_label}`) → `upsert`.
  - publish `publish()` change: preload `repo.get_map()`, call `vehicle_to_advert(vehicle, account, tmap)`; if any `unmapped` dimension ∈ `REQUIRED_DIMENSIONS` → **return 422** `{error, unmapped_required}` with RO text (no Autovit call); else proceed and include `unmapped` (optional) in the response + `last_error`.
  - `_autovit_error_message(body: str) -> str` — parse `error.details.params.*` → `"Autovit: câmp «<param>» invalid (<value>). …"`; used in the `except` at `routes.py:685`.

- [ ] **Step 1: Write the failing tests**: `test_taxonomy_get_requires_carpark`, `test_sync_requires_admin`, `test_map_upsert_requires_admin` (403 paths); `test_publish_blocks_unmapped_required_422` (monkeypatch `get_map` to leave model unmapped → 422, Autovit client never called); `test_publish_reports_unmapped_equipment` (optional unmapped in response, publish proceeds); `test_error_message_parses_params_model` (`_autovit_error_message('{"error":{"details":{"params.model":"Valoare incorecta"}}}')` contains `model`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the three routes + publish wiring + `_autovit_error_message`; reuse the existing `category-taxonomy` GET (`routes.py:253`) and `_verify_advert` (`:731`).
- [ ] **Step 4: Run** → PASS; also run the existing `test_autovit_routes_auth.py` to confirm no publish regression.
- [ ] **Step 5: Commit** — `feat(carpark): autovit taxonomy routes + publish uses map + clear errors`.

---

### Task 7: Settings UI — AutovitTaxonomy page

**Files:**
- Create: `jarvis/frontend/src/pages/Settings/AutovitTaxonomy.tsx`
- Modify: `jarvis/frontend/src/api/autovit.ts` (add `getTaxonomy`, `syncTaxonomy`, `saveTaxonomyMap`), `jarvis/frontend/src/pages/Settings/index.tsx` (add the tab/route, mirroring where `ShopifyTaxonomy` is mounted — do not alter the Shopify entry)
- Test: `jarvis/frontend/src/pages/Settings/AutovitTaxonomy.test.tsx`

**Interfaces:**
- Consumes: `GET/POST/PUT /api/autovit/taxonomy*` (Task 6).
- Produces: a per-dimension table (model grouped by make) listing each CarPark `source_value`, its current `target_code` (or "Nemapat"), an auto-suggest dropdown (top-N from the cache) with confirm/override/clear, and a "Sincronizează taxonomia" button (account picker). Unmapped rows highlighted.

- [ ] **Step 1: Write the failing test** (vitest + RTL): `renders dimensions and flags unmapped` — mock the API, assert an unmapped value shows "Nemapat" and selecting a suggestion calls `saveTaxonomyMap` with the chosen `target_code`.
- [ ] **Step 2: Run** — `cd jarvis/frontend && npx vitest run src/pages/Settings/AutovitTaxonomy.test.tsx` → FAIL.
- [ ] **Step 3: Implement** the API methods + page + tab. Use shadcn Table/Select like `ShopifyTaxonomy.tsx` (copy pattern, new file).
- [ ] **Step 4: Run** the vitest → PASS; `npm run build` → 0 TS errors.
- [ ] **Step 5: Commit** — `feat(carpark): Autovit taxonomy Settings page`.

---

### Task 8: Shopify-untouched guard + end-to-end verification

**Files:**
- Test: `jarvis/tests/carpark/test_shopify_taxonomy_unchanged.py`

- [ ] **Step 1: Write the test** `test_no_autovit_migration_touches_shopify_tables` — read `schema_carpark.py` source and assert no statement under the autovit-taxonomy additions references a `carpark_shopify_` table; and `test_shopify_taxonomy_repo_import_unchanged` — importing `shopify/taxonomy_repository.py` still exposes `get_map/resolve/upsert` (sanity that nothing was edited).
- [ ] **Step 2: Run** → PASS (guard).
- [ ] **Step 3: Full verification** — `venv/bin/python -m pytest jarvis/tests/carpark/ -q` (new green, no new failures vs the 3 known pre-existing DB fails), `cd jarvis/frontend && npm run build`, `npx vitest run src/pages/Settings/ src/pages/CarPark/`.
- [ ] **Step 4: Verify on staging** — sync taxonomy, confirm the A6 e-tron Sportback (vehicle 19) maps model→`a6-sportback-e-tron` + equipment codes, re-publish, confirm Autovit keeps the dotări (verify `params_dropped` is empty).
- [ ] **Step 5: Commit** — `test(carpark): assert shopify taxonomy untouched`.

---

## Self-Review

- **Spec coverage:** tables (T1), registry/resolver (T2), repo + publish rewrite (T3), seed/no-regression (T4), client+sync+suggest (T5), routes+errors (T6), Settings UI (T7), Shopify-isolation + E2E (T8). All spec sections covered.
- **Review Focus:** each of the 5 lines is pinned — required-unmapped→422 (T6), optional-unmapped omitted+reported (T3), make-scoped model (T2), seed-no-regress (T4), sync account/idempotent (T5).
- **Type consistency:** `resolve(mapping, dimension, source_value, make=None)` and the map shape `{dimension:{(source_value,make):{target_code,target_label}}}` are used identically in T2/T3/T6; `vehicle_to_advert(...)->(advert, unmapped)` consistent T3/T6.
- **Proportion:** plan carries decisions (signatures, test names, the emit registry, seed source), not code bodies — proportional to the spec.
