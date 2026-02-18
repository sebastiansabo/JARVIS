import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Calculator, Users, Bot, Settings, FileText, ArrowRight, ClipboardCheck, Clock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatCard } from '@/components/shared/StatCard'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { useAuth } from '@/hooks/useAuth'
import { dashboardApi } from '@/api/dashboard'
import { approvalsApi } from '@/api/approvals'

export default function Dashboard() {
  const { user } = useAuth()

  const canAccounting = !!user?.can_access_accounting

  const { data: invoices, isLoading: invoicesLoading } = useQuery({
    queryKey: ['dashboard', 'recentInvoices'],
    queryFn: () => dashboardApi.getRecentInvoices(10),
    staleTime: 60_000,
    enabled: canAccounting,
  })

  const { data: onlineUsers, isLoading: onlineLoading } = useQuery({
    queryKey: ['dashboard', 'onlineUsers'],
    queryFn: dashboardApi.getOnlineUsers,
    staleTime: 30_000,
    refetchInterval: 30_000,
  })

  const { data: companySummary, isLoading: summaryLoading } = useQuery({
    queryKey: ['dashboard', 'companySummary'],
    queryFn: dashboardApi.getCompanySummary,
    staleTime: 60_000,
    enabled: canAccounting,
  })

  const { data: approvalQueue } = useQuery({
    queryKey: ['dashboard', 'approvalQueue'],
    queryFn: () => approvalsApi.getMyQueue(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const pendingApprovals = approvalQueue?.queue ?? []

  const totalInvoices = companySummary?.reduce((sum, c) => sum + Number(c.invoice_count), 0) ?? 0
  const totalValue = companySummary?.reduce((sum, c) => sum + Number(c.total_value_ron ?? 0), 0) ?? 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">Welcome, {user?.name}.</p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link to="/app/ai-agent">
            <Bot className="mr-1.5 h-4 w-4" />
            New Chat
          </Link>
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {canAccounting && (
          <>
            <StatCard
              title="Total Invoices"
              value={totalInvoices.toLocaleString('ro-RO')}
              icon={<FileText className="h-4 w-4" />}
              isLoading={summaryLoading}
            />
            <StatCard
              title="Total Value"
              value={new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(totalValue) + ' RON'}
              icon={<Calculator className="h-4 w-4" />}
              isLoading={summaryLoading}
            />
          </>
        )}
        <StatCard
          title="Online Users"
          value={onlineUsers?.count ?? 0}
          icon={<Users className="h-4 w-4" />}
          description={onlineUsers?.users.map((u) => u.name).join(', ')}
          isLoading={onlineLoading}
        />
        {canAccounting && (
          <StatCard
            title="Companies"
            value={companySummary?.length ?? 0}
            icon={<Settings className="h-4 w-4" />}
            isLoading={summaryLoading}
          />
        )}
        <StatCard
          title="Pending Approvals"
          value={pendingApprovals.length}
          icon={<ClipboardCheck className="h-4 w-4" />}
          description={pendingApprovals.length > 0 ? 'Awaiting your decision' : undefined}
        />
      </div>

      {/* Pending Approvals */}
      {pendingApprovals.length > 0 && (
        <Card className="border-amber-300 dark:border-amber-700 bg-amber-50/50 dark:bg-amber-950/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ClipboardCheck className="h-4 w-4 text-amber-600" />
                <CardTitle className="text-base">Pending Approvals</CardTitle>
                <Badge variant="secondary" className="bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                  {pendingApprovals.length}
                </Badge>
              </div>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/app/approvals" className="text-xs">
                  View all <ArrowRight className="ml-1 h-3 w-3" />
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {pendingApprovals.slice(0, 5).map((item) => {
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
                        {item.priority === 'high' || item.priority === 'urgent' ? (
                          <Badge variant="destructive" className="text-[10px] h-4 px-1">{item.priority}</Badge>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground ml-3">
                      <Clock className="h-3 w-3" />
                      {hrs < 24 ? `${hrs}h` : `${Math.round(hrs / 24)}d`}
                    </div>
                  </Link>
                )
              })}
              {pendingApprovals.length > 5 && (
                <p className="text-xs text-center text-muted-foreground pt-1">
                  +{pendingApprovals.length - 5} more items
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent Invoices + Company Summary — only for users with accounting access */}
      {canAccounting && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Recent Invoices Table */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Recent Invoices</CardTitle>
                <Button variant="ghost" size="sm" asChild>
                  <Link to="/app/accounting" className="text-xs">
                    View all <ArrowRight className="ml-1 h-3 w-3" />
                  </Link>
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {invoicesLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="h-10 animate-pulse rounded bg-muted" />
                  ))}
                </div>
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
            </CardContent>
          </Card>

          {/* Company Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">By Company</CardTitle>
            </CardHeader>
            <CardContent>
              {summaryLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="h-12 animate-pulse rounded bg-muted" />
                  ))}
                </div>
              ) : companySummary && companySummary.length > 0 ? (
                <div className="space-y-3">
                  {companySummary.map((cs) => (
                    <div key={cs.company} className="flex items-center justify-between rounded-lg border p-3">
                      <div>
                        <p className="text-sm font-medium">{cs.company}</p>
                        <p className="text-xs text-muted-foreground">{cs.invoice_count} invoices</p>
                      </div>
                      <CurrencyDisplay
                        value={cs.total_value_ron ?? 0}
                        currency="RON"
                        className="text-sm"
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="py-8 text-center text-sm text-muted-foreground">No data.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
