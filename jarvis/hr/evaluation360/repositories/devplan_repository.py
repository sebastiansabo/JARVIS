"""Development-plan + check-in persistence."""
import json

from core.base_repository import BaseRepository


class DevplanRepository(BaseRepository):

    def get_for_participant(self, participant_id):
        return self.query_one(
            'SELECT * FROM eval_development_plans WHERE participant_id = %s', (participant_id,))

    def get_with_owner(self, plan_id):
        return self.query_one(
            '''SELECT dp.*, p.employee_id, p.cycle_id
               FROM eval_development_plans dp JOIN eval_participants p ON p.id = dp.participant_id
               WHERE dp.id = %s''', (plan_id,))

    def create(self, *, participant_id, goals, linked_competencies, status='active'):
        return self.execute(
            '''INSERT INTO eval_development_plans (participant_id, goals, linked_competencies, status)
               VALUES (%s, %s::jsonb, %s, %s) RETURNING *''',
            (participant_id, json.dumps(goals or []), linked_competencies or [], status),
            returning=True)

    def update(self, plan_id, *, goals, linked_competencies, status='active'):
        return self.execute(
            '''UPDATE eval_development_plans
               SET goals = %s::jsonb, linked_competencies = %s, status = %s, updated_at = CURRENT_TIMESTAMP
               WHERE id = %s RETURNING *''',
            (json.dumps(goals or []), linked_competencies or [], status, plan_id), returning=True)

    # ── check-ins ────────────────────────────────────────────────────
    def list_checkins(self, plan_id):
        return self.query_all(
            'SELECT * FROM eval_devplan_checkins WHERE plan_id = %s ORDER BY scheduled_date, id',
            (plan_id,))

    def add_checkin(self, plan_id, scheduled_date, note=None):
        return self.execute(
            '''INSERT INTO eval_devplan_checkins (plan_id, scheduled_date, note)
               VALUES (%s, %s, %s) RETURNING *''', (plan_id, scheduled_date, note), returning=True)

    def get_checkin_with_owner(self, checkin_id):
        return self.query_one(
            '''SELECT ci.*, dp.participant_id, p.employee_id, p.cycle_id
               FROM eval_devplan_checkins ci
               JOIN eval_development_plans dp ON dp.id = ci.plan_id
               JOIN eval_participants p ON p.id = dp.participant_id
               WHERE ci.id = %s''', (checkin_id,))

    def complete_checkin(self, checkin_id, note=None):
        return self.execute(
            '''UPDATE eval_devplan_checkins
               SET completed_at = CURRENT_TIMESTAMP, note = COALESCE(%s, note)
               WHERE id = %s AND completed_at IS NULL RETURNING *''',
            (note, checkin_id), returning=True)
