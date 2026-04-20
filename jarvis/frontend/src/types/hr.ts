export interface EventBonus {
  id: number
  user_id: number
  employee_name: string
  event_id: number
  event_name: string
  event_start: string | null
  event_end: string | null
  year: number
  month: number
  participation_start: string | null
  participation_end: string | null
  bonus_days: number | null
  hours_free: number | null
  bonus_net: number | null
  details: string | null
  allocation_month: number | null
  company: string | null
  brand: string | null
  department: string | null
  created_at: string
}

export interface HrEvent {
  id: number
  name: string
  start_date: string
  end_date: string
  company: string | null
  brand: string | null
  description: string | null
  created_by: number | null
  created_by_name: string | null
  created_at: string
}

export type ContractStatus = 'active' | 'suspended' | 'closed'

export interface HrEmployee {
  id: number
  name: string
  email: string | null
  phone: string | null
  departments: string | null
  subdepartment: string | null
  company: string | null
  brand: string | null
  is_active: boolean
  contract_status: ContractStatus
  notify_on_allocation: boolean
  notify_missing_punch: boolean | null
}

export interface EmployeeWorkStats {
  total_hours: number
  avg_daily_hours: number
  variance_minutes: number
  productivity_score: number
  days_present: number
  single_punch_days: number
  working_days: number
  expected_hours: number
  hours_per_day: number
  lunch_break_minutes: number
  schedule_start: string | null
  schedule_end: string | null
  effective_days: number
  leave_days: number
  leave_hours: number
  leave_types: string
  permit_count: number
  permit_hours: number
  avg_check_in: string | null
  avg_check_out: string | null
  schedule_companies: Array<{
    company: string; norma: number; start: string; end: string; lunch: number
    co_total?: number | null; co_carry_over?: number | null
    co_used_ytd?: number | null; co_remaining?: number | null
    leave_days?: number; leave_types?: string
  }>
  co_total?: number | null
  co_carry_over?: number | null
  co_used_ytd?: number | null
  co_balance?: number | null
  co_year?: number | null
}

export interface CoBalanceImportRun {
  run_id: string
  year: number
  source_file: string | null
  status: 'running' | 'completed' | 'failed'
  rows_total: number
  rows_matched: number
  rows_unmatched: number
  companies: string | null
  error_message: string | null
  started_at: string
  finished_at: string | null
}

export interface CoBalanceUnmatchedRow {
  id: number
  year: number
  company_name: string
  cnp: string | null
  nume: string | null
  prenume: string | null
  nr_contract: string | null
  data_incepere_contract: string | null
  departament: string | null
  total_available: number
}

export interface BonusType {
  id: number
  name: string
  amount: number
  days_per_amount: number | null
  description: string | null
  is_active: boolean
  restricted_to_user_id: number | null
  restricted_to_user_name: string | null
}

export interface HrSettings {
  hr_bonus_lock_day: number
  hr_bonus_max_hours_per_day: number
}

export interface HrPermissions {
  permissions: Record<string, { allowed: boolean; scope: string }>
  user_context: {
    user_id: number
    company: string | null
    department: string | null
    is_hr_manager: boolean
    can_access_hr: boolean
  }
}

export interface HrSummary {
  total_employees: number
  total_events: number
  total_bonuses: number
  total_bonus_amount: number | null
  total_hours: number | null
  total_days: number | null
}

export interface LockStatus {
  locked: boolean
  deadline: string
  deadline_display: string
  days_remaining: number
  message: string
  can_override: boolean
}

export interface BonusSummaryByMonth {
  month: number
  count: number
  total: number | null
}

export interface BonusSummaryByEmployee {
  id: number
  name: string
  department: string | null
  company: string | null
  brand: string | null
  bonus_count: number
  total_days: number
  total_hours: number
  total_bonus: number
}

export interface BonusSummaryByEvent {
  id: number
  name: string
  start_date: string
  end_date: string
  company: string | null
  brand: string | null
  year: number
  month: number
  bonus_count: number
  employee_count: number
  total_days: number
  total_hours: number
  total_bonus: number
}

export interface StructureCompany {
  id: number
  company: string
  vat: string | null
  created_at: string
  brands: string
  brands_list: { brand: string }[]
  parent_company_id: number | null
  display_order: number
}

export interface CompanyBrand {
  id: number
  company_id: number
  company: string
  brand: string
  is_active: boolean
  created_at: string
}

export interface DepartmentStructure {
  id: number
  company: string
  brand: string
  department: string
  subdepartment: string
  manager: string
  company_id: number
  manager_ids: string | null
  cc_email: string | null
}

export interface MasterItem {
  id: number
  name: string
  is_active: boolean
}

export interface OrganigramData {
  employees: HrEmployee[]
  structures: DepartmentStructure[]
  companies: StructureCompany[]
  current_user_id: number
  is_manager: boolean
}
