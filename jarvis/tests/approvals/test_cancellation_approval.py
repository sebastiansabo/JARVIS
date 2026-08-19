from core.approvals.handlers import entity_form

def test_cancellation_approved_reverses_and_cancels(monkeypatch):
    seen = {}
    class Repo:
        def update_status(self, sid, status): seen['status'] = (sid, status); return True
    import forms.repositories as fr
    monkeypatch.setattr(fr, 'SubmissionRepository', lambda: Repo(), raising=False)
    monkeypatch.setattr(entity_form, '_reverse_leave_permit_hours',
                        lambda sid, repo: seen.setdefault('reversed', sid), raising=False)
    monkeypatch.setattr(entity_form, '_notify_form_submission_users', lambda *a, **k: None, raising=False)
    entity_form.handle_cancellation_approved(42, {'title': 'x'})
    assert seen['reversed'] == 42 and seen['status'] == (42, 'cancelled')

def test_cancellation_rejected_restores_approved(monkeypatch):
    seen = {}
    class Repo:
        def update_status(self, sid, status): seen['status'] = (sid, status); return True
    import forms.repositories as fr
    monkeypatch.setattr(fr, 'SubmissionRepository', lambda: Repo(), raising=False)
    monkeypatch.setattr(entity_form, '_notify_form_submission_users', lambda *a, **k: None, raising=False)
    entity_form.handle_cancellation_rejected(42, {'title': 'x'})
    assert seen['status'] == (42, 'approved')
