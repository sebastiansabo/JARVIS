import { api } from './client'
import type { Theme, MenuItem, VatRate, DropdownOption, DefaultColumnsMap } from '@/types/settings'

export interface AiModel {
  id: number
  provider: string
  model_name: string
  display_name: string
  cost_per_1k_input: string
  cost_per_1k_output: string
  max_tokens: number
  default_temperature: string
  is_active: boolean
  is_default: boolean
  has_api_key: boolean
}

export const settingsApi = {
  // Themes
  getThemes: async (): Promise<Theme[]> => {
    const res = await api.get<{ themes: Theme[] } | Theme[]>('/api/themes')
    return Array.isArray(res) ? res : res.themes
  },
  getActiveTheme: () => api.get<Theme>('/api/themes/active'),
  getTheme: (id: number) => api.get<Theme>(`/api/themes/${id}`),
  createTheme: (data: Partial<Theme>) => api.post<Theme>('/api/themes', data),
  updateTheme: (id: number, data: Partial<Theme>) => api.put<Theme>(`/api/themes/${id}`, data),
  deleteTheme: (id: number) => api.delete<{ success: boolean }>(`/api/themes/${id}`),
  activateTheme: (id: number) => api.post<{ success: boolean }>(`/api/themes/${id}/activate`, {}),

  // Module Menu
  getModuleMenu: () => api.get<{ items: MenuItem[] }>('/api/module-menu'),
  getAllModuleMenu: () => api.get<{ items: MenuItem[] }>('/api/module-menu/all'),
  createMenuItem: (data: Partial<MenuItem>) => api.post<{ success: boolean; item: MenuItem }>('/api/module-menu', data),
  updateMenuItem: (id: number, data: Partial<MenuItem>) =>
    api.put<{ success: boolean; item: MenuItem }>(`/api/module-menu/${id}`, data),
  deleteMenuItem: (id: number) => api.delete<{ success: boolean }>(`/api/module-menu/${id}`),
  reorderMenuItems: (items: { id: number; sort_order: number }[]) =>
    api.post<{ success: boolean }>('/api/module-menu/reorder', { items }),

  // VAT Rates
  getVatRates: (activeOnly = false) =>
    api.get<VatRate[]>(`/api/vat-rates${activeOnly ? '?active_only=true' : ''}`),
  createVatRate: (data: Partial<VatRate>) => api.post<{ success: boolean }>('/api/vat-rates', data),
  updateVatRate: (id: number, data: Partial<VatRate>) => api.put<{ success: boolean }>(`/api/vat-rates/${id}`, data),
  deleteVatRate: (id: number) => api.delete<{ success: boolean }>(`/api/vat-rates/${id}`),

  // Dropdown Options
  getDropdownOptions: (type?: string) =>
    api.get<DropdownOption[]>(`/api/dropdown-options${type ? `?type=${type}` : ''}`),
  addDropdownOption: (data: Partial<DropdownOption>) => api.post<{ success: boolean }>('/api/dropdown-options', data),
  updateDropdownOption: (id: number, data: Partial<DropdownOption>) =>
    api.put<{ success: boolean }>(`/api/dropdown-options/${id}`, data),
  deleteDropdownOption: (id: number) => api.delete<{ success: boolean }>(`/api/dropdown-options/${id}`),

  // Notification Settings (returns flat SMTP config object)
  getNotificationSettings: () => api.get<Record<string, string>>('/api/notification-settings'),
  saveNotificationSettings: (data: Record<string, string | boolean>) =>
    api.post<{ success: boolean }>('/api/notification-settings', data),
  getNotificationLogs: () => api.get<unknown[]>('/api/notification-logs'),
  testEmail: (data: { to: string; subject?: string }) =>
    api.post<{ success: boolean }>('/api/notification-settings/test', data),

  // Default Columns
  getDefaultColumns: () => api.get<DefaultColumnsMap>('/api/default-columns'),
  setDefaultColumns: (data: { page: string; columns: string[]; apply_to_all?: boolean }) =>
    api.post<{ success: boolean }>('/api/default-columns', data),

  // AI Agent Settings
  getAiSettings: async () => {
    const res = await api.get<{ settings: Record<string, string> }>('/ai-agent/api/settings')
    return res.settings
  },
  saveAiSettings: (data: Record<string, string>) =>
    api.post<{ success: boolean }>('/ai-agent/api/settings', data),
  getAllModels: async () => {
    const res = await api.get<{ models: AiModel[] }>('/ai-agent/api/models/all')
    return res.models
  },
  setDefaultModel: (id: number) =>
    api.put<{ success: boolean }>(`/ai-agent/api/models/${id}/default`, {}),
  toggleModel: (id: number, isActive: boolean) =>
    api.put<{ success: boolean }>(`/ai-agent/api/models/${id}/toggle`, { is_active: isActive }),
  updateModelApiKey: (id: number, apiKey: string) =>
    api.put<{ success: boolean }>(`/ai-agent/api/models/${id}/api-key`, { api_key: apiKey }),
  reindexRag: (sourceType?: string) =>
    api.post<{ success: boolean }>('/ai-agent/api/rag/reindex', sourceType ? { source_type: sourceType } : {}),
  getRagStats: () =>
    api.get<{ total_documents: number; by_source_type: Record<string, number>; has_pgvector: boolean; has_embeddings: boolean; embedding_provider: string | null; embedding_dimensions: number | null }>('/ai-agent/api/rag/stats'),
  getRagSourcePermissions: () =>
    api.get<{ allowed_sources: string[] }>('/ai-agent/api/rag-source-permissions'),

  // Push Notification Manager
  getPushManagerSettings: () =>
    api.get<{
      settings: Record<string, string>
      categories: PushCategory[]
      stats: PushStats
    }>('/api/push-manager/settings'),
  savePushManagerSettings: (data: Record<string, string>) =>
    api.post<{ success: boolean }>('/api/push-manager/settings', data),
  getPushCategories: () =>
    api.get<{ categories: PushCategory[] }>('/api/push-manager/categories'),
  createPushCategory: (data: Partial<PushCategory>) =>
    api.post<{ success: boolean; category: PushCategory }>('/api/push-manager/categories', data),
  updatePushCategory: (id: number, data: Partial<PushCategory>) =>
    api.put<{ success: boolean; category: PushCategory }>(`/api/push-manager/categories/${id}`, data),
  deletePushCategory: (id: number) =>
    api.delete<{ success: boolean }>(`/api/push-manager/categories/${id}`),
  getPushStats: () =>
    api.get<PushStats>('/api/push-manager/stats'),
  testPush: () =>
    api.post<{ success: boolean; message: string }>('/api/push-manager/test', {}),
}

export interface PushCategory {
  id: number
  slug: string
  name: string
  description: string | null
  priority: 'critical' | 'high' | 'normal' | 'low'
  is_active: boolean
  max_per_hour: number | null
  ttl_seconds: number | null
  android_channel_id: string
  is_builtin: boolean
  sends_24h?: number
  created_at: string
  updated_at: string
}

export interface PushStats {
  sends_24h: number
  sends_7d: number
  sends_30d: number
  active_devices: number
}
