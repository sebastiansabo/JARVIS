import { api } from './client'
import { buildQs } from './utils'
import type {
  CompanyConnection,
  EFacturaInvoice,
  EFacturaInvoiceSummary,
  EFacturaInvoiceFilters,
  Pagination,
  SyncRun,
  SyncError,
  SyncAllResult,
  SyncCompany,
  ANAFMessage,
  ANAFFetchFilters,
  ANAFStatus,
  ImportResult,
  SupplierMapping,
  SupplierType,
  OAuthStatus,
  DuplicateInvoice,
  CompanyLookup,
  DistinctSupplier,
  ErrorStats,
} from '@/types/efactura'

const BASE = '/efactura/api'

export const efacturaApi = {
  // ── Connections ────────────────────────────────────────────
  getConnections: async () => {
    const res = await api.get<{ success: boolean; data: CompanyConnection[] }>(`${BASE}/connections`)
    return res.data
  },
  getConnection: async (cif: string) => {
    const res = await api.get<{ success: boolean; data: CompanyConnection }>(`${BASE}/connections/${cif}`)
    return res.data
  },
  createConnection: (data: { cif: string; display_name: string; environment?: string; config?: Record<string, unknown> }) =>
    api.post<{ success: boolean; data: CompanyConnection; message: string }>(`${BASE}/connections`, data),
  deleteConnection: (cif: string) =>
    api.delete<{ success: boolean; message: string }>(`${BASE}/connections/${cif}`),

  // ── Invoices ──────────────────────────────────────────────
  getInvoices: async (filters: EFacturaInvoiceFilters) => {
    const res = await api.get<{ success: boolean; data: EFacturaInvoice[]; pagination: Pagination }>(
      `${BASE}/invoices${buildQs(filters as Record<string, unknown>)}`,
    )
    return { invoices: res.data, pagination: res.pagination }
  },
  getInvoice: async (id: number) => {
    const res = await api.get<{ success: boolean; data: EFacturaInvoice }>(`${BASE}/invoices/${id}`)
    return res.data
  },
  getInvoiceSummary: async (cif: string, startDate?: string, endDate?: string) => {
    const res = await api.get<{ success: boolean; data: EFacturaInvoiceSummary }>(
      `${BASE}/invoices/summary${buildQs({ cif, start_date: startDate, end_date: endDate })}`,
    )
    return res.data
  },
  getInvoicePdfUrl: (id: number) => `${BASE}/invoices/${id}/pdf`,
  downloadArtifactUrl: (id: number, type: string) => `${BASE}/invoices/${id}/download/${type}`,

  // ── Unallocated Invoices ──────────────────────────────────
  getUnallocated: async (filters: EFacturaInvoiceFilters = {}) => {
    const res = await api.get<{
      success: boolean
      data: EFacturaInvoice[]
      companies: { id: number; name: string; cif: string }[]
      pagination: Pagination
    }>(`${BASE}/invoices/unallocated${buildQs(filters as Record<string, unknown>)}`)
    return { invoices: res.data, companies: res.companies, pagination: res.pagination }
  },
  getUnallocatedCount: async () => {
    const res = await api.get<{ success: boolean; count: number }>(`${BASE}/invoices/unallocated/count`)
    return res.count
  },
  getUnallocatedIds: async (filters?: Partial<EFacturaInvoiceFilters>) => {
    const res = await api.get<{ success: boolean; ids: number[]; count: number }>(
      `${BASE}/invoices/unallocated/ids${buildQs((filters ?? {}) as Record<string, unknown>)}`,
    )
    return res.ids
  },
  sendToModule: (invoiceIds: number[]) =>
    api.post<{ success: boolean; sent: number; duplicates: number; errors: string[] }>(
      `${BASE}/invoices/send-to-module`,
      { invoice_ids: invoiceIds },
    ),
  updateOverrides: (invoiceId: number, overrides: Record<string, string | null>) =>
    api.put<{ success: boolean }>(`${BASE}/invoices/${invoiceId}/overrides`, overrides),
  bulkUpdateOverrides: (invoiceIds: number[], overrides: Record<string, string | null>) =>
    api.put<{ success: boolean; updated_count: number }>(`${BASE}/invoices/bulk-overrides`, {
      invoice_ids: invoiceIds,
      ...overrides,
    }),

  // ── Hide / Delete / Restore ───────────────────────────────
  ignoreInvoice: (id: number, restore = false) =>
    api.post<{ success: boolean; invoice_id: number; ignored: boolean }>(`${BASE}/invoices/${id}/ignore`, { restore }),
  bulkHide: (invoiceIds: number[]) =>
    api.post<{ success: boolean; hidden: number }>(`${BASE}/invoices/bulk-hide`, { invoice_ids: invoiceIds }),
  bulkRestoreHidden: (invoiceIds: number[]) =>
    api.post<{ success: boolean; restored: number }>(`${BASE}/invoices/bulk-restore-hidden`, { invoice_ids: invoiceIds }),
  deleteInvoice: (id: number) =>
    api.post<{ success: boolean; invoice_id: number }>(`${BASE}/invoices/${id}/delete`, {}),
  restoreInvoice: (id: number) =>
    api.post<{ success: boolean; invoice_id: number }>(`${BASE}/invoices/${id}/restore`, {}),
  permanentDelete: (id: number) =>
    api.post<{ success: boolean; invoice_id: number }>(`${BASE}/invoices/${id}/permanent-delete`, {}),
  bulkDelete: (invoiceIds: number[]) =>
    api.post<{ success: boolean; deleted: number }>(`${BASE}/invoices/bulk-delete`, { invoice_ids: invoiceIds }),
  bulkRestoreBin: (invoiceIds: number[]) =>
    api.post<{ success: boolean; restored: number }>(`${BASE}/invoices/bulk-restore-bin`, { invoice_ids: invoiceIds }),
  bulkPermanentDelete: (invoiceIds: number[]) =>
    api.post<{ success: boolean; deleted: number }>(`${BASE}/invoices/bulk-permanent-delete`, { invoice_ids: invoiceIds }),

  // ── Hidden & Bin ──────────────────────────────────────────
  getHidden: async (filters: Partial<EFacturaInvoiceFilters> = {}) => {
    const res = await api.get<{ success: boolean; data: EFacturaInvoice[]; pagination: Pagination }>(
      `${BASE}/invoices/hidden${buildQs(filters as Record<string, unknown>)}`,
    )
    return { invoices: res.data, pagination: res.pagination }
  },
  getHiddenCount: async () => {
    const res = await api.get<{ success: boolean; count: number }>(`${BASE}/invoices/hidden/count`)
    return res.count
  },
  getBin: async (filters: Partial<EFacturaInvoiceFilters> = {}) => {
    const res = await api.get<{ success: boolean; data: EFacturaInvoice[]; pagination: Pagination }>(
      `${BASE}/invoices/bin${buildQs(filters as Record<string, unknown>)}`,
    )
    return { invoices: res.data, pagination: res.pagination }
  },
  getBinCount: async () => {
    const res = await api.get<{ success: boolean; count: number }>(`${BASE}/invoices/bin/count`)
    return res.count
  },

  // ── Duplicates ────────────────────────────────────────────
  getDuplicates: async () => {
    const res = await api.get<{ success: boolean; duplicates: DuplicateInvoice[]; count: number }>(
      `${BASE}/invoices/duplicates`,
    )
    return res.duplicates
  },
  markDuplicates: (invoiceIds: number[]) =>
    api.post<{ success: boolean; marked: number }>(`${BASE}/invoices/mark-duplicates`, { invoice_ids: invoiceIds }),
  getAiDuplicates: async (limit = 20) => {
    const res = await api.get<{ success: boolean; duplicates: DuplicateInvoice[]; count: number }>(
      `${BASE}/invoices/duplicates/ai?limit=${limit}`,
    )
    return res.duplicates
  },
  markAiDuplicates: (mappings: { efactura_id: number; existing_invoice_id: number }[]) =>
    api.post<{ success: boolean; marked: number }>(`${BASE}/invoices/mark-duplicates/ai`, { mappings }),

  // ── Sync ──────────────────────────────────────────────────
  triggerSync: (cif: string) =>
    api.post<{ success: boolean; message: string; note: string }>(`${BASE}/sync/trigger`, { cif }),
  getSyncHistory: async (cif?: string, limit = 20) => {
    const res = await api.get<{ success: boolean; data: SyncRun[] }>(
      `${BASE}/sync/history${buildQs({ cif, limit })}`,
    )
    return res.data
  },
  getSyncErrors: async (runId: string) => {
    const res = await api.get<{ success: boolean; data: SyncError[] }>(`${BASE}/sync/errors/${runId}`)
    return res.data
  },
  getErrorStats: async (cif?: string, hours = 24) => {
    const res = await api.get<{ success: boolean; data: ErrorStats }>(
      `${BASE}/sync/stats${buildQs({ cif, hours })}`,
    )
    return res.data
  },
  syncAll: (days = 60) =>
    api.post<{ success: boolean } & SyncAllResult>(`${BASE}/sync`, { days }),
  getSyncCompanies: async () => {
    const res = await api.get<{ success: boolean; companies: SyncCompany[]; count: number }>(
      `${BASE}/sync/companies`,
    )
    return res.companies
  },
  syncSingleCompany: (cif: string, days = 60) =>
    api.post<{ success: boolean; fetched: number; imported: number; skipped: number; errors: string[] }>(
      `${BASE}/sync/company`,
      { cif, days },
    ),

  // ── ANAF Live ─────────────────────────────────────────────
  fetchMessages: async (filters: ANAFFetchFilters) => {
    const res = await api.get<{
      success: boolean
      mock_mode: boolean
      data: {
        messages: ANAFMessage[]
        pagination: Pagination
        serial: string | null
        title: string | null
      }
    }>(`${BASE}/anaf/messages${buildQs(filters as unknown as Record<string, unknown>)}`)
    return { ...res.data, mock_mode: res.mock_mode }
  },
  downloadMessageUrl: (messageId: string, cif: string) => `${BASE}/anaf/download/${messageId}?cif=${cif}`,
  exportPdfUrl: (messageId: string, cif: string, standard = 'FACT1') =>
    `${BASE}/anaf/export-pdf/${messageId}?cif=${cif}&standard=${standard}`,
  getAnafStatus: async () => {
    const res = await api.get<{ success: boolean; data: ANAFStatus }>(`${BASE}/anaf/status`)
    return res.data
  },
  importFromAnaf: (cif: string, messageIds: string[]) =>
    api.post<{ success: boolean } & ImportResult>(`${BASE}/import`, { cif, message_ids: messageIds }),

  // ── Company Lookup ────────────────────────────────────────
  lookupCompany: async (cif: string) => {
    const res = await api.get<{ success: boolean; data: CompanyLookup }>(`${BASE}/company/lookup?cif=${cif}`)
    return res.data
  },
  lookupCompaniesBatch: async (cifs: string[]) => {
    const res = await api.post<{ success: boolean; data: Record<string, CompanyLookup> }>(
      `${BASE}/company/lookup-batch`,
      { cifs },
    )
    return res.data
  },

  // ── OAuth ─────────────────────────────────────────────────
  oauthAuthorizeUrl: (cif: string) => `/efactura/oauth/authorize?cif=${cif}`,
  oauthRevoke: (cif: string) =>
    api.post<{ success: boolean; message: string }>('/efactura/oauth/revoke', { cif }),
  getOAuthStatus: async (cif: string) => {
    const res = await api.get<{ success: boolean; data: OAuthStatus }>(`/efactura/oauth/status?cif=${cif}`)
    return res.data
  },
  refreshOAuth: (cif: string) =>
    api.post<{ success: boolean; message: string; expires_at: string }>('/efactura/oauth/refresh', { cif }),

  // ── Supplier Mappings ─────────────────────────────────────
  getMappings: async (activeOnly = true) => {
    const res = await api.get<{ success: boolean; mappings: SupplierMapping[]; count: number }>(
      `${BASE}/mappings${buildQs({ active_only: activeOnly })}`,
    )
    return res.mappings
  },
  getMapping: async (id: number) => {
    const res = await api.get<{ success: boolean; mapping: SupplierMapping }>(`${BASE}/mappings/${id}`)
    return res.mapping
  },
  createMapping: (data: {
    partner_name: string
    supplier_name: string
    partner_cif?: string
    supplier_note?: string
    supplier_vat?: string
    kod_konto?: string
    type_ids?: number[]
    brand?: string
    department?: string
    subdepartment?: string
  }) => api.post<{ success: boolean; id: number }>(`${BASE}/mappings`, data),
  updateMapping: (id: number, data: Partial<SupplierMapping>) =>
    api.put<{ success: boolean }>(`${BASE}/mappings/${id}`, data),
  deleteMapping: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/mappings/${id}`),
  lookupMapping: async (partnerName: string, partnerCif?: string) => {
    const res = await api.get<{ success: boolean; mapping: SupplierMapping | null; found: boolean }>(
      `${BASE}/mappings/lookup${buildQs({ partner_name: partnerName, partner_cif: partnerCif })}`,
    )
    return res.mapping
  },
  getDistinctSuppliers: async () => {
    const res = await api.get<{ success: boolean; partners: DistinctSupplier[]; count: number }>(
      `${BASE}/suppliers/distinct`,
    )
    return res.partners
  },
  bulkDeleteMappings: (ids: number[]) =>
    api.post<{ success: boolean; deleted_count: number }>(`${BASE}/mappings/bulk-delete`, { ids }),
  bulkSetMappingType: (ids: number[], typeName: string | null) =>
    api.post<{ success: boolean; updated: number }>(`${BASE}/mappings/bulk-set-type`, { ids, type_name: typeName }),

  // ── Supplier Types ─────────────────────────────────────────
  getSupplierTypes: async (activeOnly = true) => {
    const res = await api.get<{ success: boolean; types: SupplierType[]; count: number }>(
      `${BASE}/supplier-types${buildQs({ active_only: activeOnly, include_inactive: !activeOnly })}`,
    )
    return res.types
  },
  getSupplierType: async (id: number) => {
    const res = await api.get<{ success: boolean; type: SupplierType }>(`${BASE}/supplier-types/${id}`)
    return res.type
  },
  createSupplierType: (data: { name: string; description?: string; hide_in_filter?: boolean }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/supplier-types`, data),
  updateSupplierType: (id: number, data: Partial<SupplierType>) =>
    api.put<{ success: boolean }>(`${BASE}/supplier-types/${id}`, data),
  deleteSupplierType: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/supplier-types/${id}`),

  // ── Cleanup ──────────────────────────────────────────────
  cleanupOldUnallocated: (cif: string, days = 15) =>
    api.post<{ success: boolean; deleted: number }>(`${BASE}/invoices/cleanup-old`, { cif, days }),

  // ── Rate Limit ────────────────────────────────────────────
  getRateLimit: async () => {
    const res = await api.get<{ success: boolean; data: { max_per_hour: number; remaining: number; note: string } }>(
      `${BASE}/rate-limit`,
    )
    return res.data
  },
}
