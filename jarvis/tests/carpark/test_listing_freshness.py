# jarvis/tests/carpark/test_listing_freshness.py
from datetime import datetime, timezone, timedelta
from carpark.connectors.listing_freshness import compute_listing_freshness

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
def L(**kw):
    base = {'external_listing_id': 'gid://1', 'status': 'published',
            'last_sync': NOW - timedelta(hours=1), 'expires_at': None}
    base.update(kw); return base

def test_none_listing_is_not_published():
    assert compute_listing_freshness(None, NOW, NOW) == 'not_published'

def test_published_and_synced_after_edit_is_up_to_date():
    assert compute_listing_freshness(L(), NOW - timedelta(hours=2), NOW) == 'up_to_date'

def test_edited_after_last_sync_is_stale():
    assert compute_listing_freshness(L(), NOW - timedelta(minutes=1), NOW) == 'stale'

def test_error_status_wins():
    assert compute_listing_freshness(L(status='error'), NOW - timedelta(days=1), NOW) == 'error'

def test_archived_is_inactive():
    assert compute_listing_freshness(L(status='archived'), None, NOW) == 'inactive'

def test_past_expiry_is_expired():
    assert compute_listing_freshness(L(expires_at=NOW - timedelta(days=1)), None, NOW) == 'expired'

def test_never_synced_published_is_stale():
    assert compute_listing_freshness(L(last_sync=None), NOW, NOW) == 'stale'

def test_unknown_status_is_not_published():
    # A status outside the fixed enum (e.g. Shopify 'draft') must not leak through;
    # the frontend maps a fixed 6-value enum and breaks on anything else.
    assert compute_listing_freshness(L(status='draft'), None, NOW) == 'not_published'

# ── Naive datetimes: mirror what psycopg2 returns from TIMESTAMP (no tz) columns.
# The caller passes an aware `now`; the helper must coerce before comparing, else
# `expires_at < now` raises TypeError: can't compare offset-naive and offset-aware.
NAIVE_NOW = datetime(2026, 9, 15, 12, 0)  # no tzinfo
def NL(**kw):
    base = {'external_listing_id': 'gid://1', 'status': 'published',
            'last_sync': NAIVE_NOW - timedelta(hours=1), 'expires_at': None}
    base.update(kw); return base

def test_naive_past_expiry_is_expired():
    assert compute_listing_freshness(
        NL(expires_at=NAIVE_NOW - timedelta(days=1)), None, NOW) == 'expired'

def test_naive_edited_after_last_sync_is_stale():
    assert compute_listing_freshness(NL(), NAIVE_NOW - timedelta(minutes=1), NOW) == 'stale'

def test_naive_synced_after_edit_is_up_to_date():
    assert compute_listing_freshness(NL(), NAIVE_NOW - timedelta(hours=2), NOW) == 'up_to_date'
