"""Repository for form_submissions table."""

import json
import logging
from core.base_repository import BaseRepository
from database import dict_from_row

logger = logging.getLogger('jarvis.forms.submission_repo')


class SubmissionRepository(BaseRepository):

    def get_by_id(self, submission_id):
        """Get submission by ID with form name."""
        return self.query_one('''
            SELECT fs.*,
                   f.name as form_name,
                   f.slug as form_slug,
                   u.name as respondent_user_name
            FROM form_submissions fs
            JOIN forms f ON f.id = fs.form_id
            LEFT JOIN users u ON u.id = fs.respondent_user_id
            WHERE fs.id = %s
        ''', (submission_id,))

    def list_by_form(self, form_id, filters=None):
        """List submissions for a form with pagination."""
        filters = filters or {}
        where = ['fs.form_id = %s']
        params = [form_id]

        if filters.get('status'):
            where.append('fs.status = %s')
            params.append(filters['status'])
        if filters.get('source'):
            where.append('fs.source = %s')
            params.append(filters['source'])
        if filters.get('date_from'):
            where.append('fs.created_at >= %s')
            params.append(filters['date_from'])
        if filters.get('date_to'):
            where.append('fs.created_at <= %s')
            params.append(filters['date_to'])
        if filters.get('search'):
            where.append('''(
                fs.respondent_name ILIKE %s
                OR fs.respondent_email ILIKE %s
                OR fs.answers::text ILIKE %s
            )''')
            term = f"%{filters['search']}%"
            params.extend([term, term, term])

        where_clause = ' AND '.join(where)
        limit = min(int(filters.get('limit', 50)), 500)
        offset = int(filters.get('offset', 0))

        def _work(cursor):
            cursor.execute(f'''
                SELECT fs.*,
                       u.name as respondent_user_name
                FROM form_submissions fs
                LEFT JOIN users u ON u.id = fs.respondent_user_id
                WHERE {where_clause}
                ORDER BY fs.created_at DESC
                LIMIT %s OFFSET %s
            ''', params + [limit, offset])
            rows = cursor.fetchall()

            cursor.execute(f'''
                SELECT COUNT(*) as total
                FROM form_submissions fs
                WHERE {where_clause}
            ''', params)
            total = cursor.fetchone()['total']

            return {'submissions': [dict_from_row(r) for r in rows], 'total': total}
        return self.execute_many(_work)

    def create(self, form_id, form_version, answers, form_schema_snapshot,
               source='web_public', company_id=None, **kwargs):
        """Create a new submission. Returns the new submission ID."""
        return self.execute('''
            INSERT INTO form_submissions
                (form_id, form_version, answers, form_schema_snapshot,
                 respondent_name, respondent_email, respondent_phone,
                 respondent_ip, respondent_user_id,
                 utm_data, source, company_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::inet, %s, %s, %s, %s)
            RETURNING id
        ''', (
            form_id, form_version,
            json.dumps(answers),
            json.dumps(form_schema_snapshot),
            kwargs.get('respondent_name'),
            kwargs.get('respondent_email'),
            kwargs.get('respondent_phone'),
            kwargs.get('respondent_ip'),
            kwargs.get('respondent_user_id'),
            json.dumps(kwargs.get('utm_data', {})),
            source,
            company_id,
        ), returning=True)['id']

    def update_status(self, submission_id, status):
        """Update submission status."""
        return self.execute('''
            UPDATE form_submissions
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (status, submission_id)) > 0

    def set_approval_request(self, submission_id, approval_request_id):
        """Link submission to an approval request."""
        return self.execute('''
            UPDATE form_submissions
            SET approval_request_id = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (approval_request_id, submission_id)) > 0

    def export_by_form(self, form_id):
        """Get all submissions for export (no pagination)."""
        return self.query_all('''
            SELECT fs.*,
                   u.name as respondent_user_name
            FROM form_submissions fs
            LEFT JOIN users u ON u.id = fs.respondent_user_id
            WHERE fs.form_id = %s
            ORDER BY fs.created_at ASC
        ''', (form_id,))
