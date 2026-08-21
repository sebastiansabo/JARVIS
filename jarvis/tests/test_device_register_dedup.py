"""Registering a device upserts its token AND drops any stale tokens for the SAME
physical device — FCM rotates the token on reinstall/data-clear, leaving orphan
rows that would cause duplicate pushes to one phone."""
from core.connectors.push.repositories.device_repository import DeviceRepository


def _capture(monkeypatch):
    repo = DeviceRepository()
    calls = []
    monkeypatch.setattr(repo, 'execute',
                        lambda sql, params=None, **k: calls.append((' '.join(sql.split()), params)))
    return repo, calls


def test_register_upserts_then_dedupes_same_device(monkeypatch):
    repo, calls = _capture(monkeypatch)
    repo.register(user_id=2, push_token='NEWTOK', platform='android', device_id='dev-abc')

    assert any('INSERT INTO mobile_devices' in sql for sql, _ in calls)   # upsert the new token
    dedup = [(sql, p) for sql, p in calls
             if 'DELETE FROM mobile_devices' in sql and 'device_id' in sql and 'push_token' in sql]
    assert dedup, 'expected a dedup DELETE scoped to the same device_id + other tokens'
    assert dedup[0][1] == ('dev-abc', 'NEWTOK')


def test_register_skips_dedup_when_device_id_blank(monkeypatch):
    # A blank device_id must NOT trigger a DELETE (it would wipe every blank-device row).
    repo, calls = _capture(monkeypatch)
    repo.register(user_id=2, push_token='NEWTOK', platform='android', device_id='')
    assert not [1 for sql, _ in calls if 'DELETE FROM mobile_devices' in sql]
