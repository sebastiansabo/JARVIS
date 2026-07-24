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
