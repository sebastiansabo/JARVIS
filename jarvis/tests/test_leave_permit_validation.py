from forms.services.form_service import FormService

FULL = {
    'f_bi_leave_date': '2026-07-27',
    'f_bi_start_time': '09:00',
    'f_bi_duration_hours': '1.5',
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


def test_required_fields_now_include_duration():
    missing = FormService._leave_permit_missing_fields({
        'f_bi_leave_date': '2026-08-18', 'f_bi_start_time': '09:00', 'f_bi_reason': 'Personal'})
    assert 'f_bi_duration_hours' in missing


def test_full_set_no_missing():
    missing = FormService._leave_permit_missing_fields({
        'f_bi_leave_date': '2026-08-18', 'f_bi_start_time': '09:00',
        'f_bi_duration_hours': '1.5', 'f_bi_reason': 'Personal'})
    assert missing == []


def test_leave_precheck_rejects_missing_consent():
    err = FormService._leave_permit_precheck(
        {'f_bi_terms_accepted': False, 'signature_image': 'x'})
    assert err and 'responsabil' in err.lower()


def test_leave_precheck_rejects_missing_signature():
    err = FormService._leave_permit_precheck(
        {'f_bi_terms_accepted': True, 'signature_image': ''})
    assert err and 'semn' in err.lower()


def test_leave_precheck_ok():
    assert FormService._leave_permit_precheck(
        {'f_bi_terms_accepted': True, 'signature_image': 'data:image/png;base64,AAAA'}) is None


def test_is_new_leave_contract_true_for_new_body():
    # Current web body: has f_bi_duration_hours.
    assert FormService._is_new_leave_contract(FULL) is True


def test_is_new_leave_contract_false_for_legacy_body():
    # Live mobile body: leave_date/start_time/end_time/reason, no duration.
    legacy = {
        'f_bi_leave_date': '2026-08-18', 'f_bi_start_time': '09:00',
        'f_bi_end_time': '11:00', 'f_bi_reason': 'Personal',
    }
    assert FormService._is_new_leave_contract(legacy) is False


def test_new_contract_missing_fields_unchanged():
    # NEW required set still flags f_bi_duration_hours when absent.
    missing = FormService._leave_permit_missing_fields({
        'f_bi_leave_date': '2026-08-18', 'f_bi_start_time': '09:00', 'f_bi_reason': 'Personal'})
    assert 'f_bi_duration_hours' in missing


def test_reason_opts_from_schema_extracts_options():
    schema = [
        {'id': 'f_bi_start_time'},
        {'id': 'f_bi_reason', 'options': ['Personal', 'Pauza de masa']},
    ]
    assert FormService._reason_opts_from_schema(schema) == ['Personal', 'Pauza de masa']


def test_reason_opts_from_schema_parses_json_string():
    import json
    schema = json.dumps([{'id': 'f_bi_reason', 'options': ['A', 'B']}])
    assert FormService._reason_opts_from_schema(schema) == ['A', 'B']


def test_reason_opts_from_schema_empty_when_missing_or_blank():
    assert FormService._reason_opts_from_schema([]) == []
    assert FormService._reason_opts_from_schema(None) == []
    assert FormService._reason_opts_from_schema(
        [{'id': 'f_bi_reason', 'options': ['', '  ']}]) == []


def test_leave_form_config_from_schema():
    schema = [
        {'id': 'f_bi_leave_date', 'label': 'Data'},
        {'id': 'f_bi_reason', 'label': 'Motivul', 'options': ['Personal', 'Pauza de masa']},
        {'id': 'f_bi_notes', 'label': 'Detalii', 'placeholder': 'scrie...'},
        {'id': 'f_bi_terms', 'label': 'Sunt de acord \U0001f512'},
    ]  # no f_bi_destination / f_bi_second_approver
    cfg = FormService._leave_form_config_from_schema(schema)
    assert cfg['reasons'] == ['Personal', 'Pauza de masa']
    assert cfg['labels']['f_bi_leave_date'] == 'Data'
    assert cfg['placeholders']['f_bi_notes'] == 'scrie...'
    assert cfg['visible'] == {'f_bi_destination': False, 'f_bi_notes': True, 'f_bi_second_approver': False}
    assert cfg['terms_text'] == 'Sunt de acord \U0001f512'


def test_leave_form_config_defaults_when_empty():
    cfg = FormService._leave_form_config_from_schema([])
    assert cfg['reasons'] == ['Personal', 'Medical', 'Familial', 'Oficial', 'Altul']
    assert cfg['labels'] == {}
    assert cfg['placeholders'] == {}
    assert cfg['visible'] == {'f_bi_destination': False, 'f_bi_notes': False, 'f_bi_second_approver': False}
    assert cfg['terms_text'] == FormService.LEAVE_TERMS_TEXT
