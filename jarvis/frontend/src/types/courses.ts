export interface CourseType {
  id: number
  code: string
  name: string
  description: string | null
  requires_certification: boolean
  default_validity_months: number | null
  is_active: boolean
}

export interface Course {
  id: number
  name: string
  course_type_id: number | null
  course_type_code: string | null
  course_type_name: string | null
  requires_certification: boolean
  default_validity_months: number | null
  company_id: number | null
  company_name: string | null
  supplier_id: number | null
  supplier_name: string | null
  trainer_name: string | null
  start_date: string
  end_date: string
  location: string | null
  description: string | null
  budget: number | null
  currency: string
  status: CourseStatus
  approval_request_id: number | null
  enrollment_count: number
  created_by: number | null
  created_by_name: string | null
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export type CourseStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'in_progress'
  | 'completed'
  | 'cancelled'

export interface Enrollment {
  id: number
  course_id: number
  employee_id: number
  employee_name: string
  company: string | null
  department: string | null
  brand: string | null
  enrollment_status: EnrollmentStatus
  enrolled_at: string
  completed_at: string | null
  notes: string | null
  // joined from course
  course_name?: string
  start_date?: string
  end_date?: string
  course_status?: string
  course_type_code?: string
  course_type_name?: string
}

export type EnrollmentStatus =
  | 'enrolled'
  | 'attended'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface Certification {
  id: number
  enrollment_id: number | null
  employee_id: number
  employee_name?: string
  course_type_id: number
  course_type_code: string
  course_type_name: string
  certificate_number: string | null
  issued_date: string
  expiry_date: string | null
  status: 'active' | 'expired' | 'revoked'
  days_until_expiry: number | null
  created_at: string
}
