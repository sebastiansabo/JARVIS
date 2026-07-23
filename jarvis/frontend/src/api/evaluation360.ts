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

// ── Reviewer (capture) ──────────────────────────────────────────────────────

export interface MyAssignment {
  id: number
  cycle_id: number
  subject_id: number
  relationship: string
  status: string
  due_at: string | null
  subject_name: string
  cycle_name: string
  review_end: string | null
}

export type QuestionType = 'rating' | 'behavioral_frequency' | 'open_text' | 'forced_choice'

export interface Question {
  id: number
  competency_id: number | null
  competency_name: string | null
  type: QuestionType
  text_by_audience: Record<string, string>
  required: boolean
  sort_order: number
}

export interface EvaluationForm {
  assignment: MyAssignment
  questions: Question[]
  draft: Record<string, string | number | null>
  is_submitted: boolean
}

/** A submitted answer for one question. `rating` null means "Not observed". */
export interface Answer {
  question_id: number
  competency_id: number | null
  rating: number | null
  not_observed: boolean
  comment?: string
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

  // reviewer capture
  myAssignments: () => api.get<{ assignments: MyAssignment[] }>(`${BASE}/me/assignments`),
  getForm: (id: number) => api.get<EvaluationForm>(`${BASE}/assignments/${id}/form`),
  saveDraft: (id: number, patch: Record<string, string | number | null>) =>
    api.put<{ draft: Record<string, string | number | null> }>(
      `${BASE}/assignments/${id}/draft`, { patch, device: 'web' }),
  submit: (id: number, answers: Answer[]) =>
    api.post<{ ok: boolean }>(`${BASE}/assignments/${id}/submit`, { answers, device: 'web' }),
  selfDecline: (id: number, reason: string) =>
    api.patch<{ ok: boolean }>(`${BASE}/assignments/${id}/self-decline`, { reason }),
}

// ── Reports ─────────────────────────────────────────────────────────────────

export interface ReportHeader {
  id: number
  cycle_id: number
  cycle_name: string
  released_at: string
  acknowledged_at: string | null
}

export interface CompetencyAgg {
  competency_id: number
  competency_name: string | null
  self: number | null
  others: number | null
  gap: number | null
  johari: string | null
  categories: Record<string, { n: number; score: number | null; hidden: boolean }>
}

export interface ReportAggregates {
  competencies: CompetencyAgg[]
  visible_relationships: string[]
  hidden_relationships: string[]
}

export interface Report {
  id: number
  cycle_id: number
  participant_id: number
  aggregates_by_relationship: ReportAggregates
  gap_analysis: { flagged_competencies: number[] }
  hidden_categories: string[]
  manager_summary: string | null
  released_at: string | null
  acknowledged_at: string | null
}

export const JOHARI_LABEL: Record<string, string> = {
  confirmed_strength: 'Puncte forte confirmate',
  blind_spot: 'Puncte oarbe',
  hidden_strength: 'Puncte forte ascunse',
  agreed_growth: 'Zone de dezvoltare',
}

export interface TeamReportHeader {
  id: number
  cycle_id: number
  cycle_name: string
  employee_id: number
  employee_name: string
  released: boolean
  acknowledged: boolean
  has_summary: boolean
}

export const eval360Reports = {
  myReports: () => api.get<{ reports: ReportHeader[] }>(`${BASE}/me/reports`),
  myReport: (cycleId: number) => api.get<{ report: Report }>(`${BASE}/me/report/${cycleId}`),
  acknowledge: (reportId: number) => api.post<{ ok: boolean }>(`${BASE}/reports/${reportId}/acknowledge`),
  // manager calibration
  teamReports: () => api.get<{ reports: TeamReportHeader[] }>(`${BASE}/me/team-reports`),
  managerReport: (reportId: number) => api.get<{ report: Report }>(`${BASE}/reports/${reportId}/manager-view`),
  managerRelease: (reportId: number) => api.post<{ report: Report }>(`${BASE}/reports/${reportId}/manager-release`),
  setSummary: (reportId: number, summary: string) =>
    api.post<{ ok: boolean }>(`${BASE}/reports/${reportId}/manager-summary`, { summary }),
}

export const RELATIONSHIP_LABEL: Record<string, string> = {
  self: 'Autoevaluare',
  manager: 'Manager',
  peer: 'Coleg',
  direct_report: 'Subordonat',
  external: 'Extern',
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
