import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Calculator, Users, Bot, Settings, Plus, FileText, ArrowRight } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatCard } from '@/components/shared/StatCard'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { useAuth } from '@/hooks/useAuth'
import { dashboardApi } from '@/api/dashboard'

const apps = [
  {
    path: '/app/ai-agent',
    label: 'AI Agent',
    description: 'Ask questions about your data',
    icon: Bot,
  },
  {
    path: '/app/accounting',
    label: 'Accounting',
    description: 'Invoices, statements, e-Factura',
    icon: Calculator,
    permission: 'can_access_accounting' as const,
  },
  {
    path: '/app/hr',
    label: 'HR',
    description: 'Events and bonuses',
    icon: Users,
    permission: 'can_access_hr' as const,
  },
  {
    path: '/app/settings',
    label: 'Settings',
    description: 'Users, roles, configuration',
    icon: Settings,
    permission: 'can_access_settings' as const,
  },
]

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

  const totalInvoices = companySummary?.reduce((sum, c) => sum + Number(c.invoice_count), 0) ?? 0
  const totalValue = companySummary?.reduce((sum, c) => sum + Number(c.total_value_ron ?? 0), 0) ?? 0

  const visibleApps = apps.filter((app) => {
    if (!('permission' in app) || !app.permission) return true
    return user?.[app.permission]
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">Welcome, {user?.name}.</p>
        </div>
        <div className="flex gap-2">
          {user?.can_add_invoices && (
            <Button asChild size="sm">
              <Link to="/app/accounting/add">
                <Plus className="mr-1.5 h-4 w-4" />
                Add Invoice
              </Link>
            </Button>
          )}
          <Button variant="outline" size="sm" asChild>
            <Link to="/app/ai-agent">
              <Bot className="mr-1.5 h-4 w-4" />
              New Chat
            </Link>
          </Button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
      </div>

      {/* Quick Navigation */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {visibleApps.map((app) => {
          const Icon = app.icon
          const inner = (
            <Card className="transition-shadow hover:shadow-md">
              <CardHeader>
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-primary/10 p-2">
                    <Icon className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-base">{app.label}</CardTitle>
                    <CardDescription>{app.description}</CardDescription>
                  </div>
                </div>
              </CardHeader>
            </Card>
          )
          return (
            <Link key={app.path} to={app.path}>{inner}</Link>
          )
        })}
      </div>

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
