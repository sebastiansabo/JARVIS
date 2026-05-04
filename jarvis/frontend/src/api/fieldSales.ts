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
  'planned_date' | 'planned_time' | 'visit_type' | 'goals' | 'status' | 'outcome' |
  'contact_person' | 'companions' | 'pre_visit_data' | 'post_visit_data'
>>

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
}
