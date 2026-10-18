"""Reconcile externally-published listings (Autovit adverts, Shopify products)
back to CarPark vehicles by VIN.

Cars are often published to Autovit/Shopify outside JARVIS (or the link was
lost), so JARVIS shows them as unpublished. These helpers match live external
listings to local vehicles by VIN and report which ones to link — the pure
matcher here is platform-agnostic; the orchestration (paging a connector's
listings, writing the link rows) lives in the routes/service that owns I/O.
"""
import time
from typing import Any, Dict, List


def _norm_vin(value: Any) -> str:
    return str(value or '').strip().upper()


def match_by_vin(external_items: List[Dict[str, Any]],
                 vehicles_by_vin: Dict[str, int]) -> Dict[str, Any]:
    """Match external listings to local vehicles by VIN (exact, case/space-
    insensitive). `external_items`: [{'vin','external_id','external_url'}, ...];
    `vehicles_by_vin`: {VIN(upper): vehicle_id}. Deduplicates by VIN (first wins).
    Returns {'matches':[{vehicle_id,external_id,external_url,vin}],
    'matched':int, 'unmatched':int}."""
    matches: List[Dict[str, Any]] = []
    unmatched = 0
    seen = set()
    for item in external_items:
        vin = _norm_vin(item.get('vin'))
        if not vin or vin in seen:
            continue
        seen.add(vin)
        vehicle_id = vehicles_by_vin.get(vin)
        if vehicle_id is None:
            unmatched += 1
            continue
        matches.append({'vehicle_id': vehicle_id,
                        'external_id': item.get('external_id'),
                        'external_url': item.get('external_url'),
                        'vin': vin})
    return {'matches': matches, 'matched': len(matches), 'unmatched': unmatched}


def _advert_vin(advert: Dict[str, Any]) -> str:
    """Autovit advert -> normalised VIN from its params (or '')."""
    return _norm_vin((advert.get('params') or {}).get('vin'))


def find_active_advert_by_vin(client, vin: str, page_cap: int = 5,
                              detail_cap: int = 3, timeout: int = 4,
                              deadline_s: float = 12.0):
    """Find one ACTIVE Autovit advert on the account whose VIN matches `vin`.

    Returns ``(external_id, external_url)`` of the first match, else ``(None,
    None)``. Early-exits on the first match. Bounded for use INSIDE the publish
    request so it can't blow the ~60s gateway: at most `page_cap` pages and
    `detail_cap` per-advert detail lookups each with a short `timeout`, AND a
    hard `deadline_s` wall-clock budget (the per-call timeouts alone don't cap
    the total). VIN is read from the list result when present, else a bounded
    `get_advert`.

    Lets publish adopt+update an already-live ad by VIN instead of creating a
    duplicate (e.g. the local link was lost/removed but the ad is still up).
    """
    target = _norm_vin(vin)
    if not target:
        return None, None
    start = time.monotonic()
    detail_calls = 0
    page, total_pages = 1, 1
    while page <= min(total_pages, page_cap):
        if time.monotonic() - start > deadline_s:
            break
        data = client.get_adverts(page=page, status='active', timeout=timeout) or {}
        total_pages = data.get('total_pages', 1) or 1
        for ad in data.get('results', []) or []:
            v = _advert_vin(ad)
            if (not v and ad.get('id') and detail_calls < detail_cap
                    and time.monotonic() - start <= deadline_s):
                detail_calls += 1
                v = _advert_vin(client.get_advert(str(ad['id']), timeout=timeout) or {})
            if v and v == target:
                return str(ad.get('id')), ad.get('url')
        page += 1
    return None, None


def reconcile_autovit_account(client, account_id: int, vehicles_by_vin: Dict[str, int],
                              listing_repo, advert_cap: int = 500) -> Dict[str, Any]:
    """Scan one Autovit dealer account's active adverts, match by VIN to local
    vehicles, and create the `carpark_autovit_listings` link for any match that
    isn't linked yet (idempotent — already-linked vehicles are skipped).

    `client`: AutovitClient (get_adverts/get_advert); `listing_repo`:
    AutovitListingRepository (get/upsert). The VIN is taken from the list result
    when present, else one get_advert per result (bounded by `advert_cap`, so a
    huge account can't run away — `capped=True` flags an incomplete scan).
    """
    items: List[Dict[str, Any]] = []
    scanned = detail_calls = 0
    capped = False
    page, total_pages = 1, 1
    while page <= total_pages:
        data = client.get_adverts(page=page, status='active') or {}
        total_pages = data.get('total_pages', 1) or 1
        for ad in data.get('results', []) or []:
            scanned += 1
            vin = _advert_vin(ad)
            if not vin and ad.get('id') and detail_calls < advert_cap:
                detail_calls += 1
                vin = _advert_vin(client.get_advert(str(ad['id'])) or {})
            items.append({'vin': vin, 'external_id': str(ad.get('id')),
                          'external_url': ad.get('url')})
        if detail_calls >= advert_cap:
            capped = True
            break
        page += 1

    matched = match_by_vin(items, vehicles_by_vin)
    linked = already_linked = 0
    links: List[Dict[str, Any]] = []
    for m in matched['matches']:
        existing = listing_repo.get(m['vehicle_id'], account_id)
        if existing and existing.get('external_advert_id'):
            already_linked += 1
            continue
        listing_repo.upsert(m['vehicle_id'], account_id,
                            external_advert_id=str(m['external_id']),
                            external_url=m['external_url'], status='active')
        linked += 1
        links.append(m)
    return {'scanned': scanned, 'matched': matched['matched'],
            'unmatched': matched['unmatched'], 'linked': linked,
            'already_linked': already_linked, 'capped': capped, 'links': links}


def reconcile_shopify(client, vehicles_by_vin: Dict[str, int],
                      pub_repo, platform_id: int) -> Dict[str, Any]:
    """Scan the Shopify store's products, match SKU (= VIN) to local vehicles,
    and create the publishing-listing link for any match not linked yet.

    `client.list_products_with_sku()` -> [{'id','sku','url'}, ...]; `pub_repo`:
    PublishingRepository (get_listing_by_vehicle_platform/create_listing).
    Idempotent — vehicles with an existing linked listing are skipped.
    """
    products = client.list_products_with_sku() or []
    items = [{'vin': p.get('sku'), 'external_id': p.get('id'), 'external_url': p.get('url')}
             for p in products]
    matched = match_by_vin(items, vehicles_by_vin)
    linked = already_linked = 0
    links: List[Dict[str, Any]] = []
    for m in matched['matches']:
        existing = pub_repo.get_listing_by_vehicle_platform(m['vehicle_id'], platform_id)
        if existing and existing.get('external_listing_id'):
            already_linked += 1
            continue
        pub_repo.create_listing({'vehicle_id': m['vehicle_id'], 'platform_id': platform_id,
                                 'external_listing_id': m['external_id'],
                                 'external_url': m['external_url'], 'status': 'published'})
        linked += 1
        links.append(m)
    return {'scanned': len(products), 'matched': matched['matched'],
            'unmatched': matched['unmatched'], 'linked': linked,
            'already_linked': already_linked, 'links': links}
