"""Regression: a GROUP test-drive confirm must fire ONE aggregated staff
notification, not one push per slot.

Before the fix, `_confirm_group` called `_confirm_pending` per booking, and each
`_confirm_pending` sent its own `_notify_staff` push — so confirming an N-slot
group pushed N identical "Programare test drive nouă" alerts to the same staff.
The fix passes `notify=False` for each slot and sends a single
`_notify_staff_group` summary afterwards.

Unit-level: the service is built with `__new__` (no DB-touching __init__) and
its repo / confirm internals are stubbed, so this exercises the orchestration
logic only — no database, no real push.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from marketing.services.td_booking_service import TdBookingService


def _svc():
    return TdBookingService.__new__(TdBookingService)


def _booking(bid, status='pending_confirm'):
    return {
        'id': bid, 'status': status, 'page_id': 7,
        'car_id': 100 + bid, 'slot_id': 200 + bid,
        'customer_name': 'Ana Pop', 'customer_phone_e164': '+40721000010',
        'expires_at': datetime.now(timezone.utc) + timedelta(hours=1),
    }


def test_group_confirm_sends_one_aggregated_staff_notification():
    svc = _svc()
    svc.repo = MagicMock()
    svc.repo.get_group.return_value = [_booking(1), _booking(2), _booking(3)]
    svc.repo.get_page.return_value = {'id': 7, 'notify_user_ids': [9]}
    svc._find_or_create_crm_client = MagicMock(return_value=55)
    svc._confirm_pending = MagicMock(
        return_value={'fp_id': 1, 'advisor_id': 42, 'warning': None})
    svc._notify_staff_group = MagicMock()
    svc._notify_staff = MagicMock()  # per-slot path must stay silent for groups

    res = svc._confirm_group('gid-xyz')

    assert res.success is True
    assert res.data['confirmed'] == 3
    # every slot confirmed with its own push suppressed
    assert svc._confirm_pending.call_count == 3
    assert all(c.kwargs.get('notify') is False
               for c in svc._confirm_pending.call_args_list)
    # exactly ONE aggregated staff notification, reporting all 3 newly-confirmed
    svc._notify_staff_group.assert_called_once()
    args = svc._notify_staff_group.call_args.args
    assert args[3] == 3  # newly-confirmed count
    svc._notify_staff.assert_not_called()


def test_already_confirmed_group_members_do_not_re_notify():
    """Re-clicking a group link where some slots are already confirmed must not
    re-notify for those (they were notified on first confirm)."""
    svc = _svc()
    svc.repo = MagicMock()
    svc.repo.get_group.return_value = [
        _booking(1, status='confirmed'),
        _booking(2, status='confirmed'),
    ]
    svc._find_or_create_crm_client = MagicMock(return_value=55)
    svc._confirm_pending = MagicMock()
    svc._notify_staff_group = MagicMock()

    res = svc._confirm_group('gid-xyz')

    assert res.success is True
    assert res.data['confirmed'] == 2
    svc._confirm_pending.assert_not_called()      # nothing new to confirm
    svc._notify_staff_group.assert_not_called()   # and therefore nothing to notify


def test_notify_staff_group_single_push_union_recipients(monkeypatch):
    svc = _svc()
    sent = MagicMock()
    monkeypatch.setattr('core.notifications.notify.notify_with_push', sent)

    svc._notify_staff_group(
        {'notify_user_ids': [9, 10]}, _booking(1), {42, 9}, 3, warning=False)

    sent.assert_called_once()
    args, kwargs = sent.call_args
    assert set(args[0]) == {9, 10, 42}            # page notify list ∪ advisors, deduped
    assert args[1] == 'Programare test drive nouă'
    assert '3 mașini' in kwargs['message']
    assert kwargs['category'] == 'test_drive'


def test_notify_staff_group_singular_unit_and_warning(monkeypatch):
    svc = _svc()
    sent = MagicMock()
    monkeypatch.setattr('core.notifications.notify.notify_with_push', sent)

    svc._notify_staff_group({'notify_user_ids': [9]}, _booking(1), set(), 1, warning=True)

    kwargs = sent.call_args.kwargs
    assert '1 mașină' in kwargs['message']        # singular grammar
    assert 'suprapunere' in kwargs['message']     # soft-conflict warning carried through
