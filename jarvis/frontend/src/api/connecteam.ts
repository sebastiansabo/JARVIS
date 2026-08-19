import { api } from './client'

const BASE = '/connecteam/api'

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  })
  return sp.toString() ? `?${sp.toString()}` : ''
}

export interface ConnecteamStatus {
  connected: boolean
  status: string
  form_name: string
  total_users: number
  mapped_users: number
  unmapped_users: number
  total_submissions: number
  last_import_at: string | null
}

export interface ConnecteamUser {
  id: number
  connecteam_user_id: number
  connecteam_user_name: string | null
  mapped_jarvis_user_id: number | null
  mapped_jarvis_user_name: string | null
  mapping_method: string | null
  mapping_confidence: number
  is_active: boolean
}

export interface ImportResult {
  rows_processed: number
  inserted: number
  skipped: number
  users_created: number
  unmapped_names: string[]
}

export interface ConnecteamSubmission {
  id: number
  submission_id: string
  form_id: number
  form_name: string | null
  connecteam_user_id: number
  mapped_jarvis_user_id: number | null
  connecteam_user_name: string | null
  submission_timestamp: string
  leave_date: string | null
  leave_start_time: string | null
  leave_end_time: string | null
  leave_hours: number | null
  leave_reason: string | null
  leave_destination: string | null
  approved_by: string | null
  pending_approvers?: string[]
  status: string
  event_type: string
  entry_num: number
  received_at: string
  created_at: string
  source?: 'connecteam' | 'jarvis'
  jarvis_user_company?: string | null
}

export interface LeaveApproval {
  request_id: number
  submission_id: number
  requester_name: string | null
  leave_date: string | null
  leave_start_time: string | null
  leave_end_time: string | null
  leave_hours: number | null
  leave_reason: string | null
  requested_at: string | null
}

export interface ConversionRequest {
  id: number
  employee_user_id: number
  employee_name: string
  year: number
  month: number
  total_accumulated_hours: number
  co_days_requested: number
  approver_user_id: number
  approver_name: string
  approval_request_id: number | null
  status: 'pending' | 'approved' | 'rejected' | 'cancelled'
  created_at: string
}

export interface LeaveSchedule {
  schedule_start: string
  schedule_end: string
  day_cap_hours: number
  lunch_break_minutes: number
  source: 'sincron' | 'default'
  reasons?: string[]
  labels?: Record<string, string>
  placeholders?: Record<string, string>
  visible?: Record<string, boolean>
  terms_text?: string
}

export const connecteamApi = {
  getStatus: () =>
    api.get<{ success: boolean; data: ConnecteamStatus }>(`${BASE}/status`),

  getEmployeeSubmissions: (userId: number, year?: number, month?: number) =>
    api.get<{ success: boolean; data: ConnecteamSubmission[] }>(
      `${BASE}/submissions/employee/${userId}${qs({ year, month })}`
    ),

  // Create a Bilet de Invoire via the code-defined Invoire module form.
  submitLeavePermit: (answers: Record<string, unknown>) =>
    api.post<{ success: boolean; data: { submission_id: number } }>(
      `${BASE}/submissions/leave-permit`, { answers }
    ),

  cancelLeavePermit: (id: number) =>
    api.post<{ success: boolean; data: { status: 'cancelled' | 'cancellation_pending' } }>(
      `${BASE}/submissions/leave-permit/${id}/cancel`
    ),

  updateLeavePermit: (id: number, answers: Record<string, unknown>) =>
    api.patch<{ success: boolean; data: { submission_id: number } }>(
      `${BASE}/submissions/leave-permit/${id}`, { answers }
    ),

  // Leave requests awaiting the current user's approval (empty if not an approver).
  getPendingLeaveApprovals: () =>
    api.get<{ success: boolean; data: LeaveApproval[] }>(`${BASE}/leave-approvals/pending`),

  decideLeaveApproval: (requestId: number, decision: 'approved' | 'rejected', comment?: string) =>
    api.post<{ success: boolean; error?: string }>(
      `${BASE}/leave-approvals/${requestId}/decide`, { decision, comment }
    ),

  getApprovers: (scope?: 'all') =>
    api.get<{ success: boolean; data: { id: number; name: string }[] }>(`${BASE}/approvers${scope ? '?scope=all' : ''}`),

  getLeaveSchedule: (date?: string) =>
    api.get<{ success: boolean; data: LeaveSchedule }>(`${BASE}/leave-schedule${qs({ date })}`),

  importExcel: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{ success: boolean; data: ImportResult }>(`${BASE}/import-excel`, form)
  },

  getUsers: (activeOnly = true) =>
    api.get<{ success: boolean; data: ConnecteamUser[] }>(`${BASE}/users?active_only=${activeOnly}`),

  autoMapUsers: () =>
    api.post<{ success: boolean; name_mapped: number; total_mapped: number }>(`${BASE}/users/auto-map`),

  updateMapping: (connecteamUserId: number, jarvisUserId: number) =>
    api.put<{ success: boolean }>(`${BASE}/users/mapping`, {
      connecteam_user_id: connecteamUserId,
      jarvis_user_id: jarvisUserId,
    }),

  removeMapping: (connecteamUserId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/users/mapping?connecteam_user_id=${connecteamUserId}`),

  // ── CO Conversions ──

  createConversion: (data: {
    employee_user_id: number
    year: number
    month: number
    co_days_requested: number
    approver_user_id: number
    submission_ids?: string[]
  }) =>
    api.post<{ success: boolean; data: ConversionRequest }>(`${BASE}/conversions`, data),

  getConversions: async (year: number, month: number) => {
    const res = await api.get<{ success: boolean; data: ConversionRequest[] }>(
      `${BASE}/conversions${qs({ year, month })}`,
    )
    return res.data
  },
}
