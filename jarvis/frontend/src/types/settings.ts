export interface ThemeColors {
  bgBody: string
  bgCard: string
  bgInput: string
  bgTableHeader: string
  bgTableHover: string
  accentPrimary: string
  accentSuccess: string
  accentWarning: string
  accentDanger: string
  textPrimary: string
  textSecondary: string
  borderColor: string
  navbarBg: string
}

export interface Theme {
  id: number
  theme_name: string
  settings: { dark: ThemeColors; light: ThemeColors }
  is_active: boolean
  created_at: string
  updated_at?: string
}

export interface MenuItem {
  id: number
  module_key: string
  name: string
  label?: string
  icon: string
  url: string
  sort_order: number
  status: string
  is_active?: boolean
  color: string | null
  description: string | null
  parent_id: number | null
  children?: MenuItem[]
  created_at?: string
  updated_at?: string
}

export interface VatRate {
  id: number
  name: string
  rate: number
  is_default: boolean
  is_active: boolean
}

export interface DropdownOption {
  id: number
  dropdown_type: string
  value: string
  label: string
  color: string | null
  opacity: number | null
  sort_order: number
  is_active: boolean
  notify_on_status: boolean
}

export interface NotificationSetting {
  id: number
  event_type: string
  enabled: boolean
  email_template: string | null
  recipients: string[]
}

export interface DefaultColumn {
  id: number
  page: string
  columns: string[]
  user_id: number | null
}
