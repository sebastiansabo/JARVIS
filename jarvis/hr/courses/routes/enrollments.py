"""HR Course Enrollment routes."""
from datetime import date as date_cls
from ._shared import *  # noqa: F401, F403
from ..repositories import EnrollmentRepository, CertificationRepository, CourseActivityRepository

VALID_ENROLLMENT_STATUSES = {'enrolled', 'attended', 'completed', 'failed', 'cancelled'}

_enroll_repo = EnrollmentRepository()
_cert_repo = CertificationRepository()
_activity = CourseActivityRepository()


def _verify_enrollment(enrollment_id, course_id):
    """Fetch enrollment and verify it belongs to the given course."""
    enrollment = _enroll_repo.get_by_id(enrollment_id)
    if not enrollment or enrollment['course_id'] != course_id:
        return None
    return enrollment


@courses_bp.route('/api/courses/<int:course_id>/enrollments', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_enrollments(course_id):
    """API: Get enrollments for a course."""
    try:
        enrollments = _enroll_repo.get_by_course(course_id)
        return jsonify(enrollments)
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/enrollments', methods=['POST'])
@login_required
@courses_permission_required('edit')
def api_add_enrollments(course_id):
    """API: Add employees to a course."""
    try:
        data = request.get_json()
        employee_ids = data.get('employee_ids', [])

        if not employee_ids:
            return jsonify({'success': False, 'error': 'No employees provided'}), 400

        count = _enroll_repo.create_bulk(course_id, employee_ids)
        _activity.log(course_id, 'enrollment_added', current_user.id, current_user.name,
                       {'count': count, 'employee_ids': employee_ids})
        return jsonify({'success': True, 'enrolled': count})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/enrollments/<int:enrollment_id>', methods=['PUT'])
@login_required
@courses_permission_required('edit')
def api_update_enrollment(course_id, enrollment_id):
    """API: Update enrollment status."""
    try:
        enrollment = _verify_enrollment(enrollment_id, course_id)
        if not enrollment:
            return jsonify({'success': False, 'error': 'Enrollment not found for this course'}), 404

        data = request.get_json()
        status = data.get('enrollment_status')
        if not status:
            return jsonify({'success': False, 'error': 'enrollment_status required'}), 400
        if status not in VALID_ENROLLMENT_STATUSES:
            return jsonify({'success': False, 'error': f'Invalid enrollment status: {status}'}), 400

        _enroll_repo.update_status(enrollment_id, status)
        _activity.log(course_id, 'enrollment_status_changed', current_user.id, current_user.name,
                       {'enrollment_id': enrollment_id, 'status': status,
                        'employee_name': enrollment.get('employee_name')})
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/enrollments/<int:enrollment_id>/complete', methods=['POST'])
@login_required
@courses_permission_required('edit')
def api_complete_enrollment(course_id, enrollment_id):
    """API: Mark enrollment as completed and auto-create certification if applicable."""
    try:
        enrollment = _verify_enrollment(enrollment_id, course_id)
        if not enrollment:
            return jsonify({'success': False, 'error': 'Enrollment not found for this course'}), 404

        today = date_cls.today()

        # Update enrollment status
        _enroll_repo.update_status(enrollment_id, 'completed', completed_at=today.isoformat())

        # Auto-create certification if course type requires it
        cert_id = None
        if enrollment.get('requires_certification'):
            validity = enrollment.get('default_validity_months')
            expiry = None
            if validity:
                from dateutil.relativedelta import relativedelta
                expiry = (today + relativedelta(months=validity)).isoformat()

            cert_id = _cert_repo.create(
                enrollment_id=enrollment_id,
                employee_id=enrollment['employee_id'],
                course_type_id=enrollment['course_type_id'],
                issued_date=today.isoformat(),
                expiry_date=expiry,
            )

        _activity.log(course_id, 'enrollment_completed', current_user.id, current_user.name,
                       {'enrollment_id': enrollment_id, 'employee_name': enrollment.get('employee_name'),
                        'certification_id': cert_id})
        return jsonify({'success': True, 'certification_id': cert_id})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/enrollments/<int:enrollment_id>', methods=['DELETE'])
@login_required
@courses_permission_required('edit')
def api_delete_enrollment(course_id, enrollment_id):
    """API: Remove an enrollment."""
    try:
        enrollment = _verify_enrollment(enrollment_id, course_id)
        if not enrollment:
            return jsonify({'success': False, 'error': 'Enrollment not found for this course'}), 404

        _enroll_repo.delete(enrollment_id)
        _activity.log(course_id, 'enrollment_removed', current_user.id, current_user.name,
                       {'enrollment_id': enrollment_id, 'employee_name': enrollment.get('employee_name')})
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)
