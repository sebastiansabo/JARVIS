export interface InAppNotification {
  id: number
  type: 'info' | 'approval' | 'warning'
  title: string
  message?: string
  link?: string
  entity_type?: string
  entity_id?: number
  is_read: boolean
  created_at: string
}
