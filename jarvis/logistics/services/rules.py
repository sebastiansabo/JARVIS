"""Mapping-rule dispatch for the intake pipeline — trigger_code -> handler.

A plain dict registry (not an if/elif chain) so a later task can add the
`ETA actualizat` rule (Task 3 of the spine plan) by adding one entry to
RULES, without touching the dispatch logic in intake.py or any existing
handler.

Each handler owns the full idempotency decision for its own trigger_code —
e.g. the default "create" handler below treats a pre-existing vehicle as a
duplicate, while a future "update" handler (ETA actualizat) would instead
require the vehicle to already exist. That's why handlers receive the repos
and return the complete `{"result": ..., ...}` outcome rather than a central
dedup check living in intake.py.

No SQL here — all DB access goes through the Task 1 repositories bundled
into RuleContext.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository

# Exact Romanian-diacritic enum values the design spec fixes for this rule.
_RECEPTIE_TASK_TYPE = 'Recepție'
_RECEPTIE_ACTION = 'Recepționează mașina'
_ETAPA_IN_TRANZIT = 'În tranzit'
_HISTORY_CREATED = 'created'
_HISTORY_ETA_UPDATED = 'eta_updated'
_HISTORY_ETA_NO_OPEN_TASK = 'eta_no_open_task'
_INTAKE_ACTOR = 'intake:jarvis-alpha'


@dataclass
class RuleContext:
    """Everything a rule handler needs, bundled so dispatch stays a plain
    dict lookup instead of threading a long argument list through intake.py."""
    order_ref: str
    payload: Dict[str, Any]
    event_ts: Optional[int]
    company_id: int
    vehicle_repo: LogisticsVehicleRepository
    task_repo: TaskRepository
    history_repo: HistoryRepository


RuleHandler = Callable[[RuleContext], Dict[str, Any]]


def _apply_confirmed_guard(vehicle: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Strip any key from `patch` that's marked confirmed (truthy) in
    `vehicle['confirmed_fields']` before it reaches `update_vehicle`.

    Human-confirmed data at Recepție (bay, VIN, keys, condition…) is
    authoritative over the intake feed (design spec §2 acceptance test 3) —
    an intake-driven update to an EXISTING vehicle's columns must never
    silently overwrite it. The ordering guard in intake.py already stops
    the one required scenario (a stale event) before any handler runs;
    this is the belt-and-suspenders for any vehicle-column update a
    handler makes on a *non-stale* event.
    """
    confirmed = vehicle.get('confirmed_fields') or {}
    return {k: v for k, v in patch.items() if not confirmed.get(k)}


def _create_vehicle_with_reception_task(ctx: RuleContext) -> Dict[str, Any]:
    """Create a new vehicle (etapa_parc='În tranzit', destinatie from
    payload) plus its first Recepție task (due_at from payload['eta']), and
    record the `created` history entry.

    Shared by `handle_transport_in_derulare` (every new order) and
    `handle_eta_actualizat`'s first-seen upsert — an `ETA actualizat` event
    can be the very first thing jarvis-alpha sends for an order, in which
    case it must stand up the same vehicle+card shape, just with the ETA
    already attached.
    """
    vehicle = ctx.vehicle_repo.create_vehicle({
        'order_ref': ctx.order_ref,
        'etapa_parc': _ETAPA_IN_TRANZIT,
        'destinatie': ctx.payload.get('destinatie'),
        'company_id': ctx.company_id,
        'last_event_ts': ctx.event_ts,
    })

    task = ctx.task_repo.create_task({
        'vehicle_id': vehicle['id'],
        'action': _RECEPTIE_ACTION,
        'type': _RECEPTIE_TASK_TYPE,
        'due_at': ctx.payload.get('eta'),
        'company_id': ctx.company_id,
    })

    ctx.history_repo.record_history(
        vehicle['id'], _HISTORY_CREATED, None, vehicle,
        actor=_INTAKE_ACTOR, company_id=ctx.company_id,
    )

    return {'result': 'created', 'vehicle_id': vehicle['id'], 'task_id': task['id']}


def handle_transport_in_derulare(ctx: RuleContext) -> Dict[str, Any]:
    """`Transport in derulare` — a new order entering the yard: create the
    vehicle (etapa_parc='În tranzit', destinatie from payload) plus one
    Recepție task. Idempotent by order_ref: if a vehicle for this order
    already exists (a repeat delivery of the same event), this is a
    duplicate — no second vehicle, no second task.
    """
    existing = ctx.vehicle_repo.get_vehicle_by_order_ref(ctx.order_ref)
    if existing:
        return {'result': 'duplicate', 'vehicle_id': existing['id']}

    return _create_vehicle_with_reception_task(ctx)


def handle_eta_actualizat(ctx: RuleContext) -> Dict[str, Any]:
    """`ETA actualizat` — jarvis-alpha pushed a revised ETA for an order.

    If the order is already known, update its still-open Recepție task's
    due_at in place (never a second card) and record an `eta_updated`
    history entry. If the order is unknown (no vehicle row yet — an ETA
    event can arrive before `Transport in derulare` does), this is the
    order's first-seen upsert: create the vehicle + Recepție task exactly
    like `Transport in derulare` would, via the same shared helper.
    """
    existing = ctx.vehicle_repo.get_vehicle_by_order_ref(ctx.order_ref)
    if existing is None:
        return _create_vehicle_with_reception_task(ctx)

    task = ctx.task_repo.get_open_reception_task(existing['id'])
    if task is None:
        # No open Recepție card left on this order (e.g. already received) —
        # nothing to move, so the event had no effect: `ignored` (not
        # `updated`, which would mislead downstream consumers). Still record
        # an audit row so the trail captures the late ETA push.
        ctx.history_repo.record_history(
            existing['id'], _HISTORY_ETA_NO_OPEN_TASK,
            None, {'eta': ctx.payload.get('eta')},
            actor=_INTAKE_ACTOR, company_id=ctx.company_id,
        )
        return {'result': 'ignored', 'vehicle_id': existing['id'], 'task_id': None}

    old_due_at = task.get('due_at')
    new_eta = ctx.payload.get('eta')
    updated_task = ctx.task_repo.update_task(task['id'], {'due_at': new_eta})

    # Stamp last_event_ts so a *later* stale/out-of-order event for this
    # order is caught by intake.py's ordering guard (deferred from Task 3 —
    # the create path already sets last_event_ts; this is the only other
    # path that applies an event to an existing vehicle, so it must too).
    # Guarded on event_ts not being None: it's Optional on RuleContext, and
    # writing a NULL here would erase the vehicle's existing guard value,
    # letting a later genuinely-stale event slip past intake.py's check.
    if ctx.event_ts is not None:
        vehicle_patch = _apply_confirmed_guard(existing, {'last_event_ts': ctx.event_ts})
        if vehicle_patch:
            ctx.vehicle_repo.update_vehicle(existing['id'], vehicle_patch)

    ctx.history_repo.record_history(
        existing['id'], _HISTORY_ETA_UPDATED,
        {'due_at': old_due_at}, {'due_at': new_eta},
        actor=_INTAKE_ACTOR, company_id=ctx.company_id,
    )

    return {
        'result': 'updated',
        'vehicle_id': existing['id'],
        'task_id': updated_task['id'],
    }


# trigger_code -> handler. Each handler owns its own idempotency semantics
# (see module docstring) — adding a rule is one entry here plus a
# `handle_*` function, with no changes to intake.py's dispatch.
RULES: Dict[str, RuleHandler] = {
    'Transport in derulare': handle_transport_in_derulare,
    'ETA actualizat': handle_eta_actualizat,
}


def get_handler(code: str) -> Optional[RuleHandler]:
    """The handler registered for this trigger_code, or None if there is no
    rule for it — intake.py treats None as `result: "ignored"`."""
    return RULES.get(code)
