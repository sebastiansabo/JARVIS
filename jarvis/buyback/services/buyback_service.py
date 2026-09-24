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
from buyback import lifecycle
from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.offer_repository import OfferRepository
from buyback.repositories.event_repository import EventRepository

# Which pre-offer status a given offer round may be opened from.
_ROUND_REQUIRED_STATUS = {
    'initial': lifecycle.PENDING_EVALUATION,
    'final': lifecycle.INSPECTION,
}

# Which post-offer status an offer round lands the record in once posted.
_ROUND_TARGET_STATUS = {
    'initial': lifecycle.INITIAL_OFFER,
    'final': lifecycle.FINAL_OFFER,
}


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
        self.events.log(
            record['id'], 'status_changed', actor,
            {'from': old_status, 'to': new_status, **(details or {})},
        )
        return updated

    def post_offer(self, record, offer_type, payload, actor) -> dict:
        """Open a new offer round (`offer_type` 'initial' or 'final') on
        `record`. Enforces that the record is sitting in the status the
        round expects, and that there is no other still-pending offer on
        this record (one-pending-per-record). Advances the record's status
        to match the round, then fires notifier hooks if one is set."""
        required_status = _ROUND_REQUIRED_STATUS.get(offer_type)
        if required_status is None:
            raise ValueError(f"Unknown offer_type: {offer_type!r}")

        if record['status'] != required_status:
            raise ValueError(
                f"Cannot post a {offer_type!r} offer while record "
                f"{record['id']} is {record['status']!r} (expected "
                f"{required_status!r})"
            )

        if self.offers.pending_for_record(record['id']) is not None:
            raise ValueError(
                f"Record {record['id']} already has a pending offer — "
                "cannot open a second one"
            )

        offer = self.offers.create(
            record['id'], offer_type,
            payload.get('amount_eur'), payload.get('vat_status'),
            payload.get('valid_until'), payload.get('notes'), actor,
        )

        self.transition(
            record, _ROUND_TARGET_STATUS[offer_type], actor,
            {'offer_id': offer['id']},
        )

        if self.notifier is not None:
            self.notifier.send_offer_email(record, offer)
            self.notifier.notify_sales(record)

        return offer

    def record_decision(self, record, offer_id, decision, actor, decline_reason=None) -> dict:
        """Record the seller's `decision` ('accepted'/'declined') on
        `offer_id`, then advance the record's status accordingly. Guards
        against acting on anything but the record's single latest offer,
        only while it's still 'pending', and only while the record is
        actually sitting in an offer-awaiting-decision status — this is
        what rejects stale/superseded or already-decided offer links."""
        latest = self.offers.latest_for_record(record['id'])
        if (
            latest is None
            or latest['id'] != offer_id
            or latest['client_decision'] != 'pending'
            or record['status'] not in (lifecycle.INITIAL_OFFER, lifecycle.FINAL_OFFER)
        ):
            raise ValueError(
                f"Cannot record decision on offer {offer_id} for record "
                f"{record['id']}: not the latest pending offer, or record "
                f"is not awaiting a decision"
            )

        self.offers.record_decision(offer_id, decision, actor, decline_reason)

        if decision == 'declined':
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
