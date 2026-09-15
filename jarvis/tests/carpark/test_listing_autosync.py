"""Tests for the env-gated Shopify listing autosync tick (Task 3).

All DB/API access is mocked — connector, repos, and the module-level
`_taxo_map()` helper are patched so no real Postgres/Shopify call happens.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from tasks import listing_autosync as A

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _listing(status='published', last_sync=NOW - timedelta(hours=2)):
    return {'external_listing_id': 'gid://1', 'status': status, 'last_sync': last_sync, 'expires_at': None}


def test_resync_pushes_when_stale():
    pub = MagicMock(); pub.get_listing_by_vehicle_platform.return_value = _listing()
    photo = MagicMock(); photo.get_by_vehicle.return_value = []
    conn = MagicMock(platform_id=7); conn.publish.return_value = {'success': True}
    veh = {'id': 5, 'updated_at': NOW - timedelta(minutes=1)}   # edited after last_sync → stale
    assert A.resync_shopify_vehicle(conn, pub, photo, {}, veh, NOW) == 'pushed'
    conn.publish.assert_called_once()


def test_resync_skips_when_fresh():
    pub = MagicMock(); pub.get_listing_by_vehicle_platform.return_value = _listing(last_sync=NOW)
    conn = MagicMock(platform_id=7)
    veh = {'id': 5, 'updated_at': NOW - timedelta(hours=3)}     # synced after edit → up_to_date
    out = A.resync_shopify_vehicle(conn, pub, MagicMock(), {}, veh, NOW)
    assert out.startswith('skipped') and not conn.publish.called


def test_resync_skips_unpublished():
    pub = MagicMock(); pub.get_listing_by_vehicle_platform.return_value = None
    conn = MagicMock(platform_id=7)
    out = A.resync_shopify_vehicle(conn, pub, MagicMock(), {}, {'id': 5, 'updated_at': NOW}, NOW)
    assert out.startswith('skipped') and not conn.publish.called


def test_resync_reports_error():
    pub = MagicMock(); pub.get_listing_by_vehicle_platform.return_value = _listing()
    conn = MagicMock(platform_id=7); conn.publish.return_value = {'success': False, 'error': 'boom'}
    out = A.resync_shopify_vehicle(conn, pub, MagicMock(), {}, {'id': 5, 'updated_at': NOW}, NOW)
    assert out == 'error: boom'


def test_tick_processes_due_and_marks_run(monkeypatch):
    # NOTE: the safety gate is default-OFF (see test_tick_noop_when_disabled), so this
    # must opt in explicitly to exercise the due-processing path.
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    sch = {'id': 9, 'vehicle_id': 5, 'cadence': 'daily'}
    with patch.object(A, 'build_shopify_connector', return_value=MagicMock(platform_id=7)), \
         patch.object(A, '_taxo_map', return_value={}), \
         patch.object(A, '_config_autosync_enabled', return_value=True), \
         patch.object(A, 'ListingScheduleRepository') as SR, \
         patch.object(A, 'VehicleRepository') as VR, \
         patch.object(A, 'resync_shopify_vehicle', return_value='pushed') as RS:
        SR.return_value.list_due.return_value = [sch]
        VR.return_value.get_by_id.return_value = {'id': 5, 'updated_at': NOW}
        A.listing_autosync_tick()
        RS.assert_called_once()
        SR.return_value.mark_run.assert_called_once()


def test_autosync_enabled_env_gate(monkeypatch):
    """The env gate alone (config gate patched open) still drives autosync_enabled()."""
    with patch.object(A, '_config_autosync_enabled', return_value=True):
        monkeypatch.delenv('ENABLE_LISTING_AUTOSYNC', raising=False)
        assert A.autosync_enabled() is False
        monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
        assert A.autosync_enabled() is True


def test_env_gate_helper(monkeypatch):
    monkeypatch.delenv('ENABLE_LISTING_AUTOSYNC', raising=False)
    assert A._env_gate() is False
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    assert A._env_gate() is True


def test_config_autosync_enabled_no_account_defaults_true():
    with patch.object(A, '_get_single_account', return_value=None):
        assert A._config_autosync_enabled() is True


def test_config_autosync_enabled_reads_flag_false():
    with patch.object(A, '_get_single_account', return_value={'id': 1, 'config': {}}), \
         patch.object(A, '_parse_json', return_value={'autosync_enabled': False}):
        assert A._config_autosync_enabled() is False


def test_config_autosync_enabled_flag_absent_defaults_true():
    with patch.object(A, '_get_single_account', return_value={'id': 1, 'config': {}}), \
         patch.object(A, '_parse_json', return_value={}):
        assert A._config_autosync_enabled() is True


def test_config_autosync_enabled_fails_open_on_error():
    with patch.object(A, '_get_single_account', side_effect=RuntimeError('db down')):
        assert A._config_autosync_enabled() is True


def test_autosync_enabled_truth_table(monkeypatch):
    # env true + config flag absent (defaults True) -> enabled True
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    with patch.object(A, '_config_autosync_enabled', return_value=True):
        assert A.autosync_enabled() is True

    # env true + config flag False -> enabled False
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    with patch.object(A, '_config_autosync_enabled', return_value=False):
        assert A.autosync_enabled() is False

    # env false -> False regardless of config flag
    monkeypatch.delenv('ENABLE_LISTING_AUTOSYNC', raising=False)
    with patch.object(A, '_config_autosync_enabled', return_value=True):
        assert A.autosync_enabled() is False
    with patch.object(A, '_config_autosync_enabled', return_value=False):
        assert A.autosync_enabled() is False


def test_tick_noop_when_disabled(monkeypatch):
    """Default-OFF safety: must not touch the schedule repo at all when disabled."""
    monkeypatch.delenv('ENABLE_LISTING_AUTOSYNC', raising=False)
    with patch.object(A, 'ListingScheduleRepository') as SR, \
         patch.object(A, 'build_shopify_connector') as BC:
        A.listing_autosync_tick()
        SR.assert_not_called()
        BC.assert_not_called()


def test_tick_continues_after_one_schedule_fails(monkeypatch):
    """A per-schedule exception must not abort the batch — the next schedule still runs."""
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    ok_sch = {'id': 10, 'vehicle_id': 6, 'cadence': 'daily'}
    bad_sch = {'id': 9, 'vehicle_id': 5, 'cadence': 'daily'}
    with patch.object(A, 'build_shopify_connector', return_value=MagicMock(platform_id=7)), \
         patch.object(A, '_taxo_map', return_value={}), \
         patch.object(A, '_config_autosync_enabled', return_value=True), \
         patch.object(A, 'ListingScheduleRepository') as SR, \
         patch.object(A, 'VehicleRepository') as VR, \
         patch.object(A, 'resync_shopify_vehicle', side_effect=[RuntimeError('boom'), 'pushed']) as RS:
        SR.return_value.list_due.return_value = [bad_sch, ok_sch]
        VR.return_value.get_by_id.return_value = {'id': 5, 'updated_at': NOW}
        A.listing_autosync_tick()
        assert RS.call_count == 2
        assert SR.return_value.mark_run.call_count == 2


def test_tick_registered_only_when_enabled(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    import tasks.cleanup as C
    sched = BackgroundScheduler()
    monkeypatch.setattr(C, 'scheduler', sched)
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    C._register_listing_autosync()       # small helper added in Step 3
    assert sched.get_job('listing_autosync') is not None


def test_tick_not_registered_when_disabled(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    import tasks.cleanup as C
    sched = BackgroundScheduler()
    monkeypatch.setattr(C, 'scheduler', sched)
    monkeypatch.delenv('ENABLE_LISTING_AUTOSYNC', raising=False)
    C._register_listing_autosync()
    assert sched.get_job('listing_autosync') is None


def test_instant_noop_when_disabled(monkeypatch):
    monkeypatch.delenv('ENABLE_LISTING_AUTOSYNC', raising=False)
    with patch.object(A, 'threading') as T:
        A.maybe_instant_resync(5)
        T.Thread.assert_not_called()


def test_instant_spawns_for_instant_schedule(monkeypatch):
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    with patch.object(A, '_config_autosync_enabled', return_value=True), \
         patch.object(A, 'ListingScheduleRepository') as SR, patch.object(A, 'threading') as T:
        SR.return_value.get.return_value = {'enabled': True, 'cadence': 'instant'}
        A.maybe_instant_resync(5)
        T.Thread.assert_called_once()


def test_instant_noop_for_non_instant(monkeypatch):
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    with patch.object(A, '_config_autosync_enabled', return_value=True), \
         patch.object(A, 'ListingScheduleRepository') as SR, patch.object(A, 'threading') as T:
        SR.return_value.get.return_value = {'enabled': True, 'cadence': 'daily'}
        A.maybe_instant_resync(5)
        T.Thread.assert_not_called()
