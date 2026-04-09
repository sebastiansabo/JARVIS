import { api } from './client'

const BASE = '/identity/api'

// ── Types ──

export interface IdentityJarvisUser {
  id: number
  name: string
  email: string | null
  department: string | null
  company: string | null
}

export interface IdentitySincronMapping {
  sincron_employee_id: string
  company_name: string
  nume: string | null
  prenume: string | null
  mapping_method: string | null
  mapping_confidence: number | null
  is_active: boolean
}

export interface IdentityBiostarMapping {
  biostar_user_id: string
  name: string | null
  email: string | null
  user_group_name: string | null
  cnp: string | null
  mapping_method: string | null
  mapping_confidence: number | null
  status: string
}

export interface IdentityUnifiedRow {
  user_id: number
  name: string
  email: string | null
  cnp: string | null
  company: string | null
  department: string | null
  is_active: boolean
  sincron_mappings: IdentitySincronMapping[]
  biostar_mappings: IdentityBiostarMapping[]
  /** Derived on the client when not supplied. */
  status?: 'fully_mapped' | 'sincron_only' | 'biostar_only' | 'unmapped'
}

export interface IdentityOrphanSincron {
  id: number
  sincron_employee_id: string
  company_name: string
  nume: string | null
  prenume: string | null
  cnp: string | null
  is_active: boolean
}

export interface IdentityOrphanBiostar {
  id: number
  biostar_user_id: string
  name: string | null
  email: string | null
  user_group_name: string | null
  cnp: string | null
  status: string
}

export interface IdentityStats {
  total_users: number
  fully_mapped: number
  sincron_only: number
  biostar_only: number
  unmapped_users: number
  orphan_sincron: number
  orphan_biostar: number
}

export interface IdentityUnifiedView {
  users: IdentityUnifiedRow[]
  orphan_sincron: IdentityOrphanSincron[]
  orphan_biostar: IdentityOrphanBiostar[]
  stats: IdentityStats
}

export interface IdentityAutoMapResult {
  sincron_cnp: number
  sincron_name: number
  biostar_cnp: number
  biostar_email: number
  biostar_name: number
  biostar_cross: number
  total_mapped: number
  [errorKey: string]: number | string
}

export type IdentityMappingSource = 'sincron' | 'biostar'

// ── API ──

export const identityApi = {
  getEmployees: async () => {
    const res = await api.get<{ success: boolean; data: IdentityUnifiedView }>(
      `${BASE}/employees`,
    )
    return res.data
  },

  getStats: async () => {
    const res = await api.get<{ success: boolean; data: IdentityStats }>(
      `${BASE}/stats`,
    )
    return res.data
  },

  getJarvisUsers: async () => {
    const res = await api.get<{ success: boolean; data: IdentityJarvisUser[] }>(
      `${BASE}/jarvis-users`,
    )
    return res.data
  },

  autoMapAll: () =>
    api.post<{ success: boolean; data: IdentityAutoMapResult }>(
      `${BASE}/auto-map`, {},
    ),

  setMapping: (
    userId: number,
    body: { source: IdentityMappingSource; external_id: string; company_name?: string },
  ) =>
    api.put<{ success: boolean; data: unknown; message: string }>(
      `${BASE}/employees/${userId}/mapping`, body,
    ),

  removeMapping: (
    userId: number,
    source: IdentityMappingSource,
    params: { external_id: string; company_name?: string },
  ) => {
    const sp = new URLSearchParams()
    sp.set('external_id', params.external_id)
    if (params.company_name) sp.set('company_name', params.company_name)
    return api.delete<{ success: boolean; data: unknown; message: string }>(
      `${BASE}/employees/${userId}/mapping/${source}?${sp.toString()}`,
    )
  },
}
