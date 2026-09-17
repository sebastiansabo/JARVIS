import { api } from './client'
import type {
  Statement,
  Transaction,
  VendorMapping,
  TransactionSummary,
  TransactionFilters,
  FilterOptions,
  UploadResult,
} from '@/types/statements'

const BASE = '/statements/api'

function buildQs(filters: TransactionFilters): string {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  })
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export const statementsApi = {
  // Statements (files)
  getStatements: (limit = 100, offset = 0) =>
    api.get<{ statements: Statement[]; total: number }>(`${BASE}/statements?limit=${limit}&offset=${offset}`),
  getStatement: (id: number) => api.get<Statement>(`${BASE}/statements/${id}`),
  deleteStatement: (id: number) => api.delete<{ success: boolean }>(`${BASE}/statements/${id}`),
  uploadStatements: async (files: File[]): Promise<UploadResult> => {
    const formData = new FormData()
    files.forEach((f) => formData.append('files', f))
    const response = await fetch(`${BASE}/upload`, {
      method: 'POST',
      body: formData,
      credentials: 'same-origin',
    })
    if (!response.ok) throw new Error(`Upload failed: ${response.status}`)
    return response.json()
  },

  // Transactions
  getTransactions: (filters: TransactionFilters = {}) =>
    api.get<{ transactions: Transaction[]; count: number; total: number }>(`${BASE}/transactions${buildQs(filters)}`),
  getTransaction: (id: number) => api.get<Transaction>(`${BASE}/transactions/${id}`),
  updateTransaction: (id: number, data: Partial<Pick<Transaction, 'matched_supplier' | 'status' | 'vendor_name'>>) =>
    api.put<{ success: boolean }>(`${BASE}/transactions/${id}`, data),
  bulkIgnore: (ids: number[]) =>
    api.post<{ success: boolean; updated_count: number }>(`${BASE}/transactions/bulk-ignore`, { transaction_ids: ids }),
  bulkUpdateStatus: (ids: number[], status: string) =>
    api.post<{ success: boolean; updated_count: number }>(`${BASE}/transactions/bulk-status`, { transaction_ids: ids, status }),
  getSummary: async (filters?: Omit<TransactionFilters, 'sort' | 'limit' | 'offset'>) => {
    const res = await api.get<{ summary: TransactionSummary }>(`${BASE}/summary${buildQs(filters ?? {})}`)
    return res.summary
  },
  getFilterOptions: async () => {
    const res = await api.get<FilterOptions & { success: boolean }>(`${BASE}/filters`)
    return { companies: res.companies, suppliers: res.suppliers } as FilterOptions
  },

  // Invoice linking
  linkInvoice: (transactionId: number, invoiceId: number) =>
    api.post<{ success: boolean }>(`${BASE}/transactions/link-invoice`, { transaction_id: transactionId, invoice_id: invoiceId }),
  unlinkInvoice: (transactionId: number) =>
    api.post<{ success: boolean }>(`${BASE}/transactions/${transactionId}/unlink`, {}),

  // Merging
  mergeTransactions: (ids: number[]) =>
    api.post<{ success: boolean; merged_transaction: Transaction }>(`${BASE}/transactions/merge`, { transaction_ids: ids }),
  unmergeTransaction: (id: number) =>
    api.post<{ success: boolean; restored_ids: number[]; restored_count: number }>(`${BASE}/transactions/${id}/unmerge`, {}),
  getMergedSources: (id: number) =>
    api.get<{ sources: Transaction[] }>(`${BASE}/transactions/${id}/merged-sources`),

  // Vendor mappings
  getMappings: async (activeOnly = false) => {
    const res = await api.get<{ mappings: VendorMapping[] }>(`${BASE}/mappings${activeOnly ? '?active_only=true' : ''}`)
    return res.mappings
  },
  getMapping: (id: number) => api.get<VendorMapping>(`${BASE}/mappings/${id}`),
  createMapping: (data: { pattern: string; supplier_name: string; supplier_vat?: string; template_id?: number }) =>
    api.post<{ success: boolean; mapping_id: number }>(`${BASE}/mappings`, data),
  updateMapping: (id: number, data: Partial<VendorMapping>) =>
    api.put<{ success: boolean }>(`${BASE}/mappings/${id}`, data),
  deleteMapping: (id: number) => api.delete<{ success: boolean }>(`${BASE}/mappings/${id}`),

  // Export
  exportUrl: (filters?: TransactionFilters) => `${BASE}/export/csv${buildQs(filters ?? {})}`,
}
