"""Organization module API routes.

Company management, department structure, and organizational lookups.
"""
from flask import jsonify, request
from flask_login import login_required

from . import org_bp
from .repositories import CompanyRepository, StructureRepository
from core.utils.api_helpers import safe_error_response

_company_repo = CompanyRepository()
_structure_repo = StructureRepository()


# ============== ORGANIZATIONAL LOOKUPS ==============

@org_bp.route('/api/companies')
@login_required
def api_companies():
    """Get list of companies."""
    from models import get_companies
    return jsonify(get_companies())


@org_bp.route('/api/brands/<company>')
@login_required
def api_brands(company):
    """Get brands for a company."""
    from models import get_brands_for_company
    return jsonify(get_brands_for_company(company))


@org_bp.route('/api/departments/<company>')
@login_required
def api_departments(company):
    """Get departments for a company."""
    from models import get_departments_for_company
    return jsonify(get_departments_for_company(company))


@org_bp.route('/api/subdepartments/<company>/<department>')
@login_required
def api_subdepartments(company, department):
    """Get subdepartments for a company and department."""
    from models import get_subdepartments
    return jsonify(get_subdepartments(company, department))


@org_bp.route('/api/company-for-department/<department>')
@login_required
def api_company_for_department(department):
    """Look up which company a department belongs to."""
    from models import get_company_for_department
    company = get_company_for_department(department)
    return jsonify({'company': company})


@org_bp.route('/api/manager')
@login_required
def api_manager():
    """Get manager for a department, optionally filtered by brand."""
    from models import get_manager
    company = request.args.get('company')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')
    return jsonify({'manager': get_manager(company, department, subdepartment, brand)})


# ============== COMPANY VAT MANAGEMENT ==============

@org_bp.route('/api/companies-vat')
@login_required
def api_companies_vat():
    """Get all companies with their VAT numbers."""
    return jsonify(_company_repo.get_all_with_vat_and_brands())


@org_bp.route('/api/companies-vat', methods=['POST'])
@login_required
def api_add_company_vat():
    """Add a new company with VAT."""
    data = request.get_json()
    company = data.get('company', '').strip()
    vat = data.get('vat', '').strip()

    if not company or not vat:
        return jsonify({'success': False, 'error': 'Company and VAT are required'}), 400

    try:
        _company_repo.add_with_vat(company, vat)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@org_bp.route('/api/companies-vat/<company>', methods=['PUT'])
@login_required
def api_update_company_vat(company):
    """Update company VAT."""
    data = request.get_json()
    vat = data.get('vat', '').strip()

    if not vat:
        return jsonify({'success': False, 'error': 'VAT is required'}), 400

    if _company_repo.update_vat(company, vat):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Company not found'}), 404


@org_bp.route('/api/companies-vat/<company>', methods=['DELETE'])
@login_required
def api_delete_company_vat(company):
    """Delete a company."""
    if _company_repo.delete_by_name(company):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Company not found'}), 404


@org_bp.route('/api/match-vat/<vat>')
@login_required
def api_match_vat(vat):
    """Match a VAT number to a company."""
    company = _company_repo.match_by_vat(vat)
    if company:
        return jsonify({'success': True, 'company': company})
    return jsonify({'success': False, 'company': None})


# ============== COMPANIES CONFIGURATION ==============

@org_bp.route('/api/companies-config', methods=['GET'])
@login_required
def api_get_companies_config():
    """Get all companies for configuration."""
    return jsonify(_company_repo.get_all())


@org_bp.route('/api/companies-config', methods=['POST'])
@login_required
def api_create_company_config():
    """Create a new company."""
    data = request.get_json()
    if not data or not data.get('company'):
        return jsonify({'success': False, 'error': 'Company name is required'}), 400

    try:
        company_id = _company_repo.save(
            company=data.get('company'),
            vat=data.get('vat')
        )
        return jsonify({'success': True, 'id': company_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@org_bp.route('/api/companies-config/<int:company_id>', methods=['GET'])
@login_required
def api_get_company_config(company_id):
    """Get a specific company."""
    company = _company_repo.get(company_id)
    if not company:
        return jsonify({'success': False, 'error': 'Company not found'}), 404
    return jsonify(company)


@org_bp.route('/api/companies-config/<int:company_id>', methods=['PUT'])
@login_required
def api_update_company_config(company_id):
    """Update a company."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    try:
        success = _company_repo.update(
            company_id=company_id,
            company=data.get('company'),
            vat=data.get('vat')
        )
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Company not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@org_bp.route('/api/companies-config/<int:company_id>', methods=['DELETE'])
@login_required
def api_delete_company_config(company_id):
    """Delete a company."""
    if _company_repo.delete(company_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Company not found'}), 404


# ============== DEPARTMENT STRUCTURE ==============

@org_bp.route('/api/department-structures', methods=['GET'])
@login_required
def api_get_department_structures():
    """Get all department structures."""
    return jsonify(_structure_repo.get_all())


@org_bp.route('/api/department-structures', methods=['POST'])
@login_required
def api_create_department_structure():
    """Create a new department structure."""
    data = request.get_json()
    if not data or not data.get('company') or not data.get('department'):
        return jsonify({'success': False, 'error': 'Company and department are required'}), 400

    structure_id = _structure_repo.save(
        company=data.get('company'),
        department=data.get('department'),
        brand=data.get('brand'),
        subdepartment=data.get('subdepartment'),
        manager=data.get('manager'),
        marketing=data.get('marketing'),
        responsable_id=data.get('responsable_id'),
        manager_ids=data.get('manager_ids'),
        marketing_ids=data.get('marketing_ids'),
        cc_email=data.get('cc_email')
    )
    return jsonify({'success': True, 'id': structure_id})


@org_bp.route('/api/department-structures/<int:structure_id>', methods=['GET'])
@login_required
def api_get_department_structure(structure_id):
    """Get a specific department structure."""
    structure = _structure_repo.get(structure_id)
    if not structure:
        return jsonify({'success': False, 'error': 'Department structure not found'}), 404
    return jsonify(structure)


@org_bp.route('/api/department-structures/<int:structure_id>', methods=['PUT'])
@login_required
def api_update_department_structure(structure_id):
    """Update a department structure."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    success = _structure_repo.update(
        structure_id=structure_id,
        company=data.get('company'),
        department=data.get('department'),
        brand=data.get('brand'),
        subdepartment=data.get('subdepartment'),
        manager=data.get('manager'),
        marketing=data.get('marketing'),
        responsable_id=data.get('responsable_id'),
        manager_ids=data.get('manager_ids'),
        marketing_ids=data.get('marketing_ids'),
        cc_email=data.get('cc_email')
    )
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Department structure not found'}), 404


@org_bp.route('/api/department-structures/<int:structure_id>', methods=['DELETE'])
@login_required
def api_delete_department_structure(structure_id):
    """Delete a department structure."""
    if _structure_repo.delete(structure_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Department structure not found'}), 404


@org_bp.route('/api/department-structures/unique-departments', methods=['GET'])
@login_required
def api_get_unique_departments():
    """Get unique departments, optionally filtered by company."""
    company = request.args.get('company', '') or None
    return jsonify(_structure_repo.get_unique_departments(company))


@org_bp.route('/api/department-structures/unique-brands', methods=['GET'])
@login_required
def api_get_unique_brands():
    """Get unique brands, optionally filtered by company."""
    company = request.args.get('company', '') or None
    return jsonify(_structure_repo.get_unique_brands(company))
