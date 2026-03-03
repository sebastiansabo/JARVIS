"""Organization module API routes.

Company management, department structure, and organizational lookups.
"""
from flask import jsonify, request
from flask_login import login_required

from . import org_bp
from .repositories import CompanyRepository, StructureRepository, StructureNodeRepository
from core.utils.api_helpers import safe_error_response

_company_repo = CompanyRepository()
_structure_repo = StructureRepository()
_node_repo = StructureNodeRepository()


# ============== ORGANIZATIONAL LOOKUPS ==============

@org_bp.route('/api/companies')
@login_required
def api_companies():
    """Get list of companies. Tries structure_nodes first, falls back to legacy."""
    result = _node_repo.get_company_names()
    if result:
        return jsonify(result)
    from models import get_companies
    return jsonify(get_companies())


@org_bp.route('/api/brands/<company>')
@login_required
def api_brands(company):
    """Get brands (L1 nodes) for a company."""
    result = _node_repo.get_l1_names(company)
    if result:
        return jsonify(result)
    from models import get_brands_for_company
    return jsonify(get_brands_for_company(company))


@org_bp.route('/api/departments/<company>')
@login_required
def api_departments(company):
    """Get departments (L2 nodes) for a company."""
    result = _node_repo.get_l2_names(company)
    if result:
        return jsonify(result)
    from models import get_departments_for_company
    return jsonify(get_departments_for_company(company))


@org_bp.route('/api/subdepartments/<company>/<department>')
@login_required
def api_subdepartments(company, department):
    """Get subdepartments (L3 nodes) under a department."""
    result = _node_repo.get_l3_names(company, department)
    if result:
        return jsonify(result)
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
    """Get responsable for a structure node path (brand→department→subdepartment).

    Uses the new structure_nodes tree. Falls back to legacy department_structure
    if no match is found.
    """
    company = request.args.get('company')
    department = request.args.get('department')
    subdepartment = request.args.get('subdepartment')
    brand = request.args.get('brand')

    # Try new structure_nodes first
    if company:
        result = _node_repo.find_responsable_by_path(
            company, brand=brand, department=department, subdepartment=subdepartment
        )
        if result:
            return jsonify({'manager': result})

    # Fallback to legacy department_structure
    from models import get_manager
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
    return jsonify(_company_repo.get_all_with_vat_and_brands())


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
            vat=data.get('vat'),
            parent_company_id=data.get('parent_company_id')
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
        parent_id = data.get('parent_company_id', 'UNSET')
        success = _company_repo.update(
            company_id=company_id,
            company=data.get('company'),
            vat=data.get('vat'),
            parent_company_id=parent_id
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


# ============== BRANDS ==============

@org_bp.route('/api/brands-all', methods=['GET'])
@login_required
def api_get_all_brands():
    """Get all brands."""
    return jsonify(_company_repo.get_all_brands())


@org_bp.route('/api/brands-all', methods=['POST'])
@login_required
def api_create_brand():
    """Create a new brand."""
    data = request.get_json()
    name = (data or {}).get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Brand name is required'}), 400
    try:
        brand_id = _company_repo.create_brand(name)
        return jsonify({'success': True, 'id': brand_id})
    except Exception:
        return jsonify({'success': False, 'error': 'Brand already exists'}), 400


@org_bp.route('/api/companies-config/<int:company_id>/brands', methods=['POST'])
@login_required
def api_link_brand(company_id):
    """Link a brand to a company."""
    data = request.get_json()
    brand_id = (data or {}).get('brand_id')
    if not brand_id:
        return jsonify({'success': False, 'error': 'brand_id is required'}), 400
    link_id = _company_repo.link_brand(company_id, brand_id)
    return jsonify({'success': True, 'id': link_id})


@org_bp.route('/api/companies-config/<int:company_id>/brands/<int:brand_id>', methods=['DELETE'])
@login_required
def api_unlink_brand(company_id, brand_id):
    """Unlink a brand from a company."""
    if _company_repo.unlink_brand(company_id, brand_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Link not found'}), 404


@org_bp.route('/api/companies-config/<int:company_id>/responsables', methods=['GET'])
@login_required
def api_get_company_responsables(company_id):
    """Get responsable users for a company."""
    return jsonify(_company_repo.get_responsables(company_id))


@org_bp.route('/api/companies-config/<int:company_id>/responsables', methods=['PUT'])
@login_required
def api_set_company_responsables(company_id):
    """Set (replace) responsable users for a company."""
    data = request.get_json() or {}
    user_ids = data.get('user_ids', [])
    _company_repo.set_responsables(company_id, user_ids)
    return jsonify({'success': True})


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


# ============== STRUCTURE NODES (Generic Tree) ==============

@org_bp.route('/api/structure-nodes', methods=['GET'])
@login_required
def api_get_structure_nodes():
    """Get all structure nodes, optionally filtered by company_id."""
    company_id = request.args.get('company_id', type=int)
    if company_id:
        return jsonify(_node_repo.get_by_company(company_id))
    return jsonify(_node_repo.get_all())


@org_bp.route('/api/structure-nodes', methods=['POST'])
@login_required
def api_create_structure_node():
    """Create a new structure node."""
    data = request.get_json()
    if not data or not data.get('company_id') or not data.get('name', '').strip():
        return jsonify({'success': False, 'error': 'company_id and name are required'}), 400
    try:
        node_id = _node_repo.create(
            company_id=data['company_id'],
            name=data['name'].strip(),
            parent_id=data.get('parent_id'),
        )
        return jsonify({'success': True, 'id': node_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@org_bp.route('/api/structure-nodes/<int:node_id>', methods=['PUT'])
@login_required
def api_update_structure_node(node_id):
    """Update a structure node (name and/or has_team)."""
    data = request.get_json() or {}
    updated = False
    name = data.get('name', '').strip()
    if name:
        updated = _node_repo.update(node_id, name) or updated
    if 'has_team' in data:
        updated = _node_repo.update_has_team(node_id, bool(data['has_team'])) or updated
    if updated:
        return jsonify({'success': True})
    if not name and 'has_team' not in data:
        return jsonify({'success': False, 'error': 'name or has_team is required'}), 400
    return jsonify({'success': False, 'error': 'Node not found'}), 404


@org_bp.route('/api/structure-nodes/<int:node_id>', methods=['DELETE'])
@login_required
def api_delete_structure_node(node_id):
    """Delete a structure node and its children."""
    if _node_repo.delete(node_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Node not found'}), 404


# ============== STRUCTURE NODE MEMBERS ==============

@org_bp.route('/api/structure-nodes/members', methods=['GET'])
@login_required
def api_get_all_node_members():
    """Bulk fetch all members across all structure nodes."""
    return jsonify(_node_repo.get_all_members())


@org_bp.route('/api/structure-nodes/<int:node_id>/members', methods=['POST'])
@login_required
def api_add_node_member(node_id):
    """Add a member to a node."""
    data = request.get_json()
    user_id = (data or {}).get('user_id')
    role = (data or {}).get('role', 'team')
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id is required'}), 400
    try:
        member_id = _node_repo.add_member(node_id, user_id, role)
        return jsonify({'success': True, 'id': member_id})
    except Exception as e:
        return safe_error_response(e)


@org_bp.route('/api/structure-nodes/<int:node_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
def api_remove_node_member(node_id, user_id):
    """Remove a member from a node."""
    if _node_repo.remove_member(node_id, user_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Member not found'}), 404


@org_bp.route('/api/structure-nodes/<int:node_id>/members/set', methods=['POST'])
@login_required
def api_set_node_members(node_id):
    """Atomic replace: set all members of a given role for a node."""
    data = request.get_json()
    role = (data or {}).get('role')
    user_ids = (data or {}).get('user_ids', [])
    if not role or role not in ('responsable', 'team'):
        return jsonify({'success': False, 'error': 'role must be "responsable" or "team"'}), 400
    try:
        _node_repo.set_members(node_id, role, user_ids)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@org_bp.route('/api/structure-nodes/<int:node_id>/cascade-responsables', methods=['GET'])
@login_required
def api_get_cascade_responsables(node_id):
    """Get all responsable user IDs up the parent chain from this node."""
    return jsonify(_node_repo.get_cascade_responsable_ids(node_id))
