import { api } from './client'
import type { TagGroup, Tag, EntityTag, AutoTagRule } from '@/types/tags'

export const tagsApi = {
  // Tag groups
  getGroups: (activeOnly = true) =>
    api.get<TagGroup[]>(`/api/tag-groups?active_only=${activeOnly}`),
  createGroup: (data: Partial<TagGroup>) =>
    api.post<{ success: boolean; id: number }>('/api/tag-groups', data),
  updateGroup: (id: number, data: Partial<TagGroup>) =>
    api.put<{ success: boolean }>(`/api/tag-groups/${id}`, data),
  deleteGroup: (id: number) =>
    api.delete<{ success: boolean }>(`/api/tag-groups/${id}`),

  // Tags
  getTags: (groupId?: number) =>
    api.get<Tag[]>(`/api/tags${groupId ? `?group_id=${groupId}` : ''}`),
  createTag: (data: Partial<Tag>) =>
    api.post<{ success: boolean; id: number }>('/api/tags', data),
  updateTag: (id: number, data: Partial<Tag>) =>
    api.put<{ success: boolean }>(`/api/tags/${id}`, data),
  deleteTag: (id: number) =>
    api.delete<{ success: boolean }>(`/api/tags/${id}`),

  // Entity tags
  getEntityTags: (entityType: string, entityId: number) =>
    api.get<EntityTag[]>(`/api/entity-tags?entity_type=${entityType}&entity_id=${entityId}`),

  getEntityTagsBulk: (entityType: string, entityIds: number[]) =>
    api.get<Record<string, EntityTag[]>>(
      `/api/entity-tags/bulk?entity_type=${entityType}&entity_ids=${entityIds.join(',')}`
    ),

  addEntityTag: (entityType: string, entityId: number, tagId: number) =>
    api.post<{ success: boolean }>('/api/entity-tags', {
      entity_type: entityType,
      entity_id: entityId,
      tag_id: tagId,
    }),

  removeEntityTag: (entityType: string, entityId: number, tagId: number) =>
    api.post<{ success: boolean; count: number }>('/api/entity-tags/bulk', {
      entity_type: entityType,
      entity_ids: [entityId],
      tag_id: tagId,
      action: 'remove',
    }),

  bulkEntityTags: (entityType: string, entityIds: number[], tagId: number, action: 'add' | 'remove') =>
    api.post<{ success: boolean; count: number }>('/api/entity-tags/bulk', {
      entity_type: entityType,
      entity_ids: entityIds,
      tag_id: tagId,
      action,
    }),

  // Auto-tag rules
  getAutoTagRules: (entityType?: string) =>
    api.get<AutoTagRule[]>(`/api/auto-tag-rules${entityType ? `?entity_type=${entityType}` : ''}`),
  createAutoTagRule: (data: Partial<AutoTagRule>) =>
    api.post<{ success: boolean; id: number }>('/api/auto-tag-rules', data),
  updateAutoTagRule: (id: number, data: Partial<AutoTagRule>) =>
    api.put<{ success: boolean }>(`/api/auto-tag-rules/${id}`, data),
  deleteAutoTagRule: (id: number) =>
    api.delete<{ success: boolean }>(`/api/auto-tag-rules/${id}`),
  runAutoTagRule: (id: number) =>
    api.post<{ success: boolean; matched: number; tagged: number }>(`/api/auto-tag-rules/${id}/run`, {}),
  getEntityFields: () =>
    api.get<Record<string, string[]>>('/api/auto-tag-rules/entity-fields'),
}
