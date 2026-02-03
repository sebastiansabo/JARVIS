"""HR Events Service - Business logic for HR Events module.

This module contains all business logic related to HR Events.
Routes should call these methods instead of accessing the database directly.
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from ..repositories import (
    EmployeeRepository,
    EventRepository,
    BonusRepository,
    StructureRepository,
)


@dataclass
class ServiceResult:
    """Result of a service operation."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class HREventsService:
    """Service for HR Events business logic.

    Coordinates all HR Events operations through the repository layer.
    """

    def __init__(self):
        self.employee_repo = EmployeeRepository()
        self.event_repo = EventRepository()
        self.bonus_repo = BonusRepository()
        self.structure_repo = StructureRepository()

    # ============== Employees ==============

    def get_all_employees(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all HR employees."""
        return self.employee_repo.get_all(active_only=active_only)

    def get_employee(self, employee_id: int) -> Optional[Dict[str, Any]]:
        """Get a single employee by ID."""
        return self.employee_repo.get_by_id(employee_id)

    def create_employee(
        self,
        name: str,
        department: str = None,
        subdepartment: str = None,
        brand: str = None,
        company: str = None,
        email: str = None,
        phone: str = None,
        notify_on_allocation: bool = True
    ) -> ServiceResult:
        """Create a new employee."""
        try:
            employee_id = self.employee_repo.create(
                name=name,
                department=department,
                subdepartment=subdepartment,
                brand=brand,
                company=company,
                email=email,
                phone=phone,
                notify_on_allocation=notify_on_allocation
            )
            return ServiceResult(success=True, data={'id': employee_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_employee(
        self,
        employee_id: int,
        name: str,
        department: str = None,
        subdepartment: str = None,
        brand: str = None,
        company: str = None,
        email: str = None,
        phone: str = None,
        notify_on_allocation: bool = True,
        is_active: bool = True
    ) -> ServiceResult:
        """Update an employee."""
        try:
            self.employee_repo.update(
                employee_id=employee_id,
                name=name,
                department=department,
                subdepartment=subdepartment,
                brand=brand,
                company=company,
                email=email,
                phone=phone,
                notify_on_allocation=notify_on_allocation,
                is_active=is_active
            )
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_employee(self, employee_id: int) -> ServiceResult:
        """Soft delete an employee."""
        try:
            self.employee_repo.delete(employee_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def search_employees(self, query: str) -> List[Dict[str, Any]]:
        """Search employees by name."""
        return self.employee_repo.search(query)

    # ============== Events ==============

    def get_all_events(self) -> List[Dict[str, Any]]:
        """Get all HR events."""
        return self.event_repo.get_all()

    def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Get a single event by ID."""
        return self.event_repo.get_by_id(event_id)

    def create_event(
        self,
        name: str,
        start_date: str,
        end_date: str,
        company: str = None,
        brand: str = None,
        description: str = None,
        created_by: int = None
    ) -> ServiceResult:
        """Create a new event."""
        try:
            event_id = self.event_repo.create(
                name=name,
                start_date=start_date,
                end_date=end_date,
                company=company,
                brand=brand,
                description=description,
                created_by=created_by
            )
            return ServiceResult(success=True, data={'id': event_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_event(
        self,
        event_id: int,
        name: str,
        start_date: str,
        end_date: str,
        company: str = None,
        brand: str = None,
        description: str = None
    ) -> ServiceResult:
        """Update an event."""
        try:
            self.event_repo.update(
                event_id=event_id,
                name=name,
                start_date=start_date,
                end_date=end_date,
                company=company,
                brand=brand,
                description=description
            )
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_event(self, event_id: int) -> ServiceResult:
        """Delete an event."""
        try:
            self.event_repo.delete(event_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    # ============== Event Bonuses ==============

    def get_all_bonuses(
        self,
        year: int = None,
        month: int = None,
        employee_id: int = None,
        event_id: int = None
    ) -> List[Dict[str, Any]]:
        """Get all event bonuses with optional filters."""
        return self.bonus_repo.get_all(
            year=year,
            month=month,
            employee_id=employee_id,
            event_id=event_id
        )

    def get_bonus(self, bonus_id: int) -> Optional[Dict[str, Any]]:
        """Get a single bonus by ID."""
        return self.bonus_repo.get_by_id(bonus_id)

    def create_bonus(
        self,
        employee_id: int,
        event_id: int,
        year: int,
        month: int,
        participation_start: str = None,
        participation_end: str = None,
        bonus_days: int = None,
        hours_free: float = None,
        bonus_net: float = None,
        details: str = None,
        allocation_month: int = None,
        created_by: int = None
    ) -> ServiceResult:
        """Create a new event bonus."""
        try:
            bonus_id = self.bonus_repo.create(
                employee_id=employee_id,
                event_id=event_id,
                year=year,
                month=month,
                participation_start=participation_start,
                participation_end=participation_end,
                bonus_days=bonus_days,
                hours_free=hours_free,
                bonus_net=bonus_net,
                details=details,
                allocation_month=allocation_month,
                created_by=created_by
            )
            return ServiceResult(success=True, data={'id': bonus_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def create_bonuses_bulk(
        self,
        bonuses: List[Dict[str, Any]],
        created_by: int = None
    ) -> ServiceResult:
        """Bulk create event bonuses."""
        try:
            if not bonuses:
                return ServiceResult(success=False, error='No bonuses provided')
            created_ids = self.bonus_repo.create_bulk(bonuses, created_by=created_by)
            return ServiceResult(success=True, data={'ids': created_ids, 'count': len(created_ids)})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_bonus(
        self,
        bonus_id: int,
        employee_id: int,
        event_id: int,
        year: int,
        month: int,
        participation_start: str = None,
        participation_end: str = None,
        bonus_days: int = None,
        hours_free: float = None,
        bonus_net: float = None,
        details: str = None,
        allocation_month: int = None
    ) -> ServiceResult:
        """Update an event bonus."""
        try:
            self.bonus_repo.update(
                bonus_id=bonus_id,
                employee_id=employee_id,
                event_id=event_id,
                year=year,
                month=month,
                participation_start=participation_start,
                participation_end=participation_end,
                bonus_days=bonus_days,
                hours_free=hours_free,
                bonus_net=bonus_net,
                details=details,
                allocation_month=allocation_month
            )
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_bonus(self, bonus_id: int) -> ServiceResult:
        """Delete an event bonus."""
        try:
            self.bonus_repo.delete(bonus_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    # ============== Summary/Stats ==============

    def get_bonuses_summary(self, year: int = None) -> Dict[str, Any]:
        """Get summary statistics for event bonuses."""
        return self.bonus_repo.get_summary(year=year)

    def get_bonuses_by_month(self, year: int) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by month."""
        return self.bonus_repo.get_by_month(year)

    def get_bonuses_by_employee(self, year: int = None, month: int = None) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by employee."""
        return self.bonus_repo.get_by_employee(year=year, month=month)

    def get_bonuses_by_event(self, year: int = None, month: int = None) -> List[Dict[str, Any]]:
        """Get bonus totals grouped by event."""
        return self.bonus_repo.get_by_event(year=year, month=month)

    # ============== Bonus Types ==============

    def get_all_bonus_types(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all bonus types."""
        return self.bonus_repo.get_all_types(active_only=active_only)

    def get_bonus_type(self, bonus_type_id: int) -> Optional[Dict[str, Any]]:
        """Get a single bonus type by ID."""
        return self.bonus_repo.get_type_by_id(bonus_type_id)

    def create_bonus_type(
        self,
        name: str,
        amount: float,
        days_per_amount: int = 1,
        description: str = None
    ) -> ServiceResult:
        """Create a new bonus type."""
        try:
            bonus_type_id = self.bonus_repo.create_type(
                name=name,
                amount=amount,
                days_per_amount=days_per_amount,
                description=description
            )
            return ServiceResult(success=True, data={'id': bonus_type_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_bonus_type(
        self,
        bonus_type_id: int,
        name: str,
        amount: float,
        days_per_amount: int = 1,
        description: str = None,
        is_active: bool = True
    ) -> ServiceResult:
        """Update a bonus type."""
        try:
            self.bonus_repo.update_type(
                bonus_type_id=bonus_type_id,
                name=name,
                amount=amount,
                days_per_amount=days_per_amount,
                description=description,
                is_active=is_active
            )
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_bonus_type(self, bonus_type_id: int) -> ServiceResult:
        """Soft delete a bonus type."""
        try:
            self.bonus_repo.delete_type(bonus_type_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    # ============== Structure - Companies ==============

    def get_all_companies_full(self) -> List[Dict[str, Any]]:
        """Get all companies with full details."""
        return self.structure_repo.get_all_companies()

    def create_company(self, company: str, vat: str = None) -> ServiceResult:
        """Create a new company."""
        try:
            company_id = self.structure_repo.create_company(company=company, vat=vat)
            return ServiceResult(success=True, data={'id': company_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_company(self, company_id: int, company: str, vat: str = None) -> ServiceResult:
        """Update a company."""
        try:
            self.structure_repo.update_company(company_id=company_id, company=company, vat=vat)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_company(self, company_id: int) -> ServiceResult:
        """Delete a company."""
        try:
            self.structure_repo.delete_company(company_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    # ============== Structure - Company Brands ==============

    def get_company_brands(self, company_id: int = None) -> List[Dict[str, Any]]:
        """Get all company brands."""
        return self.structure_repo.get_company_brands(company_id=company_id)

    def get_brands_for_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get brands for a specific company."""
        return self.structure_repo.get_brands_for_company(company_id)

    def create_company_brand(self, company_id: int, brand_id: int) -> ServiceResult:
        """Create a new company brand."""
        try:
            cb_id = self.structure_repo.create_company_brand(company_id=company_id, brand_id=brand_id)
            return ServiceResult(success=True, data={'id': cb_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_company_brand(self, brand_id: int, new_brand_id: int, is_active: bool = True) -> ServiceResult:
        """Update a company brand."""
        try:
            self.structure_repo.update_company_brand(brand_id=brand_id, new_brand_id=new_brand_id, is_active=is_active)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_company_brand(self, brand_id: int) -> ServiceResult:
        """Delete a company brand."""
        try:
            self.structure_repo.delete_company_brand(brand_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    # ============== Structure - Department Structure ==============

    def get_all_department_structures(self) -> List[Dict[str, Any]]:
        """Get all department structure entries."""
        return self.structure_repo.get_all_department_structures()

    def create_department_structure(
        self,
        company_id: int,
        brand_id: int = None,
        department_id: int = None,
        subdepartment_id: int = None,
        manager: str = None
    ) -> ServiceResult:
        """Create a new department structure entry."""
        try:
            dept_id = self.structure_repo.create_department_structure(
                company_id=company_id,
                brand_id=brand_id,
                department_id=department_id,
                subdepartment_id=subdepartment_id,
                manager=manager
            )
            return ServiceResult(success=True, data={'id': dept_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_department_structure(
        self,
        dept_id: int,
        company_id: int,
        brand_id: int = None,
        department_id: int = None,
        subdepartment_id: int = None,
        manager: str = None
    ) -> ServiceResult:
        """Update a department structure entry."""
        try:
            self.structure_repo.update_department_structure(
                dept_id=dept_id,
                company_id=company_id,
                brand_id=brand_id,
                department_id=department_id,
                subdepartment_id=subdepartment_id,
                manager=manager
            )
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_department_structure(self, dept_id: int) -> ServiceResult:
        """Delete a department structure entry."""
        try:
            self.structure_repo.delete_department_structure(dept_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    # ============== Structure - Master Tables ==============

    def get_master_brands(self) -> List[Dict[str, Any]]:
        """Get all brands from master table."""
        return self.structure_repo.get_master_brands()

    def create_master_brand(self, name: str) -> ServiceResult:
        """Create a new brand in master table."""
        try:
            brand_id = self.structure_repo.create_master_brand(name)
            return ServiceResult(success=True, data={'id': brand_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_master_brand(self, brand_id: int, name: str, is_active: bool = True) -> ServiceResult:
        """Update a brand in master table."""
        try:
            self.structure_repo.update_master_brand(brand_id=brand_id, name=name, is_active=is_active)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_master_brand(self, brand_id: int) -> ServiceResult:
        """Soft delete a brand from master table."""
        try:
            self.structure_repo.delete_master_brand(brand_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def get_master_departments(self) -> List[Dict[str, Any]]:
        """Get all departments from master table."""
        return self.structure_repo.get_master_departments()

    def create_master_department(self, name: str) -> ServiceResult:
        """Create a new department in master table."""
        try:
            dept_id = self.structure_repo.create_master_department(name)
            return ServiceResult(success=True, data={'id': dept_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_master_department(self, dept_id: int, name: str, is_active: bool = True) -> ServiceResult:
        """Update a department in master table."""
        try:
            self.structure_repo.update_master_department(dept_id=dept_id, name=name, is_active=is_active)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_master_department(self, dept_id: int) -> ServiceResult:
        """Soft delete a department from master table."""
        try:
            self.structure_repo.delete_master_department(dept_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def get_master_subdepartments(self) -> List[Dict[str, Any]]:
        """Get all subdepartments from master table."""
        return self.structure_repo.get_master_subdepartments()

    def create_master_subdepartment(self, name: str) -> ServiceResult:
        """Create a new subdepartment in master table."""
        try:
            subdept_id = self.structure_repo.create_master_subdepartment(name)
            return ServiceResult(success=True, data={'id': subdept_id})
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def update_master_subdepartment(self, subdept_id: int, name: str, is_active: bool = True) -> ServiceResult:
        """Update a subdepartment in master table."""
        try:
            self.structure_repo.update_master_subdepartment(subdept_id=subdept_id, name=name, is_active=is_active)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))

    def delete_master_subdepartment(self, subdept_id: int) -> ServiceResult:
        """Soft delete a subdepartment from master table."""
        try:
            self.structure_repo.delete_master_subdepartment(subdept_id)
            return ServiceResult(success=True)
        except Exception as e:
            return ServiceResult(success=False, error=str(e))
