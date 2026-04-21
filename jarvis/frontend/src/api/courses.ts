import { api } from './client'
import type {
  Course, CourseType, Enrollment, Certification,
  EnrollmentCost, CostSummary, CompanyCostSummary, DepartmentCostSummary,
  MonthlyCost, CourseDashboardStats, CourseActivity,
} from '@/types/courses'

const BASE = '/hr/courses/api'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') sp.set(k, String(v))
  })
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const coursesApi = {
  // Courses
  getCourses: (params?: {
    company_id?: number
    course_type_id?: number
    status?: string
    search?: string
    year?: number
    month?: number
    include_deleted?: boolean
    limit?: number
    offset?: number
  }) => api.get<{ courses: Course[]; total: number }>(`${BASE}/courses${qs(params ?? {})}`),

  getCourse: (id: number) => api.get<Course>(`${BASE}/courses/${id}`),

  createCourse: (data: Partial<Course>) =>
    api.post<{ success: boolean; id: number }>(`${BASE}/courses`, data),

  updateCourse: (id: number, data: Partial<Course>) =>
    api.put<{ success: boolean }>(`${BASE}/courses/${id}`, data),

  deleteCourse: (id: number) =>
    api.delete<{ success: boolean }>(`${BASE}/courses/${id}`),

  restoreCourse: (id: number) =>
    api.post<{ success: boolean }>(`${BASE}/courses/${id}/restore`),

  bulkDeleteCourses: (ids: number[]) =>
    api.post<{ success: boolean; deleted: number }>(`${BASE}/courses/bulk-delete`, { ids }),

  bulkRestoreCourses: (ids: number[]) =>
    api.post<{ success: boolean; restored: number }>(`${BASE}/courses/bulk-restore`, { ids }),

  submitApproval: (id: number) =>
    api.post<{ success: boolean; status: string }>(`${BASE}/courses/${id}/submit-approval`),

  getAvailableYears: () =>
    api.get<number[]>(`${BASE}/courses/years`),

  // Course Types
  getCourseTypes: (activeOnly = true) =>
    api.get<CourseType[]>(`${BASE}/course-types${qs({ active_only: activeOnly })}`),

  // Enrollments
  getEnrollments: (courseId: number) =>
    api.get<Enrollment[]>(`${BASE}/courses/${courseId}/enrollments`),

  addEnrollments: (courseId: number, employeeIds: number[]) =>
    api.post<{ success: boolean; enrolled: number }>(
      `${BASE}/courses/${courseId}/enrollments`,
      { employee_ids: employeeIds },
    ),

  updateEnrollment: (courseId: number, enrollmentId: number, data: { enrollment_status: string }) =>
    api.put<{ success: boolean }>(
      `${BASE}/courses/${courseId}/enrollments/${enrollmentId}`,
      data,
    ),

  completeEnrollment: (courseId: number, enrollmentId: number) =>
    api.post<{ success: boolean; certification_id: number | null }>(
      `${BASE}/courses/${courseId}/enrollments/${enrollmentId}/complete`,
    ),

  deleteEnrollment: (courseId: number, enrollmentId: number) =>
    api.delete<{ success: boolean }>(
      `${BASE}/courses/${courseId}/enrollments/${enrollmentId}`,
    ),

  // Enrollment Costs
  getEnrollmentCosts: (courseId: number) =>
    api.get<{ costs: EnrollmentCost[]; summary: CostSummary }>(
      `${BASE}/courses/${courseId}/enrollment-costs`,
    ),

  upsertEnrollmentCost: (courseId: number, enrollmentId: number, data: {
    training_fee?: number
    per_diem?: number
    accommodation?: number
    transport?: number
    taxi?: number
    currency?: string
    notes?: string
  }) =>
    api.put<{ success: boolean; id: number }>(
      `${BASE}/courses/${courseId}/enrollments/${enrollmentId}/costs`,
      data,
    ),

  updateEnrollmentFields: (courseId: number, enrollmentId: number, data: {
    order_number?: string
    travel_order?: string
    additional_act?: string
    department?: string
    travel_mode?: string
    notes?: string
  }) =>
    api.put<{ success: boolean }>(
      `${BASE}/courses/${courseId}/enrollments/${enrollmentId}/fields`,
      data,
    ),

  // Dashboard & Cost Summary
  getDashboardStats: (params?: { year?: number; company_id?: number }) =>
    api.get<CourseDashboardStats>(`${BASE}/courses/dashboard${qs(params ?? {})}`),

  getCostSummary: (params?: { year?: number; month?: number; company_id?: number }) =>
    api.get<(CompanyCostSummary | DepartmentCostSummary)[]>(
      `${BASE}/courses/cost-summary${qs(params ?? {})}`,
    ),

  getCostByMonth: (params?: { year?: number; company_id?: number }) =>
    api.get<MonthlyCost[]>(`${BASE}/courses/cost-by-month${qs(params ?? {})}`),

  // Activity
  getCourseActivity: (courseId: number, limit = 50) =>
    api.get<CourseActivity[]>(`${BASE}/courses/${courseId}/activity${qs({ limit })}`),

  // Certifications
  getCertifications: (params?: { employee_id?: number; days_ahead?: number }) =>
    api.get<Certification[]>(`${BASE}/certifications${qs(params ?? {})}`),

  getExpiringCertifications: (days = 30) =>
    api.get<Certification[]>(`${BASE}/certifications/expiring${qs({ days })}`),

  // Invoices
  getCourseInvoices: (courseId: number) =>
    api.get<Array<{
      id: number
      invoice_number: string
      invoice_date: string
      invoice_value: number
      currency: string
      supplier: string
      status: string
    }>>(`${BASE}/courses/${courseId}/invoices`),

  linkInvoice: (courseId: number, invoiceId: number) =>
    api.post<{ success: boolean }>(`${BASE}/courses/${courseId}/invoices`, {
      invoice_id: invoiceId,
    }),

  unlinkInvoice: (courseId: number, invoiceId: number) =>
    api.delete<{ success: boolean }>(
      `${BASE}/courses/${courseId}/invoices/${invoiceId}`,
    ),

  // Profile
  getMyCourses: () =>
    api.get<{ enrollments: Enrollment[]; certifications: Certification[] }>(
      '/profile/api/courses',
    ),
}
