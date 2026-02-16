export interface ApprovalUser {
  id: number
  name: string | null
  email?: string | null
}

export interface ApprovalRequest {
  id: number
  entity_type: string | null
  entity_id: number | null
  flow_id: number | null
  flow_name: string | null
  flow_slug: string | null
  current_step_id: number | null
  current_step_name: string | null
  status: 'pending' | 'approved' | 'rejected' | 'returned' | 'cancelled' | 'expired'
  context_snapshot: Record<string, unknown> | null
  requested_by: ApprovalUser
  requested_at: string | null
  resolved_at: string | null
  resolution_note: string | null
  priority: 'low' | 'normal' | 'high' | 'urgent'
  due_by: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ApprovalQueueItem extends ApprovalRequest {
  title: string
  amount: number | null
  waiting_hours: number
}

export interface ApprovalDecision {
  id: number
  request_id: number | null
  step_id: number | null
  step_name: string | null
  decided_by: ApprovalUser
  decision: 'approved' | 'rejected' | 'returned' | 'delegated' | 'abstained'
  comment: string | null
  conditions: Record<string, unknown> | null
  delegated_to: { id: number; name: string | null } | null
  decided_at: string | null
}

export interface ApprovalStep {
  id: number
  flow_id: number | null
  name: string | null
  step_order: number | null
  approver_type: 'user' | 'role' | 'group' | 'department_manager' | null
  approver_user_id: number | null
  approver_role_name: string | null
  requires_all: boolean | null
  min_approvals: number | null
  skip_conditions: Record<string, unknown> | null
  timeout_hours: number | null
  reminder_after_hours: number | null
}

export interface ApprovalAuditEntry {
  id: number
  request_id: number | null
  action: string | null
  actor_id: number | null
  actor_name: string | null
  actor_type: string | null
  details: Record<string, unknown> | null
  created_at: string | null
}

export interface ApprovalRequestDetail extends ApprovalRequest {
  decisions: ApprovalDecision[]
  audit: ApprovalAuditEntry[]
  steps: ApprovalStep[]
}

export interface ApprovalFlow {
  id: number
  name: string
  slug: string
  entity_type: string
  description: string | null
  trigger_conditions: Record<string, unknown> | null
  priority: number
  allow_parallel_steps: boolean
  auto_approve_below: Record<string, unknown> | null
  auto_reject_after_hours: number | null
  is_active: boolean
  created_by: number | null
  created_at: string | null
  steps?: ApprovalStep[]
}

export interface ApprovalDelegation {
  id: number
  delegator_id: number
  delegate_id: number
  delegate_name?: string
  starts_at: string
  ends_at: string
  reason: string | null
  entity_type: string | null
  flow_id: number | null
  is_active: boolean
  created_at?: string
}
