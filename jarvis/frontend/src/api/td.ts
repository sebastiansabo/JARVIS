import { api } from './client'

export interface TdSlot {
  id: number
  car_id: number
  vin: string
  starts_at: string
  ends_at: string
}

export interface TdCar {
  id: number
  vin: string
  label: string
  plate?: string | null
}

export interface TdPublicPage {
  page: {
    title?: string
    intro?: string
    thank_you?: string
    logo_url?: string | null
    company_name?: string
    gdpr_text?: string | null
  }
  cars: TdCar[]
  slots: TdSlot[]
}

export const tdApi = {
  getPage: (slug: string) => api.get<TdPublicPage>(`/api/td/pages/${slug}`),

  submitBooking: (slug: string, body: {
    slot_id: number; name: string; phone: string; email: string
    license: string; license_expiry?: string
    gdpr_consent: boolean; conditions_accepted: boolean
    utm?: Record<string, string>
  }) => api.post<{ booking_id: number; status: string }>(`/api/td/pages/${slug}/bookings`, body),

  confirm: (token: string) =>
    api.post<{ status: string; fp_id?: number }>(`/api/td/bookings/confirm`, { token }),

  cancel: (token: string) =>
    api.post<{ status: string }>(`/api/td/bookings/cancel`, { token }),
}
