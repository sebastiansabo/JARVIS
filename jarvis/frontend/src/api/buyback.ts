import { api } from './client'
import type { BuybackRecord, BuybackOffer, BuybackPhoto, BuybackEvent } from '../types/buyback'

const BASE = '/api/buyback'

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== null) sp.set(k, String(v))
  })
  return sp.toString() ? `?${sp.toString()}` : ''
}

export const buybackApi = {
  listRecords: (params?: {
    status?: string
    acquisition_type?: string
    company_id?: number
    q?: string
    date_from?: string
    date_to?: string
    page?: number
    per_page?: number
    sort_by?: string
    sort_dir?: string
  }) =>
    api.get<{ records: BuybackRecord[]; total: number; page: number; per_page: number }>(
      `${BASE}/records${qs(params ?? {})}`
    ),

  getRecord: (id: number) =>
    api.get<{ record: BuybackRecord; offers: BuybackOffer[]; photos: BuybackPhoto[]; events: BuybackEvent[] }>(
      `${BASE}/records/${id}`
    ),

  createRecord: (data: Partial<BuybackRecord> & { vin: string; brand: string; model: string; images?: string[] }) =>
    api.post<{ success: boolean; record: BuybackRecord; vin_in_carpark?: boolean }>(`${BASE}/records`, data),

  updateRecord: (id: number, data: Partial<BuybackRecord>) =>
    api.put<{ record: BuybackRecord }>(`${BASE}/records/${id}`, data),

  cancelRecord: (id: number, reason?: string) =>
    api.post(`${BASE}/records/${id}/cancel`, { reason }),

  reopenRecord: (id: number) =>
    api.post(`${BASE}/records/${id}/reopen`, {}),

  deleteRecord: (id: number) =>
    api.delete(`${BASE}/records/${id}`),

  postOffer: (id: number, data: { offer_type: 'initial' | 'final'; amount_eur: number; vat_status?: string; valid_until?: string; notes?: string }) =>
    api.post<{ offer: BuybackOffer }>(`${BASE}/records/${id}/offers`, data),

  recordDecision: (id: number, offerId: number, data: { decision: 'accepted' | 'declined'; decline_reason?: string }) =>
    api.post<{ record: BuybackRecord }>(`${BASE}/records/${id}/offers/${offerId}/decision`, data),

  saveInspection: (id: number, data: { inspection_rating?: number; reconditioning_cost_eur?: number; inspection_notes?: string }) =>
    api.put(`${BASE}/records/${id}/inspection`, data),

  uploadInspectionReport: (id: number, file: File) => {
    const f = new FormData()
    f.append('file', file)
    return api.post(`${BASE}/records/${id}/inspection/report`, f)
  },

  finalize: (id: number) =>
    api.post<{ record: BuybackRecord; handoff_error?: string }>(`${BASE}/records/${id}/finalize`, {}),

  retryHandoff: (id: number) =>
    api.post(`${BASE}/records/${id}/handoff/retry`, {}),

  getLookupOptions: () =>
    api.get<Record<string, { value: string; label: string }[]>>(`${BASE}/lookups/options`),

  searchCrmClients: (q: string) =>
    api.get<{ clients: any[] }>(`${BASE}/lookups/crm-clients/search${qs({ q })}`),

  createCrmClient: (data: Record<string, unknown>) =>
    api.post<{ client: any }>(`${BASE}/lookups/crm-clients`, data),

  searchCarparkVehicles: (q: string) =>
    api.get<{ vehicles: any[] }>(`${BASE}/lookups/carpark-vehicles/search${qs({ q })}`),

  listPhotos: (id: number) =>
    api.get<{ photos: BuybackPhoto[] }>(`${BASE}/records/${id}/photos`),

  uploadPhotos: (id: number, files: File[]) => {
    const f = new FormData()
    files.forEach((x) => f.append('files', x))
    return api.post<{ photos: BuybackPhoto[] }>(`${BASE}/records/${id}/photos/upload`, f)
  },

  reorderPhotos: (id: number, ids: number[]) =>
    api.post(`${BASE}/records/${id}/photos/reorder`, { ids }),

  deletePhoto: (id: number, photoId: number) =>
    api.delete(`${BASE}/records/${id}/photos/${photoId}`),
}
