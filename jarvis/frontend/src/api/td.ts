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
    conditions_text?: string | null
    logo_url?: string | null
    company_name?: string
    gdpr_text?: string | null
  }
  cars: TdCar[]
  slots: TdSlot[]
}

/** One created booking in a group (a car+interval that was actually reserved). */
export interface TdBooked {
  booking_id: number
  slot_id: number
  car_id: number
  starts_at: string | null
  ends_at: string | null
}

/** Result of a (possibly multi-slot) booking submit. `booked` is what got
 *  reserved; `unavailable` lists slot_ids that were just taken (skipped).
 *  `booking_id`/`status` are present only for a group of one (legacy shape). */
export interface TdSubmitResult {
  group_id: string
  booked: TdBooked[]
  unavailable: number[]
  booking_id?: number
  status?: string
}

export const tdApi = {
  getPage: (slug: string) => api.get<TdPublicPage>(`/api/td/pages/${slug}`),

  submitBooking: (slug: string, body: {
    slot_ids: number[]; name: string; phone: string; email: string
    license: string; license_expiry?: string; license_photo?: string | null
    gdpr_consent: boolean; conditions_accepted: boolean
    utm?: Record<string, string>
  }) => api.post<TdSubmitResult>(`/api/td/pages/${slug}/bookings`, body),

  confirm: (token: string) =>
    api.post<{ status: string; fp_id?: number; confirmed?: number; conflicts?: number }>(
      `/api/td/bookings/confirm`, { token }),

  cancel: (token: string) =>
    api.post<{ status: string }>(`/api/td/bookings/cancel`, { token }),
}
