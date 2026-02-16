import { api } from './client'
import type { InAppNotification } from '@/types/notifications'

export const notificationsApi = {
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
