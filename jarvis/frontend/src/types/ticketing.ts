export type TicketStatus = 'open' | 'in_progress' | 'resolved' | 'closed'
export type TicketPriority = 'low' | 'medium' | 'high' | 'critical'
export type TicketCategory = 'hardware' | 'software' | 'network' | 'access' | 'other'

export interface Ticket {
  id: number
  title: string
  description: string | null
  status: TicketStatus
  priority: TicketPriority
  category: TicketCategory
  created_by: number
  created_by_name: string
  assigned_to: number | null
  assigned_to_name: string | null
  comment_count: number
  created_at: string
  updated_at: string
  resolved_at: string | null
  closed_at: string | null
}

export interface TicketComment {
  id: number
  ticket_id: number
  user_id: number
  user_name: string
  content: string
  created_at: string
}

export interface TicketStats {
  success: boolean
  open: number
  in_progress: number
  resolved: number
  closed: number
  total: number
}

export interface ItStaffUser {
  id: number
  name: string
}
