"""HR Course Invoice linking routes."""
from ._shared import *  # noqa: F401, F403
from core.base_repository import BaseRepository

_repo = BaseRepository()


@courses_bp.route('/api/courses/<int:course_id>/invoices', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_course_invoices(course_id):
    """API: Get invoices linked to a course."""
    try:
        invoices = _repo.query_all('''
            SELECT i.id, i.invoice_number, i.invoice_date, i.invoice_value,
                   i.currency, i.supplier, i.status
            FROM hr.course_invoices ci
            JOIN invoices i ON ci.invoice_id = i.id
            WHERE ci.course_id = %s
            ORDER BY i.invoice_date DESC
        ''', (course_id,))
        return jsonify(invoices)
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/invoices', methods=['POST'])
@login_required
@courses_permission_required('edit')
def api_link_invoice(course_id):
    """API: Link an invoice to a course."""
    try:
        data = request.get_json()
        invoice_id = data.get('invoice_id')
        if not invoice_id:
            return jsonify({'success': False, 'error': 'invoice_id required'}), 400

        _repo.execute('''
            INSERT INTO hr.course_invoices (course_id, invoice_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        ''', (course_id, invoice_id))

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/invoices/<int:invoice_id>', methods=['DELETE'])
@login_required
@courses_permission_required('edit')
def api_unlink_invoice(course_id, invoice_id):
    """API: Unlink an invoice from a course."""
    try:
        _repo.execute('''
            DELETE FROM hr.course_invoices WHERE course_id = %s AND invoice_id = %s
        ''', (course_id, invoice_id))

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)
