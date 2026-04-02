import { api } from './client'
import type { Invoice, InvoiceDmsLink, DmsDocSearchResult } from '@/types/invoices'
import type { ProfileSummary, ProfileInvoice, ProfileActivity, ProfileBonus, ProfilePontajeResponse, ProfileTeamPontajeResponse } from '@/types/profile'

export interface ProfileUpdatePayload {
  phone?: string
  cnp?: string
  birthdate?: string
  position?: string
  contract_work_date?: string
}

export const profileApi = {
  getSummary: () => api.get<ProfileSummary>('/profile/api/summary'),

  updateProfile: (data: ProfileUpdatePayload) => api.put<{ success: boolean }>('/profile/api/update', data),

  getInvoices: (params?: { status?: string; start_date?: string; end_date?: string; search?: string; department?: string; page?: number; per_page?: number }) => {
    const sp = new URLSearchParams()
    if (params?.status) sp.set('status', params.status)
    if (params?.start_date) sp.set('start_date', params.start_date)
    if (params?.end_date) sp.set('end_date', params.end_date)
    if (params?.search) sp.set('search', params.search)
    if (params?.department) sp.set('department', params.department)
    if (params?.page) sp.set('page', String(params.page))
    if (params?.per_page) sp.set('per_page', String(params.per_page))
    const qs = sp.toString()
    return api.get<{ invoices: ProfileInvoice[]; total: number; page: number; per_page: number }>(
      `/profile/api/invoices${qs ? `?${qs}` : ''}`,
    )
  },

  getInvoiceDetail: (id: number) => api.get<Invoice>(`/profile/api/invoices/${id}`),

  updateAllocations: (invoiceId: number, data: { allocations: Record<string, unknown>[] }) =>
    api.put<{ success: boolean }>(`/profile/api/invoices/${invoiceId}/allocations`, data),

  updateInvoiceMetadata: (invoiceId: number, data: Partial<Invoice>) =>
    api.put<{ success: boolean }>(`/profile/api/invoices/${invoiceId}/metadata`, data),

  getInvoiceDmsDocuments: (invoiceId: number) =>
    api.get<{ documents: InvoiceDmsLink[] }>(`/profile/api/invoices/${invoiceId}/dms-documents`),

  linkDmsDocument: (invoiceId: number, documentId: number) =>
    api.post<{ success: boolean; id: number }>(`/profile/api/invoices/${invoiceId}/dms-documents`, { document_id: documentId }),

  unlinkDmsDocument: (invoiceId: number, documentId: number) =>
    api.delete<{ success: boolean }>(`/profile/api/invoices/${invoiceId}/dms-documents/${documentId}`),

  searchDmsDocuments: (q?: string, limit = 20) =>
    api.get<{ documents: DmsDocSearchResult[] }>(
      `/profile/api/invoices/dms-search${q ? `?q=${encodeURIComponent(q)}&limit=${limit}` : `?limit=${limit}`}`,
    ),

  uploadAndLinkDms: (invoiceId: number, files: File[]) => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))
    return api.post<{ success: boolean; documents: Array<{ document_id: number; title: string; file: string }>; errors: Array<{ file: string; error: string }> }>(
      `/api/invoices/${invoiceId}/upload-and-link`, form,
    )
  },

  getHrEvents: (params?: { year?: number; month?: number; search?: string; page?: number; per_page?: number }) => {
    const sp = new URLSearchParams()
    if (params?.year) sp.set('year', String(params.year))
    if (params?.month) sp.set('month', String(params.month))
    if (params?.search) sp.set('search', params.search)
    if (params?.page) sp.set('page', String(params.page))
    if (params?.per_page) sp.set('per_page', String(params.per_page))
    const qs = sp.toString()
    return api.get<{ bonuses: ProfileBonus[]; total: number; page: number; per_page: number }>(
      `/profile/api/hr-events${qs ? `?${qs}` : ''}`,
    )
  },

  getActivity: (params?: { event_type?: string; page?: number; per_page?: number }) => {
    const sp = new URLSearchParams()
    if (params?.event_type) sp.set('event_type', params.event_type)
    if (params?.page) sp.set('page', String(params.page))
    if (params?.per_page) sp.set('per_page', String(params.per_page))
    const qs = sp.toString()
    return api.get<{ events: ProfileActivity[]; total: number; page: number; per_page: number }>(
      `/profile/api/activity${qs ? `?${qs}` : ''}`,
    )
  },

  getPontaje: (params?: { start?: string; end?: string }) => {
    const sp = new URLSearchParams()
    if (params?.start) sp.set('start', params.start)
    if (params?.end) sp.set('end', params.end)
    const qs = sp.toString()
    return api.get<ProfilePontajeResponse>(
      `/profile/api/pontaje${qs ? `?${qs}` : ''}`,
    )
  },

  getTeamPontaje: (params?: { mode?: 'daily' | 'range'; date?: string; start?: string; end?: string; node_id?: number }) => {
    const sp = new URLSearchParams()
    if (params?.mode) sp.set('mode', params.mode)
    if (params?.date) sp.set('date', params.date)
    if (params?.start) sp.set('start', params.start)
    if (params?.end) sp.set('end', params.end)
    if (params?.node_id) sp.set('node_id', String(params.node_id))
    const qs = sp.toString()
    return api.get<ProfileTeamPontajeResponse>(
      `/profile/api/team-pontaje${qs ? `?${qs}` : ''}`,
    )
  },

  getTeamPontajePunches: (biostarUserId: string, date: string) =>
    api.get<{ success: boolean; punches: import('@/types/biostar').BioStarPunchLog[] }>(
      `/profile/api/team-pontaje/punches?biostar_user_id=${biostarUserId}&date=${date}`,
    ),

  changePassword: (currentPassword: string, newPassword: string) =>
    api.post<{ success: boolean; message?: string; error?: string }>('/api/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
}
