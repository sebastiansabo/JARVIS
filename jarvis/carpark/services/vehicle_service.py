"""Vehicle Service — Business logic layer for CarPark vehicles.

Handles creation, updates (with audit trail), status transitions,
and pricing history.
"""
import logging
from typing import Optional, Dict, Any, List

from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.photo_repository import PhotoRepository
from carpark.repositories.cost_repository import CostRepository
from carpark.repositories.revenue_repository import RevenueRepository

logger = logging.getLogger('jarvis.carpark')

# Fields that trigger pricing history when changed
PRICE_FIELDS = {'current_price', 'list_price', 'promotional_price', 'minimum_price'}

# Fields excluded from modification audit (too noisy or internal)
AUDIT_EXCLUDE = {'updated_at', 'updated_by', 'equipment', 'optional_packages'}


class VehicleService:
    """Core business logic for vehicle operations."""

    def __init__(self):
        self._repo = VehicleRepository()
        self._photo_repo = PhotoRepository()
        self._cost_repo = CostRepository()
        self._revenue_repo = RevenueRepository()

    # ── CATALOG ──

    def get_catalog(self, filters: Dict[str, Any] = None,
                    page: int = 1, per_page: int = 25,
                    sort_by: str = 'acquisition_date',
                    sort_dir: str = 'DESC') -> Dict[str, Any]:
        """Get paginated catalog list. Delegates directly to repository."""
        per_page = min(per_page, 100)  # Cap at 100
        return self._repo.get_catalog(filters, page, per_page, sort_by, sort_dir)

    def get_status_counts(self, company_id: int = None) -> List[Dict[str, Any]]:
        """Vehicle counts per status for catalog tabs."""
        return self._repo.get_status_counts(company_id)

    def get_filter_options(self, company_id: int = None) -> Dict[str, List]:
        """Distinct filter values for dropdowns."""
        return self._repo.get_filter_options(company_id)

    # ── SINGLE VEHICLE ──

    def get_vehicle(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        """Get full vehicle detail with computed fields."""
        vehicle = self._repo.get_by_id(vehicle_id)
        if not vehicle:
            return None

        # Attach photo count
        photos = self._photo_repo.get_by_vehicle(vehicle_id)
        vehicle['photos'] = photos
        vehicle['photo_count'] = len(photos)

        return vehicle

    def get_vehicle_lean(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        """Get vehicle without attached relations (for mobile/quick lookups)."""
        return self._repo.get_by_id(vehicle_id)

    # ── CREATE ──

    def create_vehicle(self, data: Dict[str, Any],
                       created_by: int = None) -> Dict[str, Any]:
        """Create a new vehicle with validation.

        Raises ValueError on invalid data or duplicate VIN.
        """
        if not data.get('vin'):
            raise ValueError('VIN is required')
        if not data.get('brand'):
            raise ValueError('Brand is required')
        if not data.get('model'):
            raise ValueError('Model is required')

        # Check duplicate VIN
        existing = self._repo.get_by_vin(data['vin'].strip().upper())
        if existing:
            raise ValueError(f'A vehicle with VIN {data["vin"]} already exists')

        if created_by:
            data['created_by'] = created_by
            data['updated_by'] = created_by

        vehicle = self._repo.create(data)
        logger.info(f'Vehicle created: id={vehicle["id"]} vin={vehicle["vin"]} by user={created_by}')

        # Record initial status in history
        self._repo.change_status(vehicle['id'], vehicle.get('status', 'ACQUIRED'),
                                 changed_by=created_by, notes='Initial creation')

        return vehicle

    # ── UPDATE ──

    def update_vehicle(self, vehicle_id: int, data: Dict[str, Any],
                       updated_by: int = None,
                       updated_by_name: str = None) -> Optional[Dict[str, Any]]:
        """Update vehicle with field-level audit trail and pricing history.

        Compares old vs new values, logs changes to modification_history,
        and records price changes to pricing_history.
        """
        old_vehicle = self._repo.get_by_id(vehicle_id)
        if not old_vehicle:
            return None

        updated = self._repo.update(vehicle_id, data, updated_by=updated_by)
        if not updated:
            return old_vehicle

        # Audit trail: log changed fields
        from core.base_repository import BaseRepository
        history_repo = BaseRepository()  # Use base for simple inserts

        for field, new_val in data.items():
            if field in AUDIT_EXCLUDE:
                continue
            old_val = old_vehicle.get(field)

            # Compare with type coercion for decimals
            if str(old_val) != str(new_val) and not (old_val is None and new_val is None):
                self._repo.log_modification(
                    vehicle_id, field,
                    old_val, new_val,
                    changed_by=updated_by,
                    changed_by_name=updated_by_name
                )

                # Pricing history for price fields
                if field in PRICE_FIELDS:
                    try:
                        old_price = float(old_val) if old_val is not None else None
                        new_price = float(new_val) if new_val is not None else None
                        history_repo.execute('''
                            INSERT INTO carpark_pricing_history
                                (vehicle_id, old_price, new_price, change_reason, changed_by)
                            VALUES (%s, %s, %s, %s, %s)
                        ''', (vehicle_id, old_price, new_price, 'manual_update', updated_by))
                    except (TypeError, ValueError):
                        pass

        logger.info(f'Vehicle updated: id={vehicle_id} by user={updated_by}')
        return updated

    # ── STATUS CHANGE ──

    def change_status(self, vehicle_id: int, new_status: str,
                      changed_by: int = None,
                      notes: str = None) -> Optional[Dict[str, Any]]:
        """Change vehicle status with validation and history."""
        return self._repo.change_status(vehicle_id, new_status,
                                        changed_by=changed_by, notes=notes)

    # ── SOFT DELETE ──

    def delete_vehicle(self, vehicle_id: int) -> bool:
        """Soft-delete a vehicle."""
        result = self._repo.soft_delete(vehicle_id)
        if result:
            logger.info(f'Vehicle soft-deleted: id={vehicle_id}')
        return result

    # ── HISTORY ──

    def get_status_history(self, vehicle_id: int) -> List[Dict[str, Any]]:
        return self._repo.get_status_history(vehicle_id)

    def get_modification_history(self, vehicle_id: int,
                                  limit: int = 50) -> List[Dict[str, Any]]:
        return self._repo.get_modification_history(vehicle_id, limit)

    # ── LOCATIONS ──

    def get_locations(self, company_id: int = None) -> List[Dict[str, Any]]:
        return self._repo.get_locations(company_id)

    def create_location(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if not data.get('name') or not data.get('code'):
            raise ValueError('Location name and code are required')
        return self._repo.create_location(data)

    def update_location(self, location_id: int,
                        data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._repo.update_location(location_id, data)

    # ── COSTS ──

    def get_costs(self, vehicle_id: int,
                  cost_type: str = None) -> List[Dict[str, Any]]:
        return self._cost_repo.get_by_vehicle(vehicle_id, cost_type)

    def get_cost(self, cost_id: int) -> Optional[Dict[str, Any]]:
        return self._cost_repo.get_by_id(cost_id)

    def create_cost(self, vehicle_id: int, data: Dict[str, Any],
                    created_by: int = None) -> Dict[str, Any]:
        cost = self._cost_repo.create(vehicle_id, data, created_by=created_by)
        logger.info(f'Cost created: id={cost["id"]} vehicle={vehicle_id} '
                     f'type={cost["cost_type"]} amount={cost["amount"]}')
        return cost

    def update_cost(self, cost_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._cost_repo.update(cost_id, data)

    def delete_cost(self, cost_id: int) -> bool:
        return self._cost_repo.delete(cost_id)

    def get_cost_totals(self, vehicle_id: int) -> Dict[str, Any]:
        return self._cost_repo.get_totals_by_vehicle(vehicle_id)

    # ── REVENUES ──

    def get_revenues(self, vehicle_id: int,
                     revenue_type: str = None) -> List[Dict[str, Any]]:
        return self._revenue_repo.get_by_vehicle(vehicle_id, revenue_type)

    def get_revenue(self, revenue_id: int) -> Optional[Dict[str, Any]]:
        return self._revenue_repo.get_by_id(revenue_id)

    def create_revenue(self, vehicle_id: int, data: Dict[str, Any],
                       created_by: int = None) -> Dict[str, Any]:
        rev = self._revenue_repo.create(vehicle_id, data, created_by=created_by)
        logger.info(f'Revenue created: id={rev["id"]} vehicle={vehicle_id} '
                     f'type={rev["revenue_type"]} amount={rev["amount"]}')
        return rev

    def update_revenue(self, revenue_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._revenue_repo.update(revenue_id, data)

    def delete_revenue(self, revenue_id: int) -> bool:
        return self._revenue_repo.delete(revenue_id)

    def get_revenue_totals(self, vehicle_id: int) -> Dict[str, Any]:
        return self._revenue_repo.get_totals_by_vehicle(vehicle_id)

    # ── PROFITABILITY ──

    def get_profitability(self, vehicle_id: int) -> Dict[str, Any]:
        """Calculate vehicle profitability: revenues - costs."""
        costs = self._cost_repo.get_totals_by_vehicle(vehicle_id)
        revenues = self._revenue_repo.get_totals_by_vehicle(vehicle_id)
        vehicle = self._repo.get_by_id(vehicle_id)

        acquisition_price = float(vehicle.get('acquisition_price') or 0) if vehicle else 0

        total_costs = float(costs['total_with_vat'])
        total_revenues = float(revenues['total_with_vat'])

        return {
            'acquisition_price': acquisition_price,
            'total_costs': total_costs,
            'total_revenues': total_revenues,
            'total_invested': acquisition_price + total_costs,
            'profit': total_revenues - acquisition_price - total_costs,
            'costs_breakdown': costs['by_type'],
            'revenues_breakdown': revenues['by_type'],
        }
