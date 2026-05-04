"""Connecteam connector data access — users, form submissions."""

import json
from core.base_repository import BaseRepository


class ConnecteamRepository(BaseRepository):
    """CRUD for connecteam_users and connecteam_form_submissions."""

    # ── User operations ──

    def upsert_user(self, connecteam_user_id, name=None, email=None, phone=None):
        """Insert or update a Connecteam user record."""
        return self.execute('''
            INSERT INTO connecteam_users
                (connecteam_user_id, connecteam_user_name, connecteam_email, connecteam_phone)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (connecteam_user_id) DO UPDATE SET
                connecteam_user_name = COALESCE(EXCLUDED.connecteam_user_name, connecteam_users.connecteam_user_name),
                connecteam_email = COALESCE(EXCLUDED.connecteam_email, connecteam_users.connecteam_email),
                connecteam_phone = COALESCE(EXCLUDED.connecteam_phone, connecteam_users.connecteam_phone),
                updated_at = NOW()
            RETURNING id, connecteam_user_id, mapped_jarvis_user_id
        ''', (connecteam_user_id, name, email, phone), returning=True)

    def get_all_users(self, active_only=True):
        """Get all Connecteam users with mapping info."""
        query = '''
            SELECT cu.id, cu.connecteam_user_id, cu.connecteam_user_name,
                   cu.connecteam_email, cu.connecteam_phone,
                   cu.mapped_jarvis_user_id, cu.mapping_method,
                   cu.mapping_confidence, cu.is_active,
                   cu.created_at, cu.updated_at,
                   u.name AS mapped_jarvis_user_name
            FROM connecteam_users cu
            LEFT JOIN users u ON u.id = cu.mapped_jarvis_user_id
            WHERE 1=1
        '''
        params = []
        if active_only:
            query += ' AND cu.is_active = TRUE'
        query += ' ORDER BY cu.connecteam_user_name'
        return self.query_all(query, tuple(params))

    def update_user_mapping(self, connecteam_user_id, jarvis_user_id, method='manual'):
        """Manually map a Connecteam user to a JARVIS user."""
        return self.execute('''
            UPDATE connecteam_users
            SET mapped_jarvis_user_id = %s,
                mapping_method = %s,
                mapping_confidence = 100,
                updated_at = NOW()
            WHERE connecteam_user_id = %s
        ''', (jarvis_user_id, method, connecteam_user_id))

    def remove_user_mapping(self, connecteam_user_id):
        """Remove mapping for a Connecteam user."""
        return self.execute('''
            UPDATE connecteam_users
            SET mapped_jarvis_user_id = NULL,
                mapping_method = NULL,
                mapping_confidence = 0,
                updated_at = NOW()
            WHERE connecteam_user_id = %s
        ''', (connecteam_user_id,))

    def auto_map_by_name(self):
        """Auto-map Connecteam users to JARVIS users by name match."""
        return self.execute('''
            UPDATE connecteam_users cu
            SET mapped_jarvis_user_id = u.id,
                mapping_method = 'name',
                mapping_confidence = 80,
                updated_at = NOW()
            FROM users u
            WHERE LOWER(TRIM(cu.connecteam_user_name)) = LOWER(TRIM(u.name))
              AND cu.mapped_jarvis_user_id IS NULL
              AND cu.connecteam_user_name IS NOT NULL
              AND COALESCE(u.contract_status, 'active') != 'closed'
        ''')

    # ── Submission operations ──

    def get_submissions_by_jarvis_user(self, jarvis_user_id, year=None, month=None):
        """Get leave permission submissions for a JARVIS user."""
        query = '''
            SELECT cfs.id, cfs.submission_id, cfs.form_id, cfs.form_name,
                   cfs.connecteam_user_id, cfs.mapped_jarvis_user_id,
                   cfs.submission_timestamp::text,
                   cfs.leave_date::text, cfs.leave_start_time::text,
                   cfs.leave_end_time::text, cfs.leave_hours,
                   cfs.leave_reason, cfs.leave_destination, cfs.approved_by,
                   cfs.status, cfs.event_type, cfs.entry_num,
                   cfs.received_at::text, cfs.created_at::text,
                   cu.connecteam_user_name
            FROM connecteam_form_submissions cfs
            LEFT JOIN connecteam_users cu ON cu.connecteam_user_id = cfs.connecteam_user_id
            WHERE cfs.mapped_jarvis_user_id = %s
        '''
        params = [jarvis_user_id]
        if year:
            query += ' AND EXTRACT(YEAR FROM cfs.leave_date) = %s'
            params.append(year)
        if month:
            query += ' AND EXTRACT(MONTH FROM cfs.leave_date) = %s'
            params.append(month)
        query += ' ORDER BY cfs.leave_date DESC, cfs.submission_timestamp DESC'
        return self.query_all(query, tuple(params))

    def get_recent_submissions(self, limit=50, year=None, month=None):
        """Get submissions across all users, optionally filtered by year/month."""
        query = '''
            SELECT cfs.id, cfs.submission_id, cfs.form_id, cfs.form_name,
                   cfs.connecteam_user_id, cfs.mapped_jarvis_user_id,
                   cfs.submission_timestamp::text,
                   cfs.leave_date::text, cfs.leave_start_time::text,
                   cfs.leave_end_time::text, cfs.leave_hours,
                   cfs.leave_reason, cfs.leave_destination, cfs.approved_by,
                   cfs.status, cfs.event_type, cfs.entry_num,
                   cfs.received_at::text, cfs.created_at::text,
                   cu.connecteam_user_name,
                   u.name AS jarvis_user_name,
                   u.company AS jarvis_user_company
            FROM connecteam_form_submissions cfs
            LEFT JOIN connecteam_users cu ON cu.connecteam_user_id = cfs.connecteam_user_id
            LEFT JOIN users u ON u.id = cfs.mapped_jarvis_user_id
            WHERE 1=1
        '''
        params = []
        if year:
            query += ' AND EXTRACT(YEAR FROM cfs.leave_date) = %s'
            params.append(year)
        if month:
            query += ' AND EXTRACT(MONTH FROM cfs.leave_date) = %s'
            params.append(month)
        query += ' ORDER BY cfs.leave_date DESC, cfs.entry_num DESC LIMIT %s'
        params.append(limit)
        return self.query_all(query, tuple(params))

    def update_submissions_mapping(self, connecteam_user_id, jarvis_user_id):
        """Update mapped_jarvis_user_id on all submissions for a Connecteam user."""
        return self.execute('''
            UPDATE connecteam_form_submissions
            SET mapped_jarvis_user_id = %s, updated_at = NOW()
            WHERE connecteam_user_id = %s
        ''', (jarvis_user_id, connecteam_user_id))

    # ── Approvers ──

    def get_approvers_for_user(self, user_id):
        """Walk UP the structure tree to collect responsables above the user.

        Returns list of {id, name} dicts. Falls back to company L0 responsables,
        then to all L0 responsables if the user has no structure node assignment.
        """
        def _work(cursor):
            # 1. Find user's structure node assignments
            cursor.execute('''
                SELECT sn.id AS node_id, sn.company_id
                FROM structure_node_members snm
                JOIN structure_nodes sn ON snm.node_id = sn.id
                WHERE snm.user_id = %s
                ORDER BY sn.level DESC
            ''', (user_id,))
            assignments = cursor.fetchall()

            approver_ids = set()

            if assignments:
                for a in assignments:
                    node_id = a['node_id'] if isinstance(a, dict) else a[0]
                    cursor.execute('''
                        WITH RECURSIVE ancestors AS (
                            SELECT id, parent_id FROM structure_nodes WHERE id = %s
                            UNION ALL
                            SELECT sn.id, sn.parent_id
                            FROM structure_nodes sn
                            JOIN ancestors a ON sn.id = a.parent_id
                        )
                        SELECT DISTINCT snm.user_id
                        FROM ancestors a
                        JOIN structure_node_members snm ON snm.node_id = a.id
                        WHERE snm.role = 'responsable'
                          AND snm.user_id != %s
                    ''', (node_id, user_id))
                    for row in cursor.fetchall():
                        approver_ids.add(row['user_id'] if isinstance(row, dict) else row[0])

            # 2. Fallback: L0 company responsables
            if not approver_ids:
                cursor.execute('''
                    SELECT DISTINCT cr.user_id
                    FROM company_responsables cr
                    JOIN structure_node_members snm ON snm.user_id = %s
                    JOIN structure_nodes sn ON snm.node_id = sn.id
                    WHERE cr.company_id = sn.company_id
                      AND cr.user_id != %s
                ''', (user_id, user_id))
                for row in cursor.fetchall():
                    approver_ids.add(row['user_id'] if isinstance(row, dict) else row[0])

            # 3. If still empty, get all L0 responsables
            if not approver_ids:
                cursor.execute('''
                    SELECT DISTINCT cr.user_id
                    FROM company_responsables cr
                    WHERE cr.user_id != %s
                ''', (user_id,))
                for row in cursor.fetchall():
                    approver_ids.add(row['user_id'] if isinstance(row, dict) else row[0])

            # 4. Fetch names
            if not approver_ids:
                return []
            cursor.execute('''
                SELECT id, name FROM users
                WHERE id = ANY(%s)
                ORDER BY name
            ''', (list(approver_ids),))
            return [
                {'id': r['id'] if isinstance(r, dict) else r[0],
                 'name': r['name'] if isinstance(r, dict) else r[1]}
                for r in cursor.fetchall()
            ]

        return self.execute_many(_work)

    # ── Stats ──

    def get_stats(self):
        """Get connector statistics."""
        return self.query_one('''
            SELECT
                (SELECT COUNT(*) FROM connecteam_users WHERE is_active = TRUE) AS total_users,
                (SELECT COUNT(*) FROM connecteam_users
                 WHERE mapped_jarvis_user_id IS NOT NULL AND is_active = TRUE) AS mapped_users,
                (SELECT COUNT(*) FROM connecteam_users
                 WHERE mapped_jarvis_user_id IS NULL AND is_active = TRUE) AS unmapped_users,
                (SELECT COUNT(*) FROM connecteam_form_submissions) AS total_submissions,
                (SELECT MAX(created_at)::text FROM connecteam_form_submissions) AS last_import_at
        ''')
