import {
  FileText, Users, ClipboardCheck, CreditCard,
  CalendarDays, Megaphone, Bell, Sparkles,
} from 'lucide-react'
import type { User } from '@/types'

export interface WidgetLayout {
  i: string
  x: number
  y: number
  w: number
  h: number
  minW?: number
  maxW?: number
  minH?: number
  maxH?: number
}

export interface WidgetDef {
  id: string
  name: string
  icon: typeof FileText
  permission?: keyof User
  defaultLayout: { w: number; h: number; minW?: number; minH?: number }
  defaultVisible: boolean
  statCards: { key: string; title: string; icon: typeof FileText }[]
}

export interface WidgetPref {
  id: string
  visible: boolean
  layout: WidgetLayout
}

export interface DashboardPreferences {
  version: number
  widgets: WidgetPref[]
}

export const WIDGET_CATALOG: WidgetDef[] = [
  {
    id: 'happy_marquee',
    name: 'Happy',
    icon: Sparkles,
    defaultLayout: { w: 6, h: 3, minW: 3, minH: 2 },
    defaultVisible: true,
    statCards: [],
  },
  {
    id: 'accounting_invoices',
    name: 'Recent Invoices',
    icon: FileText,
    permission: 'can_access_accounting',
    defaultLayout: { w: 6, h: 4, minW: 3, minH: 3 },
    defaultVisible: true,
    statCards: [
      { key: 'total_invoices', title: 'Total Invoices', icon: FileText },
    ],
  },
  {
    id: 'statements_summary',
    name: 'Bank Statements',
    icon: CreditCard,
    permission: 'can_access_statements',
    defaultLayout: { w: 2, h: 3, minW: 2, minH: 2 },
    defaultVisible: true,
    statCards: [{ key: 'pending_txns', title: 'Pending Txns', icon: CreditCard }],
  },
  {
    id: 'hr_summary',
    name: 'HR Overview',
    icon: CalendarDays,
    permission: 'can_access_hr',
    defaultLayout: { w: 2, h: 3, minW: 2, minH: 2 },
    defaultVisible: true,
    statCards: [{ key: 'hr_events', title: 'HR Events', icon: CalendarDays }],
  },
  {
    id: 'marketing_summary',
    name: 'Marketing',
    icon: Megaphone,
    defaultLayout: { w: 2, h: 3, minW: 2, minH: 2 },
    defaultVisible: true,
    statCards: [{ key: 'active_projects', title: 'Active Projects', icon: Megaphone }],
  },
  {
    id: 'approvals_queue',
    name: 'Pending Approvals',
    icon: ClipboardCheck,
    defaultLayout: { w: 6, h: 4, minW: 3, minH: 3 },
    defaultVisible: true,
    statCards: [{ key: 'pending_approvals', title: 'Pending Approvals', icon: ClipboardCheck }],
  },
  {
    id: 'online_users',
    name: 'Online Users',
    icon: Users,
    defaultLayout: { w: 2, h: 2, minW: 1, minH: 2 },
    defaultVisible: true,
    statCards: [{ key: 'online_users', title: 'Online Users', icon: Users }],
  },
  {
    id: 'notifications_recent',
    name: 'Notifications',
    icon: Bell,
    defaultLayout: { w: 2, h: 3, minW: 2, minH: 2 },
    defaultVisible: true,
    statCards: [],
  },
]
