"""Tests for the BNR FX-feed health monitor (tasks/bnr_monitor.py)."""
from unittest.mock import ANY, MagicMock, patch

from tasks import bnr_monitor


def _fake_db(cooldown_hit=False, l0_ids=(1, 2), emails=("boss@aw.ro",)):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,) if cooldown_hit else None
    cursor.fetchall.side_effect = [
        [{'user_id': i} for i in l0_ids],   # SELECT DISTINCT user_id FROM company_responsables
        [{'email': e} for e in emails],     # SELECT email FROM users
    ]
    return conn, cursor


def _patches(fn):
    # Targets are applied in list order; the FIRST applied is closest to the
    # function and maps to the FIRST injected mock arg — so this order mirrors
    # the test signature (get_rate, clear_cache, notify, send_email, get_db,
    # get_cursor, release_db).
    for target in (
        'core.services.currency_converter.get_exchange_rate',
        'core.services.currency_converter.clear_cache',
        'core.notifications.notify.notify_with_push',
        'core.services.notification_service.send_email',
        'database.get_db',
        'database.get_cursor',
        'database.release_db',
    ):
        fn = patch(target)(fn)
    return fn


@_patches
def test_no_alert_and_no_db_when_rate_present(
        get_rate, clear_cache, notify, send_email, get_db, get_cursor, release_db):
    """Healthy feed → return early, never touch the DB or alert."""
    get_rate.return_value = 5.2554
    bnr_monitor.check_bnr_feed()
    clear_cache.assert_not_called()   # no retry needed
    notify.assert_not_called()
    send_email.assert_not_called()
    get_db.assert_not_called()


@_patches
def test_retries_once_before_alerting(
        get_rate, clear_cache, notify, send_email, get_db, get_cursor, release_db):
    """A first None triggers a cache-clear + one retry; a good retry suppresses the alert."""
    get_rate.side_effect = [None, 5.2554]   # first fails, retry succeeds
    bnr_monitor.check_bnr_feed()
    clear_cache.assert_called_once()
    assert get_rate.call_count == 2
    notify.assert_not_called()
    get_db.assert_not_called()


@_patches
def test_alerts_l0_when_feed_down(
        get_rate, clear_cache, notify, send_email, get_db, get_cursor, release_db):
    """Both attempts fail → alert L0, email them, and upsert the cooldown row."""
    get_rate.return_value = None
    conn, cursor = _fake_db(cooldown_hit=False, l0_ids=(1, 7), emails=("boss@aw.ro",))
    get_db.return_value = conn
    get_cursor.return_value = cursor

    bnr_monitor.check_bnr_feed()

    clear_cache.assert_called_once()
    assert get_rate.call_count == 2
    notify.assert_called_once()
    assert notify.call_args.args[0] == [1, 7]                    # L0 recipients
    assert notify.call_args.kwargs['category'] == 'bnr_feed_down'
    send_email.assert_called_once()
    assert send_email.call_args.args[0] == 'boss@aw.ro'
    assert send_email.call_args.kwargs.get('text_body')
    conn.commit.assert_called_once()
    # cooldown row upserted
    assert any(
        'smart_notification_state' in str(c[0][0]) and 'INSERT' in str(c[0][0]).upper()
        for c in cursor.execute.call_args_list)


@_patches
def test_respects_cooldown(
        get_rate, clear_cache, notify, send_email, get_db, get_cursor, release_db):
    """Feed down but within the 20h cooldown → no alert, no commit."""
    get_rate.return_value = None
    conn, cursor = _fake_db(cooldown_hit=True)
    get_db.return_value = conn
    get_cursor.return_value = cursor

    bnr_monitor.check_bnr_feed()

    notify.assert_not_called()
    send_email.assert_not_called()
    conn.commit.assert_not_called()
