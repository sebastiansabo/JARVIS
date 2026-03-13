import { api } from './client'
import { buildQs } from './utils'
import type { Invoice, InvoiceSummary, InvoiceFilters, SubmitInvoiceInput, InvoiceTemplate, DeptSuggestion, InvoiceDmsLink, DmsDocSearchResult, StoreToDmsResult } from '@/types/invoices'

export const invoicesApi = {
  // Invoice CRUD
  getInvoices: (filters: InvoiceFilters & { limit?: number; offset?: number; include_allocations?: boolean } = {}) =>
    api.get<Invoice[]>(`/api/db/invoices${buildQs(filters)}`),
  getInvoice: (id: number) => api.get<Invoice>(`/api/db/invoices/${id}`),
  updateInvoice: (id: number, data: Partial<Invoice>) => api.put<{ success: boolean }>(`/api/db/invoices/${id}`, data),
  deleteInvoice: (id: number) => api.delete<{ success: boolean }>(`/api/db/invoices/${id}`),
  restoreInvoice: (id: number) => api.post<{ success: boolean }>(`/api/db/invoices/${id}/restore`, {}),
  permanentDeleteInvoice: (id: number) => api.delete<{ success: boolean }>(`/api/db/invoices/${id}/permanent`),

  // Bulk operations
  bulkDelete: (ids: number[]) => api.post<{ success: boolean }>('/api/db/invoices/bulk-delete', { invoice_ids: ids }),
  bulkRestore: (ids: number[]) => api.post<{ success: boolean }>('/api/db/invoices/bulk-restore', { invoice_ids: ids }),
  bulkPermanentDelete: (ids: number[]) =>
    api.post<{ success: boolean }>('/api/db/invoices/bulk-permanent-delete', { invoice_ids: ids }),
  getDeletedInvoices: () => api.get<Invoice[]>('/api/db/invoices/bin'),

  // Allocations
  updateAllocations: (invoiceId: number, data: { allocations: Record<string, unknown>[]; send_notification?: boolean }) =>
    api.put<{ success: boolean }>(`/api/db/invoices/${invoiceId}/allocations`, data),
  updateAllocationComment: (allocationId: number, comment: string) =>
    api.put<{ success: boolean }>(`/api/allocations/${allocationId}/comment`, { comment }),
  updateDriveLink: (invoiceId: number, driveLink: string) =>
    api.put<{ success: boolean }>(`/api/invoices/${invoiceId}/drive-link`, { drive_link: driveLink }),

  // Bulk upload & save
  bulkParse: async (files: File[]): Promise<{
    success: boolean
    results: Array<{ filename: string; success: boolean; data?: Record<string, unknown>; error?: string; duplicate?: boolean }>
  }> => {
    const formData = new FormData()
    files.forEach((f) => formData.append('files[]', f))
    const response = await fetch('/api/invoices/bulk-parse', { method: 'POST', body: formData, credentials: 'same-origin' })
    if (!response.ok) throw new Error(`Bulk parse failed: ${response.status}`)
    return response.json()
  },
  bulkSubmit: (invoices: Array<SubmitInvoiceInput & Record<string, unknown>>) =>
    api.post<{
      success: boolean
      results: Array<{ invoice_number: string; success: boolean; invoice_id?: number; error?: string }>
      saved_count: number
      total: number
    }>('/api/invoices/bulk-submit', { invoices }),

  // Drive upload
  uploadToDrive: async (file: File, invoiceDate: string, company: string, invoiceNumber: string): Promise<{ success: boolean; drive_link?: string; error?: string }> => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('invoice_date', invoiceDate)
    formData.append('company', company)
    formData.append('invoice_number', invoiceNumber)
    const response = await fetch('/api/drive/upload', { method: 'POST', body: formData, credentials: 'same-origin' })
    return response.json()
  },

  // Submit & Parse
  submitInvoice: (data: SubmitInvoiceInput) => api.post<{ success: boolean; invoice_id: number }>('/api/submit', data),
  parseInvoice: async (file: File, templateId?: number): Promise<unknown> => {
    const formData = new FormData()
    formData.append('file', file)
    if (templateId) formData.append('template_id', String(templateId))
    const response = await fetch('/api/parse-invoice', {
      method: 'POST',
      body: formData,
      credentials: 'same-origin',
    })
    if (!response.ok) throw new Error(`Parse failed: ${response.status}`)
    return response.json()
  },
  listInvoiceFiles: () => api.get<string[]>('/api/invoices'),
  getTemplates: () => api.get<InvoiceTemplate[]>('/api/templates'),

  // Department suggestion
  suggestDepartment: (supplier: string) =>
    api.get<{ suggestions: DeptSuggestion[] }>(`/api/suggest-department?supplier=${encodeURIComponent(supplier)}`),

  // Search
  searchInvoices: (query: string, limit = 20) =>
    api.get<Invoice[]>(`/api/db/search?q=${encodeURIComponent(query)}&limit=${limit}`),
  checkInvoiceNumber: (number: string, excludeId?: number) =>
    api.get<{ exists: boolean }>(
      `/api/db/check-invoice-number?invoice_number=${encodeURIComponent(number)}${excludeId ? `&exclude_id=${excludeId}` : ''}`,
    ),

  // Summaries
  getCompanySummary: (filters?: InvoiceFilters) =>
    api.get<InvoiceSummary[]>(`/api/db/summary/company${buildQs(filters ?? {})}`),
  getDepartmentSummary: (filters?: InvoiceFilters) =>
    api.get<InvoiceSummary[]>(`/api/db/summary/department${buildQs(filters ?? {})}`),
  getBrandSummary: (filters?: InvoiceFilters) =>
    api.get<InvoiceSummary[]>(`/api/db/summary/brand${buildQs(filters ?? {})}`),
  getSupplierSummary: (filters?: InvoiceFilters) =>
    api.get<InvoiceSummary[]>(`/api/db/summary/supplier${buildQs(filters ?? {})}`),

  // ---- DMS Document Links ----

  getInvoiceDmsDocuments: (invoiceId: number) =>
    api.get<{ documents: InvoiceDmsLink[] }>(`/api/invoices/${invoiceId}/dms-documents`),

  linkDmsDocument: (invoiceId: number, documentId: number) =>
    api.post<{ success: boolean; id: number }>(`/api/invoices/${invoiceId}/dms-documents`, { document_id: documentId }),

  unlinkDmsDocument: (invoiceId: number, documentId: number) =>
    api.delete<{ success: boolean }>(`/api/invoices/${invoiceId}/dms-documents/${documentId}`),

  searchDmsDocuments: (q?: string, limit = 20) =>
    api.get<{ documents: DmsDocSearchResult[] }>(
      `/api/invoices/dms-search${q ? `?q=${encodeURIComponent(q)}&limit=${limit}` : `?limit=${limit}`}`,
    ),

  // ---- Store to DMS ----
  storeToDms: (invoiceIds: number[]) =>
    api.post<StoreToDmsResult>('/api/invoices/store-to-dms', { invoice_ids: invoiceIds }),
}
