"""HR Course enrollment cost, dashboard, and activity routes."""
from ._shared import *  # noqa: F401, F403
from ..repositories import (
    EnrollmentCostRepository, CourseActivityRepository,
    CourseRepository, EnrollmentRepository,
)

_cost_repo = EnrollmentCostRepository()
_activity_repo = CourseActivityRepository()
_course_repo = CourseRepository()
_enroll_repo = EnrollmentRepository()


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
