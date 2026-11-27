"""Move engine — the Kanban board's single write path for transitioning a
task between the four fixed `logistics_tasks.status` columns (Task 8 of the
spine plan).

`move_task()` is a pure orchestration layer over the Task 1 repositories (no
SQL here, per repo convention): it fetches the task to learn its *current*
status and vehicle, dispatches to the one gate that applies for this
transition (if any), applies the resulting patch via `TaskRepository.
update_task`, and records exactly one `logistics_vehicle_history` row —
EVERY successful move writes history, gated or not.

Task 9 (Recepție -> Finalizat, "Confirmă recepția") is the one gate that also
needs to touch the VEHICLE row, not just the task: `_build_patch()` validates
`ctx['reception']` (raising before any write if incomplete, or if the supplied
location/bay isn't a positive id belonging to the task's own company — a
cross-tenant IDOR guard) and stashes the validated dict on the patch under a
key `TaskRepository.update_task` doesn't recognize (so it's silently dropped
from the task UPDATE); `move_task()` pulls it back off the patch afterward and
hands it to `_confirm_reception()`, which sets vin/location_id/position_id on
the vehicle, marks them `confirmed_fields`-true, flips `etapa_parc`, and writes
a dedicated `reception_confirmed` history row alongside the generic
`task_moved` one.

Those four reception writes (task status + task_moved history + vehicle update
+ reception_confirmed history) run inside ONE `execute_many()` transaction, so
a mid-write failure rolls back all of them — the task's `Finalizat` status and
the vehicle's confirmed bay can never end up disagreeing.

On `confirmed_fields`: in the CURRENT spine nothing it protects is actually at
risk — the one out-of-order-delivery scenario (an older intake event arriving
after reception) is already stopped upstream by `apply_event`'s `event_ts`
ordering guard before any handler runs, and no intake handler updates an
*existing* vehicle's columns anyway (`handle_transport_in_derulare`'s existing
path returns `duplicate` untouched). Marking them true is defensive for a
FUTURE handler that DOES update an existing vehicle: Task 4's
`_apply_confirmed_guard` (unit-proven by `test_apply_confirmed_guard_strips_
only_confirmed_fields`) would then strip a confirmed column from that handler's
patch.

Task 10 (Îngrijire -> Finalizat, "measured-result gate" — e.g. a 12V battery
check) is the sibling of Task 9's reception gate, minus the vehicle write:
`_build_patch()` validates `ctx['measured'] = {"value": number, "unit": str}`
via `_require_measured_fields()` (a real number — `int`/`float`, never
`bool` — and a non-empty, stripped `unit`), raising BEFORE any write if
either is missing/wrong-typed. `measured_result` IS a `TASK_FIELDS` column
(Task 1), so it rides straight through to the task UPDATE; the SAME
validated dict is also stashed on the patch under a `measured` key
`TaskRepository.update_task` doesn't recognize (Task 9's `reception`
side-channel pattern) — `move_task()` pops it back off and, once present,
routes to `_finalize_care_measurement()`, which writes the task-status+
measured_result UPDATE and a dedicated `care_measured` history row
(carrying `value`/`unit`/`status`) atomically via `execute_many()`. Unlike
reception, there's no separate generic `task_moved` row for this path — the
one `care_measured` row IS this move's history entry.
"""
from typing import Any, Dict, Optional

from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.location_repository import LocationRepository, PositionRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository

_BLOCAT = 'Blocat'
_FINALIZAT = 'Finalizat'
_RECEPTIE = 'Recepție'
_INGRIJIRE = 'Îngrijire'
_ETAPA_IN_PREGATIRE = 'În pregătire'
_HISTORY_TASK_MOVED = 'task_moved'
_HISTORY_RECEPTION_CONFIRMED = 'reception_confirmed'
_HISTORY_CARE_MEASURED = 'care_measured'
_DEFAULT_ACTOR = 'user:unknown'

# ctx['reception'] = {"vin","location_id","position_id","keys","condition"} --
# every field is required (§ task-9 brief). Of these, only the first three
# have a logistics_vehicles column to write/confirm today; 'keys'/'condition'
# have no column yet (see migrations/domains/schema_logistics.py) so they're
# recorded in the reception_confirmed history entry only -- not persisted on
# the vehicle row, and not added to confirmed_fields (there's nothing on the
# vehicle for a later intake event to clobber).
_RECEPTION_FIELDS = ('vin', 'location_id', 'position_id', 'keys', 'condition')
_RECEPTION_VEHICLE_FIELDS = ('vin', 'location_id', 'position_id')


class MoveError(Exception):
    """Raised when a move is rejected by a gate (e.g. `Blocat` without a
    responsible person + next action). Carries a stable machine-readable
    `code` — routes map this straight to a 400 `{error: code}` body; the
    frontend never has to parse a human sentence to know what went wrong."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _require_block_fields(ctx: Dict[str, Any]) -> Dict[str, str]:
    """Validate ctx['block'] = {"responsible", "next_action"}, both
    non-empty (after stripping whitespace) -- raises MoveError otherwise.
    Returns the validated {"responsible", "next_action"} dict."""
    block = ctx.get('block') or {}
    responsible = (block.get('responsible') or '').strip()
    next_action = (block.get('next_action') or '').strip()
    if not responsible or not next_action:
        raise MoveError('block_requires_responsible_and_next_action')
    return {'responsible': responsible, 'next_action': next_action}


def _require_reception_fields(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Validate ctx['reception'] = {"vin","location_id","position_id","keys",
    "condition"} -- every field present and non-empty -- raises
    MoveError('reception_incomplete') otherwise. String values are stripped
    before the emptiness check (and the stripped value is what's returned);
    non-string values (e.g. an int `keys` count, including 0) pass through
    unchanged as long as they're not None."""
    reception = ctx.get('reception') or {}
    validated: Dict[str, Any] = {}
    for field in _RECEPTION_FIELDS:
        value = reception.get(field)
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == '':
            raise MoveError('reception_incomplete')
        validated[field] = value
    return validated


def _require_measured_fields(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Validate ctx['measured'] = {"value": number, "unit": str} -- `value`
    must be a real number (`int`/`float`, NOT `bool` -- booleans are ints in
    Python and must never pass as a measurement), `unit` a non-empty string
    after stripping -- raises MoveError('measured_result_required')
    otherwise. Returns the validated {"value", "unit"} dict (unit stripped,
    value passed through unchanged)."""
    measured = ctx.get('measured') or {}
    value = measured.get('value')
    unit = measured.get('unit')
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MoveError('measured_result_required')
    if not isinstance(unit, str) or not unit.strip():
        raise MoveError('measured_result_required')
    return {'value': value, 'unit': unit.strip()}


def _is_positive_int(value: Any) -> bool:
    """A real positive id -- a plain int (not a bool; `True`/`False` are ints
    in Python and must never pass as ids 1/0) strictly greater than zero."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _require_valid_bay(task: Dict[str, Any], reception: Dict[str, Any]) -> None:
    """Tenant + integrity guard for the reception's location_id/position_id,
    run BEFORE any write -- raises MoveError('reception_invalid_bay') unless:
      - both ids are positive ints (closes the 0/negative footgun too);
      - both the location AND the position belong to the task's own company
        (a cross-tenant IDOR guard: a caller must not be able to park a
        vehicle at another company's location/bay); and
      - the position actually belongs to the given location.
    This is a cross-tenant write guard of the same class as the move route's
    company-scope check -- enforced here in the service so it holds no matter
    which caller reaches move_task()."""
    location_id = reception['location_id']
    position_id = reception['position_id']
    if not _is_positive_int(location_id) or not _is_positive_int(position_id):
        raise MoveError('reception_invalid_bay')

    company_id = task.get('company_id')
    location = LocationRepository().get_location_by_id(location_id)
    position = PositionRepository().get_position_by_id(position_id)
    if location is None or position is None:
        raise MoveError('reception_invalid_bay')
    if location.get('company_id') != company_id or position.get('company_id') != company_id:
        raise MoveError('reception_invalid_bay')
    if position.get('location_id') != location_id:
        raise MoveError('reception_invalid_bay')


def _build_patch(task: Dict[str, Any], to_status: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """The field patch for this transition -- always includes `status`, plus
    whatever gate-specific fields this (to_status, task.type) pair requires.

    Raises MoveError if a required gate's ctx is missing/incomplete, BEFORE
    any write happens (this is called before `TaskRepository.update_task` in
    move_task()). Gates are dispatched on `to_status` first (Blocat applies
    regardless of task type), then `task['type']` for the Task 9/10 seams --
    see module docstring.
    """
    patch: Dict[str, Any] = {'status': to_status}

    if to_status == _BLOCAT:
        block = _require_block_fields(ctx)
        patch['block_reason'] = block['responsible']
        patch['block_next_action'] = block['next_action']
        return patch

    if to_status == _FINALIZAT and task.get('type') == _RECEPTIE:
        # "Confirmă recepția" (Task 9). Both checks raise BEFORE any write:
        # all five fields present, then the location/bay tenant-validated
        # against the task's company. The validated dict is stashed under a
        # key TASK_FIELDS doesn't whitelist -- move_task() pops it back off
        # before calling update_task, so it never reaches the task UPDATE;
        # it's move_task()'s signal to run the transactional
        # _confirm_reception() instead of the plain task-only write path.
        reception = _require_reception_fields(ctx)
        _require_valid_bay(task, reception)
        patch['reception'] = reception
        return patch

    if to_status == _FINALIZAT and task.get('type') == _INGRIJIRE:
        # Measured-result gate (Task 10): a care task (e.g. a 12V battery
        # check) can't finalize without a real reading. Validated BEFORE any
        # write, same discipline as Blocat/Recepție above. `measured_result`
        # is a real TASK_FIELDS column (Task 1) so it rides straight through
        # to the task UPDATE; the `measured` key is Task 10's own
        # side-channel (mirrors Task 9's `reception`) -- not a TASK_FIELDS
        # column, popped back off by move_task() to decide the atomic
        # _finalize_care_measurement() path and to build the
        # care_measured history row.
        measured = _require_measured_fields(ctx)
        patch['measured_result'] = measured
        patch['measured'] = measured
        return patch

    # Any other transition (De făcut/În lucru/Finalizat with no matching
    # gate) is a plain status change.
    return patch


def _confirm_reception(task: Dict[str, Any], to_status: str, task_patch: Dict[str, Any],
                       old_status: str, reception: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """The whole "Confirmă recepția" write, run ATOMICALLY in one
    execute_many() transaction (unlike the plain move path, which auto-commits
    the task update + its history row independently). All four statements --
    the task-status update, the generic `task_moved` history row, the vehicle
    update (vin/location_id/position_id + confirmed_fields + etapa_parc out of
    'În tranzit'), and the dedicated `reception_confirmed` history row -- share
    one cursor, so any failure rolls back ALL of them: the task never lands in
    `Finalizat` with the vehicle left unconfirmed, and vice versa.

    `keys`/`condition` have no vehicle column, so they appear only in the
    reception_confirmed history row (see _RECEPTION_VEHICLE_FIELDS). Returns
    the updated task dict (move_task()'s return value for this path).

    The old-vehicle read (for the confirmed_fields merge + history old-value)
    happens before the transaction opens -- it's a read, and the bay was
    already tenant-validated in _build_patch, so there's nothing a concurrent
    writer could change here that this move should refuse."""
    task_id = task['id']
    vehicle_id = task['vehicle_id']
    company_id = task.get('company_id')

    task_repo = TaskRepository()
    vehicle_repo = LogisticsVehicleRepository()
    history_repo = HistoryRepository()

    old_vehicle = vehicle_repo.get_vehicle_by_id(vehicle_id) or {}

    confirmed_fields = dict(old_vehicle.get('confirmed_fields') or {})
    for field in _RECEPTION_VEHICLE_FIELDS:
        confirmed_fields[field] = True

    vehicle_patch: Dict[str, Any] = {field: reception[field] for field in _RECEPTION_VEHICLE_FIELDS}
    vehicle_patch['confirmed_fields'] = confirmed_fields
    vehicle_patch['etapa_parc'] = _ETAPA_IN_PREGATIRE

    moved_old = {'status': old_status, 'task_id': task_id}
    moved_new = {'status': to_status, 'task_id': task_id}

    reception_old = {field: old_vehicle.get(field) for field in _RECEPTION_VEHICLE_FIELDS}
    reception_old['etapa_parc'] = old_vehicle.get('etapa_parc')
    reception_new = {
        'vin': reception['vin'],
        'location_id': reception['location_id'],
        'position_id': reception['position_id'],
        'keys': reception['keys'],
        'condition': reception['condition'],
        'etapa_parc': _ETAPA_IN_PREGATIRE,
    }

    def _work(cursor):
        updated = task_repo.update_task(task_id, task_patch, cursor=cursor)
        history_repo.record_history(
            vehicle_id, _HISTORY_TASK_MOVED, moved_old, moved_new,
            actor=actor, company_id=company_id, cursor=cursor,
        )
        vehicle_repo.update_vehicle(vehicle_id, vehicle_patch, cursor=cursor)
        history_repo.record_history(
            vehicle_id, _HISTORY_RECEPTION_CONFIRMED, reception_old, reception_new,
            actor=actor, company_id=company_id, cursor=cursor,
        )
        return updated

    return task_repo.execute_many(_work)


def _finalize_care_measurement(task: Dict[str, Any], task_patch: Dict[str, Any],
                                old_status: str, measured: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """The whole measured-result finalize (Task 10), run ATOMICALLY in one
    execute_many() transaction: the task UPDATE (status + measured_result)
    and the dedicated `care_measured` history row share one cursor, so a
    mid-write failure rolls back both -- the task can never land in
    `Finalizat` with no history row proving what was measured, or vice versa.

    Unlike `_confirm_reception`, there's no vehicle row to touch here, and
    no separate generic `task_moved` row -- `care_measured` (which already
    carries the resulting `status`) IS this move's one history entry.
    Returns the updated task dict (move_task()'s return value for this
    path)."""
    task_id = task['id']
    vehicle_id = task['vehicle_id']
    company_id = task.get('company_id')

    task_repo = TaskRepository()
    history_repo = HistoryRepository()

    old_value = {'status': old_status, 'task_id': task_id}
    new_value = {
        'status': _FINALIZAT,
        'task_id': task_id,
        'value': measured['value'],
        'unit': measured['unit'],
    }

    def _work(cursor):
        updated = task_repo.update_task(task_id, task_patch, cursor=cursor)
        history_repo.record_history(
            vehicle_id, _HISTORY_CARE_MEASURED, old_value, new_value,
            actor=actor, company_id=company_id, cursor=cursor,
        )
        return updated

    return task_repo.execute_many(_work)


def move_task(task_id: int, to_status: str, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Transition one Kanban card to `to_status`, enforcing whichever gate
    applies to this (current task, to_status) pair, and recording one audit
    history row on every successful move.

    `ctx` carries whatever a gate needs — for `to_status == 'Blocat'`:
    `{"block": {"responsible": str, "next_action": str}}`. `ctx['actor']`
    (optional) names who's making the move, for the history row; defaults
    to a generic placeholder when the caller doesn't supply one.

    Raises:
      ValueError  — task_id doesn't exist.
      MoveError   — a gate rejected the move (e.g. Blocat missing fields);
                    nothing is written, the task stays exactly where it was.

    Returns the updated task dict.
    """
    ctx = ctx or {}
    task_repo = TaskRepository()
    history_repo = HistoryRepository()

    task = task_repo.get_task_by_id(task_id)
    if task is None:
        raise ValueError(f'task {task_id} not found')

    old_status = task['status']
    patch = _build_patch(task, to_status, ctx)  # raises MoveError before any write
    # Task 9/10's side-channels (see _build_patch) -- neither is a
    # TaskRepository column, popped off before the task UPDATE so they can't
    # leak into it.
    reception = patch.pop('reception', None)
    measured = patch.pop('measured', None)
    actor = ctx.get('actor') or _DEFAULT_ACTOR

    # Reception-confirm is its own atomic write path: the task status +
    # task_moved history + vehicle update + reception_confirmed history all
    # commit together or not at all (see _confirm_reception). Measured-
    # result finalize is likewise atomic but simpler (see
    # _finalize_care_measurement): task status+measured_result + one
    # care_measured history row. Every other move is a plain task update +
    # one task_moved history row.
    if reception is not None:
        return _confirm_reception(task, to_status, patch, old_status, reception, actor)
    if measured is not None:
        return _finalize_care_measurement(task, patch, old_status, measured, actor)

    updated = task_repo.update_task(task_id, patch)

    history_new: Dict[str, Any] = {'status': to_status, 'task_id': task_id}
    for field in ('block_reason', 'block_next_action'):
        if field in patch:
            history_new[field] = patch[field]

    history_repo.record_history(
        task['vehicle_id'],
        _HISTORY_TASK_MOVED,
        {'status': old_status, 'task_id': task_id},
        history_new,
        actor=actor,
        company_id=task.get('company_id'),
    )

    return updated
