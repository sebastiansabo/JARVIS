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
  resolve: (body: { action: 'link' | 'create' | 'ignore'; partner_name: string; partner_cif?: string | null; supplier_id?: number }) =>
    api.post<{ success: boolean; supplier_id?: number; efactura_linked?: number }>(`/api/suppliers/resolve`, body),
  backfillEfactura: () =>
    api.post<{ success: boolean; bound: number }>(`/api/suppliers/backfill-efactura`, {}),
  getKonto: (id: number, companyId: number) =>
    api.get<{ success: boolean; konto: KontoConfig; has_company_config: boolean }>(`/api/suppliers/${id}/konto?company_id=${companyId}`),
  updateKonto: (id: number, companyId: number, fields: Partial<KontoConfig>, replicateAll?: boolean) =>
    api.put<{ success: boolean; id?: number; replicated?: number }>(
      `/api/suppliers/${id}/konto?company_id=${companyId}`,
      replicateAll ? { ...fields, replicate_all: true } : fields),
}
