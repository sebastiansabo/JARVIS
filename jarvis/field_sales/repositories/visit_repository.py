"""Visit Repository — CRUD and queries for kam_visit_plans and kam_visit_notes."""

from core.base_repository import BaseRepository


class VisitRepository(BaseRepository):

    def get_by_kam_and_date(self, kam_id, date):
        """Get all visits for a KAM on a specific date.

        Args:
            kam_id: users.id
            date: date string YYYY-MM-DD

        Returns:
            list of visit dicts with client_name and renewal_score
        """
        return self.query_all('''
            SELECT v.*,
                   c.display_name AS client_name,
                   c.phone AS client_phone,
                   c.city AS client_city,
                   cp.renewal_score,
                   cp.priority AS client_priority,
                   cp.fleet_size,
                   (SELECT COUNT(*) FROM kam_visit_notes n WHERE n.visit_id = v.id) AS note_count
            FROM kam_visit_plans v
            JOIN crm_clients c ON c.id = v.client_id
            LEFT JOIN client_profiles cp ON cp.client_id = v.client_id
            WHERE v.kam_id = %s AND v.planned_date = %s
            ORDER BY v.planned_time ASC NULLS LAST, v.created_at ASC
        ''', (kam_id, date))

    def get_by_id(self, visit_id):
        """Get a single visit with full details including notes.

        Args:
            visit_id: kam_visit_plans.id

        Returns:
            dict with visit, client, profile, and latest note data, or None
        """
        visit = self.query_one('''
            SELECT v.*,
                   c.display_name AS client_name,
                   c.phone AS client_phone,
                   c.email AS client_email,
                   c.city AS client_city,
                   c.company_name AS client_company,
                   cp.renewal_score,
                   cp.priority AS client_priority,
                   cp.fleet_size,
                   cp.client_type AS profile_client_type,
                   cp.cui,
                   cp.industry
            FROM kam_visit_plans v
            JOIN crm_clients c ON c.id = v.client_id
            LEFT JOIN client_profiles cp ON cp.client_id = v.client_id
            WHERE v.id = %s
        ''', (visit_id,))

        if not visit:
            return None

        # Attach notes
        notes = self.query_all('''
            SELECT id, raw_note, structured_note, structured_at, created_at
            FROM kam_visit_notes
            WHERE visit_id = %s
            ORDER BY created_at DESC
        ''', (visit_id,))
        visit['notes'] = notes

        return visit

    def create(self, data):
        """Create a new visit plan.

        Args:
            data: dict with kam_id, client_id, planned_date, planned_time,
                  visit_type, goals

        Returns:
            dict: created visit row
        """
        return self.execute('''
            INSERT INTO kam_visit_plans
                (kam_id, client_id, planned_date, planned_time, visit_type, goals)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        ''', (
            data['kam_id'],
            data['client_id'],
            data['planned_date'],
            data.get('planned_time'),
            data.get('visit_type', 'general'),
            data.get('goals'),
        ), returning=True)

    def update_status(self, visit_id, status):
        """Update visit status.

        Args:
            visit_id: kam_visit_plans.id
            status: new status string

        Returns:
            dict: updated visit or None
        """
        return self.execute('''
            UPDATE kam_visit_plans
            SET status = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING *
        ''', (status, visit_id), returning=True)

    def checkin(self, visit_id, lat=None, lng=None):
        """Mark visit as checked-in with optional GPS coordinates.

        Args:
            visit_id: kam_visit_plans.id
            lat: latitude (optional)
            lng: longitude (optional)

        Returns:
            dict: updated visit or None
        """
        return self.execute('''
            UPDATE kam_visit_plans
            SET checkin_at = NOW(),
                status = 'in_progress',
                checkin_lat = %s,
                checkin_lng = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
        ''', (lat, lng, visit_id), returning=True)

    def complete(self, visit_id, outcome):
        """Mark visit as completed with outcome.

        Args:
            visit_id: kam_visit_plans.id
            outcome: outcome string (e.g., 'positive', 'neutral', 'negative')

        Returns:
            dict: updated visit or None
        """
        return self.execute('''
            UPDATE kam_visit_plans
            SET status = 'completed',
                outcome = %s,
                checkout_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
        ''', (outcome, visit_id), returning=True)

    def update_brief(self, visit_id, brief):
        """Store AI-generated visit brief.

        Args:
            visit_id: kam_visit_plans.id
            brief: AI brief text

        Returns:
            dict: updated visit or None
        """
        return self.execute('''
            UPDATE kam_visit_plans
            SET ai_brief = %s,
                ai_brief_generated_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
        ''', (brief, visit_id), returning=True)

    def add_note(self, visit_id, raw_note, structured_note=None):
        """Add a note to a visit.

        Args:
            visit_id: kam_visit_plans.id
            raw_note: raw text note
            structured_note: optional JSONB structured note

        Returns:
            dict: created note row
        """
        import json
        structured_json = None
        structured_at = None
        if structured_note:
            structured_json = json.dumps(structured_note) if isinstance(structured_note, dict) else structured_note
            structured_at = 'NOW()'

        if structured_note:
            return self.execute('''
                INSERT INTO kam_visit_notes (visit_id, raw_note, structured_note, structured_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                RETURNING *
            ''', (visit_id, raw_note, structured_json), returning=True)
        else:
            return self.execute('''
                INSERT INTO kam_visit_notes (visit_id, raw_note)
                VALUES (%s, %s)
                RETURNING *
            ''', (visit_id, raw_note), returning=True)

    def update_note_structured(self, note_id, structured_note):
        """Update structured note after AI processing.

        Args:
            note_id: kam_visit_notes.id
            structured_note: JSONB structured note dict

        Returns:
            dict: updated note or None
        """
        import json
        structured_json = json.dumps(structured_note) if isinstance(structured_note, dict) else structured_note
        return self.execute('''
            UPDATE kam_visit_notes
            SET structured_note = %s::jsonb,
                structured_at = NOW()
            WHERE id = %s
            RETURNING *
        ''', (structured_json, note_id), returning=True)

    def get_team_visits(self, date_from, date_to, kam_id=None):
        """Get all visits in a date range, optionally filtered by KAM.

        Args:
            date_from: start date string YYYY-MM-DD
            date_to: end date string YYYY-MM-DD
            kam_id: optional users.id to filter by specific KAM

        Returns:
            list of visit dicts with client and KAM names
        """
        params = [date_from, date_to]
        kam_filter = ''
        if kam_id:
            kam_filter = 'AND v.kam_id = %s'
            params.append(kam_id)

        return self.query_all(f'''
            SELECT v.*,
                   c.display_name AS client_name,
                   c.city AS client_city,
                   u.name AS kam_name,
                   cp.renewal_score,
                   cp.priority AS client_priority,
                   (SELECT COUNT(*) FROM kam_visit_notes n WHERE n.visit_id = v.id) AS note_count
            FROM kam_visit_plans v
            JOIN crm_clients c ON c.id = v.client_id
            JOIN users u ON u.id = v.kam_id
            LEFT JOIN client_profiles cp ON cp.client_id = v.client_id
            WHERE v.planned_date >= %s AND v.planned_date <= %s
            {kam_filter}
            ORDER BY v.planned_date ASC, v.planned_time ASC NULLS LAST
        ''', tuple(params))

    def get_client_context(self, visit_id):
        """Get full context needed by AI service for a visit.

        Joins visit + client + profile + fleet + recent notes to build
        a comprehensive context dict for AI brief generation.

        Args:
            visit_id: kam_visit_plans.id

        Returns:
            dict with all context, or None if visit not found
        """
        # Visit + client + profile
        visit = self.query_one('''
            SELECT v.id AS visit_id, v.visit_type, v.goals, v.planned_date,
                   c.id AS client_id, c.display_name, c.phone, c.email,
                   c.city, c.company_name, c.nr_reg,
                   cp.client_type, cp.industry, cp.country_code,
                   cp.fleet_size, cp.renewal_score, cp.priority,
                   cp.cui, cp.anaf_data, cp.estimated_annual_value,
                   cp.assigned_kam_id
            FROM kam_visit_plans v
            JOIN crm_clients c ON c.id = v.client_id
            LEFT JOIN client_profiles cp ON cp.client_id = v.client_id
            WHERE v.id = %s
        ''', (visit_id,))

        if not visit:
            return None

        client_id = visit['client_id']

        # Fleet
        fleet = self.query_all('''
            SELECT vehicle_make, vehicle_model, vehicle_year, vin,
                   license_plate, purchase_date, financing_type,
                   financing_expiry, warranty_expiry, status,
                   renewal_candidate, renewal_reason
            FROM client_fleet
            WHERE client_id = %s
            ORDER BY purchase_date DESC NULLS LAST
        ''', (client_id,))

        # Renewal candidates
        renewal_candidates = [f for f in fleet if f.get('renewal_candidate')]

        # Recent purchases (from crm_deals)
        purchases = self.query_all('''
            SELECT brand, model_name, sale_price_net, contract_date,
                   delivery_date, fuel_type, vin, dossier_status
            FROM crm_deals
            WHERE client_id = %s
            ORDER BY contract_date DESC NULLS LAST
            LIMIT 10
        ''', (client_id,))

        # Recent visit notes
        recent_notes = self.query_all('''
            SELECT vn.raw_note, vn.structured_note, vn.created_at,
                   vp.planned_date, vp.visit_type, vp.outcome
            FROM kam_visit_notes vn
            JOIN kam_visit_plans vp ON vp.id = vn.visit_id
            WHERE vp.client_id = %s AND vp.id != %s
            ORDER BY vn.created_at DESC
            LIMIT 5
        ''', (client_id, visit_id))

        # Visit history
        visit_history = self.query_all('''
            SELECT planned_date, visit_type, status, outcome,
                   checkin_at, checkout_at
            FROM kam_visit_plans
            WHERE client_id = %s AND id != %s
            ORDER BY planned_date DESC
            LIMIT 10
        ''', (client_id, visit_id))

        # ANAF / fiscal data
        fiscal = None
        if visit.get('anaf_data'):
            import json
            if isinstance(visit['anaf_data'], str):
                try:
                    fiscal = json.loads(visit['anaf_data'])
                except (json.JSONDecodeError, TypeError):
                    fiscal = None
            elif isinstance(visit['anaf_data'], dict):
                fiscal = visit['anaf_data']

        return {
            'visit': {
                'id': visit['visit_id'],
                'type': visit['visit_type'],
                'goals': visit['goals'],
                'planned_date': str(visit['planned_date']) if visit.get('planned_date') else None,
            },
            'profile': {
                'display_name': visit.get('display_name'),
                'company_name': visit.get('company_name'),
                'client_type': visit.get('client_type'),
                'industry': visit.get('industry'),
                'country_code': visit.get('country_code'),
                'fleet_size': visit.get('fleet_size', 0),
                'renewal_score': visit.get('renewal_score', 0),
                'priority': visit.get('priority'),
                'estimated_annual_value': float(visit['estimated_annual_value']) if visit.get('estimated_annual_value') else None,
                'phone': visit.get('phone'),
                'email': visit.get('email'),
                'city': visit.get('city'),
            },
            'fleet': fleet,
            'renewal_candidates': renewal_candidates,
            'purchases': purchases,
            'visit_history': visit_history,
            'recent_notes': recent_notes,
            'fiscal': fiscal,
        }
