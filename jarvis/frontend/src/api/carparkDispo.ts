import { api } from './client'
import type {
  DispoFilters,
  DispoSummaryResponse,
  DispoKpis,
  DispoReservation,
  DispoDocument,
  DispoDocumentLinkBody,
  DocumentChecklist,
  TimelineEvent,
  SaleType,
  Vehicle,
} from '../types/carpark'

// Query-string params shared by getSummary and exportUrl: every non-empty
// DispoFilters entry, verbatim (matches dispo.py's _SUMMARY_FILTER_KEYS).
function filterParams(filters: DispoFilters): Record<string, string> {
  const params: Record<string, string> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === '') continue
    params[k] = String(v)
  }
  return params
}

export const carparkDispoApi = {
  // ── Summary / KPIs ───────────────────────────────────────
  getSummary: (
    filters: DispoFilters = {},
    page = 1,
    perPage = 25,
    sortBy = 'acquisition_date',
    sortDir = 'desc',
  ) => {
    const params: Record<string, string> = {
      page: String(page),
      per_page: String(perPage),
      sort_by: sortBy,
      sort_dir: sortDir,
      ...filterParams(filters),
    }
    return api.get<DispoSummaryResponse>('/api/carpark/dispo/summary', params)
  },

  getKpis: () => api.get<DispoKpis>('/api/carpark/dispo/kpis'),

  // ── Guarded lifecycle transitions ───────────────────────
  reserve: (
    vehicleId: number,
    body: {
      client_name?: string
      client_id?: number
      reservation_end: string
      reservation_start?: string
      client_company?: string
      client_phone?: string
      client_email?: string
      deposit_amount?: number
      deposit_paid?: boolean
      notes?: string
    },
  ) =>
    api.post<{ vehicle: Vehicle; reservation: DispoReservation }>(
      `/api/carpark/vehicles/${vehicleId}/reserve`,
      body,
    ),

  sell: (
    vehicleId: number,
    body: {
      sale_price: number
      sale_type: SaleType
      sale_date: string
      buyer_name?: string
      // Explicit null (not just absence) matters: it tells sell() to CLEAR a
      // stale CRM link when the buyer switches to a free-text/walk-in name.
      buyer_client_id?: number | null
      confirm_low_margin?: boolean
    },
  ) => api.post<{ vehicle: Vehicle }>(`/api/carpark/vehicles/${vehicleId}/sell`, body),

  deliver: (vehicleId: number, body: { delivery_date: string }) =>
    api.post<{ vehicle: Vehicle }>(`/api/carpark/vehicles/${vehicleId}/deliver`, body),

  removeFromStock: (vehicleId: number, body?: Record<string, unknown>) =>
    api.post<{ vehicle: Vehicle }>(`/api/carpark/vehicles/${vehicleId}/remove-from-stock`, body),

  reopen: (vehicleId: number, body: { reason: string; target_status: string }) =>
    api.post<{ vehicle: Vehicle }>(`/api/carpark/vehicles/${vehicleId}/reopen`, body),

  // ── Reservations ─────────────────────────────────────────
  cancelReservation: (vehicleId: number, body: { reason: string }) =>
    api.post<{ vehicle: Vehicle; reservation: DispoReservation }>(
      `/api/carpark/vehicles/${vehicleId}/cancel-reservation`,
      body,
    ),

  getReservations: (vehicleId: number) =>
    api.get<{ reservations: DispoReservation[] }>(`/api/carpark/vehicles/${vehicleId}/reservations`),

  // ── Documents ────────────────────────────────────────────
  getDocuments: (vehicleId: number) =>
    api.get<{ documents: DispoDocument[] }>(`/api/carpark/vehicles/${vehicleId}/documents`),

  // Accepts either a FormData (multipart UPLOAD MODE, only available when
  // Google Drive integration is enabled server-side) or a plain JSON body
  // (LINK MODE, always available) — api.post auto-detects FormData and
  // drops the JSON content-type header for it.
  uploadDocument: (vehicleId: number, data: FormData | DispoDocumentLinkBody) =>
    api.post<{ document: DispoDocument }>(`/api/carpark/vehicles/${vehicleId}/documents`, data),

  deleteDocument: (docId: number) =>
    api.delete<{ success: boolean }>(`/api/carpark/documents/${docId}`),

  getChecklist: (vehicleId: number) =>
    api.get<DocumentChecklist>(`/api/carpark/vehicles/${vehicleId}/documents/checklist`),

  getTimeline: (vehicleId: number) =>
    api.get<{ timeline: TimelineEvent[] }>(`/api/carpark/vehicles/${vehicleId}/timeline`),

  // ── Export ───────────────────────────────────────────────
  // Not routed through api.get: this is a direct-download URL (xlsx binary
  // response), meant for an <a href> / window.location, not a fetch() call.
  exportUrl: (filters: DispoFilters = {}) => {
    const params = { export: 'xlsx', ...filterParams(filters) }
    const qs = new URLSearchParams(params).toString()
    return `/api/carpark/dispo/summary?${qs}`
  },
}
