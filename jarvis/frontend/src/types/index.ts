export interface User {
  id: number
  email: string
  name: string
  role_id: number
  role_name: string
  is_active: boolean
  company?: string
  company_id?: number
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
  can_access_marketing: boolean
  can_access_approvals: boolean
  can_access_dms: boolean
  can_access_forms: boolean
  can_access_ai_agent: boolean
  can_edit_crm: boolean
  can_delete_crm: boolean
  can_export_crm: boolean
  can_view_original_punches: boolean
  can_view_adjusted_punches: boolean
  can_adjust_punches: boolean
  // Full v2 permissions map — "module.entity.action" → bool (for sidebar/tab visibility)
  permissions?: Record<string, boolean>
  // Scope values for granted permissions — "module.entity.action" → 'own'|'department'|'all'
  permission_scopes?: Record<string, string>
}

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  details?: Record<string, string>
}
