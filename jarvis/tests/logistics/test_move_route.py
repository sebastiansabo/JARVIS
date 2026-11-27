"""Route-level auth regression for POST /api/logistics/tasks/<id>/move —
Task 8 of the spine plan.

move_task() itself (the gate logic) is covered by test_move_blocat.py; this
file locks in the *route's own* authorization gate, which has real logic the
service layer never sees:
  - cross-tenant company-scope (this codebase has a history of cross-tenant
    IDOR bugs reaching prod — see the KAM/CRM/CarPark IDOR fixes),
  - the fail-CLOSED null-company case (`None == None` would otherwise match a
    task whose company_id is also NULL),
  - `to_status` enum validation (the status column has no DB CHECK
    constraint; a bogus value would make the card vanish from get_board()).

Auth setup mirrors jarvis/tests/dept_pulse/test_dept_pulse_routes.py: a
minimal Flask app with the real `logistics_bp` registered, `LOGIN_DISABLED`
so @login_required is a no-op, and `current_user` monkeypatched in BOTH
route modules that read it — `logistics.routes.vehicles` (where
`_user_company_id` lives) and `logistics.routes.tasks` (the actor lookup).

Real DB (localhost/defaultdb via conftest probe); seeds under the sentinel
company_id=990002 (TEST_COMPANY_ID); `logistics_cleanup` cascade-deletes it.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/logistics/test_move_route.py -v
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from flask import Flask  # noqa: E402

from database import get_cursor, get_db, release_db  # noqa: E402
from logistics import logistics_bp  # noqa: E402
import logistics.routes.tasks as tasks_routes  # noqa: E402
import logistics.routes.vehicles as vehicles_routes  # noqa: E402
from logistics.repositories.task_repository import TaskRepository  # noqa: E402
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository  # noqa: E402

from .conftest import TEST_COMPANY_ID  # noqa: E402

# A second sentinel company — a caller "logged in" as this one must NOT be
# able to move TEST_COMPANY_ID's task. Distinct id so a cross-tenant leak
# would be visible.
_OTHER_COMPANY_ID = 990003

_MOVE_URL = '/api/logistics/tasks/{task_id}/move'


class _FakeUser:
    """Minimal current_user stand-in: just the attributes the route reads
    (`company_id` for the scope gate, `name`/`email` for the history actor,
    `is_authenticated` for completeness)."""

    def __init__(self, company_id):
        self.company_id = company_id
        self.name = 'Test Mover'
        self.email = 'mover@example.com'
        self.is_authenticated = True


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.register_blueprint(logistics_bp)
    flask_app.config['TESTING'] = True
    flask_app.config['LOGIN_DISABLED'] = True  # @login_required -> no-op
    return flask_app


def _client_as(app, monkeypatch, company_id):
    """A test client whose current_user (in BOTH route modules) is a
    _FakeUser for `company_id`."""
    user = _FakeUser(company_id)
    monkeypatch.setattr(vehicles_routes, 'current_user', user)
    monkeypatch.setattr(tasks_routes, 'current_user', user)
    return app.test_client()


@pytest.fixture
def seeded_task(require_real_db, logistics_cleanup):
    """One vehicle + its De făcut task under TEST_COMPANY_ID."""
    vehicle = LogisticsVehicleRepository().create_vehicle({
        'order_ref': 'AW-MOVE-ROUTE-01',
        'destinatie': 'Intern',
        'etapa_parc': 'În tranzit',
        'company_id': TEST_COMPANY_ID,
    })
    task = TaskRepository().create_task({
        'vehicle_id': vehicle['id'],
        'action': 'Recepționează mașina',
        'type': 'Recepție',
        'company_id': TEST_COMPANY_ID,
    })
    return task


def _status_of(task_id):
    return TaskRepository().get_task_by_id(task_id)['status']


def test_cross_company_caller_forbidden_no_state_change(app, monkeypatch, seeded_task):
    """A caller from a DIFFERENT company than the task's -> 403, task
    untouched."""
    client = _client_as(app, monkeypatch, _OTHER_COMPANY_ID)

    r = client.post(_MOVE_URL.format(task_id=seeded_task['id']), json={'to_status': 'În lucru'})

    assert r.status_code == 403
    assert _status_of(seeded_task['id']) == 'De făcut'  # no state change


def test_null_company_caller_forbidden(app, monkeypatch, seeded_task):
    """A caller with company_id=None moving a real-company task -> 403, task
    untouched. (This passes with or without the hardening — the task's real
    company_id is already != None; the null==null hole is locked in by the
    next test.)"""
    client = _client_as(app, monkeypatch, None)

    r = client.post(_MOVE_URL.format(task_id=seeded_task['id']), json={'to_status': 'În lucru'})

    assert r.status_code == 403
    assert _status_of(seeded_task['id']) == 'De făcut'


def test_null_company_caller_and_null_company_task_forbidden(app, monkeypatch, require_real_db):
    """THE hardened case: a null-company caller moving a task whose own
    company_id is also NULL. Without the explicit `caller_company_id is None`
    guard, `None != None` is False -> the move would be allowed (the exact
    cross-tenant hole the fail-closed check plugs). Must be 403, task
    untouched.

    The null-company vehicle isn't swept by `logistics_cleanup` (which keys
    off company_id = TEST_COMPANY_ID), so this test owns its teardown: delete
    the vehicle (cascades to the task) in a finally."""
    vehicle = LogisticsVehicleRepository().create_vehicle({
        'order_ref': 'AW-MOVE-ROUTE-NULLCO',
        'destinatie': 'Intern',
        'etapa_parc': 'În tranzit',
        'company_id': None,
    })
    try:
        task = TaskRepository().create_task({
            'vehicle_id': vehicle['id'],
            'action': 'Recepționează mașina',
            'type': 'Recepție',
            'company_id': None,
        })
        client = _client_as(app, monkeypatch, None)

        r = client.post(_MOVE_URL.format(task_id=task['id']), json={'to_status': 'În lucru'})

        assert r.status_code == 403
        assert _status_of(task['id']) == 'De făcut'  # no state change
    finally:
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('DELETE FROM logistics_vehicles WHERE id = %s', (vehicle['id'],))
            conn.commit()
        finally:
            release_db(conn)


def test_same_company_bogus_to_status_rejected(app, monkeypatch, seeded_task):
    """A same-company caller passing a to_status outside the four board
    columns -> 400 (the enum guard), task untouched."""
    client = _client_as(app, monkeypatch, TEST_COMPANY_ID)

    r = client.post(_MOVE_URL.format(task_id=seeded_task['id']), json={'to_status': 'Teletransportat'})

    assert r.status_code == 400
    assert _status_of(seeded_task['id']) == 'De făcut'


def test_same_company_valid_move_succeeds(app, monkeypatch, seeded_task):
    """Positive control: a same-company caller moving to a legit status ->
    200, status actually changes."""
    client = _client_as(app, monkeypatch, TEST_COMPANY_ID)

    r = client.post(_MOVE_URL.format(task_id=seeded_task['id']), json={'to_status': 'În lucru'})

    assert r.status_code == 200
    assert r.get_json()['task']['status'] == 'În lucru'
    assert _status_of(seeded_task['id']) == 'În lucru'
