"""HR org-hierarchy utilities — cached wrappers for is_manager / get_managed_employee_ids.

These functions are called on almost every authenticated API request (HR, BioStar,
Sincron, Connecteam, Profile routes). Moving them here breaks the core → hr coupling
and adds a 60-second per-user in-memory cache to avoid redundant DB round-trips.

Usage (drop-in replacement for the old imports):
    from core.organization.hr_utils import is_manager, get_managed_employee_ids, get_visible_tree
"""
import time
import threading

from core.organization.manager_utils import (
    is_manager as _is_manager,
    get_managed_employee_ids as _get_managed,
    get_visible_tree as _get_visible_tree,
)

# ---------------------------------------------------------------------------
# Simple TTL cache (per-worker, thread-safe)
# ---------------------------------------------------------------------------
_cache_lock = threading.RLock()
_cache: dict = {}          # key -> (value, expires_at)
_CACHE_TTL = 60            # seconds


def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.monotonic() < entry[1]:
            return entry[0], True
        return None, False


def _cache_set(key, value, ttl=_CACHE_TTL):
    with _cache_lock:
        _cache[key] = (value, time.monotonic() + ttl)


def invalidate_user_cache(user_id: int):
    """Call after org-structure changes to flush cache for a specific user."""
    with _cache_lock:
        keys_to_delete = [k for k in _cache if str(user_id) in k]
        for k in keys_to_delete:
            del _cache[k]


# ---------------------------------------------------------------------------
# Public API — mirrors hr.events.database signatures exactly
# ---------------------------------------------------------------------------

def is_manager(user_id: int) -> bool:
    """Return True if user_id is a responsable on any organigram node or company.

    Result cached for 60 s per user.
    """
    key = f'is_manager:{user_id}'
    cached, hit = _cache_get(key)
    if hit:
        return cached

    result = _is_manager(user_id)
    _cache_set(key, result)
    return result


def get_managed_employee_ids(manager_user_id: int, node_id=None) -> list:
    """Get all user IDs visible to this manager in the organigram.

    Result cached for 60 s per (manager, node_id) pair.
    """
    key = f'managed_ids:{manager_user_id}:{node_id}'
    cached, hit = _cache_get(key)
    if hit:
        return cached

    result = _get_managed(manager_user_id, node_id)
    _cache_set(key, result)
    return result


def get_visible_tree(manager_user_id: int) -> dict:
    """Get the organigram tree visible to this manager.

    Result cached for 60 s per manager.
    """
    key = f'visible_tree:{manager_user_id}'
    cached, hit = _cache_get(key)
    if hit:
        return cached

    result = _get_visible_tree(manager_user_id)
    _cache_set(key, result)
    return result
