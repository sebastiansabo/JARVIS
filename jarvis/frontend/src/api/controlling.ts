import { api } from './client'
import { buildQs } from './utils'
import type { BabPeriod, BabUpload, MarjaReportData, BabEurRate, BabAccountGroup, BabConfigRow } from '@/types/controlling'

const BASE = '/controlling/bab/api'

export const controllingApi = {
  // Periods (12-month grid)
  getPeriods: (companyId: number) =>
    api.get<{ success: boolean; periods: BabPeriod[] }>(`${BASE}/periods${buildQs({ company_id: companyId })}`),

  // Uploads
  listUploads: (companyId: number) =>
    api.get<{ success: boolean; uploads: BabUpload[] }>(`${BASE}/uploads${buildQs({ company_id: companyId })}`),

  deleteUpload: (uploadId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/uploads/${uploadId}`),

  // Import BAB xlsx
  importBab: async (file: File, periodYear: number, periodMonth: number, companyId: number) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('period_year', String(periodYear))
    formData.append('period_month', String(periodMonth))
    formData.append('company_id', String(companyId))
    return api.post<{
      success: boolean
      upload_id: number
      period: string
      status: string
      import_count: number
      row_count: number
    }>(`${BASE}/import`, formData)
  },

  // Lock / Unlock
  lockUpload: (uploadId: number) =>
    api.post<{ success: boolean; upload: BabUpload }>(`${BASE}/uploads/${uploadId}/lock`),

  unlockUpload: (uploadId: number) =>
    api.post<{ success: boolean; upload: BabUpload }>(`${BASE}/uploads/${uploadId}/unlock`),

  // Report
  getReport: (uploadId: number) =>
    api.get<{ success: boolean; report: MarjaReportData; upload: BabUpload }>(`${BASE}/report/${uploadId}`),

  exportReport: (uploadId: number) =>
    `${BASE}/report/${uploadId}/export`,

  // EUR Rate
  getEurRate: (year: number, month: number, companyId: number) =>
    api.get<{ success: boolean; rate: BabEurRate | null }>(
      `${BASE}/eur-rate/${year}/${month}${buildQs({ company_id: companyId })}`),

  setEurRate: (year: number, month: number, companyId: number, eurRate: number) =>
    api.put<{ success: boolean; rate: BabEurRate }>(
      `${BASE}/eur-rate/${year}/${month}`, { company_id: companyId, eur_rate: eurRate }),

  // Verification (raw entries by account)
  getVerification: (uploadId: number) =>
    api.get<{ success: boolean; accounts: BabAccountGroup[]; total_entries: number; upload: BabUpload }>(
      `${BASE}/verification/${uploadId}`),

  // Report Config
  getConfig: (companyId: number) =>
    api.get<{ success: boolean; config: BabConfigRow[] }>(`${BASE}/config${buildQs({ company_id: companyId })}`),

  addConfigRow: (row: Partial<BabConfigRow>) =>
    api.post<{ success: boolean; row: BabConfigRow }>(`${BASE}/config`, row),

  updateConfigRow: (rowId: number, row: Partial<BabConfigRow>) =>
    api.put<{ success: boolean; row: BabConfigRow }>(`${BASE}/config/${rowId}`, row),

  deleteConfigRow: (rowId: number) =>
    api.delete<{ success: boolean }>(`${BASE}/config/${rowId}`),

  replaceConfig: (companyId: number, rows: Partial<BabConfigRow>[]) =>
    api.put<{ success: boolean; count: number }>(`${BASE}/config/bulk`, { company_id: companyId, rows }),

  // BNR rate auto-fetch
  getBnrRate: (year: number, month: number) =>
    api.get<{ success: boolean; eur_rate: number; rate_date: string }>(
      `${BASE}/bnr-rate${buildQs({ year, month })}`),

  // AI Analysis
  analyze: (companyId: number, mode: 'auto' | 'query', prompt?: string, crossCompany?: boolean) =>
    api.post<{ success: boolean; analysis: string; tokens_used: number }>(
      `${BASE}/analyze`, { company_id: companyId, mode, prompt, cross_company: crossCompany }),
}
