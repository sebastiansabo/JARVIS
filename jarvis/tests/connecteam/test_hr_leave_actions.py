"""Unit tests for the HR-scoped leave actions (edit details + archive/restore).

These sit under the HR Leave-Permits admin tab and cover BOTH leave sources:
- 'jarvis'     → form_submissions (details live in the `answers` JSON)
- 'connecteam' → connecteam_form_submissions (flat columns)

Following the pattern of test_leave_permit_actions.py, the module's small DB
helpers are monkeypatched so these tests exercise the branching/normalization
logic, not the database.
"""
import pytest
from core.connectors.connecteam.services import leave_permit_actions as lpa


# ── edit (details only, status untouched) ──

def test_hr_update_jarvis_writes_details_into_answers(monkeypatch):
    captured = {}
    monkeypatch.setattr(lpa, '_hr_get_jarvis',
        lambda eid: {'id': eid, 'status': 'approved',
                     'answers': {'f_bi_reason': 'old', 'f_bi_notes': 'keep'}})
    monkeypatch.setattr(lpa, '_hr_update_jarvis_answers',
        lambda eid, ans: captured.update(id=eid, ans=ans))
    out = lpa.hr_update_leave('jarvis', 42, {
        'leave_date': '2026-08-20', 'leave_start_time': '09:00',
        'leave_end_time': '11:30', 'leave_reason': 'Personal'})
    assert out == {'source': 'jarvis', 'id': 42}
    a = captured['ans']
    assert a['f_bi_leave_date'] == '2026-08-20'
    assert a['f_bi_start_time'] == '09:00' and a['f_bi_end_time'] == '11:30'
    assert a['f_bi_duration_hours'] == 2.5 and a['f_bi_hours'] == 2.5
    assert a['f_bi_reason'] == 'Personal'
    assert a['f_bi_notes'] == 'keep'          # untouched fields preserved


def test_hr_update_never_writes_status(monkeypatch):
    monkeypatch.setattr(lpa, '_hr_get_jarvis',
        lambda eid: {'id': eid, 'status': 'approved', 'answers': {}})
    monkeypatch.setattr(lpa, '_hr_update_jarvis_answers', lambda eid, ans: None)
    monkeypatch.setattr(lpa, '_set_status',
        lambda *a, **k: pytest.fail('HR edit must not change status'))
    lpa.hr_update_leave('jarvis', 42, {
        'leave_date': '2026-08-20', 'leave_start_time': '09:00',
        'leave_end_time': '10:00', 'leave_reason': 'x'})


def test_hr_update_connecteam_updates_flat_fields(monkeypatch):
    captured = {}
    monkeypatch.setattr(lpa, '_hr_get_connecteam', lambda eid: {'id': eid, 'status': 'submitted'})
    monkeypatch.setattr(lpa, '_hr_update_connecteam_fields',
        lambda eid, fields: captured.update(id=eid, fields=fields))
    lpa.hr_update_leave('connecteam', 7, {
        'leave_date': '2026-08-19', 'leave_start_time': '08:00',
        'leave_end_time': '09:00', 'leave_reason': 'Altul'})
    assert captured['id'] == 7
    f = captured['fields']
    assert f['leave_hours'] == 1.0 and f['leave_end_time'] == '09:00'
    assert f['leave_date'] == '2026-08-19' and f['leave_reason'] == 'Altul'


def test_hr_update_end_before_start_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_hr_get_jarvis', lambda eid: {'id': eid, 'answers': {}})
    with pytest.raises(ValueError):
        lpa.hr_update_leave('jarvis', 1, {
            'leave_date': '2026-08-20', 'leave_start_time': '11:00',
            'leave_end_time': '09:00', 'leave_reason': 'x'})


def test_hr_update_bad_date_raises():
    with pytest.raises(ValueError):
        lpa.hr_update_leave('jarvis', 1, {
            'leave_date': '20-08-2026', 'leave_start_time': '09:00',
            'leave_end_time': '10:00', 'leave_reason': 'x'})


def test_hr_update_unknown_source_raises():
    with pytest.raises(ValueError):
        lpa.hr_update_leave('nope', 1, {
            'leave_date': '2026-08-20', 'leave_start_time': '09:00',
            'leave_end_time': '10:00', 'leave_reason': 'x'})


def test_hr_update_missing_entity_raises_lookup(monkeypatch):
    monkeypatch.setattr(lpa, '_hr_get_jarvis', lambda eid: None)
    with pytest.raises(LookupError):
        lpa.hr_update_leave('jarvis', 999, {
            'leave_date': '2026-08-20', 'leave_start_time': '09:00',
            'leave_end_time': '10:00', 'leave_reason': 'x'})


# ── lifecycle: archive / trash / restore ──

def test_hr_archive_jarvis_records_state_and_actor(monkeypatch):
    captured = {}
    monkeypatch.setattr(lpa, '_hr_get_jarvis', lambda eid: {'id': eid})
    monkeypatch.setattr(lpa, '_hr_set_lifecycle_jarvis',
        lambda eid, state, actor: captured.update(eid=eid, state=state, actor=actor))
    out = lpa.hr_set_lifecycle('jarvis', 42, actor_id=5, state='archived')
    assert out == {'source': 'jarvis', 'id': 42, 'state': 'archived'}
    assert captured == {'eid': 42, 'state': 'archived', 'actor': 5}


def test_hr_trash_connecteam(monkeypatch):
    captured = {}
    monkeypatch.setattr(lpa, '_hr_get_connecteam', lambda eid: {'id': eid})
    monkeypatch.setattr(lpa, '_hr_set_lifecycle_connecteam',
        lambda eid, state, actor: captured.update(eid=eid, state=state, actor=actor))
    out = lpa.hr_set_lifecycle('connecteam', 7, actor_id=5, state='trashed')
    assert out['state'] == 'trashed' and captured['state'] == 'trashed'


def test_hr_restore_connecteam(monkeypatch):
    captured = {}
    monkeypatch.setattr(lpa, '_hr_get_connecteam', lambda eid: {'id': eid})
    monkeypatch.setattr(lpa, '_hr_set_lifecycle_connecteam',
        lambda eid, state, actor: captured.update(state=state))
    out = lpa.hr_set_lifecycle('connecteam', 7, actor_id=5, state='active')
    assert out['state'] == 'active' and captured['state'] == 'active'


def test_hr_lifecycle_unknown_state_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_hr_get_jarvis', lambda eid: {'id': eid})
    with pytest.raises(ValueError):
        lpa.hr_set_lifecycle('jarvis', 1, actor_id=5, state='banished')


def test_hr_lifecycle_missing_entity_raises_lookup(monkeypatch):
    monkeypatch.setattr(lpa, '_hr_get_connecteam', lambda eid: None)
    with pytest.raises(LookupError):
        lpa.hr_set_lifecycle('connecteam', 999, actor_id=5, state='trashed')


def test_hr_lifecycle_unknown_source_raises():
    with pytest.raises(ValueError):
        lpa.hr_set_lifecycle('nope', 1, actor_id=5, state='archived')


# ── trash purge ──

def test_purge_trashed_sums_both_sources(monkeypatch):
    calls = {}
    class FakeSub:
        def purge_trashed(self, days, slug): calls['sub'] = (days, slug); return 2
    class FakeCt:
        def purge_trashed(self, days): calls['ct'] = days; return 3
    monkeypatch.setattr('forms.repositories.SubmissionRepository', FakeSub)
    monkeypatch.setattr(
        'core.connectors.connecteam.repositories.connecteam_repository.ConnecteamRepository', FakeCt)
    total = lpa.purge_trashed_leaves(days=7)
    assert total == 5
    assert calls['ct'] == 7 and calls['sub'][0] == 7 and calls['sub'][1] == 'bilet-de-invoire'
