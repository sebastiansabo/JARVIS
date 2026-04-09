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
  last_sync: string | null
  form_name: string
  webhook_registered: boolean
  total_users: number
  mapped_users: number
  unmapped_users: number
  total_submissions: number
  last_webhook_at: string | null
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
  status: string
  event_type: string
  entry_num: number
  received_at: string
  created_at: string
  source?: 'connecteam' | 'jarvis'
}

export const connecteamApi = {
  getStatus: () =>
    api.get<{ success: boolean; data: ConnecteamStatus }>(`${BASE}/status`),

  getEmployeeSubmissions: (userId: number, year?: number, month?: number) =>
    api.get<{ success: boolean; data: ConnecteamSubmission[] }>(
      `${BASE}/submissions/employee/${userId}${qs({ year, month })}`
    ),

  getApprovers: () =>
    api.get<{ success: boolean; data: { id: number; name: string }[] }>(`${BASE}/approvers`),
}
