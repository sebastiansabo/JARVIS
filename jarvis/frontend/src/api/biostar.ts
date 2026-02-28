import { api } from './client'
import type {
  BioStarConfig,
  BioStarEmployee,
  BioStarEmployeeProfile,
  BioStarPunchLog,
  BioStarStatus,
  BioStarSyncRun,
  BioStarDailySummary,
  BioStarRangeSummary,
  BioStarDayHistory,
  BioStarOffScheduleRow,
  BioStarAdjustment,
  BioStarCronJob,
  JarvisUser,
} from '@/types/biostar'

const BASE = '/biostar/api'

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  })
  return sp.toString() ? `?${sp.toString()}` : ''
}

export const biostarApi = {
  // ── Connection Config ──

  getConfig: async () => {
    const res = await api.get<{ success: boolean; data: BioStarConfig | null }>(`${BASE}/config`)
    return res.data
  },

  saveConfig: (data: { host: string; port: number; login_id: string; password: string; verify_ssl?: boolean }) =>
    api.post<{ success: boolean; message: string; connector_id: number }>(`${BASE}/config`, data),

  testConnection: (data?: { host?: string; port?: number; login_id?: string; password?: string }) =>
    api.post<{ success: boolean; data?: { success: boolean; user: string; total_users: number }; error?: string }>(
      `${BASE}/test-connection`,
      data,
    ),

  // ── Status ──

  getStatus: async () => {
    const res = await api.get<{ success: boolean; data: BioStarStatus }>(`${BASE}/status`)
    return res.data
  },

  // ── User Sync ──

  syncUsers: () =>
    api.post<{
      success: boolean
      data?: { fetched: number; created: number; updated: number; mapped: number; unmapped: number }
      error?: string
    }>(`${BASE}/sync/users`),

  getEmployees: async (activeOnly = true) => {
    const res = await api.get<{ success: boolean; data: BioStarEmployee[] }>(
      `${BASE}/employees`,
      { active_only: String(activeOnly) },
    )
    return res.data
  },

  getEmployeeStats: async () => {
    const res = await api.get<{ success: boolean; data: Record<string, number> }>(`${BASE}/employees/stats`)
    return res.data
  },

  updateMapping: (biostarUserId: string, jarvisUserId: number) =>
    api.put<{ success: boolean; message: string }>(`${BASE}/employees/${biostarUserId}/mapping`, {
      jarvis_user_id: jarvisUserId,
    }),

  removeMapping: (biostarUserId: string) =>
    api.delete<{ success: boolean; message: string }>(`${BASE}/employees/${biostarUserId}/mapping`),

  updateSchedule: (biostarUserId: string, data: {
    lunch_break_minutes: number; working_hours: number;
    schedule_start?: string; schedule_end?: string
  }) =>
    api.put<{ success: boolean; message: string }>(`${BASE}/employees/${biostarUserId}/schedule`, data),

  bulkUpdateSchedule: (data: {
    biostar_user_ids: string[];
    lunch_break_minutes?: number;
    working_hours?: number;
    schedule_start?: string;
    schedule_end?: string;
  }) =>
    api.put<{ success: boolean; message: string; data: { updated: number } }>(`${BASE}/employees/bulk-schedule`, data),

  bulkDeactivate: (biostarUserIds: string[]) =>
    api.post<{ success: boolean; message: string; data: { deactivated: number } }>(`${BASE}/employees/bulk-deactivate`, {
      biostar_user_ids: biostarUserIds,
    }),

  // ── Event Sync ──

  syncEvents: (params?: { start_date?: string; end_date?: string }) =>
    api.post<{
      success: boolean
      data?: { fetched: number; inserted: number; skipped: number; date_range: { start: string; end: string } }
      error?: string
    }>(`${BASE}/sync/events`, params),

  getPunchLogs: async (params?: {
    user_id?: string
    start?: string
    end?: string
    limit?: number
    offset?: number
  }) => {
    const res = await api.get<{ success: boolean; data: BioStarPunchLog[]; total: number }>(
      `${BASE}/punch-logs${qs(params ?? {})}`,
    )
    return { logs: res.data, total: res.total }
  },

  getDailySummary: async (date: string) => {
    const res = await api.get<{ success: boolean; data: BioStarDailySummary[] }>(
      `${BASE}/punch-logs/summary`,
      { date },
    )
    return res.data
  },

  getRangeSummary: async (start: string, end: string) => {
    const res = await api.get<{ success: boolean; data: BioStarRangeSummary[] }>(
      `${BASE}/punch-logs/range-summary`,
      { start, end },
    )
    return res.data
  },

  getEmployeePunches: async (biostarUserId: string, date: string) => {
    const res = await api.get<{ success: boolean; data: BioStarPunchLog[] }>(
      `${BASE}/punch-logs/employee/${biostarUserId}`,
      { date },
    )
    return res.data
  },

  // ── Employee Profile ──

  getEmployeeProfile: async (biostarUserId: string) => {
    const res = await api.get<{ success: boolean; data: BioStarEmployeeProfile }>(
      `${BASE}/employees/${biostarUserId}/profile`,
    )
    return res.data
  },

  getEmployeeDailyHistory: async (biostarUserId: string, start: string, end: string) => {
    const res = await api.get<{ success: boolean; data: BioStarDayHistory[] }>(
      `${BASE}/employees/${biostarUserId}/daily-history`,
      { start, end },
    )
    return res.data
  },

  // ── Sync History ──

  getSyncHistory: async (params?: { sync_type?: string; limit?: number }) => {
    const res = await api.get<{ success: boolean; data: BioStarSyncRun[] }>(
      `${BASE}/sync/history${qs(params ?? {})}`,
    )
    return res.data
  },

  // ── Schedule Adjustments ──

  getOffSchedule: async (date: string, threshold = 15) => {
    const res = await api.get<{ success: boolean; data: BioStarOffScheduleRow[] }>(
      `${BASE}/adjustments/off-schedule`,
      { date, threshold: String(threshold) },
    )
    return res.data
  },

  getAdjustments: async (date: string) => {
    const res = await api.get<{ success: boolean; data: BioStarAdjustment[] }>(
      `${BASE}/adjustments`,
      { date },
    )
    return res.data
  },

  adjustEmployee: (data: {
    biostar_user_id: string; date: string;
    adjusted_first_punch: string; adjusted_last_punch: string;
    original_first_punch: string; original_last_punch: string;
    schedule_start?: string; schedule_end?: string;
    lunch_break_minutes?: number; working_hours?: number;
    original_duration_seconds?: number;
    deviation_minutes_in?: number; deviation_minutes_out?: number;
    notes?: string;
  }) =>
    api.post<{ success: boolean; message: string }>(`${BASE}/adjustments/adjust`, data),

  autoAdjustAll: (date: string, threshold = 15) =>
    api.post<{ success: boolean; data: { adjusted: number; total_flagged: number } }>(
      `${BASE}/adjustments/auto-adjust`,
      { date, threshold },
    ),

  revertAdjustment: (biostarUserId: string, date: string) =>
    api.post<{ success: boolean; message: string }>(`${BASE}/adjustments/revert`, {
      biostar_user_id: biostarUserId, date,
    }),

  // ── Cron Jobs ──

  getCronJobs: async () => {
    const res = await api.get<{ success: boolean; data: BioStarCronJob[] }>(`${BASE}/cron-jobs`)
    return res.data
  },

  updateCronJobs: (jobs: Array<{ id: string; enabled: boolean; hour: number; minute: number }>) =>
    api.put<{ success: boolean; message: string }>(`${BASE}/cron-jobs`, { jobs }),

  // ── JARVIS Users (for mapping) ──

  getJarvisUsers: async () => {
    const res = await api.get<{ success: boolean; data: JarvisUser[] }>(`${BASE}/employees/jarvis-users`)
    return res.data
  },
}
