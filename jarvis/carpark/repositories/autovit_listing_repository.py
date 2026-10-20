"""Autovit Listing Repository — per (vehicle, account) push-sync state for
carpark_autovit_listings (Task 6 of the Autovit two-way-sync plan).

One row per vehicle/account pair tracks the remote advert id/url, the last
known publish status, and the last sync/error, so the push job can upsert
idempotently instead of re-creating adverts on every run.
"""
from typing import Optional, Dict, Any, List

from core.base_repository import BaseRepository

# Columns the push job is allowed to write via upsert()/set_error(). Deliberately
# excludes vehicle_id/account_id (identity, not updatable) and the
# server-managed last_sync/updated_at (always bumped on every upsert below).
# last_published_at is distinct from last_sync: last_sync is overloaded (also
# bumped by verify-status, which doesn't publish anything), so freshness
# computations need a timestamp that only moves on an actual publish/update.
_UPDATABLE = {"external_advert_id", "external_url", "status", "last_error",
              "last_published_at"}


class AutovitListingRepository(BaseRepository):
    """Data access for carpark_autovit_listings."""

    def get(self, vehicle_id: int, account_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            "SELECT * FROM carpark_autovit_listings WHERE vehicle_id=%s AND account_id=%s",
            (vehicle_id, account_id))

    def list_by_vehicle(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """All Autovit listing rows for a vehicle (across accounts), newest first —
        so the Detail page can surface the current publish status/last error that
        was previously only visible directly in the DB."""
        return self.query_all(
            "SELECT * FROM carpark_autovit_listings WHERE vehicle_id=%s ORDER BY updated_at DESC",
            (vehicle_id,))

    def upsert(self, vehicle_id: int, account_id: int, **fields) -> Dict[str, Any]:
        """Insert or update the listing row for (vehicle_id, account_id).

        Only keys in _UPDATABLE are written; unknown kwargs are silently
        dropped. last_sync/updated_at are always refreshed to now().
        """
        cols = {k: v for k, v in fields.items() if k in _UPDATABLE}
        set_clause = ", ".join(f"{k}=EXCLUDED.{k}" for k in cols)
        set_clause = (set_clause + ", " if set_clause else "") + "last_sync=now(), updated_at=now()"
        colnames = ["vehicle_id", "account_id"] + list(cols)
        placeholders = ", ".join(["%s"] * len(colnames))
        vals = [vehicle_id, account_id] + list(cols.values())
        return self.execute(
            f"""INSERT INTO carpark_autovit_listings ({', '.join(colnames)})
                VALUES ({placeholders})
                ON CONFLICT (vehicle_id, account_id) DO UPDATE SET {set_clause}
                RETURNING *""", tuple(vals), returning=True)

    def set_error(self, vehicle_id: int, account_id: int, msg: str) -> None:
        self.upsert(vehicle_id, account_id, status="error", last_error=msg)

    def list_live_vehicle_ids(self) -> List[int]:
        """Distinct vehicle_ids with a currently-live Autovit listing (status
        'active' or 'unpaid' — same vocabulary as freshness.py's
        autovit_sweep_stale). Used by Task 8's backfill script to find
        already-published cars that predate Task 7's default-on-publish 1h
        auto-update schedule."""
        rows = self.query_all(
            "SELECT DISTINCT vehicle_id FROM carpark_autovit_listings "
            "WHERE status IN ('active', 'unpaid')")
        return [r['vehicle_id'] for r in rows]
