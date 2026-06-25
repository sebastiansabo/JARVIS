import { useState, useMemo, useCallback, lazy, Suspense } from 'react'
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
  Fingerprint,
  Gift,
  ClipboardList,
  Car,
  MessageSquare,
  Pencil,
  Ticket as TicketIcon,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuthStore } from '@/stores/authStore'
import { profileApi } from '@/api/profile'
import { checkinApi } from '@/api/checkin'
import { notificationsApi } from '@/api/notifications'
import { connecteamApi, type ConnecteamSubmission } from '@/api/connecteam'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { InAppNotification } from '@/types/notifications'
import type { ProfileInvoice, ProfileBonus } from '@/types/profile'
import type { BioStarDayHistory } from '@/types/biostar'

const VouchersPanel = lazy(() => import('@/pages/Profile/VouchersPanel'))

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

// ─── Command Hub ────────────────────────────────────────

export default function Hub() {
  const authUser = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

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

  const hasVouchersPerm = !authUser?.permissions || (authUser.permissions['vouchers.profile.view'] ?? true)
  const visibleTiles = useMemo(() => {
    return appTiles.filter((t) => {
      if (t.key === 'vouchers' && !hasVouchersPerm) return false
      return true
    })
  }, [hasVouchersPerm])

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
              <h1 className="text-lg font-bold leading-tight">Command Hub</h1>
            </div>

            {/* Right: company, role, actions */}
            <div className="ml-auto flex items-center gap-2">
              {user?.company && (
                <span className="text-xs text-muted-foreground hidden sm:inline">{user.company}</span>
              )}
              {authUser?.role_name && (
                <Badge variant="outline" className="text-xs">{authUser.role_name}</Badge>
              )}

              {/* Check In/Out */}
              {checkinStatus?.mapped && (
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
              )}

              <Button size="sm" variant="outline" onClick={() => navigate('/app/profile')}>
                <TicketIcon className="h-3.5 w-3.5 mr-1.5" />Ticket
              </Button>
              <Button size="sm" variant="outline" onClick={() => navigate('/app/profile')}>
                <Pencil className="h-3.5 w-3.5 mr-1.5" />Edit profile
              </Button>
            </div>
          </div>
        </div>
      )}

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

          </div>

          {/* Right 1/3 — Notifications */}
          <div>
            <Card className="sticky top-6">
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
              <CardContent className="space-y-1 max-h-[60vh] overflow-y-auto">
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
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Invoices Panel ─────────────────────────────────────

function HubInvoicesPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'invoices'],
    queryFn: () => profileApi.getInvoices({ per_page: 50 }),
  })
  const invoices: ProfileInvoice[] = data?.invoices ?? []

  if (isLoading) return <Skeleton className="h-64 w-full" />
  if (invoices.length === 0) {
    return <Card><CardContent className="py-12 text-center text-muted-foreground text-sm">No invoices assigned to you.</CardContent></Card>
  }

  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">My Invoices ({invoices.length})</CardTitle></CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Supplier</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Invoice #</th>
                <th className="text-right px-4 py-2 font-medium text-muted-foreground">Amount</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Date</th>
                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id} className="border-b last:border-0 hover:bg-muted/20">
                  <td className="px-4 py-2.5 font-medium truncate max-w-[200px]">{inv.supplier || '—'}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{inv.invoice_number || '—'}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums font-medium">
                    {inv.invoice_value != null ? `${Number(inv.invoice_value).toLocaleString('ro-RO', { minimumFractionDigits: 2 })} ${inv.currency || 'RON'}` : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">
                    {inv.invoice_date ? new Date(inv.invoice_date).toLocaleDateString('ro-RO') : '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={cn('inline-block text-xs px-2 py-0.5 rounded-full',
                      inv.status === 'allocated' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                      inv.status === 'pending' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                      'bg-muted text-muted-foreground',
                    )}>
                      {inv.status || 'new'}
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

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1) }
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1) }

  return (
    <div className="space-y-4">
      <Tabs value={subTab} onValueChange={(v) => setSubTab(v as HrSubTab)}>
        <TabsList className="h-8 bg-muted/50">
          <TabsTrigger value="pontaje" className="text-xs h-7 px-2.5 gap-1"><Fingerprint className="h-3.5 w-3.5" />Pontaje</TabsTrigger>
          <TabsTrigger value="bonuses" className="text-xs h-7 px-2.5 gap-1"><Gift className="h-3.5 w-3.5" />Bonuses</TabsTrigger>
          <TabsTrigger value="leave-permits" className="text-xs h-7 px-2.5 gap-1"><ClipboardList className="h-3.5 w-3.5" />Leave Permits</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={prevMonth}><ChevronLeft className="h-4 w-4" /></Button>
        <span className="text-sm font-medium w-36 text-center">{MONTHS_RO[month - 1]} {year}</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={nextMonth}><ChevronRight className="h-4 w-4" /></Button>
      </div>

      {subTab === 'pontaje' && <HubPontajeContent year={year} month={month} />}
      {subTab === 'bonuses' && <HubBonusesContent year={year} month={month} />}
      {subTab === 'leave-permits' && <HubLeavePermitsContent userId={userId} year={year} month={month} />}
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
