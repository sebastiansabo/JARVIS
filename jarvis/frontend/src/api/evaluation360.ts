import { api } from './client'

export type CycleStatus =
  | 'draft' | 'nomination' | 'active' | 'calibration' | 'released' | 'closed' | 'archived'

export interface Cycle {
  id: number
  name: string
  status: CycleStatus
  template_id: number | null
  population_filter?: Record<string, unknown>
  nomination_start: string | null
  review_start: string | null
  review_end: string | null
  calibration_end: string | null
  release_at: string | null
  release_policy: string
  created_at: string
}

export interface DeptCompletion {
  department: string
  submitted: number
  total: number
  completion_pct: number
}

export interface Progress {
  completion_pct: number
  submitted: number
  total: number
  by_status: Record<string, number>
  by_department: DeptCompletion[]
  declines_pending: number
}

export interface DryRun {
  overloaded_reviewers: { reviewer_id: number; load: number }[]
  participants_missing_peers: { employee_id: number; eligible_peers: number }[]
  blocking: boolean
}

export interface CreateCyclePayload {
  name: string
  template_id?: number | null
  timeline?: Record<string, string>
  participant_ids?: number[]
  release_policy?: string
}

const BASE = '/hr/evaluation360/api'

export const eval360Api = {
  listCycles: () => api.get<{ cycles: Cycle[] }>(`${BASE}/cycles`),
  getCycle: (id: number) => api.get<{ cycle: Cycle }>(`${BASE}/cycles/${id}`),
  createCycle: (data: CreateCyclePayload) => api.post<{ cycle: Cycle }>(`${BASE}/cycles`, data),
  transition: (id: number, target: CycleStatus, waive_blocking = false) =>
    api.post<{ cycle: Cycle }>(`${BASE}/cycles/${id}/transition`, { target, waive_blocking }),
  progress: (id: number) => api.get<{ progress: Progress }>(`${BASE}/cycles/${id}/progress`),
  dryRun: (id: number) => api.get<{ dry_run: DryRun }>(`${BASE}/cycles/${id}/dry-run`),
  nudge: (id: number, userId: number) =>
    api.post<{ ok: boolean }>(`${BASE}/cycles/${id}/nudge`, { user_id: userId }),
}

/** Forward transitions allowed from each state (mirrors the backend state machine). */
export const NEXT_STATES: Record<CycleStatus, CycleStatus[]> = {
  draft: ['nomination'],
  nomination: ['active'],
  active: ['calibration', 'released'],
  calibration: ['released'],
  released: ['closed'],
  closed: ['archived'],
  archived: [],
}

export const STATUS_LABEL: Record<CycleStatus, string> = {
  draft: 'Draft',
  nomination: 'Nominare',
  active: 'Activ',
  calibration: 'Calibrare',
  released: 'Publicat',
  closed: 'Închis',
  archived: 'Arhivat',
}
