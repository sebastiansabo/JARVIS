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
}

export type DmsDocumentStatus = 'draft' | 'active' | 'archived'
export type DmsRelationshipType = 'annex' | 'deviz' | 'proof' | 'other'

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
  created_by: number
  created_by_name: string | null
  created_at: string
  updated_at: string | null
  deleted_at: string | null
  file_count?: number
  children_count?: number
  children?: Record<DmsRelationshipType, DmsDocument[]>
  files?: DmsFile[]
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
