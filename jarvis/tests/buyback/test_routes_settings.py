"""Tests for the admin per-tenant buyback notification config routes."""


def test_get_config_defaults_for_unconfigured(client, as_role):
    as_role('Admin', 1)
    r = client.get('/api/buyback/settings/config?company_id=424242')
    assert r.status_code == 200
    cfg = r.get_json()['config']
    assert cfg['enabled'] is True
    assert cfg['acquisition_emails'] == 'achizitii@autoworld.ro'


def test_put_requires_admin(client, as_role):
    as_role('Sales', 1)  # not can_access_settings
    r = client.put('/api/buyback/settings/config', json={'company_id': 1, 'enabled': False})
    assert r.status_code == 403


def test_put_rejects_bad_email(client, as_role):
    as_role('Admin', 1)
    r = client.put('/api/buyback/settings/config',
                   json={'company_id': 424243, 'acquisition_emails': 'notanemail'})
    assert r.status_code == 400


def test_put_upserts_and_reads_back(client, as_role):
    as_role('Admin', 1)
    r = client.put('/api/buyback/settings/config',
                   json={'company_id': 424244, 'enabled': False,
                         'acquisition_emails': 'x@y.ro, z@y.ro', 'channel_push': False})
    assert r.status_code == 200
    cfg = r.get_json()['config']
    assert cfg['enabled'] is False and cfg['channel_push'] is False
    assert cfg['acquisition_emails'] == 'x@y.ro, z@y.ro'
