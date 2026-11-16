"""Tiny thread-safe per-key TTL cache for hot badge/count endpoints.

In-process (per gunicorn worker); each key's value expires after `ttl_seconds`.
Purpose: absorb the frequent badge pollers (unread-count, approvals queue
count) so they don't hit the DB on every ~30-60s poll and queue behind worker
recycles — the dominant cause of the 504s on these endpoints.

Callers MUST `invalidate(key)` on the mutations that change the cached value
(mark-read, decide, …) so a user's own action is reflected immediately rather
than delayed by up to the TTL. Values for other users self-heal within the TTL.
"""
import threading
import time


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._store: dict = {}
        self._lock = threading.Lock()

    def get_or_set(self, key, producer):
        """Return the cached value for `key`, or compute it via `producer()`,
        cache it for ttl_seconds, and return it. `producer` runs OUTSIDE the
        lock (it may hit the DB); a rare concurrent miss just computes twice."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is not None and entry[1] > now:
                return entry[0]
        value = producer()
        with self._lock:
            self._store[key] = (value, time.monotonic() + self._ttl)
        return value

    def invalidate(self, key):
        with self._lock:
            self._store.pop(key, None)
