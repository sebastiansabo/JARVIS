// Company connection to ANAF e-Factura
export interface CompanyConnection {
  id: number
  cif: string
  display_name: string
  environment: 'test' | 'production'
  last_sync_at: string | null
  last_received_cursor: string | null
  last_sent_cursor: string | null
  status: 'active' | 'paused' | 'error' | 'cert_expired'
  status_message: string | null
  config: Record<string, unknown>
  cert_fingerprint: string | null
  cert_expires_at: string | null
  created_at: string
  updated_at: string | null
}

// e-Factura invoice
export interface EFacturaInvoice {
  id: number
  cif_owner: string
  company_id: number | null
  company_name: string | null
  direction: 'received' | 'sent'
  partner_cif: string
  partner_name: string
  invoice_number: string
  invoice_series: string | null
  issue_date: string | null
  due_date: string | null
  total_amount: number
  total_vat: number
  total_without_vat: number
  currency: string
  status: 'uploaded' | 'valid' | 'invalid' | 'processed' | 'error'
  created_at: string | null
  updated_at: string | null
  // Computed / extra fields from API
  full_invoice_number?: string
  allocated?: boolean
  ignored?: boolean
  deleted?: boolean
  // Override fields (for unallocated)
  type_override?: string | null
  department_override?: string | null
  subdepartment_override?: string | null
  department_override_2?: string | null
  subdepartment_override_2?: string | null
  // Mapping fields (joined from supplier_mappings)
  mapped_supplier_name?: string | null
  mapped_type_names?: string[] | null
  mapped_brand?: string | null
  mapped_department?: string | null
  mapped_subdepartment?: string | null
  mapped_kod_konto?: string | null
}

export interface EFacturaInvoiceSummary {
  total_count: number
  total_amount: number
  by_direction: {
    received: { count: number; amount: number }
    sent: { count: number; amount: number }
  }
  by_status: Record<string, { count: number; amount: number }>
}

export interface Pagination {
  page: number
  limit: number
  total: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

// Sync run record
export interface SyncRun {
  id: number
  run_id: string
  company_cif: string
  started_at: string | null
  finished_at: string | null
  success: boolean
  direction: string | null
  messages_checked: number
  invoices_fetched: number
  invoices_created: number
  invoices_updated: number
  invoices_skipped: number
  errors_count: number
  cursor_before: string | null
  cursor_after: string | null
  error_summary: string | null
}

// Sync error
export interface SyncError {
  id: number
  run_id: string
  message_id: string | null
  invoice_ref: string | null
  error_type: string
  error_code: string | null
  error_message: string
  request_hash: string | null
  response_hash: string | null
  stack_trace: string | null
  created_at: string | null
  is_retryable: boolean
}

// ANAF message (from fetch endpoint)
export interface ANAFMessage {
  id: string
  cif: string
  upload_id: string | null
  download_id: string | null
  message_type: string
  creation_date: string | null
  status: string | null
  // Extra fields from mock/real
  tip?: string
  data_creare?: string
}

// Supplier mapping
export interface SupplierMapping {
  id: number
  partner_name: string
  partner_cif: string | null
  supplier_name: string
  supplier_note: string | null
  supplier_vat: string | null
  kod_konto: string | null
  type_ids: number[]
  type_names: string[]
  brand: string | null
  department: string | null
  subdepartment: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

// Partner type
export interface SupplierType {
  id: number
  name: string
  description: string | null
  hide_in_filter: boolean
  is_active: boolean
  mapping_count?: number
  created_at: string
  updated_at: string | null
}

// OAuth status
export interface OAuthStatus {
  authenticated: boolean
  expires_at: string | null
  expires_in_seconds: number | null
  cif: string
}

// ANAF status
export interface ANAFStatus {
  mock_mode: boolean
  rate_limit?: {
    max_per_hour: number
    remaining: number
  }
}

// Import result
export interface ImportResult {
  imported: number
  skipped: number
  errors: string[]
  company_matched: boolean
  company_id: number | null
}

// Sync all result
export interface SyncAllResult {
  companies_synced: number
  total_fetched: number
  total_imported: number
  total_skipped: number
  errors: string[]
  company_results: {
    cif: string
    display_name: string
    fetched: number
    imported: number
    skipped: number
    errors: string[]
  }[]
}

// Duplicate invoice
export interface DuplicateInvoice {
  efactura_id: number
  existing_invoice_id: number
  partner_name: string
  invoice_number: string
  amount: number
  confidence?: number
  match_reason?: string
}

// Filters for invoice listing
export interface EFacturaInvoiceFilters {
  cif?: string
  company_id?: number
  direction?: 'received' | 'sent'
  start_date?: string
  end_date?: string
  search?: string
  hide_typed?: boolean
  page?: number
  limit?: number
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
}

// ANAF fetch filters
export interface ANAFFetchFilters {
  cif: string
  days?: number
  page?: number
  filter?: 'received' | 'sent' | 'all'
}

// Company for sync
export interface SyncCompany {
  cif: string
  display_name: string
}

// Company lookup result
export interface CompanyLookup {
  name: string
  cif: string
  address: string
  vat_payer: boolean
  registration_number: string | null
}

// Distinct partner
export interface DistinctSupplier {
  partner_name: string
  partner_cif: string | null
  invoice_count?: number
}

// Error stats
export interface ErrorStats {
  total_errors: number
  by_type: Record<string, number>
  by_company: Record<string, number>
  retryable_count: number
}
