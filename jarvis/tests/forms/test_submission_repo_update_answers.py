from forms.repositories.submission_repo import SubmissionRepository

def test_update_answers_serializes_json_and_targets_id(monkeypatch):
    captured = {}
    def fake_execute(self, sql, params):
        captured['sql'] = sql; captured['params'] = params
        return 1
    monkeypatch.setattr(SubmissionRepository, 'execute', fake_execute, raising=False)
    ok = SubmissionRepository().update_answers(42, {'f_bi_hours': 1.5})
    assert ok is True
    assert 'UPDATE form_submissions' in captured['sql']
    assert 'SET answers = %s' in captured['sql']
    import json
    assert captured['params'][0] == json.dumps({'f_bi_hours': 1.5})
    assert captured['params'][1] == 42
