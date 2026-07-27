from forms.services.form_service import FormService

FULL = {
    'f_bi_leave_date': '2026-07-27',
    'f_bi_start_time': '09:00',
    'f_bi_end_time': '10:00',
    'f_bi_reason': 'Personal',
}


def test_full_answers_have_no_missing_fields():
    assert FormService._leave_permit_missing_fields(FULL) == []


def test_missing_reason_flagged():
    a = dict(FULL); a.pop('f_bi_reason')
    assert FormService._leave_permit_missing_fields(a) == ['f_bi_reason']


def test_blank_start_time_flagged():
    a = dict(FULL); a['f_bi_start_time'] = '  '
    assert FormService._leave_permit_missing_fields(a) == ['f_bi_start_time']


def test_empty_answers_flags_all_required():
    assert FormService._leave_permit_missing_fields({}) == list(FormService.LEAVE_REQUIRED_FIELDS)


def test_optional_fields_not_required():
    # second approver + notes are optional — absence does not flag
    assert FormService._leave_permit_missing_fields(FULL) == []
