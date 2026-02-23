import { api } from './client'
import type { DocumentSignature } from '@/types/signatures'

interface SignatureResponse {
  success: boolean
  signature: DocumentSignature
}

interface SignatureListResponse {
  success: boolean
  signatures: DocumentSignature[]
}

interface SignResponse {
  success: boolean
  signature: DocumentSignature
  callback_url?: string | null
}

interface RejectResponse {
  success: boolean
  callback_url?: string | null
}

export const signaturesApi = {
  request: (data: {
    document_type: string
    document_id: number
    signed_by?: number
    original_pdf_path?: string
    callback_url?: string
  }) => api.post<SignatureResponse>('/signatures/api/request', data),

  get: (id: number) =>
    api.get<SignatureResponse>(`/signatures/api/${id}`),

  getPending: () =>
    api.get<SignatureListResponse>('/signatures/api/pending'),

  getForDocument: (documentType: string, documentId: number) =>
    api.get<SignatureListResponse>(`/signatures/api/document/${documentType}/${documentId}`),

  sign: (id: number, signatureImage: string) =>
    api.post<SignResponse>(`/signatures/api/${id}/sign`, { signature_image: signatureImage }),

  reject: (id: number) =>
    api.post<RejectResponse>(`/signatures/api/${id}/reject`),
}
