import { api } from './client'
import type {
  MktProject,
  MktProjectFilters,
  MktBudgetLine,
  MktBudgetTransaction,
  MktMember,
  MktProjectKpi,
  MktKpiSnapshot,
  MktKpiDefinition,
  MktKpiBudgetLine,
  MktKpiDependency,
  MktActivity,
  MktComment,
  MktFile,
  MktDashboardSummary,
  MktBudgetOverviewChannel,
  MktKpiScoreboardItem,
  MktProjectEvent,
  HrEventSearchResult,
  InvoiceSearchResult,
  SimBenchmark,
  SimSettings,
} from '@/types/marketing'

const BASE = '/marketing/api'

function toQs(params: Record<string, unknown>): string {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

export const marketingApi = {
  // ---- Projects ----

  listProjects: (filters?: MktProjectFilters) =>
    api.get<{ projects: MktProject[]; total: number }>(`${BASE}/projects${toQs({ ...filters })}`),

  getProject: (id: number) =>
    api.get<MktProject>(`${BASE}/projects/${id}`),

  createProject: (data: Partial<MktProject>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects`, data),

  updateProject: (id: number, data: Partial<MktProject>) =>
    api.put<{ success: boolean }>(`${BASE}/projects/${id}`, data),

  deleteProject: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/projects/${id}`),

  // Status transitions
  submitApproval: (id: number, approverId?: number) =>
    api.post<{ success: boolean; request_id?: number }>(`${BASE}/projects/${id}/submit-approval`, approverId ? { approver_id: approverId } : {}),

  activateProject: (id: number) =>
    api.post<{ success: boolean }>(`${BASE}/projects/${id}/activate`),

  pauseProject: (id: number) =>
    api.post<{ success: boolean }>(`${BASE}/projects/${id}/pause`),

  completeProject: (id: number) =>
    api.post<{ success: boolean }>(`${BASE}/projects/${id}/complete`),

  duplicateProject: (id: number, name?: string) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects/${id}/duplicate`, name ? { name } : {}),

  // ---- Members ----

  getMembers: (projectId: number) =>
    api.get<{ members: MktMember[] }>(`${BASE}/projects/${projectId}/members`),

  addMember: (projectId: number, data: { user_id: number; role: string; department_structure_id?: number }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects/${projectId}/members`, data),

  updateMember: (projectId: number, memberId: number, data: { role: string }) =>
    api.put<{ success: boolean }>(`${BASE}/projects/${projectId}/members/${memberId}`, data),

  removeMember: (projectId: number, memberId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/projects/${projectId}/members/${memberId}`),

  // ---- Budget Lines ----

  getBudgetLines: (projectId: number) =>
    api.get<{ budget_lines: MktBudgetLine[] }>(`${BASE}/projects/${projectId}/budget-lines`),

  createBudgetLine: (projectId: number, data: Partial<MktBudgetLine>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects/${projectId}/budget-lines`, data),

  updateBudgetLine: (projectId: number, lineId: number, data: Partial<MktBudgetLine>) =>
    api.put<{ success: boolean }>(`${BASE}/projects/${projectId}/budget-lines/${lineId}`, data),

  deleteBudgetLine: (projectId: number, lineId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/projects/${projectId}/budget-lines/${lineId}`),

  // ---- Budget Transactions ----

  getTransactions: (lineId: number) =>
    api.get<{ transactions: MktBudgetTransaction[] }>(`${BASE}/budget-lines/${lineId}/transactions`),

  createTransaction: (lineId: number, data: Partial<MktBudgetTransaction>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/budget-lines/${lineId}/transactions`, data),

  deleteTransaction: (txId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/budget-transactions/${txId}`),

  linkTransactionInvoice: (txId: number, invoiceId: number | null) =>
    api.put<{ success: boolean }>(`${BASE}/budget-transactions/${txId}/link-invoice`, { invoice_id: invoiceId }),

  updateTransaction: (txId: number, data: { amount?: number; transaction_date?: string; description?: string }) =>
    api.put<{ success: boolean }>(`${BASE}/budget-transactions/${txId}`, data),

  // ---- KPIs ----

  getProjectKpis: (projectId: number) =>
    api.get<{ kpis: MktProjectKpi[] }>(`${BASE}/projects/${projectId}/kpis`),

  addProjectKpi: (projectId: number, data: Partial<MktProjectKpi>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects/${projectId}/kpis`, data),

  updateProjectKpi: (projectId: number, kpiId: number, data: Partial<MktProjectKpi>) =>
    api.put<{ success: boolean }>(`${BASE}/projects/${projectId}/kpis/${kpiId}`, data),

  deleteProjectKpi: (projectId: number, kpiId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/projects/${projectId}/kpis/${kpiId}`),

  addKpiSnapshot: (projectId: number, kpiId: number, data: { value: number; source?: string; notes?: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects/${projectId}/kpis/${kpiId}/snapshot`, data),

  getKpiSnapshots: (projectKpiId: number, limit?: number) =>
    api.get<{ snapshots: MktKpiSnapshot[] }>(`${BASE}/kpi-snapshots/${projectKpiId}${limit ? `?limit=${limit}` : ''}`),

  // ---- KPI Definitions (admin) ----

  getKpiDefinitions: (activeOnly = true) =>
    api.get<{ definitions: MktKpiDefinition[] }>(`${BASE}/kpi-definitions?active_only=${activeOnly}`),

  createKpiDefinition: (data: Partial<MktKpiDefinition>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/kpi-definitions`, data),

  updateKpiDefinition: (id: number, data: Partial<MktKpiDefinition>) =>
    api.put<{ success: boolean }>(`${BASE}/kpi-definitions/${id}`, data),

  // ---- Comments ----

  getComments: (projectId: number, includeInternal = false) =>
    api.get<{ comments: MktComment[] }>(`${BASE}/projects/${projectId}/comments${includeInternal ? '?include_internal=true' : ''}`),

  createComment: (projectId: number, data: { content: string; parent_id?: number; is_internal?: boolean }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects/${projectId}/comments`, data),

  updateComment: (commentId: number, data: { content: string }) =>
    api.put<{ success: boolean }>(`${BASE}/comments/${commentId}`, data),

  deleteComment: (commentId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/comments/${commentId}`),

  // ---- Files ----

  getFiles: (projectId: number) =>
    api.get<{ files: MktFile[] }>(`${BASE}/projects/${projectId}/files`),

  createFile: (projectId: number, data: { file_name: string; storage_uri: string; file_type?: string; mime_type?: string; file_size?: number; description?: string }) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects/${projectId}/files`, data),

  deleteFile: (fileId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/files/${fileId}`),

  // ---- Activity ----

  getActivity: (projectId: number, limit = 50, offset = 0) =>
    api.get<{ activity: MktActivity[] }>(`${BASE}/projects/${projectId}/activity?limit=${limit}&offset=${offset}`),

  // ---- Dashboard ----

  getDashboardSummary: () =>
    api.get<{ summary: MktDashboardSummary }>(`${BASE}/dashboard/summary`),

  getBudgetOverview: () =>
    api.get<{ channels: MktBudgetOverviewChannel[] }>(`${BASE}/dashboard/budget-overview`),

  getKpiScoreboard: () =>
    api.get<{ kpis: MktKpiScoreboardItem[] }>(`${BASE}/dashboard/kpi-scoreboard`),

  // ---- Reports ----

  getReportBudgetVsActual: () =>
    api.get<{ projects: Record<string, unknown>[] }>(`${BASE}/reports/budget-vs-actual`),

  getReportChannelPerformance: () =>
    api.get<{ channels: Record<string, unknown>[] }>(`${BASE}/reports/channel-performance`),

  // ---- Project Events (HR linking) ----

  getProjectEvents: (projectId: number) =>
    api.get<{ events: MktProjectEvent[] }>(`${BASE}/projects/${projectId}/events`),

  linkEvent: (projectId: number, eventId: number, notes?: string) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/projects/${projectId}/events`, { event_id: eventId, notes }),

  unlinkEvent: (projectId: number, eventId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/projects/${projectId}/events/${eventId}`),

  searchHrEvents: (q?: string, limit = 20) =>
    api.get<{ events: HrEventSearchResult[] }>(`${BASE}/hr-events/search${toQs({ q, limit })}`),

  // ---- Invoice search (for budget linking) ----

  searchInvoices: (q?: string, company?: string, limit = 20) =>
    api.get<{ invoices: InvoiceSearchResult[] }>(`${BASE}/invoices/search${toQs({ q, company, limit })}`),

  uploadFile: (projectId: number, file: File, description?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (description) form.append('description', description)
    return api.post<{ success: boolean; id: number; drive_link: string; file_name: string; file_size: number }>(
      `${BASE}/projects/${projectId}/files/upload`, form,
    )
  },

  // ---- KPI ↔ Budget Line linking ----

  getKpiBudgetLines: (kpiId: number) =>
    api.get<{ budget_lines: MktKpiBudgetLine[] }>(`${BASE}/kpis/${kpiId}/budget-lines`),

  linkKpiBudgetLine: (kpiId: number, budgetLineId: number, role: string = 'input') =>
    api.post<{ success: boolean; id: number }>(`${BASE}/kpis/${kpiId}/budget-lines`, { budget_line_id: budgetLineId, role }),

  unlinkKpiBudgetLine: (kpiId: number, lineId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/kpis/${kpiId}/budget-lines/${lineId}`),

  // ---- KPI ↔ KPI dependencies ----

  getKpiDependencies: (kpiId: number) =>
    api.get<{ dependencies: MktKpiDependency[] }>(`${BASE}/kpis/${kpiId}/dependencies`),

  linkKpiDependency: (kpiId: number, dependsOnKpiId: number, role: string) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/kpis/${kpiId}/dependencies`, { depends_on_kpi_id: dependsOnKpiId, role }),

  unlinkKpiDependency: (kpiId: number, depKpiId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/kpis/${kpiId}/dependencies/${depKpiId}`),

  // ---- KPI Sync ----

  syncKpi: (kpiId: number) =>
    api.post<{ success: boolean; synced: boolean; value?: number }>(`${BASE}/kpis/${kpiId}/sync`),

  syncAllKpis: (projectId: number) =>
    api.post<{ success: boolean; synced_count: number }>(`${BASE}/projects/${projectId}/kpis/sync-all`),

  // ---- Formula validation ----

  validateFormula: (formula: string) =>
    api.post<{ valid: boolean; error: string | null; variables: string[] }>(`${BASE}/kpi-formulas/validate`, { formula }),

  // ---- Benchmarks ----

  generateBenchmarks: (defId: number) =>
    api.post<{ success: boolean; benchmarks: import('@/types/marketing').KpiBenchmarks }>(`${BASE}/kpi-definitions/${defId}/generate-benchmarks`),

  // ---- Campaign Simulator ----

  getSimBenchmarks: () =>
    api.get<{ benchmarks: SimBenchmark[] }>(`${BASE}/simulator/benchmarks`),

  updateSimBenchmark: (id: number, data: { cpc?: number; cvr_lead?: number; cvr_car?: number }) =>
    api.put<{ success: boolean }>(`${BASE}/simulator/benchmarks/${id}`, data),

  bulkUpdateSimBenchmarks: (updates: { id: number; cpc?: number; cvr_lead?: number; cvr_car?: number }[]) =>
    api.put<{ success: boolean; updated: number }>(`${BASE}/simulator/benchmarks/bulk`, { updates }),

  aiDistribute: (data: {
    total_budget: number
    audience_size: number
    lead_to_sale_rate: number
    active_channels: Record<string, string[]>
    benchmarks: SimBenchmark[]
  }) =>
    api.post<{ success: boolean; allocations: Record<string, number>; reasoning: string; total_allocated: number }>(`${BASE}/simulator/ai-distribute`, data),

  createSimChannel: (data: {
    channel_label: string; funnel_stage: string
    months: { month_index: number; cpc: number; cvr_lead: number; cvr_car: number }[]
  }) =>
    api.post<{ success: boolean; channel_key: string; ids: number[] }>(`${BASE}/simulator/benchmarks`, data),

  deleteSimChannel: (channelKey: string) =>
    api.delete<{ success: boolean; deleted: number }>(`${BASE}/simulator/benchmarks/channel/${channelKey}`),

  getSimSettings: () =>
    api.get<{ settings: SimSettings }>(`${BASE}/simulator/settings`),

  updateSimSettings: (data: Partial<SimSettings>) =>
    api.put<{ success: boolean }>(`${BASE}/simulator/settings`, data),
}
