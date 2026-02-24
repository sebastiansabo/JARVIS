"""Approval system query tools."""

from ai_agent.tools.registry import tool_registry
from core.database import get_db, get_cursor, release_db


def get_pending_approvals(params: dict, user_id: int) -> dict:
    """Get pending approval requests for the current user or globally."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        if params.get('scope') == 'all':
            cursor.execute("""
                SELECT ar.id, ar.entity_type, ar.entity_id, ar.title,
                       ar.status, ar.priority, ar.created_at,
                       u.name AS requested_by,
                       ar.context_snapshot
                FROM approval_requests ar
                LEFT JOIN users u ON u.id = ar.requested_by_id
                WHERE ar.status = 'pending'
                ORDER BY ar.created_at DESC
                LIMIT 50
            """)
        else:
            # Get pending for this specific user (assigned to them)
            cursor.execute("""
                SELECT ar.id, ar.entity_type, ar.entity_id, ar.title,
                       ar.status, ar.priority, ar.created_at,
                       u.name AS requested_by,
                       ar.context_snapshot
                FROM approval_requests ar
                LEFT JOIN users u ON u.id = ar.requested_by_id
                JOIN approval_steps s ON s.flow_id = ar.flow_id
                    AND s.step_order = ar.current_step
                WHERE ar.status = 'pending'
                  AND (
                    (s.approver_type = 'user' AND s.approver_id = %s)
                    OR (s.approver_type = 'role' AND s.approver_id IN (
                        SELECT role_id FROM users WHERE id = %s
                    ))
                    OR (s.approver_type = 'context_approver'
                        AND ar.context_snapshot->>'approver_user_id' = %s::text)
                  )
                ORDER BY ar.created_at DESC
                LIMIT 50
            """, [user_id, user_id, user_id])

        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            if r.get('created_at'):
                r['created_at'] = str(r['created_at'])
            # Simplify context_snapshot for LLM
            ctx = r.pop('context_snapshot', None)
            if ctx and isinstance(ctx, dict):
                r['context'] = {
                    k: v for k, v in ctx.items()
                    if k in ('name', 'supplier', 'total_value', 'status', 'company')
                }

        return {'pending_approvals': rows, 'count': len(rows)}
    finally:
        release_db(conn)


def get_approval_status(params: dict, user_id: int) -> dict:
    """Get the approval status of a specific request."""
    request_id = params.get('request_id')
    if not request_id:
        return {'error': 'request_id is required'}

    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("""
            SELECT ar.id, ar.entity_type, ar.entity_id, ar.title,
                   ar.status, ar.priority, ar.current_step, ar.total_steps,
                   ar.created_at, ar.updated_at,
                   u.name AS requested_by
            FROM approval_requests ar
            LEFT JOIN users u ON u.id = ar.requested_by_id
            WHERE ar.id = %s
        """, [request_id])
        row = cursor.fetchone()
        if not row:
            return {'error': f'Approval request {request_id} not found'}

        result = dict(row)
        for k in ('created_at', 'updated_at'):
            if result.get(k):
                result[k] = str(result[k])

        # Get decisions
        cursor.execute("""
            SELECT ad.step_order, ad.decision, ad.comment,
                   ad.created_at, u.name AS decided_by
            FROM approval_decisions ad
            LEFT JOIN users u ON u.id = ad.user_id
            WHERE ad.request_id = %s
            ORDER BY ad.step_order, ad.created_at
        """, [request_id])
        result['decisions'] = [dict(r) for r in cursor.fetchall()]
        for d in result['decisions']:
            if d.get('created_at'):
                d['created_at'] = str(d['created_at'])

        return result
    finally:
        release_db(conn)


# Register tools
tool_registry.register(
    name='get_pending_approvals',
    description=(
        'Get pending approval requests from the approval workflow system. '
        'Use when the user asks "what approvals do I have?", "pending approvals", or "ce aprobări am?". '
        'Default scope="mine" returns only items assigned to the current user. Use scope="all" for organization-wide view. '
        'Returns: {pending_approvals: [{id, entity_type, entity_id, title, status, priority, created_at, requested_by, context}], count}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'scope': {
                'type': 'string',
                'enum': ['mine', 'all'],
                'description': 'Scope: "mine" (default) for current user, "all" for organization-wide',
            },
        },
    },
    handler=get_pending_approvals,
    permission='approvals.view',
)

tool_registry.register(
    name='get_approval_status',
    description=(
        'Get the status, progress, and decision history of a specific approval request by ID. '
        'Use when the user asks about a specific approval status or decision timeline. '
        'Returns: {id, entity_type, title, status, current_step, total_steps, requested_by, decisions: [{step_order, decision, comment, decided_by}]}'
    ),
    input_schema={
        'type': 'object',
        'properties': {
            'request_id': {'type': 'integer', 'description': 'The approval request ID'},
        },
        'required': ['request_id'],
    },
    handler=get_approval_status,
    permission='approvals.view',
)
