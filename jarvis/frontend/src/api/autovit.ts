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

export interface AutovitListing {
  id: number
  vehicle_id: number
  account_id: number
  external_advert_id: string | null
  external_url: string | null
  status: string // draft | unpaid | active | inactive | error
  last_sync: string | null
  last_error: string | null
  // Present on GET /status and POST /verify-status responses (compute_autovit_freshness) —
  // not on the dry-run `publish` response, hence optional here.
  freshness?: 'not_published' | 'up_to_date' | 'stale' | 'expired' | 'inactive' | 'error' | 'draft' | 'moderation'
}

export interface AutovitAdvertsResponse {
  results: AutovitAdvert[]
  total_elements: number
  total_pages: number
  current_page: number
}

// ── Taxonomy mapping (Settings → Connectors → Autovit → Taxonomy) ──

export interface AutovitTaxonomySuggestion {
  target_code: string
  target_label: string | null
  score: number
}

/** One admin-UI row: a distinct, in-use CarPark value for a dimension, its
 * current resolved Autovit target (if any), and ranked auto-suggest
 * candidates. `make`/`resolved_make_code` are only present on `model` rows
 * (make-scoped — Task 3's rule). */
export interface AutovitTaxonomySourceRow {
  source_value: string
  target_code: string | null
  target_label: string | null
  suggestions: AutovitTaxonomySuggestion[]
  make?: string | null
  resolved_make_code?: string | null
}

export interface AutovitTaxonomyCacheRow {
  dimension: string
  code: string
  ro_label: string | null
  param_type: string | null
  make: string | null
  options: Record<string, unknown> | null
}

export interface AutovitTaxonomyMapRow {
  dimension: string
  source_value: string
  make: string | null
  target_code: string | null
  target_label: string | null
}

export interface AutovitTaxonomyDimensionMeta {
  kind: string
  param: string | null
  required: boolean
}

export interface AutovitTaxonomyData {
  cache: AutovitTaxonomyCacheRow[]
  map: AutovitTaxonomyMapRow[]
  dimensions: Record<string, AutovitTaxonomyDimensionMeta>
  sources: Record<string, AutovitTaxonomySourceRow[]>
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

  importAll: (accountId: number) =>
    api.post<{
      success: boolean
      imported: number
      updated: number
      skipped_no_vin: number
      photo_added: number
      errors: { advert_id: string; error: string }[]
      error?: string
    }>(`${BASE}/accounts/${accountId}/import-all`, {}),

  publish: (accountId: number, vehicleId: number, options?: { dryRun?: boolean; draft?: boolean }) =>
    api.post<{
      success: boolean
      dry_run?: boolean
      advert?: Record<string, unknown>
      external_id?: string
      external_url?: string
      error?: string
      missing?: string[]
      warnings?: string[]
      updated_existing?: boolean
      status?: string
    }>(`${BASE}/accounts/${accountId}/publish`, {
      vehicle_id: vehicleId,
      dry_run: options?.dryRun,
      draft: options?.draft,
    }),

  // Deactivate (disable, reversible) the vehicle's Autovit advert.
  unpublish: (accountId: number, vehicleId: number) =>
    api.post<{ success: boolean; error?: string }>(`${BASE}/accounts/${accountId}/unpublish`, {
      vehicle_id: vehicleId,
    }),

  // Permanently delete the vehicle's Autovit advert (re-publish creates a new one).
  deleteAdvert: (accountId: number, vehicleId: number) =>
    api.post<{ success: boolean; error?: string }>(`${BASE}/accounts/${accountId}/delete-advert`, {
      vehicle_id: vehicleId,
    }),

  reconcile: () =>
    api.post<{
      success: boolean
      totals: { scanned: number; matched: number; linked: number; already_linked: number; unmatched: number }
      accounts: Array<{ account_id: number; name?: string; error?: string }>
    }>(`${BASE}/reconcile`, {}),

  getStatus: async () => {
    const res = await api.get<{ success: boolean; data: AutovitStatus }>(`${BASE}/status`)
    return res.data
  },

  getVehicleStatus: async (vehicleId: number) => {
    const res = await api.get<{ success: boolean; listings: AutovitListing[] }>(
      `${BASE}/vehicles/${vehicleId}/status`,
    )
    return res.listings
  },

  // Re-read the live advert status from Autovit and persist it (bumps last_sync).
  verifyStatus: async (vehicleId: number) => {
    const res = await api.post<{ success: boolean; refreshed: number; listings: AutovitListing[] }>(
      `${BASE}/vehicles/${vehicleId}/verify-status`,
      {},
    )
    return res
  },

  // ── Taxonomy mapping ──

  getTaxonomy: () =>
    api.get<{ success: boolean } & AutovitTaxonomyData>(`${BASE}/taxonomy`),

  syncTaxonomy: (accountId: number) =>
    api.post<{
      success: boolean
      synced?: number
      by_dimension?: Record<string, number>
      error?: string
    }>(`${BASE}/taxonomy/sync`, { account_id: accountId }),

  saveTaxonomyMap: (data: {
    dimension: string
    source_value: string
    make?: string | null
    target_code: string | null
    target_label?: string | null
  }) => api.put<{ success: boolean; error?: string }>(`${BASE}/taxonomy/map`, data),
}
