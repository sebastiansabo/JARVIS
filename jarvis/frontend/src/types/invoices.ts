export interface Invoice {
  id: number
  supplier: string
  invoice_number: string
  invoice_date: string
  invoice_value: number
  currency: string
  value_ron: number | null
  value_eur: number | null
  exchange_rate: number | null
  drive_link: string | null
  comment: string | null
  status: string
  payment_status: string
  subtract_vat: boolean
  vat_rate: number | null
  net_value: number | null
  invoice_template: string | null
  deleted_at: string | null
  created_at: string
  updated_at: string | null
  allocation_mode?: 'whole' | 'per_line'
  line_items?: LineItem[]
  allocations?: Allocation[]
}

export interface LineItem {
  description: string
  quantity: number
  unit_price: number
  amount: number
  vat_rate?: number | null
}

export interface Allocation {
  id: number
  invoice_id: number
  company: string
  brand: string | null
  department: string
  subdepartment: string | null
  allocation_percent: number
  allocation_value: number
  responsible: string | null
  comment: string | null
  locked: boolean
  reinvoice_to: string | null
  reinvoice_department: string | null
  reinvoice_subdepartment: string | null
  reinvoice_brand: string | null
  line_item_index?: number | null
  reinvoice_destinations: {
    id: number
    company: string
    brand: string | null
    department: string
    subdepartment: string | null
    percentage: number
    value: number
  }[]
}

export interface InvoiceSummary {
  company?: string
  department?: string
  brand?: string
  supplier?: string
  invoice_count: number
  total_value_ron: number
  total_value_eur: number
  avg_exchange_rate: number | null
}

export interface ParseResult {
  success: boolean
  data?: {
    supplier: string
    supplier_vat: string | null
    customer: string | null
    customer_vat: string | null
    invoice_number: string
    invoice_date: string
    invoice_value: number
    currency: string
    description: string | null
    raw_text: string | null
    auto_detected_template: string | null
    auto_detected_template_id: number | null
    drive_link: string | null
    value_ron: number | null
    value_eur: number | null
    exchange_rate: number | null
    invoice_type?: 'standard' | 'credit_note' | 'advance_payment' | 'proforma'
    line_items?: { description: string; quantity: number; unit_price: number; amount: number; vat_rate?: number | null }[]
    efactura_match?: {
      id: number
      partner_name: string
      partner_cif: string | null
      invoice_number: string
      issue_date: string | null
      total_amount: number | null
      currency: string | null
      jarvis_invoice_id: number | null
    } | null
  }
  error?: string
}

export interface DeptSuggestion {
  company: string
  brand: string | null
  department: string
  subdepartment: string | null
  frequency: number
}

export interface InvoiceTemplate {
  id: number
  name: string
  template_type: 'fixed' | 'format'
  supplier: string | null
  supplier_vat: string | null
  customer_vat: string | null
  currency: string | null
  description: string | null
}

export interface InvoiceFilters {
  company?: string
  department?: string
  subdepartment?: string
  brand?: string
  status?: string
  payment_status?: string
  start_date?: string
  end_date?: string
  search?: string
}

export interface SubmitInvoiceInput {
  supplier: string
  invoice_template?: string
  invoice_number: string
  invoice_date: string
  invoice_value: number
  currency?: string
  drive_link?: string
  comment?: string
  payment_status?: string
  subtract_vat?: boolean
  vat_rate?: number
  net_value?: number
  value_ron?: number
  value_eur?: number
  exchange_rate?: number
  allocation_mode?: 'whole' | 'per_line'
  distributions: {
    company: string
    brand?: string
    department: string
    subdepartment?: string
    allocation: number // 0-1 decimal
    locked?: boolean
    comment?: string
    line_item_index?: number
    reinvoice_destinations?: {
      company: string
      brand?: string
      department: string
      subdepartment?: string
      percentage: number
    }[]
  }[]
}
