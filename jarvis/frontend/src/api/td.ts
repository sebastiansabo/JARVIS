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
}

export interface TdPublicPage {
  page: { title?: string; intro?: string; thank_you?: string; company_name?: string }
  cars: TdCar[]
  slots: TdSlot[]
}

export const tdApi = {
  getPage: (slug: string) => api.get<TdPublicPage>(`/api/td/pages/${slug}`),

  submitBooking: (slug: string, body: {
    slot_id: number; name: string; phone: string; email: string
    utm?: Record<string, string>
  }) => api.post<{ booking_id: number; status: string }>(`/api/td/pages/${slug}/bookings`, body),

  confirm: (token: string) =>
    api.post<{ status: string; fp_id?: number }>(`/api/td/bookings/confirm`, { token }),

  cancel: (token: string) =>
    api.post<{ status: string }>(`/api/td/bookings/cancel`, { token }),
}
