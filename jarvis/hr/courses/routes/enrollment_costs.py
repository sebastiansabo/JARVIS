"""HR Course enrollment cost, dashboard, and activity routes."""
from ._shared import *  # noqa: F401, F403
from ..repositories import (
    EnrollmentCostRepository, CourseActivityRepository,
    CourseRepository, EnrollmentRepository, CourseTransactionRepository,
)

_cost_repo = EnrollmentCostRepository()
_activity_repo = CourseActivityRepository()
_course_repo = CourseRepository()
_enroll_repo = EnrollmentRepository()
_tx_repo = CourseTransactionRepository()


# ── Enrollment Costs ──────────────────────────────────────────────

@courses_bp.route('/api/courses/<int:course_id>/enrollment-costs', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_enrollment_costs(course_id):
    """Get all enrollment costs for a course with employee info."""
    try:
        costs = _cost_repo.get_by_course(course_id)
        summary = _cost_repo.get_cost_summary_by_course(course_id)
        return jsonify({'costs': costs, 'summary': summary})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/enrollments/<int:enrollment_id>/costs', methods=['PUT'])
@login_required
@courses_permission_required('edit')
def api_upsert_enrollment_cost(course_id, enrollment_id):
    """Upsert cost breakdown for an enrollment."""
    try:
        # Verify enrollment belongs to course
        enrollment = _enroll_repo.get_by_id(enrollment_id)
        if not enrollment or enrollment['course_id'] != course_id:
            return jsonify({'success': False, 'error': 'Enrollment not found for this course'}), 404

        data = request.get_json()
        cost_id = _cost_repo.upsert(
            enrollment_id=enrollment_id,
            training_fee=data.get('training_fee', 0),
            per_diem=data.get('per_diem', 0),
            accommodation=data.get('accommodation', 0),
            transport=data.get('transport', 0),
            taxi=data.get('taxi', 0),
            currency=data.get('currency', 'RON'),
            notes=data.get('notes'),
        )

        # Log activity
        _activity_repo.log(
            course_id=course_id,
            action='costs_updated',
            actor_id=current_user.id,
            actor_name=current_user.name,
            details={
                'enrollment_id': enrollment_id,
                'employee_name': enrollment.get('employee_name'),
            },
        )

        return jsonify({'success': True, 'id': cost_id})
    except Exception as e:
        return safe_error_response(e)


# ── Enrollment Fields (admin fields: order_number, travel_order, etc.) ──

@courses_bp.route('/api/courses/<int:course_id>/enrollments/<int:enrollment_id>/fields', methods=['PUT'])
@login_required
@courses_permission_required('edit')
def api_update_enrollment_fields(course_id, enrollment_id):
    """Update administrative fields on an enrollment."""
    try:
        enrollment = _enroll_repo.get_by_id(enrollment_id)
        if not enrollment or enrollment['course_id'] != course_id:
            return jsonify({'success': False, 'error': 'Enrollment not found for this course'}), 404

        data = request.get_json()
        _enroll_repo.update_fields(enrollment_id, **data)

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


# ── Dashboard & Cost Summary ─────────────────────────────────────

@courses_bp.route('/api/courses/dashboard', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_courses_dashboard():
    """Dashboard stats for courses overview."""
    try:
        year = request.args.get('year', type=int)
        if not year:
            from datetime import date
            year = date.today().year
        company_id = request.args.get('company_id', type=int)

        stats = _course_repo.get_dashboard_stats(year, company_id)
        return jsonify(stats)
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/cost-summary', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_courses_cost_summary():
    """Cost summary by company, optionally drilled into departments."""
    try:
        year = request.args.get('year', type=int)
        if not year:
            from datetime import date
            year = date.today().year
        month = request.args.get('month', type=int)
        company_id = request.args.get('company_id', type=int)

        if company_id:
            # Drill into departments for a specific company
            data = _cost_repo.get_cost_summary_by_department(company_id, year, month)
        else:
            # Top-level: by company
            data = _cost_repo.get_cost_summary_by_company(year, month)

        return jsonify(data)
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/cost-by-month', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_courses_cost_by_month():
    """Monthly cost breakdown for chart display."""
    try:
        year = request.args.get('year', type=int)
        if not year:
            from datetime import date
            year = date.today().year
        company_id = request.args.get('company_id', type=int)

        data = _cost_repo.get_cost_by_month(year, company_id)
        return jsonify(data)
    except Exception as e:
        return safe_error_response(e)


# ── Activity Log ─────────────────────────────────────────────────

# ── Transactions (manual spend + invoice-linked) ────────────────

@courses_bp.route('/api/courses/<int:course_id>/transactions', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_course_transactions(course_id):
    """Get all transactions for a course."""
    try:
        transactions = _tx_repo.get_by_course(course_id)
        totals = _tx_repo.get_totals(course_id)
        return jsonify({'transactions': transactions, 'totals': totals})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/transactions', methods=['POST'])
@login_required
@courses_permission_required('edit')
def api_create_course_transaction(course_id):
    """Create a manual spending entry or invoice-linked transaction."""
    try:
        data = request.get_json()
        invoice_id = data.get('invoice_id')

        # Prevent duplicate invoice links
        if invoice_id and _tx_repo.find_by_invoice(course_id, invoice_id):
            return jsonify({'success': False, 'error': 'Invoice already linked'}), 409

        tx = _tx_repo.create(
            course_id=course_id,
            amount=data['amount'],
            direction=data.get('direction', 'debit'),
            source=data.get('source', 'manual'),
            invoice_id=invoice_id,
            transaction_date=data.get('transaction_date'),
            description=data.get('description'),
            recorded_by=current_user.id,
            recorded_by_name=current_user.name,
        )

        action = 'invoice_linked' if invoice_id else 'spend_recorded'
        _activity_repo.log(
            course_id=course_id,
            action=action,
            actor_id=current_user.id,
            actor_name=current_user.name,
            details={
                'amount': float(data['amount']),
                'direction': data.get('direction', 'debit'),
                'description': data.get('description'),
            },
        )

        return jsonify({'success': True, 'id': tx['id'] if tx else None})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/transactions/<int:tx_id>', methods=['PUT'])
@login_required
@courses_permission_required('edit')
def api_update_course_transaction(course_id, tx_id):
    """Update a manual transaction."""
    try:
        data = request.get_json()
        tx = _tx_repo.update(
            tx_id,
            amount=data.get('amount'),
            transaction_date=data.get('transaction_date'),
            description=data.get('description'),
        )
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/transactions/<int:tx_id>', methods=['DELETE'])
@login_required
@courses_permission_required('edit')
def api_delete_course_transaction(course_id, tx_id):
    """Delete a transaction."""
    try:
        _tx_repo.delete(tx_id)

        _activity_repo.log(
            course_id=course_id,
            action='transaction_deleted',
            actor_id=current_user.id,
            actor_name=current_user.name,
        )

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/activity', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_course_activity(course_id):
    """Get activity log for a course."""
    try:
        limit = request.args.get('limit', 50, type=int)
        activity = _activity_repo.get_by_course(course_id, limit)
        return jsonify(activity)
    except Exception as e:
        return safe_error_response(e)
