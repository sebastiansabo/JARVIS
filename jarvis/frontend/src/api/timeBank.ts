import { api } from './client'

const BASE = '/hr/api/time-bank'

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  })
  return sp.toString() ? `?${sp.toString()}` : ''
}

export interface TimeBankBalance {
  user_id: number
  name: string
  email: string
  company: string
  department: string
  balance: number
}

export interface TimeBankTransaction {
  id: number
  jarvis_user_id: number
  amount: number
  tx_type: string
  description: string | null
  reference_type: string | null
  reference_id: number | null
  created_by: number | null
  created_by_name: string | null
  created_at: string
  employee_name?: string
  employee_company?: string
}

export interface TimeBankImportResult {
  source_file: string
  rows_total: number
  rows_matched: number
  rows_skipped: number
  rows_unmatched: number
  errors: string[]
}

export const timeBankApi = {
  getBalances: async () => {
    const res = await api.get<{ success: boolean; data: TimeBankBalance[] }>(`${BASE}/balances`)
    return res.data
  },

  getBalance: async (userId: number) => {
    const res = await api.get<{ success: boolean; data: { user_id: number; balance: number } }>(
      `${BASE}/balances/${userId}`,
    )
    return res.data
  },

  getTransactions: async (params?: { limit?: number; offset?: number; tx_type?: string; user_id?: number }) => {
    const res = await api.get<{ success: boolean; data: TimeBankTransaction[]; total: number }>(
      `${BASE}/transactions${qs(params ?? {})}`,
    )
    return res
  },

  getUserTransactions: async (userId: number, params?: { limit?: number; offset?: number; tx_type?: string }) => {
    const res = await api.get<{
      success: boolean; data: TimeBankTransaction[]; total: number; balance: number; user_id: number
    }>(`${BASE}/transactions/${userId}${qs(params ?? {})}`)
    return res
  },

  credit: (data: { user_id: number; amount: number; description?: string }) =>
    api.post<{ success: boolean; data: TimeBankTransaction }>(`${BASE}/credit`, data),

  debit: (data: { user_id: number; amount: number; description?: string }) =>
    api.post<{ success: boolean; data: TimeBankTransaction }>(`${BASE}/debit`, data),

  setT0: (userId: number, amount: number) =>
    api.post<{ success: boolean; data: TimeBankTransaction | null }>(`${BASE}/set-t0`, {
      user_id: userId, amount,
    }),

  importT0: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{ success: boolean; data: TimeBankImportResult }>(`${BASE}/import-t0`, form)
  },
}
