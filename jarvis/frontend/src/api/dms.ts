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
  DmsPartyRoleConfig,
  DmsEntityType,
  DmsSignatureStatus,
  DmsWmlExtraction,
  DmsWmlChunk,
  DmsDriveSync,
  DmsSupplier,
  PartySuggestion,
  DmsFolder,
  DmsFolderAclEntry,
  DmsFolderPermissions,
  DmsAuditEntry,
  DmsModuleLink,
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

  // ---- Batch Operations ----

  batchDelete: (ids: number[]) =>
    api.post<{ success: boolean; affected: number }>(`/dms/api/dms/documents/batch-delete`, { ids }),

  batchCategory: (ids: number[], categoryId: number) =>
    api.post<{ success: boolean; affected: number }>(`/dms/api/dms/documents/batch-category`, { ids, category_id: categoryId }),

  batchStatus: (ids: number[], status: string) =>
    api.post<{ success: boolean; affected: number }>(`/dms/api/dms/documents/batch-status`, { ids, status }),

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

  suggestParties: (query: string, parentId?: number) =>
    api.get<{ success: boolean; suggestions: PartySuggestion[] }>(
      `/dms/api/dms/parties/suggest${toQs({ q: query, parent_id: parentId })}`,
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

  batchDeactivateSuppliers: (ids: number[]) =>
    api.post<{ success: boolean; affected: number }>('/dms/api/dms/suppliers/batch-deactivate', { ids }),

  getSupplierDocuments: (supId: number, limit = 20) =>
    api.get<{ success: boolean; documents: Array<{
      id: number; title: string; status: string; doc_number: string | null;
      doc_date: string | null; expiry_date: string | null; parent_id: number | null;
      relationship_type: string | null; party_role: string; category_name: string | null;
    }> }>(`/dms/api/dms/suppliers/${supId}/documents?limit=${limit}`),

  getSupplierInvoices: (supId: number, limit = 10) =>
    api.get<{ success: boolean; invoices: Array<{
      id: number; supplier: string; invoice_number: string; invoice_date: string;
      invoice_value: number; currency: string; value_ron: number | null;
      value_eur: number | null; status: string; payment_status: string; drive_link: string | null;
    }> }>(`/dms/api/dms/suppliers/${supId}/invoices?limit=${limit}`),

  syncAnaf: (supId: number) =>
    api.post<{
      success: boolean; error?: string; anaf_name?: string;
      updated_fields?: string[]; supplier?: DmsSupplier;
    }>(`/dms/api/dms/suppliers/${supId}/sync-anaf`, {}),

  syncAnafBatch: () =>
    api.post<{
      success: boolean; error?: string; synced: number; total: number;
      results: Array<{
        id: number; name: string; cui: string; status: string;
        anaf_name?: string; updated_fields?: string[];
      }>;
    }>('/dms/api/dms/suppliers/sync-anaf-batch', {}),

  // ---- Party Roles ----

  listPartyRoles: (activeOnly = true) =>
    api.get<{ success: boolean; roles: DmsPartyRoleConfig[] }>(
      `/dms/api/dms/party-roles${toQs({ active_only: activeOnly })}`,
    ),

  createPartyRole: (data: Partial<DmsPartyRoleConfig>) =>
    api.post<{ success: boolean; id: number }>(`/dms/api/dms/party-roles`, data),

  updatePartyRole: (id: number, data: Partial<DmsPartyRoleConfig>) =>
    api.put<{ success: boolean }>(`/dms/api/dms/party-roles/${id}`, data),

  deletePartyRole: (id: number) =>
    api.delete<{ success: boolean }>(`/dms/api/dms/party-roles/${id}`),

  reorderPartyRoles: (ids: number[]) =>
    api.put<{ success: boolean }>(`/dms/api/dms/party-roles/reorder`, { ids }),

  // ---- Linked Invoices (reverse lookup) ----

  getDocumentInvoices: (documentId: number) =>
    api.get<{ invoices: import('@/types/invoices').LinkedInvoice[] }>(
      `/api/dms-documents/${documentId}/invoices`,
    ),

  // ---- Folders ----

  listFolders: (parentId?: number) =>
    api.get<{ success: boolean; folders: DmsFolder[] }>(
      `/dms/api/dms/folders${toQs({ parent_id: parentId })}`,
    ),

  getFolderTree: () =>
    api.get<{ success: boolean; folders: DmsFolder[] }>(
      `/dms/api/dms/folders/tree`,
    ),

  getFolder: (id: number) =>
    api.get<{ success: boolean; folder: DmsFolder; ancestors: DmsFolder[]; children: DmsFolder[] }>(
      `/dms/api/dms/folders/${id}`,
    ),

  createFolder: (data: { name: string; parent_id?: number; description?: string; icon?: string; color?: string; inherit_permissions?: boolean }) =>
    api.post<{ success: boolean; folder: DmsFolder }>(
      `/dms/api/dms/folders`, data,
    ),

  updateFolder: (id: number, data: Partial<DmsFolder>) =>
    api.put<{ success: boolean; folder: DmsFolder }>(
      `/dms/api/dms/folders/${id}`, data,
    ),

  deleteFolder: (id: number) =>
    api.delete<{ success: boolean }>(`/dms/api/dms/folders/${id}`),

  moveFolder: (id: number, parentId: number | null) =>
    api.post<{ success: boolean; folder: DmsFolder }>(
      `/dms/api/dms/folders/${id}/move`, { parent_id: parentId },
    ),

  reorderFolders: (folderIds: number[]) =>
    api.put<{ success: boolean }>(`/dms/api/dms/folders/reorder`, { folder_ids: folderIds }),

  searchFolders: (query: string) =>
    api.get<{ success: boolean; folders: DmsFolder[] }>(
      `/dms/api/dms/folders/search${toQs({ q: query })}`,
    ),

  // ---- Folder ACL ----

  getFolderAcl: (folderId: number) =>
    api.get<{ success: boolean; acl: DmsFolderAclEntry[] }>(
      `/dms/api/dms/folders/${folderId}/acl`,
    ),

  setFolderAcl: (folderId: number, data: {
    user_id?: number; role_id?: number;
    can_view?: boolean; can_add?: boolean; can_edit?: boolean;
    can_delete?: boolean; can_manage?: boolean;
  }) =>
    api.post<{ success: boolean; entry: DmsFolderAclEntry }>(
      `/dms/api/dms/folders/${folderId}/acl`, data,
    ),

  batchSetFolderAcl: (folderId: number, entries: Array<{
    user_id?: number; role_id?: number;
    can_view?: boolean; can_add?: boolean; can_edit?: boolean;
    can_delete?: boolean; can_manage?: boolean;
  }>) =>
    api.post<{ success: boolean; entries: DmsFolderAclEntry[] }>(
      `/dms/api/dms/folders/${folderId}/acl/batch`, { entries },
    ),

  removeFolderAcl: (folderId: number, aclId: number) =>
    api.delete<{ success: boolean }>(`/dms/api/dms/folders/${folderId}/acl/${aclId}`),

  getMyFolderPermissions: (folderId: number) =>
    api.get<{ success: boolean; permissions: DmsFolderPermissions }>(
      `/dms/api/dms/folders/${folderId}/my-permissions`,
    ),

  // ---- Folder Module Links ----

  getFolderLinks: (folderId: number) =>
    api.get<{ success: boolean; links: DmsModuleLink[] }>(
      `/dms/api/dms/folders/${folderId}/links`,
    ),

  linkFolder: (folderId: number, module: string, moduleEntityId: number) =>
    api.post<{ success: boolean; link: DmsModuleLink }>(
      `/dms/api/dms/folders/${folderId}/links`, { module, module_entity_id: moduleEntityId },
    ),

  unlinkFolder: (folderId: number, module: string, entityId: number) =>
    api.delete<{ success: boolean }>(
      `/dms/api/dms/folders/${folderId}/links/${module}/${entityId}`,
    ),

  getModuleLinks: (module: string, entityId: number) =>
    api.get<{ success: boolean; links: DmsModuleLink[] }>(
      `/dms/api/dms/module-links/${module}/${entityId}`,
    ),

  // ---- Audit Log ----

  getAuditLog: (params?: { entity_type?: string; limit?: number; offset?: number }) =>
    api.get<{ success: boolean; entries: DmsAuditEntry[] }>(
      `/dms/api/dms/audit${toQs({ ...params })}`,
    ),

  getEntityAudit: (entityType: string, entityId: number) =>
    api.get<{ success: boolean; entries: DmsAuditEntry[] }>(
      `/dms/api/dms/audit/${entityType}/${entityId}`,
    ),

  getFolderActivity: (folderId: number) =>
    api.get<{ success: boolean; entries: DmsAuditEntry[] }>(
      `/dms/api/dms/folders/${folderId}/activity`,
    ),

  // ---- Folder Structure Sync ----

  syncFolderStructure: (years?: number[]) =>
    api.post<{ success: boolean; companies: number; created: { roots: number; year_folders: number; category_folders: number } }>(
      `/dms/api/dms/folders/sync-structure`, years ? { years } : {},
    ),

  // ---- Google Drive Sync ----

  syncFolderToDrive: (folderId: number) =>
    api.post<{ success: boolean; drive_folder_id?: string; drive_folder_url?: string }>(
      `/dms/api/dms/folders/${folderId}/drive-sync`, {},
    ),

  getFolderDriveStatus: (folderId: number) =>
    api.get<{ success: boolean; synced: boolean; drive_folder_id?: string; drive_folder_url?: string; drive_synced_at?: string }>(
      `/dms/api/dms/folders/${folderId}/drive-sync`,
    ),

  syncAllFoldersToDrive: (companyId?: number) =>
    api.post<{ success: boolean; total: number; synced: number; skipped: number; errors: number }>(
      `/dms/api/dms/folders/drive-sync-all`, companyId ? { company_id: companyId } : {},
    ),
}
