import { api } from './client'
import type {
  ApprovalRequest,
  ApprovalQueueItem,
  ApprovalRequestDetail,
  ApprovalFlow,
  ApprovalDelegation,
  ApprovalAuditEntry,
} from '@/types/approvals'

export const approvalsApi = {
  // Requests
  submit: (data: { entity_type: string; entity_id: number; context?: Record<string, unknown>; priority?: string; due_by?: string; note?: string }) =>
    api.post<{ success: boolean; request: ApprovalRequest }>('/approvals/api/requests', data),

  listRequests: (params?: { status?: string; entity_type?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.entity_type) qs.set('entity_type', params.entity_type)
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.offset) qs.set('offset', String(params.offset))
    const q = qs.toString()
    return api.get<{ requests: ApprovalRequest[] }>(`/approvals/api/requests${q ? `?${q}` : ''}`)
  },

  getRequest: (id: number) =>
    api.get<ApprovalRequestDetail>(`/approvals/api/requests/${id}`),

  decide: (requestId: number, data: { decision: string; comment?: string; conditions?: Record<string, unknown>; delegate_to?: number; delegation_reason?: string }) =>
    api.post<{ success: boolean; request: ApprovalRequest }>(`/approvals/api/requests/${requestId}/decide`, data),

  cancel: (requestId: number, reason?: string) =>
    api.post<{ success: boolean; request: ApprovalRequest }>(`/approvals/api/requests/${requestId}/cancel`, { reason }),

  resubmit: (requestId: number, context?: Record<string, unknown>) =>
    api.post<{ success: boolean; request: ApprovalRequest }>(`/approvals/api/requests/${requestId}/resubmit`, { context }),

  escalate: (requestId: number, reason?: string) =>
    api.post<{ success: boolean; request: ApprovalRequest }>(`/approvals/api/requests/${requestId}/escalate`, { reason }),

  // Queue
  getMyQueue: (entityType?: string) =>
    api.get<{ queue: ApprovalQueueItem[] }>(`/approvals/api/my-queue${entityType ? `?entity_type=${entityType}` : ''}`),

  getMyQueueCount: () =>
    api.get<{ count: number }>('/approvals/api/my-queue/count'),

  getMyRequests: () =>
    api.get<{ requests: ApprovalRequest[] }>('/approvals/api/my-requests'),

  // Flows (admin)
  getFlows: (activeOnly = true) =>
    api.get<{ flows: ApprovalFlow[] }>(`/approvals/api/flows?active_only=${activeOnly}`),

  getFlow: (id: number) =>
    api.get<ApprovalFlow>(`/approvals/api/flows/${id}`),

  createFlow: (data: Partial<ApprovalFlow>) =>
    api.post<{ success: boolean; id: number }>('/approvals/api/flows', data),

  updateFlow: (id: number, data: Partial<ApprovalFlow>) =>
    api.put<{ success: boolean }>(`/approvals/api/flows/${id}`, data),

  deleteFlow: (id: number) =>
    api.delete<{ success: boolean }>(`/approvals/api/flows/${id}`),

  // Steps (admin)
  createStep: (flowId: number, data: Record<string, unknown>) =>
    api.post<{ success: boolean; id: number }>(`/approvals/api/flows/${flowId}/steps`, data),

  updateStep: (flowId: number, stepId: number, data: Record<string, unknown>) =>
    api.put<{ success: boolean }>(`/approvals/api/flows/${flowId}/steps/${stepId}`, data),

  deleteStep: (flowId: number, stepId: number) =>
    api.delete<{ success: boolean }>(`/approvals/api/flows/${flowId}/steps/${stepId}`),

  // Delegations
  getDelegations: () =>
    api.get<{ delegations: ApprovalDelegation[] }>('/approvals/api/delegations'),

  createDelegation: (data: { delegate_id: number; starts_at: string; ends_at: string; reason?: string; entity_type?: string; flow_id?: number }) =>
    api.post<{ success: boolean; id: number }>('/approvals/api/delegations', data),

  deleteDelegation: (id: number) =>
    api.delete<{ success: boolean }>(`/approvals/api/delegations/${id}`),

  // Audit
  getRequestAudit: (requestId: number) =>
    api.get<{ audit: ApprovalAuditEntry[] }>(`/approvals/api/requests/${requestId}/audit`),

  getGlobalAudit: (params?: { limit?: number; offset?: number; action?: string; actor_id?: number }) => {
    const qs = new URLSearchParams()
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.offset) qs.set('offset', String(params.offset))
    if (params?.action) qs.set('action', params.action)
    if (params?.actor_id) qs.set('actor_id', String(params.actor_id))
    const q = qs.toString()
    return api.get<{ audit: ApprovalAuditEntry[] }>(`/approvals/api/audit${q ? `?${q}` : ''}`)
  },

  // Entity history
  getEntityHistory: (entityType: string, entityId: number) =>
    api.get<{ history: ApprovalRequest[] }>(`/approvals/api/entity/${entityType}/${entityId}/history`),
}
