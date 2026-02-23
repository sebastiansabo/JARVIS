import { api } from './client'
import type {
  BilantTemplate,
  BilantTemplateRow,
  BilantMetricConfig,
  BilantGeneration,
  BilantGenerationDetail,
  ChartOfAccount,
} from '@/types/bilant'

const BASE = '/bilant/api'

function toQs(params: Record<string, unknown>): string {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

export const bilantApi = {
  // ── Templates ──

  listTemplates: (companyId?: number) =>
    api.get<{ templates: BilantTemplate[] }>(`${BASE}/templates${toQs({ company_id: companyId })}`),

  getTemplate: (id: number) =>
    api.get<{ template: BilantTemplate; rows: BilantTemplateRow[]; metrics: BilantMetricConfig[] }>(`${BASE}/templates/${id}`),

  createTemplate: (data: { name: string; company_id?: number; description?: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/templates`, data),

  updateTemplate: (id: number, data: Partial<BilantTemplate>) =>
    api.put<{ success: boolean }>(`${BASE}/templates/${id}`, data),

  deleteTemplate: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/templates/${id}`),

  duplicateTemplate: (id: number, name: string) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/templates/${id}/duplicate`, { name }),

  importTemplate: (file: File, name: string, companyId?: number) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', name)
    if (companyId) fd.append('company_id', String(companyId))
    return api.post<{ success: boolean; template_id?: number; row_count?: number }>(`${BASE}/templates/import`, fd)
  },

  // ── Template Rows ──

  getRows: (templateId: number) =>
    api.get<{ rows: BilantTemplateRow[] }>(`${BASE}/templates/${templateId}/rows`),

  addRow: (templateId: number, data: Partial<BilantTemplateRow>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/templates/${templateId}/rows`, data),

  updateRow: (rowId: number, data: Partial<BilantTemplateRow>) =>
    api.put<{ success: boolean }>(`${BASE}/templates/rows/${rowId}`, data),

  deleteRow: (rowId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/templates/rows/${rowId}`),

  reorderRows: (templateId: number, rowIds: number[]) =>
    api.put<{ success: boolean }>(`${BASE}/templates/${templateId}/rows/reorder`, { row_ids: rowIds }),

  // ── Metric Configs ──

  getMetricConfigs: (templateId: number) =>
    api.get<{ metrics: BilantMetricConfig[] }>(`${BASE}/templates/${templateId}/metrics`),

  setMetricConfig: (templateId: number, data: Partial<BilantMetricConfig>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/templates/${templateId}/metrics`, data),

  deleteMetricConfig: (configId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/templates/metrics/${configId}`),

  // ── Generations ──

  listGenerations: (params?: { company_id?: number; limit?: number; offset?: number }) =>
    api.get<{ generations: BilantGeneration[]; total: number }>(`${BASE}/generations${toQs(params || {})}`),

  createGeneration: (file: File, templateId: number, companyId: number, periodLabel?: string, periodDate?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('template_id', String(templateId))
    fd.append('company_id', String(companyId))
    if (periodLabel) fd.append('period_label', periodLabel)
    if (periodDate) fd.append('period_date', periodDate)
    return api.post<{ success: boolean; generation_id?: number; row_count?: number; summary?: Record<string, number> }>(`${BASE}/generations`, fd)
  },

  getGeneration: (id: number) =>
    api.get<BilantGenerationDetail>(`${BASE}/generations/${id}`),

  deleteGeneration: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/generations/${id}`),

  updateNotes: (id: number, notes: string) =>
    api.put<{ success: boolean }>(`${BASE}/generations/${id}/notes`, { notes }),

  downloadGeneration: async (id: number) => {
    const res = await fetch(`${BASE}/generations/${id}/download`, { credentials: 'same-origin' })
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = res.headers.get('content-disposition')?.match(/filename="?(.+?)"?$/)?.[1] || `Bilant_${id}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },

  downloadTemplate: async () => {
    const res = await fetch(`${BASE}/template-download`, { credentials: 'same-origin' })
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'Jarvis_Bilant_template.xlsx'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },

  // ── Compare ──

  compareGenerations: (generationIds: number[]) =>
    api.post<{ generations: BilantGeneration[]; metrics: Record<string, unknown> }>(`${BASE}/compare`, { generation_ids: generationIds }),

  // ── Chart of Accounts (Plan de Conturi) ──

  listAccounts: (params?: { company_id?: number; account_class?: number; account_type?: string; search?: string }) =>
    api.get<{ accounts: ChartOfAccount[] }>(`${BASE}/chart-of-accounts${toQs(params || {})}`),

  createAccount: (data: { code: string; name: string; account_class: number; account_type?: string; parent_code?: string; company_id?: number }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/chart-of-accounts`, data),

  updateAccount: (id: number, data: Partial<ChartOfAccount>) =>
    api.put<{ success: boolean }>(`${BASE}/chart-of-accounts/${id}`, data),

  deleteAccount: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/chart-of-accounts/${id}`),

  autocompleteAccounts: (prefix: string, companyId?: number) =>
    api.get<{ accounts: Pick<ChartOfAccount, 'code' | 'name' | 'account_class' | 'account_type'>[] }>(
      `${BASE}/chart-of-accounts/autocomplete${toQs({ prefix, company_id: companyId })}`),
}
