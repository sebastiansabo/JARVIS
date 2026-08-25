import React, { useState, useMemo, useCallback, lazy, Suspense } from 'react'
import { HubHeaderSlotContext } from '@/pages/Hub/hubHeaderSlot'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FileText,
  Activity,
  Ticket,
  Bell,
  FileCheck,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Fingerprint,
  Gift,
  ClipboardList,
  Plus,
  Car,
  MessageSquare,
  Clock,
  Award,
  Home,
  Eye,
  ExternalLink,
  SlidersHorizontal,
  Pencil,
  LogIn,
  LogOut,
  Check,
  ScanLine,
  Users,
  Target,
  FileSpreadsheet,
  MapPin,
  Loader2,
  KeyRound,
} from 'lucide-react'
import { SincronTimesheetView } from '@/components/shared/SincronTimesheetView'
import { MarqueeWidget } from '@/components/happy/MarqueeWidget'
import { OpenAcksCard } from '@/components/happy/OpenAcksCard'
import { PraiseCard } from '@/components/happy/PraiseCard'
import { PulseCard } from '@/components/happy/PulseCard'
import { PunchCard } from '@/components/shared/PunchCard'
import { InvoireForm } from '@/components/forms/InvoireForm'
import { CancelLeaveDialog } from '@/pages/Hub/CancelLeaveDialog'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
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
import { InvoicePreviewModal } from '@/pages/Profile/InvoicePreviewModal'
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
import type { BioStarDayHistory, BioStarRangeSummary } from '@/types/biostar'

import { useVoucherSchema } from '@/hooks/useVoucherSchema'
import { api } from '@/api/client'

const VouchersPanel = lazy(() => import('@/pages/Profile/VouchersPanel'))
const CreateTicketDialog = lazy(() => import('@/pages/Ticketing/CreateTicketDialog'))
const EditProfileDialogLazy = lazy(() => import('@/pages/Profile/index').then(m => ({ default: m.EditProfileDialog })))
const FormRendererLazy = lazy(() => import('@/components/forms/FormRenderer').then(m => ({ default: m.FormRenderer })))
const Digest = lazy(() => import('@/pages/Digest'))
const VoucherRedeem = lazy(() => import('@/pages/Public/VoucherRedeem'))
const HubDrivingPanel = lazy(() => import('@/pages/Hub/HubDrivingPanel'))
const HubFieldSalesPanel = lazy(() => import('@/pages/Hub/HubFieldSalesPanel'))

const VOUCHER_FORM_SLUG = 'voucher-issuance'

// ─── Types ──────────────────────────────────────────────

type ActiveModule = null | 'invoices' | 'hr' | 'vouchers' | 'forms' | 'chat' | 'approvals' | 'driving' | 'courtesy' | 'field_sales'
type HrSubTab = 'pontaje' | 'team-pontaje' | 'bonuses' | 'leave-permits' | 'sincron'

// Labels for the HR sub-sections — used both by the tile grid and the breadcrumb.
const HR_SECTION_LABELS: Record<HrSubTab, string> = {
  pontaje: 'Pontaje',
  'team-pontaje': 'Team Pontaje',
  bonuses: 'Bonusuri',
  'leave-permits': 'Învoiri',
  sincron: 'Sincron',
}

interface AppTile {
  key: NonNullable<ActiveModule>
  label: string
  icon: React.ElementType
  bg: string
  fg: string
  /** When set, the tile navigates to a route instead of opening an in-page panel. */
  route?: string
}

export const appTiles: (AppTile & { shortLabel?: string })[] = [
  { key: 'invoices', label: 'My Invoices', shortLabel: 'Invoices', icon: FileText, bg: 'bg-blue-600', fg: 'text-white' },
  { key: 'approvals', label: 'Approvals', icon: FileCheck, bg: 'bg-orange-600', fg: 'text-white' },
  { key: 'hr', label: 'HR', icon: Activity, bg: 'bg-emerald-600', fg: 'text-white' },
  { key: 'vouchers', label: 'Vouchers', icon: Ticket, bg: 'bg-amber-500', fg: 'text-white' },
  { key: 'chat', label: 'Chat', shortLabel: 'Chat', icon: MessageSquare, bg: 'bg-pink-600', fg: 'text-white' },
  { key: 'driving', label: 'Driving Sessions', shortLabel: 'Driving', icon: Car, bg: 'bg-teal-600', fg: 'text-white' },
  { key: 'courtesy', label: 'Mașini de curtoazie', shortLabel: 'Curtoazie', icon: KeyRound, bg: 'bg-indigo-600', fg: 'text-white' },
  { key: 'field_sales', label: 'Field Sales', shortLabel: 'Teren', icon: MapPin, bg: 'bg-teal-600', fg: 'text-white' },
]

const MONTHS_RO = ['Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie', 'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']

// ─── JARVIS Hub ────────────────────────────────────────

export default function Hub() {
  const authUser = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [ticketOpen, setTicketOpen] = useState(false)
  const [editProfileOpen, setEditProfileOpen] = useState(false)
  // DOM node in the breadcrumb into which the active module can portal its inline
  // toolbar (see HubHeaderSlotContext / HubCrumb actionRef).
  const [headerSlot, setHeaderSlot] = useState<HTMLElement | null>(null)
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

  const isCheckedIn = checkinStatus?.next_direction === 'OUT'
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
  const { data: approvalsCountData } = useQuery({
    queryKey: ['hub', 'approvals-count'],
    queryFn: () => fetch('/approvals/api/my-queue/count', { credentials: 'include' }).then(r => r.ok ? r.json() : { count: 0 }),
    refetchInterval: 30_000,
  })

  const tileCounts: Record<string, number> = {
    invoices: invoicesData?.total ?? -1,
    approvals: approvalsCountData?.count ?? -1, // show count badge but always visible
    hr: -1, // always show — sub-tabs auto-hide when empty
    vouchers: Array.isArray(vouchersData) ? vouchersData.length : -1,
    forms: (formsCountData?.forms ?? []).length || -1,
    driving: -1, // always show when allowed
    courtesy: -1, // always show when allowed (same gate as driving)
    field_sales: -1, // always show when allowed
  }

  const hasVouchersPerm = !authUser?.permissions || (authUser.permissions['vouchers.profile.view'] ?? true)
  const visibleTiles = useMemo(() => {
    return appTiles.filter((t) => {
      if (t.key === 'vouchers' && !hasVouchersPerm) return false
      if (t.key === 'driving' && !authUser?.can_access_carpark) return false
      if (t.key === 'courtesy' && !authUser?.can_access_carpark) return false
      if (t.key === 'field_sales' && !authUser?.can_access_field_sales) return false
      // Vouchers stays visible even at 0 (permission-gated above) — like approvals;
      // other tiles auto-hide when empty.
      if (t.key !== 'approvals' && t.key !== 'vouchers' && tileCounts[t.key] === 0) return false
      return true
    })
  }, [hasVouchersPerm, tileCounts, authUser?.can_access_carpark, authUser?.can_access_field_sales])

  return (
    <div className="space-y-6 pb-16 sm:pb-0">
      {/* Header — hidden on mobile (sidebar handles identity) */}
      <div className="hidden sm:block">
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
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
                {user?.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase() || '?'}
              </div>
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground truncate">{user?.name || 'Loading...'}</p>
                <h1 className="text-lg font-bold leading-tight">JARVIS Hub</h1>
              </div>
              <div className="ml-auto flex items-center gap-2">
                {user?.company && (
                  <span className="text-xs text-muted-foreground">{user.company}</span>
                )}
                {authUser?.role_name && (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">{authUser.role_name}</Badge>
                )}
                {checkinStatus?.mapped && (
                  <div className="flex items-center gap-2">
                    {lastPunch && (
                      <div className="text-xs text-right leading-tight hidden sm:block">
                        <p className="font-medium">
                          {lastPunch.direction === 'IN' ? 'In' : 'Out'} at{' '}
                          {new Date(lastPunch.event_datetime).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })}
                        </p>
                      </div>
                    )}
                    <Button
                      size="sm"
                      className={cn(
                        'shrink-0 font-semibold text-white',
                        isCheckedIn
                          ? 'bg-red-600 hover:bg-red-700'
                          : 'bg-green-600 hover:bg-green-700',
                      )}
                      onClick={() => punchMut.mutate()}
                      disabled={punchMut.isPending}
                    >
                      {isCheckedIn ? <LogOut className="h-3.5 w-3.5 mr-1.5" /> : <LogIn className="h-3.5 w-3.5 mr-1.5" />}
                      {punchMut.isPending ? '...' : isCheckedIn ? 'Check Out' : 'Check In'}
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Ticket Dialog */}
      <Suspense fallback={null}>
        <CreateTicketDialog open={ticketOpen} onOpenChange={setTicketOpen} />
      </Suspense>

      {/* Edit Profile Dialog */}
      {editProfileOpen && user && (
        <Suspense fallback={null}>
          <EditProfileDialogLazy
            open={editProfileOpen}
            onOpenChange={setEditProfileOpen}
            user={user}
            onSaved={() => queryClient.invalidateQueries({ queryKey: ['profile', 'summary'] })}
          />
        </Suspense>
      )}

      {/* ── Active Module (inline content) ── */}
      {activeModule !== null ? (
        <HubHeaderSlotContext.Provider value={headerSlot}>
        <div className={cn('space-y-4', activeModule === 'chat' ? 'pb-0' : 'pb-20')}>
          {/* Breadcrumb nav — shown for every module (Digest/Connecteams runs
              readOnly here, so it has no header of its own). For HR we append the
              open sub-section (read from `hrtab`) so it reads Hub › HR › Pontaje. */}
          {(() => {
            const moduleLabel = visibleTiles.find(t => t.key === activeModule)?.label || 'Section'
            const hrtab = activeModule === 'hr' ? (searchParams.get('hrtab') as HrSubTab | null) : null
            const clearHrtab = () => setSearchParams((prev) => { const p = new URLSearchParams(prev); p.delete('hrtab'); return p }, { replace: true })
            const trail: { label: string; onClick?: () => void }[] = [
              { label: 'Hub', onClick: () => setActiveModule(null) },
              { label: moduleLabel, onClick: hrtab ? clearHrtab : undefined },
            ]
            if (hrtab && HR_SECTION_LABELS[hrtab]) trail.push({ label: HR_SECTION_LABELS[hrtab] })
            // On the Învoiri sub-section, surface the "+ Învoire" action inline in
            // the breadcrumb. It opens the form via a URL flag so the modal can
            // stay co-located with the list panel that refetches on submit.
            const action = hrtab === 'leave-permits' ? (
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => setSearchParams((prev) => { const p = new URLSearchParams(prev); p.set('newinvoire', '1'); return p })}
              >
                <Plus className="h-4 w-4" /> Învoire
              </Button>
            ) : undefined
            return (
              <HubCrumb
                trail={trail}
                onBack={hrtab ? clearHrtab : () => setActiveModule(null)}
                count={hrtab ? undefined : tileCounts[activeModule]}
                action={action}
                actionRef={setHeaderSlot}
              />
            )
          })()}

          {activeModule === 'invoices' && <HubInvoicesPanel />}
          {activeModule === 'approvals' && <HubApprovalsPanel />}
          {activeModule === 'hr' && user && <HubHrPanel userId={user.id} />}
          {activeModule === 'forms' && <HubFormsPanel />}
          {activeModule === 'vouchers' && (
            <Suspense fallback={<div className="py-8 text-center text-muted-foreground text-sm">Loading...</div>}>
              <VouchersPanel />
            </Suspense>
          )}
          {activeModule === 'chat' && (
            <Suspense fallback={<div className="py-8 text-center text-muted-foreground text-sm">Loading...</div>}>
              <Digest readOnly />
            </Suspense>
          )}
          {activeModule === 'driving' && (
            <Suspense fallback={<div className="py-8 text-center text-muted-foreground text-sm">Loading...</div>}>
              <HubDrivingPanel onBack={() => setActiveModule(null)} />
            </Suspense>
          )}
          {activeModule === 'courtesy' && (
            <Suspense fallback={<div className="py-8 text-center text-muted-foreground text-sm">Loading...</div>}>
              <HubDrivingPanel documentType="service" onBack={() => setActiveModule(null)} />
            </Suspense>
          )}
          {activeModule === 'field_sales' && (
            <Suspense fallback={<div className="py-8 text-center text-muted-foreground text-sm">Loading...</div>}>
              <HubFieldSalesPanel />
            </Suspense>
          )}

        </div>
        </HubHeaderSlotContext.Provider>
      ) : (
        /* ── Grid: 2/3 apps + 1/3 notifications ── */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          {/* Left 2/3 */}
          <div className="lg:col-span-2 space-y-6">
            <HubAppsCard tiles={visibleTiles} onSelect={setActiveModule} />

            {/* Marketing Events & Bonuses Card */}
            <HubBonusCard />
          </div>

          {/* Right 1/3 — Notifications + Punch Card */}
          <div className="space-y-6">
            <MarqueeWidget enabled placement="hub_card" route="/app/hub" />
            <OpenAcksCard />
            <PraiseCard />
            <PulseCard />
            <div className="px-1">
              <button
                type="button"
                onClick={() => navigate('/app/happy/transparenta')}
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Cum funcționează Happy
              </button>
            </div>
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
                      if (n.link) {
                        const linkToModule: Record<string, NonNullable<ActiveModule>> = {
                          '/app/forms': 'forms',
                          '/app/accounting': 'invoices',
                          '/app/vouchers': 'vouchers',
                          '/app/hr': 'hr',
                          '/app/chat': 'chat',
                          '/app/approvals': 'approvals',
                        }
                        const link = n.link!
                        const mod = linkToModule[link] || Object.entries(linkToModule).find(([prefix]) => link.startsWith(prefix))?.[1]
                        if (mod) { setActiveModule(mod) } else { navigate(link) }
                      }
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

            {/* Work Summary Card */}
            <HubWorkSummaryCard />

            {/* Weekly Punch Card */}
            <HubWeeklyPunchCard />
          </div>
        </div>
      )}

      {/* ── Bottom Tab Bar (mobile only, Instagram floating pill) ──
          Suppressed while the Driving module is open: that panel renders its own
          bottom pill, and its Back returns to the Hub grid (restoring this bar). */}
      {activeModule !== 'driving' && activeModule !== 'courtesy' && activeModule !== 'chat' && (
      <div className="fixed bottom-0 inset-x-0 z-40 sm:hidden pb-[env(safe-area-inset-bottom)]">
        <div className="mx-4 mb-2 bg-zinc-900 dark:bg-zinc-800 rounded-[22px] shadow-lg">
          <div className="flex items-center justify-around h-[52px] px-1">
            <button
              type="button"
              onClick={() => setActiveModule(null)}
              className={cn('flex items-center justify-center h-9 rounded-full transition-all',
                activeModule === null
                  ? 'bg-zinc-700 dark:bg-zinc-600 text-white px-4 gap-1.5'
                  : 'text-zinc-400 w-9'
              )}
            >
              <Home className="h-[20px] w-[20px] shrink-0" />
              {activeModule === null && <span className="text-[11px] font-semibold">Hub</span>}
            </button>
            {visibleTiles.map((tile) => {
              const Icon = tile.icon
              const isActive = activeModule === tile.key
              return (
                <button
                  key={tile.key}
                  type="button"
                  onClick={() => setActiveModule(tile.key)}
                  className={cn('flex items-center justify-center h-9 rounded-full transition-all',
                    isActive
                      ? 'bg-zinc-700 dark:bg-zinc-600 text-white px-4 gap-1.5'
                      : 'text-zinc-400 w-9'
                  )}
                >
                  <Icon className="h-[20px] w-[20px] shrink-0" />
                  {isActive && <span className="text-[11px] font-semibold">{tile.shortLabel || tile.label}</span>}
                </button>
              )
            })}
          </div>
        </div>
      </div>
      )}
    </div>
  )
}

// ─── Apps Card (max 6, expandable) ──────────────────────

function HubAppsCard({ tiles, onSelect }: { tiles: AppTile[]; onSelect: (key: NonNullable<ActiveModule>) => void }) {
  const [showAll, setShowAll] = useState(false)
  const limit = 8
  const hasMore = tiles.length > limit
  const displayed = showAll ? tiles : tiles.slice(0, limit)

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground">Apps</CardTitle>
          {hasMore && (
            <button
              type="button"
              onClick={() => setShowAll(s => !s)}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
            >
              {showAll ? 'Show less' : `All (${tiles.length})`}
              <ChevronRight className={cn('h-3 w-3 transition-transform', showAll && 'rotate-90')} />
            </button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-6">
          {displayed.map((tile) => {
            const Icon = tile.icon
            return (
              <button
                key={tile.key}
                type="button"
                onClick={() => onSelect(tile.key)}
                className="flex flex-col items-center gap-2 w-20 group"
              >
                <div className={cn('flex h-16 w-16 sm:h-14 sm:w-14 items-center justify-center rounded-xl shadow-sm transition-transform group-hover:scale-105 group-hover:shadow-md', tile.bg, tile.fg)}>
                  <Icon className="h-8 w-8 sm:h-7 sm:w-7" />
                </div>
                <p className="text-[11px] font-medium text-center leading-tight">{tile.label}</p>
              </button>
            )
          })}
        </div>
      </CardContent>
    </Card>
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
  const [previewId, setPreviewId] = useState<number | null>(null)

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
      <CardHeader className="max-sm:px-3 max-sm:py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base sm:text-base">Invoices</CardTitle>
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
            <span className="text-xs text-muted-foreground">{total}</span>
          </div>
          <Button variant="ghost" size="icon" className={cn('h-8 w-8 shrink-0', showFilters && 'bg-muted')} onClick={() => setShowFilters(s => !s)}>
            <SlidersHorizontal className="h-4 w-4" />
          </Button>
        </div>
        {showFilters && (
          <div className="flex flex-col gap-2 pt-2">
            <SearchInput
              placeholder="Search invoices..."
              value={search}
              onChange={(v) => { setSearch(v); setPage(1) }}
              className="w-full"
            />
            <div className="flex flex-wrap items-center gap-2">
              <FilterBar fields={filterFields} values={filterValues} onChange={handleFilterChange} iconOnly={isMobile} />
              <DateField
                mode="range"
                startDate={startDate}
                endDate={endDate}
                onRangeChange={(s, e) => { setStartDate(s); setEndDate(e); setPage(1) }}
              />
            </div>
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
                  <div className="flex items-center gap-2">
                    {inv.drive_link.startsWith('/efactura/') && (
                      <button
                        onClick={() => setPreviewId(inv.id)}
                        className="text-muted-foreground hover:text-foreground"
                        title="Previzualizare factură"
                      >
                        <Eye className="h-3.5 w-3.5" />
                      </button>
                    )}
                    <button
                      onClick={() => handleDownloadPdf(inv)}
                      className="text-muted-foreground hover:text-foreground"
                      title="Descarcă PDF"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </button>
                  </div>
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
                                <div className="flex items-center gap-2">
                                  {inv.drive_link.startsWith('/efactura/') && (
                                    <button
                                      onClick={() => setPreviewId(inv.id)}
                                      className="text-muted-foreground hover:text-foreground"
                                      title="Previzualizare factură"
                                    >
                                      <Eye className="h-3.5 w-3.5" />
                                    </button>
                                  )}
                                  <button
                                    onClick={() => handleDownloadPdf(inv)}
                                    className="text-muted-foreground hover:text-foreground"
                                    title="Descarcă PDF"
                                  >
                                    <ExternalLink className="h-3.5 w-3.5" />
                                  </button>
                                </div>
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

      {previewId !== null && (
        <InvoicePreviewModal invoiceId={previewId} source="profile" onClose={() => setPreviewId(null)} />
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

// ─── Breadcrumb ─────────────────────────────────────────
// Shared Hub breadcrumb: inline back chevron + a clickable trail. The last
// crumb is the current location (bold, non-clickable). Used by every module
// panel so navigation is consistent across the Hub.
function HubCrumb({ trail, onBack, count, action, actionRef }: {
  trail: { label: string; onClick?: () => void }[]
  onBack: () => void
  count?: number
  action?: React.ReactNode
  /** Ref callback for the inline toolbar slot — an active module portals its own
   *  controls here so they sit on the title row (see HubHeaderSlotContext). */
  actionRef?: (el: HTMLDivElement | null) => void
}) {
  // iOS nav-bar style: a single large "‹ <previous>" back button (the crumb
  // onBack returns to) + the current page as a bold title. Bigger tap target
  // than the old inline chevron, and clearer on mobile.
  const title = trail[trail.length - 1]?.label ?? ''
  const backLabel = trail.length >= 2 ? trail[trail.length - 2].label : 'Hub'
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        onClick={onBack}
        aria-label="Înapoi"
        className="-ml-1.5 flex h-11 shrink-0 items-center gap-0.5 rounded-lg pl-1.5 pr-2.5 text-[15px] font-medium text-primary transition-colors hover:bg-accent active:scale-95"
      >
        <ChevronLeft className="h-5 w-5" />
        {backLabel}
      </button>
      <div className="flex min-w-0 flex-1 items-center gap-1.5">
        <h2 className="truncate text-lg font-semibold leading-tight">{title}</h2>
        {count != null && count > 0 && <span className="shrink-0 text-sm font-normal text-muted-foreground">({count})</span>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
      {/* Toolbar slot — a module portals its controls here so they sit INLINE on
          the title row (wraps below only when the row can't fit on a narrow
          screen). Hidden until something is portaled in. */}
      <div ref={actionRef} className="ml-auto flex flex-wrap items-center justify-end gap-2 empty:hidden" />
    </div>
  )
}

// ─── HR Panel ───────────────────────────────────────────

function HubHrPanel({ userId }: { userId: number }) {
  const navigate = useNavigate()
  const [sp, setSp] = useSearchParams()
  const section = sp.get('hrtab') as HrSubTab | null
  const openSection = (tab: HrSubTab | null) =>
    setSp((prev) => { const p = new URLSearchParams(prev); if (tab) { p.set('hrtab', tab) } else { p.delete('hrtab') } return p }, { replace: true })
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
  // Team pontaje — only returns data if the user is an organigram responsable (is_manager)
  const { data: teamData } = useQuery({
    queryKey: ['hub', 'team-pontaje', start, end],
    queryFn: () => profileApi.getTeamPontaje({ mode: 'range', start, end }),
  })
  const pontajeCount = (pontajeData?.history ?? []).length
  const teamCount = teamData?.is_manager ? (teamData?.summary?.length ?? 0) : 0
  const bonusesCount = (bonusesData?.bonuses ?? []).length
  const lpCount = (lpData?.data ?? []).length

  const dataTiles = useMemo(() => {
    // Per-employee sections are always shown as tiles (empty state inside if no data
    // that month). Team Pontaje is manager-only, so it stays data-gated.
    const t: { key: HrSubTab; label: string; icon: React.ElementType; bg: string; count: number }[] = [
      { key: 'pontaje', label: 'Pontaje', icon: Fingerprint, bg: 'bg-blue-600', count: pontajeCount },
      { key: 'sincron', label: 'Sincron', icon: FileSpreadsheet, bg: 'bg-cyan-600', count: 0 },
      { key: 'bonuses', label: 'Bonusuri', icon: Gift, bg: 'bg-amber-500', count: bonusesCount },
      { key: 'leave-permits', label: 'Învoiri', icon: ClipboardList, bg: 'bg-rose-600', count: lpCount },
    ]
    if (teamCount > 0) t.push({ key: 'team-pontaje', label: 'Team Pontaje', icon: Users, bg: 'bg-teal-600', count: teamCount })
    return t
  }, [pontajeCount, teamCount, bonusesCount, lpCount])

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1) }
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1) }
  const monthNav = (
    <div className="flex items-center gap-2">
      <Button variant="ghost" size="icon" className="h-11 w-11" onClick={prevMonth}><ChevronLeft className="h-5 w-5" /></Button>
      <span className="text-sm font-medium flex-1 text-center">{MONTHS_RO[month - 1]} {year}</span>
      <Button variant="ghost" size="icon" className="h-11 w-11" onClick={nextMonth}><ChevronRight className="h-5 w-5" /></Button>
    </div>
  )

  // ── Section view (a data tile was opened) ──
  const activeSection = dataTiles.find(t => t.key === section) ? section : null
  if (activeSection) {
    return (
      <div className="space-y-4">
        {/* Back navigation is provided by the Hub breadcrumb above this panel. */}
        {activeSection === 'pontaje' && <PunchCard />}
        {monthNav}
        {activeSection === 'pontaje' && <HubPontajeContent year={year} month={month} />}
        {activeSection === 'sincron' && <SincronTimesheetView year={year} month={month} />}
        {activeSection === 'team-pontaje' && <HubTeamPontajeContent year={year} month={month} />}
        {activeSection === 'bonuses' && <HubBonusesContent year={year} month={month} />}
        {activeSection === 'leave-permits' && <HubLeavePermitsContent userId={userId} year={year} month={month} />}
      </div>
    )
  }

  // ── Grid landing (app-like tiles) — no month nav here; months live inside sections ──
  return (
    <div className="flex flex-wrap gap-6">
      {dataTiles.map((t) => (
        <HrTile key={t.key} label={t.label} icon={t.icon} bg={t.bg} count={t.count} onClick={() => openSection(t.key)} />
      ))}
      {/* Company-wide 360 — always available */}
      <HrTile label="Evaluări 360" icon={Target} bg="bg-indigo-600" onClick={() => navigate('/app/evaluations?ctx=hub')} />
    </div>
  )
}

function HrTile({ label, icon: Icon, bg, count, onClick }: {
  label: string; icon: React.ElementType; bg: string; count?: number; onClick: () => void
}) {
  return (
    <button type="button" onClick={onClick} className="flex flex-col items-center gap-2 w-20 group">
      <div className={cn('relative flex h-16 w-16 sm:h-14 sm:w-14 items-center justify-center rounded-xl text-white shadow-sm transition-transform group-hover:scale-105 group-hover:shadow-md', bg)}>
        <Icon className="h-8 w-8 sm:h-7 sm:w-7" />
        {count != null && count > 0 && (
          <span className="absolute -top-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-full border bg-background px-1 text-[10px] font-bold text-foreground shadow-sm">{count}</span>
        )}
      </div>
      <p className="text-[11px] font-medium text-center leading-tight">{label}</p>
    </button>
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

  const extractTime = (v?: string | null) => {
    if (!v) return '—'
    if (v.length <= 5) return v
    const t = v.includes('T') ? v.split('T')[1] : v
    return t?.slice(0, 5) || '—'
  }

  const netHours = (d: BioStarDayHistory): number | null => {
    if (d.duration_seconds == null) return null
    if (d.lunch_break_minutes == null) return null
    return Math.max(0, d.duration_seconds - d.lunch_break_minutes * 60) / 3600
  }
  const totalHours = history.reduce((sum, d) => sum + (netHours(d) ?? 0), 0)

  return (
    <Card>
      <CardContent className="px-0 pb-0">
        <div className="flex items-center justify-between px-4 pb-2 text-xs text-muted-foreground">
          <span>{history.length} days</span>
          <span className="font-semibold tabular-nums">{totalHours.toFixed(1)}h total</span>
        </div>
        <div className="divide-y">
          {history.map((d) => {
            const hours = netHours(d)
            const inTime = extractTime((d as any).adjusted_first_punch ?? d.first_punch)
            const outTime = extractTime((d as any).adjusted_last_punch ?? d.last_punch)
            return (
              <div key={d.date} className="flex items-center justify-between px-4 py-2.5">
                <div>
                  <p className="text-xs font-medium">
                    {new Date(d.date + 'T00:00').toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit', month: 'short' })}
                  </p>
                  <p className="text-[10px] text-muted-foreground">{inTime} — {outTime}</p>
                </div>
                <span className={cn(
                  'text-sm font-semibold tabular-nums',
                  hours != null && hours >= 8 ? 'text-green-600' : hours != null && hours > 0 ? 'text-amber-600' : 'text-muted-foreground',
                )}>
                  {hours != null ? `${hours.toFixed(1)}h` : '—'}
                </span>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

function HubTeamPontajeContent({ year, month }: { year: number; month: number }) {
  const start = `${year}-${String(month).padStart(2, '0')}-01`
  const lastDay = new Date(year, month, 0).getDate()
  const end = `${year}-${String(month).padStart(2, '0')}-${lastDay}`

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'team-pontaje', start, end],
    queryFn: () => profileApi.getTeamPontaje({ mode: 'range', start, end }),
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />

  const rows = (data?.is_manager ? (data.summary as BioStarRangeSummary[]) : []) ?? []
  if (rows.length === 0) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">No team punch data for this month.</CardContent></Card>
  }

  // Net hours = (worked − lunch deducted per present day) / 3600, same formula as HR Pontaje.
  const netHours = (r: BioStarRangeSummary): number => {
    const worked = r.adjusted_total_duration_seconds ?? r.total_duration_seconds ?? 0
    const lunch = (r.lunch_break_minutes ?? 0) * 60 * (r.days_present ?? 0)
    return Math.max(0, worked - lunch) / 3600
  }

  const withHours = rows.map((r) => ({ r, hours: netHours(r) }))
  const teamTotal = withHours.reduce((sum, x) => sum + x.hours, 0)

  return (
    <Card>
      <CardContent className="px-0 pb-0">
        <div className="flex items-center justify-between px-4 pb-2 text-xs text-muted-foreground">
          <span>{rows.length} {rows.length === 1 ? 'member' : 'members'}</span>
          <span className="font-semibold tabular-nums">{teamTotal.toFixed(1)}h total</span>
        </div>
        <div className="divide-y">
          {withHours.map(({ r, hours }) => {
            const name = r.mapped_jarvis_user_name || r.name || '—'
            const days = r.days_present ?? 0
            return (
              <div key={r.mapped_jarvis_user_id ?? r.biostar_user_id ?? name} className="flex items-center justify-between px-4 py-2.5">
                <div>
                  <p className="text-xs font-medium">{name}</p>
                  <p className="text-[10px] text-muted-foreground">{days} {days === 1 ? 'day' : 'days'}</p>
                </div>
                <span className={cn(
                  'text-sm font-semibold tabular-nums',
                  hours > 0 ? 'text-green-600' : 'text-muted-foreground',
                )}>
                  {hours > 0 ? `${hours.toFixed(1)}h` : '—'}
                </span>
              </div>
            )
          })}
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

  // Hooks must run on every render before any early return (Rules of Hooks).
  // expandedId previously sat below the `isLoading` / `bonuses.length === 0`
  // returns, so switching to a month WITH bonuses (e.g. May) added a hook
  // mid-render and crashed the panel ("Rendered more hooks than previous").
  const [expandedId, setExpandedId] = useState<number | null>(null)

  if (isLoading) return <Skeleton className="h-48 w-full" />

  const bonuses: ProfileBonus[] = data?.bonuses ?? []
  if (bonuses.length === 0) {
    return <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">No bonuses for this month.</CardContent></Card>
  }

  const fmtDate = (d: string | null) => d ? new Date(d + 'T00:00').toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' }) : ''

  return (
    <Card>
      <CardContent className="px-0 pb-0">
        <div className="divide-y">
          {bonuses.map((b) => {
            const isOpen = expandedId === b.id
            const startStr = b.participation_start || b.start_date
            const endStr = b.participation_end || b.end_date
            return (
              <button
                key={b.id}
                type="button"
                className="w-full text-left hover:bg-muted/30 transition-colors"
                onClick={() => setExpandedId(isOpen ? null : b.id)}
              >
                <div className="flex items-center justify-between px-4 py-3">
                  <p className="text-sm font-medium">{b.event_name || '—'}</p>
                  <span className="text-sm font-semibold tabular-nums shrink-0 ml-3">{b.bonus_days ?? 0}d</span>
                </div>
                {isOpen && (
                  <div className="px-4 pb-3 grid grid-cols-2 gap-2 text-[11px]" onClick={(e) => e.stopPropagation()}>
                    <div>
                      <span className="text-muted-foreground">Period</span>
                      <p className="font-medium">{startStr && endStr ? `${fmtDate(startStr)} – ${fmtDate(endStr)}` : '—'}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Hours Free</span>
                      <p className="font-medium">{b.hours_free ?? '—'}</p>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Bonus</span>
                      <p className="font-medium">{b.bonus_net ? `${Number(b.bonus_net).toLocaleString('ro-RO')} RON` : '—'}</p>
                    </div>
                    {b.details && (
                      <div>
                        <span className="text-muted-foreground">Details</span>
                        <p className="font-medium">{b.details}</p>
                      </div>
                    )}
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// A leave submission's approval status → a small coloured badge.
function LeaveStatusBadge({ status }: { status: string }) {
  const s = (status || '').toLowerCase()
  const ui = s === 'approved'
    ? { label: 'Aprobat', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400' }
    : s === 'rejected'
      ? { label: 'Respins', cls: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400' }
      : s === 'cancelled'
        ? { label: 'Anulat', cls: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-500/15 dark:text-zinc-400' }
        : s === 'cancellation_pending'
          ? { label: 'Anulare în așteptare', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400' }
          : { label: 'În așteptare', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400' }
  return <Badge className={cn('text-[9px] border-transparent', ui.cls)}>{ui.label}</Badge>
}

// Pure gating helper: which row actions are available for a given leave
// submission status. Pending statuses can still be self-modified/withdrawn;
// once approved, only a cancellation *request* is possible (it needs manager
// sign-off since a TimeBank credit already happened); terminal/in-flight
// statuses (cancelled, rejected, cancellation_pending) offer nothing.
export function leaveRowActions(status: string) {
  const s = (status || '').toLowerCase()
  const approved = s === 'approved'
  const pending = ['flagged', 'pending_approval', 'new', 'read'].includes(s)
  return { canModify: pending, canCancel: pending, canRequestCancel: approved }
}

function HubLeavePermitsContent({ userId, year, month }: { userId: number; year: number; month: number }) {
  // All hooks stay above any early return — the query and the row-expand state
  // must be called unconditionally on every render.
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  // The "+ Învoire" trigger lives in the breadcrumb; it flags the form open via
  // the URL so the modal can stay here with the list that refetches on submit.
  const showForm = searchParams.get('newinvoire') === '1'
  const closeForm = () => setSearchParams((prev) => { const p = new URLSearchParams(prev); p.delete('newinvoire'); return p }, { replace: true })

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'leave-permits', userId, year, month],
    queryFn: () => connecteamApi.getEmployeeSubmissions(userId, year, month),
  })
  const submissions: ConnecteamSubmission[] = data?.data ?? []

  // Row being modified via the edit overlay (Task 9's InvoireForm edit mode),
  // separate from `showForm`'s create-new overlay so the two never collide.
  const [editingSubmission, setEditingSubmission] = useState<ConnecteamSubmission | null>(null)
  // The list row lacks notes / 2nd approver — fetch the full stored answers so the
  // edit form shows and preserves them (a modify overwrites the whole answer blob).
  const { data: editDetailRes, isLoading: editDetailLoading } = useQuery({
    queryKey: ['leave-permit-detail', editingSubmission?.id],
    queryFn: () => connecteamApi.getLeavePermit(editingSubmission!.id),
    enabled: !!editingSubmission,
  })
  const editAnswers = editDetailRes?.data?.answers

  // Shared by both "Anulează" (pending, self-withdraw) and "Cere anulare"
  // (approved, needs manager sign-off) — the backend endpoint is the same;
  // it decides whether to cancel outright or open an approval based on the
  // submission's current status.
  const [cancelTarget, setCancelTarget] = useState<{ id: number; approved: boolean } | null>(null)
  const cancelMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => connecteamApi.cancelLeavePermit(id, reason),
    onSuccess: (res) => {
      toast.success(res.data.status === 'cancelled' ? 'Cerere anulată' : 'Anulare trimisă spre aprobare')
      setCancelTarget(null)
      queryClient.invalidateQueries({ queryKey: ['hub', 'leave-permits'] })
    },
    onError: () => toast.error('Acțiunea a eșuat.'),
  })

  // "De aprobat" is a tab inside the Învoiri zone, shown only when the user is an
  // approver with pending requests. Falls back to "mine" when nothing's pending.
  const [view, setView] = useState<'mine' | 'approve'>('mine')
  const { data: approvalsData } = useQuery({
    queryKey: ['hub', 'leave-approvals'],
    queryFn: () => connecteamApi.getPendingLeaveApprovals(),
  })
  const approvalsCount = approvalsData?.data?.length ?? 0
  const activeView = approvalsCount === 0 ? 'mine' : view

  return (
    <div className="space-y-3">
      {approvalsCount > 0 && (
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          <button type="button" onClick={() => setView('mine')}
            className={cn('flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors', activeView === 'mine' ? 'bg-background shadow-sm' : 'text-muted-foreground')}>
            Cererile mele
          </button>
          <button type="button" onClick={() => setView('approve')}
            className={cn('flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors', activeView === 'approve' ? 'bg-background shadow-sm' : 'text-muted-foreground')}>
            De aprobat ({approvalsCount})
          </button>
        </div>
      )}

      {activeView === 'approve' ? (
        <HubLeaveApprovalsContent />
      ) : isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : submissions.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">Nicio învoire pentru această lună. Apasă <span className="font-medium text-foreground">+ Învoire</span> pentru a completa un bilet.</CardContent></Card>
      ) : (
        <Card>
          <CardContent className="px-0 pb-0">
            <div className="divide-y">
              {submissions.map((s) => {
                const key = `${s.source ?? 'ct'}-${s.id}`
                const isOpen = expandedId === key
                const dateStr = s.leave_date ? new Date(s.leave_date + 'T00:00').toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit', month: 'short' }) : '—'
                return (
                  <div key={key}>
                    <button
                      type="button"
                      className="w-full text-left hover:bg-muted/30 transition-colors"
                      onClick={() => setExpandedId(isOpen ? null : key)}
                    >
                    <div className="flex items-center justify-between px-4 py-3">
                      <div>
                        <p className="text-sm font-medium">{dateStr}</p>
                        <p className="text-[10px] text-muted-foreground">{s.leave_reason || 'Leave permit'}</p>
                        {s.status?.toLowerCase() === 'approved' && s.approved_by && (
                          <p className="text-[10px] text-emerald-600 dark:text-emerald-400">Aprobat de {s.approved_by}</p>
                        )}
                        {s.status?.toLowerCase() !== 'approved' && s.status?.toLowerCase() !== 'rejected' && s.pending_approvers?.length ? (
                          <p className="text-[10px] text-amber-600 dark:text-amber-400">Așteaptă: {s.pending_approvers.join(', ')}</p>
                        ) : null}
                      </div>
                      <div className="flex items-center gap-2 shrink-0 ml-3">
                        <LeaveStatusBadge status={s.status} />
                        {s.source === 'jarvis' && <Badge variant="secondary" className="text-[9px]">JARVIS</Badge>}
                        <span className="text-sm font-semibold tabular-nums">{s.leave_hours != null ? `${s.leave_hours}h` : '—'}</span>
                      </div>
                    </div>
                    </button>
                    {isOpen && (
                      <div className="px-4 pb-3 grid grid-cols-2 gap-2 text-[11px]" onClick={(e) => e.stopPropagation()}>
                        <div>
                          <span className="text-muted-foreground">Time</span>
                          <p className="font-medium">{s.leave_start_time?.slice(0, 5) || '—'} — {s.leave_end_time?.slice(0, 5) || '—'}</p>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Source</span>
                          <p className="font-medium">{s.source === 'jarvis' ? 'JARVIS' : 'Connecteam'}</p>
                        </div>
                        {(() => {
                          const st = s.status?.toLowerCase()
                          if (st === 'approved')
                            return (
                              <div>
                                <span className="text-muted-foreground">Aprobat de</span>
                                <p className="font-medium">{s.approved_by || '—'}</p>
                              </div>
                            )
                          if (st === 'rejected')
                            return (
                              <div>
                                <span className="text-muted-foreground">Respins de</span>
                                <p className="font-medium">{s.approved_by || '—'}</p>
                              </div>
                            )
                          return (
                            <div>
                              <span className="text-muted-foreground">Așteaptă aprobare de la</span>
                              <p className="font-medium">{s.pending_approvers?.length ? s.pending_approvers.join(', ') : 'Manager direct'}</p>
                            </div>
                          )
                        })()}
                        {s.leave_reason && (
                          <div className="col-span-2">
                            <span className="text-muted-foreground">Reason</span>
                            <p className="font-medium">{s.leave_reason}</p>
                          </div>
                        )}
                        {(() => {
                          const actions = leaveRowActions(s.status)
                          if (!actions.canModify && !actions.canCancel && !actions.canRequestCancel) return null
                          return (
                            <div className="col-span-2 flex gap-2 pt-1">
                              {actions.canModify && (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="h-8 flex-1 text-xs"
                                  onClick={() => setEditingSubmission(s)}
                                >
                                  Modifică
                                </Button>
                              )}
                              {actions.canCancel && (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="h-8 flex-1 text-xs border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-500/40 dark:text-rose-400"
                                  disabled={cancelMut.isPending}
                                  onClick={() => setCancelTarget({ id: s.id, approved: false })}
                                >
                                  Anulează
                                </Button>
                              )}
                              {actions.canRequestCancel && (
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="h-8 flex-1 text-xs border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-500/40 dark:text-amber-400"
                                  disabled={cancelMut.isPending}
                                  onClick={() => setCancelTarget({ id: s.id, approved: true })}
                                >
                                  Cere anulare
                                </Button>
                              )}
                            </div>
                          )
                        })()}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <CancelLeaveDialog
        open={!!cancelTarget}
        approved={!!cancelTarget?.approved}
        pending={cancelMut.isPending}
        onOpenChange={(v) => { if (!v) setCancelTarget(null) }}
        onConfirm={(reason) => { if (cancelTarget) cancelMut.mutate({ id: cancelTarget.id, reason }) }}
      />

      {showForm && (
        <InvoireForm
          onClose={closeForm}
          onSubmitted={() => {
            // Code-defined form → /connecteam/api/submissions/leave-permit → the
            // connecteam service merges it into this list; refetch so it appears.
            queryClient.invalidateQueries({ queryKey: ['hub', 'leave-permits'] })
          }}
        />
      )}

      {editingSubmission && editAnswers && (
        <InvoireForm
          submissionId={editingSubmission.id}
          initial={{
            // Prefer the full stored answers (carry notes + 2nd approver); fall
            // back to the list row for the fields it does have.
            f_bi_leave_date: editAnswers.f_bi_leave_date || editingSubmission.leave_date || '',
            f_bi_start_time: editAnswers.f_bi_start_time || editingSubmission.leave_start_time || '',
            f_bi_duration_hours: String(editAnswers.f_bi_duration_hours ?? editingSubmission.leave_hours ?? ''),
            f_bi_reason: editAnswers.f_bi_reason || editingSubmission.leave_reason || '',
            f_bi_second_approver: editAnswers.f_bi_second_approver || '',
            f_bi_notes: editAnswers.f_bi_notes || '',
          }}
          onClose={() => setEditingSubmission(null)}
          onSubmitted={() => {
            setEditingSubmission(null)
            queryClient.invalidateQueries({ queryKey: ['hub', 'leave-permits'] })
          }}
        />
      )}
      {editingSubmission && editDetailLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}
    </div>
  )
}

// Manager view: leave requests awaiting my approval, with approve/reject.
// Pure label helper: for a cancellation request, Aprobă actually CANCELS the
// already-granted leave (and reverses its TimeBank credit) while Respinge
// keeps it as-is — the inverse of a grant request's semantics. Same
// decideLeaveApproval('approved'|'rejected') call either way; only the
// wording changes so the manager isn't misled into treating it like a grant.
export function leaveApprovalLabels(isCancellation: boolean) {
  return isCancellation
    ? {
        badge: 'Cerere de anulare',
        approve: 'Aprobă anularea',
        reject: 'Respinge anularea',
        confirmReject: 'Confirmă respingerea anulării',
      }
    : {
        badge: null as string | null,
        approve: 'Aprobă',
        reject: 'Respinge',
        confirmReject: 'Confirmă respingerea',
      }
}

function HubLeaveApprovalsContent() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'leave-approvals'],
    queryFn: () => connecteamApi.getPendingLeaveApprovals(),
  })
  const items = data?.data ?? []

  const [rejectingId, setRejectingId] = useState<number | null>(null)
  const [rejectComment, setRejectComment] = useState('')
  const decide = useMutation({
    mutationFn: ({ requestId, decision, comment }: { requestId: number; decision: 'approved' | 'rejected'; comment?: string }) =>
      connecteamApi.decideLeaveApproval(requestId, decision, comment),
    onSuccess: (_res, vars) => {
      toast.success(vars.decision === 'approved' ? 'Învoire aprobată.' : 'Învoire respinsă.')
      setRejectingId(null); setRejectComment('')
      queryClient.invalidateQueries({ queryKey: ['hub', 'leave-approvals'] })
      queryClient.invalidateQueries({ queryKey: ['hub', 'leave-permits'] })
    },
    onError: () => toast.error('Acțiunea a eșuat.'),
  })

  if (isLoading) return <Skeleton className="h-48 w-full" />
  if (items.length === 0)
    return <Card><CardContent className="py-8 text-center text-muted-foreground text-sm">Nicio cerere de aprobat.</CardContent></Card>

  return (
    <Card>
      <CardContent className="px-0 pb-0">
        <div className="divide-y">
          {items.map((it) => {
            const dateStr = it.leave_date
              ? new Date(it.leave_date + 'T00:00').toLocaleDateString('ro-RO', { weekday: 'short', day: '2-digit', month: 'short' })
              : '—'
            const busy = decide.isPending && decide.variables?.requestId === it.request_id
            const labels = leaveApprovalLabels(!!it.is_cancellation)
            return (
              <div key={it.request_id} className="px-4 py-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    {labels.badge && (
                      <Badge variant="outline"
                        className="mb-1 border-amber-300 text-amber-700 bg-amber-50 dark:border-amber-500/40 dark:text-amber-400 dark:bg-amber-900/20">
                        {labels.badge}
                      </Badge>
                    )}
                    <p className="text-base font-semibold">{it.requester_name || 'Angajat'}</p>
                    <p className="text-sm text-muted-foreground">
                      {dateStr} · {it.leave_start_time?.slice(0, 5) || '—'}–{it.leave_end_time?.slice(0, 5) || '—'} · Motiv: {it.leave_reason || 'Învoire'}
                    </p>
                    {it.is_cancellation && it.cancellation_reason && (
                      <p className="mt-0.5 text-sm font-medium text-amber-700 dark:text-amber-400">
                        Motiv anulare: {it.cancellation_reason}
                      </p>
                    )}
                  </div>
                  <span className="text-base font-semibold tabular-nums shrink-0">{it.leave_hours != null ? `${it.leave_hours}h` : ''}</span>
                </div>
                {rejectingId === it.request_id ? (
                  <div className="space-y-2">
                    <Textarea autoFocus rows={2} value={rejectComment}
                      onChange={(e) => setRejectComment(e.target.value)}
                      placeholder="Motivul respingerii (opțional)" className="text-base" />
                    <div className="flex gap-2">
                      <Button variant="outline" className="flex-1 h-11 text-base"
                        disabled={busy} onClick={() => { setRejectingId(null); setRejectComment('') }}>
                        Anulează
                      </Button>
                      <Button className="flex-1 h-11 text-base bg-rose-600 hover:bg-rose-700 text-white"
                        disabled={busy} onClick={() => decide.mutate({ requestId: it.request_id, decision: 'rejected', comment: rejectComment })}>
                        {labels.confirmReject}
                      </Button>
                    </div>
                  </div>
                ) : (
                <div className="flex gap-2">
                  <Button variant="outline"
                    className="flex-1 h-11 text-base border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-500/40 dark:text-rose-400"
                    disabled={busy} onClick={() => { setRejectingId(it.request_id); setRejectComment('') }}>
                    {labels.reject}
                  </Button>
                  <Button className="flex-1 h-11 text-base bg-emerald-600 hover:bg-emerald-700 text-white"
                    disabled={busy} onClick={() => decide.mutate({ requestId: it.request_id, decision: 'approved' })}>
                    {labels.approve}
                  </Button>
                </div>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Approvals Panel ─────────────────────────────────────

function HubApprovalsPanel() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'approvals-queue'],
    queryFn: () => fetch('/approvals/api/my-queue', { credentials: 'include' }).then(r => r.json()),
    refetchInterval: 30_000,
  })

  const decideMutation = useMutation({
    mutationFn: ({ id, decision, comment }: { id: number; decision: string; comment?: string }) =>
      fetch(`/approvals/api/requests/${id}/decide`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, comment }),
      }).then(r => r.json()),
    onSuccess: () => {
      toast.success('Decision recorded')
      queryClient.invalidateQueries({ queryKey: ['hub', 'approvals'] })
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
    onError: () => toast.error('Failed to submit decision'),
  })

  const queue = data?.queue ?? []

  if (isLoading) return <Skeleton className="h-32 w-full rounded-lg" />
  if (queue.length === 0) return <div className="py-8 text-center text-muted-foreground text-sm">No pending approvals</div>

  return (
    <div className="space-y-3">
      {queue.map((item: any) => {
        const ctx = item.context_snapshot || {}
        const title = ctx.title || `${item.entity_type} #${item.entity_id}`
        const requestedBy = item.requested_by?.name || 'Unknown'
        const requestedAt = item.requested_at ? new Date(item.requested_at).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''
        return (
          <div key={item.id} className="rounded-lg border bg-card p-4 space-y-3">
            <div>
              <p className="text-sm font-medium">{title}</p>
              <p className="text-xs text-muted-foreground">
                From {requestedBy} &middot; {requestedAt}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                className="h-9 bg-emerald-600 hover:bg-emerald-700 text-white"
                disabled={decideMutation.isPending}
                onClick={() => decideMutation.mutate({ id: item.id, decision: 'approved' })}
              >
                Approve
              </Button>
              <Button
                size="sm"
                variant="destructive"
                className="h-9"
                disabled={decideMutation.isPending}
                onClick={() => {
                  const reason = prompt('Reason for rejection (optional):')
                  decideMutation.mutate({ id: item.id, decision: 'rejected', comment: reason || undefined })
                }}
              >
                Reject
              </Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Forms Panel ────────────────────────────────────────

function HubFormsPanel() {
  const queryClient = useQueryClient()
  const [openSlug, setOpenSlug] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'published-forms'],
    queryFn: () => fetch('/forms/api/forms/published', { credentials: 'include' }).then(r => r.json()),
  })
  const forms: { id: number; name: string; slug: string; description: string | null }[] = data?.forms ?? []

  if (isLoading) return <Skeleton className="h-48 w-full" />
  if (forms.length === 0) {
    return <Card><CardContent className="py-12 text-center text-muted-foreground text-sm">No forms available.</CardContent></Card>
  }

  const formStyle = (slug: string) => {
    if (slug.includes('voucher')) return { icon: Ticket, bg: 'bg-amber-100 dark:bg-amber-900/30', fg: 'text-amber-700 dark:text-amber-400' }
    if (slug.includes('invoire') || slug.includes('leave')) return { icon: ClipboardList, bg: 'bg-blue-100 dark:bg-blue-900/30', fg: 'text-blue-700 dark:text-blue-400' }
    if (slug.includes('drive') || slug.includes('test')) return { icon: Car, bg: 'bg-violet-100 dark:bg-violet-900/30', fg: 'text-violet-700 dark:text-violet-400' }
    if (slug.includes('feedback') || slug.includes('survey')) return { icon: MessageSquare, bg: 'bg-pink-100 dark:bg-pink-900/30', fg: 'text-pink-700 dark:text-pink-400' }
    return { icon: FileCheck, bg: 'bg-emerald-100 dark:bg-emerald-900/30', fg: 'text-emerald-700 dark:text-emerald-400' }
  }

  const openForm = forms.find(f => f.slug === openSlug)

  return (
    <>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Available Forms</CardTitle></CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-6">
            {forms.map((form) => {
              const style = formStyle(form.slug)
              const Icon = style.icon
              return (
                <button
                  key={form.id}
                  type="button"
                  onClick={() => setOpenSlug(form.slug)}
                  className="flex flex-col items-center gap-2 w-20 group"
                >
                  <div className={cn('flex h-16 w-16 sm:h-14 sm:w-14 items-center justify-center rounded-xl shadow-sm transition-transform group-hover:scale-105 group-hover:shadow-md', style.bg, style.fg)}>
                    <Icon className="h-8 w-8 sm:h-7 sm:w-7" />
                  </div>
                  <p className="text-[11px] font-medium text-center leading-tight line-clamp-2">{form.name}</p>
                </button>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {openSlug && (
        <HubFormModal
          slug={openSlug}
          name={openForm?.name || ''}
          onClose={() => setOpenSlug(null)}
          onSubmitted={() => {
            // Keep the modal open so the success screen (thank-you + PDF
            // download links) can render. The user closes it via Inchide/Back.
            queryClient.invalidateQueries({ queryKey: ['hub'] })
          }}
        />
      )}
    </>
  )
}

function HubFormModal({ slug, name, onClose, onSubmitted }: { slug: string; name: string; onClose: () => void; onSubmitted: () => void }) {
  const user = useAuthStore((s) => s.user)
  const [successData, setSuccessData] = useState<{ thank_you_message?: string; hook_data?: Record<string, string> } | null>(null)
  const isVoucherForm = slug === VOUCHER_FORM_SLUG
  const [mode, setMode] = useState<'issue' | 'redeem'>('issue')

  const { data: form, isLoading } = useQuery({
    queryKey: ['public-form', slug],
    queryFn: () => import('@/api/forms').then(m => m.formsApi.getPublicForm(slug)),
  })

  const { schema, defaultValues: voucherDefaults, submitLabel, needsSignatureSave } =
    useVoucherSchema(form?.schema ?? [], slug)

  // Build prefill defaults from form settings
  const prefillDefaults = useMemo(() => {
    const prefill = form?.settings?.prefill as Record<string, string> | undefined
    if (!prefill || !user) return {}
    const defaults: Record<string, unknown> = {}
    for (const [fieldId, source] of Object.entries(prefill)) {
      if (source === 'user.name') defaults[fieldId] = user.name || ''
      else if (source === 'user.email') defaults[fieldId] = user.email || ''
    }
    return defaults
  }, [form?.settings, user])

  const mergedDefaults = useMemo(
    () => ({ ...prefillDefaults, ...voucherDefaults }),
    [prefillDefaults, voucherDefaults],
  )

  const submitMutation = useMutation({
    mutationFn: async (answers: Record<string, unknown>) => {
      if (needsSignatureSave && answers.f_signature && typeof answers.f_signature === 'string') {
        await api.put('/profile/api/signature', { signature: answers.f_signature })
      }
      const { f_signature: _, ...formAnswers } = answers
      return import('@/api/forms').then(m => m.formsApi.submitPublicForm(slug, { answers: formAnswers }))
    },
    onSuccess: (data) => {
      setSuccessData({
        thank_you_message: data?.thank_you_message,
        hook_data: data?.hook_data,
      })
      onSubmitted()
    },
    onError: () => toast.error('Failed to submit form'),
  })

  return (
    <div className="fixed inset-0 z-50 bg-background flex flex-col animate-in slide-in-from-right duration-200">
      {/* Top nav bar */}
      <div className="shrink-0 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="flex items-center h-12 px-4">
          <Button variant="ghost" size="sm" className="h-8 gap-1.5 text-xs" onClick={onClose}>
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>
          <h2 className="flex-1 text-center text-sm font-semibold truncate px-2">{name}</h2>
          <div className="w-16" />
        </div>
      </div>
      {/* Form body */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-lg px-5 py-6">
          {successData ? (
            <div className="text-center space-y-4 py-8">
              <div className="mx-auto w-12 h-12 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <Check className="h-6 w-6 text-green-600" />
              </div>
              <p className="text-sm text-muted-foreground">{successData.thank_you_message || 'Submitted successfully!'}</p>
              {successData.hook_data?.pdf_legal_url && (
                <div className="flex flex-col gap-2 pt-2">
                  <a href={successData.hook_data.pdf_legal_url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center justify-center gap-2 rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent">
                    Download Legal PDF
                  </a>
                  {successData.hook_data.pdf_custom_url && (
                    <a href={successData.hook_data.pdf_custom_url} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center justify-center gap-2 rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent">
                      Download Custom PDF
                    </a>
                  )}
                </div>
              )}
              <Button variant="outline" size="sm" onClick={onClose}>Inchide</Button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Issue / Redeem toggle — only for the voucher form */}
              {isVoucherForm && (
                <div className="flex rounded-lg border bg-muted/40 p-1 gap-1">
                  <button
                    className={cn(
                      'flex-1 flex items-center justify-center gap-2 rounded-md py-2.5 text-sm font-medium transition-colors',
                      mode === 'issue' ? 'bg-slate-800 text-white shadow-sm' : 'text-muted-foreground hover:bg-accent',
                    )}
                    onClick={() => setMode('issue')}
                  >
                    <Ticket className="h-4 w-4" />
                    Issue Voucher
                  </button>
                  <button
                    className={cn(
                      'flex-1 flex items-center justify-center gap-2 rounded-md py-2.5 text-sm font-medium transition-colors',
                      mode === 'redeem' ? 'bg-slate-800 text-white shadow-sm' : 'text-muted-foreground hover:bg-accent',
                    )}
                    onClick={() => setMode('redeem')}
                  >
                    <ScanLine className="h-4 w-4" />
                    Redeem Voucher
                  </button>
                </div>
              )}

              {isVoucherForm && mode === 'redeem' ? (
                <Suspense fallback={<Skeleton className="h-48 w-full" />}>
                  <VoucherRedeem />
                </Suspense>
              ) : isLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
                </div>
              ) : schema.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">This form has no fields.</p>
              ) : (
                <Suspense fallback={<Skeleton className="h-48 w-full" />}>
                  <FormRendererLazy
                    schema={schema}
                    onSubmit={(answers) => submitMutation.mutate(answers)}
                    submitting={submitMutation.isPending}
                    submitLabel={submitLabel}
                    defaultValues={mergedDefaults}
                  />
                </Suspense>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
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

  const netHours = (d: BioStarDayHistory): number | null => {
    if (!d.duration_seconds) return 0
    if (d.lunch_break_minutes == null) return null // can't calculate without lunch data
    return Math.max(0, d.duration_seconds - d.lunch_break_minutes * 60) / 3600
  }

  const totalHours = history.reduce((sum, d) => sum + (netHours(d) ?? 0), 0)
  const DAYS_RO = ['Lun', 'Mar', 'Mie', 'Joi', 'Vin', 'Sam', 'Dum']

  // Build a map of date → day data
  const dayMap = new Map(history.map(d => [d.date, d]))

  // Generate all 7 days of the week
  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(monday)
    date.setDate(monday.getDate() + i)
    const dateStr = date.toISOString().slice(0, 10)
    const dayData = dayMap.get(dateStr)
    const hours = dayData ? netHours(dayData) : 0
    const isToday = dateStr === now.toISOString().slice(0, 10)
    const isFuture = date > now
    const extractTime = (v?: string | null) => {
      if (!v) return null
      // "HH:MM" (5 chars) vs "2026-06-23T08:02:00" (full ISO)
      if (v.length <= 5) return v
      const t = v.includes('T') ? v.split('T')[1] : v
      return t?.slice(0, 5) || null
    }
    const punchIn = extractTime(dayData?.adjusted_first_punch ?? dayData?.first_punch)
    const punchOut = extractTime(dayData?.adjusted_last_punch ?? dayData?.last_punch)
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
                (d.hours ?? 0) >= 8 ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                (d.hours ?? 0) > 0 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
                d.hasData ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                'bg-muted/50 text-muted-foreground',
              )}>
                {!d.isFuture && d.punchIn && <span className="text-[8px] opacity-70">{d.punchIn}</span>}
                <span className="text-[11px] font-semibold">
                  {d.isFuture ? '' : (d.hours ?? 0) > 0 ? `${(d.hours ?? 0).toFixed(1)}` : d.hasData ? '0' : '-'}
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

// ─── Work Summary Card (1/3 column) ─────────────────────

function HubWorkSummaryCard() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'work-summary', year, month],
    queryFn: () => profileApi.getWorkSummary({ year, month }),
    staleTime: 5 * 60_000,
  })

  if (isLoading) return <Skeleton className="h-32 w-full rounded-lg" />
  if (!data?.success) return null

  const { days_worked, working_days, leave_days, co_remaining } = data

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(y => y - 1) } else setMonth(m => m - 1) }
  const nextMonth = () => { if (month === 12) { setMonth(1); setYear(y => y + 1) } else setMonth(m => m + 1) }

  const leaveCodeLabels: Record<string, string> = {
    CO: 'Concediu Odihna', CM: 'Concediu Medical', CES: 'Concediu Eveniment Special',
    CFS: 'Concediu Fara Salariu', CIC: 'Concediu Ingrijire Copil',
    CMS: 'Concediu Maternitate', DLG: 'Delegatie', ZLS: 'Zile Libere Suplimentare',
  }

  const workedPct = working_days > 0 ? Math.round((days_worked / working_days) * 100) : 0

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Activity className="h-4 w-4" />
            This Month
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={prevMonth}><ChevronLeft className="h-3.5 w-3.5" /></Button>
            <span className="text-[11px] font-medium w-24 text-center">{MONTHS_RO[month - 1]} {year}</span>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={nextMonth}><ChevronRight className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Days Worked */}
        <div>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-muted-foreground">Days Worked</span>
            <span className="font-semibold tabular-nums">{days_worked} / {working_days}</span>
          </div>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all', workedPct >= 90 ? 'bg-green-500' : workedPct >= 50 ? 'bg-amber-500' : 'bg-red-500')}
              style={{ width: `${Math.min(workedPct, 100)}%` }}
            />
          </div>
        </div>

        {/* Leave Days */}
        {leave_days.length > 0 && (
          <div className="space-y-1">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">On Leave</span>
            {leave_days.map((l) => (
              <div key={l.code} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{leaveCodeLabels[l.code] || l.name}</span>
                <span className="font-medium tabular-nums">{l.days}d</span>
              </div>
            ))}
          </div>
        )}

        {/* CO Balance */}
        {co_remaining != null && (
          <div className="pt-2 border-t">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">CO Days Left</span>
              <span className="font-semibold tabular-nums text-emerald-600">{co_remaining}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Marketing Events & Bonuses Card ────────────────────

function HubBonusCard() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['hub', 'bonuses-card', year],
    queryFn: () => profileApi.getHrEvents({ year, per_page: 50 }),
    staleTime: 5 * 60_000,
  })

  const bonuses: ProfileBonus[] = data?.bonuses ?? []

  if (isLoading) return <Skeleton className="h-24 w-full" />

  const prevYear = () => setYear(y => y - 1)
  const nextYear = () => setYear(y => y + 1)

  const totalBonusNet = bonuses.reduce((sum, b) => sum + (b.bonus_net ? Number(b.bonus_net) : 0), 0)
  const fmtDate = (d: string | null) => d ? new Date(d + 'T00:00').toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' }) : ''

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Award className="h-4 w-4" />
            Events & Bonuses
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={prevYear}><ChevronLeft className="h-3.5 w-3.5" /></Button>
            <span className="text-xs font-medium w-12 text-center">{year}</span>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={nextYear}><ChevronRight className="h-3.5 w-3.5" /></Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-0 pb-0">
        {bonuses.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6 px-4">No event bonuses for {year}.</p>
        ) : (
          <>
            <div className="divide-y">
              {bonuses.map((b) => {
                const isOpen = expandedId === b.id
                const startStr = b.participation_start || b.start_date
                const endStr = b.participation_end || b.end_date
                return (
                  <button
                    key={b.id}
                    type="button"
                    className="w-full text-left hover:bg-muted/30 transition-colors"
                    onClick={() => setExpandedId(isOpen ? null : b.id)}
                  >
                    <div className="flex items-center justify-between px-4 py-2.5">
                      <div className="min-w-0">
                        <p className="text-xs font-medium truncate">{b.event_name}</p>
                        {b.brand && <p className="text-[10px] text-muted-foreground">{b.brand}</p>}
                      </div>
                      <span className="text-xs font-semibold tabular-nums shrink-0 ml-3">
                        {b.bonus_net ? `${Number(b.bonus_net).toLocaleString('ro-RO')} RON` : '—'}
                      </span>
                    </div>
                    {isOpen && (
                      <div className="px-4 pb-2.5 grid grid-cols-3 gap-2 text-[10px]" onClick={(e) => e.stopPropagation()}>
                        <div>
                          <span className="text-muted-foreground uppercase tracking-wider">Period</span>
                          <p className="font-medium mt-0.5">{startStr && endStr ? `${fmtDate(startStr)} – ${fmtDate(endStr)}` : '—'}</p>
                        </div>
                        <div>
                          <span className="text-muted-foreground uppercase tracking-wider">Days</span>
                          <p className="font-medium mt-0.5">{b.bonus_days ?? '—'}</p>
                        </div>
                        <div>
                          <span className="text-muted-foreground uppercase tracking-wider">Hours Free</span>
                          <p className="font-medium mt-0.5">{b.hours_free ?? '—'}</p>
                        </div>
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
            {totalBonusNet > 0 && (
              <div className="flex items-center justify-between px-4 py-2 border-t bg-muted/20 text-xs">
                <span className="text-muted-foreground">{bonuses.length} events</span>
                <span className="tabular-nums font-semibold">{totalBonusNet.toLocaleString('ro-RO')} RON</span>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
