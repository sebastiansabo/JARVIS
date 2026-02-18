"""JARVIS Core Settings Routes.

Platform settings management routes.
"""
from flask import jsonify, request
from flask_login import login_required, current_user

from . import settings_bp
from .themes.repositories import ThemeRepository
from .menus.repositories import MenuRepository
from .dropdowns.repositories import DropdownRepository
from core.utils.api_helpers import admin_required, error_response, safe_error_response

_theme_repo = ThemeRepository()
_menu_repo = MenuRepository()
_dropdown_repo = DropdownRepository()


# ============== THEME SETTINGS ENDPOINTS ==============

@settings_bp.route('/api/themes', methods=['GET'])
@login_required
def api_get_themes():
    """Get all themes."""
    themes = _theme_repo.get_all()
    return jsonify({'themes': themes})


@settings_bp.route('/api/themes/active', methods=['GET'])
def api_get_active_theme():
    """Get the active theme (public endpoint for CSS loading)."""
    theme = _theme_repo.get_active()
    return jsonify({'theme': theme})


@settings_bp.route('/api/themes/<int:theme_id>', methods=['GET'])
@login_required
def api_get_theme(theme_id):
    """Get a specific theme."""
    theme = _theme_repo.get_by_id(theme_id)
    if theme:
        return jsonify({'theme': theme})
    return error_response('Theme not found', 404)


@settings_bp.route('/api/themes', methods=['POST'])
@admin_required
def api_create_theme():
    """Create a new theme."""
    data = request.get_json()
    theme_name = data.get('theme_name', '').strip()
    settings = data.get('settings', {})
    is_active = data.get('is_active', False)

    if not theme_name:
        return error_response('Theme name is required')

    theme = _theme_repo.save(None, theme_name, settings, is_active)
    return jsonify({'success': True, 'theme': theme})


@settings_bp.route('/api/themes/<int:theme_id>', methods=['PUT'])
@admin_required
def api_update_theme(theme_id):
    """Update a theme."""
    data = request.get_json()
    theme_name = data.get('theme_name', '').strip()
    settings = data.get('settings', {})
    is_active = data.get('is_active')

    if not theme_name:
        return error_response('Theme name is required')

    theme = _theme_repo.save(theme_id, theme_name, settings, is_active)
    if theme:
        return jsonify({'success': True, 'theme': theme})
    return error_response('Theme not found', 404)


@settings_bp.route('/api/themes/<int:theme_id>', methods=['DELETE'])
@admin_required
def api_delete_theme(theme_id):
    """Delete a theme."""
    if _theme_repo.delete(theme_id):
        return jsonify({'success': True})
    return error_response('Cannot delete active or only theme')


@settings_bp.route('/api/themes/<int:theme_id>/activate', methods=['POST'])
@admin_required
def api_activate_theme(theme_id):
    """Activate a theme."""
    if _theme_repo.activate(theme_id):
        return jsonify({'success': True})
    return error_response('Failed to activate theme', 500)


# ============== MODULE MENU ENDPOINTS ==============

@settings_bp.route('/api/module-menu', methods=['GET'])
@login_required
def api_get_module_menu():
    """Get module menu items filtered by user permissions."""
    items = _menu_repo.get_items(include_hidden=False)

    # Filter modules based on user permissions
    permission_map = {
        'accounting': lambda u: u.can_access_accounting or u.can_view_invoices or u.can_add_invoices,
        'hr': lambda u: u.can_access_hr,
        'settings': lambda u: u.can_access_settings,
    }

    def user_can_access_module(module_key):
        check = permission_map.get(module_key)
        if check:
            return check(current_user)
        return True

    filtered_items = []
    for item in items:
        if item.get('status') == 'coming_soon':
            filtered_items.append(item)
        elif user_can_access_module(item.get('module_key', '')):
            filtered_items.append(item)

    return jsonify({'items': filtered_items})


@settings_bp.route('/api/module-menu/all', methods=['GET'])
@login_required
def api_get_all_module_menu():
    """Get all module menu items including hidden (admin endpoint)."""
    items = _menu_repo.get_all_flat()
    return jsonify({'items': items})


@settings_bp.route('/api/module-menu/<int:item_id>', methods=['GET'])
@login_required
def api_get_module_menu_item(item_id):
    """Get a specific module menu item."""
    item = _menu_repo.get_by_id(item_id)
    if item:
        return jsonify({'item': item})
    return error_response('Item not found', 404)


@settings_bp.route('/api/module-menu', methods=['POST'])
@admin_required
def api_create_module_menu_item():
    """Create a new module menu item."""
    data = request.get_json()

    if not data.get('name') or not data.get('module_key'):
        return error_response('Name and module_key are required')

    item = _menu_repo.save(None, data)
    return jsonify({'success': True, 'item': item})


@settings_bp.route('/api/module-menu/<int:item_id>', methods=['PUT'])
@admin_required
def api_update_module_menu_item(item_id):
    """Update a module menu item."""
    data = request.get_json()

    if not data.get('name') or not data.get('module_key'):
        return error_response('Name and module_key are required')

    item = _menu_repo.save(item_id, data)
    if item:
        return jsonify({'success': True, 'item': item})
    return error_response('Item not found', 404)


@settings_bp.route('/api/module-menu/<int:item_id>', methods=['DELETE'])
@admin_required
def api_delete_module_menu_item(item_id):
    """Delete a module menu item."""
    if _menu_repo.delete(item_id):
        return jsonify({'success': True})
    return error_response('Failed to delete item')


@settings_bp.route('/api/module-menu/reorder', methods=['POST'])
@admin_required
def api_reorder_module_menu():
    """Reorder module menu items."""
    data = request.get_json()
    items = data.get('items', [])

    if not items:
        return error_response('Items array is required')

    if _menu_repo.update_order(items):
        return jsonify({'success': True})
    return error_response('Failed to reorder items', 500)


# ============== VAT RATE ENDPOINTS ==============

@settings_bp.route('/api/vat-rates', methods=['GET'])
@login_required
def api_get_vat_rates():
    """Get all VAT rates."""
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    rates = _dropdown_repo.get_vat_rates(active_only=active_only)
    return jsonify(rates)


@settings_bp.route('/api/vat-rates', methods=['POST'])
@admin_required
def api_create_vat_rate():
    """Create a new VAT rate."""
    data = request.get_json()
    name = data.get('name', '').strip()
    rate = data.get('rate')

    if not name or rate is None:
        return error_response('Name and rate are required')

    try:
        rate_id = _dropdown_repo.add_vat_rate(
            name=name,
            rate=float(rate),
            is_default=data.get('is_default', False),
            is_active=data.get('is_active', True)
        )
        return jsonify({'success': True, 'id': rate_id})
    except Exception as e:
        return safe_error_response(e)


@settings_bp.route('/api/vat-rates/<int:rate_id>', methods=['PUT'])
@admin_required
def api_update_vat_rate(rate_id):
    """Update a VAT rate."""
    data = request.get_json()
    try:
        updated = _dropdown_repo.update_vat_rate(
            rate_id=rate_id,
            name=data.get('name'),
            rate=float(data['rate']) if data.get('rate') is not None else None,
            is_default=data.get('is_default'),
            is_active=data.get('is_active')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'VAT rate not found'}), 404
    except Exception as e:
        return safe_error_response(e)


@settings_bp.route('/api/vat-rates/<int:rate_id>', methods=['DELETE'])
@admin_required
def api_delete_vat_rate(rate_id):
    """Delete a VAT rate."""
    if _dropdown_repo.delete_vat_rate(rate_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'VAT rate not found'}), 404


# ============== DROPDOWN OPTIONS ENDPOINTS ==============

@settings_bp.route('/api/dropdown-options', methods=['GET'])
@login_required
def api_get_dropdown_options():
    """Get dropdown options, optionally filtered by type."""
    dropdown_type = request.args.get('type')
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    options = _dropdown_repo.get_options(dropdown_type, active_only)
    return jsonify(options)


@settings_bp.route('/api/dropdown-options', methods=['POST'])
@login_required
def api_add_dropdown_option():
    """Add a new dropdown option."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    try:
        option_id = _dropdown_repo.add_option(
            dropdown_type=data['dropdown_type'],
            value=data['value'],
            label=data['label'],
            color=data.get('color'),
            opacity=data.get('opacity', 0.7),
            sort_order=data.get('sort_order', 0),
            is_active=data.get('is_active', True),
            notify_on_status=data.get('notify_on_status', False)
        )
        return jsonify({'success': True, 'id': option_id})
    except Exception as e:
        return safe_error_response(e)


@settings_bp.route('/api/dropdown-options/<int:option_id>', methods=['PUT'])
@login_required
def api_update_dropdown_option(option_id):
    """Update a dropdown option."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    try:
        success = _dropdown_repo.update_option(
            option_id=option_id,
            value=data.get('value'),
            label=data.get('label'),
            color=data.get('color'),
            opacity=data.get('opacity'),
            sort_order=data.get('sort_order'),
            is_active=data.get('is_active'),
            notify_on_status=data.get('notify_on_status')
        )
        if success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Option not found'}), 404
    except Exception as e:
        return safe_error_response(e)


@settings_bp.route('/api/dropdown-options/<int:option_id>', methods=['DELETE'])
@login_required
def api_delete_dropdown_option(option_id):
    """Delete a dropdown option."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    if _dropdown_repo.delete_option(option_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Option not found'}), 404
