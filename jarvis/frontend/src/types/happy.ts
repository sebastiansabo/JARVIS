// Types for the Happy engagement module surface engine (Phase 1, web).
// Mirrors the contract served by GET /api/happy/* — see docs/happy/HAPPY_MODULE_SPEC.md §4.

export type HappyPlacement = 'interstitial' | 'dash_banner' | 'hub_card' | 'feed'

export type HappyTier = 'critical' | 'important' | 'normal'

export type HappyKind =
  | 'hr_announcement'
  | 'event'
  | 'action'
  | 'policy'
  | 'survey'
  | 'recognition'

export type HappyAckMode = 'none' | 'click' | 'quiz'

export type HappyAckState = 'pending' | 'acknowledged'

export type HappyEventType = 'impression' | 'read' | 'click' | 'dismiss' | 'snooze'

export interface HappyMedia {
  key: string
  url: string
  alt: string
  w?: number
  h?: number
}

export interface HappyCta {
  label: string
  href: string
  deeplink?: string
}

export interface HappyAck {
  mode: HappyAckMode
  deadline_at: string | null
  state: HappyAckState
  /** Number of comprehension questions (quiz mode only, not used in Phase 1 web). */
  questions?: number
}

export interface HappySurfaceItem {
  id: number
  kind: HappyKind
  tier: HappyTier
  kicker: string
  title: string
  summary: string
  body_md: string
  event_at: string | null
  media: HappyMedia | null
  cta: HappyCta | null
  ack: HappyAck | null
  dismissible: boolean
  snooze_remaining: number
  /** Signed short-lived token; required to POST any /api/happy/events row. */
  impression_token: string
}

export interface HappySurfaceMeta {
  capped: boolean
  next_eligible_at: string | null
}

export interface HappySurfaceResponse {
  placement: HappyPlacement
  items: HappySurfaceItem[]
  meta: HappySurfaceMeta
}

export interface HappyEventPayload {
  impression_token: string
  type: HappyEventType
  dwell_ms?: number
}

export interface HappyEventResponse {
  ok: true
}

export interface HappyAckResponse {
  acknowledged: boolean
  first_time: boolean
}

export interface HappyQuizQuestion {
  id: number
  position: number
  prompt: string
  options: string[]
}

export interface HappyQuizResponse {
  questions: HappyQuizQuestion[]
}

export interface HappyQuizResult {
  position: number
  correct: boolean
  /** Populated ONLY for wrong answers (reveal); null when the answer was correct. */
  correct_index: number | null
}

export interface HappyAckQuizResponse {
  acknowledged: boolean
  first_time?: boolean
  quiz: {
    all_correct: boolean
    results?: HappyQuizResult[]
  }
}

export interface HappySnoozeResponse {
  snooze_count: number
  snooze_remaining: number
}

export interface HappyDismissResponse {
  ok: true
}

export interface HappyInboxItem {
  id: number
  slug: string
  title: string
  tier: HappyTier
  ack_mode: HappyAckMode
  ack_deadline_at: string | null
}

export interface HappyInboxResponse {
  items: HappyInboxItem[]
}
