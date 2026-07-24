"""Reviewer nomination + assignment fan-out.

Relationships are derived from the organigram (manager, direct reports) plus
self-nominated peers. Manager/report resolvers are injected so the fan-out logic
is testable without the org schema; the defaults use the shared org utilities.
"""
from hr.evaluation360.repositories.assignment_repository import AssignmentRepository
from hr.evaluation360.repositories.event_repository import EvalEventRepository


def _default_reports_of(subject_id):
    """Direct reports of ``subject_id`` from the organigram (empty on any error)."""
    try:
        from core.organization.manager_utils import get_managed_employee_ids
        return get_managed_employee_ids(subject_id) or []
    except Exception:
        return []


def _default_manager_of(subject_id):
    """Best-effort manager lookup; returns None when unavailable. The concrete
    org query is wired at the route layer / a follow-up — kept injectable so the
    fan-out is deterministic in tests."""
    return None


def _default_peer_pool(subject_id, limit, exclude_ids):
    """Auto-nominated peers: preferentially the subject's Sincron org-node
    co-members (random sample), topped up from same-department colleagues when
    the subject isn't in the organigram or the node is too small. Injectable so
    the fan-out is deterministic in tests. Empty on any error."""
    try:
        from hr.evaluation360.repositories.cycle_repository import CycleRepository
        repo = CycleRepository()
        pool = repo.sincron_peer_pool(subject_id, limit=limit, exclude_ids=exclude_ids)
        if len(pool) < limit:
            seen = set(exclude_ids or []) | {p['id'] for p in pool}
            pool = pool + repo.peer_pool(subject_id, limit=limit - len(pool), exclude_ids=seen)
        return pool
    except Exception:
        return []


class NominationService:
    def __init__(self, assignment_repo=None, event_repo=None,
                 manager_resolver=None, reports_resolver=None, peer_pool_resolver=None):
        self.assignments = assignment_repo or AssignmentRepository()
        self.events = event_repo or EvalEventRepository()
        self._manager_of = manager_resolver or _default_manager_of
        self._reports_of = reports_resolver or _default_reports_of
        self._peer_pool = peer_pool_resolver or _default_peer_pool

    def fan_out(self, cycle_id, subject_id, peer_reviewer_ids=None, due_at=None, actor_id=None):
        """Create the self / manager / direct-report / peer assignments for one
        participant. Peers land in ``pending_approval`` (manager approval / 48h
        auto-approve); everyone else is ``invited`` immediately."""
        peer_reviewer_ids = peer_reviewer_ids or []
        created = []

        def _add(reviewer_id, relationship, source, status):
            row = self.assignments.create(
                cycle_id=cycle_id, subject_id=subject_id, reviewer_id=reviewer_id,
                relationship=relationship, source=source, status=status, due_at=due_at)
            self.events.emit('assignment.created', cycle_id=cycle_id, subject_id=subject_id,
                             assignment_id=row['id'], actor_id=actor_id,
                             payload={'relationship': relationship})
            created.append(row)

        _add(subject_id, 'self', 'hr_assigned', 'invited')
        manager_id = self._manager_of(subject_id)
        if manager_id:
            _add(manager_id, 'manager', 'hr_assigned', 'invited')
        for report_id in self._reports_of(subject_id):
            _add(report_id, 'direct_report', 'hr_assigned', 'invited')
        for peer_id in peer_reviewer_ids:
            _add(peer_id, 'peer', 'self_nominated', 'pending_approval')
        return created

    def generate_for_cycle(self, cycle_id, subject_ids, *, auto_peers=4, max_reports=4,
                           due_at=None, actor_id=None, skip_if_existing=True):
        """HR-driven fan-out for a whole cycle. For each participant creates the
        self review, the manager review (when resolvable), up to ``max_reports``
        direct-report reviews, and ``auto_peers`` peers auto-picked from the
        same-department pool. HR-assigned reviewers land ``invited`` immediately
        (no nomination round). Participants that already have assignments are
        skipped, so re-running is safe."""
        summary = {'subjects': 0, 'assignments': 0, 'skipped': 0}
        for sid in subject_ids:
            if skip_if_existing and self.assignments.list_by_subject(cycle_id, sid):
                summary['skipped'] += 1
                continue
            rows = self._fan_out_hr(cycle_id, sid, auto_peers, max_reports, due_at, actor_id)
            summary['subjects'] += 1
            summary['assignments'] += len(rows)
        return summary

    def _fan_out_hr(self, cycle_id, subject_id, auto_peers, max_reports, due_at, actor_id):
        created = []

        def _add(reviewer_id, relationship):
            row = self.assignments.create(
                cycle_id=cycle_id, subject_id=subject_id, reviewer_id=reviewer_id,
                relationship=relationship, source='hr_assigned', status='invited', due_at=due_at)
            self.events.emit('assignment.created', cycle_id=cycle_id, subject_id=subject_id,
                             assignment_id=row['id'], actor_id=actor_id,
                             payload={'relationship': relationship})
            created.append(row)

        _add(subject_id, 'self')
        used = {subject_id}

        manager_id = self._manager_of(subject_id)
        if manager_id and manager_id not in used:
            _add(manager_id, 'manager')
            used.add(manager_id)

        for rid in self._reports_of(subject_id):
            if len([c for c in created if c['relationship'] == 'direct_report']) >= max_reports:
                break
            if rid not in used:
                _add(rid, 'direct_report')
                used.add(rid)

        picked = 0
        for p in self._peer_pool(subject_id, auto_peers + len(used), used):
            if picked >= auto_peers:
                break
            pid = p['id'] if isinstance(p, dict) else p
            if pid in used:
                continue
            _add(pid, 'peer')
            used.add(pid)
            picked += 1
        return created

    # ── manual nomination (HR editor + employee self-nominate) ──────
    ACTIVE = ('pending_approval', 'invited', 'in_progress', 'submitted')

    def _peer_candidate_pool(self, subject_id, exclude_ids):
        """Full (non-random) org-node co-member pool a subject can nominate from,
        with a same-department top-up. Injected resolver in tests."""
        try:
            from hr.evaluation360.repositories.cycle_repository import CycleRepository
            repo = CycleRepository()
            pool = repo.sincron_peer_pool(subject_id, exclude_ids=exclude_ids, randomized=False)
            seen = set(exclude_ids) | {p['id'] for p in pool}
            pool = pool + repo.peer_pool(subject_id, exclude_ids=seen)
            return pool
        except Exception:
            return []

    def nomination_view(self, cycle_id, subject_id):
        """What the nomination editor needs for one subject: the reviewers already
        assigned (grouped) and the candidate peers still available to add."""
        rows = self.assignments.list_by_subject_named(cycle_id, subject_id)
        peers = [r for r in rows if r['relationship'] == 'peer' and r['status'] in self.ACTIVE]
        others = [r for r in rows if r['relationship'] != 'peer' and r['status'] in self.ACTIVE]
        used = {r['reviewer_id'] for r in rows if r['status'] in self.ACTIVE and r['reviewer_id']}
        used.add(subject_id)
        candidates = self._peer_candidate_pool(subject_id, used)
        return {'peers': peers, 'others': others, 'candidates': candidates}

    def set_peers(self, cycle_id, subject_id, peer_ids, actor_id=None,
                  status='invited', source='hr_assigned'):
        """Reconcile a subject's peer reviewers to ``peer_ids``: add the new ones,
        drop any current peer no longer listed (never a submitted one). Used by
        both the HR editor and employee self-nomination."""
        rows = self.assignments.list_by_subject(cycle_id, subject_id)
        active = [a for a in rows if a['status'] in self.ACTIVE]
        current_peers = {a['reviewer_id']: a for a in active if a['relationship'] == 'peer'}
        used_non_peer = {a['reviewer_id'] for a in active if a['relationship'] != 'peer'}
        desired = {p for p in peer_ids if p and p != subject_id and p not in used_non_peer}

        added, removed = [], []
        for pid in desired:
            if pid in current_peers:
                continue
            row = self.assignments.create(
                cycle_id=cycle_id, subject_id=subject_id, reviewer_id=pid,
                relationship='peer', source=source, status=status)
            self.events.emit('assignment.created', cycle_id=cycle_id, subject_id=subject_id,
                             assignment_id=row['id'], actor_id=actor_id,
                             payload={'relationship': 'peer', 'nominated': True})
            added.append(pid)
        for pid, a in current_peers.items():
            if pid not in desired and a['status'] != 'submitted':
                self.assignments.delete(a['id'])
                self.events.emit('assignment.removed', cycle_id=cycle_id, subject_id=subject_id,
                                 assignment_id=a['id'], actor_id=actor_id, payload={'reviewer_id': pid})
                removed.append(pid)
        return {'added': added, 'removed': removed,
                'peer_count': len(desired) if desired else len(current_peers) - len(removed)}

    def approve(self, assignment_id, actor_id=None):
        self.assignments.set_status(assignment_id, 'invited')
        self.events.emit('assignment.approved', assignment_id=assignment_id, actor_id=actor_id)
        return self.assignments.get(assignment_id)

    def auto_approve_stale(self, cycle_id, hours=48, actor_id=None):
        """Auto-approve peer nominations pending longer than ``hours``."""
        stale = self.assignments.stale_pending(cycle_id, hours)
        for a in stale:
            self.assignments.set_status(a['id'], 'invited')
            self.events.emit('assignment.approved', cycle_id=cycle_id, assignment_id=a['id'],
                             actor_id=actor_id, payload={'auto': True})
        return len(stale)

    def decline_and_replace(self, assignment_id, reason, replacement_reviewer_id, actor_id=None):
        """Decline an assignment and fan out a replacement of the same relationship."""
        original = self.assignments.get(assignment_id)
        if not original:
            raise ValueError('assignment not found')
        self.assignments.decline(assignment_id, reason)
        self.events.emit('assignment.declined', cycle_id=original['cycle_id'],
                         assignment_id=assignment_id, actor_id=actor_id,
                         payload={'reason': reason})
        replacement = self.assignments.create(
            cycle_id=original['cycle_id'], subject_id=original['subject_id'],
            reviewer_id=replacement_reviewer_id, relationship=original['relationship'],
            source='hr_assigned', status='invited', due_at=original.get('due_at'))
        self.assignments.mark_replaced(assignment_id, replacement['id'])
        self.events.emit('assignment.created', cycle_id=original['cycle_id'],
                         subject_id=original['subject_id'], assignment_id=replacement['id'],
                         actor_id=actor_id, payload={'replacement_of': assignment_id})
        return replacement
