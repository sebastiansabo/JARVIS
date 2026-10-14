import { api } from './client'
import type { VehiclePhoto } from '../types/carpark'

// CarBackground → AI photo background removal/enhancement connector (CarPark).
// Admin config sets the API key + default background; the per-vehicle picker
// enhances selected photos and toggles which enhanced version is published.

export interface CbgBackground {
  id: string
  name: string
  preview_url?: string
}

export interface CbgConnector {
  id: number
  status: string
  has_api_key: boolean
  background_id: string | null
  // The curated set of backgrounds editors may choose from in the gallery.
  // Always includes `background_id` (the starred default) as a member.
  preferred_background_ids: string[]
  api_base_url: string
  last_error: string | null
}

export interface CbgConfigResponse {
  success: boolean
  configured: boolean
  connector?: CbgConnector
}

export interface CbgSaveConfigPayload {
  api_key?: string
  // The starred default — must be one of preferred_background_ids.
  background_id?: string
  preferred_background_ids?: string[]
}

export interface CbgSaveConfigResponse {
  success: boolean
  connector: CbgConnector
}

export interface CbgBackgroundsResponse {
  success: boolean
  backgrounds: CbgBackground[]
}

export interface CbgCreditsResponse {
  success: boolean
  balance: number
}

// Enhance is now async: the POST returns immediately once the job is queued; a
// daemon worker processes the photos. Poll enhanceStatus() for live progress.
export interface CbgEnhanceResponse {
  success: boolean
  queued: number
  job_id: number
}

export interface CbgEnhanceStatus {
  success: boolean
  running: boolean
  total: number
  done: number
  created: number
  errors: string[]
  background_id: string | null
}

export interface CbgPublishResponse {
  success: boolean
  photo: VehiclePhoto
}

const BASE = '/carbackground/api'

export const carbackgroundApi = {
  getConfig: () => api.get<CbgConfigResponse>(`${BASE}/config`),

  saveConfig: (data: CbgSaveConfigPayload) =>
    api.post<CbgSaveConfigResponse>(`${BASE}/config`, data),

  listBackgrounds: () => api.get<CbgBackgroundsResponse>(`${BASE}/backgrounds`),

  credits: () => api.get<CbgCreditsResponse>(`${BASE}/credits`),

  enhance: (vehicleId: number, photoIds: number[], backgroundId?: string) =>
    api.post<CbgEnhanceResponse>(`${BASE}/vehicles/${vehicleId}/enhance`, {
      photo_ids: photoIds,
      ...(backgroundId ? { background_id: backgroundId } : {}),
    }),

  enhanceStatus: (vehicleId: number) =>
    api.get<CbgEnhanceStatus>(`${BASE}/vehicles/${vehicleId}/enhance/status`),

  setPublished: (photoId: number, published: boolean) =>
    api.put<CbgPublishResponse>(`${BASE}/photos/${photoId}/publish`, { published }),

  deleteEnhanced: (photoId: number) =>
    api.delete<CbgPublishResponse>(`${BASE}/photos/${photoId}/enhanced`),
}
