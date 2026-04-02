"""Vehicle Repository — Data access for carpark_vehicles and related tables."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository


# Fields safe for client-submitted updates (whitelist)
VEHICLE_UPDATABLE_FIELDS = {
    'vin', 'identification_number', 'registration_number', 'chassis_code',
    'emission_code', 'category', 'status', 'vehicle_type', 'state',
    'brand', 'model', 'variant', 'generation', 'equipment_level',
    'body_type', 'year_of_manufacture', 'first_registration_date',
    'color_exterior', 'color_code', 'color_interior', 'interior_code',
    'fuel_type', 'transmission', 'drive_type', 'engine_displacement_cc',
    'engine_power_hp', 'engine_power_kw', 'engine_power_electric_hp',
    'engine_torque_nm', 'co2_emissions', 'euro_standard', 'mileage_km',
    'max_weight_kg', 'doors', 'seats', 'tire_type', 'fuel_consumption',
    'equipment', 'optional_packages',
    'has_manufacturer_warranty', 'manufacturer_warranty_date',
    'has_dealer_warranty', 'dealer_warranty_months',
    'is_registered', 'is_first_owner', 'has_accident_history',
    'has_service_book', 'is_electric_vehicle', 'has_tuning',
    'youtube_url', 'listing_title', 'listing_description',
    'location_id', 'parking_spot', 'location_text',
    'source', 'supplier_name', 'supplier_cif',
    'purchase_contract_number', 'purchase_contract_date', 'owner_name',
    'acquisition_manager_id', 'acquisition_document_number',
    'acquisition_date', 'arrival_date',
    'acquisition_value', 'acquisition_vat', 'acquisition_price',
    'acquisition_currency', 'acquisition_exchange_rate',
    'purchase_price_net', 'purchase_price_currency', 'purchase_vat_rate',
    'reconditioning_cost', 'transport_cost', 'registration_cost', 'other_costs',
    'list_price', 'promotional_price', 'minimum_price', 'current_price',
    'price_currency', 'price_includes_vat', 'vat_deductible',
    'is_negotiable', 'margin_scheme',
    'eligible_for_financing', 'available_for_leasing', 'can_issue_invoice',
    'is_consignment', 'promotion_id',
    'is_test_drive', 'service_exchange_vehicle',
    'sale_price', 'sale_date', 'buyer_client_id', 'salesperson_user_id',
    'nr_stoc', 'ready_for_sale_date', 'listing_date',
    'reservation_date', 'delivery_date',
    'notes', 'internal_notes', 'brand_id',
}

# Lightweight fields for catalog list (mobile-friendly)
CATALOG_SELECT = """
    v.id, v.vin, v.nr_stoc, v.brand, v.model, v.variant, v.category, v.status,
    v.year_of_manufacture, v.fuel_type, v.transmission, v.body_type,
    v.mileage_km, v.engine_power_hp, v.color_exterior,
    v.current_price, v.list_price, v.promotional_price, v.price_currency,
    v.acquisition_date, v.arrival_date,
    v.is_consignment, v.is_test_drive, v.total_cost,
    v.location_text, v.company_id, v.days_listed,
    (CURRENT_DATE - COALESCE(v.arrival_date, v.acquisition_date)) AS stationary_days,
    (SELECT url FROM carpark_vehicle_photos p
     WHERE p.vehicle_id = v.id AND p.is_primary = TRUE LIMIT 1) AS primary_photo_url,
    (SELECT COUNT(*) FROM carpark_vehicle_photos p WHERE p.vehicle_id = v.id) AS photo_count
"""


class VehicleRepository(BaseRepository):
    """Data access for carpark_vehicles."""

    # ── LIST / SEARCH ──

    def get_catalog(self, filters: Dict[str, Any] = None,
                    page: int = 1, per_page: int = 25,
                    sort_by: str = 'acquisition_date',
                    sort_dir: str = 'DESC') -> Dict[str, Any]:
        """Paginated catalog list with lightweight fields.

        Returns: { items: [...], total: int, page: int, per_page: int }
        """
        filters = filters or {}
        where_clauses = ['v.deleted_at IS NULL']
        params: list = []

        # Status tab filter
        if filters.get('status'):
            where_clauses.append('v.status = %s')
            params.append(filters['status'])

        # Category filter
        if filters.get('category'):
            where_clauses.append('v.category = %s')
            params.append(filters['category'])

        # Brand filter
        if filters.get('brand'):
            where_clauses.append('v.brand = %s')
            params.append(filters['brand'])

        # Model filter (partial match)
        if filters.get('model'):
            where_clauses.append('v.model ILIKE %s')
            params.append(f'%{filters["model"]}%')

        # Fuel type
        if filters.get('fuel_type'):
            where_clauses.append('v.fuel_type = %s')
            params.append(filters['fuel_type'])

        # Body type
        if filters.get('body_type'):
            where_clauses.append('v.body_type = %s')
            params.append(filters['body_type'])

        # Year range
        if filters.get('year_min'):
            where_clauses.append('v.year_of_manufacture >= %s')
            params.append(int(filters['year_min']))
        if filters.get('year_max'):
            where_clauses.append('v.year_of_manufacture <= %s')
            params.append(int(filters['year_max']))

        # Price range
        if filters.get('price_min'):
            where_clauses.append('v.current_price >= %s')
            params.append(float(filters['price_min']))
        if filters.get('price_max'):
            where_clauses.append('v.current_price <= %s')
            params.append(float(filters['price_max']))

        # Mileage range
        if filters.get('km_min'):
            where_clauses.append('v.mileage_km >= %s')
            params.append(int(filters['km_min']))
        if filters.get('km_max'):
            where_clauses.append('v.mileage_km <= %s')
            params.append(int(filters['km_max']))

        # Company scope
        if filters.get('company_id'):
            where_clauses.append('v.company_id = %s')
            params.append(int(filters['company_id']))

        # Location
        if filters.get('location_id'):
            where_clauses.append('v.location_id = %s')
            params.append(int(filters['location_id']))

        # Text search (VIN, nr_stoc, brand+model)
        if filters.get('search'):
            search_term = f'%{filters["search"]}%'
            where_clauses.append(
                '(v.vin ILIKE %s OR v.nr_stoc ILIKE %s OR '
                'v.brand ILIKE %s OR v.model ILIKE %s OR '
                'v.registration_number ILIKE %s)'
            )
            params.extend([search_term] * 5)

        where_sql = ' AND '.join(where_clauses)

        # Whitelist sort columns to prevent injection
        allowed_sorts = {
            'acquisition_date', 'current_price', 'brand', 'model',
            'year_of_manufacture', 'mileage_km', 'stationary_days',
            'created_at', 'nr_stoc', 'status',
        }
        if sort_by not in allowed_sorts:
            sort_by = 'acquisition_date'
        sort_dir = 'ASC' if sort_dir.upper() == 'ASC' else 'DESC'

        # Count
        count_sql = f'SELECT COUNT(*) as total FROM carpark_vehicles v WHERE {where_sql}'
        total_row = self.query_one(count_sql, tuple(params))
        total = total_row['total'] if total_row else 0

        # Paginated results
        offset = (page - 1) * per_page
        data_sql = f"""
            SELECT {CATALOG_SELECT}
            FROM carpark_vehicles v
            WHERE {where_sql}
            ORDER BY v.{sort_by} {sort_dir}
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])
        items = self.query_all(data_sql, tuple(params))

        return {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
        }

    # ── SINGLE VEHICLE ──

    def get_by_id(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        """Full vehicle record by ID."""
        return self.query_one('''
            SELECT v.*,
                   l.name as location_name, l.code as location_code,
                   (CURRENT_DATE - COALESCE(v.arrival_date, v.acquisition_date)) AS stationary_days
            FROM carpark_vehicles v
            LEFT JOIN carpark_locations l ON v.location_id = l.id
            WHERE v.id = %s AND v.deleted_at IS NULL
        ''', (vehicle_id,))

    def get_by_vin(self, vin: str) -> Optional[Dict[str, Any]]:
        """Lookup vehicle by VIN."""
        return self.query_one('''
            SELECT id, vin, brand, model, status
            FROM carpark_vehicles
            WHERE vin = %s AND deleted_at IS NULL
        ''', (vin,))

    # ── CREATE ──

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new vehicle. Returns the created record with id."""
        # Filter to allowed fields only
        safe_data = {k: v for k, v in data.items() if k in VEHICLE_UPDATABLE_FIELDS}

        if 'vin' not in safe_data or 'brand' not in safe_data or 'model' not in safe_data:
            raise ValueError('vin, brand, and model are required')

        # Validate VIN format: 17 alphanumeric chars, no I/O/Q per ISO 3779
        import re
        vin = safe_data['vin'].strip().upper()
        if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', vin):
            raise ValueError('VIN must be exactly 17 alphanumeric characters (no I, O, Q)')
        safe_data['vin'] = vin

        # Add server-controlled fields (not user-settable via whitelist)
        for server_field in ('company_id', 'created_by', 'updated_by'):
            if server_field in data and server_field not in safe_data:
                safe_data[server_field] = data[server_field]

        columns = list(safe_data.keys())

        placeholders = ', '.join(['%s'] * len(columns))
        col_names = ', '.join(columns)
        values = [safe_data[c] for c in columns]

        return self.execute(
            f'INSERT INTO carpark_vehicles ({col_names}) VALUES ({placeholders}) RETURNING *',
            tuple(values), returning=True
        )

    # ── UPDATE ──

    def update(self, vehicle_id: int, data: Dict[str, Any],
               updated_by: int = None) -> Optional[Dict[str, Any]]:
        """Update vehicle fields. Returns updated record."""
        safe_data = {k: v for k, v in data.items() if k in VEHICLE_UPDATABLE_FIELDS}
        if not safe_data:
            return self.get_by_id(vehicle_id)

        sets = []
        params = []
        for key, value in safe_data.items():
            sets.append(f'{key} = %s')
            params.append(value)

        sets.append('updated_at = CURRENT_TIMESTAMP')
        if updated_by is not None:
            sets.append('updated_by = %s')
            params.append(updated_by)

        params.append(vehicle_id)
        return self.execute(
            f"UPDATE carpark_vehicles SET {', '.join(sets)} WHERE id = %s AND deleted_at IS NULL RETURNING *",
            tuple(params), returning=True
        )

    # ── SOFT DELETE ──

    def soft_delete(self, vehicle_id: int) -> bool:
        """Soft-delete a vehicle."""
        return self.execute(
            'UPDATE carpark_vehicles SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s AND deleted_at IS NULL',
            (vehicle_id,)
        ) > 0

    # ── STATUS CHANGE ──

    def change_status(self, vehicle_id: int, new_status: str,
                      changed_by: int = None, notes: str = None) -> Optional[Dict[str, Any]]:
        """Change vehicle status and record history. Returns updated vehicle."""
        VALID_STATUSES = {
            'ACQUIRED', 'INSPECTION', 'RECONDITIONING', 'READY_FOR_SALE',
            'LISTED', 'RESERVED', 'SOLD', 'DELIVERED',
            'PRICE_REDUCED', 'AUCTION_CANDIDATE',
            'IN_TRANSIT', 'AT_BODYSHOP', 'INSURANCE_CLAIM',
            'RETURNED', 'SCRAPPED', 'TRANSFERRED',
        }
        if new_status not in VALID_STATUSES:
            raise ValueError(f'Invalid status: {new_status}')

        def _work(cursor):
            # Get current status
            cursor.execute(
                'SELECT id, status, location_id FROM carpark_vehicles WHERE id = %s AND deleted_at IS NULL',
                (vehicle_id,)
            )
            vehicle = cursor.fetchone()
            if not vehicle:
                return None

            old_status = vehicle['status']
            if old_status == new_status:
                return dict(vehicle)

            # Update status
            cursor.execute(
                'UPDATE carpark_vehicles SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *',
                (new_status, vehicle_id)
            )
            updated = cursor.fetchone()

            # Record history
            cursor.execute('''
                INSERT INTO carpark_status_history
                    (vehicle_id, old_status, new_status, old_location_id, new_location_id, notes, changed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (vehicle_id, old_status, new_status,
                  vehicle['location_id'], vehicle['location_id'],
                  notes, changed_by))

            return dict(updated) if updated else None

        return self.execute_many(_work)

    # ── AGGREGATES ──

    def get_status_counts(self, company_id: int = None) -> List[Dict[str, Any]]:
        """Count vehicles per status (for catalog tabs)."""
        sql = '''
            SELECT status, COUNT(*) as count
            FROM carpark_vehicles
            WHERE deleted_at IS NULL
        '''
        params = []
        if company_id:
            sql += ' AND company_id = %s'
            params.append(company_id)
        sql += ' GROUP BY status ORDER BY status'
        return self.query_all(sql, tuple(params))

    def get_filter_options(self, company_id: int = None) -> Dict[str, List]:
        """Distinct values for filter dropdowns."""
        where = 'WHERE deleted_at IS NULL'
        params = []
        if company_id:
            where += ' AND company_id = %s'
            params.append(company_id)

        brands = self.query_all(
            f'SELECT DISTINCT brand FROM carpark_vehicles {where} ORDER BY brand',
            tuple(params)
        )
        fuel_types = self.query_all(
            f'SELECT DISTINCT fuel_type FROM carpark_vehicles {where} AND fuel_type IS NOT NULL ORDER BY fuel_type',
            tuple(params)
        )
        body_types = self.query_all(
            f'SELECT DISTINCT body_type FROM carpark_vehicles {where} AND body_type IS NOT NULL ORDER BY body_type',
            tuple(params)
        )
        return {
            'brands': [r['brand'] for r in brands],
            'fuel_types': [r['fuel_type'] for r in fuel_types],
            'body_types': [r['body_type'] for r in body_types],
        }

    # ── HISTORY ──

    def get_status_history(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """Get status change history for a vehicle."""
        return self.query_all('''
            SELECT sh.*, u.name as changed_by_name
            FROM carpark_status_history sh
            LEFT JOIN users u ON sh.changed_by = u.id
            WHERE sh.vehicle_id = %s
            ORDER BY sh.created_at DESC
        ''', (vehicle_id,))

    def log_modification(self, vehicle_id: int, field_name: str,
                         old_value: str, new_value: str,
                         changed_by: int = None, changed_by_name: str = None):
        """Record a field-level change for audit trail."""
        self.execute('''
            INSERT INTO carpark_modification_history
                (vehicle_id, field_name, old_value, new_value, changed_by, changed_by_name)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (vehicle_id, field_name, str(old_value) if old_value is not None else None,
              str(new_value) if new_value is not None else None,
              changed_by, changed_by_name))

    def get_modification_history(self, vehicle_id: int,
                                  limit: int = 50) -> List[Dict[str, Any]]:
        """Get field-level modification history."""
        return self.query_all('''
            SELECT mh.*, u.name as user_name
            FROM carpark_modification_history mh
            LEFT JOIN users u ON mh.changed_by = u.id
            WHERE mh.vehicle_id = %s
            ORDER BY mh.created_at DESC
            LIMIT %s
        ''', (vehicle_id, limit))

    # ── LOCATIONS ──

    def get_locations(self, company_id: int = None) -> List[Dict[str, Any]]:
        """List all active locations."""
        sql = 'SELECT * FROM carpark_locations WHERE is_active = TRUE'
        params = []
        if company_id:
            sql += ' AND company_id = %s'
            params.append(company_id)
        sql += ' ORDER BY name'
        return self.query_all(sql, tuple(params))

    def create_location(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new location."""
        return self.execute('''
            INSERT INTO carpark_locations (name, code, address, city, type, capacity, company_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        ''', (data['name'], data['code'], data.get('address'),
              data.get('city'), data.get('type'),
              data.get('capacity', 0), data.get('company_id')),
            returning=True)

    def update_location(self, location_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a location."""
        sets = []
        params = []
        for key in ('name', 'code', 'address', 'city', 'type', 'capacity', 'is_active'):
            if key in data:
                sets.append(f'{key} = %s')
                params.append(data[key])
        if not sets:
            return None
        params.append(location_id)
        return self.execute(
            f"UPDATE carpark_locations SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )
