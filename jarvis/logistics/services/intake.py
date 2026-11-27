"""Intake service — turns one jarvis-alpha event into a vehicle + task,
idempotently (Task 2 of the spine plan).

`apply_event()` is a pure orchestration layer over the Task 1 repositories
(no SQL here): it resolves the acting company, looks up a trigger_code's
rule handler in `rules.RULES`, and lets that handler make the full
create/update/duplicate decision. Every event is logged via
IntakeEventRepository regardless of outcome, including events with no
matching rule (`result: "ignored"`).
"""
from typing import Any, Dict, Optional

from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.intake_event_repository import IntakeEventRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository

from logistics.services.rules import RuleContext, get_handler

# Single-company Autoworld scope fallback (AUTOWORLD S.R.L., the holding —
# see migrations/domains/cost_centers_seed.py's SHEET_TO_COMPANY mapping)
# used only when an event's payload doesn't carry an explicit company_id.
# Tests always pass one (TEST_COMPANY_ID) via payload['company_id'].
DEFAULT_COMPANY_ID = 16

_RESULT_IGNORED = 'ignored'


def apply_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Apply one jarvis-alpha intake event.

    event = {"order_ref", "code", "event_ts", "payload"} where payload is a
    dict; `company_id` is read from payload['company_id'], falling back to
    DEFAULT_COMPANY_ID.

    Returns {"result": "created"|"updated"|"duplicate"|"ignored",
    "vehicle_id"?, "task_id"?}. Idempotent by order_ref — see rules.py for
    the per-trigger_code idempotency decision.
    """
    order_ref = event['order_ref']
    code = event['code']
    event_ts: Optional[int] = event.get('event_ts')
    payload: Dict[str, Any] = event.get('payload') or {}
    company_id = payload.get('company_id', DEFAULT_COMPANY_ID)

    handler = get_handler(code)
    if handler is None:
        outcome: Dict[str, Any] = {'result': _RESULT_IGNORED}
    else:
        ctx = RuleContext(
            order_ref=order_ref,
            payload=payload,
            event_ts=event_ts,
            company_id=company_id,
            vehicle_repo=LogisticsVehicleRepository(),
            task_repo=TaskRepository(),
            history_repo=HistoryRepository(),
        )
        outcome = handler(ctx)

    IntakeEventRepository().log(
        order_ref=order_ref,
        code=code,
        payload=payload,
        event_ts=event_ts,
        result=outcome['result'],
        company_id=company_id,
    )

    return outcome
