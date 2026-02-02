"""JARVIS Core Auth Models.

User model for Flask-Login authentication.
"""
from flask_login import UserMixin


class User(UserMixin):
    """User class for Flask-Login."""

    def __init__(self, user_data):
        self.id = user_data['id']
        self.email = user_data['email']
        self.name = user_data['name']
        self.phone = user_data.get('phone')
        self.role_id = user_data.get('role_id')
        self.role_name = user_data.get('role_name')
        self.is_active_user = user_data.get('is_active', True)

        # Organizational fields (from responsables migration)
        self.company = user_data.get('company')
        self.brand = user_data.get('brand')
        self.department = user_data.get('department')
        self.subdepartment = user_data.get('subdepartment')
        self.org_unit_id = user_data.get('org_unit_id')
        self.notify_on_allocation = user_data.get('notify_on_allocation', True)

        # Role permissions (backward compatible boolean properties)
        self.can_add_invoices = user_data.get('can_add_invoices', False)
        self.can_edit_invoices = user_data.get('can_edit_invoices', False)
        self.can_delete_invoices = user_data.get('can_delete_invoices', False)
        self.can_view_invoices = user_data.get('can_view_invoices', False)
        self.can_access_accounting = user_data.get('can_access_accounting', False)
        self.can_access_settings = user_data.get('can_access_settings', False)
        self.can_access_connectors = user_data.get('can_access_connectors', False)
        self.can_access_templates = user_data.get('can_access_templates', False)
        self.can_access_hr = user_data.get('can_access_hr', False)
        self.is_hr_manager = user_data.get('is_hr_manager', False)

        # Permission mapping for has_permission method
        self._permission_map = {
            'system.settings': self.can_access_settings,
            'invoices.view': self.can_view_invoices,
            'invoices.add': self.can_add_invoices,
            'invoices.edit': self.can_edit_invoices,
            'invoices.delete': self.can_delete_invoices,
            'accounting.dashboard': self.can_access_accounting,
            'accounting.templates': self.can_access_templates,
            'accounting.connectors': self.can_access_connectors,
            'hr.access': self.can_access_hr,
            'hr.manager': self.is_hr_manager,
        }

    @property
    def is_active(self):
        return self.is_active_user

    def has_permission(self, module: str, permission: str = None) -> bool:
        """
        Check if user has a specific permission.
        Usage:
            user.has_permission('invoices', 'add')  # Check invoices.add
            user.has_permission('invoices.add')     # Also works
        """
        if permission is None and '.' in module:
            # Allow 'module.permission' format
            module, permission = module.split('.', 1)

        perm_key = f"{module}.{permission}"
        return self._permission_map.get(perm_key, False)
