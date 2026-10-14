# Buyback → Custody (Consignment) Transfer — Design

**Date:** 2026-10-14
**Branch:** `feat/buyback-custody-transfer` (off `staging`)
**Status:** Design approved (in-chat). Awaiting spec review → implementation plan.

---

## 1. Problem

When a buyback acquisition **fails** — the client declines our purchase offer and the
record ends in `LOST` — the lead is dropped entirely today. There is no way to keep the
car in play under a different commercial arrangement.

The business wants a **second layer**: after a failed acquisition, offer to take the car on
**custody (consignment / custodie)** — we hold and sell it on the owner's behalf for a
commission instead of having bought it. Operationally that means getting the car into
CarPark marked as a consignment vehicle (not owned), carrying a custody agreement with it.

### Current state (what exists / what's missing)
- **CarPark already has `carpark_vehicles.is_consignment BOOLEAN DEFAULT FALSE`**
  (`jarvis/migrations/domains/schema_carpark.py:155`; `jarvis/frontend/src/types/carpark.ts:39`)
  but it is **dormant** — the only references are the repo field list
  (`jarvis/carpark/repositories/vehicle_repository.py:66`) and the TS type. It drives no
  pricing, listing, or invoicing behavior today.
- **`carpark_source`** is a seeded dropdown (`EXTERN COMANDA`, `BUY BACK PJ`, `IRC`,
  `DEALER`, `BUY BACK PF`, `EXTERN STOC`, `PORSCHE ROMANIA`, `PORSCHE MOBILITY` —
  `schema_carpark.py:957-964`). **No custody/consignment source value exists.**
- The buyback → CarPark hand-off (`jarvis/buyback/services/carpark_handoff.py`) runs **only**
  on `BOUGHT` records and stamps `purchase_price_net` from the accepted final offer. It
  already carries the photo gallery over and back-links via `carpark_vehicle_links`.
- `buyback_records` has `carpark_vehicle_id BIGINT` (`schema_buyback.py:42`), set by finalize
  (`finalize.py:109`). The delete guard already blocks deleting **any** record with
  `carpark_vehicle_id` set (`routes/records.py:579`; `frontend/.../index.tsx:266`).

## 2. Goals / Non-goals

**Goals (this slice)**
- On a `LOST` buyback record, an authorized user can **transfer the car into CarPark as a
  consignment vehicle** via a new action.
- At transfer, capture a **custody agreement**: owner's desired payout, commission
  (per-deal choice of **percentage or fixed**), minimum sale price (floor), contract number,
  agreement date, expiry date, currency.
- The CarPark vehicle is created with `is_consignment=true`, a new `CUSTODIE` source,
  **no purchase price**, photos carried over, and back-linked to the buyback record.
- Surface the custody relationship in both modules: a "→ Custodie" marker + CarPark link on
  the buyback record, and a "Custodie" badge + agreement card on the CarPark vehicle.

**Non-goals (deferred)**
- Consignment **accounting**: owner payout on sale, commission invoicing, VAT margin scheme.
- **Floor-price enforcement** at sale time (the floor is stored + shown, not enforced yet).
- `is_consignment` driving CarPark **pricing / listing / margin** behavior.
- Any **client-facing** custody proposition or e-signature flow.
- Triggering custody from `CANCELLED` records or at the moment of offer-decline (this slice
  is the post-`LOST` action only).

## 3. Locked decisions

1. **Entry point:** a new action on `LOST` records. The buyback **stays `LOST`** (the
   acquisition genuinely failed); custody is a downstream fact recorded via the CarPark
   back-link, not a new lifecycle status. No change to `buyback_lifecycle` transitions.
2. **"Transferred to custody" invariant:** `status='LOST' AND carpark_vehicle_id IS NOT NULL`.
   We **reuse the existing `carpark_vehicle_id`** column — **no new `buyback_records`
   columns**. Beneficial side effect: the existing delete guard already makes such a record
   non-deletable.
3. **Commission model:** per-deal choice — `commission_type ∈ {percent, fixed}` +
   `commission_value`.
4. **Agreement storage:** a new **1:1 table `carpark_vehicle_consignment`** (not columns on
   the wide `carpark_vehicles`; not on the buyback side). Keeps consignment-only fields out
   of the core vehicle row, where they would be NULL for the non-consignment majority.
5. **CarPark representation:** `status='ACQUIRED'` (enters the park as a draft, same as the
   BOUGHT hand-off) + `is_consignment=true` + `source='CUSTODIE'`; `purchase_price_net=NULL`.
6. **Permission:** a new action `buyback.record.custody`, granted initially to the same roles
   that hold `buyback.record.finalize`.

## 4. Data model

### 4.1 New table `carpark_vehicle_consignment` (in `schema_carpark.py`, idempotent)
```sql
CREATE TABLE IF NOT EXISTS carpark_vehicle_consignment (
    vehicle_id       BIGINT PRIMARY KEY REFERENCES carpark_vehicles(id) ON DELETE CASCADE,
    owner_price      NUMERIC(12,2),               -- preț dorit proprietar
    currency         VARCHAR(3)  NOT NULL DEFAULT 'EUR',
    commission_type  VARCHAR(10) NOT NULL CHECK (commission_type IN ('percent','fixed')),
    commission_value NUMERIC(12,2) NOT NULL,       -- percent (5.00 = 5%) OR fixed amount
    min_sale_price   NUMERIC(12,2),                -- floor
    contract_number  VARCHAR(50),
    agreement_date   DATE,
    expiry_date      DATE,
    created_by       INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
- 1:1 with the vehicle; cascade-deletes with it.
- `commission_value` interpretation keyed off `commission_type`. For `percent` it is a
  percentage; for `fixed` it is an amount in `currency`.

### 4.2 `carpark_source` seed (idempotent)
Add `CUSTODIE` to the `carpark_source` dropdown options (guarded insert mirroring the
existing `schema_carpark.py:953-964` block), so it appears in source filters/pickers.

### 4.3 Buyback side
No schema change. `carpark_vehicle_id` is reused as the back-link.

### 4.4 Back-link
A `carpark_vehicle_links` row (`linked_entity_type='buyback'`, `linked_entity_id=record.id`),
created by the same `_backlink` helper the BOUGHT hand-off uses.

## 5. Backend

### 5.1 Service — `handoff_to_carpark_custody(record, agreement, actor)`
New function in `jarvis/buyback/services/carpark_handoff.py`, mirroring `handoff_to_carpark`:
- Builds the vehicle `data` dict with `status='ACQUIRED'`, `source='CUSTODIE'`,
  `is_consignment=True`, `purchase_price_net=None`, owner/supplier = seller, category from
  `is_trade_in`, `company_id` server-side.
- `VehicleService().create_vehicle(data, created_by=actor)` — `ValueError` (missing/dup VIN)
  propagates verbatim, exactly as the BOUGHT path relies on.
- Inserts the `carpark_vehicle_consignment` row via the new repository (see 5.3).
- **Reuses** `_carry_photos(record['id'], veh['id'])` and `_backlink(...)` (both best-effort,
  already log-and-swallow).
- Returns the created vehicle dict.

Ordering note: create vehicle → write consignment row → carry photos → back-link, then the
route stamps `record.carpark_vehicle_id`. The consignment row is written **before** the
best-effort photo/link steps so a Spaces/FK hiccup never loses the agreement. The only
hard-failure window is the consignment `INSERT` itself (a simple local write right after the
vehicle exists): if it raises, the vehicle already exists as `is_consignment` without an
agreement row and `carpark_vehicle_id` is not yet stamped — i.e. the **same orphan-vehicle
failure mode the BOUGHT hand-off already accepts** (`finalize.py:91`: the VIN now lives in
CarPark, so a naive retry hits the dup-VIN `409`). Recovery is operational: complete the
agreement on the existing vehicle, or delete that draft vehicle and re-run the transfer. The
plan should decide whether to add a custody **retry/repair** path analogous to
`/handoff/retry`, or document the manual recovery (leaning: document for this slice, since
the failure window is a single local `INSERT`).

### 5.2 Route — `POST /buyback/records/<id>/custody`
New `jarvis/buyback/routes/custody.py`, registered on the buyback blueprint.
Guards, in order (mirroring `finalize.py`):
1. record exists → else 404
2. `_shared._guard_company(record)` → else 403
3. `@v2_permission_required('buyback', 'record', 'custody')`
4. `record['status'] == LOST` → else 409 ("only LOST records can be taken on custody")
5. `record['carpark_vehicle_id'] is None` → else 409 ("already transferred to custody")
6. **validate agreement payload** (see 5.4) → else 400

On success: run `handoff_to_carpark_custody`, then
`records_repo.update(id, {'carpark_vehicle_id': veh['id']})`, return `200 {vehicle, ...}`.
VIN `ValueError` → `409` with the verbatim message (a LOST car whose VIN already sits in
CarPark is a real conflict the user must resolve), consistent with finalize's retryable
hand-off contract.

### 5.3 Repository — `ConsignmentRepository`
New repo (subclassing `core.base_repository.BaseRepository`) with `create(vehicle_id,
agreement, created_by)` and `get_by_vehicle(vehicle_id)`. Parameterized SQL, `%s` params.

### 5.4 Agreement validation (server-side, authoritative)
- `commission_type ∈ {'percent','fixed'}` (else 400).
- `commission_value`: required, numeric, ≥ 0; for `percent`, 0–100.
- `owner_price`, `min_sale_price`: optional, numeric ≥ 0 when present.
- `currency`: 3-letter, default `EUR`.
- `agreement_date`, `expiry_date`: optional ISO dates; if both present, `expiry ≥ agreement`.
- `contract_number`: optional string ≤ 50 chars.
Never trust `company_id`/price fields that belong server-side.

## 6. Frontend

### 6.1 Buyback — ActionPanel (`jarvis/frontend/src/pages/BuyBack/ActionPanel.tsx`)
- New button **"Transferă în custodie"** shown when
  `status === 'LOST' && !record.carpark_vehicle_id && can('buyback.record.custody')`.
- Opens a dialog capturing the agreement:
  - Preț proprietar (`owner_price`) + currency
  - Comision: radio `Procent % / Sumă fixă` → `commission_type` + `commission_value`
  - Preț minim (`min_sale_price`)
  - Număr contract, Data acord, Data expirare
- Submit → `buybackApi.transferToCustody(record.id, agreement)` → success toast + link to the
  new CarPark vehicle; invalidate the record/offers queries.
- **`showReopen`** gains an extra `&& !record.carpark_vehicle_id` guard so a custody-linked
  LOST record cannot be reopened.
- When transferred: a **"→ Custodie"** badge + link to the CarPark vehicle.

### 6.2 Buyback — Detail (`BuyBackDetail.tsx`)
A new **"Custodie"** card (shown when `status === 'LOST' && carpark_vehicle_id`) rendering the
agreement terms + a link to the CarPark vehicle. Agreement fetched via the record payload or
a small dedicated endpoint (decide in plan; prefer embedding in the record GET to avoid an
extra round-trip).

### 6.3 CarPark — vehicle detail/list
- A **"Custodie"** badge wherever vehicles render a status/source chip, when `is_consignment`.
- An **agreement card** on the vehicle detail (owner price, commission, floor, contract,
  dates). `CUSTODIE` source flows into existing source filters automatically via the seed.

### 6.4 API client + types
- `buybackApi.transferToCustody(recordId, agreement)` in `frontend/src/api/buyback.ts`.
- Consignment agreement type in `frontend/src/types/buyback.ts` and/or `carpark.ts`.

## 7. Permissions
- Register action `buyback.record.custody` in the buyback permission catalog (alongside
  `finalize`). Idempotent role-grant seed mirroring finalize's grants (same roles initially).
- Route decorator: `@v2_permission_required('buyback', 'record', 'custody')`.

## 8. Testing

**Backend (`tests/`, DB-gated as the module already is)**
- Guards: non-`LOST` → 409; already-linked (`carpark_vehicle_id` set) → 409; missing
  permission → 403; cross-company → 403.
- Agreement validation: bad `commission_type`, percent > 100, negative values, expiry <
  agreement → 400.
- Happy path: vehicle created with `is_consignment=true`, `source='CUSTODIE'`,
  `purchase_price_net IS NULL`, `status='ACQUIRED'`; consignment row written with the agreed
  values; `record.carpark_vehicle_id` set; photos carried; `carpark_vehicle_links` row exists.
- VIN conflict → 409 (verbatim message), record left unlinked.

**Frontend**
- ActionPanel button visibility matrix (status × permission × `carpark_vehicle_id`).
- `showReopen` suppressed once `carpark_vehicle_id` is set.
- Agreement form validation (commission radio, required fields).
- Detail "Custodie" card + CarPark badge/agreement card render from fixture data.

## 9. Rollout
- Own branch/worktree off `staging` (separate from the parked "Preț achiziție" display fix on
  `fix/buyback-accepted-price-as-purchase`).
- Migration: new table + `CUSTODIE` dropdown seed + role grant — all idempotent
  (`CREATE TABLE IF NOT EXISTS`, guarded seed `INSERT`s, guarded grant). These touch
  `schema_carpark.py` (protected) — already confirmed in design.
- Pre-push checklist (CLAUDE.md): `npm run build`, `pytest`, `py_compile app.py`.
- Deploy **staging first → validate → `main` on double confirmation**.

## 10. Open questions (resolve during planning, not blockers)
1. Agreement read path: embed in the record GET payload vs a dedicated
   `GET /buyback/records/<id>/custody` / `GET /carpark/vehicles/<id>/consignment`.
2. Where exactly the "Custodie" badge hangs in CarPark list/detail chip rendering.
3. Whether `source='CUSTODIE'` should also appear as a filter preset in the buyback list
   (likely not needed — buyback stays LOST).
4. Minimal audit: rely on `carpark_vehicle_consignment.created_by/created_at` +
   `carpark_vehicle_links.linked_by` (no buyback-side audit columns) — confirm sufficient.
