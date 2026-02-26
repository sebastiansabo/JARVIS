import { api } from './client'

export interface CrmClient {
  id: number
  display_name: string
  name_normalized: string
  client_type: string
  phone?: string
  phone_raw?: string
  email?: string
  street?: string
  city?: string
  region?: string
  country?: string
  company_name?: string
  responsible?: string
  nr_reg?: string
  source_flags: Record<string, boolean>
  merged_into_id?: number
  created_at: string
  updated_at: string
}

export interface CrmDeal {
  id: number
  client_id?: number
  client_display_name?: string
  source: 'nw' | 'gw'
  dealer_code?: string
  dealer_name?: string
  branch?: string
  dossier_number?: string
  order_number?: string
  contract_date?: string
  order_date?: string
  delivery_date?: string
  invoice_date?: string
  registration_date?: string
  entry_date?: string
  brand?: string
  model_name?: string
  model_code?: string
  model_year?: number
  order_year?: number
  body_code?: string
  vin?: string
  engine_code?: string
  fuel_type?: string
  color?: string
  color_code?: string
  door_count?: number
  vehicle_type?: string
  list_price?: number
  purchase_price_net?: number
  sale_price_net?: number
  gross_profit?: number
  discount_value?: number
  other_costs?: number
  gw_gross_value?: number
  dossier_status?: string
  order_status?: string
  contract_status?: string
  sales_person?: string
  buyer_name?: string
  buyer_address?: string
  owner_name?: string
  owner_address?: string
  customer_group?: string
  registration_number?: string
  vehicle_specs?: Record<string, unknown>
  created_at: string
}

export interface ImportBatch {
  id: number
  source_type: string
  filename: string
  uploaded_by_name?: string
  total_rows: number
  new_rows: number
  updated_rows: number
  skipped_rows: number
  new_clients: number
  matched_clients: number
  status: string
  created_at: string
}

export interface CrmStats {
  clients: { total: number; persons: number; companies: number; merged: number }
  deals: { total: number; new_cars: number; used_cars: number; brands: number }
  last_imports: Record<string, ImportBatch | null>
}

export interface DetailedStats {
  totals: { total_deals: number; total_revenue: number; avg_price: number; brand_count: number; dealer_count: number; sales_person_count: number }
  by_brand: { brand: string; count: number; revenue: number }[]
  by_dealer: { dealer_name: string; count: number; revenue: number }[]
  by_sales_person: { sales_person: string; count: number; revenue: number }[]
  by_month: { month: string; count: number; revenue: number }[]
  by_status: { dossier_status: string; count: number }[]
}

export interface ClientDetailedStats {
  total: number
  by_type: { client_type: string; count: number }[]
  by_region: { region: string; count: number }[]
  by_city: { city: string; count: number }[]
  by_responsible: { responsible: string; count: number }[]
  clients_with_deals: number
  total_deals_linked: number
  contact_coverage: {
    with_phone: number
    with_email: number
    with_region: number
    with_city: number
    with_street: number
  }
  data_quality: {
    missing_phone: number
    missing_email: number
    missing_region: number
    missing_responsible: number
    merged_clients: number
  }
  source_flags: { source: string; count: number }[]
  by_month: { month: string; count: number }[]
}

export const crmApi = {
  getStats: () => api.get<CrmStats>('/api/crm/stats'),
  getClients: (params?: Record<string, string>) => api.get<{ clients: CrmClient[]; total: number }>('/api/crm/clients', params),
  getClient: (id: number) => api.get<{ client: CrmClient; deals: CrmDeal[] }>(`/api/crm/clients/${id}`),
  mergeClients: (keepId: number, removeId: number) => api.post<{ success: boolean }>('/api/crm/clients/merge', { keep_id: keepId, remove_id: removeId }),
  getDeals: (params?: Record<string, string>) => api.get<{ deals: CrmDeal[]; total: number }>('/api/crm/deals', params),
  getDeal: (id: number) => api.get<{ deal: CrmDeal }>(`/api/crm/deals/${id}`),
  getBrands: () => api.get<{ brands: string[] }>('/api/crm/deals/brands'),
  getDealStatuses: () => api.get<{ statuses: { dossier_status: string; count: number }[] }>('/api/crm/deals/statuses'),
  getOrderStatuses: () => api.get<{ statuses: string[] }>('/api/crm/deals/order-statuses'),
  getContractStatuses: () => api.get<{ statuses: string[] }>('/api/crm/deals/contract-statuses'),
  getDetailedStats: (params?: Record<string, string>) => api.get<DetailedStats>('/api/crm/deals/detailed-stats', params),
  getClientDetailedStats: () => api.get<ClientDetailedStats>('/api/crm/clients/detailed-stats'),
  getClientCities: () => api.get<{ cities: string[] }>('/api/crm/clients/cities'),
  getClientResponsibles: () => api.get<{ responsibles: string[] }>('/api/crm/clients/responsibles'),
  getDealers: () => api.get<{ dealers: string[] }>('/api/crm/deals/dealers'),
  getSalesPersons: () => api.get<{ sales_persons: string[] }>('/api/crm/deals/sales-persons'),
  // CRUD mutations
  updateDeal: (id: number, data: Partial<CrmDeal>) => api.put<{ success: boolean; deal: CrmDeal }>(`/api/crm/deals/${id}`, data),
  deleteDeal: (id: number) => api.delete<{ success: boolean }>(`/api/crm/deals/${id}`),
  updateClient: (id: number, data: Partial<CrmClient>) => api.put<{ success: boolean; client: CrmClient }>(`/api/crm/clients/${id}`, data),
  deleteClient: (id: number) => api.delete<{ success: boolean }>(`/api/crm/clients/${id}`),
  // Export URLs (returns URL string for <a download>)
  exportDealsUrl: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return `/api/crm/deals/export${qs}`
  },
  exportClientsUrl: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return `/api/crm/clients/export${qs}`
  },
  importFile: (file: File, sourceType: string) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('source_type', sourceType)
    return api.post<{ success: boolean; stats: Record<string, number | string[]> }>('/api/crm/import', fd)
  },
  getImportBatches: (params?: Record<string, string>) => api.get<{ batches: ImportBatch[] }>('/api/crm/import/batches', params),
}
