"""Data access for buyback_offers (offers made to a seller on a buyback
record, and the seller's decision on each).

Mirrors buyback/repositories/record_repository.py's BaseRepository style
(raw parameterized SQL via self.query_one/self.query_all/self.execute) and
its injection posture — every value is %s-bound; no caller-influenced value
is ever interpolated into SQL text. Unlike RecordRepository.create(), this
repo's create() has a FIXED column list (not built from an arbitrary dict),
so there's no column-identifier interpolation concern here at all.

The one-pending-per-record and latest-offer/status invariants are NOT
enforced here — they belong to the service layer (Task 8) and the route
(Task 10). This repo is intentionally "dumb": it just runs the queries the
brief specifies.
"""

from core.base_repository import BaseRepository


class OfferRepository(BaseRepository):

    def create(self, record_id, offer_type, amount_eur, vat_status, valid_until, notes, created_by) -> dict:
        """INSERT into buyback_offers with RETURNING *.

        `client_decision` always starts as 'pending' (the DB column default,
        made explicit here too). When `valid_until` is None, it defaults to
        `CURRENT_DATE + INTERVAL '7 days'` — computed in SQL via COALESCE so
        the DB, not Python, owns "what is today" and the interval math.
        """
        sql = (
            'INSERT INTO buyback_offers '
            '(record_id, offer_type, amount_eur, vat_status, valid_until, notes, created_by, client_decision) '
            "VALUES (%s, %s, %s, %s, COALESCE(%s, CURRENT_DATE + INTERVAL '7 days'), %s, %s, 'pending') "
            'RETURNING *'
        )
        params = (record_id, offer_type, amount_eur, vat_status, valid_until, notes, created_by)
        return self.execute(sql, params, returning=True)

    def get(self, offer_id) -> dict | None:
        return self.query_one('SELECT * FROM buyback_offers WHERE id = %s', (offer_id,))

    def latest_for_record(self, record_id) -> dict | None:
        """Most recent offer for a record, irrespective of decision status."""
        return self.query_one(
            'SELECT * FROM buyback_offers WHERE record_id = %s '
            'ORDER BY created_at DESC, id DESC LIMIT 1',
            (record_id,),
        )

    def pending_for_record(self, record_id) -> dict | None:
        """The still-undecided offer for a record, if any."""
        return self.query_one(
            "SELECT * FROM buyback_offers WHERE record_id = %s AND client_decision = 'pending' "
            'ORDER BY id DESC LIMIT 1',
            (record_id,),
        )

    def record_decision(self, offer_id, decision, decided_by, decline_reason=None) -> dict:
        """Record the seller's decision ('accepted'/'declined'/...) on an
        offer. `decided_at` is stamped server-side via NOW()."""
        sql = (
            'UPDATE buyback_offers SET client_decision = %s, decided_by = %s, '
            'decided_at = NOW(), decline_reason = %s WHERE id = %s RETURNING *'
        )
        return self.execute(sql, (decision, decided_by, decline_reason, offer_id), returning=True)
