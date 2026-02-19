"""Daily Digest Service — AI-generated morning summary.

Collects key metrics (invoices, transactions, approvals, e-Factura backlog,
marketing KPIs) and uses the configured LLM to produce a concise digest
delivered as an in-app notification.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from core.database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger

logger = get_logger('jarvis.ai_agent.services.digest')

# Settings keys
_DIGEST_ENABLED = 'daily_digest_enabled'
_DIGEST_RECIPIENTS = 'daily_digest_recipients'  # 'admins' or comma-separated user IDs

# Cache
_settings: Dict[str, str] = {}
_settings_loaded_at: float = 0


def _load_settings():
    """Load digest settings from notification_settings table (60s cache)."""
    global _settings, _settings_loaded_at
    now = time.time()
    if _settings and (now - _settings_loaded_at) < 60:
        return
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute(
            "SELECT setting_key, setting_value FROM notification_settings "
            "WHERE setting_key LIKE 'daily_digest_%%'"
        )
        _settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
        _settings_loaded_at = now
    finally:
        release_db(conn)


def _setting(key: str, default: str = '') -> str:
    return _settings.get(key, default)


def _get_recipient_ids() -> List[int]:
    """Get user IDs who should receive the digest."""
    recipients = _setting(_DIGEST_RECIPIENTS, 'admins')
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        if recipients == 'admins':
            cursor.execute('''
                SELECT u.id FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE r.name = 'Admin' AND u.is_active = TRUE
            ''')
        elif recipients == 'managers':
            cursor.execute('''
                SELECT u.id FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE r.name IN ('Admin', 'Manager') AND u.is_active = TRUE
            ''')
        elif recipients == 'all':
            cursor.execute("SELECT id FROM users WHERE is_active = TRUE")
        else:
            # Comma-separated user IDs
            try:
                return [int(uid.strip()) for uid in recipients.split(',') if uid.strip()]
            except ValueError:
                return []
        return [row['id'] for row in cursor.fetchall()]
    finally:
        release_db(conn)


def _collect_metrics() -> Dict[str, Any]:
    """Gather all metrics for the digest from the database."""
    from ai_agent.services.analytics_service import AnalyticsService

    analytics = AnalyticsService()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    metrics: Dict[str, Any] = {}

    # 1. Invoice summary by company (last 24h)
    try:
        metrics['invoices'] = analytics.get_invoice_summary(
            group_by='company', start_date=yesterday, end_date=today,
        )
    except Exception as e:
        logger.warning(f"Digest: invoice summary failed: {e}")

    # 2. Top suppliers (last 30 days)
    try:
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')
        metrics['top_suppliers'] = analytics.get_top_suppliers(
            limit=5, start_date=thirty_days_ago, end_date=today,
        )
    except Exception as e:
        logger.warning(f"Digest: top suppliers failed: {e}")

    # 3. e-Factura backlog
    try:
        metrics['efactura'] = analytics.get_efactura_summary()
    except Exception as e:
        logger.warning(f"Digest: e-Factura summary failed: {e}")

    # 4. Pending approvals count per user (global)
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT COUNT(*) AS cnt FROM approval_requests
            WHERE status = 'pending'
        ''')
        row = cursor.fetchone()
        metrics['pending_approvals'] = row['cnt'] if row else 0
    except Exception as e:
        logger.warning(f"Digest: pending approvals failed: {e}")
    finally:
        release_db(conn)

    # 5. Marketing projects with active budgets nearing limit
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT p.name, bl.category,
                   bl.planned_amount, bl.spent_amount,
                   CASE WHEN bl.planned_amount > 0
                        THEN ROUND(bl.spent_amount / bl.planned_amount * 100, 1)
                        ELSE 0 END AS utilization_pct
            FROM mkt_budget_lines bl
            JOIN mkt_projects p ON p.id = bl.project_id
            WHERE p.status IN ('active', 'in_progress')
              AND bl.planned_amount > 0
              AND bl.spent_amount / bl.planned_amount >= 0.8
            ORDER BY utilization_pct DESC
            LIMIT 10
        ''')
        metrics['budget_alerts'] = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f"Digest: budget alerts failed: {e}")
    finally:
        release_db(conn)

    return metrics


def _format_digest_plain(metrics: Dict[str, Any]) -> str:
    """Format metrics into a plain-text summary (fallback when LLM unavailable)."""
    lines = [f"Daily Digest — {datetime.now(timezone.utc).strftime('%B %d, %Y')}"]
    lines.append('')

    # Invoices
    inv = metrics.get('invoices', {})
    rows = inv.get('rows', [])
    if rows:
        total_ron = sum(float(r.get('total_value_ron', 0)) for r in rows)
        total_count = sum(int(r.get('invoice_count', 0)) for r in rows)
        lines.append(f"Invoices (last 24h): {total_count} invoices, {total_ron:,.0f} RON")
    else:
        lines.append("Invoices (last 24h): No new invoices")

    # e-Factura
    ef = metrics.get('efactura', {})
    overview = ef.get('overview', {})
    unalloc = overview.get('unallocated_count', 0)
    if unalloc:
        lines.append(f"e-Factura backlog: {unalloc} unallocated ({overview.get('unallocated_total', 0):,.0f} RON)")

    # Approvals
    pending = metrics.get('pending_approvals', 0)
    if pending:
        lines.append(f"Pending approvals: {pending}")

    # Budget alerts
    alerts = metrics.get('budget_alerts', [])
    if alerts:
        lines.append(f"Budget alerts: {len(alerts)} lines at >80% utilization")

    return '\n'.join(lines)


def _format_digest_ai(metrics: Dict[str, Any]) -> Optional[str]:
    """Use LLM to produce a formatted digest from raw metrics."""
    from ai_agent.repositories import ModelConfigRepository
    from ai_agent.providers import ClaudeProvider, OpenAIProvider, GroqProvider, GeminiProvider

    model_repo = ModelConfigRepository()
    model_config = model_repo.get_default()
    if not model_config:
        return None

    providers = {
        'claude': ClaudeProvider,
        'openai': OpenAIProvider,
        'groq': GroqProvider,
        'gemini': GeminiProvider,
    }
    provider_cls = providers.get(model_config.provider.value)
    if not provider_cls:
        return None

    provider = provider_cls()

    system = (
        "You are JARVIS, an internal business assistant for AUTOWORLD car dealership group in Romania. "
        "Generate a concise daily morning digest (max 500 chars) summarizing key business metrics. "
        "Use plain text, not markdown. Include only notable items. "
        "If nothing stands out, say 'All clear — no urgent items today.' "
        "Use Romanian number format (1.234,56) for monetary values. Always include RON currency."
    )

    import json
    user_msg = f"Generate a daily digest from these metrics:\n{json.dumps(metrics, default=str, indent=2)}"

    try:
        response = provider.generate(
            model_name=model_config.model_name,
            messages=[{'role': 'user', 'content': user_msg}],
            max_tokens=256,
            temperature=0.3,
            system=system,
        )
        return response.content.strip()
    except Exception as e:
        logger.warning(f"Digest AI formatting failed: {e}")
        return None


def generate_and_send():
    """Main entry point: collect metrics, format, send notifications.

    Returns dict with {sent_to: int, skipped: str|None}.
    """
    _load_settings()

    if _setting(_DIGEST_ENABLED) != 'true':
        return {'sent_to': 0, 'skipped': 'disabled'}

    recipient_ids = _get_recipient_ids()
    if not recipient_ids:
        return {'sent_to': 0, 'skipped': 'no recipients'}

    # Collect data
    metrics = _collect_metrics()

    # Try AI formatting, fall back to plain text
    digest_text = _format_digest_ai(metrics) or _format_digest_plain(metrics)

    # Send notifications
    from core.notifications.notify import notify_users
    today_str = datetime.now(timezone.utc).strftime('%b %d')
    notify_users(
        user_ids=recipient_ids,
        title=f'Daily Digest — {today_str}',
        message=digest_text,
        link='/app/dashboard',
        type='info',
    )

    logger.info(f"Daily digest sent to {len(recipient_ids)} users")
    return {'sent_to': len(recipient_ids)}
