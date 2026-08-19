import pytest


def test_validate_normalizes_hours_and_end(monkeypatch):
    from forms.services import form_service as fs
    monkeypatch.setattr(fs.FormService, 'get_leave_form_config',
                        lambda self: {'reasons': ['Personal'], 'terms_text': 'T'})
    monkeypatch.setattr(fs, 'get_leave_schedule', lambda uid, d: {'schedule_start': '07:00', 'schedule_end': '18:00', 'day_cap_hours': 7}, raising=False)
    monkeypatch.setattr(fs, 'validate_leave', lambda s, d, sch: None, raising=False)
    monkeypatch.setattr(fs, 'compute_return', lambda s, d: '10:30', raising=False)
    out = fs.FormService().validate_and_normalize_leave_answers(9, {
        'f_bi_leave_date': '2026-08-25', 'f_bi_start_time': '09:00',
        'f_bi_duration_hours': '1.5', 'f_bi_reason': 'Personal',
        'f_bi_terms_accepted': True, 'signature_image': 'x'})
    assert out['f_bi_hours'] == 1.5 and out['f_bi_end_time'] == '10:30'


def test_validate_raises_on_missing_fields():
    from forms.services.form_service import FormService
    with pytest.raises(ValueError):
        FormService().validate_and_normalize_leave_answers(9, {
            'f_bi_leave_date': '2026-08-25', 'f_bi_start_time': '09:00'})


def test_validate_raises_on_missing_consent_or_signature(monkeypatch):
    from forms.services import form_service as fs
    monkeypatch.setattr(fs.FormService, 'get_leave_form_config',
                        lambda self: {'reasons': ['Personal'], 'terms_text': 'T'})
    with pytest.raises(ValueError):
        fs.FormService().validate_and_normalize_leave_answers(9, {
            'f_bi_leave_date': '2026-08-25', 'f_bi_start_time': '09:00',
            'f_bi_duration_hours': '1.5', 'f_bi_reason': 'Personal',
            'f_bi_terms_accepted': False, 'signature_image': 'x'})
