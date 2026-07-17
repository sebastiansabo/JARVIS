"""Data access for fp_vehicles table (foi de parcurs vehicle stock)."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.foi_parcurs.vehicle_repository')


class FPVehicleRepository(BaseRepository):

    _SELECT = (
        'SELECT v.*, c.company AS company_name '
        'FROM fp_vehicles v '
        'LEFT JOIN companies c ON c.id = v.company_id'
    )

    def get_all(self, active_only=True):
        """Get all vehicles, optionally filtered by active status."""
        if active_only:
            return self.query_all(
                f'{self._SELECT} WHERE v.is_active = TRUE ORDER BY v.mark, v.model, v.vin'
            )
        return self.query_all(f'{self._SELECT} ORDER BY v.mark, v.model, v.vin')

    def get_by_vin(self, vin):
        """Get a single vehicle by VIN."""
        return self.query_one('SELECT * FROM fp_vehicles WHERE vin = %s', (vin,))

    def get_by_id(self, vehicle_id):
        """Get a single vehicle by ID."""
        return self.query_one('SELECT * FROM fp_vehicles WHERE id = %s', (vehicle_id,))

    def create(self, data):
        """Insert a new vehicle."""
        return self.execute(
            '''INSERT INTO fp_vehicles
               (vin, registration_number, car_id, mark, brand, model, color,
                fuel_type, fuel_tank_capacity_liters, battery_capacity_kwh, odometer_km, company_id,
                vignette_valid_until, itp_valid_until, insurance_valid_until,
                insurance_doc, talon_doc, civ_doc, registration_doc, offer_doc)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *''',
            (data['vin'], data.get('registration_number'), data.get('car_id'),
             data['mark'], data.get('brand'), data['model'], data.get('color'),
             data.get('fuel_type', 'Diesel'),
             data.get('fuel_tank_capacity_liters'),
             data.get('battery_capacity_kwh'),
             data.get('odometer_km'),
             data.get('company_id'),
             data.get('vignette_valid_until'), data.get('itp_valid_until'),
             data.get('insurance_valid_until'), data.get('insurance_doc'),
             data.get('talon_doc'), data.get('civ_doc'), data.get('registration_doc'),
             data.get('offer_doc')),
            returning=True,
        )

    def update(self, vehicle_id, data):
        """Update a vehicle."""
        sets = []
        params = []
        for col in ('vin', 'registration_number', 'car_id', 'mark', 'brand', 'model', 'color',
                    'fuel_type', 'fuel_tank_capacity_liters', 'battery_capacity_kwh', 'odometer_km',
                    'company_id', 'is_active',
                    'vignette_valid_until', 'itp_valid_until', 'insurance_valid_until',
                    'insurance_doc', 'talon_doc', 'civ_doc', 'registration_doc', 'offer_doc'):
            if col in data:
                sets.append(f'{col} = %s')
                params.append(data[col])
        if not sets:
            return None
        sets.append('updated_at = NOW()')
        params.append(vehicle_id)
        sql = f"UPDATE fp_vehicles SET {', '.join(sets)} WHERE id = %s RETURNING *"
        return self.execute(sql, tuple(params), returning=True)

    def delete(self, vehicle_id):
        """Soft-delete (set is_active=FALSE)."""
        return self.execute(
            'UPDATE fp_vehicles SET is_active = FALSE, updated_at = NOW() WHERE id = %s',
            (vehicle_id,),
        )
