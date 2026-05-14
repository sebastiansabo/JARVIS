import { api } from './client'
import type { Ticket, TicketComment, TicketStats, ItStaffUser } from '@/types/ticketing'

const BASE = '/ticketing/api'

function toQs(params: Record<string, unknown>): string {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

export const ticketingApi = {
  getTickets: (params?: {
    status?: string
    priority?: string
    category?: string
    assigned_to?: number
    my_tickets?: boolean
    search?: string
    limit?: number
    offset?: number
  }) =>
    api.get<{ success: boolean; items: Ticket[]; total: number }>(
      `${BASE}/tickets${toQs({ ...params })}`
    ),

  getTicket: (id: number) =>
    api.get<{ success: boolean; ticket: Ticket; comments: TicketComment[] }>(
      `${BASE}/tickets/${id}`
    ),

  createTicket: (data: { title: string; description?: string; priority: string; category: string }) =>
    api.post<{ success: boolean; id: number; ticket: Ticket }>(`${BASE}/tickets`, data),

  updateTicket: (id: number, data: Record<string, unknown>) =>
    api.put<{ success: boolean }>(`${BASE}/tickets/${id}`, data),

  deleteTicket: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/tickets/${id}`),

  addComment: (ticketId: number, content: string) =>
    api.post<{ success: boolean; comment: TicketComment }>(
      `${BASE}/tickets/${ticketId}/comments`,
      { content }
    ),

  deleteComment: (ticketId: number, commentId: number) =>
    api.delete<{ success: boolean }>(
      `${BASE}/tickets/${ticketId}/comments/${commentId}`
    ),

  getStats: () => api.get<TicketStats>(`${BASE}/tickets/stats`),

  getItStaff: () =>
    api.get<{ success: boolean; users: ItStaffUser[] }>(`${BASE}/users/it-staff`),
}
