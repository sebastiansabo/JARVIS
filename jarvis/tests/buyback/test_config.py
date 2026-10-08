"""Tests for the buyback notification config resolver (row-or-defaults)."""
import buyback.services.config as cfgmod
from buyback.services.config import get_config, DEFAULT_ACQUISITION_EMAIL


class _FakeRepo:
    def __init__(self, row):
        self._row = row

    def get(self, company_id):
        return self._row


def test_defaults_when_no_row(monkeypatch):
    monkeypatch.setattr(cfgmod, '_repo', _FakeRepo(None))
    monkeypatch.delenv('BUYBACK_ACQUISITION_EMAIL', raising=False)
    cfg = get_config(1)
    assert cfg['enabled'] is True
    assert cfg['acquisition_emails'] == [DEFAULT_ACQUISITION_EMAIL]
    assert cfg['channel_email'] and cfg['notify_milestones']


def test_env_fallback_for_acquisition(monkeypatch):
    monkeypatch.setattr(cfgmod, '_repo', _FakeRepo(None))
    monkeypatch.setenv('BUYBACK_ACQUISITION_EMAIL', 'env@x.ro, env2@x.ro')
    assert get_config(1)['acquisition_emails'] == ['env@x.ro', 'env2@x.ro']


def test_row_overrides(monkeypatch):
    row = {'enabled': False, 'channel_email': True, 'channel_in_app': False,
           'channel_push': False, 'notify_new_request': True, 'notify_milestones': False,
           'notify_inspection': True, 'acquisition_emails': 'a@b.ro;c@d.ro'}
    monkeypatch.setattr(cfgmod, '_repo', _FakeRepo(row))
    cfg = get_config(5)
    assert cfg['enabled'] is False and cfg['channel_in_app'] is False
    assert cfg['acquisition_emails'] == ['a@b.ro', 'c@d.ro']
