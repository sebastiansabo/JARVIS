export interface DmsCategory {
  id: number
  name: string
  slug: string
  icon: string
  color: string
  description: string | null
  company_id: number | null
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string | null
  document_count?: number
  allowed_role_ids: number[] | null
}

export type DmsDocumentStatus = 'draft' | 'active' | 'archived'
export type DmsRelationshipType = string

export interface DmsRelationshipTypeConfig {
  id: number
  slug: string
  label: string
  icon: string
  color: string
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export type DmsSignatureStatus = 'pending' | 'sent' | 'signed' | 'declined' | 'expired' | null
export type DmsPartyRole = string

export interface DmsPartyRoleConfig {
  id: number
  slug: string
  label: string
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string | null
}
export type DmsEntityType = 'company' | 'person' | 'external'

export interface DmsParty {
  id: number
  document_id: number
  party_role: DmsPartyRole
  entity_type: DmsEntityType
  entity_id: number | null
  entity_name: string
  entity_details: Record<string, unknown> | null
  sort_order: number
  created_at: string
}

export interface DmsWmlExtraction {
  file_id: number
  file_name: string
  raw_text: string | null
  extraction_method: string | null
  extracted_at: string | null
  chunk_count?: number
}

export interface DmsWmlChunk {
  id: number
  chunk_index: number
  heading: string | null
  content: string
  token_count: number | null
}

export interface DmsDocument {
  id: number
  title: string
  description: string | null
  category_id: number | null
  category_name: string | null
  category_icon: string | null
  category_color: string | null
  company_id: number
  company_name: string | null
  status: DmsDocumentStatus
  parent_id: number | null
  relationship_type: DmsRelationshipType | null
  metadata: Record<string, unknown>
  doc_number: string | null
  doc_date: string | null
  expiry_date: string | null
  days_to_expiry: number | null
  notify_user_id: number | null
  notify_user_name: string | null
  signature_status: DmsSignatureStatus
  signature_provider: string | null
  signature_requested_at: string | null
  signature_completed_at: string | null
  visibility: 'all' | 'restricted'
  allowed_role_ids: number[] | null
  allowed_user_ids: number[] | null
  created_by: number
  created_by_name: string | null
  created_at: string
  updated_at: string | null
  deleted_at: string | null
  file_count?: number
  children_count?: number
  children?: Record<DmsRelationshipType, DmsDocument[]>
  files?: DmsFile[]
  parties?: DmsParty[]
}

export interface DmsFile {
  id: number
  document_id: number
  file_name: string
  file_type: string | null
  mime_type: string | null
  file_size: number | null
  storage_type: 'drive' | 'local'
  storage_uri: string
  drive_file_id: string | null
  uploaded_by: number
  uploaded_by_name: string | null
  created_at: string
}

export interface DmsDriveSync {
  synced: boolean
  status: 'pending' | 'synced' | 'partial' | 'error' | null
  folder_url: string | null
  last_synced_at: string | null
  error_message: string | null
}

export type DmsSupplierType = 'company' | 'person'

export interface DmsSupplier {
  id: number
  name: string
  supplier_type: DmsSupplierType
  cui: string | null
  j_number: string | null
  address: string | null
  city: string | null
  county: string | null
  nr_reg_com: string | null
  bank_account: string | null
  iban: string | null
  bank_name: string | null
  phone: string | null
  email: string | null
  company_id: number | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export interface PartySuggestion {
  id: number | null
  name: string
  entity_type: DmsEntityType
  source: 'company' | 'supplier' | 'invoice'
  cui?: string | null
  vat?: string | null
  phone?: string | null
  email?: string | null
}

export interface DmsFilters {
  category_id?: number
  company_id?: number
  status?: string
  search?: string
  limit?: number
  offset?: number
}

export interface DmsStats {
  by_category: Array<{
    category_id: number
    category_name: string
    count: number
    icon: string
    color: string
  }>
  by_status: {
    total: number
    draft: number
    active: number
    archived: number
  }
}
