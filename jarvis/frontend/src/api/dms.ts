import { api } from './client'
import type {
  DmsDocument,
  DmsCategory,
  DmsFile,
  DmsFilters,
  DmsStats,
  DmsRelationshipType,
} from '@/types/dms'

const BASE = '/dms/api'

function toQs(params: Record<string, unknown>): string {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

export const dmsApi = {
  // ---- Documents ----

  listDocuments: (filters?: DmsFilters) =>
    api.get<{ success: boolean; documents: DmsDocument[]; total: number }>(
      `${BASE}/documents${toQs({ ...filters })}`,
    ),

  getDocument: (id: number) =>
    api.get<{ success: boolean; document: DmsDocument }>(`${BASE}/documents/${id}`),

  createDocument: (data: Partial<DmsDocument>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/documents`, data),

  updateDocument: (id: number, data: Partial<DmsDocument>) =>
    api.put<{ success: boolean }>(`${BASE}/documents/${id}`, data),

  deleteDocument: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/documents/${id}`),

  restoreDocument: (id: number) =>
    api.post<{ success: boolean }>(`${BASE}/documents/${id}/restore`),

  permanentDelete: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/documents/${id}/permanent`),

  // ---- Children ----

  getChildren: (parentId: number) =>
    api.get<{ success: boolean; children: Record<DmsRelationshipType, DmsDocument[]> }>(
      `${BASE}/documents/${parentId}/children`,
    ),

  createChild: (
    parentId: number,
    data: {
      title: string; description?: string; relationship_type: DmsRelationshipType;
      category_id?: number; status?: string;
      doc_number?: string; doc_date?: string; expiry_date?: string; notify_user_id?: number;
    },
  ) => api.post<{ success: boolean; id: number }>(`${BASE}/documents/${parentId}/children`, data),

  // ---- Files ----

  getFiles: (documentId: number) =>
    api.get<{ success: boolean; files: DmsFile[] }>(`${BASE}/documents/${documentId}/files`),

  uploadFiles: (documentId: number, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return api.post<{
      success: boolean
      uploaded: Array<{ id: number; file_name: string; storage_type: string; storage_uri: string; file_size: number }>
      errors: Array<{ file: string; error: string }>
    }>(`${BASE}/documents/${documentId}/files/upload`, form)
  },

  deleteFile: (fileId: number) =>
    api.delete<{ success: boolean }>(`/dms/api/dms/files/${fileId}`),

  downloadFileUrl: (fileId: number) => `/dms/api/dms/files/${fileId}/download`,

  // ---- Stats ----

  getStats: (companyId?: number) =>
    api.get<{ success: boolean } & DmsStats>(`/dms/api/dms/stats${toQs({ company_id: companyId })}`),

  // ---- Categories ----

  listCategories: (companyId?: number, activeOnly = true) =>
    api.get<{ success: boolean; categories: DmsCategory[] }>(
      `/dms/api/dms/categories${toQs({ company_id: companyId, active_only: activeOnly })}`,
    ),

  getCategory: (id: number) =>
    api.get<{ success: boolean; category: DmsCategory }>(`/dms/api/dms/categories/${id}`),

  createCategory: (data: Partial<DmsCategory>) =>
    api.post<{ success: boolean; id: number }>(`/dms/api/dms/categories`, data),

  updateCategory: (id: number, data: Partial<DmsCategory>) =>
    api.put<{ success: boolean }>(`/dms/api/dms/categories/${id}`, data),

  deleteCategory: (id: number) =>
    api.delete<{ success: boolean }>(`/dms/api/dms/categories/${id}`),

  reorderCategories: (ids: number[]) =>
    api.put<{ success: boolean }>(`/dms/api/dms/categories/reorder`, { ids }),
}
