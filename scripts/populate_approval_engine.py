#!/usr/bin/env python3
"""Populate JARVIS Jira board with Universal Approval Engine epic, tasks, and subtasks."""

import json
import os
import subprocess
import sys
import time

DOMAIN = "autoworldro.atlassian.net"
EMAIL = "sebastian.sabo@autoworld.ro"
TOKEN = os.environ['JIRA_API_TOKEN']
PROJECT = "JAR"

WORKSTREAM = 10285   # Epic
ACTIVITATE = 10286   # Story/Task
SUBTASK = 10287      # Subtask


def jira(method, endpoint, data=None):
    cmd = ["curl", "-s", "-X", method,
           f"https://{DOMAIN}/rest/api/3{endpoint}",
           "-u", f"{EMAIL}:{TOKEN}",
           "-H", "Content-Type: application/json"]
    if data:
        cmd.extend(["-d", json.dumps(data)])
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        print(f"  ERROR: {r.stdout[:200]}")
        return {}


def create_issue(issue_type_id, summary, description, parent_key=None, labels=None, start_date=None, due_date=None):
    desc_blocks = [b for b in description.split("\n\n") if b.strip()]
    fields = {
        "project": {"key": PROJECT},
        "issuetype": {"id": str(issue_type_id)},
        "summary": summary,
        "description": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": block}]} for block in desc_blocks]
        },
        "labels": labels or ["claude-code", "approval-engine"],
    }
    if parent_key:
        fields["parent"] = {"key": parent_key}
    if start_date:
        fields["customfield_10015"] = start_date
    if due_date:
        fields["duedate"] = due_date
    result = jira("POST", "/issue", {"fields": fields})
    key = result.get("key")
    if key:
        print(f"  Created {key}: {summary}")
    else:
        print(f"  FAILED: {summary} -> {json.dumps(result)[:200]}")
    return key


def transition_issue(issue_key, target_status):
    """Transition an issue to the target status (e.g., 'To Do', 'In Progress', 'Done', 'Backlog')."""
    t = jira("GET", f"/issue/{issue_key}/transitions")
    for tr in t.get("transitions", []):
        if tr["name"].lower() == target_status.lower() or tr["to"]["name"].lower() == target_status.lower():
            jira("POST", f"/issue/{issue_key}/transitions", {"transition": {"id": tr["id"]}})
            print(f"    -> {issue_key} transitioned to {target_status}")
            return True
    print(f"    -> {issue_key} could NOT transition to {target_status} (available: {[tr['name'] for tr in t.get('transitions', [])]})")
    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EPIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("━━━ Creating Epic ━━━")
epic_key = create_issue(
    WORKSTREAM,
    "Universal Approval Engine",
    "Entity-agnostic approval workflow engine for JARVIS. Configuration-driven flows with ordered steps, "
    "condition-based routing, delegation, escalation, and audit logging.\n\n"
    "Consuming modules (Accounting, e-Factura, HR, future Marketing/Procurement) submit entities for approval "
    "via the engine — the engine never imports from consuming modules.\n\n"
    "Tech: Flask blueprint, raw SQL repositories, APScheduler, React 19 + shadcn/ui.\n\n"
    "6 DB tables: approval_flows, approval_steps, approval_requests, approval_decisions, approval_audit_log, approval_delegations.\n\n"
    "Plan: memory/APPROVAL_ENGINE.md",
    start_date="2026-02-17",
    due_date="2026-04-30"
)
time.sleep(0.3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TASKS (one per phase)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

tasks = [
    {
        "id": "A1",
        "summary": "Phase A1: Core Engine (Backend)",
        "desc": (
            "Database schema (5 tables), ConditionEvaluator, repositories, ApprovalEngine service, "
            "and hooks system.\n\n"
            "Tables: approval_flows, approval_steps, approval_requests, approval_decisions, approval_audit_log\n\n"
            "Engine methods: submit(), decide(), cancel(), get_pending_for_user(), get_history_for_entity()\n\n"
            "Files: jarvis/core/approvals/ (engine.py, condition_eval.py, hooks.py, repositories/)"
        ),
        "status": "To Do",
        "subtasks": [
            ("Add 5 approval tables to init_schema.py",
             "CREATE TABLE IF NOT EXISTS for: approval_flows, approval_steps, approval_requests, "
             "approval_decisions, approval_audit_log. Integer serial PKs, TEXT+CHECK for statuses, "
             "JSONB for conditions/context/details. All indexes."),
            ("Implement ConditionEvaluator",
             "Pure function evaluating JSONB conditions against context dict. Operators: _gte, _gt, "
             "_lte, _lt, _eq, _neq, _in, _not_in, _exists, _contains, bare key = exact equality. "
             "All conditions AND'd. File: condition_eval.py"),
            ("Create FlowRepository",
             "CRUD for approval_flows + approval_steps. get_active_flows_for_entity_type(), "
             "get_flow_with_steps(). Standard try/finally + release_db pattern."),
            ("Create RequestRepository",
             "CRUD for approval_requests. get_pending_for_step(), get_by_entity(), update_status(), "
             "advance_step(). Queue query: join steps+flows for user's pending items."),
            ("Create DecisionRepository + AuditRepository",
             "DecisionRepo: create_decision(), get_decisions_for_request(). "
             "AuditRepo: log_action() (append-only), get_audit_for_request()."),
            ("Implement ApprovalEngine orchestrator",
             "submit(): find matching flow, check auto-approve, create request, advance to first step. "
             "decide(): validate authorization, record decision, evaluate step completion, advance or reject. "
             "cancel(): only requester/admin. Internal: _find_matching_flow(), _advance_to_next_step(), "
             "_resolve_approvers(), _check_auto_approve()."),
            ("Implement hooks system",
             "Simple callback registry: on(event_type, callback), fire(event_type, payload). "
             "Events: approval.submitted/decided/approved/rejected/cancelled/escalated/expired. "
             "Error handling per callback (log, don't crash)."),
            ("Seed permissions_v2 for approvals module",
             "8 permissions: queue.access, queue.decide, requests.submit, requests.view_all, "
             "flows.view, flows.manage, delegations.manage, audit.view. "
             "Defaults: Admin=all, Manager=5, User=3."),
            ("Write unit tests for engine + condition evaluator",
             "ConditionEvaluator: all operators, edge cases, empty conditions. "
             "Engine: submit (match/no-match/auto-approve/already-pending), decide (approve/reject/unauthorized), "
             "cancel. Full flow: submit->approve step 1->approve step 2->approved."),
        ]
    },
    {
        "id": "A2",
        "summary": "Phase A2: API Routes",
        "desc": (
            "Flask blueprint with all REST endpoints. Request CRUD, queue, flow admin, audit.\n\n"
            "Endpoints: ~20 routes under /approvals/api/\n\n"
            "Files: jarvis/core/approvals/routes.py, __init__.py (blueprint)\n\n"
            "Register blueprint in app.py."
        ),
        "status": "Backlog",
        "subtasks": [
            ("Create approvals blueprint + register in app.py",
             "Blueprint in core/approvals/__init__.py. Register in app.py with url_prefix='/approvals'."),
            ("Request endpoints: submit, list, detail, decide, cancel",
             "POST /api/requests (submit), GET /api/requests (list with filters), "
             "GET /api/requests/<id> (detail+decisions+audit), POST /api/requests/<id>/decide, "
             "POST /api/requests/<id>/cancel. All @login_required."),
            ("Queue endpoints: my-queue, count, my-requests",
             "GET /api/my-queue (pending for current user), GET /api/my-queue/count (badge number), "
             "GET /api/my-requests (submitted by current user). Efficient queries."),
            ("Flow admin endpoints: CRUD + step management",
             "GET/POST /api/flows, GET/PUT/DELETE /api/flows/<id>. "
             "POST/PUT/DELETE /api/flows/<id>/steps, PATCH reorder. Admin permission required."),
            ("Audit endpoint + global audit (admin)",
             "GET /api/requests/<id>/audit (per-request). GET /api/audit (global, filterable by date/actor/action). "
             "Admin-only for global audit."),
            ("Write API integration tests",
             "All endpoints return correct status codes. Permission enforcement. "
             "Pagination and filtering. Error responses."),
        ]
    },
    {
        "id": "A3",
        "summary": "Phase A3: Frontend — Queue + Request Detail",
        "desc": (
            "React pages for the approval workflow: queue page, request detail dialog, sidebar badge.\n\n"
            "Files: types/approvals.ts, api/approvals.ts, pages/Approvals/index.tsx, "
            "pages/Approvals/RequestDetail.tsx, components/ApprovalBadge.tsx\n\n"
            "Stack: React Query, shadcn/ui, Lucide icons, Tailwind 4."
        ),
        "status": "Backlog",
        "subtasks": [
            ("Create TypeScript types + API client",
             "types/approvals.ts: ApprovalFlow, ApprovalStep, ApprovalRequest, ApprovalDecision, "
             "ApprovalQueueItem, ApprovalDelegation, AuditEntry, enums for status/decision/priority. "
             "api/approvals.ts: approvalsApi object with all endpoint methods."),
            ("Build ApprovalQueue page",
             "Main page at /app/approvals. Card-based list of pending decisions. "
             "Filter by entity_type, priority. Sort by priority/waiting time/due date. "
             "Quick-action Approve/Reject buttons. Tabs: My Queue | My Requests. "
             "React Query with 30s polling."),
            ("Build RequestDetail dialog",
             "Dialog opened from queue click. Frozen context display. Decision timeline. "
             "Current step highlighted. Action buttons: Approve/Reject/Return/Delegate/Escalate. "
             "Comment field (required on reject/return). Conditions key-value editor."),
            ("Build ApprovalBadge component",
             "Sidebar badge showing pending count. Polls /my-queue/count every 60s. "
             "Click navigates to /app/approvals. Zero count = hidden badge."),
            ("Add route + sidebar navigation",
             "Add /app/approvals route to React Router. Add Approvals item to Sidebar with badge. "
             "Lucide CheckSquare icon."),
        ]
    },
    {
        "id": "A4",
        "summary": "Phase A4: Delegations + Scheduler",
        "desc": (
            "Delegation system for vacation coverage. Scheduler jobs for timeouts, reminders, expirations.\n\n"
            "New table: approval_delegations\n\n"
            "Engine additions: escalate(), resubmit(), process_timeouts(), process_reminders(), process_expirations()\n\n"
            "4 new APScheduler jobs in tasks/cleanup.py"
        ),
        "status": "Backlog",
        "subtasks": [
            ("Add approval_delegations table",
             "Schema: delegator_id, delegate_id, entity_type (nullable), flow_id (nullable), "
             "starts_at, ends_at, reason, is_active. Indexes on delegate_id and active+dates."),
            ("Create DelegationRepository + routes",
             "CRUD repo. Routes: GET/POST/DELETE /api/delegations. "
             "Only delegator or admin can manage. Include delegate in approver resolution."),
            ("Implement escalate() + resubmit() on engine",
             "escalate(): move to escalation_step or escalation_user. "
             "resubmit(): create NEW request for same entity with updated context. "
             "Both log to audit trail."),
            ("Add 4 scheduler jobs to cleanup.py",
             "check_approval_timeouts (15min interval), send_approval_reminders (15min interval), "
             "expire_stale_approvals (15min interval), deactivate_expired_delegations (daily 1am). "
             "Uses existing APScheduler + file lock pattern."),
            ("Build DelegationManager tab in frontend",
             "Tab within Approvals page. List active delegations with date range. "
             "Create: pick user, date range, optional entity_type/flow scope. Revoke button."),
        ]
    },
    {
        "id": "A5",
        "summary": "Phase A5: Flow Builder UI (Admin)",
        "desc": (
            "Admin UI for creating and managing approval flows. Visual step editor, condition builder, test mode.\n\n"
            "Location: Settings > Approvals tab OR standalone admin page.\n\n"
            "Files: pages/Settings/ApprovalsTab.tsx or pages/Approvals/FlowBuilder.tsx"
        ),
        "status": "Backlog",
        "subtasks": [
            ("Build flow list + CRUD UI",
             "List all flows with name, entity_type, active/inactive toggle, step count. "
             "Create/edit dialog with name, slug, description, entity_type, priority, "
             "auto_approve_below, auto_reject_after_hours."),
            ("Build step editor (add/remove/reorder)",
             "Ordered list of steps within a flow. Add step dialog: name, approver_type, "
             "timeout_hours, requires_all, min_approvals. Drag-to-reorder or up/down arrows. "
             "Delete step with confirmation."),
            ("Build condition builder UI",
             "Structured form for trigger_conditions and skip_conditions. "
             "Dropdowns for operator (_gte, _lt, etc.), text input for key/value. "
             "Add/remove condition rows. Preview as JSON."),
            ("Add test mode: 'Which flow matches this context?'",
             "Input: entity_type + JSON context. Backend endpoint evaluates all flows. "
             "Returns matching flow with highlighted trigger conditions. "
             "Helps admins verify flow configuration."),
        ]
    },
    {
        "id": "A6",
        "summary": "Phase A6: Entity Widget + Module Integration",
        "desc": (
            "Embeddable EntityApprovalWidget for consuming modules. Hook handlers in existing modules. "
            "Reports endpoints.\n\n"
            "Files: components/EntityApprovalWidget.tsx, module hook files\n\n"
            "Reports: turnaround time, bottleneck steps, volume trends."
        ),
        "status": "Backlog",
        "subtasks": [
            ("Build EntityApprovalWidget component",
             "Embeddable in any module page. Props: entityType, entityId. "
             "Shows: status badge, mini-timeline, approver info. "
             "'Submit for Approval' button when no active request. Small footprint."),
            ("Integrate widget into Accounting dashboard",
             "Example integration: embed in invoice detail or expanded row. "
             "Submit invoices above threshold for approval. Show approval status on invoice cards."),
            ("Register hook handlers in consuming modules",
             "approval.approved handler for invoices (mark approved_for_payment). "
             "Start with logging-only handlers, wire up real actions incrementally."),
            ("Add reports endpoints",
             "GET /api/reports/turnaround (avg time by flow/step/user). "
             "GET /api/reports/bottlenecks (steps with longest wait). "
             "GET /api/reports/volume (request count over time, groupable)."),
        ]
    },
]

print("\n━━━ Creating Tasks (Activitate) ━━━")
task_keys = {}  # "A1" -> "JAR-XX"
for task in tasks:
    key = create_issue(
        ACTIVITATE,
        task["summary"],
        task["desc"],
        parent_key=epic_key,
        start_date="2026-02-17",
    )
    task_keys[task["id"]] = key
    time.sleep(0.3)

    # Create subtasks
    if key:
        print(f"\n  ── Subtasks for {key} ({task['id']}) ──")
        for st_summary, st_desc in task["subtasks"]:
            st_key = create_issue(
                SUBTASK,
                st_summary,
                st_desc,
                parent_key=key,
            )
            time.sleep(0.3)

    print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TRANSITIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n━━━ Setting Statuses ━━━")

# Phase A1 → "To Do" (next up)
# Phases A2-A6 → stay in default status (Backlog / To Do depending on board config)
# The Jira board's default column mapping determines initial state.
# We only transition A1 to "To Do" explicitly if needed.

if task_keys.get("A1"):
    transition_issue(task_keys["A1"], "To Do")
    time.sleep(0.2)

# Try moving A2-A6 to Backlog if that transition exists
for phase_id in ["A2", "A3", "A4", "A5", "A6"]:
    key = task_keys.get(phase_id)
    if key:
        transition_issue(key, "Backlog")
        time.sleep(0.2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SUMMARY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

total_subtasks = sum(len(t["subtasks"]) for t in tasks)
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("     APPROVAL ENGINE JIRA SETUP COMPLETE")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"\nEpic: {epic_key}")
print(f"Tasks: {len([k for k in task_keys.values() if k])}")
print(f"Subtasks: {total_subtasks}")
print(f"\nPhase breakdown:")
for task in tasks:
    key = task_keys.get(task["id"], "FAILED")
    print(f"  {key}: {task['summary']} [{task['status']}] ({len(task['subtasks'])} subtasks)")
print(f"\nBoard: https://autoworldro.atlassian.net/jira/core/projects/JAR/board")
