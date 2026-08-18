import core.connectors.connecteam.services.leave_schedule as ls


def test_default_when_no_sincron(monkeypatch):
    monkeypatch.setattr(ls, '_fetch_day_schedule', lambda uid, d: None)
    out = ls.get_leave_schedule(1, '2026-08-18')
    assert out == {'schedule_start': '09:00', 'schedule_end': '18:00',
                   'day_cap_hours': 7.0, 'lunch_break_minutes': 60, 'source': 'default'}


def test_sincron_cap_is_norma_minus_lunch_capped_7(monkeypatch):
    from datetime import time
    monkeypatch.setattr(ls, '_fetch_day_schedule', lambda uid, d: {
        'schedule_start': time(9, 0), 'schedule_end': time(17, 30),
        'norma_lucru': 8, 'lunch_break_minutes': 60})
    out = ls.get_leave_schedule(1, '2026-08-18')
    assert out['schedule_start'] == '09:00' and out['schedule_end'] == '17:30'
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
