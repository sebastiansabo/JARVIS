"""BuyBackService — orchestration layer for the buyback lifecycle.

Ties together RecordRepository, OfferRepository and EventRepository behind
three guarded operations:

  - transition(): the ONE sanctioned path for flipping a record's status.
    Rejects any move `lifecycle.is_valid_transition()` doesn't allow, and
    always pairs the status flip with an audit event.
  - post_offer(): enforces that an offer round can only be opened while the
    record is in the matching pre-offer status (`initial` round requires
    PENDING_EVALUATION, `final` round requires INSPECTION), and that a
    record never has two undecided ("pending") offers open at once.
  - record_decision(): enforces that a decision can only be recorded against
    the record's single latest offer, and only while that offer is still
    'pending' and the record is sitting in an offer-awaiting-decision status
    (INITIAL_OFFER/FINAL_OFFER). This is what blocks a stale/superseded
    client link (or a decision replayed after the record already moved on)
    from mutating state a second time.

Ruling R2 (import ordering/safety): `notifier` is injected via __init__ and
defaults to None. This module does NOT import `buyback.services.email` (or
any notifier module) at top level — that module doesn't exist yet (Task 13
adds it) and importing it here would create an ordering/circular-import
hazard. Callers that want offer-posted notifications construct their own
notifier (duck-typed: `send_offer_email(record, offer)` +
`notify_sales(record)`) and pass it in; tests exercise this service with
notifier=None throughout.

The actual CarPark hand-off on a final-offer acceptance (creating/linking
the purchased vehicle) is deliberately NOT done here — record_decision()
only moves the record to BOUGHT. That finalize step is a separate
route/service (Task 14).
"""
from datetime import datetime, timezone

from buyback import lifecycle
from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.offer_repository import OfferRepository
from buyback.repositories.event_repository import EventRepository

# Which pre-offer status a given offer round may be opened from. A
# 'consignment' proposal opens from PENDING_EVALUATION (the same pre-offer
# stage as an initial buy offer) — it's an alternative to buying, offered
# before any inspection.
_ROUND_REQUIRED_STATUS = {
    'initial': lifecycle.PENDING_EVALUATION,
    'final': lifecycle.INSPECTION,
    'consignment': lifecycle.PENDING_EVALUATION,
}

# Which post-offer status an offer round lands the record in once posted.
_ROUND_TARGET_STATUS = {
    'initial': lifecycle.INITIAL_OFFER,
    'final': lifecycle.FINAL_OFFER,
    'consignment': lifecycle.CONSIGNMENT_OFFER,
}

# Statuses a record may be placed ON_HOLD from — the four "active" stages
# where work-in-progress can stall (missing photos, awaiting client, etc).
# BOUGHT/LOST/CANCELLED are terminal; ON_HOLD itself is excluded (no-op).
_HOLDABLE = (lifecycle.PENDING_EVALUATION, lifecycle.INITIAL_OFFER,
             lifecycle.INSPECTION, lifecycle.FINAL_OFFER)


class BuyBackService:

    def __init__(self, notifier=None):
        self.records = RecordRepository()
        self.offers = OfferRepository()
        self.events = EventRepository()
        self.notifier = notifier

    def transition(self, record, new_status, actor, details=None) -> dict:
        """Flip `record`'s status to `new_status` iff the lifecycle state
        machine allows it, logging a `status_changed` audit event alongside
        the flip. Raises ValueError on any illegal transition."""
        old_status = record['status']
        if not lifecycle.is_valid_transition(old_status, new_status):
            raise ValueError(
                f"Illegal transition {old_status!r} -> {new_status!r} "
                f"for buyback record {record['id']}"
            )
        updated = self.records.set_status(record['id'], new_status, actor)
        # Stamp (or clear) closed_at so the UI's resolved-window logic
        # (Active/Arhivă 72h linger) has a real resolution timestamp for
        # LOST/CANCELLED — set_status alone only touches status + updated_at,
        # which left closed_at perpetually NULL. BOUGHT keeps bought_at (stamped
        # at finalize) as its resolution time; reopening a LOST record clears
        # closed_at again so it's treated as in-progress once more.
        changes = {}
        if new_status in (lifecycle.LOST, lifecycle.CANCELLED):
            changes['closed_at'] = datetime.now(timezone.utc)
        elif new_status == lifecycle.PENDING_EVALUATION and old_status in (
            lifecycle.LOST, lifecycle.CANCELLED
        ):
            changes['closed_at'] = None
        # Leaving ON_HOLD (e.g. cancelling a held record) must clear the hold
        # bookkeeping fields — they're hidden in the UI once status != ON_HOLD,
        # but a stale hold_* would otherwise linger on the row forever.
        if old_status == lifecycle.ON_HOLD:
            changes.update({
                'hold_prior_status': None, 'hold_reason': None,
                'hold_note': None, 'held_at': None, 'held_by': None,
            })
        if changes:
            updated = self.records.update(record['id'], changes)
        self.events.log(
            record['id'], 'status_changed', actor,
            {'from': old_status, 'to': new_status, **(details or {})},
        )
        # Notify the record's creator of the status change (config-driven,
        # skip-self, best-effort — local import keeps buyback_service a leaf).
        try:
            from buyback.services.notifications import notify_owner
            notify_owner(record, 'status_changed', actor, new_status=new_status)
        except Exception:
            pass
        return updated

    def force_status(self, record, new_status, actor, note=None) -> dict:
        """Admin/Manager escape hatch: set `record`'s status to ANY valid
        status, DELIBERATELY bypassing the lifecycle state machine (unlike
        transition(), which rejects illegal moves).

        This only ever touches the buyback_records row — it NEVER creates,
        links, deletes or mutates a CarPark vehicle or an offer. In particular
        forcing BOUGHT does NOT perform the CarPark hand-off (that stays the
        finalize route's job); it only stamps bought_at so the Arhivă
        resolution-window logic has a timestamp. A record already handed off
        (carpark_vehicle_id set) keeps that link and its CarPark vehicle
        untouched regardless of the forced status.

        Bookkeeping mirrors transition():
          - LOST/CANCELLED      → stamp closed_at (resolution time).
          - any other status    → clear closed_at (back to in-progress).
          - BOUGHT (and no prior bought_at) → stamp bought_at.

        Logs a `status_changed` audit event flagged `forced: True` (+ the
        optional free-text `note`) so the override is distinguishable from a
        normal lifecycle transition in the Istoric timeline, and notifies the
        record's creator. Raises ValueError on an unknown target status or a
        no-op (new == current)."""
        old_status = record['status']
        if new_status not in lifecycle.STATUS_LABELS:
            raise ValueError(f"Unknown status {new_status!r}")
        if new_status == old_status:
            raise ValueError(
                f"Record {record['id']} is already in status {new_status!r}"
            )

        updated = self.records.set_status(record['id'], new_status, actor)

        now = datetime.now(timezone.utc)
        changes = {}
        if new_status in (lifecycle.LOST, lifecycle.CANCELLED):
            changes['closed_at'] = now
        else:
            # Any active status (incl. BOUGHT, whose resolution time is
            # bought_at, not closed_at) is no longer "closed".
            changes['closed_at'] = None
        if new_status == lifecycle.BOUGHT and record.get('bought_at') is None:
            changes['bought_at'] = now
        updated = self.records.update(record['id'], changes)

        details = {'from': old_status, 'to': new_status, 'forced': True}
        note = (note or '').strip()
        if note:
            details['note'] = note[:1000]
        self.events.log(record['id'], 'status_changed', actor, details)

        try:
            from buyback.services.notifications import notify_owner
            notify_owner(record, 'status_changed', actor, new_status=new_status)
        except Exception:
            pass
        return updated

    def hold(self, record, reason, note, actor) -> dict:
        """Put `record` ON_HOLD from one of the four active statuses
        (PENDING_EVALUATION/INITIAL_OFFER/INSPECTION/FINAL_OFFER), stamping
        the prior status (so resume() can restore it exactly), a reason,
        an optional free-text note, and who/when. Logs a `held` audit
        event. Raises ValueError if the record isn't in a holdable
        status (terminal BOUGHT/LOST/CANCELLED, or already ON_HOLD)."""
        if record['status'] not in _HOLDABLE:
            raise ValueError(f"Cannot hold a record in status {record['status']!r}")
        self.records.set_status(record['id'], lifecycle.ON_HOLD, actor)
        updated = self.records.update(record['id'], {
            'hold_prior_status': record['status'], 'hold_reason': reason[:100],
            'hold_note': (note or '').strip()[:1000] or None,
            'held_at': datetime.now(timezone.utc), 'held_by': actor,
        })
        self.events.log(record['id'], 'held', actor, {'reason': reason, 'note': note})
        return updated

    def resume(self, record, actor) -> dict:
        """Take `record` off ON_HOLD, restoring the EXACT status it was
        held from (`hold_prior_status`), and clearing the hold bookkeeping
        fields. Logs a `resumed` audit event. Raises ValueError if the
        record isn't currently ON_HOLD."""
        if record['status'] != lifecycle.ON_HOLD:
            raise ValueError(f"Record {record['id']} is not on hold")
        prior = record.get('hold_prior_status') or lifecycle.PENDING_EVALUATION
        self.records.set_status(record['id'], prior, actor)
        updated = self.records.update(record['id'], {
            'hold_prior_status': None, 'hold_reason': None, 'hold_note': None,
            'held_at': None, 'held_by': None,
        })
        self.events.log(record['id'], 'resumed', actor, {'restored_to': prior})
        return updated

    def post_offer(self, record, offer_type, payload, actor) -> dict:
        """Open a new offer round (`offer_type` 'initial' or 'final') on
        `record`. Enforces that the record is sitting in the status the
        round expects, and that there is no other still-pending offer on
        this record (one-pending-per-record). Advances the record's status
        to match the round, then fires notifier hooks if one is set.

        CORRECTION CASE: a `final` offer may also be re-posted while the
        record is ALREADY in FINAL_OFFER, to amend an agreed final price
        before the seller decides. In that case the existing pending final
        offer is superseded (marked 'superseded' — NOT 'declined', so the
        record is NOT sent to LOST) and replaced by the new one, and the
        record STAYS in FINAL_OFFER (no transition). This is the sanctioned
        way to change a final price once posted — otherwise the price is
        unreachable (offers are immutable and the lifecycle has no
        FINAL_OFFER → INSPECTION edge)."""
        required_status = _ROUND_REQUIRED_STATUS.get(offer_type)
        if required_status is None:
            raise ValueError(f"Unknown offer_type: {offer_type!r}")

        # A 'final' round re-opened while already in FINAL_OFFER corrects the
        # posted price in place, rather than advancing from INSPECTION.
        correcting_final = (
            offer_type == 'final'
            and record['status'] == _ROUND_TARGET_STATUS['final']
        )

        if not correcting_final and record['status'] != required_status:
            raise ValueError(
                f"Cannot post a {offer_type!r} offer while record "
                f"{record['id']} is {record['status']!r} (expected "
                f"{required_status!r})"
            )

        pending = self.offers.pending_for_record(record['id'])
        if pending is not None:
            if correcting_final:
                # Replace the still-pending final offer: mark it superseded
                # (distinct from a seller 'declined', which would move the
                # record to LOST) so the one-pending-per-record invariant
                # holds for the replacement offer created below.
                self.offers.record_decision(pending['id'], 'superseded', actor)
            else:
                raise ValueError(
                    f"Record {record['id']} already has a pending offer — "
                    "cannot open a second one"
                )

        # A consignment proposal carries its terms (already validated + JSON-
        # serialized by the route) in payload['consignment_terms'] rather than
        # the amount/vat/valid_until of a buy offer. Store the terms on the
        # offer; use owner_price as the headline amount_eur (amount_eur is NOT
        # NULL — fall back to 0 when no owner_price was proposed), with no
        # vat_status/valid_until.
        consignment_terms = None
        amount_eur = payload.get('amount_eur')
        vat_status = payload.get('vat_status')
        valid_until = payload.get('valid_until')
        if offer_type == 'consignment':
            consignment_terms = payload.get('consignment_terms')
            amount_eur = (consignment_terms or {}).get('owner_price') or 0
            vat_status = None
            valid_until = None

        offer = self.offers.create(
            record['id'], offer_type,
            amount_eur, vat_status, valid_until, payload.get('notes'), actor,
            consignment_terms=consignment_terms,
        )

        if correcting_final:
            # Price correction: the record is already FINAL_OFFER, so there's
            # no status change (FINAL_OFFER → FINAL_OFFER isn't a lifecycle
            # transition). Log a distinct audit event for the Istoric timeline
            # instead, carrying the superseded offer id for traceability.
            self.events.log(
                record['id'], 'offer_corrected', actor,
                {'offer_id': offer['id'],
                 'superseded_offer_id': pending['id'] if pending else None},
            )
        else:
            record = self.transition(
                record, _ROUND_TARGET_STATUS[offer_type], actor,
                {'offer_id': offer['id']},
            )

        # The notifier hooks render a seller-facing BUY offer (email + sales
        # heads-up); a consignment proposal is not a buy offer, so skip them —
        # the in-app status-change notification still fires inside transition().
        if self.notifier is not None and offer_type != 'consignment':
            # Hand the notifier the FRESH record (post-transition status),
            # not the stale pre-offer one — the email/sales hooks render
            # status, so they must see INITIAL_OFFER/FINAL_OFFER, not the
            # PENDING_EVALUATION/INSPECTION the record carried on entry.
            self.notifier.send_offer_email(record, offer)
            self.notifier.notify_sales(record)

        return offer

    def record_decision(self, record, offer_id, decision, actor, decline_reason=None) -> dict:
        """Record the seller's `decision` ('accepted'/'declined') on
        `offer_id`, then advance the record's status accordingly. Guards
        against acting on anything but the record's single latest offer,
        only while it's still 'pending', only while the record is actually
        sitting in an offer-awaiting-decision status, and only for a
        recognized `decision` value — this is what rejects stale/superseded
        or already-decided offer links. The `decision` membership check is
        part of THIS pre-mutation guard on purpose: validating it after the
        DB write would persist a bogus client_decision (e.g. 'maybe') and
        strand the offer permanently non-'pending', unreachable by this very
        guard on any retry (mirrors how post_offer validates offer_type
        before it mutates)."""
        latest = self.offers.latest_for_record(record['id'])
        if (
            decision not in ('accepted', 'declined')
            or latest is None
            or latest['id'] != offer_id
            or latest['client_decision'] != 'pending'
            or record['status'] not in (
                lifecycle.INITIAL_OFFER, lifecycle.FINAL_OFFER, lifecycle.CONSIGNMENT_OFFER
            )
        ):
            raise ValueError(
                f"Cannot record decision {decision!r} on offer {offer_id} for "
                f"record {record['id']}: unrecognized decision, or not the "
                f"latest pending offer, or record is not awaiting a decision"
            )

        # Accepting a consignment proposal performs the external CarPark custody
        # hand-off, which must SUCCEED before we stamp the offer accepted / move
        # the record — so a dup-VIN or mid-hand-off fault leaves the offer
        # pending and the record in CONSIGNMENT_OFFER (retryable), never a
        # half-accepted offer with no vehicle. Handled ahead of the generic
        # record_decision stamp below for exactly that ordering (mirrors
        # buyback.routes.custody's validate→hand-off→link sequence).
        if decision == 'accepted' and record['status'] == lifecycle.CONSIGNMENT_OFFER:
            return self._accept_consignment(record, latest, actor)

        self.offers.record_decision(offer_id, decision, actor, decline_reason)

        if decision == 'declined':
            # Also covers a declined CONSIGNMENT_OFFER → LOST (lifecycle allows
            # CONSIGNMENT_OFFER → LOST), same "didn't happen" outcome as a
            # declined buy offer.
            updated_record = self.records.update(record['id'], {'lost_reason': decline_reason})
            return self.transition(
                updated_record, lifecycle.LOST, actor,
                {'offer_id': offer_id, 'decline_reason': decline_reason},
            )

        if decision == 'accepted' and record['status'] == lifecycle.INITIAL_OFFER:
            return self.transition(record, lifecycle.INSPECTION, actor, {'offer_id': offer_id})

        if decision == 'accepted' and record['status'] == lifecycle.FINAL_OFFER:
            # Actual CarPark hand-off (creating/linking the purchased
            # vehicle) is a separate route/service — Task 14.
            return self.transition(record, lifecycle.BOUGHT, actor, {'offer_id': offer_id})

        raise ValueError(
            f"Unhandled decision {decision!r} for record {record['id']} "
            f"in status {record['status']!r}"
        )

    def _accept_consignment(self, record, offer, actor) -> dict:
        """Seller accepted a consignment proposal: perform the CarPark custody
        hand-off from the proposed terms, link the created vehicle, stamp the
        offer accepted, and move the record to CONSIGNAT.

        The hand-off runs FIRST (before stamping the decision) so a dup/invalid
        VIN — ValueError raised verbatim from VehicleService.create_vehicle, the
        route turns it into a 409 — or any other mid-hand-off fault leaves the
        offer pending and the record in CONSIGNMENT_OFFER, i.e. retryable. Only
        once a vehicle exists do we stamp `accepted`, write carpark_vehicle_id,
        and transition. Imports are LOCAL to keep this service a leaf
        (carpark_handoff pulls in carpark; custody is a route that imports
        _shared → this service — a module-level import of either would cycle)."""
        from buyback.services.carpark_handoff import handoff_to_carpark_custody
        from buyback.routes.custody import validate_custody_agreement

        # Re-coerce the JSON-stored terms (floats/ISO strings) back to the
        # Decimal/date types ConsignmentRepository expects — the same validator
        # the propose route ran, idempotent on its own serialized output.
        agreement = validate_custody_agreement(offer.get('consignment_terms') or {})
        vehicle = handoff_to_carpark_custody(record, agreement, actor)  # may raise ValueError (dup VIN)

        self.offers.record_decision(offer['id'], 'accepted', actor)
        updated = self.records.update(record['id'], {'carpark_vehicle_id': vehicle['id']})
        return self.transition(
            updated, lifecycle.CONSIGNAT, actor,
            {'offer_id': offer['id'], 'carpark_vehicle_id': vehicle['id']},
        )
