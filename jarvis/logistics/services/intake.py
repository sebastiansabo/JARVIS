"""Intake service — turns one jarvis-alpha event into a vehicle + task,
idempotently (Task 2 of the spine plan).

`apply_event()` is a pure orchestration layer over the Task 1 repositories
(no SQL here): it resolves the acting company, looks up a trigger_code's
rule handler in `rules.RULES`, and lets that handler make the full
create/update/duplicate decision. Every event is logged via
IntakeEventRepository regardless of outcome, including events with no
matching rule (`result: "ignored"`).

**Stale-event ordering guard (Task 4):** before a known trigger_code is
ever dispatched to its handler, `apply_event` checks whether an order's
vehicle row already exists and, if so, whether this event is *older* than
the last one applied to it (`event_ts < vehicle.last_event_ts`). A stale
event never reaches a handler — it's logged as `ignored` and nothing is
touched. This is what keeps a late/out-of-order jarvis-alpha delivery from
clobbering a human-confirmed field (design spec §2 acceptance test 3): the
guard only blocks events that are *strictly* older, never a same-timestamp
resend of the identical event — that's still dispatched, so a handler's own
dedup logic (e.g. `handle_transport_in_derulare`'s `duplicate` result) is
unaffected.
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
        vehicle_repo = LogisticsVehicleRepository()
        # order_ref is globally UNIQUE (see vehicle_repo docstring) — no
        # company_id filter, matching the lookup convention every handler
        # in rules.py already uses.
        existing_vehicle = vehicle_repo.get_vehicle_by_order_ref(order_ref)

        if existing_vehicle is not None and _is_stale_event(
            event_ts, existing_vehicle.get('last_event_ts')
        ):
            outcome = {'result': _RESULT_IGNORED, 'vehicle_id': existing_vehicle['id']}
        else:
            ctx = RuleContext(
                order_ref=order_ref,
                payload=payload,
                event_ts=event_ts,
                company_id=company_id,
                vehicle_repo=vehicle_repo,
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


def _is_stale_event(event_ts: Optional[int], last_event_ts: Optional[int]) -> bool:
    """True when `event_ts` is strictly older than the vehicle's
    `last_event_ts` — a late/out-of-order jarvis-alpha delivery that must
    never reach a rule handler.

    Deliberately strict-less-than, not `<=`: a *resend of the identical
    event* (same `event_ts` as the one already applied) is not "stale", it's
    a duplicate — handlers already own that decision (e.g.
    `handle_transport_in_derulare` returns `duplicate` for a repeat
    `Transport in derulare` on an existing order) and must still run.

    Either side missing means there's nothing to compare against, so the
    event can't be judged stale.
    """
    if event_ts is None or last_event_ts is None:
        return False
    return event_ts < last_event_ts
