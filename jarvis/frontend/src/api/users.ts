import { api } from './client'
import type { UserDetail, CreateUserInput, UpdateUserInput, AuditEvent } from '@/types/users'

export const usersApi = {
  // Users
  getUsers: () => api.get<UserDetail[]>('/api/users'),
  getUser: (id: number) => api.get<UserDetail>(`/api/users/${id}`),
  createUser: (data: CreateUserInput) => api.post<{ success: boolean; id: number }>('/api/users', data),
  updateUser: (id: number, data: UpdateUserInput) => api.put<{ success: boolean }>(`/api/users/${id}`, data),
  deleteUser: (id: number) => api.delete<{ success: boolean }>(`/api/users/${id}`),
  bulkDeleteUsers: (ids: number[]) => api.post<{ success: boolean; deleted: number }>('/api/users/bulk-delete', { ids }),
  bulkUpdateRole: (ids: number[], role_id: number) =>
    api.post<{ success: boolean; updated: number }>('/api/users/bulk-update-role', { ids, role_id }),

  // Employees
  getEmployees: () => api.get<UserDetail[]>('/api/employees'),
  getEmployee: (id: number) => api.get<UserDetail>(`/api/employees/${id}`),
  createEmployee: (data: Partial<UserDetail>) => api.post<{ success: boolean; id: number }>('/api/employees', data),
  updateEmployee: (id: number, data: Partial<UserDetail>) =>
    api.put<{ success: boolean }>(`/api/employees/${id}`, data),
  deleteEmployee: (id: number) => api.delete<{ success: boolean }>(`/api/employees/${id}`),

  // Password
  setUserPassword: (userId: number, password: string) =>
    api.post<{ success: boolean }>(`/api/users/${userId}/set-password`, { password }),
  setDefaultPasswords: () => api.post<{ success: boolean }>('/api/users/set-default-passwords', {}),
  updateProfile: (data: { name?: string; phone?: string }) =>
    api.post<{ success: boolean }>('/api/auth/update-profile', data),

  // Org path (from organigram assignments)
  getUserOrgPath: (userId: number) =>
    api.get<{ company: string; brand: string; department: string; subdepartment: string; role: string }[]>(`/api/users/${userId}/org-path`),

  // Events / Audit Log
  getEvents: (params?: { limit?: number; offset?: number; event_type?: string; entity_type?: string }) => {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', String(params.limit))
    if (params?.offset) searchParams.set('offset', String(params.offset))
    if (params?.event_type) searchParams.set('event_type', params.event_type)
    if (params?.entity_type) searchParams.set('entity_type', params.entity_type)
    const qs = searchParams.toString()
    return api.get<AuditEvent[]>(`/api/events${qs ? `?${qs}` : ''}`)
  },
  getEventTypes: () => api.get<string[]>('/api/events/types'),
}
