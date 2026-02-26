export interface User {
  id: number
  email: string
  name: string
  role_id: number
  role_name: string
  is_active: boolean
  company?: string
  brand?: string
  department?: string
  subdepartment?: string
  can_add_invoices: boolean
  can_edit_invoices: boolean
  can_delete_invoices: boolean
  can_view_invoices: boolean
  can_access_accounting: boolean
  can_access_settings: boolean
  can_access_connectors: boolean
  can_access_templates: boolean
  can_access_hr: boolean
  can_access_efactura: boolean
  can_access_statements: boolean
  is_hr_manager: boolean
  can_access_crm: boolean
  can_edit_crm: boolean
  can_delete_crm: boolean
  can_export_crm: boolean
}

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  details?: Record<string, string>
}
