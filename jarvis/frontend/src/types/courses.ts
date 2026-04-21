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
  course_code: string | null
  duration_hours: number | null
  travel_mode: string | null
  status: CourseStatus | null
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
  // Admin fields (from Excel)
  order_number: string | null
  travel_order: string | null
  additional_act: string | null
  travel_mode: string | null
  // Inline cost data (joined from enrollment_costs)
  training_fee: number | null
  per_diem: number | null
  accommodation: number | null
  transport: number | null
  taxi: number | null
  total_cost: number | null
  cost_currency: string | null
  cost_notes: string | null
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

export interface EnrollmentCost {
  id: number
  enrollment_id: number
  employee_id: number
  employee_name: string
  employee_company: string | null
  user_department: string | null
  enrollment_department: string | null
  enrollment_status: EnrollmentStatus
  enrollment_travel_mode: string | null
  order_number: string | null
  travel_order: string | null
  additional_act: string | null
  training_fee: number
  per_diem: number
  accommodation: number
  transport: number
  taxi: number
  total_cost: number
  currency: string
  notes: string | null
}

export interface CostSummary {
  total_training_fee: number
  total_per_diem: number
  total_accommodation: number
  total_transport: number
  total_taxi: number
  total_cost: number
  enrollment_count: number
}

export interface CompanyCostSummary {
  company_id: number
  company_name: string
  training_fee: number
  per_diem: number
  accommodation: number
  transport: number
  taxi: number
  total_cost: number
  course_count: number
  participant_count: number
  total_days: number
}

export interface DepartmentCostSummary {
  department: string
  training_fee: number
  per_diem: number
  accommodation: number
  transport: number
  taxi: number
  total_cost: number
  course_count: number
  participant_count: number
}

export interface MonthlyCost {
  month: number
  training_fee: number
  per_diem: number
  accommodation: number
  transport: number
  taxi: number
  total_cost: number
  course_count: number
}

export interface CourseDashboardStats {
  total_courses: number
  total_participants: number
  total_cost: number
  total_days: number
  by_status: Array<{ status: CourseStatus; count: number }>
}

export interface CourseActivity {
  id: number
  course_id: number
  action: string
  actor_id: number | null
  actor_name: string | null
  actor_display_name: string | null
  details: Record<string, unknown>
  created_at: string
}
