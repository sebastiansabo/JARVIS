"""Cycle lifecycle: creation, guarded state transitions, dry-run validation,
and status-only progress aggregation (never response content)."""
from hr.evaluation360.domain import state_machine as sm
from hr.evaluation360.repositories.cycle_repository import CycleRepository
from hr.evaluation360.repositories.assignment_repository import AssignmentRepository
from hr.evaluation360.repositories.event_repository import EvalEventRepository

MAX_REVIEWER_LOAD = 8   # indicator A6
MIN_ELIGIBLE_PEERS = 3  # indicator A7


class CycleError(Exception):
    """Raised when a cycle operation violates a business rule."""


class CycleService:
    def __init__(self, cycle_repo=None, assignment_repo=None, event_repo=None):
        self.cycles = cycle_repo or CycleRepository()
        self.assignments = assignment_repo or AssignmentRepository()
        self.events = event_repo or EvalEventRepository()

    # ── creation ────────────────────────────────────────────────────
    def create_cycle(self, data, created_by):
        cycle = self.cycles.create(
            name=data['name'],
            template_id=data.get('template_id'),
            population_filter=data.get('population_filter', {}),
            timeline=data.get('timeline', {}),
            anonymity_policy=data.get('anonymity_policy'),
            reminder_policy=data.get('reminder_policy'),
            release_policy=data.get('release_policy', 'manager_gated'),
            created_by=created_by,
        )
        for emp_id in data.get('participant_ids', []):
            self.cycles.add_participant(cycle['id'], emp_id)
        self.events.emit('cycle.created', cycle_id=cycle['id'], actor_id=created_by)
        return cycle

    # ── dry-run validation (A6 / A7) ────────────────────────────────
    def dry_run(self, cycle_id):
        """Health checks. A7 (participants with < 3 eligible peers) is *blocking*
        for draft→nomination; A6 (reviewer load > 8) is a warning that blocks
        auto-approve, not the transition."""
        overloaded = [
            {'reviewer_id': r['reviewer_id'], 'load': r['load']}
            for r in self.assignments.reviewer_load(cycle_id)
            if r['load'] > MAX_REVIEWER_LOAD
        ]
        missing_peers = []
        for p in self.cycles.list_participants(cycle_id):
            pool = self.cycles.eligible_peer_count(p['employee_id'])
            if pool < MIN_ELIGIBLE_PEERS:
                missing_peers.append({'employee_id': p['employee_id'], 'eligible_peers': pool})
        return {
            'overloaded_reviewers': overloaded,
            'participants_missing_peers': missing_peers,
            'blocking': bool(missing_peers),
        }

    # ── guarded transition ──────────────────────────────────────────
    def transition(self, cycle_id, target, actor_id, waive_blocking=False):
        cycle = self.cycles.get(cycle_id)
        if not cycle:
            raise CycleError('cycle not found')
        # State machine raises InvalidTransition on an illegal move.
        sm.assert_transition(cycle['status'], target)
        # A7 gate: draft → nomination is blocked until resolved or explicitly waived.
        if target == sm.NOMINATION:
            report = self.dry_run(cycle_id)
            if report['blocking'] and not waive_blocking:
                raise CycleError(
                    'dry-run blocking: %d participant(s) with < %d eligible peers'
                    % (len(report['participants_missing_peers']), MIN_ELIGIBLE_PEERS))
        self.cycles.set_status(cycle_id, target)
        self.events.emit(f'cycle.{target}', cycle_id=cycle_id, actor_id=actor_id)
        return self.cycles.get(cycle_id)

    # ── progress (status only) ──────────────────────────────────────
    def progress(self, cycle_id):
        counts = self.assignments.status_counts(cycle_id)
        submitted = counts.get('submitted', 0)
        # Total excludes dropped (declined/replaced) work from the denominator.
        total = sum(n for s, n in counts.items() if s not in ('declined', 'replaced'))
        completion = round(submitted / total * 100, 1) if total else 0.0
        return {
            'completion_pct': completion,
            'submitted': submitted,
            'total': total,
            'by_status': counts,
            'declines_pending': counts.get('declined', 0),
        }
