"""Dispo Service — guarded lifecycle transitions for CarPark Dispo.

This is where the Dispo module's business logic lives (routes in Task 2.3
must stay thin: parse the request, call a method here, map exceptions to
HTTP status codes). Every mutating method follows the same shape:

  1. load the vehicle
  2. TENANT GUARD — the vehicle must belong to the caller's company
  3. validate the action's own guards (required fields, doc checklist, ...)
  4. apply DB writes (reservation/vehicle field updates)
  5. call VehicleService.change_status() for the status move itself, which
     enforces the TRANSITIONS matrix and writes carpark_status_history
  6. notify

Exception convention (deliberately narrow, so routes can map with a simple
except/except): a cross-company vehicle raises PermissionError (-> 403);
everything else that's the caller's fault (vehicle not found, missing
fields, an unmet business guard) raises ValueError (-> 400). ValueError
messages for the two machine-checked guards are prefixed so a route/client
can branch on them without string-matching prose:
  - `sell()`  ->  "LOW_MARGIN: ..."      (not blocking — retry with confirm_low_margin=True)
  - `deliver()` -> "MISSING_PV_LIVRARE: ..." (hard-blocking — no override)

Tenant note (carried forward from Task 2.1): DocumentRepository and
ReservationRepository have no company_id column of their own, so ownership
is only enforceable by going vehicle-first — every method here loads the
vehicle via VehicleRepository and checks vehicle['company_id'] before
touching any document/reservation row for it.
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from carpark.repositories.document_repository import DocumentRepository
from carpark.repositories.reservation_repository import ReservationRepository
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.services.vehicle_service import VehicleService
from carpark.services.publishing_service import PublishingService
from core.notifications.notify import notify_user

logger = logging.getLogger('jarvis.carpark')


# Required-document checklist, keyed by lifecycle point (not by vehicle
# status — a vehicle detail view wants to see the *whole* checklist at
# once, not just the slice relevant to its current stage). Only the
# DELIVERED bucket is a hard gate (enforced directly by deliver() via
# DocumentRepository.has_type, independent of this map); the rest are soft
# — they surface in checklist()'s `missing` list but never block a
# transition.
#   intake             (soft) — expected once the car is acquired
#   SOLD                (soft) — expected once the sale is recorded
#   DELIVERED           (HARD) — blocks deliver() when pv_livrare is absent
#   remove_from_stock   (soft) — expected before the car leaves the pipeline
REQUIRED_DOCS: Dict[str, List[str]] = {
    'intake': ['pv_intrare', 'factura_achizitie'],
    'SOLD': ['contract_vanzare'],
    'DELIVERED': ['pv_livrare'],
    'remove_from_stock': ['factura_vanzare'],
}

# Statuses a vehicle must be in before it can be pulled out of the pipeline.
_STOCK_REMOVABLE_STATUSES = {'DELIVERED', 'TRANSFERRED', 'SCRAPPED', 'RETURNED'}

# Fields cleared when reopen() moves a vehicle out of SOLD/DELIVERED — a
# reopened vehicle no longer has a valid sale record. buyer_client_id is
# whitelisted on VehicleRepository.update(); buyer_name/sale_type are not
# (see module docstring bottom note / task report — pre-existing gap from
# the Task 1.1 migration, not fixed here since repos are out of scope for
# this task).
_SALE_FIELDS_TO_CLEAR = ('sale_price', 'sale_date', 'sale_type', 'buyer_client_id', 'buyer_name')


def _uid(user) -> Optional[int]:
    """Extract a user id from either a dict or an object (e.g. flask_login's
    current_user) — the route layer may hand either through."""
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get('id')
    return getattr(user, 'id', None)


def _uname(user) -> Optional[str]:
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get('name')
    return getattr(user, 'name', None)


class DispoService:
    """Guarded status transitions + side effects for the CarPark Dispo module.

    Collaborators are injected with real defaults so routes can simply do
    `DispoService()`, while tests can inject mocks for every dependency
    (no DB access needed to exercise the business logic).
    """

    def __init__(self,
                 document_repo: DocumentRepository = None,
                 reservation_repo: ReservationRepository = None,
                 vehicle_repo: VehicleRepository = None,
                 vehicle_service: VehicleService = None,
                 publishing_service: PublishingService = None,
                 notify_fn=None):
        self._document_repo = document_repo or DocumentRepository()
        self._reservation_repo = reservation_repo or ReservationRepository()
        self._vehicle_repo = vehicle_repo or VehicleRepository()
        self._vehicle_service = vehicle_service or VehicleService()
        self._publishing_service = publishing_service or PublishingService()
        self._notify = notify_fn or notify_user

    # ── shared guards ──

    def _load_vehicle_or_raise(self, vehicle_id: int, company_id: int) -> Dict[str, Any]:
        """Load the vehicle and enforce tenant ownership. Always call this
        first, before any other validation, per the module's guard order."""
        vehicle = self._vehicle_repo.get_by_id(vehicle_id)
        if not vehicle:
            raise ValueError(f'Vehicle {vehicle_id} not found')
        if vehicle.get('company_id') != company_id:
            raise PermissionError(
                f'Vehicle {vehicle_id} does not belong to company {company_id}')
        return vehicle

    def _notify_vehicle_contacts(self, vehicle: Dict[str, Any], title: str,
                                  message: str = None) -> None:
        """Notify whoever has a stake in this vehicle. The domain doesn't yet
        model a distinct "backoffice" user/queue, so the assigned salesperson
        (the only user reliably associated with a vehicle) is used as the
        single notification target for every lifecycle event, including
        delivery. Silently does nothing when no salesperson is assigned."""
        salesperson_id = vehicle.get('salesperson_user_id')
        if not salesperson_id:
            return
        try:
            self._notify(salesperson_id, title, message=message,
                          entity_type='carpark_vehicle', entity_id=vehicle.get('id'))
        except Exception as e:  # notification failures must never break a transition
            logger.error(f'Dispo notify failed for vehicle {vehicle.get("id")}: {e}')

    # ── RESERVE ──

    def reserve(self, vehicle_id: int, company_id: int, user, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an active reservation and move the vehicle to RESERVED."""
        vehicle = self._load_vehicle_or_raise(vehicle_id, company_id)
        data = data or {}

        if not data.get('client_name') and not data.get('client_id'):
            raise ValueError('client_name or client_id is required to reserve a vehicle')
        if not data.get('reservation_end'):
            raise ValueError('reservation_end is required to reserve a vehicle')

        reservation_data = {
            'client_id': data.get('client_id'),
            'client_name': data.get('client_name'),
            'client_company': data.get('client_company'),
            'client_phone': data.get('client_phone'),
            'client_email': data.get('client_email'),
            'reservation_start': data.get('reservation_start'),
            'reservation_end': data.get('reservation_end'),
            'deposit_amount': data.get('deposit_amount'),
            'deposit_paid': data.get('deposit_paid'),
            'notes': data.get('notes'),
            'status': 'active',
            'user_id': _uid(user),
            'created_by': _uid(user),
        }
        reservation = self._reservation_repo.create(vehicle_id, reservation_data)

        updated_vehicle = self._vehicle_service.change_status(
            vehicle_id, 'RESERVED', changed_by=_uid(user),
            notes=f"Reserved for {data.get('client_name') or data.get('client_id')}")

        self._notify_vehicle_contacts(
            vehicle, 'Vehicul rezervat',
            message=f"{vehicle.get('brand', '')} {vehicle.get('model', '')} a fost rezervat".strip())

        return {'vehicle': updated_vehicle, 'reservation': reservation}

    # ── CANCEL RESERVATION ──

    def cancel_reservation(self, vehicle_id: int, company_id: int, user, reason: str) -> Dict[str, Any]:
        """Cancel the active reservation and restore the vehicle's pre-RESERVED
        status, read from the most recent RESERVED entry in status history."""
        vehicle = self._load_vehicle_or_raise(vehicle_id, company_id)

        if not reason:
            raise ValueError('reason is required to cancel a reservation')

        reservation = self._reservation_repo.active_for_vehicle(vehicle_id)
        if not reservation:
            raise ValueError('No active reservation to cancel')

        cancelled = self._reservation_repo.set_status(reservation['id'], 'cancelled')

        prior_status = self._prior_status_before_reserved(vehicle_id)
        updated_vehicle = self._vehicle_service.change_status(
            vehicle_id, prior_status, changed_by=_uid(user), notes=reason,
            allow_reserved_exit=True)

        self._notify_vehicle_contacts(vehicle, 'Rezervare anulată', message=reason)

        return {'vehicle': updated_vehicle, 'reservation': cancelled}

    def _prior_status_before_reserved(self, vehicle_id: int) -> str:
        """Most recent carpark_status_history row with new_status='RESERVED';
        returns its old_status, falling back to READY_FOR_SALE if there's no
        such row (or old_status was somehow empty)."""
        history = self._vehicle_service.get_status_history(vehicle_id) or []
        for entry in history:
            if entry.get('new_status') == 'RESERVED':
                return entry.get('old_status') or 'READY_FOR_SALE'
        return 'READY_FOR_SALE'

    # ── SELL ──

    def sell(self, vehicle_id: int, company_id: int, user, data: Dict[str, Any]) -> Dict[str, Any]:
        """Record the sale, move the vehicle to SOLD, close any active
        reservation, and deactivate its listings. Warns (does not block) on
        low margin unless data['confirm_low_margin'] is truthy."""
        vehicle = self._load_vehicle_or_raise(vehicle_id, company_id)
        data = data or {}

        missing = [f for f in ('sale_price', 'sale_type', 'sale_date') if not data.get(f)]
        if not data.get('buyer_name') and not data.get('buyer_client_id'):
            missing.append('buyer_name or buyer_client_id')
        if missing:
            raise ValueError(f"Missing required fields to sell: {', '.join(missing)}")

        if not data.get('confirm_low_margin'):
            reasons = self._low_margin_reasons(vehicle_id, vehicle, data['sale_price'])
            if reasons:
                raise ValueError('LOW_MARGIN: ' + '; '.join(reasons))

        sale_fields: Dict[str, Any] = {
            'sale_price': data['sale_price'],
            'sale_type': data['sale_type'],
            'sale_date': data['sale_date'],
        }
        # Write buyer keys THROUGH by presence, not truthiness: when the caller
        # sends buyer_client_id (even as an explicit None — a buyer switched
        # from a CRM-linked client to a walk-in / free-text name), we must
        # persist that None to CLEAR the old link. A truthy check would drop
        # the None and leave a stale buyer_client_id pointing at the wrong CRM
        # client while buyer_name shows the new name — silent corruption.
        if 'buyer_client_id' in data:
            sale_fields['buyer_client_id'] = data['buyer_client_id']
        if data.get('buyer_name'):
            sale_fields['buyer_name'] = data['buyer_name']

        self._vehicle_service.update_vehicle(
            vehicle_id, sale_fields, updated_by=_uid(user), updated_by_name=_uname(user))

        updated_vehicle = self._vehicle_service.change_status(
            vehicle_id, 'SOLD', changed_by=_uid(user), notes='Vehicle sold',
            allow_reserved_exit=True)

        active_reservation = self._reservation_repo.active_for_vehicle(vehicle_id)
        if active_reservation:
            self._reservation_repo.set_status(active_reservation['id'], 'converted')

        self._publishing_service.deactivate_all(vehicle_id)

        self._notify_vehicle_contacts(
            vehicle, 'Vehicul vândut',
            message=f"{vehicle.get('brand', '')} {vehicle.get('model', '')} a fost vândut".strip())

        return {'vehicle': updated_vehicle}

    def _low_margin_reasons(self, vehicle_id: int, vehicle: Dict[str, Any],
                             sale_price) -> List[str]:
        """Reasons (if any) this sale would be low-margin: proposed sale_price
        under the vehicle's minimum_price, and/or a negative prospective gross
        margin.

        gross_margin = sale_price - acquisition_price - SUM(cost.amount),
        using the VAT-EXCLUSIVE cost basis so this number reconciles with the
        canonical gross_margin the salesperson sees in the Dispo summary
        table: DispoRepository (dispo_repository.py) computes
        `sale_price - acquisition_price - COALESCE(SUM(amount), 0)` where the
        cost total is `SUM(carpark_vehicle_costs.amount)` — base amounts only,
        excluding the separate vat_amount column. We therefore take
        `get_cost_totals()['total_amount']` (= SUM(amount)) rather than
        `get_profitability()['total_costs']`, which is VAT-INCLUSIVE
        (`total_with_vat` = SUM(amount) + SUM(vat_amount)) and would fire this
        warning against a more pessimistic margin than the dashboard figure,
        leaving the salesperson unable to reconcile the two."""
        reasons: List[str] = []
        sale_price = float(sale_price)

        minimum_price = vehicle.get('minimum_price')
        if minimum_price is not None and sale_price < float(minimum_price):
            reasons.append(f'sale_price {sale_price} is below minimum_price {float(minimum_price)}')

        acquisition_price = float(vehicle.get('acquisition_price') or 0)
        cost_totals = self._vehicle_service.get_cost_totals(vehicle_id) or {}
        total_costs = float(cost_totals.get('total_amount') or 0)  # VAT-exclusive: SUM(amount)
        gross_margin = sale_price - acquisition_price - total_costs
        if gross_margin < 0:
            reasons.append(f'gross margin would be negative ({gross_margin:.2f})')

        return reasons

    # ── DELIVER ──

    def deliver(self, vehicle_id: int, company_id: int, user, data: Dict[str, Any]) -> Dict[str, Any]:
        """Hard-blocked on a missing pv_livrare document. Records delivery_date
        and moves the vehicle to DELIVERED."""
        vehicle = self._load_vehicle_or_raise(vehicle_id, company_id)
        data = data or {}

        if not self._document_repo.has_type(vehicle_id, 'pv_livrare'):
            raise ValueError(
                'MISSING_PV_LIVRARE: proces verbal de livrare document required before delivery')
        if not data.get('delivery_date'):
            raise ValueError('delivery_date is required to deliver a vehicle')

        self._vehicle_service.update_vehicle(
            vehicle_id, {'delivery_date': data['delivery_date']},
            updated_by=_uid(user), updated_by_name=_uname(user))

        updated_vehicle = self._vehicle_service.change_status(
            vehicle_id, 'DELIVERED', changed_by=_uid(user), notes='Vehicle delivered')

        self._notify_vehicle_contacts(
            vehicle, 'Vehicul livrat',
            message=f"{vehicle.get('brand', '')} {vehicle.get('model', '')} a fost livrat".strip())

        return {'vehicle': updated_vehicle}

    # ── REMOVE FROM STOCK ──

    def remove_from_stock(self, vehicle_id: int, company_id: int, user) -> Dict[str, Any]:
        """Flags the vehicle as out of the pipeline. Requires a terminal
        status (DELIVERED/TRANSFERRED/SCRAPPED/RETURNED). Permission
        (can_delete_carpark) is enforced at the route layer — this method
        assumes an already-authorized call and only validates the status
        guard."""
        vehicle = self._load_vehicle_or_raise(vehicle_id, company_id)

        if vehicle.get('status') not in _STOCK_REMOVABLE_STATUSES:
            raise ValueError(
                f"Cannot remove from stock: status {vehicle.get('status')} is not one of "
                f"{sorted(_STOCK_REMOVABLE_STATUSES)}")

        updated_vehicle = self._vehicle_service.update_vehicle(
            vehicle_id, {'stock_removed': True, 'stock_removed_date': date.today()},
            updated_by=_uid(user), updated_by_name=_uname(user))

        self._notify_vehicle_contacts(
            vehicle, 'Vehicul scos din stoc',
            message=f"{vehicle.get('brand', '')} {vehicle.get('model', '')} a fost scos din stoc".strip())

        return {'vehicle': updated_vehicle}

    # ── REOPEN ──

    def reopen(self, vehicle_id: int, company_id: int, user, reason: str,
               target_status: str) -> Dict[str, Any]:
        """Move a vehicle backward in the pipeline (e.g. SOLD -> LISTED after
        a bad sale). Legality of the target status is enforced by
        VehicleService.change_status's TRANSITIONS matrix. Clears sale fields
        (and delivery_date, if applicable) when leaving SOLD/DELIVERED, since
        those no longer describe a real sale."""
        vehicle = self._load_vehicle_or_raise(vehicle_id, company_id)

        if not reason:
            raise ValueError('reason is required to reopen a vehicle')

        old_status = vehicle.get('status')
        if old_status in ('SOLD', 'DELIVERED'):
            clear_fields: Dict[str, Any] = {field: None for field in _SALE_FIELDS_TO_CLEAR}
            if old_status == 'DELIVERED':
                clear_fields['delivery_date'] = None
            self._vehicle_service.update_vehicle(
                vehicle_id, clear_fields, updated_by=_uid(user), updated_by_name=_uname(user))

        updated_vehicle = self._vehicle_service.change_status(
            vehicle_id, target_status, changed_by=_uid(user), notes=reason)

        self._notify_vehicle_contacts(vehicle, 'Vehicul redeschis', message=reason)

        return {'vehicle': updated_vehicle}

    # ── DOCUMENT CHECKLIST ──

    def checklist(self, vehicle_id: int, company_id: int) -> Dict[str, Any]:
        """Full required-document checklist for a vehicle, across every
        lifecycle point in REQUIRED_DOCS (not just its current stage — the
        detail view wants the whole picture). `blocks_delivery` is the one
        actionable hard gate, mirroring deliver()'s own guard."""
        self._load_vehicle_or_raise(vehicle_id, company_id)

        required = list(dict.fromkeys(
            doc_type for docs in REQUIRED_DOCS.values() for doc_type in docs))
        present = self._document_repo.distinct_types(vehicle_id)
        present_set = set(present)
        missing = [doc_type for doc_type in required if doc_type not in present_set]

        return {
            'required': required,
            'present': present,
            'missing': missing,
            'blocks_delivery': 'pv_livrare' not in present_set,
        }
