import { useQuery } from '@tanstack/react-query'
import { api } from './client'

// ── Campaign types ──

export type HappyTier = 'critical' | 'important' | 'normal'
export type HappyCampaignStatus = 'draft' | 'scheduled' | 'live' | 'paused' | 'archived'
export type HappyAckMode = 'none' | 'click' | 'quiz'

export interface AdminCampaign {
  id: number
  slug: string
  kind: string
  tier: HappyTier
  status: HappyCampaignStatus
  placements: string[]
  title: string
  summary?: string | null
  body_md?: string | null
  ack_mode?: HappyAckMode
  ack_deadline_at?: string | null
  starts_at?: string | null
  ends_at?: string | null
  media_key?: string | null
  media_alt?: string | null
  cta_label?: string | null
  cta_href?: string | null
  cta_deeplink?: string | null
}

export interface AdminAudienceRule {
  mode: 'include' | 'exclude'
  dimension: string
  value: string
}

export interface AdminQuizQuestion {
  position: number
  prompt: string
  options: string[]
  correct_index: number
}

export interface AdminCampaignDetail {
  campaign: AdminCampaign
  audience: AdminAudienceRule[]
  quiz: AdminQuizQuestion[]
}

export interface CampaignCreatePayload {
  slug: string
  kind: string
  tier: HappyTier
  placements: string[]
  title: string
  summary?: string
  body_md?: string
  ack_mode: HappyAckMode
  ack_deadline_at?: string | null
  starts_at?: string
  ends_at?: string
  media_key?: string
  media_alt?: string
  cta_label?: string
  cta_href?: string
  cta_deeplink?: string
}

export interface CampaignUpdatePayload extends Partial<CampaignCreatePayload> {
  audience?: AdminAudienceRule[]
  quiz?: AdminQuizQuestion[]
}

export interface PreviewAudienceResponse {
  count: number
  cohorts: { company: string; n: number }[]
}

export interface CampaignFunnel {
  targeted: number
  reached: number
  read_8s: number
  clicked: number
  acknowledged: number
  dismissed: number
}

export interface CampaignStats {
  daily: Array<Record<string, number | string>>
  funnel: CampaignFunnel
}

export interface ComplianceRow {
  user_id: number
  acknowledged: boolean
  acknowledged_at: string | null
  method: string | null
}

export interface ComplianceExport {
  campaign_id: number
  acknowledgements: ComplianceRow[]
}

export interface PublishResult {
  campaign: AdminCampaign
  targeted: number
}

export interface PublishError {
  error: string
  details?: string[]
}

// ── Pulse types ──

export type HappyPulseQType = 'likert5' | 'enps' | 'single' | 'open'

export interface AdminPulse {
  id: number
  slug: string
  title: string
  cadence: string
  status: string
  min_group_size?: number
  min_comment_group?: number
  opens_at?: string | null
  closes_at?: string | null
}

export interface AdminPulseQuestion {
  position: number
  prompt_ro: string
  prompt_en?: string | null
  qtype: HappyPulseQType
  driver?: string | null
}

export interface AdminPulseDetail {
  pulse: AdminPulse
  questions: AdminPulseQuestion[]
}

export interface PulseCreatePayload {
  slug: string
  title: string
  cadence: string
  min_group_size?: number
  min_comment_group?: number
}

/** One question's aggregate within a results block (backend `agg()` output). */
export type PulseQuestionScore =
  | { type: 'enps'; n: number; nps: number }
  | { type: 'likert5' | 'single'; n: number; avg: number; driver?: string | null }

/**
 * A results block — the overall roll-up or a single cohort. Mirrors the backend
 * `PulseRepository.get_results` contract exactly: either a suppressed marker
 * (below the anonymity threshold — numbers MUST stay hidden) or a map of
 * question-key → typed score.
 */
export type PulseBlock =
  | { suppressed: true; reason: string; n: number }
  | { [questionKey: string]: PulseQuestionScore }

export interface PulseResults {
  pulse_id?: number
  min_group_size?: number
  participation: { responses: number; invited: number; rate: number | null }
  overall: PulseBlock
  /** Keyed by opaque cohort_key: `node:<id>`, `company:<id>`, or `all`. */
  cohorts: Record<string, PulseBlock>
}

// ── Praise / KPI ──

export interface PraiseFlag {
  id: number
  kudos_id: number
  rule: string
  detail: unknown
  created_at: string
  from_user: number | string
  to_user: number | string
  period: string
}

export interface HappyHealth {
  live_campaigns: number
  open_ack_backlog: { count: number; oldest_deadline: string | null }
  kudos_last_7d: number
  flagged_kudos: number
  latest_pulse: { title: string; responses: number; invited: number; status: string } | null
}

// ── API ──

export const happyAdminApi = {
  // Campaigns
  listCampaigns: (status?: string) =>
    api.get<{ campaigns: AdminCampaign[] }>('/api/happy/admin/campaigns', status ? { status } : undefined),
  getCampaign: (id: number) => api.get<AdminCampaignDetail>(`/api/happy/admin/campaigns/${id}`),
  createCampaign: (body: CampaignCreatePayload) =>
    api.post<{ campaign: AdminCampaign }>('/api/happy/admin/campaigns', body),
  updateCampaign: (id: number, body: CampaignUpdatePayload) =>
    api.put<{ campaign: AdminCampaign }>(`/api/happy/admin/campaigns/${id}`, body),
  previewAudience: (id: number, audience?: AdminAudienceRule[]) =>
    api.post<PreviewAudienceResponse>(`/api/happy/admin/campaigns/${id}/preview-audience`, { audience }),
  publishCampaign: (id: number) => api.post<PublishResult>(`/api/happy/admin/campaigns/${id}/publish`),
  pauseCampaign: (id: number) => api.post<{ campaign: AdminCampaign }>(`/api/happy/admin/campaigns/${id}/pause`),
  getStats: (id: number) => api.get<CampaignStats>(`/api/happy/admin/campaigns/${id}/stats`),
  complianceExport: (id: number) =>
    api.get<ComplianceExport>(`/api/happy/admin/campaigns/${id}/compliance-export`),

  // Pulses
  listPulses: (status?: string) =>
    api.get<{ pulses: AdminPulse[] }>('/api/happy/admin/pulses', status ? { status } : undefined),
  getPulse: (id: number) => api.get<AdminPulseDetail>(`/api/happy/admin/pulses/${id}`),
  createPulse: (body: PulseCreatePayload) => api.post<{ pulse: AdminPulse }>('/api/happy/admin/pulses', body),
  updateQuestions: (id: number, questions: AdminPulseQuestion[]) =>
    api.put<{ questions: AdminPulseQuestion[] }>(`/api/happy/admin/pulses/${id}/questions`, { questions }),
  openPulse: (id: number, audienceUserIds?: number[]) =>
    api.post<{ status: string; invited: number }>(
      `/api/happy/admin/pulses/${id}/open`,
      audienceUserIds && audienceUserIds.length ? { audience_user_ids: audienceUserIds } : undefined,
    ),
  closePulse: (id: number) => api.post<{ status: string }>(`/api/happy/admin/pulses/${id}/close`),
  getResults: (id: number) => api.get<PulseResults>(`/api/happy/admin/pulses/${id}/results`),

  // Praise / KPI
  getFlags: () => api.get<{ flags: PraiseFlag[] }>('/api/happy/admin/praise/flags'),
  getHealth: () => api.get<HappyHealth>('/api/happy/admin/health'),
}

// ── Hooks ──

export function useAdminCampaigns(status?: string, enabled = true) {
  return useQuery({
    queryKey: ['happy', 'admin', 'campaigns', status ?? 'all'],
    queryFn: () => happyAdminApi.listCampaigns(status),
    enabled,
  })
}

export function useAdminCampaign(id: number | null) {
  return useQuery({
    queryKey: ['happy', 'admin', 'campaign', id],
    queryFn: () => happyAdminApi.getCampaign(id as number),
    enabled: id != null,
  })
}

export function useCampaignStats(id: number | null) {
  return useQuery({
    queryKey: ['happy', 'admin', 'campaign', id, 'stats'],
    queryFn: () => happyAdminApi.getStats(id as number),
    enabled: id != null,
  })
}

export function useAdminPulses(status?: string, enabled = true) {
  return useQuery({
    queryKey: ['happy', 'admin', 'pulses', status ?? 'all'],
    queryFn: () => happyAdminApi.listPulses(status),
    enabled,
  })
}

export function useAdminPulse(id: number | null) {
  return useQuery({
    queryKey: ['happy', 'admin', 'pulse', id],
    queryFn: () => happyAdminApi.getPulse(id as number),
    enabled: id != null,
  })
}

export function usePulseResults(id: number | null) {
  return useQuery({
    queryKey: ['happy', 'admin', 'pulse', id, 'results'],
    queryFn: () => happyAdminApi.getResults(id as number),
    enabled: id != null,
  })
}

export function usePraiseFlags(enabled = true) {
  return useQuery({
    queryKey: ['happy', 'admin', 'praise', 'flags'],
    queryFn: () => happyAdminApi.getFlags(),
    enabled,
  })
}

export function useHappyHealth(enabled = true) {
  return useQuery({
    queryKey: ['happy', 'admin', 'health'],
    queryFn: () => happyAdminApi.getHealth(),
    enabled,
  })
}
