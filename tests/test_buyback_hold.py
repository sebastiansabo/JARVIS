import sys, os
from unittest.mock import MagicMock, patch
from contextlib import ExitStack

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
from buyback import lifecycle
from buyback.services.buyback_service import BuyBackService

def test_on_hold_transitions_and_label():
    assert lifecycle.ON_HOLD == 'ON_HOLD'
    assert lifecycle.STATUS_LABELS['ON_HOLD'] == 'Suspendat'
    assert lifecycle.is_valid_transition('PENDING_EVALUATION', 'ON_HOLD')
    assert lifecycle.is_valid_transition('INSPECTION', 'ON_HOLD')
    assert lifecycle.is_valid_transition('ON_HOLD', 'INSPECTION')
    assert lifecycle.is_valid_transition('ON_HOLD', 'PENDING_EVALUATION')
    # existing transitions preserved
    assert lifecycle.is_valid_transition('PENDING_EVALUATION', 'INITIAL_OFFER')
    assert not lifecycle.is_valid_transition('BOUGHT', 'ON_HOLD')


def _service():
    svc = BuyBackService()
    svc.records = MagicMock()
    svc.events = MagicMock()
    return svc


ACTIVE_STATUSES = [
    lifecycle.PENDING_EVALUATION,
    lifecycle.INITIAL_OFFER,
    lifecycle.INSPECTION,
    lifecycle.FINAL_OFFER,
]


@pytest.mark.parametrize('old_status', ACTIVE_STATUSES)
def test_hold_from_each_active_status(old_status):
    svc = _service()
    rec = {'id': 1, 'status': old_status}
    svc.records.set_status.return_value = {**rec, 'status': lifecycle.ON_HOLD}
    svc.records.update.return_value = {**rec, 'status': lifecycle.ON_HOLD, 'hold_prior_status': old_status}

    result = svc.hold(rec, 'Poze lipsă', 'lipsesc 3 poze', actor=9)

    svc.records.set_status.assert_called_once_with(1, lifecycle.ON_HOLD, 9)

    update_args = svc.records.update.call_args.args
    assert update_args[0] == 1
    payload = update_args[1]
    assert payload['hold_prior_status'] == old_status
    assert payload['hold_reason'] == 'Poze lipsă'
    assert payload['hold_note'] == 'lipsesc 3 poze'
    assert payload['held_by'] == 9
    assert payload['held_at'] is not None

    svc.events.log.assert_called_once_with(
        1, 'held', 9, {'reason': 'Poze lipsă', 'note': 'lipsesc 3 poze'}
    )

    # returned value is exactly what update() returned
    assert result is svc.records.update.return_value


@pytest.mark.parametrize('bad_status', [
    lifecycle.BOUGHT, lifecycle.LOST, lifecycle.CANCELLED, lifecycle.ON_HOLD,
])
def test_hold_from_non_active_status_raises(bad_status):
    svc = _service()
    rec = {'id': 2, 'status': bad_status}

    with pytest.raises(ValueError):
        svc.hold(rec, 'reason', 'note', actor=9)

    svc.records.set_status.assert_not_called()
    svc.records.update.assert_not_called()
    svc.events.log.assert_not_called()


@pytest.mark.parametrize('note', [None, '', '   ', '\n\t '])
def test_hold_note_blank_stored_as_none(note):
    svc = _service()
    rec = {'id': 5, 'status': lifecycle.INSPECTION}

    svc.hold(rec, 'Poze lipsă', note, actor=9)

    payload = svc.records.update.call_args.args[1]
    assert payload['hold_note'] is None


def test_hold_note_truncated_to_1000_chars():
    svc = _service()
    rec = {'id': 6, 'status': lifecycle.INSPECTION}

    svc.hold(rec, 'Poze lipsă', 'x' * 1500, actor=9)

    payload = svc.records.update.call_args.args[1]
    assert payload['hold_note'] == 'x' * 1000


def test_resume_from_on_hold_restores_exact_prior_status():
    svc = _service()
    rec = {
        'id': 3, 'status': lifecycle.ON_HOLD,
        'hold_prior_status': lifecycle.INSPECTION,
    }
    svc.records.set_status.return_value = {**rec, 'status': lifecycle.INSPECTION}
    svc.records.update.return_value = {**rec, 'status': lifecycle.INSPECTION}

    result = svc.resume(rec, actor=7)

    svc.records.set_status.assert_called_once_with(3, lifecycle.INSPECTION, 7)

    update_args = svc.records.update.call_args.args
    assert update_args[0] == 3
    payload = update_args[1]
    assert payload == {
        'hold_prior_status': None,
        'hold_reason': None,
        'hold_note': None,
        'held_at': None,
        'held_by': None,
    }

    svc.events.log.assert_called_once_with(
        3, 'resumed', 7, {'restored_to': lifecycle.INSPECTION}
    )

    assert result is svc.records.update.return_value


def test_resume_from_non_on_hold_raises():
    svc = _service()
    rec = {'id': 4, 'status': lifecycle.PENDING_EVALUATION}

    with pytest.raises(ValueError):
        svc.resume(rec, actor=7)

    svc.records.set_status.assert_not_called()
    svc.records.update.assert_not_called()
    svc.events.log.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# Route tests: POST /records/<id>/hold + POST /records/<id>/resume
#
# Called as plain function calls (hold.hold_record(100), not via the test
# client) inside app.test_request_context(), matching the established
# pattern for this codebase's permission-gated route tests (see
# tests/test_dms_file_download_company_access.py,
# tests/test_buyback_intake_error.py). The permission gate
# (@v2_permission_required) and the route body each read their OWN
# module-level `current_user` binding (core.roles.decorators.current_user
# and buyback.routes.hold.current_user respectively), and _guard_company's
# _permitted_company_ids() reads buyback.routes._shared's own `current_user`
# binding — so a test that wants a consistent "logged-in as X" story must
# patch all three.
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(
        secret_key='test-secret-key-for-tests',
        database_url=os.environ.get('DATABASE_URL', 'postgresql://localhost/defaultdb'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['LOGIN_DISABLED'] = True
    return application


class _Admin:
    """Authenticated admin: passes the @v2_permission_required gate (admin
    bypass -> g.permission_scope = 'all') and is used as the route's own
    current_user (current_user.id becomes the actor on hold/resume)."""
    id = 9
    company_id = 3
    is_authenticated = True
    is_admin = True
    can_access_settings = True


class _NoPermUser:
    """Authenticated, but no admin flag and no role -> the permission gate
    itself denies with 403 before the route body (and its repo/service
    mocks) ever runs."""
    id = 11
    company_id = 3
    is_authenticated = True
    is_admin = False
    can_access_settings = False
    role_id = None


def _record(**overrides):
    base = {
        'id': 100, 'company_id': 3, 'status': lifecycle.PENDING_EVALUATION,
        'created_by': 42, 'record_code': 'BB-TEST01',
    }
    base.update(overrides)
    return base


def _hold_ctx(record, *, actor=None, permitted_company_ids=None):
    """Build the (module, repo, service, patches) tuple shared by every
    hold/resume route test: the triple current_user patch, a mocked
    records_repo returning `record`, a mocked service, and a muted
    notify_held (so no real email/push fires). `patches` is a list of
    not-yet-entered patch.object(...) context managers — apply with
    `_patched(patches)`."""
    from buyback.routes import hold
    from core.roles import decorators

    actor = actor or _Admin()
    repo = MagicMock()
    repo.get_by_id.return_value = record
    service = MagicMock()

    patches = [
        patch.object(decorators, 'current_user', actor),
        patch.object(hold, 'current_user', actor),
        patch.object(hold._shared, 'current_user', actor),
        patch.object(hold._shared, 'records_repo', repo),
        patch.object(hold._shared, 'service', service),
        patch.object(hold, 'notify_held'),
    ]
    if permitted_company_ids is not None:
        patches.append(
            patch.object(hold._shared, '_permitted_company_ids',
                         return_value=permitted_company_ids)
        )
    return hold, repo, service, patches


def _patched(patches):
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


def _unwrap(resp):
    """Route handlers return either a bare jsonify(...) (implicit 200) or a
    (jsonify(...), status) tuple -> normalize to (body, status)."""
    return resp if isinstance(resp, tuple) else (resp, 200)


def test_hold_route_happy_path(app):
    record = _record()
    hold, repo, service, patches = _hold_ctx(record)
    updated = _record(status=lifecycle.ON_HOLD, hold_reason='Poze lipsă')
    service.hold.return_value = updated

    with app.test_request_context(json={'reason': 'Poze lipsă', 'note': 'lipsesc 3 poze'}):
        with _patched(patches):
            resp = hold.hold_record(100)
            # notify_held must be checked INSIDE the patch scope — it's a
            # local `hold.py` import, so the patch.object(hold, ...) mock is
            # only reachable via `hold.notify_held` while still patched;
            # outside the `with`, that name reverts to the real function.
            hold.notify_held.assert_called_once_with(updated, 'Poze lipsă', 'lipsesc 3 poze', 9)

    body, status = _unwrap(resp)
    data = body.get_json()
    assert status == 200
    assert data['success'] is True
    assert data['record']['status'] == lifecycle.ON_HOLD
    service.hold.assert_called_once_with(record, 'Poze lipsă', 'lipsesc 3 poze', 9)


def test_hold_route_non_active_status_returns_409(app):
    record = _record(status=lifecycle.BOUGHT)
    hold, repo, service, patches = _hold_ctx(record)
    service.hold.side_effect = ValueError("Cannot hold a record in status 'BOUGHT'")

    with app.test_request_context(json={'reason': 'Poze lipsă'}):
        with _patched(patches):
            resp = hold.hold_record(100)
            hold.notify_held.assert_not_called()

    body, status = _unwrap(resp)
    assert status == 409
    assert body.get_json()['success'] is False


@pytest.mark.parametrize('payload', [{}, {'reason': ''}, {'reason': '   '}, {'reason': 123}])
def test_hold_route_missing_or_empty_reason_returns_400(app, payload):
    record = _record()
    hold, repo, service, patches = _hold_ctx(record)

    with app.test_request_context(json=payload):
        with _patched(patches):
            resp = hold.hold_record(100)

    body, status = _unwrap(resp)
    assert status == 400
    service.hold.assert_not_called()


def test_hold_route_no_permission_returns_403(app):
    record = _record()
    hold, repo, service, patches = _hold_ctx(record, actor=_NoPermUser())

    with app.test_request_context(json={'reason': 'Poze lipsă'}):
        with _patched(patches):
            resp = hold.hold_record(100)

    body, status = _unwrap(resp)
    assert status == 403
    service.hold.assert_not_called()


def test_hold_route_cross_company_returns_403(app):
    record = _record(company_id=8)
    hold, repo, service, patches = _hold_ctx(record, permitted_company_ids={3})

    with app.test_request_context(json={'reason': 'Poze lipsă'}):
        with _patched(patches):
            resp = hold.hold_record(100)

    body, status = _unwrap(resp)
    assert status == 403
    service.hold.assert_not_called()


def test_hold_route_notify_failure_does_not_block_the_hold(app):
    """notify_held is best-effort (fires AFTER the hold already committed):
    a raising notifier must not turn a successful hold into an error
    response."""
    record = _record()
    hold, repo, service, patches = _hold_ctx(record)
    updated = _record(status=lifecycle.ON_HOLD)
    service.hold.return_value = updated

    with app.test_request_context(json={'reason': 'Poze lipsă'}):
        with _patched(patches):
            hold.notify_held.side_effect = Exception('smtp down')
            resp = hold.hold_record(100)

    body, status = _unwrap(resp)
    assert status == 200
    assert body.get_json()['success'] is True
    service.hold.assert_called_once()


def test_resume_route_happy_path(app):
    record = _record(status=lifecycle.ON_HOLD, hold_prior_status=lifecycle.INSPECTION)
    hold, repo, service, patches = _hold_ctx(record)
    updated = _record(status=lifecycle.INSPECTION, hold_prior_status=None)
    service.resume.return_value = updated

    with app.test_request_context():
        with _patched(patches):
            resp = hold.resume_record(100)

    body, status = _unwrap(resp)
    data = body.get_json()
    assert status == 200
    assert data['success'] is True
    assert data['record']['status'] == lifecycle.INSPECTION
    service.resume.assert_called_once_with(record, 9)


def test_resume_route_not_on_hold_returns_409(app):
    record = _record(status=lifecycle.PENDING_EVALUATION)
    hold, repo, service, patches = _hold_ctx(record)
    service.resume.side_effect = ValueError('Record 100 is not on hold')

    with app.test_request_context():
        with _patched(patches):
            resp = hold.resume_record(100)

    body, status = _unwrap(resp)
    assert status == 409
    assert body.get_json()['success'] is False


def test_resume_route_cross_company_returns_403(app):
    record = _record(company_id=8, status=lifecycle.ON_HOLD)
    hold, repo, service, patches = _hold_ctx(record, permitted_company_ids={3})

    with app.test_request_context():
        with _patched(patches):
            resp = hold.resume_record(100)

    body, status = _unwrap(resp)
    assert status == 403
    service.resume.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# Final-review fix wave: cancel-from-ON_HOLD must be a legal transition
# (not a 409), must clear the hold_* bookkeeping, and hold_reason must
# never overflow the VARCHAR(100) column.
# ─────────────────────────────────────────────────────────────────────────

def test_on_hold_to_cancelled_transition_allowed():
    assert lifecycle.is_valid_transition('ON_HOLD', 'CANCELLED')
    # existing ON_HOLD transitions must still be intact
    assert lifecycle.is_valid_transition('ON_HOLD', 'INSPECTION')
    assert lifecycle.is_valid_transition('ON_HOLD', 'PENDING_EVALUATION')
    assert lifecycle.is_valid_transition('ON_HOLD', 'INITIAL_OFFER')
    assert lifecycle.is_valid_transition('ON_HOLD', 'FINAL_OFFER')


def test_transition_on_hold_to_cancelled_clears_hold_fields():
    svc = _service()
    rec = {
        'id': 10, 'status': lifecycle.ON_HOLD,
        'hold_prior_status': lifecycle.INSPECTION, 'hold_reason': 'Poze lipsă',
        'hold_note': 'lipsesc poze', 'held_at': 'some-ts', 'held_by': 3,
    }
    svc.records.set_status.return_value = {**rec, 'status': lifecycle.CANCELLED}
    svc.records.update.return_value = {**rec, 'status': lifecycle.CANCELLED}

    svc.transition(rec, lifecycle.CANCELLED, actor=9)

    svc.records.set_status.assert_called_once_with(10, lifecycle.CANCELLED, 9)

    update_args = svc.records.update.call_args.args
    assert update_args[0] == 10
    payload = update_args[1]
    assert payload['hold_prior_status'] is None
    assert payload['hold_reason'] is None
    assert payload['hold_note'] is None
    assert payload['held_at'] is None
    assert payload['held_by'] is None
    # existing CANCELLED bookkeeping (resolution timestamp) preserved
    assert payload['closed_at'] is not None


def test_hold_reason_truncated_to_100_chars():
    svc = _service()
    rec = {'id': 11, 'status': lifecycle.INSPECTION}

    svc.hold(rec, 'x' * 150, 'note', actor=9)

    payload = svc.records.update.call_args.args[1]
    assert payload['hold_reason'] == 'x' * 100
    assert len(payload['hold_reason']) == 100
