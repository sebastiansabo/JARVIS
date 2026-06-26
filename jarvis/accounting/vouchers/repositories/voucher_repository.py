"""Data access layer for vouchers."""
import json
import logging
import random
import string
from datetime import date, timedelta

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.vouchers.repository')


def _generate_voucher_code() -> str:
    """Generate VCH-YYYYMM-XXXXXX code."""
    today = date.today()
    prefix = f"VCH-{today.strftime('%Y%m')}-"
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return prefix + suffix


def _benefit_display(row: dict) -> str:
    """Format benefit for display based on voucher_type."""
    vt = row.get('voucher_type', '')
    if vt == 'value':
        val = row.get('value_lei')
        return f"{val} LEI" if val is not None else ''
    elif vt == 'accessory_discount_code':
        return row.get('discount_code') or ''
    elif vt == 'accessory_percentage':
        pct = row.get('discount_percentage')
        return f"{pct}%" if pct is not None else ''
    elif vt == 'service_items':
        items = row.get('service_items')
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except (json.JSONDecodeError, TypeError):
                items = []
        if items:
            return f"{len(items)} service item{'s' if len(items) != 1 else ''}"
        return ''
    return ''


class VoucherRepository(BaseRepository):

    def create(self, company_id: int, issued_by_user_id: int,
               client_name: str, contract_number: str, car_vin: str,
               validity_months: int, voucher_type: str,
               value_lei=None, discount_code=None,
               discount_percentage=None, service_items=None,
               approver_user_id=None, notes=None,
               client_email=None, form_submission_id=None) -> dict:
        """Insert a new voucher. Retries on code collision. Returns full row."""
        for attempt in range(5):
            code = _generate_voucher_code()
            try:
                row = self.execute('''
                    INSERT INTO vouchers
                        (company_id, voucher_code, client_name, contract_number,
                         car_vin, validity_months, issued_by_user_id, voucher_type,
                         value_lei, discount_code, discount_percentage, service_items,
                         status, approver_user_id, notes, client_email, form_submission_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            'pending_approval', %s, %s, %s, %s)
                    RETURNING *
                ''', (
                    company_id, code, client_name, contract_number,
                    car_vin, validity_months, issued_by_user_id, voucher_type,
                    value_lei, discount_code, discount_percentage,
                    json.dumps(service_items) if service_items else None,
                    approver_user_id, notes, client_email, form_submission_id,
                ), returning=True)
                return row
            except Exception as e:
                if 'unique' in str(e).lower() and 'voucher_code' in str(e).lower():
                    if attempt < 4:
                        continue
                raise
        raise RuntimeError('Failed to generate unique voucher code after 5 attempts')

    def get_by_id(self, voucher_id: int) -> dict | None:
        """Get a single voucher with joined user names."""
        return self.query_one('''
            SELECT v.*,
                   u_issued.name  AS issued_by_name,
                   u_approver.name AS approver_name,
                   u_redeemed.name AS redeemed_by_name,
                   CASE WHEN v.expires_at IS NOT NULL AND v.status = 'active'
                        THEN (v.expires_at - CURRENT_DATE)
                        ELSE NULL END AS days_remaining
            FROM vouchers v
            LEFT JOIN users u_issued   ON u_issued.id = v.issued_by_user_id
            LEFT JOIN users u_approver ON u_approver.id = v.approver_user_id
            LEFT JOIN users u_redeemed ON u_redeemed.id = v.redeemed_by_user_id
            WHERE v.id = %s
        ''', (voucher_id,))

    def get_all(self, company_id=None, status=None, voucher_type=None,
                issued_by_user_id=None, expiring_soon=False,
                date_from=None, date_to=None, expiring_within_days=None,
                limit=200, offset=0) -> list[dict]:
        """List vouchers with filters. company_id=None shows all companies."""
        conditions = []
        params = []
        if company_id:
            conditions.append('v.company_id = %s')
            params.append(company_id)

        if status:
            if isinstance(status, list):
                placeholders = ','.join(['%s'] * len(status))
                conditions.append(f'v.status IN ({placeholders})')
                params.extend(status)
            else:
                conditions.append('v.status = %s')
                params.append(status)

        if voucher_type:
            if isinstance(voucher_type, list):
                placeholders = ','.join(['%s'] * len(voucher_type))
                conditions.append(f'v.voucher_type IN ({placeholders})')
                params.extend(voucher_type)
            else:
                conditions.append('v.voucher_type = %s')
                params.append(voucher_type)

        if issued_by_user_id:
            conditions.append('v.issued_by_user_id = %s')
            params.append(issued_by_user_id)

        if expiring_soon:
            conditions.append("v.status = 'active'")
            conditions.append("v.expires_at <= CURRENT_DATE + INTERVAL '30 days'")
            conditions.append('v.expires_at >= CURRENT_DATE')

        if expiring_within_days is not None:
            conditions.append("v.status = 'active'")
            conditions.append("v.expires_at <= CURRENT_DATE + %s * INTERVAL '1 day'")
            conditions.append('v.expires_at >= CURRENT_DATE')
            params.append(expiring_within_days)

        if date_from:
            conditions.append('v.issued_at >= %s')
            params.append(date_from)

        if date_to:
            conditions.append('v.issued_at <= %s')
            params.append(date_to)

        where = ' AND '.join(conditions) if conditions else 'TRUE'
        params.extend([limit, offset])

        rows = self.query_all(f'''
            SELECT v.*,
                   u_issued.name AS issued_by_name,
                   u_approver.name AS approver_name,
                   CASE WHEN v.expires_at IS NOT NULL AND v.status = 'active'
                        THEN (v.expires_at - CURRENT_DATE)
                        ELSE NULL END AS days_remaining
            FROM vouchers v
            LEFT JOIN users u_issued ON u_issued.id = v.issued_by_user_id
            LEFT JOIN users u_approver ON u_approver.id = v.approver_user_id
            WHERE {where}
            ORDER BY v.created_at DESC
            LIMIT %s OFFSET %s
        ''', tuple(params))

        for row in rows:
            row['benefit_display'] = _benefit_display(row)
        return rows

    def get_by_user(self, user_id: int, limit=100, offset=0) -> list[dict]:
        """Get vouchers issued by a specific user (for profile tab)."""
        rows = self.query_all('''
            SELECT v.*,
                   u_issued.name AS issued_by_name,
                   u_approver.name AS approver_name,
                   CASE WHEN v.expires_at IS NOT NULL AND v.status = 'active'
                        THEN (v.expires_at - CURRENT_DATE)
                        ELSE NULL END AS days_remaining
            FROM vouchers v
            LEFT JOIN users u_issued ON u_issued.id = v.issued_by_user_id
            LEFT JOIN users u_approver ON u_approver.id = v.approver_user_id
            WHERE v.issued_by_user_id = %s OR v.approver_user_id = %s
            ORDER BY v.created_at DESC
            LIMIT %s OFFSET %s
        ''', (user_id, user_id, limit, offset))

        for row in rows:
            row['benefit_display'] = _benefit_display(row)
        return rows

    def update_status(self, voucher_id: int, status: str,
                      issued_at=None, expires_at=None,
                      approval_request_id=None) -> dict | None:
        """Update voucher status and optional fields. Returns updated row."""
        sets = ['status = %s', 'updated_at = CURRENT_TIMESTAMP']
        params = [status]

        if issued_at is not None:
            sets.append('issued_at = %s')
            params.append(issued_at)
        if expires_at is not None:
            sets.append('expires_at = %s')
            params.append(expires_at)
        if approval_request_id is not None:
            sets.append('approval_request_id = %s')
            params.append(approval_request_id)

        params.append(voucher_id)
        return self.execute(
            f"UPDATE vouchers SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def redeem(self, voucher_id: int, redeemed_by_user_id: int,
               redemption_notes: str = None) -> dict | None:
        """Mark voucher as redeemed. Returns updated row."""
        return self.execute('''
            UPDATE vouchers
            SET status = 'redeemed',
                redeemed_at = CURRENT_TIMESTAMP,
                redeemed_by_user_id = %s,
                redemption_notes = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'active' AND expires_at >= CURRENT_DATE
            RETURNING *
        ''', (redeemed_by_user_id, redemption_notes, voucher_id), returning=True)

    def archive_redeemed(self) -> int:
        """Move redeemed vouchers to archived after 2 hours. Returns count."""
        return self.execute('''
            UPDATE vouchers
            SET status = 'archived', updated_at = CURRENT_TIMESTAMP
            WHERE status = 'redeemed'
              AND redeemed_at < CURRENT_TIMESTAMP - INTERVAL '2 hours'
        ''')

    def delete_voucher(self, voucher_id: int) -> bool:
        """Hard-delete a voucher. Returns True if deleted."""
        count = self.execute(
            'DELETE FROM vouchers WHERE id = %s', (voucher_id,)
        )
        return count > 0

    def expire_active(self) -> int:
        """Set status='expired' for active vouchers past expiry. Returns count."""
        return self.execute('''
            UPDATE vouchers
            SET status = 'expired', updated_at = CURRENT_TIMESTAMP
            WHERE status = 'active' AND expires_at < CURRENT_DATE
        ''')

    def get_expiring_on(self, target_date: date) -> list[dict]:
        """Get active vouchers expiring on a specific date."""
        return self.query_all('''
            SELECT v.*, u.name AS issued_by_name, u.email AS issued_by_email
            FROM vouchers v
            JOIN users u ON u.id = v.issued_by_user_id
            WHERE v.status = 'active' AND v.expires_at = %s
        ''', (target_date,))

    def get_summary_counts(self, company_id=None) -> dict:
        """Get status counts and total active value for summary bar."""
        where = 'WHERE company_id = %s' if company_id else ''
        params = (company_id,) if company_id else ()
        row = self.query_one(f'''
            SELECT
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE status = 'active' AND expires_at <= CURRENT_DATE + INTERVAL '30 days' AND expires_at >= CURRENT_DATE) AS expiring_soon_count,
                COUNT(*) FILTER (WHERE status = 'redeemed' AND date_trunc('month', redeemed_at) = date_trunc('month', CURRENT_DATE)) AS redeemed_this_month,
                COUNT(*) FILTER (WHERE status = 'expired') AS expired_count,
                COALESCE(SUM(value_lei) FILTER (WHERE status = 'active' AND voucher_type = 'value'), 0) AS total_active_value
            FROM vouchers
            {where}
        ''', params)
        return row or {}

    def get_digest_data(self, company_id: int, ref_date: date) -> dict:
        """Get data for monthly digest email."""
        first_of_month = ref_date.replace(day=1)
        prev_month_start = (first_of_month - timedelta(days=1)).replace(day=1)
        prev_month_end = first_of_month - timedelta(days=1)
        next_month_end = (first_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        summary = self.query_one('''
            SELECT
                COUNT(*) FILTER (WHERE status = 'active') AS active_count,
                COALESCE(SUM(value_lei) FILTER (WHERE status = 'active' AND voucher_type = 'value'), 0) AS active_total_value,
                COUNT(*) FILTER (WHERE status = 'redeemed' AND redeemed_at >= %s AND redeemed_at < %s) AS redeemed_last_month,
                COALESCE(SUM(value_lei) FILTER (WHERE status = 'redeemed' AND voucher_type = 'value' AND redeemed_at >= %s AND redeemed_at < %s), 0) AS redeemed_last_month_value,
                COUNT(*) FILTER (WHERE status = 'expired' AND updated_at >= %s AND updated_at < %s) AS expired_last_month,
                COUNT(*) FILTER (WHERE status = 'active' AND expires_at >= %s AND expires_at <= %s) AS expiring_this_month,
                COUNT(*) FILTER (WHERE created_at >= %s AND created_at < %s) AS new_last_month
            FROM vouchers
            WHERE company_id = %s
        ''', (
            prev_month_start, first_of_month,
            prev_month_start, first_of_month,
            prev_month_start, first_of_month,
            first_of_month, next_month_end,
            prev_month_start, first_of_month,
            company_id,
        ))

        per_user = self.query_all('''
            SELECT
                v.issued_by_user_id,
                u.name AS user_name,
                u.email AS user_email,
                COUNT(*) FILTER (WHERE v.status = 'active') AS active_count,
                COUNT(*) FILTER (WHERE v.status = 'redeemed') AS redeemed_count,
                COUNT(*) FILTER (WHERE v.status = 'expired') AS expired_count,
                COUNT(*) FILTER (WHERE v.status = 'pending_approval') AS pending_count,
                COALESCE(SUM(v.value_lei) FILTER (WHERE v.status = 'active' AND v.voucher_type = 'value'), 0) AS active_value,
                COUNT(*) FILTER (WHERE v.status = 'active' AND v.expires_at >= %s AND v.expires_at <= %s) AS expiring_this_month
            FROM vouchers v
            JOIN users u ON u.id = v.issued_by_user_id
            WHERE v.company_id = %s
            GROUP BY v.issued_by_user_id, u.name, u.email
            ORDER BY u.name
        ''', (first_of_month, next_month_end, company_id))

        return {
            'summary': summary or {},
            'per_user': per_user,
        }
