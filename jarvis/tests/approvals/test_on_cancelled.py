from core.approvals.handlers import entity_form

def test_handle_cancelled_marks_submission_cancelled(monkeypatch):
    seen = {}
    class Repo:
        def update_status(self, sid, status): seen['status'] = (sid, status); return True
    import forms.repositories as fr
    monkeypatch.setattr(fr, 'SubmissionRepository', lambda: Repo(), raising=False)
    monkeypatch.setattr(entity_form, '_notify_form_submission_users', lambda *a, **k: None, raising=False)
    entity_form.handle_cancelled(42, {'title': 'x'})
    assert seen['status'] == (42, 'cancelled')

def test_handle_cancelled_skips_when_cancellation_request(monkeypatch):
    seen = {}
    class Repo:
        def update_status(self, sid, status): seen['called'] = True; return True
    import forms.repositories as fr
    monkeypatch.setattr(fr, 'SubmissionRepository', lambda: Repo(), raising=False)
    entity_form.handle_cancelled(42, {'cancellation': True})
    assert 'called' not in seen
