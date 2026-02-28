// BioStar 2 / Pontaje types

export interface BioStarConfig {
  id?: number
  host: string
  port: number
  login_id: string
  password?: string
  verify_ssl: boolean
  status: string
  last_sync: string | null
}

export interface BioStarEmployee {
  id: number
  biostar_user_id: string
  name: string
  email: string | null
  phone: string | null
  user_group_id: string | null
  user_group_name: string | null
  card_ids: string[]
  mapped_jarvis_user_id: number | null
  mapped_jarvis_user_name: string | null
  mapping_method: string | null
  mapping_confidence: number | null
  lunch_break_minutes: number
  working_hours: number
  schedule_start: string | null
  schedule_end: string | null
  status: string
  last_synced_at: string
  created_at: string
  updated_at: string
}

export interface BioStarPunchLog {
  id: number
  biostar_event_id: string
  biostar_user_id: string
  employee_name: string | null
  event_datetime: string
  event_type: string
  direction: 'IN' | 'OUT' | null
  device_id: string | null
  device_name: string | null
  door_id: string | null
  door_name: string | null
  auth_type: string | null
  synced_at: string
}

export interface BioStarSyncRun {
  id: number
  run_id: string
  sync_type: 'users' | 'events'
  started_at: string
  finished_at: string | null
  success: boolean
  records_fetched: number
  records_created: number
  records_updated: number
  records_skipped: number
  errors_count: number
  error_summary: string | null
}

export interface BioStarStatus {
  connected: boolean
  status: string
  host: string | null
  last_sync_users: string | null
  last_sync_events: string | null
  employee_count: {
    total: number
    active: number
    mapped: number
    unmapped: number
  }
  event_count: number
}

export interface BioStarDailySummary {
  biostar_user_id: string
  name: string
  email: string | null
  user_group_name: string | null
  mapped_jarvis_user_id: number | null
  mapped_jarvis_user_name: string | null
  lunch_break_minutes: number
  working_hours: number
  schedule_start: string | null
  schedule_end: string | null
  first_punch: string
  last_punch: string
  total_punches: number
  duration_seconds: number | null
}

export interface BioStarDayHistory {
  date: string
  first_punch: string
  last_punch: string
  total_punches: number
  duration_seconds: number | null
  lunch_break_minutes?: number
  working_hours?: number
  schedule_start?: string | null
  schedule_end?: string | null
}

export interface BioStarEmployeeProfile {
  id: number
  biostar_user_id: string
  name: string
  email: string | null
  phone: string | null
  user_group_id: string | null
  user_group_name: string | null
  mapped_jarvis_user_id: number | null
  mapped_jarvis_user_name: string | null
  mapped_jarvis_user_email: string | null
  lunch_break_minutes: number
  working_hours: number
  schedule_start: string | null
  schedule_end: string | null
  status: string
}

export interface BioStarOffScheduleRow {
  biostar_user_id: string
  name: string
  email: string | null
  user_group_name: string | null
  mapped_jarvis_user_id: number | null
  mapped_jarvis_user_name: string | null
  schedule_start: string | null
  schedule_end: string | null
  lunch_break_minutes: number
  working_hours: number
  first_punch: string
  last_punch: string
  total_punches: number
  duration_seconds: number | null
  deviation_in: number
  deviation_out: number
  // null if not yet adjusted
  adjustment_id: number | null
  adjusted_first_punch: string | null
  adjusted_last_punch: string | null
  adjustment_type: string | null
  adjusted_by: number | null
  notes: string | null
}

export interface BioStarAdjustment {
  id: number
  biostar_user_id: string
  date: string
  name: string
  email: string | null
  user_group_name: string | null
  original_first_punch: string
  original_last_punch: string
  original_duration_seconds: number | null
  adjusted_first_punch: string
  adjusted_last_punch: string
  adjusted_duration_seconds: number | null
  schedule_start: string | null
  schedule_end: string | null
  lunch_break_minutes: number | null
  working_hours: number | null
  deviation_minutes_in: number | null
  deviation_minutes_out: number | null
  adjustment_type: string
  adjusted_by: number | null
  adjusted_by_name: string | null
  notes: string | null
  created_at: string
}

export interface BioStarRangeSummary {
  biostar_user_id: string
  name: string
  email: string | null
  user_group_name: string | null
  mapped_jarvis_user_id: number | null
  mapped_jarvis_user_name: string | null
  lunch_break_minutes: number
  working_hours: number
  schedule_start: string | null
  schedule_end: string | null
  days_present: number
  total_duration_seconds: number | null
  avg_duration_seconds: number | null
  total_punches: number
  earliest_punch: string | null
  latest_punch: string | null
}

export interface BioStarCronJob {
  id: string
  label: string
  description: string
  enabled: boolean
  hour: number
  minute: number
  last_run: string | null
  last_success: boolean | null
  last_message: string | null
}

export interface JarvisUser {
  id: number
  name: string
  email: string | null
  department: string | null
  company: string | null
}
