"""Autovit Listing Repository — per (vehicle, account) push-sync state for
carpark_autovit_listings (Task 6 of the Autovit two-way-sync plan).

One row per vehicle/account pair tracks the remote advert id/url, the last
known publish status, and the last sync/error, so the push job can upsert
idempotently instead of re-creating adverts on every run.
"""
from typing import Optional, Dict, Any

from core.base_repository import BaseRepository

# Columns the push job is allowed to write via upsert()/set_error(). Deliberately
# excludes vehicle_id/account_id (identity, not updatable) and the
# server-managed last_sync/updated_at (always bumped on every upsert below).
_UPDATABLE = {"external_advert_id", "external_url", "status", "last_error"}


class AutovitListingRepository(BaseRepository):
    """Data access for carpark_autovit_listings."""

    def get(self, vehicle_id: int, account_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            "SELECT * FROM carpark_autovit_listings WHERE vehicle_id=%s AND account_id=%s",
            (vehicle_id, account_id))

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
