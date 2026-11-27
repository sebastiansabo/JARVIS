"""Move engine — the Kanban board's single write path for transitioning a
task between the four fixed `logistics_tasks.status` columns (Task 8 of the
spine plan).

`move_task()` is a pure orchestration layer over the Task 1 repositories (no
SQL here, per repo convention): it fetches the task to learn its *current*
status and vehicle, dispatches to the one gate that applies for this
transition (if any), applies the resulting patch via `TaskRepository.
update_task`, and records exactly one `logistics_vehicle_history` row —
EVERY successful move writes history, gated or not.

Gate seams for later tasks (deliberately left open, not hardcoded shut):
  - Task 9 adds a `type == 'Recepție'` branch for `to_status == 'Finalizat'`
    (confirmă recepția — sets vehicle fields + confirmed_fields).
  - Task 10 adds a `type == 'Îngrijire'` branch for `to_status == 'Finalizat'`
    (measured-result gate).
Both slot into `_build_patch()` as additional `elif` branches keyed off
`task['type']`, alongside the Blocat gate this task implements — none of
them need to touch `move_task()`'s fetch/update/history skeleton.
"""
from typing import Any, Dict, Optional

from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.task_repository import TaskRepository

_BLOCAT = 'Blocat'
_HISTORY_TASK_MOVED = 'task_moved'
_DEFAULT_ACTOR = 'user:unknown'


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


def _build_patch(task: Dict[str, Any], to_status: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """The field patch for this transition -- always includes `status`, plus
    whatever gate-specific fields this (to_status, task.type) pair requires.

    Raises MoveError if a required gate's ctx is missing/incomplete. Gates
    are dispatched on `to_status` first (Blocat applies regardless of task
    type), then `task['type']` for the Task 9/10 seams -- see module
    docstring.
    """
    patch: Dict[str, Any] = {'status': to_status}

    if to_status == _BLOCAT:
        block = _require_block_fields(ctx)
        patch['block_reason'] = block['responsible']
        patch['block_next_action'] = block['next_action']
        return patch

    # Seam for Task 9 (Recepție -> Finalizat: "Confirmă recepția") and
    # Task 10 (Îngrijire -> Finalizat: measured-result gate) -- both key off
    # task['type'] for this same `elif` chain, without touching move_task()
    # itself. Any other transition (De făcut/În lucru/Finalizat with no
    # matching gate) is a plain status change.

    return patch


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
        actor=ctx.get('actor') or _DEFAULT_ACTOR,
        company_id=task.get('company_id'),
    )

    return updated
