import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bot, FileText, Calculator, CreditCard, Receipt, CalendarDays, Megaphone, ClipboardCheck, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { StatCard } from '@/components/shared/StatCard'
import { useAuth } from '@/hooks/useAuth'
import { dashboardApi } from '@/api/dashboard'
import { approvalsApi } from '@/api/approvals'
import { statementsApi } from '@/api/statements'
import { efacturaApi } from '@/api/efactura'
import { hrApi } from '@/api/hr'
import { marketingApi } from '@/api/marketing'
import { useDashboardPrefs } from './useDashboardPrefs'
import { CustomizeSheet } from './CustomizeSheet'
import {
  AccountingInvoicesWidget,
  AccountingCompaniesWidget,
  StatementsSummaryWidget,
  EFacturaWidget,
  HrSummaryWidget,
  MarketingSummaryWidget,
  ApprovalsQueueWidget,
  OnlineUsersWidget,
  NotificationsWidget,
} from './widgets'

const WIDGET_COMPONENTS: Record<string, React.ComponentType<{ enabled: boolean }>> = {
  accounting_invoices: AccountingInvoicesWidget,
  accounting_companies: AccountingCompaniesWidget,
  statements_summary: StatementsSummaryWidget,
  efactura_status: EFacturaWidget,
  hr_summary: HrSummaryWidget,
  marketing_summary: MarketingSummaryWidget,
  approvals_queue: ApprovalsQueueWidget,
  online_users: OnlineUsersWidget,
  notifications_recent: NotificationsWidget,
}

export default function Dashboard() {
  const { user } = useAuth()
  const { permittedWidgets, visibleWidgets, toggleWidget, moveWidget, resetDefaults, isVisible } = useDashboardPrefs(user)

  const canAccounting = !!user?.can_access_accounting
  const canStatements = !!user?.can_access_statements
  const canEfactura = !!user?.can_access_efactura
  const canHr = !!user?.can_access_hr

  // ── Stat card data queries (only fire when relevant widget is visible) ──

  const { data: companySummary, isLoading: summaryLoading } = useQuery({
    queryKey: ['dashboard', 'companySummary'],
    queryFn: dashboardApi.getCompanySummary,
    staleTime: 60_000,
    enabled: canAccounting && (isVisible('accounting_invoices') || isVisible('accounting_companies')),
  })

  const { data: onlineUsers, isLoading: onlineLoading } = useQuery({
    queryKey: ['dashboard', 'onlineUsers'],
    queryFn: dashboardApi.getOnlineUsers,
    staleTime: 30_000,
    refetchInterval: 30_000,
    enabled: isVisible('online_users'),
  })

  const { data: approvalQueue } = useQuery({
    queryKey: ['dashboard', 'approvalQueue'],
    queryFn: () => approvalsApi.getMyQueue(),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled: isVisible('approvals_queue'),
  })

  const { data: stmtData, isLoading: stmtLoading } = useQuery({
    queryKey: ['dashboard', 'statementsSummary'],
    queryFn: () => statementsApi.getSummary(),
    staleTime: 60_000,
    enabled: canStatements && isVisible('statements_summary'),
  })

  const { data: efacturaData, isLoading: efacturaLoading } = useQuery({
    queryKey: ['dashboard', 'efacturaUnallocated'],
    queryFn: efacturaApi.getUnallocatedCount,
    staleTime: 60_000,
    enabled: canEfactura && isVisible('efactura_status'),
  })

  const { data: hrData, isLoading: hrLoading } = useQuery({
    queryKey: ['dashboard', 'hrSummary', new Date().getFullYear()],
    queryFn: () => hrApi.getSummary({ year: new Date().getFullYear() }),
    staleTime: 60_000,
    enabled: canHr && isVisible('hr_summary'),
  })

  const { data: mktData, isLoading: mktLoading } = useQuery({
    queryKey: ['dashboard', 'mktSummary'],
    queryFn: () => marketingApi.getDashboardSummary(),
    staleTime: 60_000,
    enabled: isVisible('marketing_summary'),
  })

  // Computed stats
  const totalInvoices = companySummary?.reduce((s, c) => s + Number(c.invoice_count), 0) ?? 0
  const totalValue = companySummary?.reduce((s, c) => s + Number(c.total_value_ron ?? 0), 0) ?? 0
  const pendingApprovals = approvalQueue?.queue?.length ?? 0
  const pendingTxns = stmtData?.by_status?.pending?.count ?? 0
  const unallocatedEf = efacturaData ?? 0
  const hrEvents = hrData?.total_events ?? 0
  const activeProjects = mktData?.summary?.active_count ?? 0

  // Build stat cards based on visible widgets
  const statCards: { key: string; title: string; value: string | number; icon: React.ReactNode; isLoading: boolean; description?: string }[] = []

  if (isVisible('accounting_invoices') && canAccounting) {
    statCards.push({
      key: 'total_invoices', title: 'Total Invoices',
      value: totalInvoices.toLocaleString('ro-RO'),
      icon: <FileText className="h-4 w-4" />, isLoading: summaryLoading,
    })
    statCards.push({
      key: 'total_value', title: 'Total Value',
      value: new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(totalValue) + ' RON',
      icon: <Calculator className="h-4 w-4" />, isLoading: summaryLoading,
    })
  }
  if (isVisible('statements_summary') && canStatements) {
    statCards.push({
      key: 'pending_txns', title: 'Pending Txns',
      value: pendingTxns,
      icon: <CreditCard className="h-4 w-4" />, isLoading: stmtLoading,
    })
  }
  if (isVisible('efactura_status') && canEfactura) {
    statCards.push({
      key: 'unallocated_ef', title: 'Unallocated e-Factura',
      value: unallocatedEf,
      icon: <Receipt className="h-4 w-4" />, isLoading: efacturaLoading,
    })
  }
  if (isVisible('hr_summary') && canHr) {
    statCards.push({
      key: 'hr_events', title: 'HR Events',
      value: hrEvents,
      icon: <CalendarDays className="h-4 w-4" />, isLoading: hrLoading,
      description: `${new Date().getFullYear()}`,
    })
  }
  if (isVisible('marketing_summary')) {
    statCards.push({
      key: 'active_projects', title: 'Active Projects',
      value: activeProjects,
      icon: <Megaphone className="h-4 w-4" />, isLoading: mktLoading,
    })
  }
  if (isVisible('approvals_queue')) {
    statCards.push({
      key: 'pending_approvals', title: 'Pending Approvals',
      value: pendingApprovals,
      icon: <ClipboardCheck className="h-4 w-4" />,
      isLoading: false,
      description: pendingApprovals > 0 ? 'Awaiting your decision' : undefined,
    })
  }
  if (isVisible('online_users')) {
    statCards.push({
      key: 'online_users', title: 'Online Users',
      value: onlineUsers?.count ?? 0,
      icon: <Users className="h-4 w-4" />, isLoading: onlineLoading,
      description: onlineUsers?.users.map(u => u.name).join(', '),
    })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">Welcome, {user?.name}.</p>
        </div>
        <div className="flex items-center gap-2">
          <CustomizeSheet
            permittedWidgets={permittedWidgets}
            toggleWidget={toggleWidget}
            moveWidget={moveWidget}
            resetDefaults={resetDefaults}
          />
          <Button variant="outline" size="sm" asChild>
            <Link to="/app/ai-agent">
              <Bot className="mr-1.5 h-4 w-4" />
              New Chat
            </Link>
          </Button>
        </div>
      </div>

      {/* Stat Cards */}
      {statCards.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {statCards.map(sc => (
            <StatCard
              key={sc.key}
              title={sc.title}
              value={sc.value}
              icon={sc.icon}
              isLoading={sc.isLoading}
              description={sc.description}
            />
          ))}
        </div>
      )}

      {/* Widget Grid */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {visibleWidgets.map(wp => {
          const Component = WIDGET_COMPONENTS[wp.id]
          if (!Component) return null
          return <Component key={wp.id} enabled />
        })}
      </div>
    </div>
  )
}
