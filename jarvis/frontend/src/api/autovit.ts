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

  getStatus: async () => {
    const res = await api.get<{ success: boolean; data: AutovitStatus }>(`${BASE}/status`)
    return res.data
  },
}
