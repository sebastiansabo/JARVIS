import { api } from './client'

// AutoFox → JARVIS inbound photo webhook connector (CarPark).
// Admin-facing config/logs API; the webhook itself is called by AutoFox.

export interface AutofoxConnector {
  id: number
  status: string
  webhook_url: string
  token_preview: string
  allowed_ips: string[]
  replace_existing: boolean
  last_sync: string | null
  last_error: string | null
}

export interface AutofoxConfigResponse {
  success: boolean
  configured: boolean
  webhook_url: string
  connector?: AutofoxConnector
}

export interface AutofoxSaveResponse {
  success: boolean
  connector: AutofoxConnector
  // Full token + a ready-to-send curl are returned ONLY when (re)generated.
  token?: string
  curl_example?: string
}

export interface AutofoxLog {
  id: number
  sync_type: string
  status: string
  invoices_found: number
  invoices_imported: number
  error_message: string | null
  // JSON column: {ip, ip_allowed, vin, image_refs, multipart_files, raw, created, skipped_duplicates, errors}
  details: Record<string, unknown> | string | null
  created_at: string
}

export interface AutofoxSavePayload {
  rotate_token?: boolean
  allowed_ips?: string[]
  replace_existing?: boolean
  enabled?: boolean
}

// ── Sync-from-AutoFox (per-vehicle photo pull) ──

export interface AutofoxSyncPhoto {
  conversion_id: string
  path: string
  retouch_state: string | null
  date_modified: string | null
  vin: string
  already_imported: boolean
}

export interface AutofoxPhotosResponse {
  success: boolean
  vin: string
  matched_vehicle: boolean
  vehicle_id: number | null
  photos: AutofoxSyncPhoto[]
}

export interface AutofoxImportResponse {
  success: boolean
  vin: string
  vehicle_id: number
  created: number
  skipped_duplicates: number
  errors: string[]
}

const BASE = '/autofox/api'

export const autofoxApi = {
  getConfig: () => api.get<AutofoxConfigResponse>(`${BASE}/config`),

  saveConfig: (data: AutofoxSavePayload) =>
    api.post<AutofoxSaveResponse>(`${BASE}/config`, data),

  getLogs: async (limit = 20) => {
    const res = await api.get<{ success: boolean; logs: AutofoxLog[] }>(`${BASE}/logs`, {
      limit: String(limit),
    })
    return res.logs
  },

  // Pull: list what AutoFox has for a VIN, import selected, and a thumbnail proxy.
  listPhotos: (vin: string) =>
    api.get<AutofoxPhotosResponse>(`${BASE}/photos`, { vin }),

  importPhotos: (vin: string, conversionIds: string[]) =>
    api.post<AutofoxImportResponse>(`${BASE}/import`, { vin, conversion_ids: conversionIds }),

  // Browser can't send our Bearer to AutoFox → load thumbnails through JARVIS.
  imageProxyUrl: (path: string) => `${BASE}/image?path=${encodeURIComponent(path)}`,
}
