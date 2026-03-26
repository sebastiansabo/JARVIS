// Forms Module — TypeScript types

export type FormStatus = 'draft' | 'published' | 'disabled' | 'archived'

export type FieldType =
  | 'short_text'
  | 'long_text'
  | 'email'
  | 'phone'
  | 'number'
  | 'dropdown'
  | 'radio'
  | 'checkbox'
  | 'date'
  | 'file_upload'
  | 'heading'
  | 'paragraph'
  | 'hidden'
  | 'signature'

export interface ApprovalConfig {
  flow_id?: number
  notify_on_submit?: number[]
  notify_on_approve?: number[]
  notify_on_reject?: number[]
  notify_respondent?: boolean
  requires_signature?: boolean
  signature_signer?: 'respondent' | 'approver' | 'owner'
}

export interface FormField {
  id: string
  type: FieldType
  label: string
  required?: boolean
  placeholder?: string
  options?: string[]
  order: number
  config?: Record<string, unknown>
}

export interface Form {
  id: number
  name: string
  slug: string
  description: string | null
  company_id: number
  company_name: string | null
  status: FormStatus
  schema: FormField[]
  published_schema: FormField[] | null
  settings: FormSettings
  utm_config: UtmConfig
  branding: FormBranding
  owner_id: number
  owner_name: string | null
  created_by: number
  created_by_name: string | null
  version: number
  published_at: string | null
  requires_approval: boolean
  approval_config?: ApprovalConfig
  submission_count?: number
  created_at: string
  updated_at: string | null
}

export interface FormSettings {
  thank_you_message?: string
  redirect_url?: string
  submission_limit?: number
  limit_message?: string
}

export interface UtmConfig {
  track?: string[]
  defaults?: Record<string, string>
}

export interface FormBranding {
  logo_url?: string
  primary_color?: string
  background_color?: string
}

export interface FormFilters {
  status?: string
  company_id?: number
  owner_id?: number
  search?: string
  limit?: number
  offset?: number
}

export interface FormSubmission {
  id: number
  form_id: number
  form_version: number
  answers: Record<string, unknown>
  form_schema_snapshot: FormField[]
  respondent_name: string | null
  respondent_email: string | null
  respondent_phone: string | null
  respondent_ip: string | null
  respondent_user_id: number | null
  respondent_user_name: string | null
  utm_data: Record<string, string>
  source: 'web_public' | 'web_internal' | 'mobile'
  status: 'new' | 'read' | 'flagged' | 'approved' | 'rejected'
  approval_request_id: number | null
  form_name?: string
  form_slug?: string
  company_id: number | null
  created_at: string
  updated_at: string | null
}

export interface SubmissionFilters {
  status?: string
  source?: string
  search?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
}

// Public form data (returned by /forms/public/:slug)
export interface PublicForm {
  id: number
  name: string
  slug: string
  description: string | null
  schema: FormField[]
  settings: FormSettings
  branding: FormBranding
  utm_config: UtmConfig
  company_name: string
}
