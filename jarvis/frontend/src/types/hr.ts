export interface EventBonus {
  id: number
  user_id: number
  employee_name: string
  event_id: number
  event_name: string
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
  notify_on_allocation: boolean
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
