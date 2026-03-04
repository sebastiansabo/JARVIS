export interface UserDetail {
  id: number
  name: string
  email: string
  phone: string | null
  role_id: number
  role_name: string
  is_active: boolean
  company: string | null
  brand: string | null
  department: string | null
  subdepartment: string | null
  notify_on_allocation: boolean
  last_login: string | null
  created_at: string
  cnp: string | null
  birthdate: string | null
  position: string | null
  contract_work_date: string | null
}

export interface CreateUserInput {
  name: string
  email: string
  phone?: string
  password?: string
  role_id?: number
  is_active?: boolean
}

export interface UpdateUserInput {
  name?: string
  email?: string
  phone?: string
  role_id?: number
  is_active?: boolean
  notify_on_allocation?: boolean
  company?: string
  brand?: string
  department?: string
  subdepartment?: string
  cnp?: string
  birthdate?: string
  position?: string
  contract_work_date?: string
}

export interface AuditEvent {
  id: number
  event_type: string
  event_description: string
  user_id: number | null
  user_name: string | null
  user_email: string | null
  entity_type: string | null
  entity_id: number | null
  ip_address: string | null
  user_agent: string | null
  details: Record<string, unknown> | null
  created_at: string
}
