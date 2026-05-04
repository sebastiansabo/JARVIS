import { api } from './client'

interface DashboardStats {
  total_events: number
  unique_users: number
  total_sessions: number
  page_views: number
  interactions: number
  avg_session_duration: number | null
  avg_pages_per_session: number
  daily_active: Array<{ day: string; active_users: number; events: number }>
}

interface TelemetryEvent {
  id: number
  event_name: string
  event_category: string
  session_id: string
  user_id: number | null
  user_name: string | null
  company_id: number | null
  role_name: string | null
  properties: Record<string, unknown>
  page_path: string | null
  page_title: string | null
  client_ts: string
  server_ts: string
}

interface TelemetrySession {
  id: number
  session_id: string
  user_id: number | null
  user_name: string | null
  company_id: number | null
  role_name: string | null
  started_at: string
  last_seen_at: string
  ended_at: string | null
  duration_seconds: number | null
  page_views: number
  event_count: number
  entry_page: string | null
  exit_page: string | null
  is_mobile: boolean
}

interface PopularPage {
  page_path: string
  view_count: number
  unique_users: number
  unique_sessions: number
  avg_duration_ms: number | null
}

interface PopularAction {
  event_name: string
  button_id: string | null
  button_text: string | null
  click_count: number
  unique_users: number
}

interface JourneyStep {
  event_name: string
  page_path: string | null
  page_title: string | null
  previous_page: string | null
  duration_ms: string | null
  client_ts: string
}

export const telemetryApi = {
  getDashboard: (days = 30) =>
    api.get<{ success: boolean; data: DashboardStats }>('/api/admin/telemetry/dashboard', { days: String(days) })
      .then(r => r.data),

  getEvents: (params: { limit?: number; offset?: number; event_name?: string; user_id?: number; session_id?: string } = {}) => {
    const p: Record<string, string> = {}
    if (params.limit) p.limit = String(params.limit)
    if (params.offset) p.offset = String(params.offset)
    if (params.event_name) p.event_name = params.event_name
    if (params.user_id) p.user_id = String(params.user_id)
    if (params.session_id) p.session_id = params.session_id
    return api.get<{ success: boolean; data: TelemetryEvent[] }>('/api/admin/telemetry/events', p).then(r => r.data)
  },

  getSessions: (params: { limit?: number; offset?: number; user_id?: number } = {}) => {
    const p: Record<string, string> = {}
    if (params.limit) p.limit = String(params.limit)
    if (params.offset) p.offset = String(params.offset)
    if (params.user_id) p.user_id = String(params.user_id)
    return api.get<{ success: boolean; data: TelemetrySession[] }>('/api/admin/telemetry/sessions', p).then(r => r.data)
  },

  getPopularPages: (days = 30) =>
    api.get<{ success: boolean; data: PopularPage[] }>('/api/admin/telemetry/popular-pages', { days: String(days) })
      .then(r => r.data),

  getPopularActions: (days = 30) =>
    api.get<{ success: boolean; data: PopularAction[] }>('/api/admin/telemetry/popular-actions', { days: String(days) })
      .then(r => r.data),

  getUserJourney: (sessionId: string) =>
    api.get<{ success: boolean; data: JourneyStep[] }>('/api/admin/telemetry/user-journeys', { session_id: sessionId })
      .then(r => r.data),

  getEventNames: () =>
    api.get<{ success: boolean; data: string[] }>('/api/admin/telemetry/event-names').then(r => r.data),
}

export type { DashboardStats, TelemetryEvent, TelemetrySession, PopularPage, PopularAction, JourneyStep }
