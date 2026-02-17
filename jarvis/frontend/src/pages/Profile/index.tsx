import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTabParam } from '@/hooks/useTabParam'
import {
  FileText,
  Activity,
  Gift,
  Receipt,
  DollarSign,
  User,
  Mail,
  Phone,
  Building2,
  Shield,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { EmptyState } from '@/components/shared/EmptyState'
import { SearchInput } from '@/components/shared/SearchInput'
import { profileApi } from '@/api/profile'
import { cn, usePersistedState } from '@/lib/utils'
import type { ProfileInvoice, ProfileActivity, ProfileBonus } from '@/types/profile'

type Tab = 'invoices' | 'hr-events' | 'activity'

const tabs: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: 'invoices', label: 'My Invoices', icon: FileText },
  { key: 'hr-events', label: 'HR Events', icon: Gift },
  { key: 'activity', label: 'Activity Log', icon: Activity },
]

export default function Profile() {
  const [activeTab, setActiveTab] = useTabParam<Tab>('invoices')

  const { data: summary, isLoading } = useQuery({
    queryKey: ['profile', 'summary'],
    queryFn: profileApi.getSummary,
  })

  const user = summary?.user

  return (
    <div className="space-y-6">
      <PageHeader title="My Profile" description="Your account overview and activity." />

      {/* User Info Card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
            {/* Avatar */}
            {isLoading ? (
              <Skeleton className="h-16 w-16 rounded-full shrink-0" />
            ) : (
              <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xl font-bold">
                {user?.name
                  ?.split(' ')
                  .map((n) => n[0])
                  .join('')
                  .slice(0, 2)
                  .toUpperCase() || '?'}
              </div>
            )}

            {/* User Details */}
            <div className="flex-1 min-w-0">
              {isLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-6 w-48" />
                  <Skeleton className="h-4 w-64" />
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold">{user?.name}</h2>
                    {user?.role && <StatusBadge status={user.role} />}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <Mail className="h-3.5 w-3.5" />
                      {user?.email}
                    </span>
                    {user?.phone && (
                      <span className="flex items-center gap-1.5">
                        <Phone className="h-3.5 w-3.5" />
                        {user.phone}
                      </span>
                    )}
                    {user?.department && (
                      <span className="flex items-center gap-1.5">
                        <Building2 className="h-3.5 w-3.5" />
                        {user.department}
                      </span>
                    )}
                    {user?.company && (
                      <span className="flex items-center gap-1.5">
                        <Shield className="h-3.5 w-3.5" />
                        {user.company}
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats Row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          title="Invoices"
          value={summary?.invoices.total ?? 0}
          icon={<Receipt className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Invoice Value"
          value={
            summary
              ? new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
                  summary.invoices.total_value,
                ) + ' RON'
              : '0'
          }
          icon={<DollarSign className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="HR Bonuses"
          value={summary?.hr_events.total_bonuses ?? 0}
          icon={<Gift className="h-4 w-4" />}
          isLoading={isLoading}
        />
        <StatCard
          title="Activity Events"
          value={summary?.activity.total_events ?? 0}
          icon={<Activity className="h-4 w-4" />}
          isLoading={isLoading}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border p-1 w-fit">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors',
                activeTab === tab.key
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {activeTab === 'invoices' && <InvoicesPanel />}
      {activeTab === 'hr-events' && <HrEventsPanel />}
      {activeTab === 'activity' && <ActivityPanel />}
    </div>
  )
}

// ─── Invoices Panel ─────────────────────────────────────────────────

function InvoicesPanel() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = usePersistedState('profile-invoices-page-size', 25)

  const { data, isLoading } = useQuery({
    queryKey: ['profile', 'invoices', { search, page, perPage }],
    queryFn: () => profileApi.getInvoices({ search: search || undefined, page, per_page: perPage }),
  })

  const invoices = data?.invoices ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / perPage)

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">
            My Invoices
            <span className="ml-2 text-sm font-normal text-muted-foreground">({total})</span>
          </CardTitle>
          <SearchInput
            placeholder="Search invoices..."
            value={search}
            onChange={(v) => { setSearch(v); setPage(1) }}
            className="w-full sm:w-64"
          />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : invoices.length === 0 ? (
          <EmptyState title="No invoices" description="No invoices assigned to you yet." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Invoice #</TableHead>
                    <TableHead>Supplier</TableHead>
                    <TableHead>Company</TableHead>
                    <TableHead>Department</TableHead>
                    <TableHead className="text-right">Value</TableHead>
                    <TableHead className="text-right">%</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoices.map((inv: ProfileInvoice) => (
                    <TableRow key={inv.id}>
                      <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                        {new Date(inv.invoice_date).toLocaleDateString('ro-RO')}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{inv.invoice_number}</TableCell>
                      <TableCell className="max-w-[200px] truncate font-medium">{inv.supplier}</TableCell>
                      <TableCell className="text-sm">{inv.company}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{inv.department || '-'}</TableCell>
                      <TableCell className="text-right">
                        <CurrencyDisplay value={inv.allocation_value} currency={inv.currency} className="text-sm" />
                      </TableCell>
                      <TableCell className="text-right text-sm text-muted-foreground">
                        {inv.allocation_percent}%
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={inv.status} />
                      </TableCell>
                      <TableCell>
                        {inv.drive_link && (
                          <a
                            href={inv.drive_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <Pagination page={page} totalPages={totalPages} total={total} perPage={perPage} onPageChange={setPage} onPerPageChange={(n) => { setPerPage(n); setPage(1) }} />
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ─── HR Events Panel ────────────────────────────────────────────────

function HrEventsPanel() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = usePersistedState('profile-hr-page-size', 25)

  const { data, isLoading } = useQuery({
    queryKey: ['profile', 'hr-events', { search, page, perPage }],
    queryFn: () => profileApi.getHrEvents({ search: search || undefined, page, per_page: perPage }),
  })

  const bonuses = data?.bonuses ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / perPage)

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">
            HR Event Bonuses
            <span className="ml-2 text-sm font-normal text-muted-foreground">({total})</span>
          </CardTitle>
          <SearchInput
            placeholder="Search events..."
            value={search}
            onChange={(v) => { setSearch(v); setPage(1) }}
            className="w-full sm:w-64"
          />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : bonuses.length === 0 ? (
          <EmptyState title="No HR events" description="No event bonuses assigned to you." />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead>Event</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead className="text-right">Days</TableHead>
                  <TableHead className="text-right">Hours</TableHead>
                  <TableHead className="text-right">Net Bonus</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bonuses.map((b: ProfileBonus) => (
                  <TableRow key={b.id}>
                    <TableCell className="whitespace-nowrap text-sm">
                      {String(b.month).padStart(2, '0')}/{b.year}
                    </TableCell>
                    <TableCell className="font-medium">{b.event_name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{b.company || '-'}</TableCell>
                    <TableCell className="text-right text-sm">{b.bonus_days ?? '-'}</TableCell>
                    <TableCell className="text-right text-sm">{b.hours_free ?? '-'}</TableCell>
                    <TableCell className="text-right">
                      {b.bonus_net != null ? (
                        <CurrencyDisplay value={b.bonus_net} currency="RON" className="text-sm" />
                      ) : (
                        '-'
                      )}
                    </TableCell>
                    <TableCell className="max-w-[150px] truncate text-xs text-muted-foreground">
                      {b.details || '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <Pagination page={page} totalPages={totalPages} total={total} perPage={perPage} onPageChange={setPage} onPerPageChange={(n) => { setPerPage(n); setPage(1) }} />
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Activity Panel ─────────────────────────────────────────────────

function ActivityPanel() {
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = usePersistedState('profile-activity-page-size', 25)

  const { data, isLoading } = useQuery({
    queryKey: ['profile', 'activity', { page, perPage }],
    queryFn: () => profileApi.getActivity({ page, per_page: perPage }),
  })

  const events = data?.events ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / perPage)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Activity Log
          <span className="ml-2 text-sm font-normal text-muted-foreground">({total})</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <EmptyState title="No activity" description="No activity recorded yet." />
        ) : (
          <>
            <div className="space-y-1">
              {events.map((ev: ProfileActivity) => (
                <div
                  key={ev.id}
                  className="flex items-start gap-3 rounded-md px-3 py-2.5 transition-colors hover:bg-muted/50"
                >
                  <div className="mt-0.5">
                    <ActivityIcon type={ev.event_type} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono">{ev.event_type}</span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(ev.created_at).toLocaleString('ro-RO')}
                      </span>
                    </div>
                    {ev.ip_address && (
                      <p className="mt-0.5 text-xs text-muted-foreground">IP: {ev.ip_address}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <Pagination page={page} totalPages={totalPages} total={total} perPage={perPage} onPageChange={setPage} onPerPageChange={(n) => { setPerPage(n); setPage(1) }} />
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────

function ActivityIcon({ type }: { type: string }) {
  const base = 'h-5 w-5 rounded-full p-0.5'
  switch (type) {
    case 'login':
      return <User className={cn(base, 'text-green-600')} />
    case 'logout':
      return <User className={cn(base, 'text-gray-400')} />
    case 'login_failed':
      return <Shield className={cn(base, 'text-red-500')} />
    default:
      return <Activity className={cn(base, 'text-blue-500')} />
  }
}

function Pagination({
  page,
  totalPages,
  total,
  perPage,
  onPageChange,
  onPerPageChange,
}: {
  page: number
  totalPages: number
  total: number
  perPage: number
  onPageChange: (p: number) => void
  onPerPageChange?: (n: number) => void
}) {
  const from = (page - 1) * perPage + 1
  const to = Math.min(page * perPage, total)

  return (
    <div className="mt-4 flex items-center justify-between">
      <span className="text-xs text-muted-foreground">
        {from}-{to} of {total}
      </span>
      <div className="flex items-center gap-3">
        {onPerPageChange && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Rows</span>
            <Select
              value={String(perPage)}
              onValueChange={(v) => onPerPageChange(Number(v))}
            >
              <SelectTrigger className="h-8 w-[70px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[25, 50, 100, 200].map((n) => (
                  <SelectItem key={n} value={String(n)}>{n}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="flex gap-1">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
