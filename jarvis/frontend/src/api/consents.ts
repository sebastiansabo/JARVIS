import { api } from './client'

export interface ConsentDocument {
  id: number
  doc_key: string
  title: string
  body: string
  sort_order: number
  version: number
  requires_signature: boolean
}

// Admin editor + single-document fetch also return the moderation flags
// (see core/consents/repositories/consent_repository.py get_by_key/get_by_id/list_all).
export interface ConsentDocumentAdmin extends ConsentDocument {
  is_active: boolean
  is_mandatory: boolean
  updated_at?: string
  updated_by?: number
}

// create_document()/update_document() RETURNING clause only returns this subset.
export interface ConsentDocumentMutationResult {
  id: number
  doc_key: string
  title: string
  version: number
  is_active: boolean
}

export interface CreateConsentDocumentPayload {
  doc_key: string
  title: string
  body?: string
  sort_order?: number
  requires_signature?: boolean
  is_mandatory?: boolean
  is_active?: boolean
}

export interface UpdateConsentDocumentPayload {
  title?: string
  body?: string
  sort_order?: number
  is_active?: boolean
}

export interface ConsentComplianceDocument {
  doc_key: string
  title: string
  signed: boolean
  signed_at: string | null
}

export interface ConsentComplianceUser {
  user_id: number
  name: string
  email: string
  company: string
  documents: ConsentComplianceDocument[]
}

interface PendingConsentsResponse {
  complete: boolean
  pending: ConsentDocument[]
}

// GET /api/consents/mine — current user's signed state for every active
// document (LEFT JOIN, so unsigned docs still appear with signed_at: null).
// Powers the profile "Acorduri semnate" section.
export interface ConsentMineDocument {
  doc_key: string
  title: string
  signed_at: string | null
}

interface SignConsentResponse {
  complete: boolean
  pending_count: number
}

export const consentsApi = {
  getPending: () => api.get<PendingConsentsResponse>('/api/consents/pending'),

  getMine: () => api.get<{ documents: ConsentMineDocument[] }>('/api/consents/mine'),

  sign: (documentId: number, signatureImage: string) =>
    api.post<SignConsentResponse>('/api/consents/sign', {
      document_id: documentId,
      signature_image: signatureImage,
    }),

  getDocument: (docKey: string) =>
    api.get<{ document: ConsentDocumentAdmin }>(`/api/consents/documents/${docKey}`),

  listDocuments: () => api.get<{ documents: ConsentDocumentAdmin[] }>('/api/consents/documents'),

  createDocument: (payload: CreateConsentDocumentPayload) =>
    api.post<{ document: ConsentDocumentMutationResult }>('/api/consents/documents', payload),

  updateDocument: (id: number, payload: UpdateConsentDocumentPayload) =>
    api.put<{ document: ConsentDocumentMutationResult }>(`/api/consents/documents/${id}`, payload),

  getCompliance: (status?: 'pending') =>
    api.get<{ compliance: ConsentComplianceUser[] }>(
      '/api/consents/compliance',
      status ? { status } : undefined,
    ),
}
