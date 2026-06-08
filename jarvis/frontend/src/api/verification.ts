import { api } from './client'

const BASE = '/verification/api'

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  })
  return sp.toString() ? `?${sp.toString()}` : ''
}

export interface VerificationRun {
  id: number
  run_id: string
  year: number
  month: number
  status: 'running' | 'completed' | 'failed'
  triggered_by: number | null
  started_at: string
  finished_at: string | null
  summary: {
    total?: number
    by_type?: Record<string, number>
    by_severity?: Record<string, number>
    by_company?: Record<string, number>
    error?: string
  }
}

export interface VerificationDiscrepancy {
  id: number
  run_id: string
  jarvis_user_id: number | null
  company_name: string | null
  employee_name: string | null
  discrepancy_type: string
  day: string | null
  sincron_value: Record<string, unknown> | null
  biostar_value: Record<string, unknown> | null
  jarvis_value: Record<string, unknown> | null
  severity: 'error' | 'warning' | 'info'
  is_resolved: boolean
  resolved_by: number | null
  resolved_at: string | null
  notes: string | null
  created_at: string
}

export const verificationApi = {
  runVerification: (year: number, month: number) =>
    api.post<{ success: boolean; data: { run_id: string; discrepancy_count: number; summary: VerificationRun['summary'] } }>(
      `${BASE}/run`,
      { year, month },
    ),

  getResults: async (year: number, month: number, includeResolved = false) => {
    const res = await api.get<{
      success: boolean
      run: VerificationRun | null
      data: VerificationDiscrepancy[]
    }>(`${BASE}/results${qs({ year, month, include_resolved: includeResolved })}`)
    return res
  },

  resolveDiscrepancy: (id: number, notes = '') =>
    api.post<{ success: boolean }>(`${BASE}/resolve/${id}`, { notes }),
}
