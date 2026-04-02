import { api } from './client'

const BASE = '/sincron/api'

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  })
  return sp.toString() ? `?${sp.toString()}` : ''
}

export interface SincronStatus {
  connected: boolean
  status: string
  last_sync: string | null
  companies_configured: number
  employee_count: { total: number; mapped: number; unmapped: number; companies: number }
}

export interface SincronEmployee {
  id: number
  sincron_employee_id: string
  company_name: string
  nume: string
  prenume: string
  id_contract: string
  nr_contract: string
  data_incepere_contract: string | null
  mapped_jarvis_user_id: number | null
  mapped_jarvis_user_name: string | null
  mapping_method: string | null
  mapping_confidence: number
  is_active: boolean
  last_synced_at: string
}

export interface SincronSyncRun {
  id: number
  run_id: string
  sync_type: string
  company_name: string | null
  year: number
  month: number
  status: string
  employees_synced: number
  records_created: number
  error_message: string | null
  started_at: string
  finished_at: string | null
}

export interface JarvisUser {
  id: number
  name: string
  email: string
  company: string
  department: string
}

export const sincronApi = {
  // ── Status ──

  getStatus: async () => {
    const res = await api.get<{ success: boolean; data: SincronStatus }>(`${BASE}/status`)
    return res.data
  },

  // ── Config (admin) ──

  getConfig: async () => {
    const res = await api.get<{ success: boolean; data: {
      id: number; status: string; last_sync: string | null;
      companies_configured: Record<string, boolean>; companies_count: number
    } | null }>(`${BASE}/config`)
    return res.data
  },

  saveConfig: (companyTokens: Record<string, string>) =>
    api.post<{ success: boolean; message: string; connector_id: number }>(
      `${BASE}/config`, { company_tokens: companyTokens },
    ),

  testConnection: (companyName?: string) =>
    api.post<{ success: boolean; companies: Record<string, { success: boolean; error?: string }> }>(
      `${BASE}/test-connection`, companyName ? { company_name: companyName } : {},
    ),

  // ── Sync (admin) ──

  syncTimesheets: (params?: { year?: number; month?: number; company_name?: string }) =>
    api.post<{ success: boolean; message?: string; error?: string }>(
      `${BASE}/sync/timesheets`, params,
    ),

  syncTimesheetsNow: (params?: { year?: number; month?: number; company_name?: string }) =>
    api.post<{
      success: boolean; year: number; month: number;
      total_employees: number; total_records: number;
      companies: Record<string, { success: boolean; employees?: number; records?: number; error?: string }>
    }>(`${BASE}/sync/timesheets/now`, params),

  getSyncHistory: async (params?: { sync_type?: string; limit?: number }) => {
    const res = await api.get<{ success: boolean; data: SincronSyncRun[] }>(
      `${BASE}/sync/history${qs(params ?? {})}`,
    )
    return res.data
  },

  // ── Employees (admin) ──

  getEmployees: async (company?: string, activeOnly = true) => {
    const res = await api.get<{ success: boolean; data: SincronEmployee[] }>(
      `${BASE}/employees${qs({ company, active_only: activeOnly })}`,
    )
    return res.data
  },

  getEmployeeStats: async () => {
    const res = await api.get<{ success: boolean; data: Record<string, number> }>(
      `${BASE}/employees/stats`,
    )
    return res.data
  },

  getUnmapped: async () => {
    const res = await api.get<{ success: boolean; data: SincronEmployee[] }>(
      `${BASE}/employees/unmapped`,
    )
    return res.data
  },

  autoMap: () =>
    api.post<{ success: boolean; cnp_mapped: number; name_mapped: number; total_mapped: number }>(
      `${BASE}/employees/auto-map`, {},
    ),

  updateMapping: (sincronEmployeeId: string, companyName: string, jarvisUserId: number) =>
    api.put<{ success: boolean; message: string }>(`${BASE}/employees/mapping`, {
      sincron_employee_id: sincronEmployeeId,
      company_name: companyName,
      jarvis_user_id: jarvisUserId,
    }),

  removeMapping: (sincronEmployeeId: string, companyName: string) =>
    fetch(`${BASE}/employees/mapping`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ sincron_employee_id: sincronEmployeeId, company_name: companyName }),
    }).then(r => r.json()) as Promise<{ success: boolean; message: string }>,

  getJarvisUsers: async () => {
    const res = await api.get<{ success: boolean; data: JarvisUser[] }>(
      `${BASE}/employees/jarvis-users`,
    )
    return res.data
  },

  // ── Activity Codes ──

  getActivityCodes: async () => {
    const res = await api.get<{ success: boolean; data: Array<{
      short_code: string; short_code_en: string; description: string | null; category: string | null
    }> }>(`${BASE}/activity-codes`)
    return res.data
  },
}
