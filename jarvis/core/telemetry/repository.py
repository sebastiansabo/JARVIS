"""Telemetry Repository — data access for telemetry events and sessions."""

import json

from core.base_repository import BaseRepository


class TelemetryRepository(BaseRepository):
    """Repository for telemetry event and session operations."""

    # ── Event ingestion ──────────────────────────────────────────────

    def insert_events(self, events: list[dict]) -> int:
        """Batch insert telemetry events.

        Args:
            events: List of event dicts with keys matching telemetry_events columns.

        Returns:
            Number of rows inserted.
        """
        if not events:
            return 0

        def _batch(cursor):
            sql = '''
                INSERT INTO telemetry_events
                (event_name, event_category, session_id, user_id, company_id, role_name,
                 properties, page_path, page_title, referrer,
                 screen_width, screen_height, user_agent, locale, timezone, client_ts)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            '''
            rows = []
            for e in events:
                rows.append((
                    e['event_name'], e.get('event_category', 'interaction'),
                    e['session_id'], e.get('user_id'), e.get('company_id'), e.get('role_name'),
                    json.dumps(e.get('properties', {})),
                    e.get('page_path'), e.get('page_title'), e.get('referrer'),
                    e.get('screen_width'), e.get('screen_height'),
                    e.get('user_agent'), e.get('locale'), e.get('timezone'),
                    e['client_ts'],
                ))
            cursor.executemany(sql, rows)
            return cursor.rowcount

        return self.execute_many(_batch)

    # ── Session management ───────────────────────────────────────────

    def upsert_session(self, session_data: dict) -> None:
        """Create or update a telemetry session."""
        self.execute('''
            INSERT INTO telemetry_sessions
            (session_id, user_id, company_id, role_name,
             started_at, last_seen_at, entry_page,
             screen_width, screen_height, user_agent, locale, timezone, is_mobile)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                last_seen_at = EXCLUDED.last_seen_at,
                user_id = COALESCE(EXCLUDED.user_id, telemetry_sessions.user_id)
        ''', (
            session_data['session_id'], session_data.get('user_id'),
            session_data.get('company_id'), session_data.get('role_name'),
            session_data['started_at'], session_data['last_seen_at'],
            session_data.get('entry_page'),
            session_data.get('screen_width'), session_data.get('screen_height'),
            session_data.get('user_agent'), session_data.get('locale'),
            session_data.get('timezone'), session_data.get('is_mobile', False),
        ))

    def update_session_heartbeat(self, session_id: str, user_id: int = None) -> None:
        """Update last_seen_at for an active session."""
        self.execute('''
            UPDATE telemetry_sessions
            SET last_seen_at = NOW()
            WHERE session_id = %s
        ''', (session_id,))

    def end_session(self, session_id: str, exit_page: str = None) -> None:
        """Mark a session as ended and compute duration."""
        self.execute('''
            UPDATE telemetry_sessions
            SET ended_at = NOW(),
                exit_page = COALESCE(%s, exit_page),
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER
            WHERE session_id = %s AND ended_at IS NULL
        ''', (exit_page, session_id))

    def update_session_counts(self, session_id: str, page_views: int, event_count: int,
                              exit_page: str = None) -> None:
        """Increment session page view and event counters."""
        self.execute('''
            UPDATE telemetry_sessions
            SET page_views = page_views + %s,
                event_count = event_count + %s,
                exit_page = COALESCE(%s, exit_page),
                last_seen_at = NOW()
            WHERE session_id = %s
        ''', (page_views, event_count, exit_page, session_id))

    def close_stale_sessions(self, stale_minutes: int = 5) -> int:
        """Close sessions with no heartbeat for stale_minutes."""
        return self.execute('''
            UPDATE telemetry_sessions
            SET ended_at = last_seen_at,
                duration_seconds = EXTRACT(EPOCH FROM (last_seen_at - started_at))::INTEGER
            WHERE ended_at IS NULL
              AND last_seen_at < NOW() - %s * INTERVAL '1 minute'
        ''', (stale_minutes,))

    # ── Cleanup ──────────────────────────────────────────────────────

    def delete_old_events(self, retention_days: int = 90) -> int:
        """Delete events older than retention_days."""
        return self.execute('''
            DELETE FROM telemetry_events
            WHERE server_ts < NOW() - %s * INTERVAL '1 day'
        ''', (retention_days,))

    def delete_old_sessions(self, retention_days: int = 90) -> int:
        """Delete sessions older than retention_days."""
        return self.execute('''
            DELETE FROM telemetry_sessions
            WHERE started_at < NOW() - %s * INTERVAL '1 day'
        ''', (retention_days,))

    # ── Analytics queries ────────────────────────────────────────────

    def get_events(self, limit: int = 100, offset: int = 0,
                   user_id: int = None, event_name: str = None,
                   page_path: str = None, session_id: str = None,
                   start_date: str = None, end_date: str = None) -> list[dict]:
        """Get telemetry events with optional filters."""
        query = '''
            SELECT te.*, u.name as user_name
            FROM telemetry_events te
            LEFT JOIN users u ON te.user_id = u.id
        '''
        params = []
        conditions = []
        if user_id:
            conditions.append('te.user_id = %s')
            params.append(user_id)
        if event_name:
            conditions.append('te.event_name = %s')
            params.append(event_name)
        if page_path:
            conditions.append('te.page_path = %s')
            params.append(page_path)
        if session_id:
            conditions.append('te.session_id = %s')
            params.append(session_id)
        if start_date:
            conditions.append('te.server_ts >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('te.server_ts <= %s')
            params.append(end_date)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY te.server_ts DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])
        return self.query_all(query, params)

    def get_sessions(self, limit: int = 50, offset: int = 0,
                     user_id: int = None,
                     start_date: str = None, end_date: str = None) -> list[dict]:
        """Get telemetry sessions with optional filters."""
        query = '''
            SELECT ts.*, u.name as user_name
            FROM telemetry_sessions ts
            LEFT JOIN users u ON ts.user_id = u.id
        '''
        params = []
        conditions = []
        if user_id:
            conditions.append('ts.user_id = %s')
            params.append(user_id)
        if start_date:
            conditions.append('ts.started_at >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('ts.started_at <= %s')
            params.append(end_date)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY ts.started_at DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])
        return self.query_all(query, params)

    def get_popular_pages(self, days: int = 30, limit: int = 20) -> list[dict]:
        """Get most visited pages in the last N days."""
        return self.query_all('''
            SELECT page_path,
                   COUNT(*) as view_count,
                   COUNT(DISTINCT user_id) as unique_users,
                   COUNT(DISTINCT session_id) as unique_sessions,
                   ROUND(AVG((properties->>'duration_ms')::NUMERIC))::INTEGER as avg_duration_ms
            FROM telemetry_events
            WHERE event_name = 'Page Viewed'
              AND server_ts >= NOW() - %s * INTERVAL '1 day'
              AND page_path IS NOT NULL
            GROUP BY page_path
            ORDER BY view_count DESC
            LIMIT %s
        ''', (days, limit))

    def get_popular_actions(self, days: int = 30, limit: int = 20) -> list[dict]:
        """Get most used interactions in the last N days."""
        return self.query_all('''
            SELECT event_name,
                   properties->>'button_id' as button_id,
                   properties->>'button_text' as button_text,
                   COUNT(*) as click_count,
                   COUNT(DISTINCT user_id) as unique_users
            FROM telemetry_events
            WHERE event_name != 'Page Viewed'
              AND event_category = 'interaction'
              AND server_ts >= NOW() - %s * INTERVAL '1 day'
            GROUP BY event_name, properties->>'button_id', properties->>'button_text'
            ORDER BY click_count DESC
            LIMIT %s
        ''', (days, limit))

    def get_dashboard_stats(self, days: int = 30) -> dict:
        """Get aggregated telemetry dashboard stats."""
        stats = self.query_one('''
            SELECT
                COUNT(*) as total_events,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT session_id) as total_sessions,
                COUNT(CASE WHEN event_name = 'Page Viewed' THEN 1 END) as page_views,
                COUNT(CASE WHEN event_category = 'interaction' AND event_name != 'Page Viewed' THEN 1 END) as interactions
            FROM telemetry_events
            WHERE server_ts >= NOW() - %s * INTERVAL '1 day'
        ''', (days,))

        session_stats = self.query_one('''
            SELECT
                ROUND(AVG(duration_seconds))::INTEGER as avg_session_duration,
                ROUND(AVG(page_views), 1)::NUMERIC as avg_pages_per_session
            FROM telemetry_sessions
            WHERE started_at >= NOW() - %s * INTERVAL '1 day'
              AND duration_seconds IS NOT NULL
              AND duration_seconds > 0
        ''', (days,))

        daily_active = self.query_all('''
            SELECT DATE(server_ts) as day,
                   COUNT(DISTINCT user_id) as active_users,
                   COUNT(*) as events
            FROM telemetry_events
            WHERE server_ts >= NOW() - %s * INTERVAL '1 day'
            GROUP BY DATE(server_ts)
            ORDER BY day
        ''', (days,))

        return {
            **(stats or {}),
            'avg_session_duration': (session_stats or {}).get('avg_session_duration'),
            'avg_pages_per_session': float((session_stats or {}).get('avg_pages_per_session') or 0),
            'daily_active': daily_active,
        }

    def get_user_journey(self, session_id: str) -> list[dict]:
        """Get the page navigation sequence for a single session."""
        return self.query_all('''
            SELECT event_name, page_path, page_title,
                   properties->>'previous_page' as previous_page,
                   properties->>'duration_ms' as duration_ms,
                   client_ts
            FROM telemetry_events
            WHERE session_id = %s
              AND event_name IN ('Page Viewed', 'Session Started', 'Session Ended')
            ORDER BY client_ts ASC
        ''', (session_id,))

    def get_event_names(self) -> list[str]:
        """Get distinct event names for filtering."""
        rows = self.query_all('''
            SELECT DISTINCT event_name FROM telemetry_events
            ORDER BY event_name
        ''')
        return [r['event_name'] for r in rows]
