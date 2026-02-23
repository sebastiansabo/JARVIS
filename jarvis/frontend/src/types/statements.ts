export interface Statement {
  id: number
  filename: string
  file_hash: string | null
  company_name: string | null
  company_cui: string | null
  account_number: string | null
  period_from: string | null
  period_to: string | null
  total_transactions: number
  new_transactions: number
  duplicate_transactions: number
  uploaded_by: number | null
  uploaded_by_name?: string | null
  uploaded_at: string
}

export interface Transaction {
  id: number
  statement_id: number | null
  statement_file: string | null
  company_name: string | null
  company_cui: string | null
  account_number: string | null
  transaction_date: string
  value_date: string | null
  description: string
  vendor_name: string | null
  matched_supplier: string | null
  amount: number
  currency: string
  original_amount: number | null
  original_currency: string | null
  exchange_rate: number | null
  auth_code: string | null
  card_number: string | null
  transaction_type: string | null
  status: 'pending' | 'resolved' | 'ignored'
  invoice_id: number | null
  invoice_number?: string | null
  match_method: string | null
  suggested_invoice_id: number | null
  suggested_confidence: number | null
  merged_from_id: number | null
  merged_count?: number
  created_at: string
  updated_at: string | null
}

export interface VendorMapping {
  id: number
  pattern: string
  supplier_name: string
  supplier_vat: string | null
  template_id: number | null
  is_active: boolean
  created_at: string
}

export interface TransactionSummary {
  by_status: {
    pending: { count: number; total: number }
    resolved: { count: number; total: number }
    ignored: { count: number; total: number }
    merged?: { count: number; total: number }
  }
  by_company: { company_name: string; company_cui: string; count: number; total: number }[]
  by_supplier: { matched_supplier: string; count: number; total: number }[]
}

export interface TransactionFilters {
  status?: string
  company_cui?: string
  supplier?: string
  date_from?: string
  date_to?: string
  search?: string
  sort?: string
  limit?: number
  offset?: number
}

export interface FilterOptions {
  companies: { company_name: string; company_cui: string }[]
  suppliers: string[]
}

export interface UploadResult {
  success: boolean
  statements: {
    filename: string
    statement_id: number
    company_name: string
    company_cui: string
    total_transactions: number
    new_transactions: number
    duplicate_transactions: number
    vendor_matched_count: number
    invoice_matched_count: number
    period: { from: string; to: string }
  }[]
  total_new: number
  total_duplicates: number
}

export interface AutoMatchResult {
  success: boolean
  matched: number
  suggested: number
  unmatched: number
  results: {
    transaction_id: number
    status: 'matched' | 'suggested' | 'unmatched'
    invoice_id?: number
    confidence?: number
  }[]
  message: string
}

export interface InvoiceSuggestion {
  invoice_id: number
  invoice_number: string
  supplier: string
  amount: number
  currency: string
  date: string
  confidence: number
  match_reason: string
}
