import { api } from './client'
import type { FSClientSearch } from './fieldSales'
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
  TransferDestination,
  TransferOut,
  TransferBody,
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
    companyId?: number | null,
  ) => {
    const params: Record<string, string> = {
      page: String(page),
      per_page: String(perPage),
      sort_by: sortBy,
      sort_dir: sortDir,
      ...filterParams(filters),
    }
    if (companyId != null) params.company_id = String(companyId)
    return api.get<DispoSummaryResponse>('/api/carpark/dispo/summary', params)
  },

  getKpis: (companyId?: number | null) => {
    const params: Record<string, string> = {}
    if (companyId != null) params.company_id = String(companyId)
    return api.get<DispoKpis>('/api/carpark/dispo/kpis', params)
  },

  // ── CRM client search (carpark-scoped) ──────────────────
  // Same response shape as fieldSalesApi.searchClients, gated on carpark
  // access instead of field_sales_required so a CarPark editor without
  // field-sales access isn't 403'd. Scoped server-side to the caller's own
  // company — companyId here is forwarded but the backend ignores it.
  searchClients: (q: string, companyId?: number) => {
    const params: Record<string, string> = { q }
    if (companyId && companyId > 0) params.company_id = String(companyId)
    return api.get<{ success: boolean; clients: FSClientSearch[]; count: number }>(
      '/api/carpark/clients/search',
      params,
    )
  },

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

  // ── Inter-company transfer (AutoWorld group) ─────────────
  // Sibling companies in the caller's AutoWorld group, EXCLUDING the
  // caller's own company (transfer_repository.group_companies) — feeds
  // TransferDialog's destination picker. A non-AutoWorld (single-member
  // group) company gets `companies: []` — handled gracefully by the dialog.
  getTransferDestinations: () =>
    api.get<{ companies: TransferDestination[] }>('/api/carpark/vehicles/transfer-destinations'),

  // Accepts either a FormData (multipart UPLOAD MODE — file + to_company_id
  // etc as form fields, only available when Google Drive is enabled server-
  // side) or a plain JSON body (LINK MODE — file_url/dms_document_id),
  // exactly like uploadDocument above. Returns the moved vehicle + the
  // carpark_transfers log row (transfers.py's transfer_vehicle route).
  transfer: (vehicleId: number, data: FormData | TransferBody) =>
    api.post<{ vehicle: Vehicle; transfer: TransferOut }>(`/api/carpark/vehicles/${vehicleId}/transfer`, data),

  // Caller company's OUTBOUND transfer history — not yet rendered anywhere
  // (later "ghost" row task), but the client method is added now so that
  // task only needs to build UI on top of it.
  getTransfersOut: () => api.get<{ transfers: TransferOut[] }>('/api/carpark/vehicles/transfers-out'),

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
  exportUrl: (filters: DispoFilters = {}, companyId?: number | null) => {
    const params: Record<string, string> = { export: 'xlsx', ...filterParams(filters) }
    if (companyId != null) params.company_id = String(companyId)
    const qs = new URLSearchParams(params).toString()
    return `/api/carpark/dispo/summary?${qs}`
  },
}
