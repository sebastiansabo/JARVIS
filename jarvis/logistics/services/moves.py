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
`ctx['reception']` (raising before any write if incomplete) and stashes it on
the patch under a key `TaskRepository.update_task` doesn't recognize (so it's
silently dropped from the task UPDATE); `move_task()` pulls it back off the
patch afterward and hands it to `_confirm_reception()`, which sets vin/
location_id/position_id on the vehicle, marks them `confirmed_fields`-true
(protecting them from a later stale intake overwrite — Task 4's
`_apply_confirmed_guard`), flips `etapa_parc`, and writes a dedicated
`reception_confirmed` history row alongside the generic `task_moved` one.

Gate seam for a later task (deliberately left open, not hardcoded shut):
  - Task 10 adds a `type == 'Îngrijire'` branch for `to_status == 'Finalizat'`
    (measured-result gate) — another `elif` in `_build_patch()` keyed off
    `task['type']`, alongside Blocat and Recepție.
"""
from typing import Any, Dict, Optional

from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository

_BLOCAT = 'Blocat'
_FINALIZAT = 'Finalizat'
_RECEPTIE = 'Recepție'
_ETAPA_IN_PREGATIRE = 'În pregătire'
_HISTORY_TASK_MOVED = 'task_moved'
_HISTORY_RECEPTION_CONFIRMED = 'reception_confirmed'
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
        # "Confirmă recepția" (Task 9). The validated dict is stashed under
        # a key TASK_FIELDS doesn't whitelist -- move_task() pops it back off
        # before calling update_task, so it never reaches the task UPDATE;
        # it's move_task()'s signal to also run _confirm_reception() once the
        # task's own status write succeeds.
        patch['reception'] = _require_reception_fields(ctx)
        return patch

    # Seam for Task 10 (Îngrijire -> Finalizat: measured-result gate) -- keys
    # off task['type'] for this same `elif` chain, without touching
    # move_task() itself. Any other transition (De făcut/În lucru/Finalizat
    # with no matching gate) is a plain status change.

    return patch


def _confirm_reception(task: Dict[str, Any], reception: Dict[str, Any],
                        history_repo: HistoryRepository, actor: str) -> None:
    """Task 9's vehicle-side effects, run from move_task() once the task's
    own status write has succeeded. Sets vin/location_id/position_id on the
    vehicle, merges each into confirmed_fields as `true` (so Task 4's
    `_apply_confirmed_guard` protects them from a later stale/out-of-order
    intake overwrite), flips etapa_parc out of 'În tranzit', and records a
    dedicated `reception_confirmed` history row -- `keys`/`condition` appear
    only in that history row (see _RECEPTION_VEHICLE_FIELDS)."""
    vehicle_repo = LogisticsVehicleRepository()
    vehicle_id = task['vehicle_id']
    old_vehicle = vehicle_repo.get_vehicle_by_id(vehicle_id) or {}

    confirmed_fields = dict(old_vehicle.get('confirmed_fields') or {})
    for field in _RECEPTION_VEHICLE_FIELDS:
        confirmed_fields[field] = True

    vehicle_patch: Dict[str, Any] = {field: reception[field] for field in _RECEPTION_VEHICLE_FIELDS}
    vehicle_patch['confirmed_fields'] = confirmed_fields
    vehicle_patch['etapa_parc'] = _ETAPA_IN_PREGATIRE

    vehicle_repo.update_vehicle(vehicle_id, vehicle_patch)

    old_snapshot = {field: old_vehicle.get(field) for field in _RECEPTION_VEHICLE_FIELDS}
    old_snapshot['etapa_parc'] = old_vehicle.get('etapa_parc')
    new_snapshot = {
        'vin': reception['vin'],
        'location_id': reception['location_id'],
        'position_id': reception['position_id'],
        'keys': reception['keys'],
        'condition': reception['condition'],
        'etapa_parc': _ETAPA_IN_PREGATIRE,
    }
    history_repo.record_history(
        vehicle_id, _HISTORY_RECEPTION_CONFIRMED, old_snapshot, new_snapshot,
        actor=actor, company_id=task.get('company_id'),
    )


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
    # Task 9's side-channel (see _build_patch) -- never a TaskRepository
    # column, popped off before the task UPDATE so it can't leak into it.
    reception = patch.pop('reception', None)
    actor = ctx.get('actor') or _DEFAULT_ACTOR

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

    if reception is not None:
        _confirm_reception(task, reception, history_repo, actor)

    return updated
