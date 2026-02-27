import { api } from './client'
import type {
  DmsDocument,
  DmsCategory,
  DmsFile,
  DmsFilters,
  DmsStats,
  DmsRelationshipType,
  DmsRelationshipTypeConfig,
  DmsParty,
  DmsPartyRole,
  DmsEntityType,
  DmsSignatureStatus,
  DmsWmlExtraction,
  DmsWmlChunk,
  DmsDriveSync,
  DmsSupplier,
  PartySuggestion,
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
      visibility?: 'all' | 'restricted'; allowed_role_ids?: number[] | null; allowed_user_ids?: number[] | null;
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

  // ---- Relationship Types ----

  listRelationshipTypes: (activeOnly = true) =>
    api.get<{ success: boolean; types: DmsRelationshipTypeConfig[] }>(
      `/dms/api/dms/relationship-types${toQs({ active_only: activeOnly })}`,
    ),

  createRelationshipType: (data: Partial<DmsRelationshipTypeConfig>) =>
    api.post<{ success: boolean; id: number }>(`/dms/api/dms/relationship-types`, data),

  updateRelationshipType: (id: number, data: Partial<DmsRelationshipTypeConfig>) =>
    api.put<{ success: boolean }>(`/dms/api/dms/relationship-types/${id}`, data),

  deleteRelationshipType: (id: number) =>
    api.delete<{ success: boolean }>(`/dms/api/dms/relationship-types/${id}`),

  reorderRelationshipTypes: (ids: number[]) =>
    api.put<{ success: boolean }>(`/dms/api/dms/relationship-types/reorder`, { ids }),

  // ---- Parties ----

  listParties: (documentId: number) =>
    api.get<{ success: boolean; parties: DmsParty[] }>(
      `${BASE}/documents/${documentId}/parties`,
    ),

  createParty: (documentId: number, data: {
    party_role: DmsPartyRole; entity_type: DmsEntityType;
    entity_name: string; entity_id?: number; entity_details?: Record<string, unknown>;
  }) => api.post<{ success: boolean; id: number }>(
    `${BASE}/documents/${documentId}/parties`, data,
  ),

  updateParty: (partyId: number, data: Partial<DmsParty>) =>
    api.put<{ success: boolean }>(`/dms/api/dms/parties/${partyId}`, data),

  deleteParty: (partyId: number) =>
    api.delete<{ success: boolean }>(`/dms/api/dms/parties/${partyId}`),

  suggestParties: (query: string) =>
    api.get<{ success: boolean; suggestions: PartySuggestion[] }>(
      `/dms/api/dms/parties/suggest${toQs({ q: query })}`,
    ),

  // ---- Signatures ----

  updateSignatureStatus: (documentId: number, data: {
    signature_status: DmsSignatureStatus; signature_provider?: string;
  }) => api.put<{ success: boolean }>(
    `${BASE}/documents/${documentId}/signature-status`, data,
  ),

  getPendingSignatures: () =>
    api.get<{ success: boolean; documents: DmsDocument[] }>(
      `${BASE}/documents/pending-signatures`,
    ),

  // ---- Extraction ----

  extractText: (documentId: number) =>
    api.post<{ success: boolean; extractions: DmsWmlExtraction[] }>(
      `${BASE}/documents/${documentId}/extract`,
    ),

  getExtractedText: (documentId: number) =>
    api.get<{ success: boolean; extractions: DmsWmlExtraction[] }>(
      `${BASE}/documents/${documentId}/text`,
    ),

  getChunks: (documentId: number) =>
    api.get<{ success: boolean; chunks: DmsWmlChunk[] }>(
      `${BASE}/documents/${documentId}/chunks`,
    ),

  // ---- Drive Sync ----

  getDriveSync: (documentId: number) =>
    api.get<{ success: boolean; sync: DmsDriveSync | null; drive_available: boolean }>(
      `${BASE}/documents/${documentId}/drive-sync`,
    ),

  syncToDrive: (documentId: number) =>
    api.post<{ success: boolean; folder_url?: string; uploaded?: string[]; skipped?: string[]; errors?: Array<{ file: string; error: string }> }>(
      `${BASE}/documents/${documentId}/drive-sync`,
    ),

  unsyncDrive: (documentId: number) =>
    api.delete<{ success: boolean }>(
      `${BASE}/documents/${documentId}/drive-sync`,
    ),

  getDriveStatus: () =>
    api.get<{ success: boolean; available: boolean }>(
      `/dms/api/dms/drive-status`,
    ),

  // ---- Suppliers ----

  listSuppliers: (params?: { search?: string; supplier_type?: string; active_only?: boolean; limit?: number; offset?: number }) =>
    api.get<{ success: boolean; suppliers: DmsSupplier[]; total: number }>(
      `/dms/api/dms/suppliers${toQs({ ...params })}`,
    ),

  getSupplier: (id: number) =>
    api.get<{ success: boolean; supplier: DmsSupplier }>(`/dms/api/dms/suppliers/${id}`),

  createSupplier: (data: Partial<DmsSupplier>) =>
    api.post<{ success: boolean; id: number }>(`/dms/api/dms/suppliers`, data),

  updateSupplier: (id: number, data: Partial<DmsSupplier>) =>
    api.put<{ success: boolean }>(`/dms/api/dms/suppliers/${id}`, data),

  deleteSupplier: (id: number) =>
    api.delete<{ success: boolean }>(`/dms/api/dms/suppliers/${id}`),
}
