import { api } from './client'

const BASE = '/shopify/api'

export interface ShopifyAccount {
  id: number; name: string; store_domain: string; client_id: string
  status: string; last_error?: string | null
  credential_fields: { client_secret: string }
  autosync_enabled?: boolean
}

export interface TaxonomyPayload {
  dimensions: string[]
  sources: Record<string, string[]>
  allowed_values: Record<string, { id: string; name: string }[]>
  mapping: Record<string, Record<string, { target_gid?: string; target_label?: string; shopify_attribute_gid?: string }>>
}

export interface FieldMapRow {
  source_expr: string | null
  target_namespace: string
  target_key: string
  target_type: string
  transform: string
  is_active: boolean
  last_seen_in_store: boolean
}

export interface SchemaDrift {
  new: { namespace: string; key: string; type: string }[]
  stale: { target_namespace: string; target_key: string }[]
  type_changed: { target_namespace: string; target_key: string; map_type: string; store_type: string }[]
  ok: number
}

export interface SchemaPayload {
  success: boolean
  field_map: FieldMapRow[]
  value_map: Record<string, Record<string, string>>
  store_defs: Record<string, string>
  drift: Partial<SchemaDrift>
}

export const shopifyApi = {
  getAccounts: async () => (await api.get<{ success: boolean; accounts: ShopifyAccount[] }>(`${BASE}/config`)).accounts,
  saveAccount: (data: { id?: number; store_domain: string; client_id: string; client_secret?: string }) =>
    api.post<{ success: boolean; account: ShopifyAccount }>(`${BASE}/config`, data),
  deleteAccount: (id: number) => api.delete<{ success: boolean }>(`${BASE}/config/${id}`),
  setAutosync: (enabled: boolean) => api.post<{ success: boolean; autosync_enabled: boolean }>(`${BASE}/autosync`, { enabled }),
  testConnection: () => api.post<{ success: boolean; data?: { name: string; currencyCode: string }; error?: string }>(`${BASE}/test-connection`, {}),
  getTaxonomy: () => api.get<{ success: boolean } & TaxonomyPayload>(`${BASE}/taxonomy`),
  saveTaxonomy: (mappings: Array<{ dimension: string; source_value: string; target_gid?: string; target_label?: string; shopify_attribute_gid?: string }>) =>
    api.post<{ success: boolean; saved: number }>(`${BASE}/taxonomy`, { mappings }),
  publishVehicle: (vid: number) => api.post<{ success: boolean; external_id?: string; external_url?: string; warnings?: string[]; error?: string }>(`${BASE}/vehicles/${vid}/publish`, {}),
  unpublishVehicle: (vid: number) => api.post<{ success: boolean; error?: string }>(`${BASE}/vehicles/${vid}/unpublish`, {}),
  vehicleStatus: (vid: number) => api.get<{
    success: boolean
    listing: { status: string; external_url?: string; last_sync?: string | null; published_at?: string | null; expires_at?: string | null; error_message?: string | null } | null
    freshness: 'not_published' | 'up_to_date' | 'stale' | 'expired' | 'inactive' | 'error'
    vehicle_updated_at?: string | null
  }>(`${BASE}/vehicles/${vid}/status`),
  publishBulk: (vehicleIds?: number[]) => api.post<{ success: boolean; published: number; results: Array<{ vehicle_id: number; success: boolean; error?: string }> }>(`${BASE}/publish-bulk`, vehicleIds ? { vehicle_ids: vehicleIds } : {}),
  getSchema: () => api.get<SchemaPayload>(`${BASE}/schema`),
  saveSchema: (field_entries: Partial<FieldMapRow>[], value_entries: { dimension: string; source_value: string; ro_value: string }[]) =>
    api.post<{ success: boolean; saved: number }>(`${BASE}/schema`, { field_entries, value_entries }),
  syncSchema: () => api.post<{ success: boolean; drift: Partial<SchemaDrift> }>(`${BASE}/schema/sync`, {}),
}
