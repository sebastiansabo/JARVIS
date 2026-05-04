"""HR Course Certification routes."""
from ._shared import *  # noqa: F401, F403
from ..repositories import CertificationRepository

_cert_repo = CertificationRepository()


@courses_bp.route('/api/certifications', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_certifications():
    """API: Get certifications. Filter by employee_id or get expiring ones."""
    try:
        employee_id = request.args.get('employee_id', type=int)

        if employee_id:
            certs = _cert_repo.get_by_employee(employee_id)
        else:
            days = request.args.get('days_ahead', 90, type=int)
            certs = _cert_repo.get_expiring(days)

        return jsonify(certs)
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/certifications/expiring', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_expiring_certifications():
    """API: Get certifications expiring within N days."""
    try:
        days = request.args.get('days', 30, type=int)
        certs = _cert_repo.get_expiring(days)
        return jsonify(certs)
    except Exception as e:
        return safe_error_response(e)
