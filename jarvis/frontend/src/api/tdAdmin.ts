import { api } from './client'

const B = '/marketing/api/td'

export interface TdAdminPage {
  id: number
  project_id: number | null
  company_id: number
  event_id: number | null
  slug: string
  status: 'draft' | 'open' | 'closed'
  opens_at: string | null
  closes_at: string | null
  min_lead_minutes: number
  slot_minutes: number
  buffer_minutes: number
  max_bookings_per_contact: number
  access_code: string | null
  title: string | null
  intro: string | null
  thank_you: string | null
  conditions_text?: string | null
  logo_url?: string | null
  email_subject?: string | null
  email_body?: string | null
  require_license_photo?: boolean
  notify_user_ids: number[] | null
  created_by: number | null
  created_at: string
  updated_at: string
  deleted_at: string | null
}

/** A driving session on a car that overlaps the event's windows — surfaced so
 *  staff aren't surprised when a "busy" car shows no public slots. */
export interface TdSessionConflict {
  id: number
  contract_id: string
  status: string
  route_type: string
  departure_datetime: string
  return_datetime: string | null
  client_name: string | null
  advisor_name: string | null
}

export interface TdAdminCar {
  id: number
  page_id: number
  vin: string
  vehicle_id: number | null
  default_advisor_user_id: number | null
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string
  conflicts?: TdSessionConflict[]
}

/** One band for the Driving Hub Calendar overlay: an event car committed for
 *  the event's window range. */
export interface TdCalendarEvent {
  page_id: number
  title: string | null
  slug: string
  status: 'draft' | 'open' | 'closed'
  vin: string
  starts_at: string
  ends_at: string
}

export interface TdAdminWindow {
  id: number
  page_id: number
  window_date: string
  start_time: string
  end_time: string
  slot_minutes: number | null
  created_at: string
}

export type TdBookingStatus =
  | 'pending_confirm' | 'confirmed' | 'cancelled' | 'expired' | 'conflict' | 'completed' | 'no_show'

export interface TdAdminBooking {
  id: number
  page_id: number
  slot_id: number
  car_id: number
  customer_name: string
  customer_phone_e164: string
  customer_email: string
  crm_client_id: number | null
  foi_de_parcurs_id: number | null
  advisor_user_id: number | null
  status: TdBookingStatus
  expires_at: string
  confirmed_at: string | null
  cancelled_at: string | null
  created_at: string
  updated_at: string
}

export interface TdOpenSlot {
  id: number
  car_id: number
  vin: string
  starts_at: string
  ends_at: string
  mark?: string | null
  model?: string | null
  registration_number?: string | null
}

export type TdWaitlistStatus = 'new' | 'contacted' | 'done' | 'dismissed'

export interface TdWaitlistEntry {
  id: number
  page_id: number
  customer_name: string
  customer_phone_e164: string
  customer_email: string | null
  preferred_car_vin: string | null
  note: string | null
  status: TdWaitlistStatus
  created_at: string
  handled_at: string | null
  handled_by: number | null
}

export const tdAdminApi = {
  listPages: (companyId?: number) =>
    api.get<{ pages: TdAdminPage[] }>(`${B}/pages${companyId ? `?company_id=${companyId}` : ''}`),

  createPage: (body: Record<string, unknown>) => api.post<TdAdminPage>(`${B}/pages`, body),

  updatePage: (id: number, body: Record<string, unknown>) => api.patch<TdAdminPage>(`${B}/pages/${id}`, body),

  setStatus: (id: number, status: string) => api.post<TdAdminPage>(`${B}/pages/${id}/status`, { status }),

  addCar: (id: number, body: Record<string, unknown>) => api.post<TdAdminCar>(`${B}/pages/${id}/cars`, body),

  removeCar: (cid: number) => api.delete<{ ok: boolean }>(`${B}/cars/${cid}`),

  listCars: (id: number) => api.get<{ cars: TdAdminCar[] }>(`${B}/pages/${id}/cars`),

  addWindow: (id: number, body: Record<string, unknown>) => api.post<TdAdminWindow>(`${B}/pages/${id}/windows`, body),

  listWindows: (id: number) => api.get<{ windows: TdAdminWindow[]; slot_count: number }>(`${B}/pages/${id}/windows`),

  calendarEvents: (companyId: number, from: string, to: string) =>
    api.get<{ events: TdCalendarEvent[] }>(`${B}/calendar-events?company_id=${companyId}&from=${from}&to=${to}`),

  deleteWindow: (wid: number) => api.delete<{ ok: boolean }>(`${B}/windows/${wid}`),

  materialize: (id: number) => api.post<{ inserted: number }>(`${B}/pages/${id}/materialize`, {}),

  listBookings: (id: number, status?: string) =>
    api.get<{ bookings: TdAdminBooking[] }>(`${B}/pages/${id}/bookings${status ? `?status=${status}` : ''}`),

  reassignAdvisor: (bid: number, advisor_user_id: number) =>
    api.patch<{ ok: boolean }>(`${B}/bookings/${bid}/advisor`, { advisor_user_id }),

  deleteBooking: (bid: number) => api.delete<{ ok: boolean }>(`${B}/bookings/${bid}`),

  editBooking: (bid: number, body: Record<string, unknown>) =>
    api.patch<{ ok: boolean; booking: TdAdminBooking }>(`${B}/bookings/${bid}`, body),

  listOpenSlots: (id: number) => api.get<{ slots: TdOpenSlot[] }>(`${B}/pages/${id}/open-slots`),

  listWaitlist: (id: number) => api.get<{ waitlist: TdWaitlistEntry[] }>(`${B}/pages/${id}/waitlist`),

  updateWaitlist: (wid: number, status: TdWaitlistStatus) =>
    api.patch<TdWaitlistEntry>(`${B}/waitlist/${wid}`, { status }),
}
