"""
Settings Service - Business logic for admin/settings operations.

Provides a clean service layer API for users, roles, permissions,
companies, departments, and other platform settings.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from core.utils.logging_config import get_logger
from database import (
    # Users
    get_all_users,
    get_user,
    get_user_by_email,
    save_user,
    update_user,
    delete_user,
    authenticate_user,
    set_user_password,
    update_user_last_login,
    update_user_last_seen,
    get_online_users_count,
    set_default_password_for_users,
    # Roles & Permissions
    get_all_roles,
    get_role,
    save_role,
    update_role,
    delete_role,
    get_all_permissions,
    get_permissions_flat,
    get_role_permissions,
    get_role_permissions_list,
    set_role_permissions,
    # Companies & Structure
    get_all_companies,
    get_company,
    save_company,
    update_company,
    delete_company as delete_company_db,
    get_all_department_structures,
    get_department_structure,
    save_department_structure,
    update_department_structure,
    delete_department_structure,
    get_unique_departments,
    get_unique_brands,
    # Responsables
    get_all_responsables,
    get_responsable,
    save_responsable,
    update_responsable,
    delete_responsable,
    # VAT Rates
    get_vat_rates,
    add_vat_rate,
    update_vat_rate,
    delete_vat_rate,
    # Notifications
    get_notification_settings,
    save_notification_settings_bulk,
    save_notification_setting,
    get_notification_logs,
    # Dropdown Options
    get_dropdown_options,
    get_dropdown_option,
    add_dropdown_option,
    update_dropdown_option,
    delete_dropdown_option,
    # User Events
    log_user_event,
    get_user_events,
    get_event_types,
)

logger = get_logger('jarvis.core.services.settings')


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class SettingsService:
    """
    Service for platform settings and admin operations.

    Manages users, roles, permissions, companies, and configuration.
    """

    # ============== Users ==============

    def get_all_users(self) -> ServiceResult:
        """Get all users."""
        try:
            users = get_all_users()
            return ServiceResult(success=True, data=users)
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_user(self, user_id: int) -> ServiceResult:
        """Get a single user by ID."""
        try:
            user = get_user(user_id)
            if user is None:
                return ServiceResult(success=False, error="User not found")
            return ServiceResult(success=True, data=user)
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_user_by_email(self, email: str) -> ServiceResult:
        """Get a user by email."""
        try:
            user = get_user_by_email(email)
            if user is None:
                return ServiceResult(success=False, error="User not found")
            return ServiceResult(success=True, data=user)
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            return ServiceResult(success=False, error=str(e))

    def create_user(
        self,
        email: str,
        name: str,
        role_id: int,
        is_active: bool = True,
    ) -> ServiceResult:
        """Create a new user."""
        try:
            # Check if email already exists
            existing = get_user_by_email(email)
            if existing:
                return ServiceResult(success=False, error="Email already exists")

            user_id = save_user(email, name, role_id, is_active)
            if user_id:
                logger.info("User created", extra={'user_id': user_id, 'email': email})
                return ServiceResult(success=True, data={'user_id': user_id})
            return ServiceResult(success=False, error="Failed to create user")
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_user(
        self,
        user_id: int,
        email: str,
        name: str,
        role_id: int,
        is_active: bool = True,
    ) -> ServiceResult:
        """Update an existing user."""
        try:
            success = update_user(user_id, email, name, role_id, is_active)
            if success:
                logger.info("User updated", extra={'user_id': user_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to update user")
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def delete_user(self, user_id: int) -> ServiceResult:
        """Delete a user."""
        try:
            success = delete_user(user_id)
            if success:
                logger.info("User deleted", extra={'user_id': user_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to delete user")
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def authenticate_user(self, email: str, password: str) -> ServiceResult:
        """Authenticate a user by email and password."""
        try:
            user = authenticate_user(email, password)
            if user:
                update_user_last_login(user['id'])
                return ServiceResult(success=True, data=user)
            return ServiceResult(success=False, error="Invalid credentials")
        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            return ServiceResult(success=False, error=str(e))

    def set_user_password(self, user_id: int, password: str) -> ServiceResult:
        """Set password for a user."""
        try:
            success = set_user_password(user_id, password)
            if success:
                logger.info("Password updated", extra={'user_id': user_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to set password")
        except Exception as e:
            logger.error(f"Error setting password: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_user_last_seen(self, user_id: int) -> ServiceResult:
        """Update user's last seen timestamp."""
        try:
            update_user_last_seen(user_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def get_online_users_count(self) -> ServiceResult:
        """Get count of online users."""
        try:
            count = get_online_users_count()
            return ServiceResult(success=True, data={'count': count})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def set_default_passwords(self) -> ServiceResult:
        """Set default passwords for users without passwords."""
        try:
            count = set_default_password_for_users()
            return ServiceResult(success=True, data={'updated_count': count})
        except Exception as e:
            logger.error(f"Error setting default passwords: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Roles ==============

    def get_all_roles(self) -> ServiceResult:
        """Get all roles."""
        try:
            roles = get_all_roles()
            return ServiceResult(success=True, data=roles)
        except Exception as e:
            logger.error(f"Error getting roles: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_role(self, role_id: int) -> ServiceResult:
        """Get a single role by ID."""
        try:
            role = get_role(role_id)
            if role is None:
                return ServiceResult(success=False, error="Role not found")
            return ServiceResult(success=True, data=role)
        except Exception as e:
            logger.error(f"Error getting role {role_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def create_role(self, name: str, description: str = None) -> ServiceResult:
        """Create a new role."""
        try:
            role_id = save_role(name, description)
            if role_id:
                logger.info("Role created", extra={'role_id': role_id, 'name': name})
                return ServiceResult(success=True, data={'role_id': role_id})
            return ServiceResult(success=False, error="Failed to create role")
        except Exception as e:
            logger.error(f"Error creating role: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_role(
        self,
        role_id: int,
        name: str,
        description: str = None,
    ) -> ServiceResult:
        """Update an existing role."""
        try:
            success = update_role(role_id, name, description)
            if success:
                logger.info("Role updated", extra={'role_id': role_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to update role")
        except Exception as e:
            logger.error(f"Error updating role {role_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def delete_role(self, role_id: int) -> ServiceResult:
        """Delete a role."""
        try:
            success = delete_role(role_id)
            if success:
                logger.info("Role deleted", extra={'role_id': role_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Cannot delete role (may be in use)")
        except Exception as e:
            logger.error(f"Error deleting role {role_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Permissions ==============

    def get_all_permissions(self) -> ServiceResult:
        """Get all permissions (hierarchical)."""
        try:
            permissions = get_all_permissions()
            return ServiceResult(success=True, data=permissions)
        except Exception as e:
            logger.error(f"Error getting permissions: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_permissions_flat(self) -> ServiceResult:
        """Get all permissions (flat list)."""
        try:
            permissions = get_permissions_flat()
            return ServiceResult(success=True, data=permissions)
        except Exception as e:
            logger.error(f"Error getting flat permissions: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_role_permissions(self, role_id: int) -> ServiceResult:
        """Get permissions for a role."""
        try:
            permissions = get_role_permissions(role_id)
            return ServiceResult(success=True, data=permissions)
        except Exception as e:
            logger.error(f"Error getting role permissions: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_role_permissions_list(self, role_id: int) -> ServiceResult:
        """Get permission IDs for a role."""
        try:
            permission_ids = get_role_permissions_list(role_id)
            return ServiceResult(success=True, data=permission_ids)
        except Exception as e:
            logger.error(f"Error getting role permission list: {e}")
            return ServiceResult(success=False, error=str(e))

    def set_role_permissions(
        self,
        role_id: int,
        permission_ids: List[int],
    ) -> ServiceResult:
        """Set permissions for a role."""
        try:
            success = set_role_permissions(role_id, permission_ids)
            if success:
                logger.info(
                    "Role permissions updated",
                    extra={'role_id': role_id, 'permissions': len(permission_ids)}
                )
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to set permissions")
        except Exception as e:
            logger.error(f"Error setting role permissions: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Companies ==============

    def get_all_companies(self) -> ServiceResult:
        """Get all companies."""
        try:
            companies = get_all_companies()
            return ServiceResult(success=True, data=companies)
        except Exception as e:
            logger.error(f"Error getting companies: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_company(self, company_id: int) -> ServiceResult:
        """Get a single company by ID."""
        try:
            company = get_company(company_id)
            if company is None:
                return ServiceResult(success=False, error="Company not found")
            return ServiceResult(success=True, data=company)
        except Exception as e:
            logger.error(f"Error getting company {company_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def create_company(self, company: str, vat: str = None) -> ServiceResult:
        """Create a new company."""
        try:
            company_id = save_company(company, vat)
            if company_id:
                logger.info("Company created", extra={'company_id': company_id})
                return ServiceResult(success=True, data={'company_id': company_id})
            return ServiceResult(success=False, error="Failed to create company")
        except Exception as e:
            logger.error(f"Error creating company: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_company(
        self,
        company_id: int,
        company: str,
        vat: str = None,
    ) -> ServiceResult:
        """Update an existing company."""
        try:
            success = update_company(company_id, company, vat)
            if success:
                logger.info("Company updated", extra={'company_id': company_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to update company")
        except Exception as e:
            logger.error(f"Error updating company {company_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def delete_company(self, company_id: int) -> ServiceResult:
        """Delete a company."""
        try:
            success = delete_company_db(company_id)
            if success:
                logger.info("Company deleted", extra={'company_id': company_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to delete company")
        except Exception as e:
            logger.error(f"Error deleting company {company_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Department Structure ==============

    def get_all_department_structures(self) -> ServiceResult:
        """Get all department structures."""
        try:
            structures = get_all_department_structures()
            return ServiceResult(success=True, data=structures)
        except Exception as e:
            logger.error(f"Error getting department structures: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_department_structure(self, structure_id: int) -> ServiceResult:
        """Get a single department structure by ID."""
        try:
            structure = get_department_structure(structure_id)
            if structure is None:
                return ServiceResult(success=False, error="Structure not found")
            return ServiceResult(success=True, data=structure)
        except Exception as e:
            logger.error(f"Error getting structure {structure_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def create_department_structure(self, data: Dict) -> ServiceResult:
        """Create a new department structure entry."""
        try:
            structure_id = save_department_structure(data)
            if structure_id:
                logger.info("Structure created", extra={'structure_id': structure_id})
                return ServiceResult(success=True, data={'structure_id': structure_id})
            return ServiceResult(success=False, error="Failed to create structure")
        except Exception as e:
            logger.error(f"Error creating structure: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_department_structure(
        self,
        structure_id: int,
        data: Dict,
    ) -> ServiceResult:
        """Update a department structure entry."""
        try:
            success = update_department_structure(structure_id, data)
            if success:
                logger.info("Structure updated", extra={'structure_id': structure_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to update structure")
        except Exception as e:
            logger.error(f"Error updating structure {structure_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def delete_department_structure(self, structure_id: int) -> ServiceResult:
        """Delete a department structure entry."""
        try:
            success = delete_department_structure(structure_id)
            if success:
                logger.info("Structure deleted", extra={'structure_id': structure_id})
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to delete structure")
        except Exception as e:
            logger.error(f"Error deleting structure {structure_id}: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_unique_departments(self) -> ServiceResult:
        """Get unique department names."""
        try:
            departments = get_unique_departments()
            return ServiceResult(success=True, data=departments)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def get_unique_brands(self) -> ServiceResult:
        """Get unique brand names."""
        try:
            brands = get_unique_brands()
            return ServiceResult(success=True, data=brands)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    # ============== Responsables ==============

    def get_all_responsables(self) -> ServiceResult:
        """Get all responsables."""
        try:
            responsables = get_all_responsables()
            return ServiceResult(success=True, data=responsables)
        except Exception as e:
            logger.error(f"Error getting responsables: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_responsable(self, responsable_id: int) -> ServiceResult:
        """Get a single responsable by ID."""
        try:
            responsable = get_responsable(responsable_id)
            if responsable is None:
                return ServiceResult(success=False, error="Responsable not found")
            return ServiceResult(success=True, data=responsable)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def create_responsable(self, data: Dict) -> ServiceResult:
        """Create a new responsable."""
        try:
            responsable_id = save_responsable(data)
            if responsable_id:
                return ServiceResult(success=True, data={'responsable_id': responsable_id})
            return ServiceResult(success=False, error="Failed to create responsable")
        except Exception as e:
            logger.error(f"Error creating responsable: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_responsable(self, responsable_id: int, data: Dict) -> ServiceResult:
        """Update a responsable."""
        try:
            success = update_responsable(responsable_id, data)
            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to update responsable")
        except Exception as e:
            logger.error(f"Error updating responsable: {e}")
            return ServiceResult(success=False, error=str(e))

    def delete_responsable(self, responsable_id: int) -> ServiceResult:
        """Delete a responsable."""
        try:
            success = delete_responsable(responsable_id)
            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to delete responsable")
        except Exception as e:
            logger.error(f"Error deleting responsable: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== VAT Rates ==============

    def get_vat_rates(self) -> ServiceResult:
        """Get all VAT rates."""
        try:
            rates = get_vat_rates()
            return ServiceResult(success=True, data=rates)
        except Exception as e:
            logger.error(f"Error getting VAT rates: {e}")
            return ServiceResult(success=False, error=str(e))

    def create_vat_rate(self, name: str, rate: float) -> ServiceResult:
        """Create a new VAT rate."""
        try:
            rate_id = add_vat_rate(name, rate)
            if rate_id:
                return ServiceResult(success=True, data={'rate_id': rate_id})
            return ServiceResult(success=False, error="Failed to create VAT rate")
        except Exception as e:
            logger.error(f"Error creating VAT rate: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_vat_rate(
        self,
        rate_id: int,
        name: str,
        rate: float,
    ) -> ServiceResult:
        """Update a VAT rate."""
        try:
            success = update_vat_rate(rate_id, name, rate)
            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to update VAT rate")
        except Exception as e:
            logger.error(f"Error updating VAT rate: {e}")
            return ServiceResult(success=False, error=str(e))

    def delete_vat_rate(self, rate_id: int) -> ServiceResult:
        """Delete a VAT rate."""
        try:
            success = delete_vat_rate(rate_id)
            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to delete VAT rate")
        except Exception as e:
            logger.error(f"Error deleting VAT rate: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Notifications ==============

    def get_notification_settings(self) -> ServiceResult:
        """Get notification settings."""
        try:
            settings = get_notification_settings()
            return ServiceResult(success=True, data=settings)
        except Exception as e:
            logger.error(f"Error getting notification settings: {e}")
            return ServiceResult(success=False, error=str(e))

    def save_notification_settings(self, settings: List[Dict]) -> ServiceResult:
        """Save notification settings in bulk."""
        try:
            success = save_notification_settings_bulk(settings)
            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to save settings")
        except Exception as e:
            logger.error(f"Error saving notification settings: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_notification_logs(
        self,
        limit: int = 50,
        event_type: str = None,
    ) -> ServiceResult:
        """Get notification logs."""
        try:
            logs = get_notification_logs(limit, event_type)
            return ServiceResult(success=True, data=logs)
        except Exception as e:
            logger.error(f"Error getting notification logs: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== Dropdown Options ==============

    def get_dropdown_options(self, category: str = None) -> ServiceResult:
        """Get dropdown options, optionally filtered by category."""
        try:
            options = get_dropdown_options(category)
            return ServiceResult(success=True, data=options)
        except Exception as e:
            logger.error(f"Error getting dropdown options: {e}")
            return ServiceResult(success=False, error=str(e))

    def create_dropdown_option(
        self,
        category: str,
        value: str,
        label: str = None,
        sort_order: int = 0,
    ) -> ServiceResult:
        """Create a new dropdown option."""
        try:
            option_id = add_dropdown_option(category, value, label, sort_order)
            if option_id:
                return ServiceResult(success=True, data={'option_id': option_id})
            return ServiceResult(success=False, error="Failed to create option")
        except Exception as e:
            logger.error(f"Error creating dropdown option: {e}")
            return ServiceResult(success=False, error=str(e))

    def update_dropdown_option(
        self,
        option_id: int,
        value: str,
        label: str = None,
        sort_order: int = 0,
    ) -> ServiceResult:
        """Update a dropdown option."""
        try:
            success = update_dropdown_option(option_id, value, label, sort_order)
            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to update option")
        except Exception as e:
            logger.error(f"Error updating dropdown option: {e}")
            return ServiceResult(success=False, error=str(e))

    def delete_dropdown_option(self, option_id: int) -> ServiceResult:
        """Delete a dropdown option."""
        try:
            success = delete_dropdown_option(option_id)
            if success:
                return ServiceResult(success=True)
            return ServiceResult(success=False, error="Failed to delete option")
        except Exception as e:
            logger.error(f"Error deleting dropdown option: {e}")
            return ServiceResult(success=False, error=str(e))

    # ============== User Events (Audit Log) ==============

    def log_event(
        self,
        user_id: int,
        event_type: str,
        details: Dict = None,
    ) -> ServiceResult:
        """Log a user event."""
        try:
            log_user_event(user_id, event_type, details)
            return ServiceResult(success=True)
        except Exception as e:
            logger.error(f"Error logging event: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_user_events(
        self,
        user_id: int = None,
        event_type: str = None,
        limit: int = 100,
    ) -> ServiceResult:
        """Get user events (audit log)."""
        try:
            events = get_user_events(user_id, event_type, limit)
            return ServiceResult(success=True, data=events)
        except Exception as e:
            logger.error(f"Error getting user events: {e}")
            return ServiceResult(success=False, error=str(e))

    def get_event_types(self) -> ServiceResult:
        """Get available event types."""
        try:
            types = get_event_types()
            return ServiceResult(success=True, data=types)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))
