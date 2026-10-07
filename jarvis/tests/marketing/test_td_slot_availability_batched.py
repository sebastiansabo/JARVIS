"""available_slots must compute live availability in BULK, not per slot.

The public event page (`GET /api/td/pages/<slug>`) calls available_slots on every
open. It runs its availability checks (lockout, FP conflicts, pending holds) once
per DISTINCT VIN, not per slot -- a batching lock that keeps the old N x query
fan-out from creeping back. These are pure unit tests: self.repo/self.fp/self.veh are
replaced with test doubles, so no DB is touched. They assert both the RESULT (a
manual lockout HARD-hides the car; an overlapping session/hold keeps the slot with a
soft `overlap` marker; the time-blind whole-car open-session gate is NOT used on the
public read) and that each check runs once per distinct VIN.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime, timezone  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from marketing.services.td_slot_service import TdSlotService  # noqa: E402

# now is before every slot, page lead-time is 0 -> the lead filter never trims.
NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _slot(sid, vin, start, end, car_id=10):
    # Mirror list_open_slots: BaseRepository serializes timestamps to ISO strings.
    return {'id': sid, 'vin': vin, 'car_id': car_id,
            'starts_at': start, 'ends_at': end,
            'mark': 'Audi', 'model': 'A3', 'registration_number': 'B 01 AAA'}


def _conflict(dep, ret):
    return {'id': 1, 'status': 'PLANNED', 'departure_datetime': dep, 'return_datetime': ret}


def _svc(open_slots, *, conflicts=None, lock=None, open_session=None, holds=None,
         min_lead_minutes=0):
    svc = TdSlotService()
    svc.repo = MagicMock()
    svc.fp = MagicMock()
    svc.veh = MagicMock()
    svc.repo.get_page.return_value = {'min_lead_minutes': min_lead_minutes}
    svc.repo.list_open_slots.return_value = list(open_slots)
    svc.repo.pending_hold_windows.return_value = list(holds or [])
    svc.fp.find_conflicts.return_value = list(conflicts or [])
    svc.fp.get_open_session.return_value = open_session
    svc.veh.get_lock_by_vin.return_value = lock
    return svc


def test_all_free_returns_all_slots_and_batches_checks_per_vin():
    slots = [
        _slot(1, 'VIN_A', '2099-10-01T10:00:00+00:00', '2099-10-01T10:30:00+00:00'),
        _slot(2, 'VIN_A', '2099-10-01T10:30:00+00:00', '2099-10-01T11:00:00+00:00'),
        _slot(3, 'VIN_A', '2099-10-01T11:00:00+00:00', '2099-10-01T11:30:00+00:00'),
    ]
    svc = _svc(slots)
    out = svc.available_slots(1, NOW)
    assert [s['id'] for s in out] == [1, 2, 3]                 # all returned
    assert all(s['overlap'] is None for s in out)             # all clear, no warning
    # 3 slots, 1 VIN -> each availability check runs exactly ONCE (not 3x). The public
    # read no longer consults get_open_session (the time-blind whole-car gate is gone).
    assert svc.veh.get_lock_by_vin.call_count == 1
    assert svc.fp.get_open_session.call_count == 0
    assert svc.fp.find_conflicts.call_count == 1
    assert svc.repo.pending_hold_windows.call_count == 1


def test_conflict_annotates_only_the_overlapping_slot():
    slots = [
        _slot(1, 'VIN_A', '2099-10-01T10:00:00+00:00', '2099-10-01T10:30:00+00:00'),
        _slot(2, 'VIN_A', '2099-10-01T10:30:00+00:00', '2099-10-01T11:00:00+00:00'),
    ]
    # A live session 10:40-10:50 overlaps slot 2 only (slot 1 ends 10:30). The
    # overlapping slot is KEPT with a soft 'session' marker, never dropped.
    svc = _svc(slots, conflicts=[_conflict('2099-10-01T10:40:00+00:00',
                                           '2099-10-01T10:50:00+00:00')])
    out = svc.available_slots(1, NOW)
    assert [s['id'] for s in out] == [1, 2]            # both returned
    assert out[0]['overlap'] is None                   # slot 1 clear
    assert out[1]['overlap']['kind'] == 'session'      # slot 2 soft-warned


def test_conflict_overlap_is_inclusive_at_boundary():
    # find_conflicts overlap is inclusive: a session starting exactly at a slot's end
    # still overlaps -> the slot is KEPT but soft-marked (not dropped).
    slots = [_slot(1, 'VIN_A', '2099-10-01T10:00:00+00:00', '2099-10-01T10:30:00+00:00')]
    svc = _svc(slots, conflicts=[_conflict('2099-10-01T10:30:00+00:00',
                                           '2099-10-01T11:00:00+00:00')])
    out = svc.available_slots(1, NOW)
    assert [s['id'] for s in out] == [1]
    assert out[0]['overlap']['kind'] == 'session'


def test_lockout_hides_all_vin_slots_without_conflict_query():
    slots = [
        _slot(1, 'VIN_A', '2099-10-01T10:00:00+00:00', '2099-10-01T10:30:00+00:00'),
        _slot(2, 'VIN_A', '2099-10-01T10:30:00+00:00', '2099-10-01T11:00:00+00:00'),
    ]
    svc = _svc(slots, lock={'locked_out': True})
    assert svc.available_slots(1, NOW) == []
    # a locked car short-circuits: no point querying FP conflicts for its slots
    assert svc.fp.find_conflicts.call_count == 0


def test_open_session_no_longer_hides_slots():
    # The public event page must NOT drop a car just because it is out now: a slot with
    # no time-overlap stays bookable (clear) even with an open session on the VIN.
    slots = [_slot(1, 'VIN_A', '2099-10-01T10:00:00+00:00', '2099-10-01T10:30:00+00:00')]
    svc = _svc(slots, open_session={'id': 99})
    out = svc.available_slots(1, NOW)
    assert [s['id'] for s in out] == [1]
    assert out[0]['overlap'] is None


def test_pending_hold_overlap_is_half_open():
    # has_pending_overlap uses half-open overlap (start < to AND end > frm): a hold
    # starting exactly at a slot's end does NOT block that slot (unlike a conflict).
    slots = [
        _slot(1, 'VIN_A', '2099-10-01T10:00:00+00:00', '2099-10-01T10:30:00+00:00'),
        _slot(2, 'VIN_A', '2099-10-01T10:30:00+00:00', '2099-10-01T11:00:00+00:00'),
    ]
    svc = _svc(slots, holds=[{'starts_at': '2099-10-01T10:30:00+00:00',
                              'ends_at': '2099-10-01T11:00:00+00:00'}])
    out = svc.available_slots(1, NOW)
    assert [s['id'] for s in out] == [1, 2]          # both returned
    assert out[0]['overlap'] is None                 # slot 1 free (boundary touch)
    assert out[1]['overlap']['kind'] == 'hold'       # slot 2 held -> soft-marked


def test_two_vins_query_each_vin_once():
    slots = [
        _slot(1, 'VIN_A', '2099-10-01T10:00:00+00:00', '2099-10-01T10:30:00+00:00'),
        _slot(2, 'VIN_A', '2099-10-01T10:30:00+00:00', '2099-10-01T11:00:00+00:00'),
        _slot(3, 'VIN_B', '2099-10-01T10:00:00+00:00', '2099-10-01T10:30:00+00:00'),
        _slot(4, 'VIN_B', '2099-10-01T10:30:00+00:00', '2099-10-01T11:00:00+00:00'),
    ]
    svc = _svc(slots)
    out = svc.available_slots(1, NOW)
    assert [s['id'] for s in out] == [1, 2, 3, 4]
    assert svc.veh.get_lock_by_vin.call_count == 2      # once per distinct VIN
    assert svc.fp.find_conflicts.call_count == 2
