import {
  FileText, Users, ClipboardCheck, CreditCard, Receipt,
  CalendarDays, Megaphone, Bell,
} from 'lucide-react'
import type { User } from '@/types'

export interface WidgetDef {
  id: string
  name: string
  icon: typeof FileText
  permission?: keyof User       // boolean flag on User
  colSpan: 1 | 2
  defaultVisible: boolean
  /** Which stat cards this widget contributes to the top row */
  statCards: { key: string; title: string; icon: typeof FileText }[]
}

export interface WidgetPref {
  id: string
  visible: boolean
  order: number
}

export interface DashboardPreferences {
  version: number
  widgets: WidgetPref[]
}

export const WIDGET_CATALOG: WidgetDef[] = [
  {
    id: 'accounting_invoices',
    name: 'Recent Invoices',
    icon: FileText,
    permission: 'can_access_accounting',
    colSpan: 2,
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
    colSpan: 1,
    defaultVisible: true,
    statCards: [{ key: 'pending_txns', title: 'Pending Txns', icon: CreditCard }],
  },
  {
    id: 'efactura_status',
    name: 'e-Factura',
    icon: Receipt,
    permission: 'can_access_efactura',
    colSpan: 1,
    defaultVisible: true,
    statCards: [{ key: 'unallocated_efactura', title: 'Unallocated e-Factura', icon: Receipt }],
  },
  {
    id: 'hr_summary',
    name: 'HR Overview',
    icon: CalendarDays,
    permission: 'can_access_hr',
    colSpan: 1,
    defaultVisible: true,
    statCards: [{ key: 'hr_events', title: 'HR Events', icon: CalendarDays }],
  },
  {
    id: 'marketing_summary',
    name: 'Marketing',
    icon: Megaphone,
    colSpan: 1,
    defaultVisible: true,
    statCards: [{ key: 'active_projects', title: 'Active Projects', icon: Megaphone }],
  },
  {
    id: 'approvals_queue',
    name: 'Pending Approvals',
    icon: ClipboardCheck,
    colSpan: 2,
    defaultVisible: true,
    statCards: [{ key: 'pending_approvals', title: 'Pending Approvals', icon: ClipboardCheck }],
  },
  {
    id: 'online_users',
    name: 'Online Users',
    icon: Users,
    colSpan: 1,
    defaultVisible: true,
    statCards: [{ key: 'online_users', title: 'Online Users', icon: Users }],
  },
  {
    id: 'notifications_recent',
    name: 'Notifications',
    icon: Bell,
    colSpan: 1,
    defaultVisible: true,
    statCards: [],
  },
]
