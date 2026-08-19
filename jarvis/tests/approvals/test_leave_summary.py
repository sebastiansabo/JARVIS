"""Pure formatter that turns a loaded leave submission row into the summary shown
in the approver email + in-app detail. Only Bilet de Învoire submissions produce a
summary; anything else returns None so callers fall back to the generic rendering."""
from core.approvals.handlers.leave_summary import format_leave_summary


def _row(**answers):
    return {
        'slug': 'bilet-de-invoire',
        'requester_name': 'Seba',
        'answers': answers,
    }


def test_full_leave_row_maps_all_fields():
    row = _row(f_bi_leave_date='2026-08-20', f_bi_start_time='07:00',
               f_bi_end_time='10:00', f_bi_hours=3, f_bi_reason='Personal',
               f_bi_notes='la medic')
    assert format_leave_summary(row) == {
        'requester_name': 'Seba', 'leave_date': '2026-08-20',
        'start': '07:00', 'end': '10:00', 'hours': 3,
        'reason': 'Personal', 'notes': 'la medic',
    }


def test_non_leave_slug_returns_none():
    row = {'slug': 'test-drive', 'requester_name': 'X', 'answers': {}}
    assert format_leave_summary(row) is None


def test_missing_row_returns_none():
    assert format_leave_summary(None) is None


def test_missing_answer_keys_default_to_blank_and_dont_crash():
    s = format_leave_summary(_row(f_bi_start_time='09:00'))
    assert s['start'] == '09:00'
    assert s['reason'] == '' and s['notes'] == '' and s['end'] == ''
    assert s['requester_name'] == 'Seba'
