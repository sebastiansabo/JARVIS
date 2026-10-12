import { api } from './client'

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
  background_id?: string
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

export interface CbgEnhanceResponse {
  success: boolean
  created: number
  errors: string[]
}

export interface CbgPublishResponse {
  success: boolean
  published: boolean
}

export interface CbgDeleteEnhancedResponse {
  success: boolean
}

const BASE = '/carbackground/api'

export const carbackgroundApi = {
  getConfig: () => api.get<CbgConfigResponse>(`${BASE}/config`),

  saveConfig: (data: CbgSaveConfigPayload) =>
    api.post<CbgSaveConfigResponse>(`${BASE}/config`, data),

  listBackgrounds: () => api.get<CbgBackgroundsResponse>(`${BASE}/backgrounds`),

  credits: () => api.get<CbgCreditsResponse>(`${BASE}/credits`),

  enhance: (vehicleId: number, photoIds: number[]) =>
    api.post<CbgEnhanceResponse>(`${BASE}/vehicles/${vehicleId}/enhance`, {
      photo_ids: photoIds,
    }),

  setPublished: (photoId: number, published: boolean) =>
    api.put<CbgPublishResponse>(`${BASE}/photos/${photoId}/publish`, { published }),

  deleteEnhanced: (photoId: number) =>
    api.delete<CbgDeleteEnhancedResponse>(`${BASE}/photos/${photoId}/enhanced`),
}
