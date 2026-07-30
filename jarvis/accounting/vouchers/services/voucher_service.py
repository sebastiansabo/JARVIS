"""Business logic for voucher operations."""
import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from accounting.vouchers.repositories import VoucherRepository
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.vouchers.service')


class VoucherService:

    def __init__(self):
        self.repo = VoucherRepository()
        self._base = BaseRepository()

    def resolve_approver(self, user_id: int, company_id: int,
                         explicit_approver_id: int = None) -> dict | None:
        """Resolve the approver for a voucher.

        If explicit_approver_id is given, return that user.
        Otherwise, look up the user's manager from org structure:
          1. Find user's org_unit_id -> parent structure_node -> responsable
          2. Fallback to company_responsables (L0)

        Returns dict with 'id', 'name', 'email' or None if not found.
        """
        if explicit_approver_id:
            return self._base.query_one(
                'SELECT id, name, email FROM users WHERE id = %s',
                (explicit_approver_id,)
            )

        # Try structure_nodes: find user's node, then parent's responsable
        user_row = self._base.query_one(
            'SELECT org_unit_id FROM users WHERE id = %s', (user_id,)
        )
        if user_row and user_row.get('org_unit_id'):
            node = self._base.query_one('''
                SELECT sn_parent.responsable_user_id
                FROM structure_nodes sn
                JOIN structure_nodes sn_parent ON sn_parent.id = sn.parent_id
                WHERE sn.id = %s AND sn_parent.responsable_user_id IS NOT NULL
            ''', (user_row['org_unit_id'],))
            if node and node.get('responsable_user_id'):
                return self._base.query_one(
                    'SELECT id, name, email FROM users WHERE id = %s',
                    (node['responsable_user_id'],)
                )

        # Fallback: company_responsables (L0)
        resp = self._base.query_one('''
            SELECT cr.user_id, u.name, u.email
            FROM company_responsables cr
            JOIN users u ON u.id = cr.user_id
            WHERE cr.company_id = %s
            LIMIT 1
        ''', (company_id,))
        if resp:
            return {'id': resp['user_id'], 'name': resp['name'], 'email': resp['email']}

        return None

    def create_voucher(self, data: dict, user_id: int, company_id: int) -> dict:
        """Create a voucher and submit for approval.

        Args:
            data: Validated VoucherCreate dict
            user_id: Current user ID
            company_id: Current user's company ID

        Returns: Created voucher dict with approver info

        Raises: ValueError if no approver can be resolved, or if submission
            to the approval engine fails. In the latter case the voucher row
            (already inserted) is deleted so no orphan pending voucher is
            left behind (fail closed — design doc §6.A5).
        """
        # Resolve approver BEFORE inserting the voucher — fail closed.
        approver = self.resolve_approver(
            user_id, company_id,
            explicit_approver_id=data.get('approver_user_id')
        )
        if not approver:
            raise ValueError('Nu s-a putut determina un aprobator pentru voucher')

        # Create voucher
        voucher = self.repo.create(
            company_id=company_id,
            issued_by_user_id=user_id,
            client_name=data['client_name'],
            contract_number=data['contract_number'],
            car_vin=data['car_vin'],
            validity_months=data['validity_months'],
            voucher_type=data['voucher_type'],
            value_lei=data.get('value_lei'),
            discount_code=data.get('discount_code'),
            discount_percentage=data.get('discount_percentage'),
            service_items=data.get('service_items'),
            approver_user_id=approver['id'],
            notes=data.get('notes'),
        )

        # Submit to approval engine — fail closed: if this fails, roll back
        # the voucher row rather than leaving an orphan pending_approval
        # voucher with no approval request behind it.
        try:
            from core.approvals.engine import ApprovalEngine
            engine = ApprovalEngine()
            context = {
                'title': f"Voucher {voucher['voucher_code']} — {voucher['client_name']}",
                'voucher_code': voucher['voucher_code'],
                'client_name': voucher['client_name'],
                'voucher_type': voucher['voucher_type'],
                'value_lei': str(voucher.get('value_lei') or ''),
                'discount_code': voucher.get('discount_code') or '',
                'discount_percentage': str(voucher.get('discount_percentage') or ''),
                'company_id': company_id,
                'approver_user_id': approver['id'],
                'stakeholder_approver_ids': [approver['id']],
            }
            approval = engine.submit(
                entity_type='voucher',
                entity_id=voucher['id'],
                context=context,
                requested_by=user_id,
            )
            if not approval:
                raise RuntimeError('ApprovalEngine.submit returned no approval request')
            self.repo.update_status(
                voucher['id'],
                status='pending_approval',
                approval_request_id=approval.get('id'),
            )
        except Exception as e:
            logger.error(
                'Failed to submit voucher %s for approval — rolling back voucher creation',
                voucher['voucher_code'], exc_info=True,
            )
            self.repo.delete_voucher(voucher['id'])
            raise ValueError('Trimiterea spre aprobare a eșuat') from e

        voucher['approver_name'] = approver['name']
        return voucher

    def activate_voucher(self, voucher_id: int):
        """Called by approval hook when voucher is approved."""
        voucher = self.repo.get_by_id(voucher_id)
        if not voucher:
            logger.warning('Voucher %s not found for activation', voucher_id)
            return

        # Use f_start_date from form submission if available, else today
        start = date.today()
        if voucher.get('form_submission_id'):
            try:
                from forms.repositories import SubmissionRepository
                sub = SubmissionRepository().get_by_id(voucher['form_submission_id'])
                if sub:
                    raw = (sub.get('answers') or {}).get('f_start_date', '')
                    if raw:
                        start = date.fromisoformat(str(raw)[:10])
            except Exception:
                pass

        expires = start + relativedelta(months=voucher['validity_months'])
        self.repo.update_status(
            voucher_id,
            status='active',
            issued_at=start,
            expires_at=expires,
        )
        logger.info('Voucher %s activated, issued %s expires %s', voucher['voucher_code'], start, expires)

        # Notify issuer
        self._notify_issuer_approved(voucher)

    def reject_voucher(self, voucher_id: int, reason: str = None):
        """Called by approval hook when voucher is rejected."""
        voucher = self.repo.get_by_id(voucher_id)
        if not voucher:
            return

        self.repo.update_status(voucher_id, status='rejected')
        logger.info('Voucher %s rejected', voucher['voucher_code'])

        self._notify_issuer_rejected(voucher, reason)

    def redeem_voucher(self, voucher_id: int, redeemed_by_user_id: int,
                       notes: str = None) -> dict | None:
        """Mark voucher as redeemed. Returns updated row or None."""
        voucher = self.repo.get_by_id(voucher_id)
        if not voucher:
            return None
        if voucher['status'] != 'active':
            raise ValueError(f"Cannot redeem voucher with status '{voucher['status']}'")
        expires = voucher.get('expires_at')
        if expires:
            if isinstance(expires, str):
                expires = date.fromisoformat(expires)
            if expires < date.today():
                raise ValueError('Cannot redeem expired voucher')

        result = self.repo.redeem(voucher_id, redeemed_by_user_id, notes)
        if result:
            self._notify_issuer_redeemed(voucher, redeemed_by_user_id)
        return result

    # -- Notifications -----------------------------------------------
    # NOTE: the approver is now notified by the approval engine's own
    # `_on_submitted` hook (context carries `approver_user_id` /
    # `stakeholder_approver_ids` as of Slice 1 — design doc §6.A2), so the
    # old service-level `_notify_approver` email was retired to avoid a
    # duplicate notification.

    def _notify_issuer_approved(self, voucher: dict):
        try:
            from core.services.notification_service import send_email
            issuer = self._base.query_one(
                'SELECT email FROM users WHERE id = %s', (voucher['issued_by_user_id'],)
            )
            if issuer:
                send_email(
                    to_email=issuer['email'],
                    subject=f"Voucher {voucher['voucher_code']} approved and active",
                    html_body=f"<p>Your voucher <strong>{voucher['voucher_code']}</strong> for client {voucher['client_name']} has been approved and is now active.</p>",
                )
        except Exception:
            logger.exception('Failed to notify issuer for voucher %s', voucher['voucher_code'])

    def _notify_issuer_rejected(self, voucher: dict, reason: str = None):
        try:
            from core.services.notification_service import send_email
            issuer = self._base.query_one(
                'SELECT email FROM users WHERE id = %s', (voucher['issued_by_user_id'],)
            )
            if issuer:
                reason_text = f" Reason: {reason}" if reason else ""
                send_email(
                    to_email=issuer['email'],
                    subject=f"Voucher {voucher['voucher_code']} rejected",
                    html_body=f"<p>Your voucher <strong>{voucher['voucher_code']}</strong> has been rejected.{reason_text}</p>",
                )
        except Exception:
            logger.exception('Failed to notify issuer for voucher %s', voucher['voucher_code'])

    def _notify_issuer_redeemed(self, voucher: dict, redeemed_by_user_id: int):
        try:
            from core.services.notification_service import send_email
            issuer = self._base.query_one(
                'SELECT email FROM users WHERE id = %s', (voucher['issued_by_user_id'],)
            )
            redeemer = self._base.query_one(
                'SELECT name FROM users WHERE id = %s', (redeemed_by_user_id,)
            )
            if issuer:
                redeemer_name = redeemer['name'] if redeemer else 'accounting'
                send_email(
                    to_email=issuer['email'],
                    subject=f"Voucher {voucher['voucher_code']} was redeemed",
                    html_body=f"<p>Your voucher <strong>{voucher['voucher_code']}</strong> was redeemed by {redeemer_name}.</p>",
                )
        except Exception:
            logger.exception('Failed to notify issuer for voucher %s', voucher['voucher_code'])
