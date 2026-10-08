"""Tests for config-driven buyback notifications (primitives mocked)."""
import buyback.services.notifications as nmod


def _cfg(**over):
    base = {'enabled': True, 'channel_email': True, 'channel_in_app': True,
            'channel_push': True, 'notify_new_request': True,
            'notify_milestones': True, 'notify_inspection': True,
            'acquisition_emails': ['achizitii@autoworld.ro']}
    base.update(over)
    return base


def _patch(monkeypatch, cfg, sink):
    monkeypatch.setattr(nmod, 'get_config', lambda cid: cfg)
    import core.services.notification_service as ns
    import core.notifications.push_service as ps
    import core.notifications.repositories.in_app_repo as ia
    import core.auth.repositories.user_repository as ur
    monkeypatch.setattr(ns, 'send_email', lambda **k: sink['email'].append(k) or (True, ''))
    monkeypatch.setattr(ps, 'send_push_to_users', lambda *a, **k: sink['push'].append((a, k)))
    monkeypatch.setattr(ia.InAppNotificationRepository, 'create', lambda self, **k: sink['in_app'].append(k))
    monkeypatch.setattr(ur.UserRepository, 'get_by_id', lambda self, uid: {'email': 'owner@x.ro'})


def _sink():
    return {'email': [], 'push': [], 'in_app': []}


def test_new_request_emails_acquisition(monkeypatch):
    s = _sink(); _patch(monkeypatch, _cfg(), s)
    nmod.notify_new_request({'id': 1, 'company_id': 1, 'record_code': 'BB-1',
                             'brand': 'BMW', 'model': 'X5', 'seller_name': 'Ion'})
    assert [e['to_email'] for e in s['email']] == ['achizitii@autoworld.ro']


def test_new_request_still_emails_when_channel_email_off(monkeypatch):
    s = _sink(); _patch(monkeypatch, _cfg(channel_email=False), s)
    nmod.notify_new_request({'id': 1, 'company_id': 1, 'brand': 'BMW', 'model': 'X5'})
    assert len(s['email']) == 1  # acquisition NOT gated by channel_email


def test_new_request_skipped_when_disabled(monkeypatch):
    s = _sink(); _patch(monkeypatch, _cfg(enabled=False), s)
    nmod.notify_new_request({'id': 1, 'company_id': 1})
    assert not s['email']


def test_owner_skips_self(monkeypatch):
    s = _sink(); _patch(monkeypatch, _cfg(), s)
    nmod.notify_owner({'id': 1, 'company_id': 1, 'created_by': 7}, 'status_changed', 7, new_status='LOST')
    assert not (s['email'] or s['push'] or s['in_app'])


def test_owner_skips_null_creator(monkeypatch):
    s = _sink(); _patch(monkeypatch, _cfg(), s)
    nmod.notify_owner({'id': 1, 'company_id': 1, 'created_by': None}, 'status_changed', 7, new_status='LOST')
    assert not (s['email'] or s['push'] or s['in_app'])


def test_owner_honors_channel_toggles(monkeypatch):
    s = _sink(); _patch(monkeypatch, _cfg(channel_push=False, channel_email=False), s)
    nmod.notify_owner({'id': 1, 'company_id': 1, 'created_by': 7, 'brand': 'BMW', 'model': 'X5'},
                      'status_changed', 99, new_status='INITIAL_OFFER')
    assert len(s['in_app']) == 1 and not s['push'] and not s['email']


def test_owner_inspection_group_gate(monkeypatch):
    s = _sink(); _patch(monkeypatch, _cfg(notify_inspection=False), s)
    nmod.notify_owner({'id': 1, 'company_id': 1, 'created_by': 7}, 'inspection_updated', 99)
    assert not (s['email'] or s['push'] or s['in_app'])


def test_owner_channel_failure_is_swallowed(monkeypatch):
    s = _sink(); _patch(monkeypatch, _cfg(), s)
    import core.notifications.push_service as ps
    def boom(*a, **k):
        raise RuntimeError('fcm down')
    monkeypatch.setattr(ps, 'send_push_to_users', boom)
    # must not raise; in-app + email still fire
    nmod.notify_owner({'id': 1, 'company_id': 1, 'created_by': 7, 'brand': 'BMW', 'model': 'X5'},
                      'status_changed', 99, new_status='BOUGHT')
    assert len(s['in_app']) == 1 and len(s['email']) == 1
