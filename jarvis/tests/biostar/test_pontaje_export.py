import datetime as dt
from core.connectors.biostar.services import pontaje_export_service as pes

def _dt(day, hhmm):
    h, m = map(int, hhmm.split(':'))
    return dt.datetime(2026, 7, 1, h, m) if day == 1 else dt.datetime(2026, 7, day, h, m)

BASE = dict(jarvis_user_id=10, biostar_user_id='b1', name='Dan P.', group='AW ONE',
            company_id=5, company='AW ONE', static_start='08:00', static_end='17:00',
            first_punch=None, last_punch=None, total_punches=0, duration_seconds=None,
            adjusted_first_punch=None, adjusted_last_punch=None)

def row(**kw):
    r = dict(BASE); r.update(kw); r['day'] = dt.date(2026, 7, kw.get('_d', 1)); return r

def test_present_uses_contract_lunch_and_net_duration():
    pr = [row(first_punch=_dt(1,'08:03'), last_punch=_dt(1,'17:12'), total_punches=4,
              duration_seconds=9*3600+9*60)]
    sched = {(10, 5, dt.date(2026,7,1)): {'schedule_start':'09:00','schedule_end':'12:00','lunch_break_minutes':3}}
    out = pes.build_rows(pr, sched, {})
    r = out[0]
    assert r[pes.HEADERS.index('Checked In')] == '08:03'
    assert r[pes.HEADERS.index('Lunch')] == '3 min'
    assert r[pes.HEADERS.index('Schedule')] == '09:00–12:00'
    # net = 9:09 gross - 3 min = 9:06
    assert r[pes.HEADERS.index('Duration')] == '9:06'
    assert r[pes.HEADERS.index('Status')] == 'Present'

def test_adjusted_overrides_raw():
    pr = [row(first_punch=_dt(1,'09:14'), last_punch=_dt(1,'17:22'), total_punches=3,
              duration_seconds=8*3600,
              adjusted_first_punch=_dt(1,'09:00'), adjusted_last_punch=_dt(1,'17:30'))]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'09:00','schedule_end':'18:00','lunch_break_minutes':30}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Checked In')] == '09:00'   # adjusted
    assert r[pes.HEADERS.index('Actual In')] == '09:14'    # raw

def test_single_punch_is_not_exited():
    pr = [row(first_punch=_dt(1,'08:12'), last_punch=_dt(1,'08:12'), total_punches=1)]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':30}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Checked Out')] == ''
    assert r[pes.HEADERS.index('Duration')] == ''
    assert r[pes.HEADERS.index('Status')] == 'Not exited'

def test_absent_on_holiday_shows_code_and_absent():
    pr = [row()]  # no punches
    codes = {(10, dt.date(2026,7,1)): 'CO'}
    r = pes.build_rows(pr, {}, codes)[0]
    assert r[pes.HEADERS.index('Sincron')] == 'CO'
    assert r[pes.HEADERS.index('Status')] == 'Absent'
    assert r[pes.HEADERS.index('Punches')] == '0'

def test_null_lunch_stays_blank_and_duration_deducts_zero():
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2,
              duration_seconds=8*3600)]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':None}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Lunch')] == ''      # null -> blank
    assert r[pes.HEADERS.index('Duration')] == '8:00'  # deducts 0

def test_work_code_os_is_present_not_leave():
    pr = [row(first_punch=_dt(1,'07:58'), last_punch=_dt(1,'18:20'), total_punches=5,
              duration_seconds=10*3600)]
    codes = {(10, dt.date(2026,7,1)): 'OS'}
    r = pes.build_rows(pr, {}, codes)[0]
    assert r[pes.HEADERS.index('Sincron')] == 'OS'
    assert r[pes.HEADERS.index('Status')] == 'Present'

def test_weekday_and_zero_lunch():
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2, duration_seconds=8*3600)]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':0}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Weekday')] == 'Wed'
    assert r[pes.HEADERS.index('Lunch')] == '0 min'
    assert r[pes.HEADERS.index('Duration')] == '8:00'

def test_months_between_spans_year_boundary():
    from core.connectors.biostar.services import pontaje_export_service as pes
    assert pes._months_between('2025-12-20', '2026-02-03') == [(2025,12),(2026,1),(2026,2)]

def test_build_rows_accepts_iso_string_inputs_present():
    # Real runtime shape: database.dict_from_row converts date/datetime -> ISO strings.
    r = dict(BASE)
    r.update(
        day='2026-07-01',
        first_punch='2026-07-01T08:03:00',
        last_punch='2026-07-01T17:12:00',
        total_punches=4,
        duration_seconds=9 * 3600 + 9 * 60,
    )
    sched = {(10, 5, '2026-07-01'): {'schedule_start': '09:00', 'schedule_end': '12:00',
                                     'lunch_break_minutes': 30}}
    out = pes.build_rows([r], sched, {})
    row_out = out[0]
    assert row_out[pes.HEADERS.index('Date')] == '2026-07-01'
    assert row_out[pes.HEADERS.index('Weekday')] == 'Wed'
    assert row_out[pes.HEADERS.index('Checked In')] == '08:03'
    assert row_out[pes.HEADERS.index('Duration')] == '8:39'

def test_build_rows_accepts_iso_string_inputs_adjusted():
    r = dict(BASE)
    r.update(
        day='2026-07-01',
        first_punch='2026-07-01T09:14:00',
        last_punch='2026-07-01T17:22:00',
        total_punches=3,
        duration_seconds=8 * 3600,
        adjusted_first_punch='2026-07-01T09:00:00',
        adjusted_last_punch='2026-07-01T17:30:00',
    )
    sched = {(10, 5, '2026-07-01'): {'schedule_start': '09:00', 'schedule_end': '18:00',
                                     'lunch_break_minutes': 30}}
    row_out = pes.build_rows([r], sched, {})[0]
    assert row_out[pes.HEADERS.index('Checked In')] == '09:00'   # adjusted
    assert row_out[pes.HEADERS.index('Actual In')] == '09:14'    # raw
    # gross = 8:30 (adjusted span) - 30 min lunch = 8:00
    assert row_out[pes.HEADERS.index('Duration')] == '8:00'
