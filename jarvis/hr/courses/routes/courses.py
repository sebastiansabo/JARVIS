"""HR Courses CRUD routes."""
from ._shared import *  # noqa: F401, F403
from ..repositories import CourseRepository

_repo = CourseRepository()

VALID_COURSE_STATUSES = {'draft', 'pending_approval', 'approved', 'in_progress', 'completed', 'cancelled'}


@courses_bp.route('/api/courses', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_courses():
    """API: Get all courses with filters."""
    try:
        company_id = request.args.get('company_id', type=int)
        course_type_id = request.args.get('course_type_id', type=int)
        status = request.args.get('status')
        search = request.args.get('search')
        limit = request.args.get('limit', 200, type=int)
        offset = request.args.get('offset', 0, type=int)

        courses = _repo.get_all(
            company_id=company_id,
            course_type_id=course_type_id,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )
        total = _repo.get_count(
            company_id=company_id,
            course_type_id=course_type_id,
            status=status,
            search=search,
        )

        return jsonify({'courses': courses, 'total': total})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses', methods=['POST'])
@login_required
@courses_permission_required('add')
def api_create_course():
    """API: Create a new course."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        for field in ('name', 'course_type_id', 'start_date', 'end_date'):
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400

        if data['start_date'] > data['end_date']:
            return jsonify({'success': False, 'error': 'Start date must be before end date'}), 400

        course_id = _repo.create(
            name=data['name'],
            course_type_id=data['course_type_id'],
            company_id=data.get('company_id'),
            start_date=data['start_date'],
            end_date=data['end_date'],
            supplier_id=data.get('supplier_id'),
            trainer_name=data.get('trainer_name'),
            location=data.get('location'),
            description=data.get('description'),
            budget=data.get('budget'),
            currency=data.get('currency', 'RON'),
            created_by=current_user.id,
        )

        return jsonify({'success': True, 'id': course_id})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>', methods=['GET'])
@login_required
@courses_permission_required('view')
def api_get_course(course_id):
    """API: Get a single course."""
    try:
        course = _repo.get_by_id(course_id)
        if not course:
            return jsonify({'success': False, 'error': 'Course not found'}), 404
        return jsonify(course)
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>', methods=['PUT'])
@login_required
@courses_permission_required('edit')
def api_update_course(course_id):
    """API: Update a course."""
    try:
        data = request.get_json()

        # Prevent direct status changes via PUT — must use submit-approval
        status = data.get('status')
        if status:
            allowed_direct = {'cancelled', 'in_progress', 'completed'}
            if status not in allowed_direct:
                return jsonify({'success': False, 'error': f'Cannot set status to {status} directly'}), 400

        if data.get('start_date') and data.get('end_date') and data['start_date'] > data['end_date']:
            return jsonify({'success': False, 'error': 'Start date must be before end date'}), 400

        _repo.update(
            course_id,
            name=data.get('name'),
            course_type_id=data.get('course_type_id'),
            company_id=data.get('company_id'),
            supplier_id=data.get('supplier_id'),
            trainer_name=data.get('trainer_name'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            location=data.get('location'),
            description=data.get('description'),
            budget=data.get('budget'),
            currency=data.get('currency'),
            status=status,
        )

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>', methods=['DELETE'])
@login_required
@courses_permission_required('delete')
def api_delete_course(course_id):
    """API: Delete a course."""
    try:
        course = _repo.get_by_id(course_id)
        if not course:
            return jsonify({'success': False, 'error': 'Course not found'}), 404
        _repo.delete(course_id)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@courses_bp.route('/api/courses/<int:course_id>/submit-approval', methods=['POST'])
@login_required
@courses_permission_required('edit')
def api_submit_course_approval(course_id):
    """API: Submit a course for approval."""
    try:
        course = _repo.get_by_id(course_id)
        if not course:
            return jsonify({'success': False, 'error': 'Course not found'}), 404

        if course['status'] != 'draft':
            return jsonify({'success': False, 'error': 'Only draft courses can be submitted for approval'}), 400

        try:
            from core.approvals.engine import ApprovalEngine, NoMatchingFlowError
            engine = ApprovalEngine()
            approval = engine.submit(
                entity_type='hr_course',
                entity_id=course_id,
                context={
                    'course_name': course['name'],
                    'budget': float(course['budget']) if course.get('budget') else 0,
                    'company_id': course.get('company_id'),
                },
                requested_by=current_user.id,
            )
            new_status = 'approved' if approval.get('status') == 'approved' else 'pending_approval'
            _repo.update(course_id, status=new_status, approval_request_id=approval.get('id'))
            return jsonify({'success': True, 'status': new_status, 'approval': approval})
        except (ImportError, NameError):
            # No approval engine available — auto-approve
            _repo.update(course_id, status='approved')
            return jsonify({'success': True, 'status': 'approved', 'note': 'No approval flow configured'})
        except Exception:
            # NoMatchingFlowError or similar — auto-approve
            _repo.update(course_id, status='approved')
            return jsonify({'success': True, 'status': 'approved', 'note': 'No approval flow configured'})
    except Exception as e:
        return safe_error_response(e)
