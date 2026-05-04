"""Telemetry routes — event ingestion and analytics endpoints."""

import time
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from core.utils.logging_config import get_logger
from .repository import TelemetryRepository

logger = get_logger('jarvis.telemetry')
telemetry_bp = Blueprint('telemetry', __name__)
_repo = TelemetryRepository()

# Simple in-memory rate limiter: user_id -> (count, window_start)
_rate_limits: dict[int, tuple[int, float]] = {}
_RATE_LIMIT = 100  # max events per minute
_RATE_WINDOW = 60  # seconds


def _check_rate_limit(user_id: int) -> bool:
    """Return True if under rate limit, False if exceeded."""
    now = time.time()
    entry = _rate_limits.get(user_id)
    if entry is None or (now - entry[1]) > _RATE_WINDOW:
        _rate_limits[user_id] = (1, now)
        return True
    count, window_start = entry
    if count >= _RATE_LIMIT:
        return False
    _rate_limits[user_id] = (count + 1, window_start)
    return True


def _categorize_event(event_name: str) -> str:
    """Determine event category from name."""
    nav_events = {'Page Viewed', 'Session Started', 'Session Ended'}
    if event_name in nav_events:
        return 'navigation'
    return 'interaction'


# ── Ingestion endpoints ──────────────────────────────────────────

@telemetry_bp.route('/api/telemetry/events', methods=['POST'])
@login_required
def ingest_events():
    """Batch insert telemetry events from the frontend."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    events = data.get('events', [])
    if not events:
        return jsonify({'success': False, 'error': 'No events provided'}), 400

    if len(events) > 50:
        events = events[:50]

    if not _check_rate_limit(current_user.id):
        return jsonify({'success': False, 'error': 'Rate limit exceeded'}), 429

    user_agent = request.headers.get('User-Agent', '')
    is_mobile = 'jarvis-mobile' in user_agent.lower() or request.headers.get('Authorization', '').startswith('Bearer ')

    # Enrich with server-side user context
    enriched = []
    # Track per-session counts (handles batches with mixed sessions)
    session_counts: dict[str, dict] = {}  # sid -> {page_views, event_count, last_page}

    for raw in events:
        event_name = raw.get('event', '')
        if not event_name:
            continue

        sid = raw.get('session_id', '')
        if not sid:
            continue

        client_ts = raw.get('timestamp')
        if not client_ts:
            client_ts = datetime.now(timezone.utc).isoformat()

        ctx = raw.get('context', {})
        props = raw.get('properties', {})
        page_path = ctx.get('page_path') or props.get('page_path')

        # Accumulate per-session counts
        if sid not in session_counts:
            session_counts[sid] = {'page_views': 0, 'event_count': 0, 'last_page': None}
        session_counts[sid]['event_count'] += 1
        if event_name == 'Page Viewed':
            session_counts[sid]['page_views'] += 1
            session_counts[sid]['last_page'] = page_path

        enriched.append({
            'event_name': event_name,
            'event_category': _categorize_event(event_name),
            'session_id': sid,
            'user_id': current_user.id,
            'company_id': getattr(current_user, 'company_id', None),
            'role_name': getattr(current_user, 'role_name', None),
            'properties': props,
            'page_path': page_path,
            'page_title': ctx.get('page_title'),
            'referrer': ctx.get('referrer'),
            'screen_width': ctx.get('screen_width'),
            'screen_height': ctx.get('screen_height'),
            'user_agent': user_agent,
            'locale': ctx.get('locale'),
            'timezone': ctx.get('timezone'),
            'client_ts': client_ts,
        })

    if not enriched:
        return jsonify({'success': True, 'inserted': 0})

    try:
        count = _repo.insert_events(enriched)

        # Update per-session counts
        for sid, counts in session_counts.items():
            _repo.update_session_counts(
                session_id=sid,
                page_views=counts['page_views'],
                event_count=counts['event_count'],
                exit_page=counts['last_page'],
            )

        # Handle session lifecycle events
        for raw in events:
            event_name = raw.get('event', '')
            sid = raw.get('session_id', '')

            if event_name == 'Session Started' and sid:
                ctx = raw.get('context', {})
                props = raw.get('properties', {})
                _repo.upsert_session({
                    'session_id': sid,
                    'user_id': current_user.id,
                    'company_id': getattr(current_user, 'company_id', None),
                    'role_name': getattr(current_user, 'role_name', None),
                    'started_at': raw.get('timestamp', datetime.now(timezone.utc).isoformat()),
                    'last_seen_at': datetime.now(timezone.utc).isoformat(),
                    'entry_page': props.get('entry_page') or ctx.get('page_path'),
                    'screen_width': ctx.get('screen_width'),
                    'screen_height': ctx.get('screen_height'),
                    'user_agent': user_agent,
                    'locale': ctx.get('locale'),
                    'timezone': ctx.get('timezone'),
                    'is_mobile': is_mobile,
                })

            elif event_name == 'Session Ended' and sid:
                props = raw.get('properties', {})
                _repo.end_session(sid, exit_page=props.get('exit_page'))

        return jsonify({'success': True, 'inserted': count})
    except Exception as e:
        logger.exception(f'Failed to insert telemetry events: {e}')
        return jsonify({'success': False, 'error': 'Failed to store events'}), 500


@telemetry_bp.route('/api/telemetry/heartbeat', methods=['POST'])
@login_required
def heartbeat():
    """Session keepalive — updates last_seen_at."""
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'error': 'Missing session_id'}), 400

    try:
        _repo.update_session_heartbeat(session_id, user_id=current_user.id)
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f'Heartbeat failed: {e}')
        return jsonify({'success': False}), 500


# ── Admin analytics endpoints ────────────────────────────────────

@telemetry_bp.route('/api/admin/telemetry/dashboard')
@login_required
def telemetry_dashboard():
    """Aggregated analytics dashboard data."""
    if getattr(current_user, 'role_name', None) != 'Admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    days = request.args.get('days', 30, type=int)
    days = min(days, 365)

    stats = _repo.get_dashboard_stats(days=days)
    return jsonify({'success': True, 'data': stats})


@telemetry_bp.route('/api/admin/telemetry/events')
@login_required
def telemetry_events():
    """Raw event log with filters."""
    if getattr(current_user, 'role_name', None) != 'Admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    events = _repo.get_events(
        limit=min(request.args.get('limit', 100, type=int), 500),
        offset=request.args.get('offset', 0, type=int),
        user_id=request.args.get('user_id', type=int),
        event_name=request.args.get('event_name'),
        page_path=request.args.get('page_path'),
        session_id=request.args.get('session_id'),
        start_date=request.args.get('start_date'),
        end_date=request.args.get('end_date'),
    )
    return jsonify({'success': True, 'data': events})


@telemetry_bp.route('/api/admin/telemetry/sessions')
@login_required
def telemetry_sessions():
    """Session list with duration/page stats."""
    if getattr(current_user, 'role_name', None) != 'Admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    sessions = _repo.get_sessions(
        limit=min(request.args.get('limit', 50, type=int), 200),
        offset=request.args.get('offset', 0, type=int),
        user_id=request.args.get('user_id', type=int),
        start_date=request.args.get('start_date'),
        end_date=request.args.get('end_date'),
    )
    return jsonify({'success': True, 'data': sessions})


@telemetry_bp.route('/api/admin/telemetry/popular-pages')
@login_required
def telemetry_popular_pages():
    """Top pages by view count."""
    if getattr(current_user, 'role_name', None) != 'Admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    days = request.args.get('days', 30, type=int)
    limit = min(request.args.get('limit', 20, type=int), 100)
    pages = _repo.get_popular_pages(days=days, limit=limit)
    return jsonify({'success': True, 'data': pages})


@telemetry_bp.route('/api/admin/telemetry/popular-actions')
@login_required
def telemetry_popular_actions():
    """Top interactions by click count."""
    if getattr(current_user, 'role_name', None) != 'Admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    days = request.args.get('days', 30, type=int)
    limit = min(request.args.get('limit', 20, type=int), 100)
    actions = _repo.get_popular_actions(days=days, limit=limit)
    return jsonify({'success': True, 'data': actions})


@telemetry_bp.route('/api/admin/telemetry/user-journeys')
@login_required
def telemetry_user_journeys():
    """Page flow sequence for a specific session."""
    if getattr(current_user, 'role_name', None) != 'Admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id required'}), 400

    journey = _repo.get_user_journey(session_id)
    return jsonify({'success': True, 'data': journey})


@telemetry_bp.route('/api/admin/telemetry/event-names')
@login_required
def telemetry_event_names():
    """Distinct event names for filter dropdowns."""
    if getattr(current_user, 'role_name', None) != 'Admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    names = _repo.get_event_names()
    return jsonify({'success': True, 'data': names})
