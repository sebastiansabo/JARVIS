import { api } from './client'

const BASE = '/shopify/api'

export interface ShopifyAccount {
  id: number; name: string; store_domain: string; client_id: string
  status: string; last_error?: string | null
  credential_fields: { client_secret: string }
}

export interface TaxonomyPayload {
  dimensions: string[]
  sources: Record<string, string[]>
  allowed_values: Record<string, { id: string; name: string }[]>
  mapping: Record<string, Record<string, { target_gid?: string; target_label?: string; shopify_attribute_gid?: string }>>
}

export const shopifyApi = {
  getAccounts: async () => (await api.get<{ success: boolean; accounts: ShopifyAccount[] }>(`${BASE}/config`)).accounts,
  saveAccount: (data: { id?: number; store_domain: string; client_id: string; client_secret?: string }) =>
    api.post<{ success: boolean; account: ShopifyAccount }>(`${BASE}/config`, data),
  deleteAccount: (id: number) => api.delete<{ success: boolean }>(`${BASE}/config/${id}`),
  testConnection: () => api.post<{ success: boolean; data?: { name: string; currencyCode: string }; error?: string }>(`${BASE}/test-connection`, {}),
  getTaxonomy: () => api.get<{ success: boolean } & TaxonomyPayload>(`${BASE}/taxonomy`),
  saveTaxonomy: (mappings: Array<{ dimension: string; source_value: string; target_gid?: string; target_label?: string; shopify_attribute_gid?: string }>) =>
    api.post<{ success: boolean; saved: number }>(`${BASE}/taxonomy`, { mappings }),
  publishVehicle: (vid: number) => api.post<{ success: boolean; external_id?: string; external_url?: string; warnings?: string[]; error?: string }>(`${BASE}/vehicles/${vid}/publish`, {}),
  unpublishVehicle: (vid: number) => api.post<{ success: boolean; error?: string }>(`${BASE}/vehicles/${vid}/unpublish`, {}),
  vehicleStatus: (vid: number) => api.get<{ success: boolean; listing: { status: string; external_url?: string } | null }>(`${BASE}/vehicles/${vid}/status`),
  publishBulk: (vehicleIds?: number[]) => api.post<{ success: boolean; published: number; results: Array<{ vehicle_id: number; success: boolean; error?: string }> }>(`${BASE}/publish-bulk`, vehicleIds ? { vehicle_ids: vehicleIds } : {}),
}
