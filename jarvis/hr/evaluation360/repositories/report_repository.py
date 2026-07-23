"""Report persistence — pre-aggregated, anonymity-gated payloads only.

Raw individual responses never live here; ``aggregates_by_relationship`` is the
server-built, gated report. HR status reads (:func:`list_for_cycle`) return
completion/release flags only, never report content.
"""
import json

from core.base_repository import BaseRepository


class ReportRepository(BaseRepository):

    def upsert(self, *, cycle_id, participant_id, aggregates, gap_analysis, hidden_categories):
        return self.execute(
            '''INSERT INTO eval_reports
                 (cycle_id, participant_id, aggregates_by_relationship, gap_analysis, hidden_categories)
               VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
               ON CONFLICT (participant_id) DO UPDATE
                 SET aggregates_by_relationship = excluded.aggregates_by_relationship,
                     gap_analysis = excluded.gap_analysis,
                     hidden_categories = excluded.hidden_categories
               RETURNING *''',
            (cycle_id, participant_id, json.dumps(aggregates), json.dumps(gap_analysis),
             hidden_categories or []), returning=True,
        )

    def get(self, report_id):
        return self.query_one('SELECT * FROM eval_reports WHERE id = %s', (report_id,))

    def get_with_owner(self, report_id):
        """Report joined to its participant's employee_id (for ownership checks)."""
        return self.query_one(
            '''SELECT r.*, p.employee_id
               FROM eval_reports r JOIN eval_participants p ON p.id = r.participant_id
               WHERE r.id = %s''', (report_id,))

    def get_for_employee(self, cycle_id, employee_id):
        return self.query_one(
            '''SELECT r.*, p.employee_id
               FROM eval_reports r JOIN eval_participants p ON p.id = r.participant_id
               WHERE r.cycle_id = %s AND p.employee_id = %s''', (cycle_id, employee_id))

    def list_for_cycle(self, cycle_id):
        """HR status view — flags only, no report content."""
        return self.query_all(
            '''SELECT r.id, r.participant_id, p.employee_id, u.name AS employee_name,
                      (r.released_at IS NOT NULL) AS released,
                      (r.acknowledged_at IS NOT NULL) AS acknowledged,
                      (r.manager_summary IS NOT NULL) AS has_summary
               FROM eval_reports r
               JOIN eval_participants p ON p.id = r.participant_id
               JOIN users u ON u.id = p.employee_id
               WHERE r.cycle_id = %s
               ORDER BY u.name''', (cycle_id,))

    def release(self, report_id):
        return self.execute(
            'UPDATE eval_reports SET released_at = CURRENT_TIMESTAMP WHERE id = %s AND released_at IS NULL',
            (report_id,))

    def acknowledge(self, report_id):
        return self.execute(
            'UPDATE eval_reports SET acknowledged_at = CURRENT_TIMESTAMP WHERE id = %s', (report_id,))

    def set_manager_summary(self, report_id, summary):
        return self.execute(
            'UPDATE eval_reports SET manager_summary = %s WHERE id = %s', (summary, report_id))
