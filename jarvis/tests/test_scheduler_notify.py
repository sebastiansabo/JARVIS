import core.approvals.handlers.event_handlers as eh


def test_approved_decider_ids_filters_by_decision():
    decisions = [
        {'decided_by': 5, 'decision': 'approved'},
        {'decided_by': 9, 'decision': 'returned'},
        {'decided_by': 7, 'decision': 'approved'},
    ]
    assert eh._approved_decider_ids(decisions) == {5, 7}


def test_scheduler_skipped_when_manager_is_decider(monkeypatch):
    sent = []
    monkeypatch.setattr(eh, '_load_leave_submission', lambda sid: {
        'slug': 'bilet-de-invoire', 'respondent_user_id': 1, 'company_id': 16,
        'requester_name': 'Ana', 'answers': {'f_bi_leave_date': '2026-08-18',
        'f_bi_start_time': '09:00', 'f_bi_end_time': '10:00', 'f_bi_hours': 1.0}})
    monkeypatch.setattr(eh, '_resolve_manager', lambda uid, cid: {'id': 5, 'name': 'Boss', 'email': 'b@x.ro'})
    monkeypatch.setattr(eh, '_load_approved_deciders', lambda rid: {5})   # manager already approved
    monkeypatch.setattr(eh, 'notify_user', lambda *a, **k: sent.append(a))
    eh._maybe_notify_leave_scheduler(request_id=100, submission_id=55, ctx={})
    assert sent == []


def test_scheduler_notified_when_manager_differs(monkeypatch):
    sent = []
    monkeypatch.setattr(eh, '_load_leave_submission', lambda sid: {
        'slug': 'bilet-de-invoire', 'respondent_user_id': 1, 'company_id': 16,
        'requester_name': 'Ana', 'answers': {'f_bi_leave_date': '2026-08-18',
        'f_bi_start_time': '09:00', 'f_bi_end_time': '10:00', 'f_bi_hours': 1.0}})
    monkeypatch.setattr(eh, '_resolve_manager', lambda uid, cid: {'id': 8, 'name': 'Boss', 'email': 'b@x.ro'})
    monkeypatch.setattr(eh, '_load_approved_deciders', lambda rid: {5})   # someone else approved
    monkeypatch.setattr(eh, 'notify_user', lambda *a, **k: sent.append((a, k)))
    monkeypatch.setattr(eh, '_get_user_email', lambda uid: ('Boss', None))  # skip email branch
    eh._maybe_notify_leave_scheduler(request_id=100, submission_id=55, ctx={})
    assert len(sent) == 1 and sent[0][0][0] == 8   # notified user id 8
