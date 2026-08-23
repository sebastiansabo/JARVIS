import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  HappyPlacement,
  HappySurfaceResponse,
  HappyEventPayload,
  HappyEventResponse,
  HappyAckResponse,
  HappyQuizResponse,
  HappyAckQuizResponse,
  HappySnoozeResponse,
  HappyDismissResponse,
  HappyInboxResponse,
  HappyValueTagsResponse,
  HappyWallet,
  HappySendKudosPayload,
  HappySendKudosResponse,
  HappyReceivedResponse,
  HappyMyPraise,
  HappyPulseCurrent,
  HappyPulseAnswers,
} from '@/types/happy'

/**
 * Client for the Happy surface engine. Session-cookie auth via the shared `api`
 * helper (which does NOT auto-unwrap — the Happy contract returns bare objects).
 */
export const happyApi = {
  getSurface: (placement: HappyPlacement, route: string) =>
    api.get<HappySurfaceResponse>('/api/happy/surface', { placement, route }),

  postEvent: (payload: HappyEventPayload) =>
    api.post<HappyEventResponse>('/api/happy/events', payload),

  ack: (campaignId: number, impressionToken: string, surface: string) =>
    api.post<HappyAckResponse>(`/api/happy/campaigns/${campaignId}/ack`, {
      impression_token: impressionToken,
      method: 'click',
      surface,
    }),

  getQuiz: (campaignId: number) =>
    api.get<HappyQuizResponse>(`/api/happy/campaigns/${campaignId}/quiz`),

  // Comprehension-check ack. `answers` maps question position → chosen option index.
  ackQuiz: (campaignId: number, impressionToken: string, answers: Record<number, number>) =>
    api.post<HappyAckQuizResponse>(`/api/happy/campaigns/${campaignId}/ack`, {
      impression_token: impressionToken,
      method: 'quiz',
      answers,
    }),

  snooze: (campaignId: number, impressionToken: string) =>
    api.post<HappySnoozeResponse>(`/api/happy/campaigns/${campaignId}/snooze`, {
      impression_token: impressionToken,
    }),

  dismiss: (campaignId: number, impressionToken: string) =>
    api.post<HappyDismissResponse>(`/api/happy/campaigns/${campaignId}/dismiss`, {
      impression_token: impressionToken,
    }),

  getInbox: () => api.get<HappyInboxResponse>('/api/happy/inbox'),
}

/**
 * Reads a placement's resolved surface for the current user + route.
 * The server owns selection, ordering and frequency capping — the client only renders.
 */
export function useHappySurface(placement: HappyPlacement, route: string, enabled = true) {
  return useQuery({
    queryKey: ['happy', 'surface', placement, route],
    queryFn: () => happyApi.getSurface(placement, route),
    enabled,
    staleTime: 30_000,
  })
}

/** Peer-recognition (Praise) client. Session-cookie auth via the shared `api` helper. */
export const praiseApi = {
  getValueTags: () => api.get<HappyValueTagsResponse>('/api/happy/praise/value-tags'),

  getWallet: () => api.get<HappyWallet>('/api/happy/praise/wallet'),

  sendKudos: (payload: HappySendKudosPayload) =>
    api.post<HappySendKudosResponse>('/api/happy/praise/kudos', payload),

  getReceived: (limit = 10, offset = 0) =>
    api.get<HappyReceivedResponse>('/api/happy/praise/received', {
      limit: String(limit),
      offset: String(offset),
    }),

  getMyPraise: () => api.get<HappyMyPraise>('/api/happy/praise/me'),
}

/** Own giveable/redeemable balances + monthly expiry. */
export function useWallet(enabled = true) {
  return useQuery({
    queryKey: ['happy', 'praise', 'wallet'],
    queryFn: () => praiseApi.getWallet(),
    enabled,
    staleTime: 30_000,
  })
}

/** Own recognition streak + 12-week sent/received trend. No peer comparison. */
export function useMyPraise(enabled = true) {
  return useQuery({
    queryKey: ['happy', 'praise', 'me'],
    queryFn: () => praiseApi.getMyPraise(),
    enabled,
    staleTime: 60_000,
  })
}

/** Anonymous Pulse (surveys / eNPS) client. No identity is ever sent or returned. */
export const pulseApi = {
  getCurrent: () => api.get<HappyPulseCurrent>('/api/happy/pulse/current'),

  respond: (pulseId: number, answers: HappyPulseAnswers) =>
    api.post<{ ok: true }>(`/api/happy/pulse/${pulseId}/respond`, { answers }),
}

/** The currently live pulse for this user (or `pulse: null` when none is open). */
export function useCurrentPulse(enabled = true) {
  return useQuery({
    queryKey: ['happy', 'pulse', 'current'],
    queryFn: () => pulseApi.getCurrent(),
    enabled,
    staleTime: 60_000,
  })
}
