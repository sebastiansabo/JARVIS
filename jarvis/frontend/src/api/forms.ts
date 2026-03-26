import { api } from './client'
import type {
  Form,
  FormFilters,
  FormSubmission,
  SubmissionFilters,
  PublicForm,
} from '@/types/forms'

const BASE = '/forms/api'

function toQs(params: Record<string, unknown>): string {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

export const formsApi = {
  // ---- Forms CRUD ----

  listForms: (filters?: FormFilters) =>
    api.get<{ forms: Form[]; total: number }>(`${BASE}/forms${toQs({ ...filters })}`),

  getForm: (id: number) =>
    api.get<Form>(`${BASE}/forms/${id}`),

  createForm: (data: Partial<Form>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/forms`, data),

  updateForm: (id: number, data: Partial<Form>) =>
    api.put<{ success: boolean }>(`${BASE}/forms/${id}`, data),

  publishForm: (id: number) =>
    api.post<{ success: boolean; version: number }>(`${BASE}/forms/${id}/publish`),

  disableForm: (id: number) =>
    api.post<{ success: boolean }>(`${BASE}/forms/${id}/disable`),

  duplicateForm: (id: number) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/forms/${id}/duplicate`),

  deleteForm: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/forms/${id}`),

  // ---- Submissions ----

  listSubmissions: (formId: number, filters?: SubmissionFilters) =>
    api.get<{ submissions: FormSubmission[]; total: number }>(
      `${BASE}/forms/${formId}/submissions${toQs({ ...filters })}`
    ),

  getSubmission: (id: number) =>
    api.get<FormSubmission>(`${BASE}/submissions/${id}`),

  updateSubmissionStatus: (id: number, status: string) =>
    api.put<{ success: boolean }>(`${BASE}/submissions/${id}/status`, { status }),

  triggerApproval: (id: number) =>
    api.post<{ success: boolean; approval_request_id?: number }>(
      `${BASE}/submissions/${id}/approve`
    ),

  submitInternal: (formId: number, answers: Record<string, unknown>, source = 'web_internal') =>
    api.post<{ success: boolean; submission_id: number }>(
      `${BASE}/forms/${formId}/submit`,
      { answers, source }
    ),

  // ---- Export ----

  getExportUrl: (formId: number) => `${BASE}/forms/${formId}/export`,

  // ---- Public (no auth) ----

  getPublicForm: (slug: string) =>
    api.get<PublicForm>(`/forms/public/${slug}`),

  submitPublicForm: (slug: string, data: {
    answers: Record<string, unknown>
    utm_data?: Record<string, string>
    respondent_name?: string
    respondent_email?: string
    respondent_phone?: string
  }) =>
    api.post<{
      success: boolean
      submission_id: number
      thank_you_message?: string
      redirect_url?: string
    }>(`/forms/public/${slug}/submit`, data),
}
