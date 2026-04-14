"""Mobile dashboard repository — aggregated stats for the mobile home screen."""
import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.mobile.dashboard_repo')


class MobileDashboardRepository(BaseRepository):

    def get_invoice_stats(self):
        """Return (total_count, revenue, pending_count) for invoices."""
        try:
            row = self.query_one('''
                SELECT COUNT(*), COALESCE(SUM(invoice_value), 0),
                       COUNT(*) FILTER (WHERE status = 'pending')
                FROM invoices WHERE deleted_at IS NULL
            ''')
            if row:
                vals = list(row.values()) if isinstance(row, dict) else list(row)
                return int(vals[0]), float(vals[1]), int(vals[2])
        except Exception as e:
            logger.warning('get_invoice_stats failed: %s', e)
        return 0, 0.0, 0

    def get_pending_approvals_count(self, user_id):
        """Return pending approval decisions count for user."""
        try:
            row = self.query_one('''
                SELECT COUNT(*) FROM approval_decisions ad
                JOIN approval_requests ar ON ar.id = ad.request_id
                WHERE ad.decided_by = %s AND ad.decision = 'pending' AND ar.status = 'pending'
            ''', (user_id,))
            vals = list(row.values()) if isinstance(row, dict) else list(row)
            return int(vals[0]) if row else 0
        except Exception as e:
            logger.warning('get_pending_approvals_count failed: %s', e)
            return 0

    def get_pending_signatures_count(self, user_id):
        """Return pending signature requests count for user."""
        try:
            row = self.query_one('''
                SELECT COUNT(*) FROM document_signatures
                WHERE signed_by = %s AND status = 'pending'
            ''', (user_id,))
            vals = list(row.values()) if isinstance(row, dict) else list(row)
            return int(vals[0]) if row else 0
        except Exception as e:
            logger.warning('get_pending_signatures_count failed: %s', e)
            return 0

    def get_client_count(self):
        """Return total active (non-blacklisted) client count."""
        try:
            row = self.query_one('SELECT COUNT(*) FROM crm_clients WHERE is_blacklisted = false')
            vals = list(row.values()) if isinstance(row, dict) else list(row)
            return int(vals[0]) if row else 0
        except Exception as e:
            logger.warning('get_client_count failed: %s', e)
            return 0

    def get_recent_invoices(self, limit=5):
        """Return most recent invoices."""
        try:
            return self.query_all('''
                SELECT id, invoice_number, supplier, invoice_value AS amount,
                       currency, invoice_date AS date, status
                FROM invoices WHERE deleted_at IS NULL
                ORDER BY created_at DESC LIMIT %s
            ''', (limit,))
        except Exception as e:
            logger.warning('get_recent_invoices failed: %s', e)
            return []

    def get_recent_clients(self, limit=5):
        """Return most recently created active clients."""
        try:
            return self.query_all('''
                SELECT id, display_name AS name, company_name AS cui,
                       '' AS contact_person, phone, email, city, client_type AS status
                FROM crm_clients WHERE is_blacklisted = false
                ORDER BY created_at DESC LIMIT %s
            ''', (limit,))
        except Exception as e:
            logger.warning('get_recent_clients failed: %s', e)
            return []

    def get_upcoming_events(self, limit=3):
        """Return upcoming HR events. Returns [] if table doesn't exist."""
        try:
            exists_row = self.query_one('''
                SELECT EXISTS (SELECT 1 FROM information_schema.tables
                               WHERE table_schema = 'public' AND table_name = 'hr_events')
            ''')
            exists = list(exists_row.values())[0] if isinstance(exists_row, dict) else exists_row[0]
            if not exists:
                return []
            return self.query_all('''
                SELECT he.id, he.title, he.event_date AS date, he.end_date,
                       he.location, he.event_type AS type, he.status,
                       (SELECT COUNT(*) FROM hr_event_participants WHERE event_id = he.id) AS participants_count
                FROM hr_events he WHERE he.event_date >= CURRENT_DATE
                ORDER BY he.event_date ASC LIMIT %s
            ''', (limit,))
        except Exception as e:
            logger.warning('get_upcoming_events failed: %s', e)
            return []

    def get_pending_approvals_widget(self, user_id):
        """Return pending step-based approval count for widget."""
        try:
            row = self.query_one('''
                SELECT COUNT(*) FROM approval_step_decisions asd
                JOIN approval_request_steps ars ON ars.id = asd.step_id
                JOIN approval_requests ar ON ar.id = ars.request_id
                WHERE asd.approver_id = %s AND asd.decision = 'pending' AND ar.status = 'pending'
            ''', (user_id,))
            vals = list(row.values()) if isinstance(row, dict) else list(row)
            return int(vals[0]) if row else 0
        except Exception as e:
            logger.warning('get_pending_approvals_widget failed: %s', e)
            return 0

    def get_next_event(self):
        """Return the next upcoming HR event title and date, or (None, None)."""
        try:
            row = self.query_one('''
                SELECT title, event_date FROM hr_events
                WHERE event_date >= CURRENT_DATE
                ORDER BY event_date ASC LIMIT 1
            ''')
            if row:
                vals = list(row.values()) if isinstance(row, dict) else list(row)
                return vals[0], str(vals[1])
        except Exception as e:
            logger.warning('get_next_event failed: %s', e)
        return None, None
