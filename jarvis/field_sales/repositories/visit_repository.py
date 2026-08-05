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
                  planned_end_time, visit_type, goals, company_id

        Returns:
            dict: created visit row
        """
        return self.execute('''
            INSERT INTO kam_visit_plans
                (kam_id, client_id, planned_date, planned_time, planned_end_time, visit_type, goals, company_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        ''', (
            data['kam_id'],
            data['client_id'],
            data['planned_date'],
            data.get('planned_time'),
            data.get('planned_end_time'),
            data.get('visit_type', 'general'),
            data.get('goals'),
            data.get('company_id'),
        ), returning=True)

    def update_visit(self, visit_id, data):
        """Update editable visit fields.

        Args:
            visit_id: kam_visit_plans.id
            data: dict with optional keys: planned_date, planned_time, planned_end_time, visit_type, goals,
                  status, outcome, pre_visit_data, post_visit_data, contact_person, companions

        Returns:
            dict: updated visit or None
        """
        import json as _json
        sets = []
        params = []
        for field in ('planned_date', 'planned_time', 'planned_end_time', 'visit_type', 'goals', 'status', 'outcome', 'contact_person'):
            if field in data:
                sets.append(f'{field} = %s')
                params.append(data[field])
        for field in ('pre_visit_data', 'post_visit_data'):
            if field in data:
                sets.append(f'{field} = %s::jsonb')
                val = data[field]
                params.append(_json.dumps(val) if isinstance(val, dict) else val)
        if 'companions' in data:
            sets.append('companions = %s')
            params.append(data['companions'])
        if not sets:
            return self.query_one('SELECT * FROM kam_visit_plans WHERE id = %s', (visit_id,))
        sets.append('updated_at = NOW()')
        params.append(visit_id)
        return self.execute(f'''
            UPDATE kam_visit_plans
            SET {', '.join(sets)}
            WHERE id = %s
            RETURNING *
        ''', tuple(params), returning=True)

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

    def create_route(self, data):
        """Create a visit route with multiple stops.

        Args:
            data: dict with kam_id, planned_date, name, created_by, stops[],
                  company_id (tenant tag applied to every stop)

        Returns:
            dict: created route with visit list
        """
        route = self.execute('''
            INSERT INTO kam_visit_routes (kam_id, planned_date, name, created_by)
            VALUES (%s, %s, %s, %s)
            RETURNING *
        ''', (
            data['kam_id'],
            data['planned_date'],
            data.get('name'),
            data.get('created_by'),
        ), returning=True)

        route_id = route['id']
        company_id = data.get('company_id')
        visits = []
        for i, stop in enumerate(data.get('stops', [])):
            visit = self.execute('''
                INSERT INTO kam_visit_plans
                    (kam_id, client_id, planned_date, planned_time, visit_type, goals, route_id, sequence, company_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            ''', (
                data['kam_id'],
                stop['client_id'],
                data['planned_date'],
                stop.get('planned_time'),
                stop.get('visit_type', 'general'),
                stop.get('goals'),
                route_id,
                i + 1,
                company_id,
            ), returning=True)
            visits.append(visit)

        route['visits'] = visits
        return route

    def get_routes(self, date_from, date_to, kam_id=None):
        """Get routes in a date range, optionally filtered by KAM.

        Args:
            date_from: start date YYYY-MM-DD
            date_to: end date YYYY-MM-DD
            kam_id: optional filter

        Returns:
            list of route dicts with stop count and KAM name
        """
        params = [date_from, date_to]
        kam_filter = ''
        if kam_id:
            kam_filter = 'AND r.kam_id = %s'
            params.append(kam_id)

        return self.query_all(f'''
            SELECT r.*,
                   u.name AS kam_name,
                   (SELECT COUNT(*) FROM kam_visit_plans v WHERE v.route_id = r.id) AS stop_count
            FROM kam_visit_routes r
            JOIN users u ON u.id = r.kam_id
            WHERE r.planned_date >= %s AND r.planned_date <= %s
            {kam_filter}
            ORDER BY r.planned_date DESC, r.created_at DESC
        ''', tuple(params))

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
                   (SELECT COUNT(*) FROM kam_visit_notes n WHERE n.visit_id = v.id) AS note_count,
                   r.name AS route_name
            FROM kam_visit_plans v
            JOIN crm_clients c ON c.id = v.client_id
            JOIN users u ON u.id = v.kam_id
            LEFT JOIN client_profiles cp ON cp.client_id = v.client_id
            LEFT JOIN kam_visit_routes r ON r.id = v.route_id
            WHERE v.planned_date >= %s AND v.planned_date <= %s
            {kam_filter}
            ORDER BY v.planned_date ASC,
                     v.route_id ASC NULLS LAST,
                     v.sequence ASC,
                     v.planned_time ASC NULLS LAST
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

    # ═══════════════════════════════════════════════════════════
    # Task methods
    # ═══════════════════════════════════════════════════════════

    def get_tasks_for_visit(self, visit_id):
        """Get all tasks for a visit with follow-up counts."""
        return self.query_all('''
            SELECT t.*,
                   u.name AS assigned_to_name,
                   cu.name AS created_by_name,
                   (SELECT COUNT(*) FROM kam_task_follow_ups f WHERE f.task_id = t.id) AS follow_up_count
            FROM kam_visit_tasks t
            LEFT JOIN users u ON u.id = t.assigned_to
            LEFT JOIN users cu ON cu.id = t.created_by
            WHERE t.visit_id = %s
            ORDER BY t.due_date ASC NULLS LAST, t.created_at ASC
        ''', (visit_id,))

    def create_task(self, data):
        """Create a visit task."""
        return self.execute('''
            INSERT INTO kam_visit_tasks (visit_id, description, assigned_to, due_date, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        ''', (
            data['visit_id'],
            data['description'],
            data.get('assigned_to'),
            data.get('due_date'),
            data.get('created_by'),
        ), returning=True)

    def update_task(self, task_id, data):
        """Update a task (status, description, due_date)."""
        sets = []
        params = []
        for field in ('description', 'due_date', 'assigned_to'):
            if field in data:
                sets.append(f'{field} = %s')
                params.append(data[field])
        if 'status' in data:
            sets.append('status = %s')
            params.append(data['status'])
            if data['status'] == 'completed':
                sets.append('completed_at = NOW()')
            else:
                sets.append('completed_at = NULL')
        if not sets:
            return self.query_one('SELECT * FROM kam_visit_tasks WHERE id = %s', (task_id,))
        sets.append('updated_at = NOW()')
        params.append(task_id)
        return self.execute(f'''
            UPDATE kam_visit_tasks
            SET {', '.join(sets)}
            WHERE id = %s
            RETURNING *
        ''', tuple(params), returning=True)

    def get_task_by_id(self, task_id):
        """Get a single task."""
        return self.query_one('SELECT * FROM kam_visit_tasks WHERE id = %s', (task_id,))

    def get_follow_ups(self, task_id):
        """Get follow-up entries for a task."""
        return self.query_all('''
            SELECT f.*, u.name AS created_by_name
            FROM kam_task_follow_ups f
            LEFT JOIN users u ON u.id = f.created_by
            WHERE f.task_id = %s
            ORDER BY f.created_at ASC
        ''', (task_id,))

    def add_follow_up(self, task_id, note, created_by):
        """Add a follow-up note to a task."""
        return self.execute('''
            INSERT INTO kam_task_follow_ups (task_id, note, created_by)
            VALUES (%s, %s, %s)
            RETURNING *
        ''', (task_id, note, created_by), returning=True)

    def get_pending_tasks(self, user_id):
        """Get all pending tasks assigned to a user, across all visits."""
        return self.query_all('''
            SELECT t.*,
                   v.planned_date, v.visit_type,
                   c.display_name AS client_name,
                   cu.name AS created_by_name,
                   (SELECT COUNT(*) FROM kam_task_follow_ups f WHERE f.task_id = t.id) AS follow_up_count
            FROM kam_visit_tasks t
            JOIN kam_visit_plans v ON v.id = t.visit_id
            JOIN crm_clients c ON c.id = v.client_id
            LEFT JOIN users cu ON cu.id = t.created_by
            WHERE t.assigned_to = %s AND t.status IN ('pending', 'in_progress')
            ORDER BY t.due_date ASC NULLS LAST, t.created_at ASC
        ''', (user_id,))
