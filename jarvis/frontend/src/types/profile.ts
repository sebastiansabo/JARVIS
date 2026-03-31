export interface ProfileUser {
  id: number
  name: string
  email: string
  phone: string | null
  role: string | null
  company: string | null
  brand: string | null
  department: string | null
  subdepartment: string | null
  cnp: string | null
  birthdate: string | null
  position: string | null
  contract_work_date: string | null
}

export interface ProfileSummary {
  user: ProfileUser
  is_org_responsable: boolean
  invoices: {
    total: number
    total_value: number
    by_status: Record<string, number>
  }
  hr_events: {
    total_bonuses: number
    total_amount: number
    events_count: number
  }
  notifications: {
    total: number
    sent: number
    failed: number
  }
  activity: {
    total_events: number
  }
}

export interface ProfileInvoice {
  id: number
  invoice_number: string
  invoice_date: string
  invoice_value: number
  currency: string
  supplier: string
  status: string
  payment_status: string
  company: string
  brand: string | null
  department: string | null
  subdepartment: string | null
  allocation_percent: number
  allocation_value: number
  drive_link: string | null
  comment: string | null
  created_at: string
  updated_at: string | null
}

export interface ProfileActivity {
  id: number
  event_type: string
  details: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
}

export interface ProfileBonus {
  id: number
  year: number
  month: number
  bonus_days: number | null
  hours_free: number | null
  bonus_net: number | null
  details: string | null
  allocation_month: number | null
  participation_start: string | null
  participation_end: string | null
  event_name: string
  start_date: string | null
  end_date: string | null
  company: string | null
  brand: string | null
  created_at: string
  updated_at: string | null
}

export interface ProfilePontajeEmployee {
  biostar_user_id: string
  name: string
  lunch_break_minutes: number
  working_hours: number
  schedule_start: string | null
  schedule_end: string | null
  user_group_name: string | null
}

export interface ProfilePontajeResponse {
  success: boolean
  mapped: boolean
  employee: ProfilePontajeEmployee | null
  history: import('@/types/biostar').BioStarDayHistory[]
  today_punches: import('@/types/biostar').BioStarPunchLog[]
}

export interface OrgTreeNode {
  id: number | string
  name: string
  level: number
  parent_id: number | null
  company_id: number
}

export interface OrgTree {
  companies: OrgTreeNode[]
  nodes: OrgTreeNode[]
}

export interface ProfileTeamPontajeResponse {
  success: boolean
  is_manager: boolean
  mode: 'daily' | 'range'
  summary: import('@/types/biostar').BioStarDailySummary[] | import('@/types/biostar').BioStarRangeSummary[]
  tree?: OrgTree
  date?: string
  start?: string
  end?: string
}
