import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { QueryError } from '@/components/QueryError'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { Skeleton } from '@/components/ui/skeleton'
import { ArrowRight, Clock, GripVertical, CreditCard, Receipt, CalendarDays, Megaphone, Bell, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { dashboardApi } from '@/api/dashboard'
import { approvalsApi } from '@/api/approvals'
import { statementsApi } from '@/api/statements'
import { efacturaApi } from '@/api/efactura'
import { hrApi } from '@/api/hr'
import { marketingApi } from '@/api/marketing'
import { notificationsApi } from '@/api/notifications'

// ── Shell ──

interface WidgetShellProps {
  title: string
  icon: React.ReactNode
  linkTo?: string
  linkLabel?: string
  children: React.ReactNode
  className?: string
}

export function WidgetShell({ title, icon, linkTo, linkLabel = 'View all', children, className }: WidgetShellProps) {
  return (
    <Card className={cn('h-full flex flex-col', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="widget-drag-handle flex flex-1 cursor-grab items-center gap-2">
            <GripVertical className="h-3.5 w-3.5 text-muted-foreground/50" />
            {icon}
            <CardTitle className="text-base">{title}</CardTitle>
          </div>
          {linkTo && (
            <Button variant="ghost" size="sm" asChild>
              <Link to={linkTo} className="text-xs">
                {linkLabel} <ArrowRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-auto">{children}</CardContent>
    </Card>
  )
}

// ── Accounting: Recent Invoices ──

export function AccountingInvoicesWidget({ enabled }: { enabled: boolean }) {
  const { data: invoices, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard', 'recentInvoices'],
    queryFn: () => dashboardApi.getRecentInvoices(5),
    staleTime: 60_000,
    enabled,
  })

  return (
    <WidgetShell title="Recent Invoices" icon={<span />} linkTo="/app/accounting">
      {isError ? (
        <QueryError message="Failed to load invoices" onRetry={() => refetch()} />
      ) : isLoading ? (
        <TableSkeleton rows={5} columns={5} />
      ) : invoices && invoices.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Supplier</TableHead>
              <TableHead>Invoice #</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Value</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {invoices.map((inv) => (
              <TableRow key={inv.id}>
                <TableCell className="font-medium">{inv.supplier}</TableCell>
                <TableCell className="text-muted-foreground">{inv.invoice_number}</TableCell>
                <TableCell className="text-muted-foreground">{inv.invoice_date}</TableCell>
                <TableCell className="text-right">
                  <CurrencyDisplay value={inv.invoice_value} currency={inv.currency} />
                </TableCell>
                <TableCell>
                  <StatusBadge status={inv.payment_status || inv.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <p className="py-8 text-center text-sm text-muted-foreground">No invoices yet.</p>
      )}
    </WidgetShell>
  )
}

// ── Statements Summary ──

export function StatementsSummaryWidget({ enabled }: { enabled: boolean }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard', 'statementsSummary'],
    queryFn: () => statementsApi.getSummary(),
    staleTime: 60_000,
    enabled,
  })
  const statItems = [
    { label: 'Pending', count: data?.by_status?.pending?.count ?? 0, total: data?.by_status?.pending?.total ?? 0, color: 'text-amber-600' },
    { label: 'Matched', count: data?.by_status?.resolved?.count ?? 0, total: data?.by_status?.resolved?.total ?? 0, color: 'text-green-600' },
    { label: 'Ignored', count: data?.by_status?.ignored?.count ?? 0, total: data?.by_status?.ignored?.total ?? 0, color: 'text-muted-foreground' },
  ]

  return (
    <WidgetShell title="Bank Statements" icon={<CreditCard className="h-4 w-4 text-muted-foreground" />} linkTo="/app/statements">
      {isError ? (
        <QueryError message="Failed to load" onRetry={() => refetch()} />
      ) : isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {statItems.map(s => (
            <div key={s.label} className="flex items-center justify-between rounded-lg border p-3">
              <div>
                <p className={cn('text-sm font-medium', s.color)}>{s.label}</p>
                <p className="text-xs text-muted-foreground">{s.count} transactions</p>
              </div>
              <p className="text-sm font-semibold">
                {Number(s.total).toLocaleString('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} RON
              </p>
            </div>
          ))}
        </div>
      )}
    </WidgetShell>
  )
}

// ── e-Factura Status ──

export function EFacturaWidget({ enabled }: { enabled: boolean }) {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', 'efacturaUnallocated'],
    queryFn: efacturaApi.getUnallocatedCount,
    staleTime: 60_000,
    enabled,
  })
  const count = data ?? 0

  return (
    <WidgetShell
      title="e-Factura"
      icon={<Receipt className="h-4 w-4 text-muted-foreground" />}
      linkTo="/app/efactura"
      className={count > 0 ? 'border-amber-300 dark:border-amber-700' : undefined}
    >
      {isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <div className="flex flex-col items-center py-4">
          <p className={cn('text-3xl font-bold', count > 0 ? 'text-amber-600' : 'text-green-600')}>{count}</p>
          <p className="text-sm text-muted-foreground mt-1">
            {count > 0 ? 'unallocated invoices to review' : 'All invoices allocated'}
          </p>
        </div>
      )}
    </WidgetShell>
  )
}

// ── HR Summary ──

export function HrSummaryWidget({ enabled }: { enabled: boolean }) {
  const year = new Date().getFullYear()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard', 'hrSummary', year],
    queryFn: () => hrApi.getSummary({ year }),
    staleTime: 60_000,
    enabled,
  })
  return (
    <WidgetShell title="HR Overview" icon={<CalendarDays className="h-4 w-4 text-muted-foreground" />} linkTo="/app/hr">
      {isError ? (
        <QueryError message="Failed to load" onRetry={() => refetch()} />
      ) : isLoading ? (
        <div className="grid grid-cols-2 gap-3">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-14 w-full" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Events', value: data?.total_events ?? 0 },
            { label: 'Employees', value: data?.total_employees ?? 0 },
            { label: 'Bonuses', value: data?.total_bonuses ?? 0 },
            { label: 'Total Amount', value: `${Number(data?.total_bonus_amount ?? 0).toLocaleString('ro-RO')} RON` },
          ].map(s => (
            <div key={s.label} className="rounded-lg border p-3 text-center">
              <p className="text-lg font-semibold">{s.value}</p>
              <p className="text-xs text-muted-foreground">{s.label}</p>
            </div>
          ))}
        </div>
      )}
    </WidgetShell>
  )
}

// ── Marketing Summary ──

export function MarketingSummaryWidget({ enabled }: { enabled: boolean }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard', 'mktSummary'],
    queryFn: () => marketingApi.getDashboardSummary(),
    staleTime: 60_000,
    enabled,
  })
  const s = data?.summary

  const utilPct = s?.total_budget ? Math.round(((s?.total_spent ?? 0) / s.total_budget) * 100) : 0

  return (
    <WidgetShell title="Marketing" icon={<Megaphone className="h-4 w-4 text-muted-foreground" />} linkTo="/app/marketing">
      {isError ? (
        <QueryError message="Failed to load" onRetry={() => refetch()} />
      ) : isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Active Projects</span>
            <span className="text-sm font-semibold">{s?.active_count ?? 0}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Budget</span>
            <span className="text-sm font-semibold">{Number(s?.total_budget ?? 0).toLocaleString('ro-RO')} RON</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Spent</span>
            <span className="text-sm font-semibold">{Number(s?.total_spent ?? 0).toLocaleString('ro-RO')} RON</span>
          </div>
          <div>
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>Utilization</span>
              <span>{utilPct}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  utilPct > 90 ? 'bg-red-500' : utilPct > 70 ? 'bg-amber-500' : 'bg-blue-500',
                )}
                style={{ width: `${Math.min(utilPct, 100)}%` }}
              />
            </div>
          </div>
          {(s?.kpi_alerts ?? 0) > 0 && (
            <div className="flex items-center gap-2 text-sm text-amber-600">
              <AlertTriangle className="h-4 w-4" />
              {s!.kpi_alerts} KPI alert{s!.kpi_alerts > 1 ? 's' : ''}
            </div>
          )}
        </div>
      )}
    </WidgetShell>
  )
}

// ── Approvals Queue ──

export function ApprovalsQueueWidget({ enabled }: { enabled: boolean }) {
  const { data } = useQuery({
    queryKey: ['dashboard', 'approvalQueue'],
    queryFn: () => approvalsApi.getMyQueue(),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled,
  })
  const items = data?.queue ?? []

  return (
    <WidgetShell
      title="Pending Approvals"
      icon={<span />}
      linkTo="/app/approvals"
      className={items.length > 0 ? 'border-amber-300 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-950/20' : undefined}
    >
      {items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">No pending approvals</p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 5).map((item) => {
            const ctx = item.context_snapshot as Record<string, unknown> | null
            const title = (ctx?.name as string) || (ctx?.supplier as string) || item.title || `${item.entity_type} #${item.entity_id}`
            const link = item.entity_type === 'mkt_project'
              ? `/app/marketing/projects/${item.entity_id}`
              : item.entity_type === 'invoice'
                ? '/app/accounting'
                : '/app/approvals'
            const hrs = Math.round(item.waiting_hours ?? 0)
            return (
              <Link key={item.id} to={link} className="flex items-center justify-between rounded-lg border bg-background p-3 hover:bg-muted/50 transition-colors">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{title}</p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="capitalize">{(item.entity_type ?? '').replace('_', ' ')}</span>
                    <span>&middot;</span>
                    <span>by {item.requested_by?.name ?? 'Unknown'}</span>
                    {(item.priority === 'high' || item.priority === 'urgent') && (
                      <Badge variant="destructive" className="text-[10px] h-4 px-1">{item.priority}</Badge>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground ml-3">
                  <Clock className="h-3 w-3" />
                  {hrs < 24 ? `${hrs}h` : `${Math.round(hrs / 24)}d`}
                </div>
              </Link>
            )
          })}
          {items.length > 5 && (
            <p className="text-xs text-center text-muted-foreground pt-1">+{items.length - 5} more items</p>
          )}
        </div>
      )}
    </WidgetShell>
  )
}

// ── Online Users ──

export function OnlineUsersWidget({ enabled }: { enabled: boolean }) {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', 'onlineUsers'],
    queryFn: dashboardApi.getOnlineUsers,
    staleTime: 30_000,
    refetchInterval: 30_000,
    enabled,
  })

  return (
    <WidgetShell title="Online Users" icon={<span />}>
      {isLoading ? (
        <Skeleton className="h-12 w-full" />
      ) : (
        <div className="flex flex-col items-center py-2">
          <p className="text-3xl font-bold">{data?.count ?? 0}</p>
          {data?.users && data.users.length > 0 && (
            <p className="text-xs text-muted-foreground mt-1 text-center">
              {data.users.map(u => u.name).join(', ')}
            </p>
          )}
        </div>
      )}
    </WidgetShell>
  )
}

// ── Notifications ──

export function NotificationsWidget({ enabled }: { enabled: boolean }) {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', 'recentNotifications'],
    queryFn: () => notificationsApi.getNotifications({ limit: 5, unread_only: true }),
    staleTime: 30_000,
    refetchInterval: 60_000,
    enabled,
  })
  const items = data?.notifications ?? []

  function timeAgo(d: string) {
    const ms = Date.now() - new Date(d).getTime()
    const mins = Math.floor(ms / 60000)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return `${Math.floor(hrs / 24)}d ago`
  }

  return (
    <WidgetShell title="Notifications" icon={<Bell className="h-4 w-4 text-muted-foreground" />}>
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">All caught up</p>
      ) : (
        <div className="space-y-2">
          {items.map(n => (
            <div key={n.id} className="flex items-start gap-2 rounded-lg border p-2.5">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{n.title}</p>
                {n.message && <p className="text-xs text-muted-foreground truncate">{n.message}</p>}
              </div>
              <span className="text-[10px] text-muted-foreground whitespace-nowrap mt-0.5">{timeAgo(n.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </WidgetShell>
  )
}
