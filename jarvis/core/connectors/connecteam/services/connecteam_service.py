"""Connecteam service — Excel import, user mapping, data queries.

Manual-import only (Connecteam plan does not include API/webhooks).
"""

import hashlib
import json
import logging
import re
from datetime import datetime, date, time

from ..repositories.connecteam_repository import ConnecteamRepository
from ..config import BILET_INVOIRE_FORM_ID, BILET_INVOIRE_FORM_NAME, JARVIS_LEAVE_FORM_SLUG

logger = logging.getLogger('jarvis.connecteam.service')

STATUS_MAP = {
    'Aprobat': 'approved',
    'Refuzat': 'rejected',
    'None': 'submitted',
    '': 'submitted',
    None: 'submitted',
}


def _safe_float(val):
    """Convert value to float, return None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _hm_to_minutes(val):
    """Parse an 'HH:MM' string to minutes since midnight, or None."""
    if not isinstance(val, str):
        return None
    m = re.match(r'^(\d{1,2}):(\d{2})$', val.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h * 60 + mi


def _leave_hours(answers):
    """Leave duration in hours. Preferred: computed from the start/end times, so
    it is robust to the display-formatted duration field ("1 h", "50 min").
    Falls back to a legacy numeric f_bi_hours (older/Connecteam submissions)."""
    s = _hm_to_minutes(answers.get('f_bi_start_time'))
    e = _hm_to_minutes(answers.get('f_bi_end_time'))
    if s is not None and e is not None and e > s:
        return round((e - s) / 60, 2)
    return _safe_float(answers.get('f_bi_hours'))


def _decider_name(decisions):
    """Name of the approver whose decision closed the request (approved/rejected)."""
    for d in decisions or []:
        if d.get('decision') in ('approved', 'rejected'):
            return d.get('decided_by_name') or None
    return None


def _pending_approver_names(request_id, submission_id=None):
    """Names of the approver(s) a still-pending request is currently waiting on.

    Falls back to looking the request up by entity when the submission has no
    linked approval_request_id (older submissions created before linking)."""
    try:
        from core.approvals.repositories import RequestRepository
        if not request_id and submission_id:
            request_id = RequestRepository().get_pending_for_entity('form_submission', submission_id)
        if not request_id:
            return []
        from core.approvals.handlers._shared import _get_current_step_approvers
        from database import get_db, get_cursor, release_db
        ids = _get_current_step_approvers(request_id)
        if not ids:
            return []
        conn = get_db()
        try:
            cur = get_cursor(conn)
            placeholders = ','.join(['%s'] * len(ids))
            cur.execute(f'SELECT name FROM users WHERE id IN ({placeholders})', list(ids))
            return [(r['name'] if isinstance(r, dict) else r[0]) for r in cur.fetchall()]
        finally:
            release_db(conn)
    except Exception as e:
        logger.warning('Pending approver lookup failed for request %s: %s', request_id, e)
        return []


def _name_to_fake_ct_id(name: str) -> int:
    """Generate a deterministic fake Connecteam user ID from a name."""
    h = hashlib.md5(name.strip().upper().encode()).hexdigest()
    return int(h[:12], 16) % 10_000_000_000


def _parse_time_str(val) -> str | None:
    """Parse time value from Excel (could be string or datetime)."""
    if val is None:
        return None
    if isinstance(val, time):
        return val.strftime('%H:%M')
    if isinstance(val, datetime):
        return val.strftime('%H:%M')
    s = str(val).strip()
    if not s:
        return None
    if ':' in s:
        parts = s.split(':')
        return f'{int(parts[0]):02d}:{int(parts[1]):02d}'
    return s


def _parse_date_val(val) -> date | None:
    """Parse date from Excel (datetime object or string)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _calc_hours(start: str | None, end: str | None) -> float | None:
    """Calculate hours between two HH:MM strings."""
    if not start or not end:
        return None
    try:
        sh, sm = map(int, start.split(':'))
        eh, em = map(int, end.split(':'))
        diff = (eh * 60 + em) - (sh * 60 + sm)
        return round(diff / 60, 2) if diff > 0 else None
    except (ValueError, TypeError):
        return None


class ConnecteamService:
    """Business logic for Connecteam manual import connector."""

    def __init__(self):
        self.repo = ConnecteamRepository()

    # ── Excel import ──

    def import_from_rows(self, rows):
        """Import rows from Excel export into DB.

        Excel columns (Bilet de Invoire export):
            0: # (entry_num)
            1: Full name
            2: Submission Date (datetime)
            3: Submission Time (redundant)
            4: Departament
            5: Data (leave_date)
            6: Ora de Plecare (start_time)
            7: Ora de Sosire (end_time)
            8: Motive (reason)
            9: Semnatura Angajat
           10: Aviz superior ierarhic (approved_by)
           11: More recipients
           12: Semnatura
           13: Click pentru APROBARE / REFUZ (status)
           14: Person
        """
        from database import get_db, get_cursor, release_db

        conn = get_db()
        cursor = get_cursor(conn)

        try:
            # Build JARVIS user lookup by uppercase name
            cursor.execute("SELECT id, name FROM users WHERE name IS NOT NULL AND COALESCE(contract_status, 'active') != 'closed'")
            jarvis_users = {}
            for u in cursor.fetchall():
                name = u['name'] if isinstance(u, dict) else u[1]
                uid = u['id'] if isinstance(u, dict) else u[0]
                jarvis_users[name.strip().upper()] = uid

            stats = {
                'rows_processed': len(rows),
                'inserted': 0,
                'skipped': 0,
                'users_created': 0,
                'unmapped_names': [],
            }

            for row in rows:
                entry_num = row[0]
                full_name = row[1]
                sub_date = row[2]
                leave_date_val = row[5]
                start_time = row[6]
                end_time = row[7]
                reason = row[8]
                approved_by = row[10]  # Aviz superior ierarhic
                person = row[14] if len(row) > 14 else None  # Person (approver)
                status_raw = row[13] if len(row) > 13 else None

                if not full_name or not entry_num:
                    continue

                name_upper = full_name.strip().upper()
                ct_user_id = _name_to_fake_ct_id(full_name)
                submission_id = f'CT-{entry_num}'

                # Skip if already imported
                cursor.execute(
                    "SELECT 1 FROM connecteam_form_submissions WHERE submission_id = %s",
                    (submission_id,))
                if cursor.fetchone():
                    stats['skipped'] += 1
                    continue

                # Check/create connecteam user
                cursor.execute(
                    "SELECT id, mapped_jarvis_user_id FROM connecteam_users WHERE connecteam_user_id = %s",
                    (ct_user_id,))
                ct_user = cursor.fetchone()

                jarvis_uid = jarvis_users.get(name_upper)
                if not jarvis_uid and full_name.strip() not in stats['unmapped_names']:
                    stats['unmapped_names'].append(full_name.strip())

                if not ct_user:
                    cursor.execute("""
                        INSERT INTO connecteam_users
                            (connecteam_user_id, connecteam_user_name, mapped_jarvis_user_id,
                             mapping_method, mapping_confidence, is_active)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                        ON CONFLICT (connecteam_user_id) DO NOTHING
                    """, (ct_user_id, full_name.strip(), jarvis_uid,
                          'name' if jarvis_uid else None,
                          80 if jarvis_uid else 0))
                    stats['users_created'] += 1
                else:
                    existing_mapped = ct_user['mapped_jarvis_user_id'] if isinstance(ct_user, dict) else ct_user[1]
                    jarvis_uid = existing_mapped or jarvis_uid

                # Parse fields
                leave_date = _parse_date_val(leave_date_val)
                start_t = _parse_time_str(start_time)
                end_t = _parse_time_str(end_time)
                hours = _calc_hours(start_t, end_t)
                status = STATUS_MAP.get(str(status_raw).strip() if status_raw else '', 'submitted')

                # Submission timestamp
                if isinstance(sub_date, datetime):
                    sub_ts = sub_date
                elif isinstance(sub_date, date):
                    sub_ts = datetime.combine(sub_date, time(0, 0))
                else:
                    sub_ts = datetime.now()

                # Clean approved_by — prefer Person column, fallback to Aviz superior
                raw_approver = person if (person and str(person).strip() and str(person).strip() not in ('None', 'none')) else approved_by
                approved_str = None
                if raw_approver and str(raw_approver).strip() and str(raw_approver).strip() not in ('None', 'none'):
                    approved_str = str(raw_approver).strip().split(',')[0].strip()

                cursor.execute("""
                    INSERT INTO connecteam_form_submissions
                        (submission_id, form_id, form_name, connecteam_user_id,
                         mapped_jarvis_user_id, submission_timestamp, submission_timezone,
                         entry_num, leave_date, leave_start_time, leave_end_time,
                         leave_hours, leave_reason, approved_by, status,
                         raw_answers, event_type, received_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    submission_id, BILET_INVOIRE_FORM_ID, BILET_INVOIRE_FORM_NAME,
                    ct_user_id, jarvis_uid, sub_ts, 'Europe/Bucharest',
                    entry_num, leave_date, start_t, end_t,
                    hours, reason, approved_str, status,
                    '[]', 'form_submission', sub_ts,
                ))
                stats['inserted'] += 1

                # Debit leave hours from Time Bank (auto-approved)
                # Only personal leave counts — lunch breaks don't affect Time Bank
                if jarvis_uid and hours and hours > 0 and str(reason or '').strip().lower() != 'pauza de masa':
                    try:
                        from hr.time_bank.service import TimeBankService
                        TimeBankService().debit(
                            user_id=jarvis_uid,
                            amount=hours,
                            tx_type='connecteam',
                            description=f'Bilet de invoire: {hours}h on {leave_date or "N/A"}',
                            reference_type='connecteam_submission',
                            reference_id=int(entry_num),
                            created_by=None,
                        )
                    except Exception as tb_err:
                        logger.warning('Time Bank credit failed for %s: %s', submission_id, tb_err)

            conn.commit()
            logger.info('Excel import: %d inserted, %d skipped, %d users created',
                        stats['inserted'], stats['skipped'], stats['users_created'])
            return stats

        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    # ── User mapping ──

    def auto_map_users(self):
        """Auto-map Connecteam users to JARVIS users by name."""
        name_mapped = self.repo.auto_map_by_name() or 0

        # Update submissions mapping for newly mapped users
        mapped_users = self.repo.get_all_users()
        for user in mapped_users:
            if user.get('mapped_jarvis_user_id'):
                self.repo.update_submissions_mapping(
                    user['connecteam_user_id'],
                    user['mapped_jarvis_user_id'],
                )

        return {
            'success': True,
            'name_mapped': name_mapped,
            'total_mapped': name_mapped,
        }

    def update_user_mapping(self, connecteam_user_id, jarvis_user_id):
        """Manually map a Connecteam user to a JARVIS user."""
        self.repo.update_user_mapping(connecteam_user_id, jarvis_user_id, method='manual')
        self.repo.update_submissions_mapping(connecteam_user_id, jarvis_user_id)

    def remove_user_mapping(self, connecteam_user_id):
        """Remove mapping for a Connecteam user."""
        self.repo.remove_user_mapping(connecteam_user_id)

    # ── Query ──

    def get_all_submissions(self, year=None, month=None, limit=500):
        """Get all leave permission submissions across all users.

        Combines data from two sources:
        - Connecteam imported submissions (connecteam_form_submissions)
        - JARVIS internal form submissions (form_submissions for 'bilet-de-invoire')
        """
        ct_submissions = self.repo.get_recent_submissions(limit, year, month)
        for s in ct_submissions:
            s['source'] = 'connecteam'

        jarvis_submissions = self._get_all_jarvis_form_submissions(year, month, limit)

        all_subs = ct_submissions + jarvis_submissions
        all_subs.sort(
            key=lambda s: s.get('leave_date') or s.get('created_at') or '',
            reverse=True,
        )
        return all_subs[:limit]

    def _get_all_jarvis_form_submissions(self, year=None, month=None, limit=500):
        """Fetch ALL JARVIS internal 'Bilet de Invoire' form submissions."""
        from database import get_db, get_cursor, release_db, dict_from_row

        conn = get_db()
        cursor = get_cursor(conn)
        try:
            cursor.execute(
                "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL LIMIT 1",
                (JARVIS_LEAVE_FORM_SLUG,)
            )
            form_row = cursor.fetchone()
            if not form_row:
                return []

            form_id = form_row['id'] if isinstance(form_row, dict) else form_row[0]

            query = '''
                SELECT fs.id, fs.form_id, f.name AS form_name,
                       fs.answers, fs.status, fs.source, fs.approval_request_id,
                       fs.respondent_user_id, fs.created_at::text,
                       u.name AS respondent_name,
                       u.company AS respondent_company
                FROM form_submissions fs
                JOIN forms f ON f.id = fs.form_id
                LEFT JOIN users u ON u.id = fs.respondent_user_id
                WHERE fs.form_id = %s
            '''
            params: list = [form_id]

            if year:
                query += " AND EXTRACT(YEAR FROM fs.created_at) = %s"
                params.append(year)
            if month:
                query += " AND EXTRACT(MONTH FROM fs.created_at) = %s"
                params.append(month)

            query += ' ORDER BY fs.created_at DESC LIMIT %s'
            params.append(limit)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            from core.approvals.repositories import DecisionRepository
            dec_repo = DecisionRepository()

            results = []
            for row in rows:
                r = dict_from_row(row) if not isinstance(row, dict) else dict(row)
                answers = r.get('answers', {})
                if isinstance(answers, str):
                    answers = json.loads(answers)

                request_id = r.get('approval_request_id')
                status = r.get('status', 'new')
                approved_by = (
                    _decider_name(dec_repo.get_decisions_for_request(request_id))
                    if request_id else None
                ) or answers.get('f_bi_approved_by')
                pending_approvers = (
                    _pending_approver_names(request_id, r['id'])
                    if status not in ('approved', 'rejected') else []
                )

                results.append({
                    'id': r['id'],
                    'submission_id': f"jarvis-{r['id']}",
                    'form_id': r['form_id'],
                    'form_name': r.get('form_name', BILET_INVOIRE_FORM_NAME),
                    'connecteam_user_id': None,
                    'mapped_jarvis_user_id': r.get('respondent_user_id'),
                    'connecteam_user_name': r.get('respondent_name'),
                    'jarvis_user_name': r.get('respondent_name'),
                    'jarvis_user_company': r.get('respondent_company'),
                    'submission_timestamp': r.get('created_at'),
                    'leave_date': answers.get('f_bi_leave_date'),
                    'leave_start_time': answers.get('f_bi_start_time'),
                    'leave_end_time': answers.get('f_bi_end_time'),
                    'leave_hours': _leave_hours(answers),
                    'leave_reason': answers.get('f_bi_reason'),
                    'leave_destination': answers.get('f_bi_destination'),
                    'approved_by': approved_by,
                    'pending_approvers': pending_approvers,
                    'status': r.get('status', 'new'),
                    'event_type': 'jarvis_form',
                    'entry_num': None,
                    'received_at': r.get('created_at'),
                    'created_at': r.get('created_at'),
                    'source': 'jarvis',
                })
            return results
        except Exception as e:
            logger.error('Error fetching all JARVIS form submissions: %s', e)
            return []
        finally:
            release_db(conn)

    def get_user_submissions(self, jarvis_user_id, year=None, month=None):
        """Get leave permission submissions for a JARVIS user.

        Combines data from two sources:
        - Connecteam imported submissions (connecteam_form_submissions)
        - JARVIS internal form submissions (form_submissions for 'bilet-de-invoire')
        """
        ct_submissions = self.repo.get_submissions_by_jarvis_user(
            jarvis_user_id, year, month
        )
        for s in ct_submissions:
            s['source'] = 'connecteam'

        jarvis_submissions = self._get_jarvis_form_submissions(
            jarvis_user_id, year, month
        )

        all_subs = ct_submissions + jarvis_submissions
        all_subs.sort(
            key=lambda s: s.get('leave_date') or s.get('created_at') or '',
            reverse=True,
        )
        return all_subs

    def get_pending_leave_approvals(self, user_id):
        """Leave requests awaiting this user's approval (primary or backup approver).

        Naturally scoped: only requests where the user is a current-step approver
        are returned, so a non-approver gets an empty list.
        """
        from core.approvals.handlers._shared import _get_current_step_approvers
        from database import get_db, get_cursor, release_db, dict_from_row
        conn = get_db()
        cursor = get_cursor(conn)
        try:
            cursor.execute('''
                SELECT r.id AS request_id, r.entity_id AS submission_id,
                       fs.answers, r.requested_at::text AS requested_at,
                       u.name AS requester_name, r.context_snapshot
                FROM approval_requests r
                JOIN form_submissions fs ON fs.id = r.entity_id
                JOIN forms f ON f.id = fs.form_id
                JOIN users u ON u.id = r.requested_by
                WHERE r.entity_type = 'form_submission'
                  AND r.status IN ('pending', 'in_progress')
                  AND f.slug = %s
                ORDER BY r.requested_at DESC
            ''', (JARVIS_LEAVE_FORM_SLUG,))
            rows = cursor.fetchall()
        finally:
            release_db(conn)

        out = []
        for row in rows:
            r = dict_from_row(row) if not isinstance(row, dict) else dict(row)
            if user_id not in (_get_current_step_approvers(r['request_id']) or []):
                continue
            answers = r.get('answers') or {}
            if isinstance(answers, str):
                answers = json.loads(answers)
            ctx = r.get('context_snapshot') or {}
            if isinstance(ctx, str):
                ctx = json.loads(ctx)
            out.append({
                'request_id': r['request_id'],
                'submission_id': r['submission_id'],
                'requester_name': r.get('requester_name'),
                'leave_date': answers.get('f_bi_leave_date'),
                'leave_start_time': answers.get('f_bi_start_time'),
                'leave_end_time': answers.get('f_bi_end_time'),
                'leave_hours': _leave_hours(answers),
                'leave_reason': answers.get('f_bi_reason'),
                'requested_at': r.get('requested_at'),
                'is_cancellation': bool(ctx.get('cancellation')),
                'cancellation_reason': ctx.get('cancellation_reason') or None,
            })
        return out

    def decide_leave_approval(self, request_id, decision, user_id, comment=None):
        """Approve/reject a leave request the user is a current-step approver for."""
        from core.approvals.handlers._shared import _get_current_step_approvers
        from core.approvals.engine import ApprovalEngine
        if user_id not in (_get_current_step_approvers(request_id) or []):
            raise PermissionError('Not an approver for this request')
        return ApprovalEngine().decide(request_id, decision, user_id, comment=comment)

    def _get_jarvis_form_submissions(self, jarvis_user_id, year=None, month=None):
        """Fetch JARVIS internal 'Bilet de Invoire' form submissions for a user."""
        from database import get_db, get_cursor, release_db, dict_from_row

        conn = get_db()
        cursor = get_cursor(conn)
        try:
            cursor.execute(
                "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL LIMIT 1",
                (JARVIS_LEAVE_FORM_SLUG,)
            )
            form_row = cursor.fetchone()
            if not form_row:
                return []

            form_id = form_row['id'] if isinstance(form_row, dict) else form_row[0]

            query = '''
                SELECT fs.id, fs.form_id, f.name AS form_name,
                       fs.answers, fs.status, fs.source, fs.approval_request_id,
                       fs.respondent_user_id, fs.created_at::text,
                       u.name AS respondent_name
                FROM form_submissions fs
                JOIN forms f ON f.id = fs.form_id
                LEFT JOIN users u ON u.id = fs.respondent_user_id
                WHERE fs.form_id = %s AND fs.respondent_user_id = %s
            '''
            params = [form_id, jarvis_user_id]

            if year:
                query += " AND EXTRACT(YEAR FROM fs.created_at) = %s"
                params.append(year)
            if month:
                query += " AND EXTRACT(MONTH FROM fs.created_at) = %s"
                params.append(month)

            query += ' ORDER BY fs.created_at DESC'
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            from core.approvals.repositories import DecisionRepository
            dec_repo = DecisionRepository()

            results = []
            for row in rows:
                r = dict_from_row(row) if not isinstance(row, dict) else dict(row)
                answers = r.get('answers', {})
                if isinstance(answers, str):
                    answers = json.loads(answers)

                request_id = r.get('approval_request_id')
                status = r.get('status', 'new')
                approved_by = (
                    _decider_name(dec_repo.get_decisions_for_request(request_id))
                    if request_id else None
                ) or answers.get('f_bi_approved_by')
                pending_approvers = (
                    _pending_approver_names(request_id, r['id'])
                    if status not in ('approved', 'rejected') else []
                )

                results.append({
                    'id': r['id'],
                    'submission_id': f"jarvis-{r['id']}",
                    'form_id': r['form_id'],
                    'form_name': r.get('form_name', BILET_INVOIRE_FORM_NAME),
                    'connecteam_user_id': None,
                    'mapped_jarvis_user_id': jarvis_user_id,
                    'connecteam_user_name': r.get('respondent_name'),
                    'submission_timestamp': r.get('created_at'),
                    'leave_date': answers.get('f_bi_leave_date'),
                    'leave_start_time': answers.get('f_bi_start_time'),
                    'leave_end_time': answers.get('f_bi_end_time'),
                    'leave_hours': _leave_hours(answers),
                    'leave_reason': answers.get('f_bi_reason'),
                    'leave_destination': answers.get('f_bi_destination'),
                    'approved_by': approved_by,
                    'pending_approvers': pending_approvers,
                    'status': r.get('status', 'new'),
                    'event_type': 'jarvis_form',
                    'entry_num': None,
                    'received_at': r.get('created_at'),
                    'created_at': r.get('created_at'),
                    'source': 'jarvis',
                })
            return results
        except Exception as e:
            logger.error('Error fetching JARVIS form submissions: %s', e)
            return []
        finally:
            release_db(conn)

    def get_status(self):
        """Get connector status (submission/user counts)."""
        stats = self.repo.get_stats()
        return {
            'connected': True,
            'status': 'manual_import',
            'form_name': BILET_INVOIRE_FORM_NAME,
            'total_users': stats.get('total_users', 0) if stats else 0,
            'mapped_users': stats.get('mapped_users', 0) if stats else 0,
            'unmapped_users': stats.get('unmapped_users', 0) if stats else 0,
            'total_submissions': stats.get('total_submissions', 0) if stats else 0,
            'last_import_at': stats.get('last_import_at') if stats else None,
        }
