# Autovit Status Self-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the hourly Autovit auto-sweep pull each due listing's live status so the Detail → Anunțuri chip self-corrects (`unpaid → active`, plus `active → expired/removed/moderation`) within ≤1h, with no manual "Verifică status" click.

**Architecture:** Extract the verify-status route's pull-and-upsert into one shared helper in `autovit/service.py`, then call that helper for each due listing inside the sweep's Autovit loop *before* the existing stale/republish decision, so the decision runs against the freshly-upserted status. The manual verify route refactors to call the same helper (dedup, behavior-identical). No new scheduler, no new schedule rows — reuses the `1h` auto-schedule already created at publish.

**Tech Stack:** Python / Flask, APScheduler (existing in-process scheduler), Postgres, pytest with `unittest.mock`.

**Spec:** [docs/superpowers/specs/2026-11-16-autovit-status-self-update-design.md](../specs/2026-11-16-autovit-status-self-update-design.md)

## Global Constraints

- Sweep runs only when `autosync_enabled()` is true — `ENABLE_LISTING_AUTOSYNC=='true'` **and** the config kill-switch. Do not change this gate. (Both satisfied on prod; staging has `ENABLE_SCHEDULER=false`.)
- Autovit sweep pass is scoped to the **primary** Autovit account (`accounts[0]`) — unchanged.
- The shared helper must reach `_build_client` and `_listing_repo` through the **live `routes`-module attribute lookup** (`r._build_client(...)`, `r._listing_repo.upsert(...)`), NOT a name-import — so `patch.object(routes, "...")` keeps intercepting from inside `service.py` (see `service.py` module docstring).
- Status read is **best-effort**: a failure logs and returns `None`; it must never abort the republish branch or raise out of the sweep.
- Upsert writes `status`, `external_url` (falling back to the existing one), `last_error=None`; `last_sync`/`updated_at` bump to `now()` inside `upsert` (unchanged repo behavior).
- Helper tests are pure mock — no DB, no network (match `test_autovit_service.py`). DB-backed carpark tests otherwise need `DATABASE_URL=postgresql://localhost/defaultdb`.

## Review Focus

- **Listing with no `external_advert_id` / missing account_id** (never-published or half-written row): helper must return `None` without building a client or upserting — covered in Task 1.
- **Autovit read raises / times out** (token fetch or GET hangs): helper swallows, logs, returns `None`; the sweep still runs its republish decision on the pre-pull status — covered in Tasks 1 & 2.
- **`active → expired/removed` discovered by the pull** (full reconcile both directions): sweep reflects the new status and does NOT republish an expired/removed ad — covered in Task 2.
- **Manual listing** (`cadence='manual'` / disabled schedule): never polled, because `list_due` only returns enabled rows — confirmed by a Task 2 test asserting `resync_autovit_vehicle` is not reached for a non-due row.
- **Status unchanged by the pull** (`unpaid` stays `unpaid` — user hasn't paid yet): no vehicle-level reconcile churn; `sync_listing_status_hook` fires only on an actual status transition — covered in Task 2.

---

### Task 1: Shared `refresh_autovit_listing_status` helper + route dedup

**Files:**
- Modify: `jarvis/carpark/connectors/autovit/service.py` (add helper)
- Modify: `jarvis/carpark/connectors/autovit/routes.py:303-327` (verify route calls helper; add import)
- Test: `jarvis/tests/carpark/test_autovit_service.py`

**Interfaces:**
- Produces: `refresh_autovit_listing_status(connector: dict, listing: dict, *, timeout: int = 10) -> str | None` in `service.py`. Reads `listing['external_advert_id']`, `listing['vehicle_id']`, `account_id = listing.get('account_id') or connector['id']`; returns `None` if any is missing. Builds `client = r._build_client(connector)`, sets `client.timeout = timeout`, reads `live = client.get_account_advert(str(ext_id), timeout=timeout) or {}`. On exception: `logger.warning(...)`, return `None`. If `live.get('status')`: `r._listing_repo.upsert(vehicle_id, account_id, status=status, external_url=live.get('url') or listing.get('external_url'), last_error=None)`; return that status. Else return `None`.
- Consumes (route): the above helper, imported alongside `republish_vehicle`.

- [ ] **Step 1: Write the failing tests** in `test_autovit_service.py`

```python
def test_refresh_status_pulls_and_upserts():
    listing = {"external_advert_id": "123", "vehicle_id": 7, "account_id": 1,
               "status": "unpaid", "external_url": "u"}
    client = MagicMock()
    client.get_account_advert.return_value = {"status": "active", "url": "new"}
    with patch.object(r, "_build_client", return_value=client), \
         patch.object(r, "_listing_repo") as repo:
        out = svc.refresh_autovit_listing_status({"id": 1}, listing, timeout=10)
    assert out == "active"
    repo.upsert.assert_called_once_with(7, 1, status="active",
                                        external_url="new", last_error=None)

def test_refresh_status_skips_when_no_advert_id():
    with patch.object(r, "_build_client") as bc, patch.object(r, "_listing_repo") as repo:
        out = svc.refresh_autovit_listing_status(
            {"id": 1}, {"vehicle_id": 7, "account_id": 1}, timeout=10)
    assert out is None
    bc.assert_not_called(); repo.upsert.assert_not_called()

def test_refresh_status_swallows_read_failure():
    client = MagicMock(); client.get_account_advert.side_effect = RuntimeError("timeout")
    listing = {"external_advert_id": "123", "vehicle_id": 7, "account_id": 1}
    with patch.object(r, "_build_client", return_value=client), \
         patch.object(r, "_listing_repo") as repo:
        out = svc.refresh_autovit_listing_status({"id": 1}, listing, timeout=10)
    assert out is None
    repo.upsert.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && python3 -m pytest tests/carpark/test_autovit_service.py -k refresh_status -v`
Expected: FAIL (`AttributeError: module 'carpark.connectors.autovit.service' has no attribute 'refresh_autovit_listing_status'`)

- [ ] **Step 3: Implement `refresh_autovit_listing_status` in `service.py`** per the Interfaces block. Place it near `republish_vehicle`; reuse the module `logger`.

- [ ] **Step 4: Refactor `verify_vehicle_status` in `routes.py:303-327`** to call the helper per listing instead of the inline read/upsert:

```python
from .service import republish_vehicle, refresh_autovit_listing_status
...
for listing in _listing_repo.list_by_vehicle(vehicle_id):
    account_id = listing.get('account_id')
    connector = _repo.get(account_id) if account_id else None
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        continue
    if refresh_autovit_listing_status(connector, listing, timeout=10):
        refreshed += 1
```
Keep the trailing freshness re-serialize + `sync_listing_status_hook(vehicle_id, ...)` block unchanged.

- [ ] **Step 5: Run the helper tests + the existing route/service suites**

Run: `cd jarvis && python3 -m pytest tests/carpark/test_autovit_service.py tests/carpark/test_autovit_pull.py tests/carpark/test_autovit_routes_freshness.py -v`
Expected: PASS (helper tests pass; route tests unchanged — behavior-identical)

- [ ] **Step 6: Commit**

```bash
git add jarvis/carpark/connectors/autovit/service.py jarvis/carpark/connectors/autovit/routes.py jarvis/tests/carpark/test_autovit_service.py
git commit -m "refactor(carpark/autovit): extract shared live-status pull helper; verify route delegates"
```

---

### Task 2: Pull live status in the hourly sweep (self-update)

**Files:**
- Modify: `jarvis/tasks/listing_autosync.py` (import helper; call it in `resync_autovit_vehicle`)
- Test: `jarvis/tests/carpark/test_listing_autosync.py`

**Interfaces:**
- Consumes: `refresh_autovit_listing_status` (Task 1) and the existing `sync_listing_status_hook` (import from `carpark.connectors.listing_status_hook`).
- Produces: `resync_autovit_vehicle(account, vehicle, taxonomy_map, now, catalog_index=None) -> str` — now pulls live status first, re-reads the listing, then runs the existing `autovit_sweep_stale` / `republish_vehicle` logic. Result string is prefixed `status:<pulled>; ` when a status was pulled (e.g. `status:active; skipped (up_to_date)`, `status:active; pushed`). On a status *transition*, calls `sync_listing_status_hook(vehicle['id'])` best-effort.

- [ ] **Step 1: Write the failing tests** in `test_listing_autosync.py` (helper `_autovit_listing` already exists in this file)

```python
def test_resync_autovit_pulls_status_and_clears_draft():
    """A draft (unpaid) that's now paid on Autovit flips to active and the
    stale decision runs against the fresh status."""
    repo = MagicMock()
    repo.get.side_effect = [_autovit_listing(status='unpaid'),      # pre-pull
                            _autovit_listing(status='active')]       # post-pull re-read
    veh = {'id': 5, 'updated_at': NOW - timedelta(hours=3)}  # synced after edit → up_to_date
    with patch.object(A, 'AutovitListingRepository', return_value=repo), \
         patch.object(A, 'refresh_autovit_listing_status', return_value='active') as RF, \
         patch.object(A, 'sync_listing_status_hook') as HOOK:
        out = A.resync_autovit_vehicle({'id': 1}, veh, {}, NOW)
    RF.assert_called_once()
    assert out == 'status:active; skipped (up_to_date)'
    HOOK.assert_called_once_with(5)   # unpaid → active is a transition

def test_resync_autovit_expired_not_republished():
    repo = MagicMock()
    repo.get.side_effect = [_autovit_listing(status='active'),
                            _autovit_listing(status='expired')]
    veh = {'id': 5, 'updated_at': NOW - timedelta(minutes=1)}  # would be stale if active
    with patch.object(A, 'AutovitListingRepository', return_value=repo), \
         patch.object(A, 'refresh_autovit_listing_status', return_value='expired'), \
         patch.object(A, 'sync_listing_status_hook'):
        out = A.resync_autovit_vehicle({'id': 1}, veh, {}, NOW)
    assert out == 'status:expired; skipped (expired)'

def test_resync_autovit_status_pull_failure_still_decides():
    repo = MagicMock()
    repo.get.return_value = _autovit_listing(status='active')  # single read; no re-read on None
    veh = {'id': 5, 'updated_at': NOW - timedelta(minutes=1)}  # stale → would push
    with patch.object(A, 'AutovitListingRepository', return_value=repo), \
         patch.object(A, 'refresh_autovit_listing_status', return_value=None), \
         patch.object(A, 'republish_vehicle', return_value={'success': True}) as PUB, \
         patch.object(A, 'sync_listing_status_hook') as HOOK, \
         patch.object(A, 'VehiclePhotoRepository', return_value=MagicMock()):
        out = A.resync_autovit_vehicle({'id': 1}, veh, {}, NOW)
    assert out == 'pushed'           # no prefix when nothing pulled
    PUB.assert_called_once()
    HOOK.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jarvis && python3 -m pytest tests/carpark/test_listing_autosync.py -k "autovit and (pulls or expired or failure)" -v`
Expected: FAIL (`AttributeError: ... has no attribute 'refresh_autovit_listing_status'` / assertion on prefix)

- [ ] **Step 3: Wire the pull into `resync_autovit_vehicle`** in `listing_autosync.py`. Add imports `from carpark.connectors.autovit.service import republish_vehicle, refresh_autovit_listing_status` and `from carpark.connectors.listing_status_hook import sync_listing_status as sync_listing_status_hook`. Then:

```python
def resync_autovit_vehicle(account, vehicle, taxonomy_map, now, catalog_index=None):
    repo = AutovitListingRepository()
    listing = repo.get(vehicle['id'], account['id'])
    prefix = ''
    if listing:
        old_status = (listing.get('status') or '').lower()
        pulled = refresh_autovit_listing_status(account, listing, timeout=10)
        if pulled:
            prefix = f'status:{pulled}; '
            listing = repo.get(vehicle['id'], account['id'])  # re-read fresh status
            if pulled.lower() != old_status:
                try:
                    sync_listing_status_hook(vehicle['id'])
                except Exception:
                    logger.exception('sync_listing_status_hook failed (vehicle %s)', vehicle['id'])
    if not autovit_sweep_stale(listing, vehicle.get('updated_at'), now):
        reason = compute_autovit_freshness(listing, vehicle.get('updated_at'), now)
        return f'{prefix}skipped ({reason})'
    photos = VehiclePhotoRepository().urls(vehicle['id'])
    res = republish_vehicle(account, vehicle, photos, taxonomy_map, now=now, catalog_index=catalog_index)
    if res.get('success'):
        return f'{prefix}pushed'
    if res.get('unmapped_required'):
        return f"{prefix}skipped: unmapped " + ', '.join(res['unmapped_required'])
    if res.get('missing'):
        return f"{prefix}skipped: missing " + ', '.join(res['missing'])
    return f"{prefix}error: {res.get('error')}"
```
(Single `repo` local replaces the prior double `AutovitListingRepository().get(...)`.)

- [ ] **Step 4: Run the new tests + the full autosync suite**

Run: `cd jarvis && python3 -m pytest tests/carpark/test_listing_autosync.py -v`
Expected: PASS (new Autovit tests pass; existing Shopify/tick tests unaffected — `_only_shopify_due` keeps the Autovit due list empty)

- [ ] **Step 5: Commit**

```bash
git add jarvis/tasks/listing_autosync.py jarvis/tests/carpark/test_listing_autosync.py
git commit -m "feat(carpark/autovit): hourly sweep pulls live listing status (Draft self-clears, full reconcile)"
```

---

## Notes for the executor

- **Branch:** base a feature branch off `origin/staging` (the repo's `dev` is stale) per the JARVIS git workflow; do NOT work on the current `fix/buyback-other-details` branch.
- **No deploy in this plan.** Shipping follows the repo's FF promotion (`dev:staging` → validate → `staging:main`, 2 confirms) and is a separate, user-initiated step.
- **Can't demo the tick on staging** (`ENABLE_SCHEDULER=false`). Verification is the unit tests here; live confirmation happens on prod after promotion (or by manually invoking `listing_autosync_tick()` against a DB with a due Autovit draft).
