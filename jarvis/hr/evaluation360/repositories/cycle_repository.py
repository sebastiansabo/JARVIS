"""Review-cycle and participant persistence."""
import json

from core.base_repository import BaseRepository


class CycleRepository(BaseRepository):
    """CRUD for eval_cycles + eval_participants."""

    def create(self, *, name, template_id, population_filter, timeline,
               anonymity_policy=None, reminder_policy=None,
               release_policy='manager_gated', created_by=None):
        timeline = timeline or {}
        return self.execute(
            '''INSERT INTO eval_cycles
                 (name, template_id, population_filter, nomination_start, review_start,
                  review_end, calibration_end, release_at, anonymity_policy,
                  reminder_policy, release_policy, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
            (name, template_id, json.dumps(population_filter or {}),
             timeline.get('nomination_start'), timeline.get('review_start'),
             timeline.get('review_end'), timeline.get('calibration_end'),
             timeline.get('release_at'), json.dumps(anonymity_policy or {'min_n': 3}),
             json.dumps(reminder_policy or {}), release_policy, created_by),
            returning=True,
        )

    def get(self, cycle_id):
        return self.query_one('SELECT * FROM eval_cycles WHERE id = %s', (cycle_id,))

    def list(self):
        return self.query_all('SELECT * FROM eval_cycles ORDER BY created_at DESC')

    def set_status(self, cycle_id, status):
        return self.execute(
            'UPDATE eval_cycles SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
            (status, cycle_id),
        )

    def add_participant(self, cycle_id, employee_id):
        return self.execute(
            '''INSERT INTO eval_participants (cycle_id, employee_id)
               VALUES (%s, %s) ON CONFLICT (cycle_id, employee_id) DO NOTHING RETURNING *''',
            (cycle_id, employee_id), returning=True,
        )

    def list_participants(self, cycle_id):
        return self.query_all(
            'SELECT * FROM eval_participants WHERE cycle_id = %s ORDER BY id', (cycle_id,))

    def list_participants_named(self, cycle_id):
        """Participants joined to their user name + peer-reviewer count — for the
        HR nomination editor (status only)."""
        return self.query_all(
            '''SELECT p.employee_id, u.name, u.department,
                      (SELECT COUNT(*) FROM eval_assignments a
                        WHERE a.cycle_id = p.cycle_id AND a.subject_id = p.employee_id
                          AND a.relationship = 'peer'
                          AND a.status IN ('pending_approval','invited','in_progress','submitted')) AS peer_count
               FROM eval_participants p
               JOIN users u ON u.id = p.employee_id
               WHERE p.cycle_id = %s
               ORDER BY u.name''',
            (cycle_id,))

    def participant_cycles(self, employee_id):
        """Cycles where this user is a participant and nomination is still open
        (draft/nomination/active) — drives the employee's self-nominate entry."""
        return self.query_all(
            '''SELECT c.id, c.name, c.status,
                      (SELECT COUNT(*) FROM eval_assignments a
                        WHERE a.cycle_id = c.id AND a.subject_id = %s
                          AND a.relationship = 'peer'
                          AND a.status IN ('pending_approval','invited','in_progress','submitted')) AS peer_count
               FROM eval_participants p
               JOIN eval_cycles c ON c.id = p.cycle_id
               WHERE p.employee_id = %s
                 AND c.status IN ('draft','nomination','active')
               ORDER BY c.created_at DESC''',
            (employee_id, employee_id))

    def get_participant(self, cycle_id, employee_id):
        return self.query_one(
            'SELECT * FROM eval_participants WHERE cycle_id = %s AND employee_id = %s',
            (cycle_id, employee_id))

    def eligible_peer_count(self, employee_id):
        """Count active colleagues in the same department (excludes self) — the
        pool from which peers can be nominated. Used by the A7 dry-run check."""
        row = self.query_one(
            '''SELECT COUNT(*) AS n FROM users u
               WHERE u.is_active = TRUE
                 AND u.id <> %s
                 AND u.department IS NOT NULL
                 AND u.department = (SELECT department FROM users WHERE id = %s)''',
            (employee_id, employee_id),
        )
        return (row or {}).get('n', 0)

    def peer_pool(self, employee_id, limit=None, exclude_ids=None):
        """Same-department active colleagues (excludes self and ``exclude_ids``),
        as the id/name rows an assignment fan-out can pick peers from."""
        params = [employee_id, employee_id]
        extra = ''
        if exclude_ids:
            extra = ' AND u.id <> ALL(%s)'
            params.append(list(exclude_ids))
        sql = (
            '''SELECT u.id, u.name FROM users u
               WHERE u.is_active = TRUE
                 AND u.id <> %s
                 AND u.department IS NOT NULL
                 AND u.department = (SELECT department FROM users WHERE id = %s)'''
            + extra + ' ORDER BY u.name')
        if limit:
            sql += ' LIMIT %s'
            params.append(limit)
        return self.query_all(sql, tuple(params))

    def sincron_peer_pool(self, employee_id, limit=None, exclude_ids=None, randomized=True):
        """Peers drawn from the subject's *Sincron org node(s)* — active JARVIS
        users who share at least one org node with the subject (resolved through
        the mapped Sincron employee). Random order by default so a large team
        doesn't always yield the same alphabetical few."""
        params = [employee_id, employee_id]
        extra = ''
        if exclude_ids:
            extra = ' AND u.id <> ALL(%s)'
            params.append(list(exclude_ids))
        order = 'RANDOM()' if randomized else 'name'
        sql = (
            '''WITH subj_emp AS (
                   SELECT sincron_employee_id, company_name
                   FROM sincron_employees WHERE mapped_jarvis_user_id = %s
               ),
               subj_nodes AS (
                   SELECT DISTINCT m.node_id
                   FROM sincron_org_members m
                   JOIN subj_emp s ON s.sincron_employee_id = m.sincron_employee_id
                                  AND s.company_name = m.company_name
               )
               SELECT id, name FROM (
                   SELECT DISTINCT u.id, u.name
                   FROM sincron_org_members m
                   JOIN subj_nodes sn ON sn.node_id = m.node_id
                   JOIN sincron_employees se ON se.sincron_employee_id = m.sincron_employee_id
                                            AND se.company_name = m.company_name
                   JOIN users u ON u.id = se.mapped_jarvis_user_id
                   WHERE u.is_active = TRUE AND u.id <> %s''' + extra
            + f'''
               ) x ORDER BY {order}''')
        if limit:
            sql += ' LIMIT %s'
            params.append(limit)
        return self.query_all(sql, tuple(params))

    # ── population picker (cycle builder) ────────────────────────────
    def list_eligible_employees(self, search=None, department=None, limit=200):
        """Active users for the population picker, with department for grouping."""
        clauses = ['u.is_active = TRUE']
        params = []
        if search:
            clauses.append('u.name ILIKE %s')
            params.append(f'%{search}%')
        if department:
            clauses.append('u.department = %s')
            params.append(department)
        params.append(limit)
        return self.query_all(
            f'''SELECT u.id, u.name, u.department, u.company_id
                FROM users u
                WHERE {" AND ".join(clauses)}
                ORDER BY u.department NULLS LAST, u.name
                LIMIT %s''',
            tuple(params))

    # ── Sincron organigram as a population source ────────────────────
    def sincron_org_tree(self):
        """The Sincron org tree (nodes across companies). ``member_count`` is the
        distinct count of active JARVIS users under the node *and its descendants*
        — i.e. exactly how many participants selecting the node would add."""
        return self.query_all(
            '''WITH RECURSIVE node_anc AS (
                   -- map every node to itself and each of its ancestors
                   SELECT id AS node_id, id AS anc_id FROM sincron_org_nodes
                   UNION ALL
                   SELECT na.node_id, n.parent_id
                   FROM node_anc na JOIN sincron_org_nodes n ON n.id = na.anc_id
                   WHERE n.parent_id IS NOT NULL
               ),
               elig AS (
                   SELECT m.node_id, se.mapped_jarvis_user_id AS uid
                   FROM sincron_org_members m
                   JOIN sincron_employees se
                     ON se.sincron_employee_id = m.sincron_employee_id
                    AND se.company_name = m.company_name
                   JOIN users u ON u.id = se.mapped_jarvis_user_id
                   WHERE u.is_active = TRUE
               )
               SELECT n.id, n.company_id, c.company AS company_name, n.parent_id,
                      n.name, n.node_type, n.level, n.display_order,
                      COUNT(DISTINCT e.uid) AS member_count
               FROM sincron_org_nodes n
               JOIN companies c ON c.id = n.company_id
               LEFT JOIN node_anc na ON na.anc_id = n.id        -- n + all descendants
               LEFT JOIN elig e ON e.node_id = na.node_id
               GROUP BY n.id, n.company_id, c.company, n.parent_id,
                        n.name, n.node_type, n.level, n.display_order
               ORDER BY c.company, n.level, n.display_order, n.name''')

    def sincron_org_node_members(self, node_id):
        """Active JARVIS users under a node *and its descendants*, resolved via
        Sincron member → mapped_jarvis_user_id. Shaped like list_eligible_employees."""
        return self.query_all(
            '''WITH RECURSIVE sub AS (
                   SELECT id FROM sincron_org_nodes WHERE id = %s
                   UNION ALL
                   SELECT n.id FROM sincron_org_nodes n JOIN sub ON n.parent_id = sub.id
               )
               SELECT DISTINCT u.id, u.name, u.department, u.company_id
               FROM sincron_org_members m
               JOIN sub ON sub.id = m.node_id
               JOIN sincron_employees se
                 ON se.sincron_employee_id = m.sincron_employee_id
                AND se.company_name = m.company_name
               JOIN users u ON u.id = se.mapped_jarvis_user_id
               WHERE u.is_active = TRUE
               ORDER BY u.name''',
            (node_id,))

    def list_departments(self):
        rows = self.query_all(
            '''SELECT department, COUNT(*) AS n FROM users
               WHERE is_active = TRUE AND department IS NOT NULL AND department <> ''
               GROUP BY department ORDER BY department''')
        return [{'department': r['department'], 'count': r['n']} for r in rows]

    def employee_ids_for_filter(self, *, departments=None, company_ids=None):
        """Resolve a population_filter to a concrete set of active employee ids."""
        clauses = ['is_active = TRUE']
        params = []
        if departments:
            clauses.append('department = ANY(%s)')
            params.append(list(departments))
        if company_ids:
            clauses.append('company_id = ANY(%s)')
            params.append(list(company_ids))
        rows = self.query_all(
            f'SELECT id FROM users WHERE {" AND ".join(clauses)} ORDER BY id',
            tuple(params))
        return [r['id'] for r in rows]
