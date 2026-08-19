import core.connectors.connecteam.services.leave_schedule as ls


def test_default_when_no_sincron(monkeypatch):
    monkeypatch.setattr(ls, '_fetch_day_schedule', lambda uid, d: None)
    out = ls.get_leave_schedule(1, '2026-08-18')
    assert out == {'schedule_start': '07:00', 'schedule_end': '18:00',
                   'day_cap_hours': 7.0, 'lunch_break_minutes': 60, 'source': 'default'}


def test_sincron_keeps_fixed_window_only_tightens_cap(monkeypatch):
    # A Sincron contract (e.g. 08:00–17:00) must NOT narrow the selectable
    # window — that stays the fixed 07:00–18:00 program — it only sets the cap.
    from datetime import time
    monkeypatch.setattr(ls, '_fetch_day_schedule', lambda uid, d: {
        'schedule_start': time(8, 0), 'schedule_end': time(17, 0),
        'norma_lucru': 8, 'lunch_break_minutes': 60})
    out = ls.get_leave_schedule(1, '2026-08-18')
    assert out['schedule_start'] == '07:00' and out['schedule_end'] == '18:00'
    assert out['day_cap_hours'] == 7.0 and out['source'] == 'sincron'


def test_part_time_cap(monkeypatch):
    from datetime import time
    monkeypatch.setattr(ls, '_fetch_day_schedule', lambda uid, d: {
        'schedule_start': time(9, 0), 'schedule_end': time(13, 0),
        'norma_lucru': 4, 'lunch_break_minutes': 0})
    assert ls.get_leave_schedule(1, '2026-08-18')['day_cap_hours'] == 4.0


def test_compute_return():
    assert ls.compute_return('09:00', 1.5) == '10:30'
    assert ls.compute_return('09:30', 0.5) == '10:00'


SCHED = {'schedule_start': '09:00', 'schedule_end': '18:00', 'day_cap_hours': 7.0,
         'lunch_break_minutes': 60, 'source': 'sincron'}


def test_validate_ok():
    assert ls.validate_leave('09:00', 1.5, SCHED) is None


def test_validate_rejects_unaligned_start():
    assert ls.validate_leave('09:10', 1.0, SCHED) is not None


def test_validate_rejects_over_cap():
    assert ls.validate_leave('09:00', 7.5, SCHED) is not None


def test_validate_rejects_half_step():
    assert ls.validate_leave('09:00', 0.75, SCHED) is not None


def test_validate_rejects_before_window():
    assert ls.validate_leave('08:00', 1.0, SCHED) is not None


def test_validate_rejects_return_past_window():
    assert ls.validate_leave('17:30', 1.0, SCHED) is not None
