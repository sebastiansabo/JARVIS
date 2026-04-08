import { api } from './client'

export interface AutovitAccount {
  id: number
  name: string
  email: string
  environment: string
  client_id: string
  status: string
  last_sync: string | null
  last_error: string | null
  credential_fields: {
    client_secret: string
    password: string
  }
}

export interface AutovitStatus {
  total_accounts: number
  connected: number
  has_accounts: boolean
}

export interface AutovitAdvert {
  id: string
  title: string
  status: string
  url: string
  created_at: string
  params: Record<string, unknown>
  photos: string[]
  description: string
}

export interface AutovitAdvertsResponse {
  results: AutovitAdvert[]
  total_elements: number
  total_pages: number
  current_page: number
}

const BASE = '/autovit/api'

export const autovitApi = {
  getAccounts: async () => {
    const res = await api.get<{ success: boolean; accounts: AutovitAccount[] }>(`${BASE}/config`)
    return res.accounts
  },

  saveAccount: (data: {
    id?: number
    email: string
    client_id: string
    client_secret?: string
    password?: string
    environment?: string
  }) => api.post<{ success: boolean; account: AutovitAccount }>(`${BASE}/config`, data),

  deleteAccount: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/config/${id}`),

  testConnection: (accountId: number) =>
    api.post<{ success: boolean; data?: { username: string }; error?: string }>(
      `${BASE}/test-connection`,
      { account_id: accountId },
    ),

  getAccount: async (id: number) => {
    const res = await api.get<{ success: boolean; account: AutovitAccount }>(`${BASE}/config/${id}`)
    return res.account
  },

  getAdverts: async (accountId: number, page = 1) => {
    const res = await api.get<{ success: boolean; data: AutovitAdvertsResponse }>(
      `${BASE}/accounts/${accountId}/adverts`,
      { page: String(page) },
    )
    return res.data
  },

  importAdvert: (accountId: number, advertId: string) =>
    api.post<{
      success: boolean
      vehicle?: { id: number; vin: string; brand: string; model: string }
      error?: string
      existing_vehicle_id?: number
    }>(`${BASE}/accounts/${accountId}/import-advert`, { advert_id: advertId }),

  getStatus: async () => {
    const res = await api.get<{ success: boolean; data: AutovitStatus }>(`${BASE}/status`)
    return res.data
  },
}
