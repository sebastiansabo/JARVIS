import core.connectors.connecteam.services.leave_schedule as ls


def test_default_when_no_sincron(monkeypatch):
    monkeypatch.setattr(ls, '_fetch_company_schedules', lambda uid, d: [])
    out = ls.get_leave_schedule(1, '2026-08-18')
    assert out['schedule_start'] == '07:00' and out['schedule_end'] == '18:00'
    assert out['day_cap_hours'] == 8.0 and out['lunch_break_minutes'] == 60
    assert out['source'] == 'default' and out['companies'] == []


def test_sincron_uses_real_company_window(monkeypatch):
    # The selectable window now follows the company's real program (08:00–17:00),
    # the cap is the norma (8h, net of lunch), and the lunch is per-employee.
    from datetime import time
    monkeypatch.setattr(ls, '_fetch_company_schedules', lambda uid, d: [{
        'company_name': 'AUTOWORLD S.R.L.', 'norma_lucru': 8,
        'schedule_start': time(8, 0), 'schedule_end': time(17, 0),
        'lunch_break_minutes': 60}])
    out = ls.get_leave_schedule(1, '2026-08-18')
    assert out['schedule_start'] == '08:00' and out['schedule_end'] == '17:00'
    assert out['day_cap_hours'] == 8.0 and out['source'] == 'sincron'
    assert out['selected_company'] == 'AUTOWORLD S.R.L.'
    assert len(out['companies']) == 1


def test_part_time_cap_and_window(monkeypatch):
    from datetime import time
    monkeypatch.setattr(ls, '_fetch_company_schedules', lambda uid, d: [{
        'company_name': 'X', 'norma_lucru': 4,
        'schedule_start': time(9, 0), 'schedule_end': time(13, 0),
        'lunch_break_minutes': 0}])
    out = ls.get_leave_schedule(1, '2026-08-18')
    assert out['day_cap_hours'] == 4.0
    assert out['schedule_start'] == '09:00' and out['schedule_end'] == '13:00'


def test_multi_company_selects_primary_then_by_name(monkeypatch):
    from datetime import time
    rows = [
        {'company_name': 'PRIMARY', 'norma_lucru': 8,
         'schedule_start': time(8, 0), 'schedule_end': time(17, 0), 'lunch_break_minutes': 60},
        {'company_name': 'SECOND', 'norma_lucru': 1,
         'schedule_start': time(17, 0), 'schedule_end': time(18, 0), 'lunch_break_minutes': 0},
    ]
    monkeypatch.setattr(ls, '_fetch_company_schedules', lambda uid, d: rows)
    # Default → primary (highest norma)
    out = ls.get_leave_schedule(1, '2026-08-18')
    assert out['selected_company'] == 'PRIMARY' and out['day_cap_hours'] == 8.0
    assert len(out['companies']) == 2
    # Explicit selection → that company's window/cap/lunch
    out2 = ls.get_leave_schedule(1, '2026-08-18', company_name='SECOND')
    assert out2['selected_company'] == 'SECOND'
    assert out2['schedule_start'] == '17:00' and out2['schedule_end'] == '18:00'
    assert out2['day_cap_hours'] == 1.0 and out2['lunch_break_minutes'] == 0


def test_compute_return():
    assert ls.compute_return('09:00', 1.5) == '10:30'
    assert ls.compute_return('09:30', 0.5) == '10:00'


def test_full_day_return_adds_lunch():
    sched = {'day_cap_hours': 8.0, 'lunch_break_minutes': 60}
    assert ls._full_day_lunch(8.0, sched) == 60
    assert ls.compute_return('08:00', 8.0, ls._full_day_lunch(8.0, sched)) == '17:00'


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
