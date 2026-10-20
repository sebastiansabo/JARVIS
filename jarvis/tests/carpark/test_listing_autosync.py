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


def _autovit_listing(status='active', last_published_at=NOW - timedelta(hours=2)):
    return {'external_advert_id': '123', 'status': status, 'last_published_at': last_published_at}


def _only_shopify_due(rows):
    """list_due side_effect: only the 'shopify' platform call gets `rows`;
    the generalized tick also calls list_due('autovit', now) unconditionally,
    which must see an empty due list so these Shopify-focused tests don't
    accidentally fall into the (unmocked) Autovit account-resolution branch."""
    return lambda platform_type, now: rows if platform_type == 'shopify' else []


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
        SR.return_value.list_due.side_effect = _only_shopify_due([sch])
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


def test_config_autosync_enabled_fails_closed_on_error():
    # A DB/config read failure must NOT let autosync push to the live store — fail
    # closed so a partial outage can't fire an unintended marketplace sync.
    with patch.object(A, '_get_single_account', side_effect=RuntimeError('db down')):
        assert A._config_autosync_enabled() is False


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
        SR.return_value.list_due.side_effect = _only_shopify_due([bad_sch, ok_sch])
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


def test_scheduler_interval_is_1h(monkeypatch):
    """Task 6: the sweep now runs hourly (was every 4h) so freshly-stale
    listings are picked up within an hour instead of up to four."""
    from datetime import timedelta
    from apscheduler.schedulers.background import BackgroundScheduler
    import tasks.cleanup as C
    sched = BackgroundScheduler()
    monkeypatch.setattr(C, 'scheduler', sched)
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    C._register_listing_autosync()
    job = sched.get_job('listing_autosync')
    assert job is not None
    assert job.trigger.interval == timedelta(hours=1)


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


# ── resync_autovit_vehicle (Task 5: generalize the sweep to both platforms) ──

def test_resync_autovit_skips_when_not_stale():
    with patch.object(A, 'AutovitListingRepository') as LR, \
         patch.object(A, 'autovit_sweep_stale', return_value=False), \
         patch.object(A, 'republish_vehicle') as RV:
        LR.return_value.get.return_value = _autovit_listing(last_published_at=NOW)
        veh = {'id': 5, 'updated_at': NOW - timedelta(hours=3)}   # synced after edit → not stale
        out = A.resync_autovit_vehicle({'id': 1}, veh, {}, NOW)
        assert out.startswith('skipped')
        assert not RV.called


def test_resync_autovit_skips_unmapped_required():
    with patch.object(A, 'AutovitListingRepository') as LR, \
         patch.object(A, 'autovit_sweep_stale', return_value=True), \
         patch.object(A, 'VehiclePhotoRepository') as PR, \
         patch.object(A, 'republish_vehicle',
                       return_value={'success': False, 'unmapped_required': ['fuel_type']}) as RV:
        LR.return_value.get.return_value = _autovit_listing()
        PR.return_value.urls.return_value = []
        veh = {'id': 5, 'updated_at': NOW}
        out = A.resync_autovit_vehicle({'id': 1}, veh, {}, NOW)
        assert out == 'skipped: unmapped fuel_type'
        RV.assert_called_once()


def test_resync_autovit_pushes_when_stale():
    with patch.object(A, 'AutovitListingRepository') as LR, \
         patch.object(A, 'autovit_sweep_stale', return_value=True), \
         patch.object(A, 'VehiclePhotoRepository') as PR, \
         patch.object(A, 'republish_vehicle', return_value={'success': True}) as RV:
        LR.return_value.get.return_value = _autovit_listing()
        PR.return_value.urls.return_value = []
        veh = {'id': 5, 'updated_at': NOW}
        out = A.resync_autovit_vehicle({'id': 1}, veh, {}, NOW)
        assert out == 'pushed'
        RV.assert_called_once()


def test_resync_autovit_reports_error():
    """Bonus parity case mirroring test_resync_reports_error (Shopify) — not in
    the brief's required list, but the same error-mapping branch deserves the
    same coverage Shopify's resync already has."""
    with patch.object(A, 'AutovitListingRepository') as LR, \
         patch.object(A, 'autovit_sweep_stale', return_value=True), \
         patch.object(A, 'VehiclePhotoRepository') as PR, \
         patch.object(A, 'republish_vehicle', return_value={'success': False, 'error': 'boom'}):
        LR.return_value.get.return_value = _autovit_listing()
        PR.return_value.urls.return_value = []
        veh = {'id': 5, 'updated_at': NOW}
        out = A.resync_autovit_vehicle({'id': 1}, veh, {}, NOW)
        assert out == 'error: boom'


# ── listing_autosync_tick generalized to the Autovit due loop ──

def test_tick_processes_autovit_due(monkeypatch):
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    sch = {'id': 21, 'vehicle_id': 8, 'cadence': 'daily'}
    with patch.object(A, '_config_autosync_enabled', return_value=True), \
         patch.object(A, 'ListingScheduleRepository') as SR, \
         patch.object(A, 'VehicleRepository') as VR, \
         patch.object(A, 'ConnectorRepository') as CR, \
         patch.object(A, 'AutovitTaxonomyRepository') as TR, \
         patch.object(A, 'resync_autovit_vehicle', return_value='pushed') as RA:
        SR.return_value.list_due.side_effect = (
            lambda platform_type, now: [sch] if platform_type == 'autovit' else [])
        VR.return_value.get_by_id.return_value = {'id': 8, 'updated_at': NOW}
        CR.return_value.get_all_by_type.return_value = [{'id': 99}]
        TR.return_value.get_map.return_value = {}
        A.listing_autosync_tick()
        RA.assert_called_once()
        SR.return_value.mark_run.assert_called_once()
        args, _ = SR.return_value.mark_run.call_args
        assert args[0] == sch['id']
        # cadence 'daily' -> 1440 minutes; next_run_at ≈ real now + cadence
        # (the tick stamps datetime.now(timezone.utc) internally, not the
        # fixture's fixed NOW, so compare against the actual wall clock).
        expected = datetime.now(timezone.utc) + timedelta(minutes=1440)
        assert abs((args[1] - expected).total_seconds()) < 5
        assert args[2] == 'pushed'


def test_tick_autovit_continues_after_one_schedule_fails(monkeypatch):
    """Mirrors test_tick_continues_after_one_schedule_fails (Shopify): a
    per-schedule exception in the Autovit loop must not abort the batch."""
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    bad_sch = {'id': 23, 'vehicle_id': 8, 'cadence': 'daily'}
    ok_sch = {'id': 24, 'vehicle_id': 9, 'cadence': 'daily'}
    with patch.object(A, '_config_autosync_enabled', return_value=True), \
         patch.object(A, 'ListingScheduleRepository') as SR, \
         patch.object(A, 'VehicleRepository') as VR, \
         patch.object(A, 'ConnectorRepository') as CR, \
         patch.object(A, 'AutovitTaxonomyRepository') as TR, \
         patch.object(A, 'resync_autovit_vehicle',
                       side_effect=[RuntimeError('boom'), 'pushed']) as RA:
        SR.return_value.list_due.side_effect = (
            lambda platform_type, now: [bad_sch, ok_sch] if platform_type == 'autovit' else [])
        VR.return_value.get_by_id.return_value = {'id': 9, 'updated_at': NOW}
        CR.return_value.get_all_by_type.return_value = [{'id': 99}]
        TR.return_value.get_map.return_value = {}
        A.listing_autosync_tick()
        assert RA.call_count == 2
        assert SR.return_value.mark_run.call_count == 2


def test_tick_autovit_no_account_skips(monkeypatch):
    """No Autovit connector configured: due rows are marked skipped, and the
    sweep must not crash or call resync_autovit_vehicle."""
    monkeypatch.setenv('ENABLE_LISTING_AUTOSYNC', 'true')
    sch = {'id': 22, 'vehicle_id': 8, 'cadence': 'daily'}
    with patch.object(A, '_config_autosync_enabled', return_value=True), \
         patch.object(A, 'ListingScheduleRepository') as SR, \
         patch.object(A, 'ConnectorRepository') as CR, \
         patch.object(A, 'resync_autovit_vehicle') as RA:
        SR.return_value.list_due.side_effect = (
            lambda platform_type, now: [sch] if platform_type == 'autovit' else [])
        CR.return_value.get_all_by_type.return_value = []
        A.listing_autosync_tick()
        assert not RA.called
        SR.return_value.mark_run.assert_called_once()
        args, _ = SR.return_value.mark_run.call_args
        assert args[0] == sch['id']
        assert 'skipped' in args[2]
