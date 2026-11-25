import { api } from './client'
import type {
  InAppNotification, NotificationPreferencesView, UpdatePreferenceBody, ChannelFlags,
} from '@/types/notifications'

export const notificationsApi = {
  getPreferences: () =>
    api.get<NotificationPreferencesView>('/notifications/api/preferences'),

  updatePreference: (body: UpdatePreferenceBody) =>
    api.post<{ success: boolean; preferences: ChannelFlags }>(
      '/notifications/api/preferences', body),

  getNotifications: (params?: { limit?: number; offset?: number; unread_only?: boolean }) => {
    const qs = new URLSearchParams()
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.offset) qs.set('offset', String(params.offset))
    if (params?.unread_only) qs.set('unread_only', 'true')
    const q = qs.toString()
    return api.get<{ notifications: InAppNotification[] }>(`/notifications/api/list${q ? `?${q}` : ''}`)
  },

  getUnreadCount: () =>
    api.get<{ count: number }>('/notifications/api/unread-count'),

  markRead: (id: number) =>
    api.post<{ success: boolean }>(`/notifications/api/mark-read/${id}`),

  markAllRead: () =>
    api.post<{ success: boolean; count: number }>('/notifications/api/mark-all-read'),
}
