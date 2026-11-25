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

// ---- Per-user notification preferences (4-channel) ----

export type NotificationChannel = 'in_app' | 'push' | 'email' | 'sms'

export type ChannelFlags = Record<NotificationChannel, boolean>

export interface NotificationCategory {
  slug: string
  name: string
  mandatory: boolean
}

export interface NotificationPreferencesView {
  categories: NotificationCategory[]
  preferences: Record<string, ChannelFlags>
  mandatory: string[]
  channels: NotificationChannel[]
  has_phone: boolean
}

export interface UpdatePreferenceBody {
  category_slug: string
  in_app_enabled: boolean
  push_enabled: boolean
  email_enabled: boolean
  sms_enabled: boolean
}
