import { api } from './client'
import type { CheckinLocation, CheckinStatus, PunchResult } from '@/types/checkin'

const BASE = '/mobile-checkin/api'

export const checkinApi = {
  getLocations: async () => {
    const res = await api.get<{ success: boolean; data: CheckinLocation[] }>(`${BASE}/locations`)
    return res.data
  },

  getStatus: async () => {
    const res = await api.get<{ success: boolean; data: CheckinStatus }>(`${BASE}/status`)
    return res.data
  },

  punch: (data: { lat?: number; lng?: number; direction?: string; qr_token?: string }) =>
    api.post<PunchResult>(`${BASE}/punch`, data),

  // Admin
  getAllLocations: async () => {
    const res = await api.get<{ success: boolean; data: CheckinLocation[] }>(`${BASE}/locations?all=true`)
    return res.data
  },

  createLocation: (data: { name: string; latitude: number; longitude: number; allowed_radius_meters?: number; auto_checkout_radius_meters?: number; allowed_ips?: string[]; is_active?: boolean }) =>
    api.post<{ success: boolean; data: CheckinLocation }>(`${BASE}/locations`, data),

  updateLocation: (id: number, data: Partial<CheckinLocation>) =>
    api.put<{ success: boolean; data: CheckinLocation }>(`${BASE}/locations/${id}`, data),

  deleteLocation: (id: number) =>
    api.delete<{ success: boolean; message: string }>(`${BASE}/locations/${id}`),
}
