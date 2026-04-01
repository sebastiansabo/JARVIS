"""Client Field Sales Repository — profiles, fleet, 360 view, search."""

import json
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.field_sales.client_repo')


class ClientFSRepository(BaseRepository):

    def get_or_create_profile(self, client_id):
        """Get client profile, creating a default one if it doesn't exist.

        Args:
            client_id: crm_clients.id

        Returns:
            dict: client_profiles row
        """
        profile = self.query_one(
            'SELECT * FROM client_profiles WHERE client_id = %s',
            (client_id,)
        )
        if profile:
            return profile

        # Create with defaults
        return self.execute('''
            INSERT INTO client_profiles (client_id)
            VALUES (%s)
            ON CONFLICT (client_id) DO UPDATE SET updated_at = NOW()
            RETURNING *
        ''', (client_id,), returning=True)

    def update_profile(self, client_id, data):
        """Update client profile fields.

        Args:
            client_id: crm_clients.id
            data: dict of fields to update

        Returns:
            dict: updated profile row, or None
        """
        if not data:
            return None

        # Ensure profile exists
        self.get_or_create_profile(client_id)

        allowed = {
            'client_type', 'industry', 'country_code', 'legal_form',
            'country_detected_from', 'assigned_kam_id', 'fleet_size',
            'renewal_score', 'last_scored_at', 'cui', 'anaf_data',
            'anaf_fetched_at', 'estimated_annual_value', 'priority',
        }

        fields = {k: v for k, v in data.items() if k in allowed}
        if not fields:
            return None

        sets = ', '.join(f'{k} = %s' for k in fields)
        vals = list(fields.values()) + [client_id]

        return self.execute(
            f'UPDATE client_profiles SET {sets}, updated_at = NOW() WHERE client_id = %s RETURNING *',
            tuple(vals),
            returning=True,
        )

    def get_fleet(self, client_id):
        """Get all fleet vehicles for a client.

        Args:
            client_id: crm_clients.id

        Returns:
            list of fleet vehicle dicts
        """
        return self.query_all('''
            SELECT * FROM client_fleet
            WHERE client_id = %s
            ORDER BY purchase_date DESC NULLS LAST, created_at DESC
        ''', (client_id,))

    def upsert_fleet_vehicle(self, data):
        """Insert a new fleet vehicle record.

        Args:
            data: dict with client_id and vehicle fields

        Returns:
            dict: created fleet row
        """
        return self.execute('''
            INSERT INTO client_fleet
                (client_id, vehicle_make, vehicle_model, vehicle_year, vin,
                 license_plate, sale_id, purchase_date, purchase_price,
                 purchase_currency, estimated_mileage, financing_type,
                 financing_expiry, warranty_expiry, status,
                 renewal_candidate, renewal_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        ''', (
            data['client_id'],
            data.get('vehicle_make'),
            data.get('vehicle_model'),
            data.get('vehicle_year'),
            data.get('vin'),
            data.get('license_plate'),
            data.get('sale_id'),
            data.get('purchase_date'),
            data.get('purchase_price'),
            data.get('purchase_currency', 'EUR'),
            data.get('estimated_mileage'),
            data.get('financing_type'),
            data.get('financing_expiry'),
            data.get('warranty_expiry'),
            data.get('status', 'active'),
            data.get('renewal_candidate', False),
            data.get('renewal_reason'),
        ), returning=True)

    def update_fleet_vehicle(self, vehicle_id, data):
        """Update an existing fleet vehicle.

        Args:
            vehicle_id: client_fleet.id
            data: dict of fields to update

        Returns:
            dict: updated fleet row, or None
        """
        allowed = {
            'vehicle_make', 'vehicle_model', 'vehicle_year', 'vin',
            'license_plate', 'sale_id', 'purchase_date', 'purchase_price',
            'purchase_currency', 'estimated_mileage', 'financing_type',
            'financing_expiry', 'warranty_expiry', 'status',
            'renewal_candidate', 'renewal_reason',
        }

        fields = {k: v for k, v in data.items() if k in allowed}
        if not fields:
            return None

        sets = ', '.join(f'{k} = %s' for k in fields)
        vals = list(fields.values()) + [vehicle_id]

        return self.execute(
            f'UPDATE client_fleet SET {sets}, updated_at = NOW() WHERE id = %s RETURNING *',
            tuple(vals),
            returning=True,
        )

    def get_last_purchases(self, client_id, limit=10):
        """Get recent purchases from crm_deals.

        Args:
            client_id: crm_clients.id
            limit: max rows

        Returns:
            list of deal dicts
        """
        return self.query_all('''
            SELECT id, source, brand, model_name, vin, sale_price_net,
                   contract_date, delivery_date, fuel_type, model_year,
                   dossier_status, buyer_name, dealer_name, color
            FROM crm_deals
            WHERE client_id = %s
            ORDER BY contract_date DESC NULLS LAST
            LIMIT %s
        ''', (client_id, limit))

    def get_last_interactions(self, client_id, limit=10):
        """Get recent interactions (visit notes) for a client.

        Since no separate interactions table exists, we query
        kam_visit_plans + kam_visit_notes.

        Args:
            client_id: crm_clients.id
            limit: max rows

        Returns:
            list of interaction dicts
        """
        return self.query_all('''
            SELECT vn.id, vn.raw_note, vn.structured_note, vn.created_at,
                   vp.planned_date, vp.visit_type, vp.status AS visit_status,
                   vp.outcome, u.name AS kam_name
            FROM kam_visit_notes vn
            JOIN kam_visit_plans vp ON vp.id = vn.visit_id
            JOIN users u ON u.id = vp.kam_id
            WHERE vp.client_id = %s
            ORDER BY vn.created_at DESC
            LIMIT %s
        ''', (client_id, limit))

    def get_visit_history(self, client_id, limit=10):
        """Get visit history for a client.

        Args:
            client_id: crm_clients.id
            limit: max rows

        Returns:
            list of visit dicts
        """
        return self.query_all('''
            SELECT vp.id, vp.planned_date, vp.planned_time, vp.visit_type,
                   vp.status, vp.outcome, vp.goals, vp.checkin_at,
                   vp.checkout_at, u.name AS kam_name,
                   (SELECT COUNT(*) FROM kam_visit_notes n WHERE n.visit_id = vp.id) AS note_count
            FROM kam_visit_plans vp
            JOIN users u ON u.id = vp.kam_id
            WHERE vp.client_id = %s
            ORDER BY vp.planned_date DESC
            LIMIT %s
        ''', (client_id, limit))

    def update_renewal_score(self, client_id, score):
        """Update renewal score on client profile.

        Args:
            client_id: crm_clients.id
            score: integer 0-100

        Returns:
            int: affected rows
        """
        return self.execute('''
            UPDATE client_profiles
            SET renewal_score = %s, last_scored_at = NOW(), updated_at = NOW()
            WHERE client_id = %s
        ''', (score, client_id))

    def search_clients(self, query, limit=20):
        """Search clients by name, company, or nr_reg.

        Uses ILIKE for name_normalized and company_name, exact for nr_reg.

        Args:
            query: search string
            limit: max results

        Returns:
            list of client dicts with profile info
        """
        if not query or not query.strip():
            return []

        search_term = f'%{query.strip().lower()}%'

        return self.query_all('''
            SELECT c.id, c.display_name, c.company_name, c.phone, c.email,
                   c.city, c.nr_reg, c.client_type,
                   cp.priority, cp.renewal_score, cp.fleet_size,
                   cp.assigned_kam_id, cp.cui,
                   u.name AS kam_name
            FROM crm_clients c
            LEFT JOIN client_profiles cp ON cp.client_id = c.id
            LEFT JOIN users u ON u.id = cp.assigned_kam_id
            WHERE c.merged_into_id IS NULL
              AND (c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL)
              AND (
                  c.name_normalized ILIKE %s
                  OR c.company_name ILIKE %s
                  OR c.nr_reg = %s
                  OR cp.cui = %s
              )
            ORDER BY c.display_name ASC
            LIMIT %s
        ''', (search_term, search_term, query.strip(), query.strip(), limit))

    def get_360(self, client_id):
        """Build a comprehensive 360-degree client view.

        Each sub-section is in its own try/except to never fail the whole view.

        Args:
            client_id: crm_clients.id

        Returns:
            dict with profile, fleet, purchases, interactions, visit_history,
            renewal_candidates, fiscal sections (null on error for each)
        """
        result = {
            'client': None,
            'profile': None,
            'fleet': None,
            'purchases': None,
            'interactions': None,
            'visit_history': None,
            'renewal_candidates': None,
            'fiscal': None,
        }

        # Client base data
        try:
            result['client'] = self.query_one(
                'SELECT * FROM crm_clients WHERE id = %s',
                (client_id,)
            )
        except Exception as e:
            logger.error('360 client base failed for %s: %s', client_id, str(e))

        # Profile
        try:
            result['profile'] = self.get_or_create_profile(client_id)
        except Exception as e:
            logger.error('360 profile failed for %s: %s', client_id, str(e))

        # Fleet
        try:
            fleet = self.get_fleet(client_id)
            result['fleet'] = fleet
            result['renewal_candidates'] = [
                v for v in (fleet or []) if v.get('renewal_candidate')
            ]
        except Exception as e:
            logger.error('360 fleet failed for %s: %s', client_id, str(e))

        # Purchases
        try:
            result['purchases'] = self.get_last_purchases(client_id, limit=10)
        except Exception as e:
            logger.error('360 purchases failed for %s: %s', client_id, str(e))

        # Interactions (visit notes)
        try:
            result['interactions'] = self.get_last_interactions(client_id, limit=10)
        except Exception as e:
            logger.error('360 interactions failed for %s: %s', client_id, str(e))

        # Visit history
        try:
            result['visit_history'] = self.get_visit_history(client_id, limit=10)
        except Exception as e:
            logger.error('360 visit_history failed for %s: %s', client_id, str(e))

        # Fiscal / ANAF data
        try:
            profile = result.get('profile') or {}
            anaf_data = profile.get('anaf_data')
            if anaf_data:
                if isinstance(anaf_data, str):
                    result['fiscal'] = json.loads(anaf_data)
                elif isinstance(anaf_data, dict):
                    result['fiscal'] = anaf_data
        except Exception as e:
            logger.error('360 fiscal failed for %s: %s', client_id, str(e))

        return result

    def get_managed_clients(self, priority=None, country_code=None,
                            min_renewal_score=None, assigned_kam_id=None,
                            limit=50, offset=0):
        """Get clients with profiles for manager overview, with filtering.

        Args:
            priority: optional filter (low/medium/high)
            country_code: optional filter (RO/DE/HU/etc.)
            min_renewal_score: optional minimum score
            assigned_kam_id: optional filter by assigned KAM
            limit: max results
            offset: pagination offset

        Returns:
            tuple: (list of client dicts, total count)
        """
        conditions = [
            'c.merged_into_id IS NULL',
            '(c.is_blacklisted = FALSE OR c.is_blacklisted IS NULL)',
        ]
        params = []

        if priority:
            conditions.append('cp.priority = %s')
            params.append(priority)
        if country_code:
            conditions.append('cp.country_code = %s')
            params.append(country_code)
        if min_renewal_score is not None:
            conditions.append('cp.renewal_score >= %s')
            params.append(int(min_renewal_score))
        if assigned_kam_id:
            conditions.append('cp.assigned_kam_id = %s')
            params.append(int(assigned_kam_id))

        where = ' AND '.join(conditions)
        count_params = tuple(params)

        params.extend([limit, offset])

        rows = self.query_all(f'''
            SELECT c.id, c.display_name, c.company_name, c.phone, c.city,
                   cp.priority, cp.renewal_score, cp.fleet_size,
                   cp.country_code, cp.client_type, cp.cui,
                   cp.assigned_kam_id,
                   u.name AS kam_name
            FROM crm_clients c
            JOIN client_profiles cp ON cp.client_id = c.id
            LEFT JOIN users u ON u.id = cp.assigned_kam_id
            WHERE {where}
            ORDER BY cp.renewal_score DESC NULLS LAST, c.display_name ASC
            LIMIT %s OFFSET %s
        ''', tuple(params))

        count_row = self.query_one(f'''
            SELECT COUNT(*) AS count
            FROM crm_clients c
            JOIN client_profiles cp ON cp.client_id = c.id
            WHERE {where}
        ''', count_params)

        return rows, count_row['count'] if count_row else 0
