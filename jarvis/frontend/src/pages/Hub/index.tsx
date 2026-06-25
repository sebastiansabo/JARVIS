import React, { useState, useMemo, useCallback, lazy, Suspense } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Activity,
  Ticket,
  LogIn,
  LogOut,
  Bell,
  FileCheck,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Fingerprint,
  Gift,
  ClipboardList,
  Car,
  MessageSquare,
  Ticket as TicketIcon,
  Clock,
  Award,
  Eye,
  ExternalLink,
  SlidersHorizontal,
  Pencil,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { DateField } from '@/components/ui/date-field'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { EmptyState } from '@/components/shared/EmptyState'
import { SearchInput } from '@/components/shared/SearchInput'
import { FilterBar, type FilterField } from '@/components/shared/FilterBar'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { InvoiceLinkedDocs } from '@/components/shared/InvoiceLinkedDocs'
import { AllocationEditor, allocationsToRows, rowsToApiPayload } from '@/pages/Accounting/AllocationEditor'
import { EditInvoiceDialog } from '@/pages/Accounting/EditInvoiceDialog'
import { dedupeMergedAllocations } from '@/pages/Accounting/allocationUtils'
import { LineItemAllocationsView } from '@/pages/Accounting/LineItemAllocationsView'
import { useAuthStore } from '@/stores/authStore'
import { useAuth } from '@/hooks/useAuth'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { profileApi } from '@/api/profile'
import { settingsApi } from '@/api/settings'
import { checkinApi } from '@/api/checkin'
import { notificationsApi } from '@/api/notifications'
import { connecteamApi, type ConnecteamSubmission } from '@/api/connecteam'
import { cn, usePersistedState } from '@/lib/utils'
import { toast } from 'sonner'
import type { InAppNotification } from '@/types/notifications'
import type { ProfileInvoice, ProfileBonus } from '@/types/profile'
import type { Invoice } from '@/types/invoices'
import type { BioStarDayHistory } from '@/types/biostar'

const VouchersPanel = lazy(() => import('@/pages/Profile/VouchersPanel'))
const CreateTicketDialog = lazy(() => import('@/pages/Ticketing/CreateTicketDialog'))

// ─── Types ──────────────────────────────────────────────

type ActiveModule = null | 'invoices' | 'hr' | 'vouchers' | 'forms'
type HrSubTab = 'pontaje' | 'bonuses' | 'leave-permits'

interface AppTile {
  key: NonNullable<ActiveModule>
  label: string
  icon: React.ElementType
  bg: string
  fg: string
}

const appTiles: AppTile[] = [
  { key: 'invoices', label: 'My Invoices', icon: FileText, bg: 'bg-blue-600', fg: 'text-white' },
  { key: 'hr', label: 'HR', icon: Activity, bg: 'bg-emerald-600', fg: 'text-white' },
  { key: 'vouchers', label: 'Vouchers', icon: Ticket, bg: 'bg-amber-500', fg: 'text-white' },
  { key: 'forms', label: 'Forms', icon: ClipboardList, bg: 'bg-violet-600', fg: 'text-white' },
]

const MONTHS_RO = ['Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie', 'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

// ─── JARVIS Hub ────────────────────────────────────────

export default function Hub() {
  const authUser = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [ticketOpen, setTicketOpen] = useState(false)
  const activeModule = (searchParams.get('module') as ActiveModule) || null
  const setActiveModule = useCallback((mod: ActiveModule) => {
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev)
      if (mod) { p.set('module', mod) } else { p.delete('module'); p.delete('hrtab') }
      return p
    }, { replace: true })
  }, [setSearchParams])

  // Profile summary
  const { data: summary, isLoading: loadingProfile } = useQuery({
    queryKey: ['profile', 'summary'],
    queryFn: profileApi.getSummary,
  })
  const user = summary?.user

  // Check-in status
  const { data: checkinStatus } = useQuery({
    queryKey: ['checkin', 'status'],
    queryFn: async () => {
      const res = await checkinApi.getStatus()
      return (res as any).data ?? res
    },
    refetchInterval: 60_000,
  })

  const punchMut = useMutation({
    mutationFn: async () => {
      const pos = await new Promise<GeolocationPosition | null>((resolve) => {
        if (!navigator.geolocation) return resolve(null)
        navigator.geolocation.getCurrentPosition(resolve, () => resolve(null), {
          enableHighAccuracy: true, timeout: 5000, maximumAge: 0,
        })
      })
      const payload: { lat?: number; lng?: number; direction?: string } = {}
      if (pos) { payload.lat = pos.coords.latitude; payload.lng = pos.coords.longitude }
      payload.direction = checkinStatus?.next_direction ?? 'IN'
      const res = await checkinApi.punch(payload)
      return (res as any).data ?? res
    },
    onSuccess: (res) => {
      if (res.success) {
        queryClient.invalidateQueries({ queryKey: ['checkin', 'status'] })
        toast.success(`${res.direction} at ${res.time} — ${res.location}`)
      } else {
        toast.error(res.error || 'Punch failed')
      }
    },
    onError: () => toast.error('Punch failed'),
  })

  const checkinDir = checkinStatus?.next_direction ?? 'IN'
  const isCheckedIn = checkinDir !== 'IN'
  const lastPunch = checkinStatus?.punches?.length
    ? checkinStatus.punches[checkinStatus.punches.length - 1]
    : null

  // Notifications
  const { data: notifData } = useQuery({
    queryKey: ['notifications', 'hub'],
    queryFn: () => notificationsApi.getNotifications({ limit: 15 }),
    refetchInterval: 60_000,
  })
  const notifications: InAppNotification[] = notifData?.notifications ?? []

  const markReadMut = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })

  // Pre-fetch counts to hide empty tiles
  const { data: invoicesData } = useQuery({
    queryKey: ['hub', 'invoices-count'],
    queryFn: () => profileApi.getInvoices({ per_page: 1 }),
    staleTime: 60_000,
  })
  const { data: vouchersData } = useQuery({
    queryKey: ['hub', 'vouchers-count'],
    queryFn: () => fetch('/api/vouchers/my?limit=1', { credentials: 'include' }).then(r => r.json()),
    staleTime: 60_000,
  })
  const { data: formsCountData } = useQuery({
    queryKey: ['hub', 'forms-count'],
    queryFn: () => fetch('/forms/api/forms/published', { credentials: 'include' }).then(r => r.json()),
    staleTime: 60_000,
  })

  const tileCounts: Record<string, number> = {
    invoices: invoicesData?.total ?? -1,
    hr: -1, // always show — sub-tabs auto-hide when empty
    vouchers: Array.isArray(vouchersData) ? vouchersData.length : -1,
    forms: (formsCountData?.forms ?? []).length || -1,
  }

  const hasVouchersPerm = !authUser?.permissions || (authUser.permissions['vouchers.profile.view'] ?? true)
  const visibleTiles = useMemo(() => {
    return appTiles.filter((t) => {
      if (t.key === 'vouchers' && !hasVouchersPerm) return false
      if (tileCounts[t.key] === 0) return false
      return true
    })
  }, [hasVouchersPerm, tileCounts])

  return (
    <div className="space-y-6">
      {/* Header */}
      {loadingProfile ? (
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-4">
            <Skeleton className="h-11 w-11 rounded-full shrink-0" />
            <div className="space-y-1.5"><Skeleton className="h-3 w-24" /><Skeleton className="h-5 w-36" /></div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-4">
            {/* Avatar + Name */}
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
              {user?.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase() || '?'}
            </div>
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground truncate">{user?.name || 'Loading...'}</p>
              <h1 className="text-lg font-bold leading-tight">JARVIS Hub</h1>
            </div>

            {/* Right: company, role, actions */}
            <div className="ml-auto flex items-center gap-2">
              {user?.company && (
                <span className="text-xs text-muted-foreground hidden sm:inline">{user.company}</span>
              )}
              {authUser?.role_name && (
                <Badge variant="outline" className="text-xs">{authUser.role_name}</Badge>
              )}

              {/* Check In/Out — always visible */}
              <div className="flex items-center gap-2">
                {lastPunch && (
                  <div className="text-xs text-right leading-tight hidden sm:block">
                    <p className="font-medium">
                      {lastPunch.direction === 'IN' ? 'In' : 'Out'} at{' '}
                      {new Date(lastPunch.event_datetime).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                    {lastPunch.raw_data?.location_name && (
                      <p className="text-muted-foreground">{lastPunch.raw_data.location_name}</p>
                    )}
                  </div>
                )}
                <Button
                  size="sm"
                  className={cn('font-semibold text-white', isCheckedIn ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700')}
                  onClick={() => punchMut.mutate()}
                  disabled={punchMut.isPending}
                >
                  {isCheckedIn ? <LogOut className="h-3.5 w-3.5 mr-1.5" /> : <LogIn className="h-3.5 w-3.5 mr-1.5" />}
                  {punchMut.isPending ? '...' : isCheckedIn ? 'Check Out' : 'Check In'}
                </Button>
              </div>

              <Button size="sm" variant="outline" onClick={() => setTicketOpen(true)}>
                <TicketIcon className="h-3.5 w-3.5 mr-1.5" />Ticket
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Ticket Dialog */}
      <Suspense fallback={null}>
        <CreateTicketDialog open={ticketOpen} onOpenChange={setTicketOpen} />
      </Suspense>

      {/* ── Active Module (inline content) ── */}
      {activeModule !== null ? (
        <div className="space-y-4">
          <Button variant="ghost" size="sm" className="gap-1.5 -ml-1" onClick={() => setActiveModule(null)}>
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>
          {activeModule === 'invoices' && <HubInvoicesPanel />}
          {activeModule === 'hr' && user && <HubHrPanel userId={user.id} />}
          {activeModule === 'forms' && <HubFormsPanel />}
          {activeModule === 'vouchers' && (
            <Suspense fallback={<div className="py-8 text-center text-muted-foreground text-sm">Loading...</div>}>
              <VouchersPanel />
            </Suspense>
          )}
        </div>
      ) : (
        /* ── Grid: 2/3 apps + 1/3 notifications ── */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left 2/3 */}
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Apps</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-6">
                  {visibleTiles.map((tile) => {
                    const Icon = tile.icon
                    return (
                      <button
                        key={tile.key}
                        type="button"
                        onClick={() => setActiveModule(tile.key)}
                        className="flex flex-col items-center gap-1.5 w-20 group"
                      >
                        <div className={cn('flex h-14 w-14 items-center justify-center rounded-xl shadow-sm transition-transform group-hover:scale-105 group-hover:shadow-md', tile.bg, tile.fg)}>
                          <Icon className="h-7 w-7" />
                        </div>
                        <p className="text-[11px] font-medium text-center leading-tight">{tile.label}</p>
                      </button>
                    )
                  })}
                </div>
              </CardContent>
            </Card>

            {/* HR Summary Card */}
            <HubHrSummaryCard />

            {/* Marketing Events & Bonuses Card */}
            <HubBonusCard />
          </div>

          {/* Right 1/3 — Notifications + Punch Card */}
          <div className="space-y-6">
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                    <Bell className="h-4 w-4" />
                    Notifications
                  </CardTitle>
                  {notifications.some((n) => !n.is_read) && (
                    <Button variant="ghost" size="sm" className="h-6 text-[10px] px-2" onClick={() => {
                      notificationsApi.markAllRead().then(() => queryClient.invalidateQueries({ queryKey: ['notifications'] }))
                    }}>
                      Mark all read
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-1 max-h-[40vh] overflow-y-auto">
                {notifications.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center py-6">No notifications</p>
                ) : notifications.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    className={cn('w-full text-left rounded-md px-3 py-2.5 transition-colors hover:bg-accent/50', !n.is_read && 'bg-primary/5')}
                    onClick={() => {
                      if (!n.is_read) markReadMut.mutate(n.id)
                      if (n.link) navigate(n.link)
                    }}
                  >
                    <div className="flex items-start gap-2">
                      {!n.is_read && <span className="mt-1.5 h-2 w-2 rounded-full bg-primary shrink-0" />}
                      <div className="min-w-0 flex-1">
                        <p className={cn('text-xs leading-tight', !n.is_read ? 'font-medium' : 'text-muted-foreground')}>{n.title}</p>
                        {n.message && <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">{n.message}</p>}
                        <p className="text-[10px] text-muted-foreground mt-1">
                          {new Date(n.created_at).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                        </p>
                      </div>
                    </div>
                  </button>
                ))}
              </CardContent>
            </Card>

            {/* Weekly Punch Card */}
            <HubWeeklyPunchCard />
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Invoices Panel (full-featured, same as Profile) ────

function HubInvoicesPanel() {
  const isMobile = useIsMobile()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [department, setDepartment] = useState('')
  const [status, setStatus] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [archiveView, setArchiveView] = useState<'active' | 'archived'>('active')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = usePersistedState('hub-invoices-page-size', 25)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editInvoice, setEditInvoice] = useState<Invoice | null>(null)

  const isArchivedView = archiveView === 'archived'
  const canEdit = isArchivedView ? false : (user?.can_edit_invoices || (user?.permissions?.['invoices.records.edit'] ?? false))

  const handleDownloadPdf = async (inv: ProfileInvoice) => {
    const url = inv.drive_link?.startsWith('/efactura/')
      ? `/profile/api/invoices/${inv.id}/pdf`
      : inv.drive_link
    if (!url) return
    if (!inv.drive_link?.startsWith('/efactura/')) {
      window.open(url, '_blank', 'noopener')
      return
    }
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const filename = res.headers.get('Content-Disposition')?.match(/filename="?([^";\n]+)"?/)?.[1] || `invoice-${inv.id}.pdf`
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = filename
      document.body.appendChild(a)
      a.click()
      URL.revokeObjectURL(a.href)
      a.remove()
    } catch {
      window.location.href = url
    }
  }

  const { data: dropdownOptions = [] } = useQuery({
    queryKey: ['settings', 'dropdowns'],
    queryFn: () => settingsApi.getDropdownOptions(),
    staleTime: 10 * 60_000,
  })
  const statusOptions = useMemo(
    () => dropdownOptions.filter((d) => d.dropdown_type === 'invoice_status' && d.value).map((d) => ({ value: d.value, label: d.label, color: d.color })),
    [dropdownOptions],
  )
  const statusLabelMap = useMemo(
    () => Object.fromEntries(statusOptions.map((o) => [o.value, o.label])),
    [statusOptions],
  )
  const paymentOptions = useMemo(
    () => dropdownOptions.filter((d) => d.dropdown_type === 'payment_status' && d.value).map((d) => ({ value: d.value, label: d.label })),
    [dropdownOptions],
  )

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'invoices', { search, department, status, startDate, endDate, page, perPage, archiveView }],
    queryFn: () => profileApi.getInvoices({ search: search || undefined, department: department || undefined, status: status || undefined, start_date: startDate || undefined, end_date: endDate || undefined, page, per_page: perPage, archive_view: archiveView }),
  })

  const { data: expandedInvoice } = useQuery({
    queryKey: ['profile', 'invoice-detail', expandedId],
    queryFn: () => profileApi.getInvoiceDetail(expandedId!),
    enabled: expandedId !== null,
  })

  const saveMutation = useMutation({
    mutationFn: (payload: { invoiceId: number; company: string; rows: import('@/pages/Accounting/AllocationEditor').AllocationRow[] }) =>
      profileApi.updateAllocations(payload.invoiceId, {
        allocations: rowsToApiPayload(payload.company, payload.rows),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hub', 'invoices'] })
      queryClient.invalidateQueries({ queryKey: ['profile', 'invoices'] })
      queryClient.invalidateQueries({ queryKey: ['invoices'] })
      setEditingId(null)
      toast.success('Allocations updated')
    },
    onError: () => toast.error('Failed to update allocations'),
  })

  const invoices = data?.invoices ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / perPage)

  const filterFields: FilterField[] = useMemo(() => [
    { key: 'status', label: 'Status', type: 'select' as const, options: statusOptions },
  ], [statusOptions])

  const filterValues: Record<string, string> = useMemo(() => ({
    department,
    status,
  }), [department, status])

  const handleFilterChange = (values: Record<string, string>) => {
    if ('department' in values) { setDepartment(values.department || ''); setPage(1) }
    if ('status' in values) { setStatus(values.status || ''); setPage(1) }
  }

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id)
    if (expandedId === id) setEditingId(null)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base">
              My Invoices
              <span className="ml-2 text-sm font-normal text-muted-foreground">({total})</span>
            </CardTitle>
            <div className="flex items-center rounded-md border bg-muted/50 p-0.5 gap-0.5">
              <Button
                variant={archiveView === 'active' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => { setArchiveView('active'); setPage(1) }}
              >
                Active
              </Button>
              <Button
                variant={archiveView === 'archived' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => { setArchiveView('archived'); setPage(1) }}
              >
                Archived
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Button variant="ghost" size="icon" className={cn('h-8 w-8', showFilters && 'bg-muted')} onClick={() => setShowFilters(s => !s)} title="Toggle filters">
              <SlidersHorizontal className="h-4 w-4" />
            </Button>
            <SearchInput
              placeholder="Search invoices..."
              value={search}
              onChange={(v) => { setSearch(v); setPage(1) }}
              className="w-full sm:w-64"
            />
          </div>
        </div>
        {showFilters && (
          <div className="flex flex-wrap items-center gap-2 pt-2">
            <FilterBar fields={filterFields} values={filterValues} onChange={handleFilterChange} iconOnly={isMobile} />
            <DateField
              mode="range"
              startDate={startDate}
              endDate={endDate}
              onRangeChange={(s, e) => { setStartDate(s); setEndDate(e); setPage(1) }}
            />
          </div>
        )}
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
            {isMobile ? (
              <MobileCardList
                data={invoices}
                fields={[
                  { key: 'supplier', label: 'Supplier', isPrimary: true, render: (inv) => (
                    <div className="flex items-center gap-1.5">
                      <span className="truncate">{inv.supplier}</span>
                      {inv.is_observer && (
                        <Badge variant="outline" className="gap-0.5 px-1.5 py-0 text-[10px] text-muted-foreground">
                          <Eye className="h-2.5 w-2.5" />
                          Observer
                        </Badge>
                      )}
                    </div>
                  ) },
                  { key: 'invoice_number', label: 'Invoice #', isSecondary: true, render: (inv) => <span className="font-mono">{inv.invoice_number}</span> },
                  { key: 'date', label: 'Date', isSecondary: true, render: (inv) => new Date(inv.invoice_date).toLocaleDateString('ro-RO') },
                  { key: 'value', label: 'Value', render: (inv) => <CurrencyDisplay value={inv.invoice_value} currency={inv.currency} className="text-xs" /> },
                  { key: 'status', label: 'Status', render: (inv) => <StatusBadge status={inv.status} label={statusLabelMap[inv.status] || inv.status} /> },
                  { key: 'company', label: 'Company', expandOnly: true, render: (inv) => inv.company },
                  { key: 'department', label: 'Department', expandOnly: true, render: (inv) => inv.department || '-' },
                  { key: 'percent', label: 'Allocation', expandOnly: true, render: (inv) => {
                    const allocs = inv.allocation_mode === 'per_line' && inv.allocations
                      ? dedupeMergedAllocations(inv.allocations as never)
                      : (inv.allocations ?? [])
                    return (allocs.length || 1) > 1 ? 'split' : `${inv.allocation_percent}%`
                  } },
                ] satisfies MobileCardField<ProfileInvoice>[]}
                getRowId={(inv) => inv.id}
                actions={(inv) => inv.drive_link ? (
                  <button
                    onClick={() => handleDownloadPdf(inv)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-6" />
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
                    {invoices.map((inv: ProfileInvoice) => {
                      const isExpanded = expandedId === inv.id
                      const dedupedAllocs = inv.allocation_mode === 'per_line' && inv.allocations
                        ? dedupeMergedAllocations(inv.allocations as never)
                        : (inv.allocations ?? [])
                      const allocCount = dedupedAllocs.length || 1

                      return (
                        <React.Fragment key={inv.id}>
                          <TableRow
                            className="cursor-pointer hover:bg-muted/40"
                            onClick={() => toggleExpand(inv.id)}
                          >
                            <TableCell className="px-1">
                              {isExpanded
                                ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                                : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                              {new Date(inv.invoice_date).toLocaleDateString('ro-RO')}
                            </TableCell>
                            <TableCell className="font-mono text-xs">{inv.invoice_number}</TableCell>
                            <TableCell className="max-w-[200px] font-medium">
                              <div className="flex items-center gap-1.5">
                                <span className="truncate">{inv.supplier}</span>
                                {inv.is_observer && (
                                  <Badge
                                    variant="outline"
                                    className="gap-0.5 px-1.5 py-0 text-[10px] text-muted-foreground"
                                    title="You are an observer on this invoice (view-only)"
                                  >
                                    <Eye className="h-2.5 w-2.5" />
                                    Observer
                                  </Badge>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="text-sm">{inv.company}</TableCell>
                            <TableCell className="text-sm text-muted-foreground">
                              {inv.department || '-'}
                              {allocCount > 1 && <span className="ml-1 text-xs text-muted-foreground/60">+{allocCount - 1}</span>}
                            </TableCell>
                            <TableCell className="text-right">
                              <CurrencyDisplay value={inv.invoice_value} currency={inv.currency} className="text-sm" />
                            </TableCell>
                            <TableCell className="text-right text-sm text-muted-foreground">
                              {allocCount > 1 ? 'split' : `${inv.allocation_percent}%`}
                            </TableCell>
                            <TableCell>
                              <StatusBadge status={inv.status} label={statusLabelMap[inv.status] || inv.status} />
                            </TableCell>
                            <TableCell onClick={(e) => e.stopPropagation()}>
                              {inv.drive_link && (
                                <button
                                  onClick={() => handleDownloadPdf(inv)}
                                  className="text-muted-foreground hover:text-foreground"
                                >
                                  <ExternalLink className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </TableCell>
                          </TableRow>
                          {isExpanded && (
                            <TableRow>
                              <TableCell colSpan={10} className="p-0">
                                <HubInvoiceExpansion
                                  invoiceId={inv.id}
                                  invoice={expandedInvoice}
                                  isEditing={editingId === inv.id}
                                  canEdit={canEdit}
                                  onEdit={() => setEditingId(inv.id)}
                                  onCancelEdit={() => setEditingId(null)}
                                  onSave={(company, rows) => saveMutation.mutate({ invoiceId: inv.id, company, rows })}
                                  isSaving={saveMutation.isPending}
                                  onEditInvoice={(fullInv) => setEditInvoice(fullInv)}
                                />
                              </TableCell>
                            </TableRow>
                          )}
                        </React.Fragment>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}

            <HubPagination page={page} totalPages={totalPages} total={total} perPage={perPage} onPageChange={setPage} onPerPageChange={(n) => { setPerPage(n); setPage(1) }} />
          </>
        )}
      </CardContent>

      {editInvoice && (
        <EditInvoiceDialog
          invoice={editInvoice}
          open={!!editInvoice}
          onClose={() => setEditInvoice(null)}
          statusOptions={statusOptions}
          paymentOptions={paymentOptions}
          mode="profile"
          apiOverrides={{
            updateInvoice: profileApi.updateInvoiceMetadata,
            updateAllocations: profileApi.updateAllocations,
          }}
          invalidateQueryKeys={[['hub', 'invoices'], ['profile', 'invoices'], ['profile', 'invoice-detail'], ['invoices']]}
        />
      )}
    </Card>
  )
}

// ─── Invoice Expansion Row ──────────────────────────────

function HubInvoiceExpansion({
  invoiceId,
  invoice,
  isEditing,
  canEdit,
  onEdit,
  onCancelEdit,
  onSave,
  isSaving,
  onEditInvoice,
}: {
  invoiceId: number
  invoice: unknown
  isEditing: boolean
  canEdit: boolean
  onEdit: () => void
  onCancelEdit: () => void
  onSave: (company: string, rows: import('@/pages/Accounting/AllocationEditor').AllocationRow[]) => void
  isSaving: boolean
  onEditInvoice: (inv: Invoice) => void
}) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const inv = invoice as any

  if (!inv) {
    return (
      <div className="px-8 py-4 bg-muted/30">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          Loading allocations...
        </div>
      </div>
    )
  }

  const rawAllocations = (inv.allocations ?? []) as Array<Record<string, unknown>>
  const isPerLine = inv.allocation_mode === 'per_line'
  const allocations = (
    isPerLine
      ? (dedupeMergedAllocations(rawAllocations as unknown as never) as unknown as Array<Record<string, unknown>>)
      : rawAllocations
  )
  const effectiveValue = (inv.net_value ?? inv.invoice_value) as number
  const currency = inv.currency as string

  if (isEditing) {
    return (
      <div className="px-8 py-3 bg-muted/30 border-l-2 border-l-primary/50">
        <AllocationEditor
          initialCompany={allocations[0]?.company as string}
          initialRows={allocations.length > 0 ? allocationsToRows(allocations as never, effectiveValue) : undefined}
          effectiveValue={effectiveValue}
          currency={currency}
          onSave={onSave}
          onCancel={onCancelEdit}
          isSaving={isSaving}
          compact
        />
      </div>
    )
  }

  if (allocations.length === 0) {
    return (
      <div className="px-8 py-4 bg-muted/30">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">No allocations</span>
          {canEdit && (
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => onEditInvoice(inv as Invoice)}>
                <Pencil className="h-3 w-3 mr-1" /> Edit Invoice
              </Button>
              <Button variant="outline" size="sm" onClick={onEdit}>
                <Pencil className="h-3 w-3 mr-1" /> Add Allocation
              </Button>
            </div>
          )}
        </div>
        <InvoiceLinkedDocs
          invoiceId={invoiceId}
          isBin={false}
          canEdit={canEdit}
          api={{
            getDocs: profileApi.getInvoiceDmsDocuments,
            unlinkDoc: profileApi.unlinkDmsDocument,
            searchDocs: profileApi.searchDmsDocuments,
            linkDoc: profileApi.linkDmsDocument,
            uploadAndLink: profileApi.uploadAndLinkDms,
          }}
        />
      </div>
    )
  }

  if (isPerLine && (inv.line_items?.length ?? 0) > 0) {
    return (
      <div className="px-8 py-3 bg-muted/30 border-l-2 border-l-primary/50">
        <LineItemAllocationsView
          invoice={inv as Invoice}
          canEdit={canEdit}
          onEdit={() => onEditInvoice(inv as Invoice)}
        />
        {canEdit && (
          <div className="mt-2 flex justify-end">
            <Button variant="outline" size="sm" onClick={() => onEditInvoice(inv as Invoice)}>
              <Pencil className="h-3 w-3 mr-1" /> Edit Invoice
            </Button>
          </div>
        )}
        <InvoiceLinkedDocs
          invoiceId={invoiceId}
          isBin={false}
          canEdit={canEdit}
          api={{
            getDocs: profileApi.getInvoiceDmsDocuments,
            unlinkDoc: profileApi.unlinkDmsDocument,
            searchDocs: profileApi.searchDmsDocuments,
            linkDoc: profileApi.linkDmsDocument,
            uploadAndLink: profileApi.uploadAndLinkDms,
          }}
        />
      </div>
    )
  }

  const hasBrand = allocations.some(a => a.brand) || allocations.some(a => (a.reinvoice_destinations as Array<Record<string, unknown>> | undefined)?.some(rd => rd.brand))
  const hasSubdept = allocations.some(a => a.subdepartment) || allocations.some(a => (a.reinvoice_destinations as Array<Record<string, unknown>> | undefined)?.some(rd => rd.subdepartment))

  return (
    <div className="px-8 py-3 bg-muted/30 border-l-2 border-l-primary/50">
      <table className="text-xs w-full">
        <thead>
          <tr className="text-[10px] text-muted-foreground/70 uppercase tracking-wider">
            <th className="py-1 pr-4 text-left font-medium">Company</th>
            {hasBrand && <th className="py-1 pr-4 text-left font-medium">Brand</th>}
            <th className="py-1 pr-4 text-left font-medium">Department</th>
            {hasSubdept && <th className="py-1 pr-4 text-left font-medium">Sub-dept</th>}
            <th className="py-1 pr-4 text-left font-medium">Responsible</th>
            <th className="py-1 pr-4 text-right font-medium">Amount</th>
            <th className="py-1 pr-4 text-right font-medium w-14">%</th>
            <th className="w-7" />
          </tr>
        </thead>
        <tbody>
          {allocations.map((alloc, idx) => {
            const reinvoiceDests = (alloc.reinvoice_destinations ?? []) as Array<Record<string, unknown>>
            const hasReinvoice = reinvoiceDests.length > 0
            const totalTableRows = allocations.reduce(
              (sum, a) => sum + 1 + ((a.reinvoice_destinations as Array<unknown> | undefined)?.length ?? 0), 0
            )
            return (
              <React.Fragment key={alloc.id as number}>
                <tr className={cn('border-t border-border/50', hasReinvoice && 'text-muted-foreground/50')}>
                  <td className="py-1 pr-4">{alloc.company as string}</td>
                  {hasBrand && <td className="py-1 pr-4">{(alloc.brand as string) || '-'}</td>}
                  <td className="py-1 pr-4">{alloc.department as string}</td>
                  {hasSubdept && <td className="py-1 pr-4">{(alloc.subdepartment as string) || '-'}</td>}
                  <td className="py-1 pr-4 text-muted-foreground">{(alloc.responsible as string) || '-'}</td>
                  <td className={cn('py-1 pr-4 text-right tabular-nums', hasReinvoice && 'opacity-40')}>
                    <CurrencyDisplay value={alloc.allocation_value as number} currency={currency} />
                  </td>
                  <td className="py-1 pr-4 text-right tabular-nums">{alloc.allocation_percent as number}%</td>
                  {idx === 0 && canEdit && (
                    <td rowSpan={totalTableRows} className="py-1 pl-1 align-middle w-7">
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onEdit}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                    </td>
                  )}
                </tr>
                {hasReinvoice && reinvoiceDests.map((rd) => (
                  <tr key={rd.id as number} className="text-[11px]">
                    <td className="py-0.5 pl-6 pr-4 text-foreground">{rd.company as string}</td>
                    {hasBrand && <td className="py-0.5 pr-4 text-foreground">{(rd.brand as string) || '-'}</td>}
                    <td className="py-0.5 pr-4 text-foreground">{rd.department as string}</td>
                    {hasSubdept && <td className="py-0.5 pr-4 text-foreground">{(rd.subdepartment as string) || '-'}</td>}
                    <td className="py-0.5 pr-4 text-muted-foreground italic">reinvoiced</td>
                    <td className="py-0.5 pr-4 text-right text-foreground tabular-nums">
                      <CurrencyDisplay value={rd.value as number} currency={currency} />
                    </td>
                    <td className="py-0.5 pr-4 text-right text-foreground tabular-nums">{rd.percentage as number}%</td>
                  </tr>
                ))}
              </React.Fragment>
            )
          })}
        </tbody>
      </table>

      {canEdit && (
        <div className="mt-2 flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onEditInvoice(inv as Invoice)}>
            <Pencil className="h-3 w-3 mr-1" /> Edit Invoice
          </Button>
        </div>
      )}

      <InvoiceLinkedDocs
        invoiceId={invoiceId}
        isBin={false}
        canEdit={canEdit}
        api={{
          getDocs: profileApi.getInvoiceDmsDocuments,
          unlinkDoc: profileApi.unlinkDmsDocument,
          searchDocs: profileApi.searchDmsDocuments,
          linkDoc: profileApi.linkDmsDocument,
          uploadAndLink: profileApi.uploadAndLinkDms,
        }}
      />
    </div>
  )
}

// ─── Pagination ─────────────────────────────────────────

function HubPagination({
  page, totalPages, total, perPage, onPageChange, onPerPageChange,
}: {
  page: number; totalPages: number; total: number; perPage: number
  onPageChange: (p: number) => void; onPerPageChange?: (n: number) => void
}) {
  const from = (page - 1) * perPage + 1
  const to = Math.min(page * perPage, total)
  return (
    <div className="mt-4 flex items-center justify-between">
      <span className="text-xs text-muted-foreground">{from}-{to} of {total}</span>
      <div className="flex items-center gap-3">
        {onPerPageChange && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Rows</span>
            <Select value={String(perPage)} onValueChange={(v) => onPerPageChange(Number(v))}>
              <SelectTrigger className="h-8 w-[70px]"><SelectValue /></SelectTrigger>
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

// ─── HR Panel ───────────────────────────────────────────

function HubHrPanel({ userId }: { userId: number }) {
  const [sp, setSp] = useSearchParams()
  const subTab = (sp.get('hrtab') as HrSubTab) || 'pontaje'
  const setSubTab = (tab: HrSubTab) => {
    setSp((prev) => { const p = new URLSearchParams(prev); p.set('hrtab', tab); return p }, { replace: true })
  }
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const start = `${year}-${String(month).padStart(2, '0')}-01`
  const lastDay = new Date(year, month, 0).getDate()
  const end = `${year}-${String(month).padStart(2, '0')}-${lastDay}`

  // Pre-fetch all HR data to know which tabs have content
  const { data: pontajeData } = useQuery({
    queryKey: ['hub', 'pontaje', start, end],
    queryFn: () => profileApi.getPontaje({ start, end }),
  })
  const { data: bonusesData } = useQuery({
    queryKey: ['hub', 'bonuses', year, month],
    queryFn: () => profileApi.getHrEvents({ year, month }),
  })
  const { data: lpData } = useQuery({
    queryKey: ['hub', 'leave-permits', userId, year, month],
    queryFn: () => connecteamApi.getEmployeeSubmissions(userId, year, month),
  })

  const pontajeCount = (pontajeData?.history ?? []).length
  const bonusesCount = (bonusesData?.bonuses ?? []).length
  const lpCount = (lpData?.data ?? []).length

  const availableTabs = useMemo(() => {
    const tabs: { key: HrSubTab; label: string; icon: React.ElementType }[] = []
    if (pontajeCount > 0) tabs.push({ key: 'pontaje', label: 'Pontaje', icon: Fingerprint })
    if (bonusesCount > 0) tabs.push({ key: 'bonuses', label: 'Bonuses', icon: Gift })
    if (lpCount > 0) tabs.push({ key: 'leave-permits', label: 'Leave Permits', icon: ClipboardList })
    return tabs
  }, [pontajeCount, bonusesCount, lpCount])

  // Auto-select first available tab if current has no data
  const effectiveTab = availableTabs.find(t => t.key === subTab) ? subTab : availableTabs[0]?.key ?? 'pontaje'

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1) }
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1) }

  if (availableTabs.length === 0) {
    return <Card><CardContent className="py-12 text-center text-muted-foreground text-sm">No HR data for {MONTHS_RO[month - 1]} {year}.</CardContent></Card>
  }

  return (
    <div className="space-y-4">
      {availableTabs.length > 1 && (
        <Tabs value={effectiveTab} onValueChange={(v) => setSubTab(v as HrSubTab)}>
          <TabsList className="h-8 bg-muted/50">
            {availableTabs.map((tab) => {
              const Icon = tab.icon
              return <TabsTrigger key={tab.key} value={tab.key} className="text-xs h-7 px-2.5 gap-1"><Icon className="h-3.5 w-3.5" />{tab.label}</TabsTrigger>
            })}
          </TabsList>
        </Tabs>
      )}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={prevMonth}><ChevronLeft className="h-4 w-4" /></Button>
        <span className="text-sm font-medium w-36 text-center">{MONTHS_RO[month - 1]} {year}</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={nextMonth}><ChevronRight className="h-4 w-4" /></Button>
      </div>

      {effectiveTab === 'pontaje' && <HubPontajeContent year={year} month={month} />}
      {effectiveTab === 'bonuses' && <HubBonusesContent year={year} month={month} />}
      {effectiveTab === 'leave-permits' && <HubLeavePermitsContent userId={userId} year={year} month={month} />}
    </div>
  )
}

function HubPontajeContent({ year, month }: { year: number; month: number }) {
  const start = `${year}-${String(month).padStart(2, '0')}-01`
  const lastDay = new Date(year, month, 0).getDate()
  const end = `${year}-${String(month).padStart(2, '0')}-${lastDay}`

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'pontaje', start, end],
    queryFn: () => profileApi.getPontaje({ start, end }),
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />

  const history: BioStarDayHistory[] = data?.history ?? []
  if (history.length === 0) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">No punch data for this month.</CardContent></Card>
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Date</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">First In</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Last Out</th>
                <th className="text-right px-4 py-2 font-medium text-muted-foreground">Hours</th>
              </tr>
            </thead>
            <tbody>
              {history.map((d) => {
                const hours = d.duration_seconds != null ? d.duration_seconds / 3600 : null
                return (
                  <tr key={d.date} className="border-b last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2 whitespace-nowrap font-medium">
                      {new Date(d.date + 'T00:00').toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit', month: 'short' })}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">{d.first_punch || '—'}</td>
                    <td className="px-4 py-2 text-muted-foreground">{d.last_punch || '—'}</td>
                    <td className="px-4 py-2 text-right tabular-nums font-medium">{hours != null ? `${hours.toFixed(1)}h` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

function HubBonusesContent({ year, month }: { year: number; month: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'bonuses', year, month],
    queryFn: () => profileApi.getHrEvents({ year, month }),
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />

  const bonuses: ProfileBonus[] = data?.bonuses ?? []
  if (bonuses.length === 0) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">No bonuses for this month.</CardContent></Card>
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Type</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Details</th>
                <th className="text-right px-4 py-2 font-medium text-muted-foreground">Days</th>
              </tr>
            </thead>
            <tbody>
              {bonuses.map((b) => (
                <tr key={b.id} className="border-b last:border-0 hover:bg-muted/20">
                  <td className="px-4 py-2 font-medium">{b.event_name || '—'}</td>
                  <td className="px-4 py-2 text-muted-foreground truncate max-w-[250px]">{b.details || '—'}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{b.bonus_days ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

function HubLeavePermitsContent({ userId, year, month }: { userId: number; year: number; month: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'leave-permits', userId, year, month],
    queryFn: () => connecteamApi.getEmployeeSubmissions(userId, year, month),
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />

  const submissions: ConnecteamSubmission[] = data?.data ?? []
  if (submissions.length === 0) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">No leave permits for this month.</CardContent></Card>
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Date</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Start</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">End</th>
                <th className="text-right px-4 py-2 font-medium text-muted-foreground">Hours</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Reason</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Source</th>
              </tr>
            </thead>
            <tbody>
              {submissions.map((s) => (
                <tr key={`${s.source ?? 'ct'}-${s.id}`} className="border-b last:border-0 hover:bg-muted/20">
                  <td className="px-4 py-2 whitespace-nowrap font-medium">
                    {s.leave_date ? new Date(s.leave_date + 'T00:00').toLocaleDateString('ro-RO') : '—'}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">{s.leave_start_time?.slice(0, 5) || '—'}</td>
                  <td className="px-4 py-2 text-muted-foreground">{s.leave_end_time?.slice(0, 5) || '—'}</td>
                  <td className="px-4 py-2 text-right tabular-nums font-medium">{s.leave_hours != null ? `${s.leave_hours}h` : '—'}</td>
                  <td className="px-4 py-2 text-muted-foreground truncate max-w-[200px]">{s.leave_reason || '—'}</td>
                  <td className="px-4 py-2">
                    <span className={cn('text-xs px-1.5 py-0.5 rounded-full',
                      s.source === 'jarvis' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
                    )}>
                      {s.source === 'jarvis' ? 'JARVIS' : 'Connecteam'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Forms Panel ────────────────────────────────────────

function HubFormsPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'published-forms'],
    queryFn: () => fetch('/forms/api/forms/published', { credentials: 'include' }).then(r => r.json()),
  })
  const forms: { id: number; name: string; slug: string; description: string | null }[] = data?.forms ?? []

  if (isLoading) return <Skeleton className="h-48 w-full" />
  if (forms.length === 0) {
    return <Card><CardContent className="py-12 text-center text-muted-foreground text-sm">No forms available.</CardContent></Card>
  }

  // Map form slugs to distinct icon/color combos
  const formStyle = (slug: string) => {
    if (slug.includes('voucher')) return { icon: Ticket, bg: 'bg-amber-100 dark:bg-amber-900/30', fg: 'text-amber-700 dark:text-amber-400' }
    if (slug.includes('invoire') || slug.includes('leave')) return { icon: ClipboardList, bg: 'bg-blue-100 dark:bg-blue-900/30', fg: 'text-blue-700 dark:text-blue-400' }
    if (slug.includes('drive') || slug.includes('test')) return { icon: Car, bg: 'bg-violet-100 dark:bg-violet-900/30', fg: 'text-violet-700 dark:text-violet-400' }
    if (slug.includes('feedback') || slug.includes('survey')) return { icon: MessageSquare, bg: 'bg-pink-100 dark:bg-pink-900/30', fg: 'text-pink-700 dark:text-pink-400' }
    return { icon: FileCheck, bg: 'bg-emerald-100 dark:bg-emerald-900/30', fg: 'text-emerald-700 dark:text-emerald-400' }
  }

  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Available Forms</CardTitle></CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-6">
          {forms.map((form) => {
            const style = formStyle(form.slug)
            const Icon = style.icon
            return (
              <Link
                key={form.id}
                to={`/f/${form.slug}`}
                className="flex flex-col items-center gap-1.5 w-20 group"
              >
                <div className={cn('flex h-14 w-14 items-center justify-center rounded-xl shadow-sm transition-transform group-hover:scale-105 group-hover:shadow-md', style.bg, style.fg)}>
                  <Icon className="h-7 w-7" />
                </div>
                <p className="text-[11px] font-medium text-center leading-tight line-clamp-2">{form.name}</p>
              </Link>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Weekly Punch Card ──────────────────────────────────

function HubWeeklyPunchCard() {
  // Get Monday of current week
  const now = new Date()
  const dayOfWeek = now.getDay()
  const monday = new Date(now)
  monday.setDate(now.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)

  const start = monday.toISOString().slice(0, 10)
  const end = sunday.toISOString().slice(0, 10)

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'weekly-punch', start, end],
    queryFn: () => profileApi.getPontaje({ start, end }),
    staleTime: 5 * 60_000,
  })

  const history: BioStarDayHistory[] = data?.history ?? []
  if (isLoading) return <Skeleton className="h-32 w-full rounded-lg" />
  if (!data?.mapped) return null // No BioStar mapping

  const totalHours = history.reduce((sum, d) => sum + (d.duration_seconds ? d.duration_seconds / 3600 : 0), 0)
  const DAYS_RO = ['Lun', 'Mar', 'Mie', 'Joi', 'Vin', 'Sam', 'Dum']

  // Build a map of date → day data
  const dayMap = new Map(history.map(d => [d.date, d]))

  // Generate all 7 days of the week
  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(monday)
    date.setDate(monday.getDate() + i)
    const dateStr = date.toISOString().slice(0, 10)
    const dayData = dayMap.get(dateStr)
    const hours = dayData?.duration_seconds ? dayData.duration_seconds / 3600 : 0
    const isToday = dateStr === now.toISOString().slice(0, 10)
    const isFuture = date > now
    const punchIn = dayData?.first_punch?.slice(0, 5) || null
    const punchOut = dayData?.last_punch?.slice(0, 5) || null
    return { dateStr, label: DAYS_RO[i], day: date.getDate(), hours, isToday, isFuture, hasData: !!dayData, punchIn, punchOut }
  })

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Clock className="h-4 w-4" />
            This Week
          </CardTitle>
          <span className="text-xs font-semibold tabular-nums">{totalHours.toFixed(1)}h</span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex justify-between gap-1">
          {weekDays.map((d) => (
            <div key={d.dateStr} className="flex flex-col items-center gap-1 flex-1">
              <span className="text-[10px] text-muted-foreground">{d.label}</span>
              <div className={cn(
                'w-full rounded-md flex flex-col items-center justify-center py-2 gap-0.5',
                d.isToday ? 'ring-2 ring-primary ring-offset-1' : '',
                d.isFuture ? 'bg-muted/30 text-muted-foreground/50' :
                d.hours >= 8 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                d.hours > 0 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
                d.hasData ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                'bg-muted/50 text-muted-foreground',
              )}>
                {!d.isFuture && d.punchIn && <span className="text-[8px] opacity-70">{d.punchIn}</span>}
                <span className="text-[11px] font-semibold">
                  {d.isFuture ? '' : d.hours > 0 ? `${d.hours.toFixed(1)}` : d.hasData ? '0' : '-'}
                </span>
                {!d.isFuture && d.punchOut && <span className="text-[8px] opacity-70">{d.punchOut}</span>}
              </div>
              <span className={cn('text-[9px]', d.isToday ? 'font-bold' : 'text-muted-foreground')}>{d.day}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ─── HR Summary Card ────────────────────────────────────

function HubHrSummaryCard() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const { data: tsData, isLoading } = useQuery({
    queryKey: ['hub', 'sincron-timesheet', year, month],
    queryFn: () => profileApi.getSincronTimesheet({ year, month }),
    staleTime: 5 * 60_000,
  })

  const summary = tsData?.data?.summary ?? []
  const employee = tsData?.data?.employee

  if (isLoading) return <Skeleton className="h-24 w-full" />
  if (!employee && summary.length === 0) return null

  // Activity code colors
  const codeColors: Record<string, string> = {
    OZ: 'text-green-600', CES: 'text-blue-600', CFS: 'text-blue-500',
    CIC: 'text-purple-600', CM: 'text-red-600', CMS: 'text-red-500',
    CO: 'text-amber-600', DLG: 'text-orange-600', OSW: 'text-cyan-600',
    X: 'text-gray-500', ZLS: 'text-pink-600',
  }

  const totalEntry = summary.reduce((sum, s) => sum + (s.unit === 'hours' ? s.total_value : 0), 0)

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1) }
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1) }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">Timesheet</CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={prevMonth}><ChevronLeft className="h-3.5 w-3.5" /></Button>
            <span className="text-xs font-medium w-28 text-center">{MONTHS_RO[month - 1]} {year}</span>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={nextMonth}><ChevronRight className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/30">
                {summary.map((s) => (
                  <th key={s.short_code} className={cn('px-2.5 py-1.5 font-medium text-center whitespace-nowrap', codeColors[s.short_code] || 'text-muted-foreground')}>
                    {s.short_code}
                  </th>
                ))}
                <th className="px-2.5 py-1.5 font-semibold text-right whitespace-nowrap">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                {summary.map((s) => (
                  <td key={s.short_code} className="px-2.5 py-2 text-center tabular-nums font-medium">
                    {s.total_value > 0 ? (s.unit === 'hours' ? `${s.total_value}` : s.day_count > 0 ? s.day_count : '—') : '—'}
                  </td>
                ))}
                <td className="px-2.5 py-2 text-right tabular-nums font-semibold">{totalEntry > 0 ? `${totalEntry}h` : '—'}</td>
              </tr>
              {/* Days row */}
              <tr className="border-t">
                {summary.map((s) => (
                  <td key={`d-${s.short_code}`} className="px-2.5 py-1 text-center text-[10px] text-muted-foreground">
                    {s.day_count > 0 ? `${s.day_count}d` : ''}
                  </td>
                ))}
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Marketing Events & Bonuses Card ────────────────────

function HubBonusCard() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'bonuses-card', year],
    queryFn: () => profileApi.getHrEvents({ year, per_page: 50 }),
    staleTime: 5 * 60_000,
  })

  const bonuses: ProfileBonus[] = data?.bonuses ?? []

  if (isLoading) return <Skeleton className="h-24 w-full" />
  if (bonuses.length === 0 && year === now.getFullYear()) return null

  const prevYear = () => setYear(y => y - 1)
  const nextYear = () => setYear(y => y + 1)

  const totalBonusDays = bonuses.reduce((sum, b) => sum + (b.bonus_days ?? 0), 0)
  const totalHoursFree = bonuses.reduce((sum, b) => sum + (b.hours_free ?? 0), 0)
  const totalBonusNet = bonuses.reduce((sum, b) => sum + (b.bonus_net ? Number(b.bonus_net) : 0), 0)

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Award className="h-4 w-4" />
            Marketing Events & Bonuses
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={prevYear}><ChevronLeft className="h-3.5 w-3.5" /></Button>
            <span className="text-xs font-medium w-12 text-center">{year}</span>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={nextYear}><ChevronRight className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {bonuses.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6">No event bonuses for {year}.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="text-left px-3 py-1.5 font-medium text-muted-foreground">Event</th>
                    <th className="text-left px-3 py-1.5 font-medium text-muted-foreground">Period</th>
                    <th className="text-right px-3 py-1.5 font-medium text-muted-foreground">Days</th>
                    <th className="text-right px-3 py-1.5 font-medium text-muted-foreground">Hours</th>
                    <th className="text-right px-3 py-1.5 font-medium text-muted-foreground">Bonus</th>
                  </tr>
                </thead>
                <tbody>
                  {bonuses.map((b) => {
                    const startStr = b.participation_start || b.start_date
                    const endStr = b.participation_end || b.end_date
                    const fmtDate = (d: string | null) => d ? new Date(d + 'T00:00').toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' }) : ''
                    return (
                      <tr key={b.id} className="border-b last:border-0 hover:bg-muted/20">
                        <td className="px-3 py-2">
                          <div className="font-medium">{b.event_name}</div>
                          {b.brand && <div className="text-[10px] text-muted-foreground">{b.brand}</div>}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">
                          {startStr && endStr ? `${fmtDate(startStr)} – ${fmtDate(endStr)}` : fmtDate(startStr) || '—'}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums font-medium">{b.bonus_days ?? '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{b.hours_free ?? '—'}</td>
                        <td className="px-3 py-2 text-right tabular-nums font-medium">
                          {b.bonus_net ? `${Number(b.bonus_net).toLocaleString('ro-RO')} RON` : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {/* Totals row */}
            <div className="flex items-center justify-end gap-4 px-3 py-2 border-t bg-muted/20 text-xs">
              {totalBonusDays > 0 && <span className="tabular-nums font-medium">{totalBonusDays} days</span>}
              {totalHoursFree > 0 && <span className="tabular-nums">{totalHoursFree}h free</span>}
              {totalBonusNet > 0 && <span className="tabular-nums font-semibold">{totalBonusNet.toLocaleString('ro-RO')} RON</span>}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
