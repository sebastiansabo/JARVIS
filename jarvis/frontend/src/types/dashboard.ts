export interface DashboardStats {
  total_invoices: number
  total_value_ron: number
  total_value_eur: number
  pending_invoices: number
  online_users: number
}

export interface RecentInvoice {
  id: number
  supplier: string
  invoice_number: string
  invoice_date: string
  invoice_value: number
  currency: string
  status: string
  payment_status: string
  created_at: string
  company?: string
  department?: string
}

export interface OnlineUsersResponse {
  count: number
  users: { id: number; name: string; last_seen: string }[]
}

export interface CompanySummary {
  company: string
  invoice_count: number
  total_value_ron: number
  total_value_eur: number
  avg_exchange_rate: number
}
