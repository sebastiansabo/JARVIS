"""Ghost-user (leadership privacy) visibility helper.

A "ghost" (users.is_ghost = TRUE) is hidden from activity/stat/feed surfaces
others see. They remain visible to themselves and to the configurable
super-admin list (notification_settings key 'ghost_visible_admin_ids', CSV of
user ids). Read-time only; nothing is deleted.

Usage in a repo query:
    from core.organization.ghost import ghost_exclude_clause
    frag, gargs = ghost_exclude_clause('u.id')        # read surface: context viewer
    sql = f"... WHERE ... {frag}"; args += gargs
    # enrollment / scheduled body: force full hide
    frag, gargs = ghost_exclude_clause('u.id', viewer_id=None)
"""
import time
import threading

_lock = threading.RLock()
_cache: dict = {}          # key -> (value, expires_at)
_TTL = 60
_UNSET = object()


def _cache_get(key):
    with _lock:
        e = _cache.get(key)
        if e and time.monotonic() < e[1]:
            return e[0], True
        return None, False


def _cache_set(key, value):
    with _lock:
        _cache[key] = (value, time.monotonic() + _TTL)


def invalidate_ghost_cache():
    with _lock:
        _cache.clear()


# --- patchable DB/settings seams -------------------------------------------
def _fetch_ghost_ids() -> set:
    from database import get_db, get_cursor, release_db
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT id FROM users WHERE is_ghost = TRUE")
        return {r['id'] for r in cur.fetchall()}
    finally:
        release_db(conn)


def _fetch_admin_ids() -> set:
    from core.services.settings_service import get_notification_settings
    raw = (get_notification_settings().get('ghost_visible_admin_ids', '') or '')
    out = set()
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _resolve_viewer():
    """Current user id from Flask/JWT request context, else None (scheduled)."""
    try:
        from flask import request, has_request_context
        if not has_request_context():
            return None
        jwt_user = getattr(request, '_jwt_user', None)
        if jwt_user is not None:
            return getattr(jwt_user, 'id', None)
        from flask_login import current_user
        if current_user and getattr(current_user, 'is_authenticated', False):
            return current_user.id
        return None
    except Exception:
        return None


# --- public API ------------------------------------------------------------
def get_ghost_user_ids() -> set:
    v, hit = _cache_get('ghost_ids')
    if hit:
        return v
    v = _fetch_ghost_ids()
    _cache_set('ghost_ids', v)
    return v


def get_ghost_admin_ids() -> set:
    v, hit = _cache_get('admin_ids')
    if hit:
        return v
    v = _fetch_admin_ids()
    _cache_set('admin_ids', v)
    return v


def can_see_ghosts(viewer_id) -> bool:
    if viewer_id is None:
        return False
    return int(viewer_id) in get_ghost_admin_ids()


def hidden_ghost_ids(viewer_id) -> set:
    ghosts = get_ghost_user_ids()
    if not ghosts:
        return set()
    if can_see_ghosts(viewer_id):
        return set()
    if viewer_id is not None:
        return ghosts - {int(viewer_id)}
    return set(ghosts)


def ghost_exclude_clause(col: str = 'u.id', viewer_id=_UNSET):
    """Return (sql_fragment, params). Empty ('', []) when nothing to hide.

    viewer_id defaults to the request-context viewer (super-admins bypass).
    Pass viewer_id=None to force full hide (enrollment/target/scheduler bodies).
    """
    vid = _resolve_viewer() if viewer_id is _UNSET else viewer_id
    ids = hidden_ghost_ids(vid)
    if not ids:
        return '', []
    return f' AND {col} <> ALL(%s)', [list(ids)]
