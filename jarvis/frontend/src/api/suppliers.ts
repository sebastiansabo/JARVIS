import { api } from '@/api/client'

export interface KontoConfig {
  konto_debit: string | null
  konto_credit: string | null
  klient: string | null
  gegenkonto_debit: string | null
  gegenkonto_credit: string | null
  kostenstelle_debit: string | null
  kostenstelle_credit: string | null
  extbeleg_debit: string | null
  extbeleg_credit: string | null
  steuercode: string | null
  text_template: string | null
  belegart: string | null
}

export interface MasterSupplier extends Partial<KontoConfig> {
  id: number
  name: string
  cui?: string | null
  nr_reg_com?: string | null
  ref_no?: string | null
  is_active?: boolean
  has_company_config?: boolean
  aliases?: { id: number; alias_name: string | null; alias_cui_normalized: string | null; source: string }[]
}

export interface WorklistItem {
  source: 'efactura' | 'invoice'
  partner_name: string
  partner_cif: string | null
  count?: number
  candidate_id: number | null
  confidence: 'medium' | 'low' | 'none'
  method: string
}

/** A distinct e-Factura *supplier* partner (received invoice) not yet linked to the master —
 * a candidate row in the "Sync cu e-Factura" import modal. `existing` (with candidate_id/name)
 * means it already resolves to a master supplier, so the UI defaults it unchecked (link, not create). */
export interface EfacturaPartner {
  partner_name: string
  partner_cif: string | null
  count: number
  existing: boolean
  candidate_id: number | null
  candidate_name: string | null
  confidence: 'high' | 'medium' | 'low' | 'none'
}

export interface BudgetedInvoice {
  id: number
  supplier: string
  invoice_number: string
  invoice_date: string
  net_value: number | null
  invoice_value: number
  value_ron: number | null
  value_eur: number | null
  currency: string
  status: string
  supplier_id: number
}

/** Trigger a browser download for a raw fetch Response that carries a file (blob) body,
 * using the filename from its Content-Disposition header (falling back to `fallbackFilename`).
 * Mirrors the download helpers in api/bilant.ts and Hub/Profile's handleDownloadPdf. */
async function _triggerFileDownload(res: Response, fallbackFilename: string): Promise<void> {
  const blob = await res.blob()
  const filename = res.headers.get('Content-Disposition')?.match(/filename="?([^";\n]+)"?/)?.[1] || fallbackFilename
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** POST a body via a raw fetch (the shared `api` client always parses JSON, but these two
 * endpoints return a CSV/ZIP file download) and trigger a browser download of the response.
 * The export routes return 200 + JSON (not a file) when there is nothing to export — that
 * case, and any non-OK response, is surfaced as a thrown Error for the caller to toast. */
async function _downloadPost(path: string, body: unknown, fallbackFilename: string): Promise<void> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const contentType = res.headers.get('Content-Type') || ''
  if (!res.ok || contentType.includes('application/json')) {
    let message = 'Exportul a eșuat'
    try {
      const data = await res.json()
      if (Array.isArray(data?.skipped) && data.skipped.length > 0) {
        message = 'Nicio factură validă de exportat (configurație EuroFib incompletă sau sume lipsă)'
      } else if (data?.error) {
        message = String(data.error)
      }
    } catch {
      // response body wasn't JSON — keep the default message
    }
    throw new Error(message)
  }
  await _triggerFileDownload(res, fallbackFilename)
}

export const suppliersApi = {
  list: (companyId?: number, search?: string) => {
    const params = new URLSearchParams()
    if (companyId !== undefined) params.set('company_id', String(companyId))
    if (search) params.set('search', search)
    const qs = params.toString()
    return api.get<{ success: boolean; suppliers: MasterSupplier[] }>(`/api/suppliers${qs ? `?${qs}` : ''}`)
  },
  get: (id: number) =>
    api.get<{ success: boolean; supplier: MasterSupplier }>(`/api/suppliers/${id}`),
  create: (data: Partial<MasterSupplier>) =>
    api.post<{ success: boolean; id: number }>(`/api/suppliers`, data),
  update: (id: number, data: Partial<MasterSupplier>) =>
    api.put<{ success: boolean }>(`/api/suppliers/${id}`, data),
  addAlias: (id: number, alias_name?: string, alias_cui?: string) =>
    api.post<{ success: boolean; id: number }>(`/api/suppliers/${id}/aliases`, { alias_name, alias_cui }),
  merge: (survivor_id: number, duplicate_id: number) =>
    api.post<{ success: boolean }>(`/api/suppliers/merge`, { survivor_id, duplicate_id }),
  worklist: (companyId?: number) =>
    api.get<{ success: boolean; items: WorklistItem[] }>(`/api/suppliers/worklist${companyId !== undefined ? `?company_id=${companyId}` : ''}`),
  fetchInvoices: (companyId: number, startDate: string, endDate: string, status?: string) =>
    api.get<{ success: boolean; invoices: BudgetedInvoice[] }>(
      `/api/suppliers/invoices?company_id=${companyId}&start_date=${startDate}&end_date=${endDate}`
      + (status ? `&status=${encodeURIComponent(status)}` : '')),
  resolve: (body: { action: 'link' | 'create' | 'ignore'; partner_name: string; partner_cif?: string | null; supplier_id?: number }) =>
    api.post<{ success: boolean; supplier_id?: number; efactura_linked?: number }>(`/api/suppliers/resolve`, body),
  /** Distinct e-Factura supplier partners (received invoices) not yet in the master — the
   * "Sync cu e-Factura" picker. Company-scoped when companyId is given. */
  efacturaPartners: (companyId?: number) =>
    api.get<{ success: boolean; partners: EfacturaPartner[] }>(
      `/api/suppliers/efactura-partners${companyId !== undefined ? `?company_id=${companyId}` : ''}`),
  /** Bulk-import the selected e-Factura partners: new ones are created, ones matching an existing
   * master supplier are linked (no duplicate). */
  importEfactura: (partners: { partner_name: string; partner_cif: string | null }[]) =>
    api.post<{ success: boolean; created: number; linked: number; skipped: { partner_name: string; reason: string }[] }>(
      '/api/suppliers/import-efactura', { partners }),
  backfillEfactura: () =>
    api.post<{ success: boolean; bound: number }>(`/api/suppliers/backfill-efactura`, {}),
  getKonto: (id: number, companyId: number) =>
    api.get<{ success: boolean; konto: KontoConfig; has_company_config: boolean }>(`/api/suppliers/${id}/konto?company_id=${companyId}`),
  updateKonto: (id: number, companyId: number, fields: Partial<KontoConfig>, replicateAll?: boolean) =>
    api.put<{ success: boolean; id?: number; replicated?: number }>(
      `/api/suppliers/${id}/konto?company_id=${companyId}`,
      replicateAll ? { ...fields, replicate_all: true } : fields),
  /** EuroFib MEDLINE single-file download (CSV or XLSX) — one supplier's invoices, an explicit
   * invoiceIds set, or all budgeted invoices for the period when invoiceIds is omitted;
   * grouped/ordered per build_csv. */
  exportCsv: (companyId: number, startDate: string, endDate: string, invoiceIds?: number[], format: 'csv' | 'xlsx' = 'csv') =>
    _downloadPost(
      '/api/suppliers/export',
      { company_id: companyId, start_date: startDate, end_date: endDate, invoice_ids: invoiceIds, format },
      `eurofib_${companyId}_${startDate}_${endDate}.${format}`),
  /** Revert exported invoices back to 'Bugetata' (send to In lucru). */
  unprocess: (invoiceIds: number[]) =>
    api.post<{ success: boolean; reverted: number }>('/api/suppliers/unprocess', { invoice_ids: invoiceIds }),
}
