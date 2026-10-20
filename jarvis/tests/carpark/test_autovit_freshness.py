# jarvis/tests/carpark/test_autovit_freshness.py
from datetime import datetime, timezone, timedelta
from carpark.connectors.autovit.freshness import (
    compute_autovit_freshness, autovit_sweep_stale,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def L(**kw):
    base = {'external_advert_id': 'x', 'status': 'active',
            'last_published_at': NOW - timedelta(hours=1)}
    base.update(kw)
    return base


# ── compute_autovit_freshness ──

def test_no_listing_not_published():
    assert compute_autovit_freshness(None, NOW, NOW) == 'not_published'


def test_no_external_advert_id_not_published():
    assert compute_autovit_freshness(L(external_advert_id=None), NOW, NOW) == 'not_published'


def test_unpaid_is_draft():
    assert compute_autovit_freshness(L(status='unpaid'), NOW, NOW) == 'draft'


def test_active_edited_after_publish_is_stale():
    out = compute_autovit_freshness(L(), NOW, NOW)  # vehicle edited NOW, published 1h ago
    assert out == 'stale'


def test_active_fresh_is_up_to_date():
    out = compute_autovit_freshness(L(), NOW - timedelta(hours=2), NOW)  # vehicle edited before publish
    assert out == 'up_to_date'


def test_moderation():
    assert compute_autovit_freshness(L(status='moderation'), NOW, NOW) == 'moderation'


def test_expired():
    assert compute_autovit_freshness(L(status='expired'), NOW, NOW) == 'expired'


def test_removed_is_inactive():
    assert compute_autovit_freshness(L(status='removed_by_user'), NOW, NOW) == 'inactive'
    assert compute_autovit_freshness(L(status='removed_by_moderator'), NOW, NOW) == 'inactive'
    assert compute_autovit_freshness(L(status='disabled'), NOW, NOW) == 'inactive'
    assert compute_autovit_freshness(L(status='inactive'), NOW, NOW) == 'inactive'


def test_error_wins():
    assert compute_autovit_freshness(L(status='error'), NOW, NOW) == 'error'


def test_active_never_published_is_stale():
    assert compute_autovit_freshness(L(last_published_at=None), NOW, NOW) == 'stale'


def test_unknown_status_is_not_published():
    assert compute_autovit_freshness(L(status='something_else'), NOW, NOW) == 'not_published'


# ── autovit_sweep_stale ──

def test_sweep_stale_true_for_active_edited():
    assert autovit_sweep_stale(L(status='active'), NOW, NOW) is True


def test_sweep_stale_true_for_unpaid_edited():
    assert autovit_sweep_stale(L(status='unpaid'), NOW, NOW) is True


def test_sweep_stale_false_when_fresh():
    out = autovit_sweep_stale(L(status='active'), NOW - timedelta(hours=2), NOW)
    assert out is False


def test_sweep_stale_false_for_inactive():
    assert autovit_sweep_stale(L(status='inactive'), NOW, NOW) is False
