export type SignatureStatus = 'pending' | 'signed' | 'rejected' | 'expired'

export interface DocumentSignature {
  id: number
  document_type: string
  document_id: number
  signed_by: number
  signer_name?: string
  status: SignatureStatus
  signed_at: string | null
  ip_address: string | null
  document_hash: string | null
  original_pdf_path: string | null
  signed_pdf_path: string | null
  callback_url: string | null
  has_signature_image?: boolean
  created_at: string
  updated_at: string
}
