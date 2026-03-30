"""Smart Notification Service (AI5).

Scheduled, rule-based alerts for KPIs, budgets, invoices, and e-Factura.
No LLM calls — pure SQL + threshold logic.
"""

import time
from datetime import datetime, timedelta
from typing import Optional, Dict

from database import get_db, get_cursor, release_db
from core.utils.logging_config import get_logger
from core.notifications.notify import notify_user, notify_users

logger = get_logger('jarvis.core.notifications.smart')


class SmartNotificationService:
    """Runs threshold-based checks and emits in-app notifications."""

    def __init__(self):
        self._settings: Dict[str, str] = {}
        self._settings_loaded_at: float = 0

    # ── Public entry point (called from scheduler) ──

    def run_all_checks(self):
        """Run all enabled smart notification checks."""
        self._load_settings()

        if self._setting('smart_alerts_enabled') != 'true':
            logger.debug('Smart alerts disabled globally, skipping')
            return {}

        results = {}

        if self._setting('smart_kpi_alerts_enabled') == 'true':
            results['kpi'] = self._check_kpi_thresholds()

        if self._setting('smart_budget_alerts_enabled') == 'true':
            results['budget'] = self._check_budget_utilization()

        if self._setting('smart_invoice_anomaly_enabled') == 'true':
            results['invoice'] = self._check_invoice_anomalies()

        if self._setting('smart_efactura_backlog_enabled') == 'true':
            results['efactura'] = self._check_efactura_backlog()

        total = sum(results.values())
        if total > 0:
            logger.info(f'Smart alerts: {total} notifications sent ({results})')
        else:
            logger.debug('Smart alerts: no alerts triggered')

        return results

    # ── KPI Threshold Alerts ──

    def _check_kpi_thresholds(self) -> int:
        """Check active project KPIs against warning/critical thresholds."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            conn.autocommit = False
            cursor.execute('''
                SELECT pk.id, pk.project_id, pk.current_value, pk.target_value,
                       pk.threshold_warning, pk.threshold_critical, pk.status,
                       kd.name as kpi_name, kd.direction,
                       p.name as project_name, p.owner_id
                FROM mkt_project_kpis pk
                JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
                JOIN mkt_projects p ON p.id = pk.project_id
                WHERE p.deleted_at IS NULL
                  AND p.status IN ('active', 'approved')
                  AND pk.current_value IS NOT NULL
                  AND (pk.threshold_warning IS NOT NULL OR pk.threshold_critical IS NOT NULL)
            ''')
            rows = cursor.fetchall()

            count = 0
            cooldown_hours = int(self._setting('smart_alert_cooldown_hours', '24'))

            for row in rows:
                row = dict(row)
                current = float(row['current_value'] or 0)

                breach = self._evaluate_kpi_breach(
                    current, row.get('direction', 'higher'),
                    float(row['threshold_warning']) if row['threshold_warning'] else None,
                    float(row['threshold_critical']) if row['threshold_critical'] else None,
                )

                if not breach:
                    continue

                alert_type = f'kpi_{breach}'
                if self._should_alert(cursor, alert_type, 'project_kpi', row['id'],
                                      cooldown_hours, current):
                    level = 'WARNING' if breach == 'warning' else 'CRITICAL'
                    threshold_val = row.get(f'threshold_{breach}')
                    notify_user(
                        row['owner_id'],
                        f'KPI {level}: {row["kpi_name"]}',
                        message=(
                            f'Project "{row["project_name"]}" — '
                            f'current value: {current:,.0f}, '
                            f'threshold: {threshold_val:,.0f}'
                        ),
                        link=f'/app/marketing/projects/{row["project_id"]}',
                        entity_type='mkt_project',
                        entity_id=row['project_id'],
                        type='warning' if breach == 'warning' else 'error',
                        category='smart_alert',
                    )
                    self._record_alert(cursor, alert_type, 'project_kpi', row['id'], current)
                    count += 1

            conn.commit()
            return count
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f'KPI threshold check failed: {e}')
            return 0
        finally:
            release_db(conn)

    def _evaluate_kpi_breach(self, current: float, direction: str,
                             warning: Optional[float],
                             critical: Optional[float]) -> Optional[str]:
        """Evaluate if current value breaches warning or critical threshold.

        direction='higher' means higher is better (breach = below threshold).
        direction='lower' means lower is better (breach = above threshold).
        """
        if direction == 'higher':
            if critical is not None and current <= critical:
                return 'critical'
            if warning is not None and current <= warning:
                return 'warning'
        else:
            if critical is not None and current >= critical:
                return 'critical'
            if warning is not None and current >= warning:
                return 'warning'
        return None

    # ── Budget Utilization Alerts ──

    def _check_budget_utilization(self) -> int:
        """Check budget lines where spent/planned exceeds 80% or 100%."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            conn.autocommit = False
            cursor.execute('''
                SELECT bl.id, bl.project_id, bl.channel, bl.planned_amount,
                       bl.spent_amount, bl.currency,
                       p.name as project_name, p.owner_id
                FROM mkt_budget_lines bl
                JOIN mkt_projects p ON p.id = bl.project_id
                WHERE p.deleted_at IS NULL
                  AND p.status IN ('active', 'approved')
                  AND bl.planned_amount > 0
            ''')
            rows = cursor.fetchall()

            count = 0
            cooldown_hours = int(self._setting('smart_alert_cooldown_hours', '24'))

            for row in rows:
                row = dict(row)
                planned = float(row['planned_amount'])
                spent = float(row['spent_amount'] or 0)
                utilization = spent / planned

                if utilization >= 1.0:
                    alert_type = 'budget_100'
                elif utilization >= 0.8:
                    alert_type = 'budget_80'
                else:
                    continue

                if self._should_alert(cursor, alert_type, 'budget_line', row['id'],
                                      cooldown_hours, spent):
                    pct = round(utilization * 100, 1)
                    level = 'OVER BUDGET' if utilization >= 1.0 else 'Budget at 80%'
                    notify_user(
                        row['owner_id'],
                        f'{level}: {row["channel"]}',
                        message=(
                            f'Project "{row["project_name"]}" — '
                            f'{pct}% used ({spent:,.0f} / {planned:,.0f} {row["currency"]})'
                        ),
                        link=f'/app/marketing/projects/{row["project_id"]}',
                        entity_type='mkt_project',
                        entity_id=row['project_id'],
                        type='warning' if utilization < 1.0 else 'error',
                        category='smart_alert',
                    )
                    self._record_alert(cursor, alert_type, 'budget_line', row['id'], spent)
                    count += 1

            conn.commit()
            return count
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f'Budget utilization check failed: {e}')
            return 0
        finally:
            release_db(conn)

    # ── Invoice Anomaly Detection ──

    def _check_invoice_anomalies(self) -> int:
        """Detect invoice amount outliers: >N sigma from supplier average."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            conn.autocommit = False
            sigma = float(self._setting('smart_invoice_anomaly_sigma', '2'))
            cooldown_hours = int(self._setting('smart_alert_cooldown_hours', '24'))

            cursor.execute('''
                WITH supplier_stats AS (
                    SELECT supplier,
                           AVG(invoice_value) as avg_value,
                           STDDEV_POP(invoice_value) as stddev_value,
                           COUNT(*) as inv_count
                    FROM invoices
                    WHERE deleted_at IS NULL
                      AND supplier IS NOT NULL
                      AND invoice_value > 0
                    GROUP BY supplier
                    HAVING COUNT(*) >= 5
                )
                SELECT i.id, i.invoice_number, i.supplier, i.invoice_value,
                       i.currency,
                       ss.avg_value, ss.stddev_value, ss.inv_count
                FROM invoices i
                JOIN supplier_stats ss ON ss.supplier = i.supplier
                WHERE i.deleted_at IS NULL
                  AND i.created_at >= NOW() - INTERVAL '24 hours'
                  AND ss.stddev_value > 0
                  AND ABS(i.invoice_value - ss.avg_value) > (%s * ss.stddev_value)
            ''', (sigma,))
            rows = cursor.fetchall()

            if not rows:
                conn.commit()
                return 0

            # Get admin user IDs for notification
            admin_ids = self._get_admin_ids(cursor)
            if not admin_ids:
                conn.commit()
                return 0

            count = 0
            for row in rows:
                row = dict(row)
                if self._should_alert(cursor, 'invoice_anomaly', 'invoice', row['id'],
                                      cooldown_hours, float(row['invoice_value'])):
                    avg = float(row['avg_value'])
                    diff_pct = round(abs(float(row['invoice_value']) - avg) / avg * 100, 0)
                    notify_users(
                        admin_ids,
                        f'Unusual invoice: {row["invoice_number"]}',
                        message=(
                            f'Supplier "{row["supplier"]}" — '
                            f'{row["invoice_value"]:,.0f} {row["currency"]} '
                            f'({diff_pct:.0f}% from avg {avg:,.0f})'
                        ),
                        link='/app/accounting',
                        entity_type='invoice',
                        entity_id=row['id'],
                        type='warning',
                        category='smart_alert',
                    )
                    self._record_alert(cursor, 'invoice_anomaly', 'invoice',
                                       row['id'], float(row['invoice_value']))
                    count += 1

            conn.commit()
            return count
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f'Invoice anomaly check failed: {e}')
            return 0
        finally:
            release_db(conn)

    # ── e-Factura Backlog Alert ──

    def _check_efactura_backlog(self) -> int:
        """Alert admins if unallocated e-Factura count exceeds threshold."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            conn.autocommit = False
            threshold = int(self._setting('smart_efactura_backlog_threshold', '50'))

            cursor.execute('''
                SELECT COUNT(*) as cnt
                FROM efactura_invoices
                WHERE deleted_at IS NULL
                  AND jarvis_invoice_id IS NULL
                  AND ignored = FALSE
            ''')
            backlog = cursor.fetchone()['cnt']

            if backlog < threshold:
                conn.commit()
                return 0

            cooldown_hours = int(self._setting('smart_alert_cooldown_hours', '24'))

            if not self._should_alert(cursor, 'efactura_backlog', 'efactura', 0,
                                      cooldown_hours, float(backlog)):
                conn.commit()
                return 0

            admin_ids = self._get_admin_ids(cursor)
            if not admin_ids:
                conn.commit()
                return 0

            notify_users(
                admin_ids,
                f'e-Factura backlog: {backlog} unallocated invoices',
                message=f'Threshold is {threshold}. Please review and allocate.',
                link='/app/efactura',
                entity_type='efactura',
                type='warning',
                category='smart_alert',
            )
            self._record_alert(cursor, 'efactura_backlog', 'efactura', 0, float(backlog))
            conn.commit()
            return 1
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f'e-Factura backlog check failed: {e}')
            return 0
        finally:
            release_db(conn)

    # ── Helpers ──

    def _get_admin_ids(self, cursor) -> list:
        """Get IDs of active admin users."""
        cursor.execute('''
            SELECT u.id FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE r.name = 'Admin' AND u.is_active = TRUE
        ''')
        return [row['id'] for row in cursor.fetchall()]

    def _should_alert(self, cursor, alert_type: str, entity_type: str,
                      entity_id: int, cooldown_hours: int,
                      current_value: float) -> bool:
        """Check if we should send this alert (cooldown + value change)."""
        cursor.execute('''
            SELECT last_alerted_at, last_value
            FROM smart_notification_state
            WHERE alert_type = %s AND entity_type = %s AND entity_id = %s
        ''', (alert_type, entity_type, entity_id))
        row = cursor.fetchone()

        if not row:
            return True

        last_at = row['last_alerted_at']
        last_val = float(row['last_value']) if row['last_value'] is not None else None

        if datetime.utcnow() - last_at < timedelta(hours=cooldown_hours):
            # Within cooldown — only re-alert if value changed >10%
            if last_val is not None and last_val != 0:
                change = abs(current_value - last_val) / abs(last_val)
                if change < 0.1:
                    return False
            else:
                return False

        return True

    def _record_alert(self, cursor, alert_type: str, entity_type: str,
                      entity_id: int, value: float):
        """Record that we sent an alert (upsert into state table)."""
        cursor.execute('''
            INSERT INTO smart_notification_state (alert_type, entity_type, entity_id, last_alerted_at, last_value)
            VALUES (%s, %s, %s, NOW(), %s)
            ON CONFLICT (alert_type, entity_type, entity_id)
            DO UPDATE SET last_alerted_at = NOW(), last_value = %s
        ''', (alert_type, entity_type, entity_id, value, value))

    def _load_settings(self):
        """Load smart alert settings from notification_settings table."""
        now = time.time()
        if self._settings and (now - self._settings_loaded_at) < 60:
            return
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                "SELECT setting_key, setting_value FROM notification_settings WHERE setting_key LIKE 'smart_%%'"
            )
            self._settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
            self._settings_loaded_at = now
        finally:
            release_db(conn)

    def _setting(self, key: str, default: str = '') -> str:
        return self._settings.get(key, default)
