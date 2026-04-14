from ._shared import *


# ============== Structure Data Routes ==============

@events_bp.route('/api/structure/companies', methods=['GET'])
@login_required
@hr_required
def api_get_companies():
    """API: Get all companies."""
    companies = get_companies()
    return jsonify(companies)


@events_bp.route('/api/structure/brands/<company>', methods=['GET'])
@login_required
@hr_required
def api_get_brands(company):
    """API: Get brands for a company."""
    brands = get_brands_for_company(company)
    return jsonify(brands)


@events_bp.route('/api/structure/departments/<company>', methods=['GET'])
@login_required
@hr_required
def api_get_departments(company):
    """API: Get departments for a company."""
    departments = get_departments_for_company(company)
    return jsonify(departments)


# ============== Companies CRUD API ==============

@events_bp.route('/api/structure/companies-full', methods=['GET'])
@login_required
@hr_required
def api_get_companies_full():
    """API: Get all companies with full details including brands from company_brands."""
    companies = get_all_companies_with_brands()
    # Format for API response
    for company in companies:
        if company.get('created_at'):
            company['created_at'] = company['created_at'].isoformat() if hasattr(company['created_at'], 'isoformat') else company['created_at']
        brand_list = company.get('brands', [])
        company['brands'] = ', '.join(brand_list) if isinstance(brand_list, list) else brand_list
        company['brands_list'] = [{'brand': b} for b in (brand_list if isinstance(brand_list, list) else [])]
    return jsonify(companies)


@events_bp.route('/api/structure/companies', methods=['POST'])
@login_required
@hr_permission_required('structure', 'edit')
def api_create_company():
    """API: Create a new company."""
    data = request.get_json()
    company_id = create_company(data['company'], data.get('vat'), data.get('parent_company_id'))
    return jsonify({'success': True, 'id': company_id})


@events_bp.route('/api/structure/companies/<int:company_id>', methods=['PUT'])
@login_required
@hr_permission_required('structure', 'edit')
def api_update_company(company_id):
    """API: Update a company."""
    data = request.get_json()
    try:
        update_company(company_id, data['company'], data.get('vat'), data.get('parent_company_id'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True})


@events_bp.route('/api/structure/companies/<int:company_id>', methods=['DELETE'])
@login_required
@hr_permission_required('structure', 'edit')
def api_delete_company(company_id):
    """API: Delete a company."""
    delete_company(company_id)
    return jsonify({'success': True})


# ============== Company Brands CRUD API ==============

@events_bp.route('/api/structure/company-brands', methods=['GET'])
@login_required
@hr_required
def api_get_company_brands():
    """API: Get all company brands."""
    company_id = request.args.get('company_id', type=int)
    brands = get_all_company_brands(company_id)
    return jsonify(brands)


@events_bp.route('/api/structure/company-brands', methods=['POST'])
@login_required
@hr_permission_required('structure', 'edit')
@handle_api_errors
def api_create_company_brand():
    """API: Create a new company brand."""

    data = request.get_json()
    brand_id = create_company_brand(data['company_id'], data['brand'])
    clear_structure_cache()
    return jsonify({'success': True, 'id': brand_id})


@events_bp.route('/api/structure/company-brands/<int:brand_id>', methods=['PUT'])
@login_required
@hr_permission_required('structure', 'edit')
def api_update_company_brand(brand_id):
    """API: Update a company brand."""

    data = request.get_json()
    update_company_brand(brand_id, data.get('company_id'), data['brand'], data.get('is_active', True))
    clear_structure_cache()
    return jsonify({'success': True})


@events_bp.route('/api/structure/company-brands/<int:brand_id>', methods=['DELETE'])
@login_required
@hr_permission_required('structure', 'edit')
def api_delete_company_brand(brand_id):
    """API: Delete a company brand."""

    delete_company_brand(brand_id)
    clear_structure_cache()
    return jsonify({'success': True})


@events_bp.route('/api/structure/companies/<int:company_id>/brands', methods=['GET'])
@login_required
@hr_required
def api_get_brands_for_company(company_id):
    """API: Get brands for a specific company."""
    brands = get_all_company_brands(company_id)
    return jsonify(brands)


# ============== Departments CRUD API ==============

@events_bp.route('/api/structure/departments-full', methods=['GET'])
@login_required
@hr_required
def api_get_departments_full():
    """API: Get all department structure entries with full details via JOINs."""
    structures = get_all_department_structures()
    return jsonify(structures)


@events_bp.route('/api/structure/departments', methods=['POST'])
@login_required
@hr_permission_required('structure', 'edit')
def api_create_department():
    """API: Create a new department structure entry."""


    data = request.get_json()

    # Look up the text values from master tables (if IDs provided)
    company_name = get_name_by_id('companies', data.get('company_id')) or data.get('company', '')
    brand_name = get_name_by_id('brands', data.get('brand_id')) or data.get('brand', '')
    dept_name = get_name_by_id('departments', data.get('department_id')) or data.get('department', '')
    subdept_name = get_name_by_id('subdepartments', data.get('subdepartment_id')) or data.get('subdepartment', '')

    dept_id = create_department_structure(
        data.get('company_id'),
        data.get('manager', ''),
        company_name, brand_name, dept_name, subdept_name,
        data.get('manager_ids'),
        data.get('cc_email')
    )
    clear_structure_cache()
    return jsonify({'success': True, 'id': dept_id})


@events_bp.route('/api/structure/departments/<int:dept_id>', methods=['PUT'])
@login_required
@hr_permission_required('structure', 'edit')
def api_update_department(dept_id):
    """API: Update a department structure entry."""


    data = request.get_json()

    # Look up the text values from master tables (if IDs provided)
    company_name = get_name_by_id('companies', data.get('company_id')) or data.get('company', '')
    brand_name = get_name_by_id('brands', data.get('brand_id')) or data.get('brand', '')
    dept_name = get_name_by_id('departments', data.get('department_id')) or data.get('department', '')
    subdept_name = get_name_by_id('subdepartments', data.get('subdepartment_id')) or data.get('subdepartment', '')

    update_department_structure(
        dept_id, data.get('company_id'),
        data.get('manager', ''),
        company_name, brand_name, dept_name, subdept_name,
        data.get('manager_ids'),
        data.get('cc_email')
    )
    clear_structure_cache()
    return jsonify({'success': True})


@events_bp.route('/api/structure/departments/<int:dept_id>', methods=['DELETE'])
@login_required
@hr_permission_required('structure', 'edit')
def api_delete_department(dept_id):
    """API: Delete a department."""
    delete_department_structure(dept_id)
    return jsonify({'success': True})
