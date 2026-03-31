"""Form submission management routes (authenticated)."""

import csv
import io
import logging
import re

from flask import jsonify, request, make_response, g
from flask_login import login_required, current_user

from forms import forms_bp
from forms.repositories import FormRepository, SubmissionRepository
from forms.services.form_service import FormService, UserContext
from core.utils.api_helpers import get_json_or_error, handle_api_errors, v2_permission_required

logger = logging.getLogger('jarvis.forms.routes.submissions')

_form_repo = FormRepository()
_submission_repo = SubmissionRepository()
_service = FormService()

# Max rows in a single CSV export
_EXPORT_LIMIT = 10_000


def form_permission_required(entity, action):
    return v2_permission_required('forms', entity, action)


def _check_scope_access(record):
    """Return True if current_user can access this record based on V2 scope."""
    if not record:
        return False
    scope = getattr(g, 'permission_scope', 'all')
    if scope == 'all':
        return True
    if scope == 'department':
        return record.get('company_id') == getattr(current_user, 'company_id', None)
    if scope == 'own':
        return record.get('owner_id') == current_user.id or record.get('created_by') == current_user.id
    return False


def _sanitize_csv_value(value):
    """Escape values that could trigger formula injection in spreadsheets."""
    if value is None:
        return ''
    s = str(value)
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r', '\n'):
        return "'" + s
    return s


# ---- List submissions for a form ----

@forms_bp.route('/api/forms/<int:form_id>/submissions', methods=['GET'])
@login_required
@form_permission_required('submission', 'view')
def api_list_submissions(form_id):
    """List submissions for a form with filters."""
    form = _form_repo.get_by_id(form_id)
    if not form or not _check_scope_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    filters = {
        'status': request.args.get('status'),
        'source': request.args.get('source'),
        'search': request.args.get('search'),
        'date_from': request.args.get('date_from'),
        'date_to': request.args.get('date_to'),
        'limit': request.args.get('limit', 50),
        'offset': request.args.get('offset', 0),
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    result = _submission_repo.list_by_form(form_id, filters)
    return jsonify(result)


# ---- Get single submission ----

@forms_bp.route('/api/submissions/<int:submission_id>', methods=['GET'])
@login_required
@form_permission_required('submission', 'view')
def api_get_submission(submission_id):
    """Get submission detail."""
    submission = _submission_repo.get_by_id(submission_id)
    if not submission or not _check_scope_access(submission):
        return jsonify({'success': False, 'error': 'Submission not found'}), 404
    return jsonify(submission)


# ---- Update submission status ----

@forms_bp.route('/api/submissions/<int:submission_id>/status', methods=['PUT'])
@login_required
@form_permission_required('submission', 'edit')
@handle_api_errors
def api_update_submission_status(submission_id):
    """Update submission status (read, flagged, etc.)."""
    submission = _submission_repo.get_by_id(submission_id)
    if not submission or not _check_scope_access(submission):
        return jsonify({'success': False, 'error': 'Submission not found'}), 404

    data, error = get_json_or_error()
    if error:
        return error

    status = data.get('status')
    if status not in ('new', 'read', 'flagged'):
        return jsonify({'success': False, 'error': 'Invalid status'}), 400

    _submission_repo.update_status(submission_id, status)
    return jsonify({'success': True})


# ---- Trigger approval ----

@forms_bp.route('/api/submissions/<int:submission_id>/approve', methods=['POST'])
@login_required
@form_permission_required('submission', 'approve')
@handle_api_errors
def api_trigger_approval(submission_id):
    """Submit a form response for approval."""
    submission = _submission_repo.get_by_id(submission_id)
    if not submission or not _check_scope_access(submission):
        return jsonify({'success': False, 'error': 'Submission not found'}), 404

    result = _service.trigger_approval(submission_id, current_user.id)
    if result.success:
        return jsonify({'success': True, **result.data})
    return jsonify({'success': False, 'error': result.error}), result.status_code


# ---- Internal submission ----

@forms_bp.route('/api/forms/<int:form_id>/submit', methods=['POST'])
@login_required
@form_permission_required('form', 'view')
@handle_api_errors
def api_submit_internal(form_id):
    """Submit a form as a logged-in user."""
    form = _form_repo.get_by_id(form_id)
    if not form or not _check_scope_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    data, error = get_json_or_error()
    if error:
        return error

    user = UserContext(user_id=current_user.id)
    source = data.get('source', 'web_internal')
    if source not in ('web_internal', 'mobile'):
        source = 'web_internal'

    result = _service.submit_internal(form_id, data.get('answers', {}), user, source)
    if result.success:
        return jsonify({'success': True, **result.data}), result.status_code
    return jsonify({'success': False, 'error': result.error}), result.status_code


# ---- CSV Export ----

@forms_bp.route('/api/forms/<int:form_id>/export', methods=['GET'])
@login_required
@form_permission_required('submission', 'view')
def api_export_submissions(form_id):
    """Export form submissions as CSV."""
    form = _form_repo.get_by_id(form_id)
    if not form or not _check_scope_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    submissions = _submission_repo.export_by_form(form_id, limit=_EXPORT_LIMIT)
    if not submissions:
        return jsonify({'success': False, 'error': 'No submissions to export'}), 404

    # Build CSV using form schema for column headers
    schema = form.get('published_schema') or form.get('schema', [])
    field_ids = []
    headers = ['#', 'Submitted At', 'Source', 'Status', 'Respondent Name',
               'Respondent Email', 'Respondent Phone']

    for field in schema:
        if field.get('type') not in ('heading', 'paragraph'):
            field_ids.append(field.get('id'))
            headers.append(field.get('label', field.get('id', '')))

    # UTM columns
    utm_keys = set()
    for sub in submissions:
        utm = sub.get('utm_data', {})
        if isinstance(utm, dict):
            utm_keys.update(utm.keys())
    utm_keys = sorted(utm_keys)
    headers.extend(utm_keys)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for idx, sub in enumerate(submissions, 1):
        answers = sub.get('answers', {})
        if isinstance(answers, str):
            import json
            answers = json.loads(answers)
        utm = sub.get('utm_data', {})
        if isinstance(utm, str):
            import json
            utm = json.loads(utm)

        row = [
            idx,
            _sanitize_csv_value(sub.get('created_at', '')),
            _sanitize_csv_value(sub.get('source', '')),
            _sanitize_csv_value(sub.get('status', '')),
            _sanitize_csv_value(sub.get('respondent_name', '')),
            _sanitize_csv_value(sub.get('respondent_email', '')),
            _sanitize_csv_value(sub.get('respondent_phone', '')),
        ]
        for fid in field_ids:
            val = answers.get(fid, '')
            if isinstance(val, list):
                val = ', '.join(str(v) for v in val)
            row.append(_sanitize_csv_value(val))
        for uk in utm_keys:
            row.append(_sanitize_csv_value(utm.get(uk, '')))

        writer.writerow(row)

    # Sanitize slug for Content-Disposition
    safe_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', form.get('slug', 'export'))
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{safe_slug}-submissions.csv"'
    return response
