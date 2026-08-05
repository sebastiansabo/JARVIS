import { api } from './client'

export interface FSVisitNote {
  id: number
  raw_note: string
  structured_note?: Record<string, unknown>
  structured_at?: string
  created_at: string
}

export interface PreVisitData {
  confirmed_contact_person?: string
  confirmed_address?: string
  known_fleet_count?: number
  acquisition_methods?: string[]
  shareholders_info?: string
  work_points_count?: number
  annual_revenue_estimate?: number
  visit_objectives?: string[]
  materials_prepared?: string[]
  companion_names?: string[]
  notes?: string
}

export interface PostVisitData {
  satisfaction_level?: number        // 1-5
  purchase_intent?: string           // none | exploring | interested | ready_to_buy | negotiating
  fleet_profile_updated?: boolean
  cross_brand_interest?: string[]
  competitor_vehicles_seen?: string[]
  decision_maker_met?: boolean
  decision_maker_name?: string
  budget_range?: string
  preferred_financing?: string
  timeline_to_purchase?: string
  next_steps?: string
  notes?: string
}

export interface FSVisit {
  id: number
  kam_id: number
  client_id: number
  planned_date: string
  planned_time?: string
  planned_end_time?: string
  visit_type: string
  status: string
  outcome?: string
  goals?: string
  ai_brief?: string
  ai_brief_generated_at?: string
  checkin_at?: string
  checkout_at?: string
  checkin_lat?: number
  checkin_lng?: number
  client_name: string
  client_phone?: string
  client_email?: string
  client_city?: string
  client_company?: string
  kam_name: string
  renewal_score?: number
  client_priority?: string
  fleet_size?: number
  profile_client_type?: string
  cui?: string
  industry?: string
  note_count?: number
  notes?: FSVisitNote[]
  route_id?: number | null
  sequence?: number
  route_name?: string | null
  // Phase 1: structured visit data
  pre_visit_data?: PreVisitData
  post_visit_data?: PostVisitData
  contact_person?: string
  companions?: string[]
}

export interface FSVisitTask {
  id: number
  visit_id: number
  description: string
  assigned_to?: number
  assigned_to_name?: string
  due_date?: string
  status: string
  completed_at?: string
  created_by?: number
  created_by_name?: string
  created_at: string
  updated_at: string
  follow_up_count?: number
  // Joined fields for pending tasks view
  planned_date?: string
  visit_type?: string
  client_name?: string
}

export interface FSTaskFollowUp {
  id: number
  task_id: number
  note: string
  created_by?: number
  created_by_name?: string
  created_at: string
}

export interface FSManagerOverview {
  success: boolean
  visits: FSVisit[]
  summary: {
    total: number
    by_status: Record<string, number>
    by_kam: Record<string, { total: number; completed: number; in_progress: number; planned: number }>
  }
}

export interface FSClientSearch {
  id: number
  display_name: string
  company_name?: string
  city?: string
  nr_reg?: string
  client_type: string
}

export interface CreateVisitPayload {
  client_id: number
  planned_date: string
  planned_time?: string
  planned_end_time?: string
  visit_type?: string
  goals?: string
  kam_id?: number
}

export interface RouteStop {
  client_id: number
  planned_time?: string
  visit_type?: string
  goals?: string
}

export interface CreateRoutePayload {
  kam_id: number
  planned_date: string
  name?: string
  stops: RouteStop[]
}

export type VisitUpdatePayload = Partial<Pick<FSVisit,
  'planned_date' | 'planned_time' | 'planned_end_time' | 'visit_type' | 'goals' | 'status' | 'outcome' |
  'contact_person' | 'companions' | 'pre_visit_data' | 'post_visit_data'
>>

export interface FSStructuredNote {
  // NOTE: the AI/backend may omit any field at runtime (the stored structured
  // note is whatever the LLM returned), so consumers MUST guard array access
  // (e.g. `x?.length ?? 0`) — a missing array is undefined, not []. Types below
  // describe the full/happy shape; treat arrays as possibly-absent.
  visit_summary: string
  contact_person: string | null
  vehicles_discussed: { action: string; current_vehicle: string | null; interested_in: string | null; budget_eur: number | null }[]
  commitments_made: string[]
  next_steps: { action: string; owner: string; deadline: string | null }[]
  opportunity_value_eur: number | null
  decision_timeline: string | null
  follow_up_date: string | null
  objections: string[]
  risk_flags: string[]
}

export interface FSClientProfile {
  id: number; client_id: number; client_type: string; industry: string | null
  country_code: string; legal_form: string | null; assigned_kam_id: number | null
  fleet_size: number; renewal_score: number; cui: string | null
  estimated_annual_value: number | null; priority: string
}
export interface FSClientFleetVehicle {
  id: number; client_id: number; vehicle_make: string; vehicle_model: string
  vehicle_year: number; vin: string | null; license_plate: string | null
  purchase_date: string | null; purchase_price: number | null; purchase_currency: string
  estimated_mileage: number | null; financing_type: string | null; financing_expiry: string | null
  warranty_expiry: string | null; status: string; renewal_candidate: boolean; renewal_reason: string | null
}
export interface FSSaleSummary {
  id: number; brand: string; model_name: string; contract_date: string | null
  sale_price_net: number | null; vin: string | null; source: string
}
export interface FSVisitSummary {
  id: number; planned_date: string; visit_type: string; status: string
  outcome: string | null; visit_summary: string | null; kam_name?: string; client_name?: string
}
// ANAF fiscal payload comes in two shapes: NESTED (real ANAF fetch — fields live
// under date_generale / inregistrare_scop_Tva / stare_inactiv) and FLAT (AI-fallback
// path — fields at the top level). FiscalSection unwraps with a flat fallback so both
// render. Allow the nested containers alongside the flat keys.
export interface FSAnafData {
  // Nested (real ANAF) containers
  date_generale?: Record<string, unknown>
  inregistrare_scop_Tva?: Record<string, unknown>
  stare_inactiv?: Record<string, unknown>
  // Flat (AI-fallback) keys
  denumire?: string
  cui?: string
  adresa?: string
  nrRegCom?: string
  scpTVA?: boolean
  telefon?: string
  cod_postal?: string
  stare_inregistrare?: string
  [k: string]: unknown
}
export interface FSInventoryMatch {
  id: number; brand: string; model_name: string; model_year: number
  sale_price_net: number; vin: string | null
}
export interface FSClient360 {
  profile: FSClientProfile | null
  fleet: FSClientFleetVehicle[]
  last_purchases: FSSaleSummary[]
  last_interactions: FSVisitSummary[]
  visit_history: FSVisitSummary[]
  renewal_candidates: FSClientFleetVehicle[]
  inventory_matches: FSInventoryMatch[]
  fiscal: FSAnafData | null
}

export const fieldSalesApi = {
  getManagerOverview: (dateFrom: string, dateTo: string, kamId?: number) => {
    const params: Record<string, string> = { date_from: dateFrom, date_to: dateTo }
    if (kamId) params.kam_id = String(kamId)
    return api.get<FSManagerOverview>('/api/field-sales/manager/overview', params)
  },

  searchClients: (q: string) =>
    api.get<{ success: boolean; clients: FSClientSearch[]; count: number }>(
      '/api/field-sales/clients/search',
      { q },
    ),

  createVisit: (data: CreateVisitPayload) =>
    api.post<{ success: boolean; visit: FSVisit }>('/api/field-sales/visits', data),

  getVisit: (visitId: number) =>
    api.get<{ success: boolean; visit: FSVisit }>(`/api/field-sales/visits/${visitId}`),

  updateVisit: (visitId: number, data: VisitUpdatePayload) =>
    api.put<{ success: boolean; visit: FSVisit }>(`/api/field-sales/visits/${visitId}`, data),

  createRoute: (data: CreateRoutePayload) =>
    api.post<{ success: boolean; route: { id: number; visits: FSVisit[] } }>('/api/field-sales/routes', data),

  // ── Tasks ──
  getVisitTasks: (visitId: number) =>
    api.get<{ success: boolean; tasks: FSVisitTask[] }>(`/api/field-sales/visits/${visitId}/tasks`),

  createTask: (visitId: number, data: { description: string; due_date?: string; assigned_to?: number }) =>
    api.post<{ success: boolean; task: FSVisitTask }>(`/api/field-sales/visits/${visitId}/tasks`, data),

  updateTask: (taskId: number, data: Partial<Pick<FSVisitTask, 'description' | 'status' | 'due_date' | 'assigned_to'>>) =>
    api.put<{ success: boolean; task: FSVisitTask }>(`/api/field-sales/tasks/${taskId}`, data),

  getTaskFollowUps: (taskId: number) =>
    api.get<{ success: boolean; follow_ups: FSTaskFollowUp[] }>(`/api/field-sales/tasks/${taskId}/follow-ups`),

  addTaskFollowUp: (taskId: number, note: string) =>
    api.post<{ success: boolean; follow_up: FSTaskFollowUp }>(`/api/field-sales/tasks/${taskId}/follow-ups`, { note }),

  getPendingTasks: () =>
    api.get<{ success: boolean; tasks: FSVisitTask[] }>('/api/field-sales/tasks/pending'),

  // ── Hub daily-driver ──
  getTodayVisits: (date: string) =>
    api.get<{ success: boolean; visits: FSVisit[]; date: string }>('/api/field-sales/visits/today', { date }),

  getMyVisits: (dateFrom: string, dateTo: string) =>
    api.get<{ success: boolean; visits: FSVisit[]; date_from: string; date_to: string }>(
      '/api/field-sales/visits/mine', { date_from: dateFrom, date_to: dateTo }),

  checkin: (visitId: number, coords: { lat?: number; lng?: number }) =>
    api.post<{ success: boolean; visit: FSVisit }>(`/api/field-sales/visits/${visitId}/checkin`, coords),

  checkout: (visitId: number, data: { outcome: string }) =>
    api.post<{ success: boolean; visit: FSVisit }>(`/api/field-sales/visits/${visitId}/checkout`, data),

  addNote: (visitId: number, data: { raw_note: string }) =>
    api.post<{ success: boolean; note: FSVisitNote; structured_note: FSStructuredNote | null }>(
      `/api/field-sales/visits/${visitId}/note`, data),

  getClient360: (clientId: number) => {
    // Backend returns { profile, fleet, purchases, interactions, visit_history,
    // renewal_candidates, inventory_matches, fiscal } — normalize to FSClient360.
    return api.get<Record<string, unknown>>(`/api/field-sales/clients/${clientId}/360`).then((res) => ({
      profile: (res.profile as FSClient360['profile']) ?? null,
      fleet: (res.fleet as FSClient360['fleet']) ?? [],
      last_purchases: (res.purchases as FSClient360['last_purchases']) ?? [],
      last_interactions: (res.interactions as FSClient360['last_interactions']) ?? [],
      visit_history: (res.visit_history as FSClient360['visit_history']) ?? [],
      renewal_candidates: (res.renewal_candidates as FSClient360['renewal_candidates']) ?? [],
      inventory_matches: (res.inventory_matches as FSClient360['inventory_matches']) ?? [],
      fiscal: (res.fiscal as FSClient360['fiscal']) ?? null,
    }))
  },

  refreshFiscal: (clientId: number) =>
    api.post<{ success: boolean }>(`/api/field-sales/clients/${clientId}/refresh-fiscal`),
}
