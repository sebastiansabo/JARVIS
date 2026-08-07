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
    assert r[pes.HEADERS.index('Checked In')] == ''      # no adjustment -> blank
    assert r[pes.HEADERS.index('Actual In')] == '08:03'  # raw punch
    assert r[pes.HEADERS.index('Lunch')] == '3 min'
    assert r[pes.HEADERS.index('Schedule')] == '09:00–12:00'
    # net = 9:09 gross - 3 min = 9:06
    assert r[pes.HEADERS.index('Duration')] == '9:06'
    assert r[pes.HEADERS.index('Actual Status')] == 'Present'
    assert r[pes.HEADERS.index('Status')] == 'Present'

def test_adjusted_overrides_raw():
    pr = [row(first_punch=_dt(1,'09:14'), last_punch=_dt(1,'17:22'), total_punches=3,
              duration_seconds=8*3600,
              adjusted_first_punch=_dt(1,'09:00'), adjusted_last_punch=_dt(1,'17:30'))]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'09:00','schedule_end':'18:00','lunch_break_minutes':30}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Checked In')] == '09:00'   # adjusted
    assert r[pes.HEADERS.index('Actual In')] == '09:14'    # raw

def test_adjustment_only_day_actual_absent_adjusted_present():
    # Manager entered an adjustment for a day with no physical punch.
    pr = [row(first_punch=None, last_punch=None, total_punches=0,
              adjusted_first_punch=_dt(1,'09:00'), adjusted_last_punch=_dt(1,'17:00'))]
    r = pes.build_rows(pr, {}, {})[0]
    assert r[pes.HEADERS.index('Checked In')] == '09:00'   # adjustment shown
    assert r[pes.HEADERS.index('Checked Out')] == '17:00'
    assert r[pes.HEADERS.index('Actual In')] == ''         # no raw punch
    assert r[pes.HEADERS.index('Actual Status')] == 'Absent'    # physically absent
    assert r[pes.HEADERS.index('Status')] == 'Present'  # corrected present

def test_checked_columns_blank_without_adjustment():
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2,
              duration_seconds=8*3600)]
    r = pes.build_rows(pr, {}, {})[0]
    assert r[pes.HEADERS.index('Checked In')] == ''
    assert r[pes.HEADERS.index('Checked Out')] == ''
    assert r[pes.HEADERS.index('Actual In')] == '08:00'
    assert r[pes.HEADERS.index('Actual Out')] == '16:00'

def test_single_punch_is_not_exited():
    pr = [row(first_punch=_dt(1,'08:12'), last_punch=_dt(1,'08:12'), total_punches=1)]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':30}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Checked Out')] == ''
    assert r[pes.HEADERS.index('Duration')] == ''
    assert r[pes.HEADERS.index('Actual Status')] == 'Not exited'
    assert r[pes.HEADERS.index('Status')] == 'Not exited'

def test_absent_on_holiday_shows_code_and_absent():
    pr = [row()]  # no punches
    codes = {(10, 5, dt.date(2026,7,1)): 'CO'}
    r = pes.build_rows(pr, {}, codes)[0]
    assert r[pes.HEADERS.index('Sincron')] == 'CO'
    assert r[pes.HEADERS.index('Actual Status')] == 'Absent'
    assert r[pes.HEADERS.index('Status')] == 'Absent'
    assert r[pes.HEADERS.index('Punches')] == '0'

def test_weekend_no_punch_marks_weekend():
    # 2026-07-04 is a Saturday.
    pr = [row(_d=4)]  # no punches
    r = pes.build_rows(pr, {}, {})[0]
    assert r[pes.HEADERS.index('Weekday')] == 'Sat'
    assert r[pes.HEADERS.index('Actual Status')] == 'Weekend'
    assert r[pes.HEADERS.index('Status')] == 'Weekend'

def test_weekend_with_punch_stays_present():
    pr = [row(_d=4, first_punch=_dt(4,'09:00'), last_punch=_dt(4,'13:00'),
              total_punches=2, duration_seconds=4*3600)]
    r = pes.build_rows(pr, {}, {})[0]
    assert r[pes.HEADERS.index('Actual Status')] == 'Present'
    assert r[pes.HEADERS.index('Status')] == 'Present'

def test_holiday_no_punch_marks_holiday():
    pr = [row()]  # 2026-07-01 (Wed), no punches
    holidays = {'2026-07-01'}
    r = pes.build_rows(pr, {}, {}, holidays)[0]
    assert r[pes.HEADERS.index('Actual Status')] == 'Holiday'
    assert r[pes.HEADERS.index('Status')] == 'Holiday'

def test_holiday_takes_precedence_over_weekend():
    # Saturday that is also a public holiday -> Holiday wins.
    pr = [row(_d=4)]
    holidays = {'2026-07-04'}
    r = pes.build_rows(pr, {}, {}, holidays)[0]
    assert r[pes.HEADERS.index('Actual Status')] == 'Holiday'
    assert r[pes.HEADERS.index('Status')] == 'Holiday'

def test_permit_no_punch_marks_permit():
    pr = [row()]  # 2026-07-01 (Wed), no punches
    permits = {(10, '2026-07-01'): {'hours': 8.0, 'sources': ['Connecteam']}}
    r = pes.build_rows(pr, {}, {}, None, permits)[0]
    assert r[pes.HEADERS.index('Permit')] == '8h (Connecteam)'
    assert r[pes.HEADERS.index('Actual Status')] == 'Permit'
    assert r[pes.HEADERS.index('Status')] == 'Permit'

def test_permit_with_punch_stays_present_but_shows_permit():
    pr = [row(first_punch=_dt(1,'09:00'), last_punch=_dt(1,'15:00'),
              total_punches=2, duration_seconds=6*3600)]
    permits = {(10, '2026-07-01'): {'hours': 2.5, 'sources': ['JARVIS']}}
    r = pes.build_rows(pr, {}, {}, None, permits)[0]
    assert r[pes.HEADERS.index('Permit')] == '2.5h (JARVIS)'
    assert r[pes.HEADERS.index('Actual Status')] == 'Present'
    assert r[pes.HEADERS.index('Status')] == 'Present'

def test_permit_multiple_sources_formatting():
    pr = [row()]
    permits = {(10, '2026-07-01'): {'hours': 3.0, 'sources': ['Connecteam', 'JARVIS']}}
    r = pes.build_rows(pr, {}, {}, None, permits)[0]
    assert r[pes.HEADERS.index('Permit')] == '3h (Connecteam, JARVIS)'

def test_holiday_and_weekend_outrank_permit():
    permits = {(10, '2026-07-01'): {'hours': 8.0, 'sources': ['Connecteam']},
               (10, '2026-07-04'): {'hours': 8.0, 'sources': ['Connecteam']}}
    # Holiday (Wed 2026-07-01) beats permit
    r1 = pes.build_rows([row()], {}, {}, {'2026-07-01'}, permits)[0]
    assert r1[pes.HEADERS.index('Actual Status')] == 'Holiday'
    # Weekend (Sat 2026-07-04) beats permit
    r2 = pes.build_rows([row(_d=4)], {}, {}, None, permits)[0]
    assert r2[pes.HEADERS.index('Actual Status')] == 'Weekend'

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
    codes = {(10, 5, dt.date(2026,7,1)): 'OS'}
    r = pes.build_rows(pr, {}, codes)[0]
    assert r[pes.HEADERS.index('Sincron')] == 'OS'
    assert r[pes.HEADERS.index('Actual Status')] == 'Present'
    assert r[pes.HEADERS.index('Status')] == 'Present'

def test_weekday_and_zero_lunch():
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2, duration_seconds=8*3600)]
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':0}}
    r = pes.build_rows(pr, sched, {})[0]
    assert r[pes.HEADERS.index('Weekday')] == 'Wed'
    assert r[pes.HEADERS.index('Lunch')] == '0 min'
    assert r[pes.HEADERS.index('Duration')] == '8:00'

def test_excluded_contract_shows_marker_not_biostar_fallback():
    # Contract flagged exclude_from_pontaje: no sched entry, but (uid, company) is
    # in excluded_keys -> Romanian marker instead of BioStar static 08:00-17:00.
    pr = [row(first_punch=_dt(1,'17:00'), last_punch=_dt(1,'18:00'), total_punches=2,
              duration_seconds=3600)]
    r = pes.build_rows(pr, {}, {}, excluded_keys={(10, 5)})[0]
    assert r[pes.HEADERS.index('Schedule')] == 'Exclus din pontaj'

def test_no_sincron_mapping_shows_distinct_marker():
    # No sched entry and not excluded -> "no Sincron schedule" marker (no BioStar fallback).
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2,
              duration_seconds=8*3600)]
    r = pes.build_rows(pr, {}, {})[0]
    assert r[pes.HEADERS.index('Schedule')] == 'Fără orar Sincron'

def test_real_schedule_beats_excluded_marker():
    # A real Sincron schedule always wins, even if the pair is also in excluded_keys.
    pr = [row()]
    sched = {(10, 5, dt.date(2026,7,1)): {'schedule_start':'09:00','schedule_end':'17:00','lunch_break_minutes':60}}
    r = pes.build_rows(pr, sched, {}, excluded_keys={(10, 5)})[0]
    assert r[pes.HEADERS.index('Schedule')] == '09:00–17:00'

# ── Sincron leave code overrides punch-driven "Present" (official Status) ──

def test_leave_code_overrides_present_status_and_blanks_duration():
    # Employee on CO (annual leave) all day but with a stray badge punch: the
    # official Status must reflect the leave, not "Present", and worked Duration
    # must be blank — while the raw punch still shows in the Actual columns.
    pr = [row(first_punch=_dt(1,'06:57'), last_punch=_dt(1,'08:05'), total_punches=2,
              duration_seconds=3600)]
    codes = {(10, 5, dt.date(2026,7,1)): 'CO'}
    r = pes.build_rows(pr, {}, codes, leave_codes={'CO'})[0]
    assert r[pes.HEADERS.index('Status')] == 'CO'            # official = on leave
    assert r[pes.HEADERS.index('Duration')] == ''            # no worked hours on leave
    assert r[pes.HEADERS.index('Actual Status')] == 'Present'  # raw badge preserved
    assert r[pes.HEADERS.index('Actual In')] == '06:57'      # raw punch preserved
    assert r[pes.HEADERS.index('Sincron')] == 'CO'

def test_leave_code_shows_as_status_without_punch():
    # No punch + leave code -> Status shows the code (not the generic 'Absent').
    pr = [row()]  # 2026-07-01 (Wed), no punches
    codes = {(10, 5, dt.date(2026,7,1)): 'CM'}
    r = pes.build_rows(pr, {}, codes, leave_codes={'CM'})[0]
    assert r[pes.HEADERS.index('Status')] == 'CM'
    assert r[pes.HEADERS.index('Actual Status')] == 'Absent'  # physically absent

def test_work_code_not_in_leave_set_stays_present():
    # DLG (delegation) is working off-site, not leave -> Present + Duration kept.
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2,
              duration_seconds=8*3600)]
    codes = {(10, 5, dt.date(2026,7,1)): 'DLG'}
    sched = {(10,5,dt.date(2026,7,1)): {'schedule_start':'08:00','schedule_end':'16:00','lunch_break_minutes':0}}
    r = pes.build_rows(pr, sched, codes, leave_codes={'CO','CM','CMS'})[0]
    assert r[pes.HEADERS.index('Status')] == 'Present'
    assert r[pes.HEADERS.index('Duration')] == '8:00'

def test_no_leave_codes_arg_preserves_present_behaviour():
    # Backward-compat: without leave_codes, a CO code does NOT override Present.
    pr = [row(first_punch=_dt(1,'08:00'), last_punch=_dt(1,'16:00'), total_punches=2,
              duration_seconds=8*3600)]
    codes = {(10, 5, dt.date(2026,7,1)): 'CO'}
    r = pes.build_rows(pr, {}, codes)[0]
    assert r[pes.HEADERS.index('Status')] == 'Present'

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
    assert row_out[pes.HEADERS.index('Checked In')] == ''       # no adjustment -> blank
    assert row_out[pes.HEADERS.index('Actual In')] == '08:03'   # raw punch
    assert row_out[pes.HEADERS.index('Duration')] == '8:39'

def test_build_code_map_first_wins_per_company():
    # First row per (user, company, day) wins (leave prioritized upstream).
    rows = [
        {'mapped_jarvis_user_id': 10, 'company_id': 5, 'day': '2026-07-01', 'short_code': 'CO'},
        {'mapped_jarvis_user_id': 10, 'company_id': 5, 'day': '2026-07-01', 'short_code': 'OZ'},  # must NOT override
        {'mapped_jarvis_user_id': 11, 'company_id': 5, 'day': '2026-07-01', 'short_code': 'OZ'},
    ]
    m = pes._build_code_map(rows)
    assert m[(10, 5, '2026-07-01')] == 'CO'
    assert m[(11, 5, '2026-07-01')] == 'OZ'


def test_build_code_map_keys_by_company():
    # Same user+day, two companies with different codes — kept separate, not collapsed.
    rows = [
        {'mapped_jarvis_user_id': 10, 'company_id': 5, 'day': '2026-07-01', 'short_code': 'CO'},
        {'mapped_jarvis_user_id': 10, 'company_id': 7, 'day': '2026-07-01', 'short_code': 'OZ'},
    ]
    m = pes._build_code_map(rows)
    assert m[(10, 5, '2026-07-01')] == 'CO'
    assert m[(10, 7, '2026-07-01')] == 'OZ'


def test_sincron_code_is_per_company_not_bled():
    # A base-contract CO must NOT bleed onto a secondary contract where OZ was worked.
    pr = [
        row(company_id=5, company='AW ONE'),                 # base: on CO
        row(company_id=7, company='AW TWO',
            first_punch=_dt(1, '08:00'), last_punch=_dt(1, '16:00'),
            total_punches=2, duration_seconds=8*3600),       # secondary: worked
    ]
    codes = {(10, 5, dt.date(2026,7,1)): 'CO',
             (10, 7, dt.date(2026,7,1)): 'OZ'}
    out = pes.build_rows(pr, {}, codes, leave_codes={'CO'})
    base_row = next(r for r in out if r[pes.HEADERS.index('Company')] == 'AW ONE')
    sec_row  = next(r for r in out if r[pes.HEADERS.index('Company')] == 'AW TWO')
    assert base_row[pes.HEADERS.index('Sincron')] == 'CO'
    assert sec_row[pes.HEADERS.index('Sincron')] == 'OZ'      # its own code, not CO
    # and the leave-override only fires on the row whose own code is CO
    assert base_row[pes.HEADERS.index('Status')] == 'CO'
    assert sec_row[pes.HEADERS.index('Status')] == 'Present'

def test_fmt_hm_carries_rounding():
    from core.connectors.biostar.services import pontaje_export_service as pes
    assert pes._fmt_hm(8*3600 + 59*60 + 35) == '9:00'   # was '8:60'
    assert pes._fmt_hm(8*3600 + 39*60) == '8:39'
    assert pes._fmt_hm(8*3600) == '8:00'

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

def test_resolve_export_ids_no_filter_passthrough():
    assert pes.resolve_export_ids(None) is None
    assert pes.resolve_export_ids([1, 2]) == [1, 2]

def test_resolve_export_ids_see_all_honours_request():
    assert pes.resolve_export_ids(None, employee_ids=[2, 9]) == [2, 9]

def test_resolve_export_ids_intersects_with_scope():
    assert pes.resolve_export_ids([1, 2, 3], employee_ids=[2, 9]) == [2]

def test_resolve_export_ids_deny_strips_everything():
    assert pes.resolve_export_ids([-1], employee_ids=[2, 3]) == []

def test_resolve_export_ids_group_path():
    assert pes.resolve_export_ids([1, 2, 3], group_ids=[2, 3, 7]) == [2, 3]

def test_resolve_export_ids_employee_beats_group():
    assert pes.resolve_export_ids([1, 2, 3], group_ids=[3], employee_ids=[2]) == [2]

def test_resolve_export_ids_dedupes_and_casts():
    assert pes.resolve_export_ids(None, employee_ids=['2', 2, '5']) == [2, 5]
