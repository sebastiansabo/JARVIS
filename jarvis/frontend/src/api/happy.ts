import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  HappyPlacement,
  HappySurfaceResponse,
  HappyEventPayload,
  HappyEventResponse,
  HappyAckResponse,
  HappySnoozeResponse,
  HappyDismissResponse,
  HappyInboxResponse,
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
