"""HR Course Types routes."""
from ._shared import *  # noqa: F401, F403
from ..repositories import CourseRepository

_repo = CourseRepository()


@courses_bp.route('/api/course-types', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_course_types():
    """API: Get all course types."""
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        types = _repo.get_all_types(active_only=active_only)
        return jsonify(types)
    except Exception as e:
        return safe_error_response(e)
