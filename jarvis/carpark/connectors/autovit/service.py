"""Autovit publish core — shared by the `publish()` route (Task 4) and the
auto-sweep (Task 5, next).

Extracted verbatim from `routes.py`'s `publish()` handler (routes.py:777-911
pre-refactor): taxonomy resolve (`taxonomy.vehicle_to_advert`) -> 422
unmapped-REQUIRED guard -> 400 missing-fields guard -> dry_run early return
-> (else) build client, fill location/contact, attach the (already-fetched)
photo collection, create/update the advert (VIN-adopt + removed-recreate
handling), post-write `_verify_advert`, and stamp the listing row via
`AutovitListingRepository.upsert(..., last_published_at=now)` (Task 3).

`publish()` now only does HTTP concerns (auth, request parsing, translating
this module's return dict into the exact pre-refactor JSON responses/status
codes) and calls `republish_vehicle()` for everything else.

IMPORTANT — mocking: `test_autovit_push.py` patches helpers (`_build_client`,
`_verify_advert`, `_fill_location_contact`, `_autovit_error_message`, the
`_listing_repo`/`reconcile_service` singletons) via `patch.object(routes,
"...")` / `monkeypatch.setattr(routes, "...")`, i.e. on the `routes` MODULE
object. Those helpers are deliberately left defined in `routes.py` (not
moved here) and are called from this module through a *live* attribute
lookup — `r._build_client(...)`, `r._verify_advert(...)`, etc. — rather than
`from .routes import _build_client`. A plain name-import would bind this
module's own copy of the reference at import time, which a test's patch on
`routes.<name>` would never touch; the qualified `r.<name>` lookup re-reads
`routes.__dict__` on every call, so the patch is always visible here too.
"""
import logging
import time

import requests

from . import routes as r
from . import taxonomy
from . import taxonomy_map as taxonomy_map_module
from .client import AutovitClient
from carpark.services import reconcile_service
from carpark.services.photo_urls import public_photo_urls

logger = logging.getLogger('jarvis.autovit.service')


def _attach_image_collection(client: AutovitClient, advert: dict, photos,
                             photos_error=None) -> dict:
    """Build an Autovit image collection from already-fetched photo keys/URLs
    and attach its id to `advert`. Returns {'sent': n, 'error': str|None}.

    `photos` is resolved by the caller (the route via
    `VehiclePhotoRepository.urls(vehicle_id)`, or the sweep) — this function
    does no DB access of its own. `carpark_vehicle_photos.url` holds PRIVATE
    Spaces object keys, not URLs — Autovit fetches images server-side and
    cannot read those, so every key is presigned first.

    `photos_error` lets the caller report a failure it hit WHILE fetching the
    photo keys (e.g. a DB error on the photos query). That failure can't block
    the advert, but it must NOT be swallowed either — it's returned as the
    `error` here so it lands in `last_error` with a `photos:` prefix and flips
    `photos_ok` to False, exactly as the pre-refactor inline fetch did.
    """
    if photos_error:
        return {'sent': 0, 'error': photos_error}
    try:
        photo_urls = public_photo_urls(photos or [])
    except Exception as e:
        logger.warning('Autovit photo presign failed: %s', e)
        return {'sent': 0, 'error': f'photo lookup failed: {e}'}
    if not photo_urls:
        return {'sent': 0, 'error': None}
    try:
        icid = client.create_image_collection(photo_urls)
    except Exception as e:
        # A bare "400 Bad Request" isn't actionable — capture Autovit's actual
        # rejection reason (the HTTPError response body) plus a sample source URL
        # (host/path/query shape) so the real cause is diagnosable from the logs.
        body = getattr(getattr(e, 'response', None), 'text', '') or ''
        sample = photo_urls[0] if photo_urls else ''
        logger.warning(
            'Autovit image collection failed: %s | autovit_body=%s | sample_source=%s',
            e, body[:600], sample[:220])
        return {'sent': len(photo_urls), 'error': f'image collection rejected: {e}'}
    if not icid:
        return {'sent': len(photo_urls), 'error': 'image collection returned no id'}
    advert['image_collection_id'] = icid
    return {'sent': len(photo_urls), 'error': None}


def republish_vehicle(account: dict, vehicle: dict, photos, taxonomy_map: dict,
                      *, dry_run: bool = False, now, photos_error=None) -> dict:
    """Push core: resolve `vehicle` against `taxonomy_map` into an Autovit
    advert and (unless blocked or `dry_run`) create/update it on Autovit,
    then stamp the listing row.

    `photos_error` (optional): a failure string from the caller's own photo
    fetch (the route catches a raising `_photo_repo.urls` and passes it here
    with an empty `photos`). It never blocks the advert, but is surfaced in
    `last_error`/`warnings` + `photos_ok=False` so a transient DB blip on the
    photo query can't silently publish an advert with no record photos were
    lost.

    Returns one of:
    - `{'success': False, 'unmapped_required': [...], 'unmapped': [...]}` —
      a REQUIRED dimension (make/model/body_type/fuel_type/color) has no
      taxonomy mapping. Autovit is never called.
    - `{'success': False, 'missing': [...], 'advert': ..., 'unmapped': [...]}`
      — the assembled advert is missing fields `taxonomy.validate_for_publish`
      requires. Autovit is never called.
    - `{'success': True, 'dry_run': True, 'advert': ..., 'unmapped': [...]}`
      — `dry_run=True`: the advert was assembled + validated but never sent.
    - `{'success': True, 'external_id', 'external_url', 'status',
      'updated_existing', 'photos_sent', 'photos_ok', 'photos_remote',
      'params_dropped', 'unmapped', 'warnings'}` — the advert was pushed and
      the listing row upserted with `last_published_at=now`.
    - `{'success': False, 'error': str}` — Autovit rejected the push (the
      listing row's `last_error` is set via `_listing_repo.set_error`).
    """
    advert, unmapped = taxonomy.vehicle_to_advert(vehicle, account, taxonomy_map)
    # An unmapped value in a REQUIRED dimension would doom the Autovit call to
    # a 400 anyway — block BEFORE spending the network round-trip.
    unmapped_required = [u for u in unmapped
                         if u.split(':', 1)[0] in taxonomy_map_module.REQUIRED_DIMENSIONS]
    if unmapped_required:
        return {'success': False, 'unmapped_required': unmapped_required, 'unmapped': unmapped}

    missing = taxonomy.validate_for_publish(advert)
    if missing:
        return {'success': False, 'missing': missing, 'advert': advert, 'unmapped': unmapped}

    if dry_run:
        return {'success': True, 'dry_run': True, 'advert': advert, 'unmapped': unmapped}

    client = r._build_client(account)
    # 504-guard: a single publish chains several sequential Autovit calls (token,
    # location/contact backfill, image collection, create/update, verify). At the
    # default 15s each they can sum past DO's ~60s gateway limit → 504. Cap the
    # per-call timeout to 10s here (the best-effort backfill and the verify are
    # bounded even shorter at their call sites) so the worst case stays ~<55s.
    client.timeout = 10
    _t0 = time.monotonic()
    # Backfill location + contact from the account's own adverts if the config
    # didn't carry them (Autovit requires them on create).
    r._fill_location_contact(client, advert)
    _t_fill = time.monotonic()
    # Photos: non-fatal (an advert is created fine without them, as an unpaid
    # draft) but NOT silent — a failure is recorded on the listing row and in
    # the response so it shows up in JARVIS instead of as an empty gallery on
    # Autovit's form.
    photo_result = _attach_image_collection(client, advert, photos, photos_error)
    _t_photos = time.monotonic()

    vehicle_id = vehicle['id']
    account_id = account['id']

    try:
        existing = r._listing_repo.get(vehicle_id, account_id)
        ext_id = existing.get('external_advert_id') if existing else None
        # An advert the user/moderator removed on Autovit can't be updated — the
        # PUT returns 400 ("Bad Request"). Treat a known-removed listing as gone
        # and create a fresh advert instead of failing the publish.
        removed_on_autovit = bool(existing) and str(existing.get('status') or '').startswith('removed')
        updated_existing = bool(ext_id) and not removed_on_autovit
        if updated_existing:
            try:
                client.update_advert(ext_id, advert)
            except requests.HTTPError as e:
                code = getattr(e.response, 'status_code', None)
                if code not in (400, 404, 410):
                    raise
                # Advert gone/invalid on Autovit — recreate rather than surface a 400.
                logger.info('Autovit update of advert %s returned %s; recreating', ext_id, code)
                updated_existing = False
        if updated_existing:
            ext_url = existing.get('external_url')
            ext_status = 'active'
        else:
            # VIN-dedup: before creating, check whether a live Autovit ad with
            # this vehicle's VIN already exists on the account. If so, adopt +
            # update it (connect/reconcile the listing) instead of posting a
            # duplicate — covers the case where the local link was lost/removed
            # but the ad is still up.
            adopted_id, adopted_url = reconcile_service.find_active_advert_by_vin(
                client, vehicle.get('vin'))
            if adopted_id:
                logger.info('Autovit: adopting live advert %s by VIN for vehicle %s '
                            '(no duplicate)', adopted_id, vehicle_id)
                client.update_advert(adopted_id, advert)
                ext_id, ext_url, ext_status = adopted_id, adopted_url, 'active'
                updated_existing = True
            else:
                # New adverts are created in Autovit's `unpaid` status — a private
                # draft, not visible on the marketplace until paid/activated.
                result = client.create_advert(advert) or {}
                ext_id = result.get('id')
                ext_url = result.get('url')
                ext_status = result.get('status') or 'unpaid'
        _t_write = time.monotonic()

        # Post-write verification: read the advert back and diff what we sent
        # against what Autovit kept. Silently-dropped params are otherwise
        # invisible (the create/update returns 2xx regardless).
        verify = r._verify_advert(client, ext_id, advert)
        # Prefer the status Autovit actually reports (read back) over our guess —
        # a create lands 'unpaid'; an active ad updated in place stays 'active'.
        if verify.get('status_remote'):
            ext_status = verify['status_remote']
        # Per-stage timing — surfaces which leg is slow when a publish flirts
        # with the gateway limit (the whole reason for the bounds above).
        logger.info(
            'Autovit publish timing vehicle=%s update=%s fill=%.1fs photos=%.1fs '
            'write=%.1fs verify=%.1fs total=%.1fs', vehicle_id, updated_existing,
            _t_fill - _t0, _t_photos - _t_fill, _t_write - _t_photos,
            time.monotonic() - _t_write, time.monotonic() - _t0)

        # Problems belong in last_error (the fault surface that drives the error
        # badge). The "already published" note is informational — it goes to the
        # response warnings (a toast) only, and must NOT pollute last_error.
        problems = []
        if photo_result['error']:
            problems.append(f"photos: {photo_result['error']}")
        if verify['params_dropped']:
            problems.append('params_dropped: ' + ', '.join(verify['params_dropped']))
        if verify['photos_remote'] is not None and photo_result['sent'] and \
                verify['photos_remote'] < photo_result['sent']:
            problems.append(f"photos: sent {photo_result['sent']}, Autovit kept {verify['photos_remote']}")
        if unmapped:
            # Non-required unmapped values (equipment, etc.) didn't block the
            # publish, but a dropped value is still a fault worth surfacing —
            # same treatment as params_dropped/photos above.
            problems.append('unmapped: ' + ', '.join(unmapped))
        last_error = '; '.join(problems) if problems else None
        warnings = (['Anunț deja publicat pe Autovit — a fost actualizat.']
                    if updated_existing else []) + problems

        r._listing_repo.upsert(vehicle_id, account_id,
                               external_advert_id=str(ext_id),
                               external_url=ext_url,
                               status=ext_status,
                               last_error=last_error,
                               last_published_at=now)
        return {'success': True, 'external_id': ext_id,
                'external_url': ext_url, 'status': ext_status,
                'updated_existing': updated_existing,
                'photos_sent': photo_result['sent'],
                'photos_ok': photo_result['error'] is None,
                'photos_remote': verify['photos_remote'],
                'params_dropped': verify['params_dropped'],
                'unmapped': unmapped,
                'warnings': warnings}
    except Exception as e:
        # Capture Autovit's actual rejection reason (the HTTPError response body) —
        # str(e) is just "400 Bad Request for url ...", which isn't actionable.
        body = getattr(getattr(e, 'response', None), 'text', '') or ''
        logger.exception('Autovit publish failed for vehicle %s | autovit_body=%s',
                         vehicle_id, body[:800])
        # A body means Autovit actually responded with a structured rejection —
        # parse it into something a non-engineer can act on. No body (e.g. a
        # network/timeout/mock error) falls back to the plain str(e).
        msg = r._autovit_error_message(body) if body else str(e)
        r._listing_repo.set_error(vehicle_id, account_id, msg)
        return {'success': False, 'error': msg}
