# Autovit listing status self-update (hourly sweep) — Design

**Date:** 2026-11-16
**Size:** small change
**Status:** approved (approach A; full reconcile; follows Auto toggle)

## Intent / why

After a car is published to Autovit, JARVIS writes the draft as `unpaid`. Once
the user manually pays/activates the ad on Autovit.ro it becomes `active`, but
JARVIS never learns — the Detail → Anunțuri chip stays stuck on **"Draft
(neplătit)"** until someone clicks **⋯ → "Verifică status acum"**
([verify_vehicle_status](../../../jarvis/carpark/connectors/autovit/routes.py)).

The sales team expects the badge to reflect reality on its own. This makes the
hourly Autovit auto-sweep pull the live advert status so the chip self-corrects
within ≤1h, no click.

## Goals

- A listing on **Auto** has its real Autovit status reflected within ≤1h, with
  no manual action — primarily `unpaid → active` (clears the Draft badge).
- Full reconcile: also reflect `active → expired / removed_by_* / moderation`
  so the chip stays honest in both directions.
- Reuse the existing scheduler, schedule rows, and verify logic — no new cron,
  no new scheduler registration.
- Manual **"Verifică status acum"** button keeps working unchanged (and shares
  the same code path).

## Non-goals

- No change to *what* content is pushed to Autovit (republish logic untouched).
- No polling of listings set to **Manual** (cadence `manual`/disabled) — those
  rely on the button. This is deliberate (see Gating).
- No new per-car "status-sync" toggle — status-pull rides the existing Auto
  switch.
- Shopify side unchanged (it has no equivalent paid/unpaid-draft concept).

## Anti-goals

- Don't add an unbounded burst of Autovit API calls. The pull is one read per
  **due** Autovit listing per tick — bounded by the same due-loop the sweep
  already walks (~18 listings/hr today). If the fleet grows large, a LIMIT is a
  parked follow-up (mirrors the existing sweep's unbounded-batch note).
- Don't let a status-read failure break the republish pass — best-effort,
  isolated per listing (matches the route's `try/except … continue`).

## Constraints

- Runs only when `ENABLE_LISTING_AUTOSYNC=true` **and** the config kill-switch
  is on — same two-level gate as today ([autosync_enabled](../../../jarvis/tasks/listing_autosync.py)).
  Both are satisfied on prod; staging has `ENABLE_SCHEDULER=false` so the tick
  can't be demoed there (validate via unit tests + prod).
- The sweep's Autovit pass is scoped to the **primary** Autovit account
  (`accounts[0]`), unchanged.
- Timestamps: upsert bumps `last_sync` (aware UTC) exactly as the verify route
  does, so the freshness classifier stays consistent.

## Approaches considered

- **A — Fold the status-pull into the hourly sweep (CHOSEN).** Extract the
  verify route's pull-and-upsert into one shared helper in `autovit/service.py`;
  call it for each due listing in the sweep's Autovit loop *before* the
  stale/republish decision, so the republish decision runs against the freshly
  upserted status. Refactor the route to call the same helper (dedup, no
  behavior change). Reuses the scheduler + `carpark_listing_schedules` rows +
  the `1h` row auto-created at publish — the draft Audi is *already* visited
  hourly; the sweep just ignores it today.
  *Trade-off:* +1 Autovit read per due listing/hr. Negligible now.

- **B — Separate "poll only unpaid drafts" job.** A new repo query
  (`list_by_status('unpaid')`) + a parallel pass that pulls status only for
  drafts, independent of schedule rows. *Rejected:* second code path that pulls
  status, misses `active → expired/removed`, and duplicates logic the sweep is
  already positioned to run.

- **C — Lazy verify-on-view.** Trigger a background verify when someone opens
  the car's Anunțuri tab and the listing is a stale draft. *Rejected:* not true
  self-update — the list view and other users don't see the flip until someone
  opens that specific car.

## The how (decided)

1. **Shared helper** `refresh_autovit_listing_status(connector, listing, *, timeout=10) -> str | None`
   in `autovit/service.py`: builds a bounded client, reads
   `client.get_account_advert(ext_id)`, upserts `status` (+ `external_url`,
   `last_error=None`) via `AutovitListingRepository.upsert`, returns the new
   status (or `None` on no-id / read failure, logged). This is the exact logic
   currently inline in `verify_vehicle_status`.

2. **Route refactor:** `verify_vehicle_status` loops over listings and calls the
   helper — identical observable behavior, just deduplicated.

3. **Sweep:** in `resync_autovit_vehicle` (or the Autovit due-loop), call the
   helper first for the listing, then re-read the listing so the existing
   `autovit_sweep_stale` / `compute_autovit_freshness` decision runs against the
   real status. Status-pull is best-effort and must not abort the republish
   branch. `mark_run`'s `last_result` string gains the pulled status for
   observability (e.g. `status:active; skipped (up_to_date)`).

4. **Gating = Auto toggle (free):** the sweep already only iterates
   `list_due` (enabled schedules), so Manual listings are skipped with no extra
   code. A published listing defaults to a `1h` enabled row, so the common case
   is covered automatically.

5. After an upsert that changes the live-channel count (e.g. a discovered
   removal), call `sync_listing_status_hook(vehicle_id)` best-effort — same
   reconcile the verify route already does — so the vehicle's lifecycle status
   stays consistent. (Decide during impl whether to hook it per-change in the
   sweep or leave sweep-side reconcile as a follow-up; the route keeps it.)

## Left to the builder

- Exact placement of the status-pull (inside `resync_autovit_vehicle` vs the
  loop body) — pick whichever keeps the helper single-sourced and testable.
- Whether the sweep calls `sync_listing_status_hook` per upsert or defers it
  (bounded either way; route behavior is unchanged regardless).
- Tests (TDD): helper upserts live status; sweep flips `unpaid → active`
  (freshness `draft → up_to_date`); full-reconcile `active → expired` reflected;
  Manual/disabled listing is not polled; read failure doesn't break republish.
  DB-backed carpark tests need `DATABASE_URL=postgresql://localhost/defaultdb`.
