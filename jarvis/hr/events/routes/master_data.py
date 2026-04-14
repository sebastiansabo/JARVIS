from ._shared import *


# ============== Master Tables CRUD API ==============

# --- Brands Master Table ---

@events_bp.route('/api/master/brands', methods=['GET'])
@login_required
@hr_required
def api_get_master_brands():
    """API: Get all brands from master table."""
    brands = get_all_master_brands()
    return jsonify(brands)


@events_bp.route('/api/master/brands', methods=['POST'])
@login_required
@hr_permission_required('structure', 'edit')
@handle_api_errors
def api_create_master_brand():
    """API: Create a new brand in master table."""

    data = request.get_json()
    brand_id = create_master_brand(data['name'])
    clear_structure_cache()
    return jsonify({'success': True, 'id': brand_id})


@events_bp.route('/api/master/brands/<int:brand_id>', methods=['PUT'])
@login_required
@hr_permission_required('structure', 'edit')
def api_update_master_brand(brand_id):
    """API: Update a brand in master table."""

    data = request.get_json()
    update_master_brand(brand_id, data['name'], data.get('is_active', True))
    clear_structure_cache()
    return jsonify({'success': True})


@events_bp.route('/api/master/brands/<int:brand_id>', methods=['DELETE'])
@login_required
@hr_permission_required('structure', 'edit')
def api_delete_master_brand(brand_id):
    """API: Delete a brand from master table."""

    delete_master_brand(brand_id)
    clear_structure_cache()
    return jsonify({'success': True})


# --- Departments Master Table ---

@events_bp.route('/api/master/departments', methods=['GET'])
@login_required
@hr_required
def api_get_master_departments():
    """API: Get all departments from master table."""
    departments = get_all_master_departments()
    return jsonify(departments)


@events_bp.route('/api/master/departments', methods=['POST'])
@login_required
@hr_permission_required('structure', 'edit')
@handle_api_errors
def api_create_master_department():
    """API: Create a new department in master table."""

    data = request.get_json()
    dept_id = create_master_department(data['name'])
    clear_structure_cache()
    return jsonify({'success': True, 'id': dept_id})


@events_bp.route('/api/master/departments/<int:dept_id>', methods=['PUT'])
@login_required
@hr_permission_required('structure', 'edit')
def api_update_master_department(dept_id):
    """API: Update a department in master table."""

    data = request.get_json()
    update_master_department(dept_id, data['name'], data.get('is_active', True))
    clear_structure_cache()
    return jsonify({'success': True})


@events_bp.route('/api/master/departments/<int:dept_id>', methods=['DELETE'])
@login_required
@hr_permission_required('structure', 'edit')
def api_delete_master_department(dept_id):
    """API: Delete a department from master table."""

    delete_master_department(dept_id)
    clear_structure_cache()
    return jsonify({'success': True})


# --- Subdepartments Master Table ---

@events_bp.route('/api/master/subdepartments', methods=['GET'])
@login_required
@hr_required
def api_get_master_subdepartments():
    """API: Get all subdepartments from master table."""
    subdepartments = get_all_master_subdepartments()
    return jsonify(subdepartments)


@events_bp.route('/api/master/subdepartments', methods=['POST'])
@login_required
@hr_permission_required('structure', 'edit')
@handle_api_errors
def api_create_master_subdepartment():
    """API: Create a new subdepartment in master table."""

    data = request.get_json()
    subdept_id = create_master_subdepartment(data['name'])
    clear_structure_cache()
    return jsonify({'success': True, 'id': subdept_id})


@events_bp.route('/api/master/subdepartments/<int:subdept_id>', methods=['PUT'])
@login_required
@hr_permission_required('structure', 'edit')
def api_update_master_subdepartment(subdept_id):
    """API: Update a subdepartment in master table."""

    data = request.get_json()
    update_master_subdepartment(subdept_id, data['name'], data.get('is_active', True))
    clear_structure_cache()
    return jsonify({'success': True})


@events_bp.route('/api/master/subdepartments/<int:subdept_id>', methods=['DELETE'])
@login_required
@hr_permission_required('structure', 'edit')
def api_delete_master_subdepartment(subdept_id):
    """API: Delete a subdepartment from master table."""

    delete_master_subdepartment(subdept_id)
    clear_structure_cache()
    return jsonify({'success': True})
