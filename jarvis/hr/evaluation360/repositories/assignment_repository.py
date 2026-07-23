"""Reviewer-assignment persistence + status aggregation (status only — this
layer never exposes response content)."""
from core.base_repository import BaseRepository

# Assignment states that still count as "live" work (not dropped).
ACTIVE_STATES = ('pending_approval', 'invited', 'in_progress', 'submitted')


class AssignmentRepository(BaseRepository):
    """CRUD + aggregates for eval_assignments."""

    def create(self, *, cycle_id, subject_id, relationship, reviewer_id=None,
               external_email=None, source='hr_assigned', status='invited', due_at=None):
        return self.execute(
            '''INSERT INTO eval_assignments
                 (cycle_id, subject_id, reviewer_id, external_email, relationship,
                  source, status, due_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
            (cycle_id, subject_id, reviewer_id, external_email, relationship,
             source, status, due_at), returning=True,
        )

    def get(self, assignment_id):
        return self.query_one('SELECT * FROM eval_assignments WHERE id = %s', (assignment_id,))

    def list_by_cycle(self, cycle_id):
        return self.query_all(
            'SELECT * FROM eval_assignments WHERE cycle_id = %s ORDER BY id', (cycle_id,))

    def list_by_subject(self, cycle_id, subject_id):
        return self.query_all(
            'SELECT * FROM eval_assignments WHERE cycle_id = %s AND subject_id = %s ORDER BY id',
            (cycle_id, subject_id))

    def set_status(self, assignment_id, status):
        return self.execute(
            'UPDATE eval_assignments SET status = %s WHERE id = %s', (status, assignment_id))

    def decline(self, assignment_id, reason):
        return self.execute(
            "UPDATE eval_assignments SET status = 'declined', decline_reason = %s WHERE id = %s",
            (reason, assignment_id))

    def mark_replaced(self, assignment_id, replaced_by_id):
        return self.execute(
            "UPDATE eval_assignments SET status = 'replaced', replaced_by_id = %s WHERE id = %s",
            (replaced_by_id, assignment_id))

    def status_counts(self, cycle_id):
        """{status: count} across all assignments in the cycle."""
        rows = self.query_all(
            'SELECT status, COUNT(*) AS n FROM eval_assignments WHERE cycle_id = %s GROUP BY status',
            (cycle_id,))
        return {r['status']: r['n'] for r in rows}

    def reviewer_load(self, cycle_id):
        """[{reviewer_id, load}] — count of live assignments per reviewer."""
        return self.query_all(
            '''SELECT reviewer_id, COUNT(*) AS load
               FROM eval_assignments
               WHERE cycle_id = %s AND reviewer_id IS NOT NULL
                 AND status IN ('pending_approval', 'invited', 'in_progress', 'submitted')
               GROUP BY reviewer_id''',
            (cycle_id,))

    def peer_counts_by_subject(self, cycle_id):
        """[{subject_id, peers}] — nominated peer assignments per participant."""
        return self.query_all(
            '''SELECT subject_id, COUNT(*) AS peers
               FROM eval_assignments
               WHERE cycle_id = %s AND relationship = 'peer'
                 AND status IN ('pending_approval', 'invited', 'in_progress', 'submitted')
               GROUP BY subject_id''',
            (cycle_id,))

    def stale_pending(self, cycle_id, hours):
        """Peer nominations awaiting approval longer than ``hours`` (48h auto-approve)."""
        return self.query_all(
            '''SELECT * FROM eval_assignments
               WHERE cycle_id = %s AND status = 'pending_approval'
                 AND created_at < (CURRENT_TIMESTAMP - (%s || ' hours')::interval)''',
            (cycle_id, str(hours)))
