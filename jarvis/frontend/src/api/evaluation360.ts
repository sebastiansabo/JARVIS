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
  population_filter?: { departments?: string[]; company_ids?: number[] }
  release_policy?: string
}

export interface GenerateSummary {
  subjects: number
  assignments: number
  skipped: number
}

// ── Competency library + form templates (HR authoring) ──────────────────────

export interface Competency {
  id: number
  name: string
  definition: string | null
  cluster: string | null
  is_active: boolean
  usage_count: number
}

export interface TemplateSummary {
  id: number
  name: string
  version: number
  status: 'draft' | 'published' | 'archived'
  forked_from_id: number | null
  competency_ids: number[]
  question_count: number
  cycle_count: number
  created_at: string
}

/** One question block on a template. `text_by_audience` maps a relationship
 *  (self/manager/peer/direct_report) to the prompt shown to that rater. */
export interface TemplateQuestion {
  id?: number
  competency_id: number | null
  competency_name?: string | null
  type: QuestionType
  text_by_audience: Record<string, string>
  required: boolean
  sort_order?: number
}

export interface TemplateDetail {
  template: TemplateSummary
  questions: TemplateQuestion[]
  forked?: boolean
}

export interface EligibleEmployee {
  id: number
  name: string
  department: string | null
  company_id: number | null
}

export interface DepartmentInfo { department: string; count: number }

/** A node in the Sincron organigram, with the count of members that resolve to
 *  an active JARVIS user (= how many participants selecting it would add). */
export interface SincronOrgNode {
  id: number
  company_id: number
  company_name: string
  parent_id: number | null
  name: string
  node_type: 'department' | 'role' | 'team'
  level: number
  member_count: number
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
  /** Inbox progress (spec §6.1): rating questions answered in the draft / total. */
  answered: number
  total: number
  est_minutes: number
}

export type QuestionType = 'rating' | 'behavioral_frequency' | 'open_text' | 'forced_choice'

/** Behavioral anchors for a competency, keyed by locale (spec §6.2, i18n per user). */
export interface CompetencyAnchors {
  min_label?: string
  max_label?: string
  levels?: string[]
}

export interface Question {
  id: number
  competency_id: number | null
  competency_name: string | null
  competency_definition?: string | null
  /** Per-locale anchor descriptors from the template; may be absent/empty on old data. */
  competency_level_descriptors?: Record<string, CompetencyAnchors> | null
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
  generateAssignments: (id: number, autoPeers = 4) =>
    api.post<{ generated: GenerateSummary }>(`${BASE}/cycles/${id}/generate-assignments`, { auto_peers: autoPeers }),
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
  commentNudge: (id: number, questionId: number) =>
    api.post<{ ok: boolean }>(`${BASE}/assignments/${id}/comment-nudge`, { question_id: questionId }),
  selfDecline: (id: number, reason: string) =>
    api.patch<{ ok: boolean }>(`${BASE}/assignments/${id}/self-decline`, { reason }),
}

// ── Competency library + form templates (HR authoring) ──────────────────────

export interface SaveTemplatePayload {
  name?: string
  competency_ids?: number[]
  questions?: TemplateQuestion[]
}

export const eval360Library = {
  listCompetencies: (includeInactive = false) =>
    api.get<{ competencies: Competency[] }>(`${BASE}/competencies${includeInactive ? '?include_inactive=1' : ''}`),
  createCompetency: (data: { name: string; cluster?: string; definition?: string }) =>
    api.post<{ competency: Competency }>(`${BASE}/competencies`, data),
  updateCompetency: (id: number, data: Partial<Pick<Competency, 'name' | 'cluster' | 'definition' | 'is_active'>>) =>
    api.patch<{ competency: Competency }>(`${BASE}/competencies/${id}`, data),

  listTemplates: (includeArchived = false) =>
    api.get<{ templates: TemplateSummary[] }>(`${BASE}/templates${includeArchived ? '?include_archived=1' : ''}`),
  getTemplate: (id: number) => api.get<TemplateDetail>(`${BASE}/templates/${id}`),
  createTemplate: (data: SaveTemplatePayload) => api.post<TemplateDetail>(`${BASE}/templates`, data),
  saveTemplate: (id: number, data: SaveTemplatePayload) => api.patch<TemplateDetail>(`${BASE}/templates/${id}`, data),
  publishTemplate: (id: number) => api.post<TemplateDetail>(`${BASE}/templates/${id}/publish`),
  forkTemplate: (id: number) => api.post<TemplateDetail>(`${BASE}/templates/${id}/fork`),
  archiveTemplate: (id: number) => api.post<TemplateDetail>(`${BASE}/templates/${id}/archive`),
}

export const eval360Population = {
  departments: () => api.get<{ departments: DepartmentInfo[] }>(`${BASE}/departments`),
  eligibleEmployees: (params: { search?: string; department?: string } = {}) => {
    const qs = new URLSearchParams()
    if (params.search) qs.set('search', params.search)
    if (params.department) qs.set('department', params.department)
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return api.get<{ employees: EligibleEmployee[] }>(`${BASE}/eligible-employees${suffix}`)
  },
  // Sincron organigram source
  sincronOrgTree: () => api.get<{ nodes: SincronOrgNode[] }>(`${BASE}/sincron-org`),
  sincronOrgMembers: (nodeId: number) =>
    api.get<{ employees: EligibleEmployee[] }>(`${BASE}/sincron-org/${nodeId}/members`),
}

// ── Peer nomination (HR editor + employee self-nominate) ────────────────────

export interface NominatedReviewer {
  id: number
  reviewer_id: number | null
  relationship: string
  source: string
  status: string
  reviewer_name: string | null
}
export interface NominationView {
  peers: NominatedReviewer[]
  others: NominatedReviewer[]
  candidates: { id: number; name: string; department: string | null }[]
}
export interface NominationParticipant {
  employee_id: number
  name: string
  department: string | null
  peer_count: number
}
export interface NominationCycle {
  id: number
  name: string
  status: CycleStatus
  peer_count: number
}

export const eval360Nomination = {
  participants: (cycleId: number) =>
    api.get<{ participants: NominationParticipant[] }>(`${BASE}/cycles/${cycleId}/nomination-participants`),
  myNominations: () => api.get<{ cycles: NominationCycle[] }>(`${BASE}/me/nominations`),
  view: (cycleId: number, subjectId: number) =>
    api.get<NominationView>(`${BASE}/nominate/${cycleId}/${subjectId}`),
  setPeers: (cycleId: number, subjectId: number, peerIds: number[]) =>
    api.post<{ result: { added: number[]; removed: number[]; peer_count: number } }>(
      `${BASE}/nominate/${cycleId}/${subjectId}`, { peer_ids: peerIds }),
}

export const TEMPLATE_STATUS_LABEL: Record<TemplateSummary['status'], string> = {
  draft: 'Ciornă',
  published: 'Publicat',
  archived: 'Arhivat',
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
  /** Reviewers behind this competency's "others" composite (visible, non-self). */
  others_n: number
  gap: number | null
  johari: string | null
  categories: Record<string, { n: number; score: number | null; hidden: boolean }>
}

export interface ReportAggregates {
  competencies: CompetencyAgg[]
  visible_relationships: string[]
  hidden_relationships: string[]
  /** Report-level denominator behind "others" (visible non-self reviewers). */
  others_n: number
}

export interface Report {
  id: number
  cycle_id: number
  participant_id: number
  /** Present on the manager/owner view (get_with_owner); used to author the dev plan. */
  employee_id?: number
  aggregates_by_relationship: ReportAggregates
  gap_analysis: { flagged_competencies: number[] }
  hidden_categories: string[]
  manager_summary: string | null
  debrief_scheduled_at: string | null
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
  debrief_scheduled: boolean
  needs_summary_backfill: boolean
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
  scheduleDebrief: (reportId: number, scheduledAt?: string) =>
    api.post<{ ok: boolean }>(`${BASE}/reports/${reportId}/schedule-debrief`, { scheduled_at: scheduledAt }),
}

// ── Development plans ───────────────────────────────────────────────────────

export interface DevPlanGoal {
  competency_id?: number | null
  title?: string
  description?: string
  target_date?: string | null
  text?: string   // legacy shape — migrated to `title` on load
}
export interface PlanSuggestion { synthesis: string; goals: DevPlanGoal[] }
export interface DevPlan {
  id: number
  participant_id: number
  goals: DevPlanGoal[]
  linked_competencies: number[]
  status: string
}
export interface Checkin {
  id: number
  plan_id: number
  scheduled_date: string | null
  completed_at: string | null
  note: string | null
}
export interface DevPlanBundle { participant_id: number; plan: DevPlan | null; checkins: Checkin[]; can_edit: boolean }

export const eval360DevPlan = {
  get: (cycleId: number, employeeId: number) =>
    api.get<DevPlanBundle>(`${BASE}/dev-plan/${cycleId}/${employeeId}`),
  save: (cycleId: number, employeeId: number, goals: DevPlanGoal[], linked: number[]) =>
    api.post<{ plan: DevPlan }>(`${BASE}/dev-plan/${cycleId}/${employeeId}`, { goals, linked_competencies: linked }),
  generate: (cycleId: number, employeeId: number, mode: 'ai' | 'seed') =>
    api.post<{ suggestion: PlanSuggestion }>(`${BASE}/dev-plan/${cycleId}/${employeeId}/generate`, { mode }),
  finalize: (cycleId: number, employeeId: number) =>
    api.post<{ plan: DevPlan }>(`${BASE}/dev-plan/${cycleId}/${employeeId}/finalize`),
  addCheckin: (planId: number, scheduledDate: string, note?: string) =>
    api.post<{ checkin: Checkin }>(`${BASE}/dev-plans/${planId}/checkins`, { scheduled_date: scheduledDate, note }),
  completeCheckin: (checkinId: number, note?: string) =>
    api.post<{ ok: boolean }>(`${BASE}/checkins/${checkinId}/complete`, { note }),
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
