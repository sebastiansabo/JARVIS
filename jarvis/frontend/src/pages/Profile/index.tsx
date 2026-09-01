import React, { useState, useMemo, useEffect, lazy, Suspense } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useTabParam } from '@/hooks/useTabParam'
import {
  FileSpreadsheet,
  FileText,
  Activity,
  Gift,
  User,
  Mail,
  Phone,
  Building2,
  Shield,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  Fingerprint,
  Clock,
  LogIn,
  LogOut,
  Users,
  Pencil,
  Calendar,
  Briefcase,
  Hash,
  Cake,
  PartyPopper,
  Key,
  Eye,
  EyeOff,
  CheckCircle2,
  MapPin,
  SlidersHorizontal,
  ClipboardList,
  Plus,
  Ticket,
  MoreHorizontal,
  FileCheck2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MobileBottomTabs } from '@/components/shared/MobileBottomTabs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { DateField } from '@/components/ui/date-field'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatCard } from '@/components/shared/StatCard'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { InvoicePreviewModal } from './InvoicePreviewModal'
import { EmptyState } from '@/components/shared/EmptyState'
import { SearchInput } from '@/components/shared/SearchInput'
import { FilterBar, type FilterField } from '@/components/shared/FilterBar'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { fmtPunchTime } from '@/lib/punchTime'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { profileApi, type ProfileUpdatePayload } from '@/api/profile'
import { consentsApi } from '@/api/consents'
import { sincronApi, type SincronTimesheetData } from '@/api/sincron'
import { settingsApi } from '@/api/settings'
import { checkinApi } from '@/api/checkin'
import { usersApi } from '@/api/users'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'
import { connecteamApi, type ConnecteamSubmission } from '@/api/connecteam'
import { InvoireForm } from '@/components/forms/InvoireForm'
import { AllocationEditor, allocationsToRows, rowsToApiPayload } from '@/pages/Accounting/AllocationEditor'
import { EditInvoiceDialog } from '@/pages/Accounting/EditInvoiceDialog'
import { dedupeMergedAllocations } from '@/pages/Accounting/allocationUtils'
import { LineItemAllocationsView } from '@/pages/Accounting/LineItemAllocationsView'
import { InvoiceLinkedDocs } from '@/components/shared/InvoiceLinkedDocs'
import { toast } from 'sonner'
import { cn, usePersistedState } from '@/lib/utils'
import type { Invoice } from '@/types/invoices'
import type { ProfileInvoice, ProfileActivity, ProfileBonus, OrgTreeNode } from '@/types/profile'
import type { BioStarDayHistory, BioStarPunchLog, BioStarDailySummary, BioStarRangeSummary } from '@/types/biostar'

const VouchersPanel = lazy(() => import('./VouchersPanel'))
const CreateTicketDialog = lazy(() => import('@/pages/Ticketing/CreateTicketDialog'))

type Tab = 'invoices' | 'hr' | 'vouchers'
type HrSubTab = 'hr-events' | 'pontaje' | 'team-pontaje' | 'sincron' | 'leave-permits'

const mainTabs: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: 'invoices', label: 'My Invoices', icon: FileText },
  { key: 'hr', label: 'HR', icon: Activity },
  { key: 'vouchers', label: 'Vouchers', icon: Ticket },
]

const hrSubTabs: { key: HrSubTab; label: string; icon: React.ElementType }[] = [
  { key: 'hr-events', label: 'Bonuses', icon: Gift },
  { key: 'pontaje', label: 'Pontaje', icon: Fingerprint },
  { key: 'team-pontaje', label: 'Team Pontaje', icon: Users },
  { key: 'sincron', label: 'Sincron', icon: FileSpreadsheet },
  { key: 'leave-permits', label: 'Leave Permits', icon: ClipboardList },
]

export default function Profile() {
  const isMobile = useIsMobile()
  const authUser = useAuthStore((s) => s.user)
  const hasVouchersPerm = !authUser?.permissions || (authUser.permissions['vouchers.profile.view'] ?? true)
  const visibleMainTabs = hasVouchersPerm ? mainTabs : mainTabs.filter((t) => t.key !== 'vouchers')
  const [activeTab, setActiveTab] = useTabParam<Tab>('invoices')
  const [activeHrSubTab, setActiveHrSubTab] = useTabParam<HrSubTab>('pontaje', 'hrtab')
  const [profileDetailsOpen, setProfileDetailsOpen] = useState(false)
  const [ticketOpen, setTicketOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)

  const queryClient = useQueryClient()

  const { data: summary, isLoading } = useQuery({
    queryKey: ['profile', 'summary'],
    queryFn: profileApi.getSummary,
  })

  const user = summary?.user

  // Fetch org path from organigram
  const { data: orgPaths = [] } = useQuery({
    queryKey: ['user-org-path', user?.id],
    queryFn: () => usersApi.getUserOrgPath(user!.id),
    enabled: !!user?.id,
  })

  // Check-in status for header quick action
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
        queryClient.invalidateQueries({ queryKey: ['profile', 'pontaje'] })
        toast.success(`${res.direction} at ${res.time} — ${res.location}`)
      } else {
        toast.error(res.error || 'Punch failed')
      }
    },
    onError: () => toast.error('Punch failed — try the Check In page'),
  })

  const checkinDir = checkinStatus?.next_direction ?? 'IN'
  const isCheckedIn = checkinDir !== 'IN'
  const lastPunch = checkinStatus?.punches?.length
    ? checkinStatus.punches[checkinStatus.punches.length - 1]
    : null

  return (
    <div className="space-y-6">
      {/* Command Center Header */}
      {isLoading ? (
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-4">
            <Skeleton className="h-11 w-11 rounded-full shrink-0" />
            <div className="space-y-1.5">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-5 w-36" />
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-4">
            {/* Left: Avatar + Identity */}
            <button
              type="button"
              className="flex items-center gap-3 min-w-0 hover:opacity-80 transition-opacity"
              onClick={() => setProfileDetailsOpen(true)}
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
                {user?.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase() || '?'}
              </div>
              <div className="min-w-0 text-left">
                <p className="text-xs text-muted-foreground truncate">
                  {user?.name || 'Loading...'}
                </p>
                <h1 className="text-lg font-bold leading-tight">Command Center</h1>
              </div>
            </button>

            {/* Right: Actions */}
            <div className="ml-auto flex items-center gap-2">
              {user?.company && (
                <span className="text-xs text-muted-foreground hidden sm:inline">{user.company}</span>
              )}
              {user?.role && (
                <Badge variant="outline" className="text-xs">
                  {user.role}
                </Badge>
              )}

              {/* Desktop action buttons */}
              {!isMobile && (
                <>
                  {checkinStatus?.mapped && (
                    <div className="flex items-center gap-2">
                      {lastPunch && (
                        <div className="text-xs text-right leading-tight">
                          <p className="font-medium">
                            {lastPunch.direction === 'IN' ? 'In' : 'Out'} at{' '}
                            {fmtPunchTime(lastPunch.event_datetime)}
                          </p>
                          {lastPunch.raw_data?.location_name && (
                            <p className="text-muted-foreground">{lastPunch.raw_data.location_name}</p>
                          )}
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
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setTicketOpen(true)}
                  >
                    <Ticket className="h-3.5 w-3.5 mr-1.5" />
                    Ticket
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditOpen(true)}
                  >
                    <Pencil className="h-3.5 w-3.5 mr-1.5" />
                    Edit profile
                  </Button>
                </>
              )}

              {/* Mobile: overflow menu */}
              {isMobile && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="sm" variant="outline">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {checkinStatus?.mapped && (
                      <DropdownMenuItem onClick={() => punchMut.mutate()} disabled={punchMut.isPending}>
                        {isCheckedIn ? <LogOut className="h-4 w-4 mr-2" /> : <LogIn className="h-4 w-4 mr-2" />}
                        {isCheckedIn ? 'Check Out' : 'Check In'}
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={() => setTicketOpen(true)}>
                      <Ticket className="h-4 w-4 mr-2" />
                      New Ticket
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setEditOpen(true)}>
                      <Pencil className="h-4 w-4 mr-2" />
                      Edit profile
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Dialogs */}
      {user && (
        <ProfileDetailsDialog
          open={profileDetailsOpen}
          onOpenChange={setProfileDetailsOpen}
          user={user}
          orgPaths={orgPaths}
          sincronDepartment={summary?.sincron?.department}
          onEdit={() => setEditOpen(true)}
        />
      )}
      {user && (
        <EditProfileDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          user={user}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ['profile', 'summary'] })}
        />
      )}
      <Suspense fallback={null}>
        <CreateTicketDialog open={ticketOpen} onOpenChange={setTicketOpen} />
      </Suspense>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
        {isMobile ? (
          <MobileBottomTabs>
            <TabsList className="w-full">
              {visibleMainTabs.map((tab) => {
                const Icon = tab.icon
                return (
                  <TabsTrigger key={tab.key} value={tab.key}>
                    <Icon className="h-5 w-5" />
                    {tab.label}
                  </TabsTrigger>
                )
              })}
            </TabsList>
          </MobileBottomTabs>
        ) : (
          <div className="flex gap-2">
            {visibleMainTabs.map((tab) => {
              const Icon = tab.icon
              const isActive = activeTab === tab.key
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    'flex items-center gap-2.5 rounded-lg border px-5 py-2.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-card text-muted-foreground border-border hover:text-foreground hover:bg-muted/50',
                  )}
                >
                  <Icon className="h-5 w-5" />
                  {tab.label}
                </button>
              )
            })}
          </div>
        )}
      </Tabs>

      {/* HR Sub-Tabs */}
      {activeTab === 'hr' && (
        <Tabs value={activeHrSubTab} onValueChange={(v) => setActiveHrSubTab(v as HrSubTab)}>
          <TabsList className="w-auto h-8 bg-muted/50">
            {hrSubTabs.map((tab) => {
              const Icon = tab.icon
              return (
                <TabsTrigger key={tab.key} value={tab.key} className="text-xs h-7 px-2.5 gap-1">
                  <Icon className="h-3.5 w-3.5" />
                  {tab.label}
                </TabsTrigger>
              )
            })}
          </TabsList>
        </Tabs>
      )}

      {/* Tab Content */}
      {activeTab === 'invoices' && <InvoicesPanel orgDepartments={orgPaths.map(o => o.department).filter(Boolean)} isOrgResponsable={summary?.is_org_responsable ?? false} />}
      {activeTab === 'hr' && activeHrSubTab === 'hr-events' && <HrEventsPanel />}
      {activeTab === 'hr' && activeHrSubTab === 'pontaje' && <PontajePanel />}
      {activeTab === 'hr' && activeHrSubTab === 'team-pontaje' && <TeamPontajePanel />}
      {activeTab === 'hr' && activeHrSubTab === 'sincron' && <SincronPanel />}
      {activeTab === 'hr' && activeHrSubTab === 'leave-permits' && user && <LeavePermitsPanel userId={user.id} />}
      {activeTab === 'vouchers' && <Suspense fallback={<div className="py-8 text-center text-muted-foreground">Loading...</div>}><VouchersPanel /></Suspense>}
    </div>
  )
}

// ─── Anniversary Banners ──────────────────────────────────────────

function isTodayAnniversary(dateStr: string | null | undefined): { match: boolean; years: number } {
  if (!dateStr) return { match: false, years: 0 }
  const d = new Date(dateStr)
  const now = new Date()
  if (d.getMonth() === now.getMonth() && d.getDate() === now.getDate()) {
    return { match: true, years: now.getFullYear() - d.getFullYear() }
  }
  return { match: false, years: 0 }
}

function AnniversaryBanners({ birthdate, contractDate, name }: { birthdate: string | null | undefined; contractDate: string | null | undefined; name: string }) {
  const bday = isTodayAnniversary(birthdate)
  const workAnniv = isTodayAnniversary(contractDate)
  const firstName = name.split(' ')[0] || name

  if (!bday.match && !workAnniv.match) return null

  return (
    <div className="mt-4 space-y-2">
      {bday.match && (
        <div className="flex items-center gap-3 rounded-lg border border-pink-200 bg-pink-50 dark:border-pink-900 dark:bg-pink-950/30 px-4 py-3">
          <Cake className="h-5 w-5 text-pink-500 shrink-0" />
          <span className="text-sm">
            <span className="font-semibold">Happy Birthday, {firstName}!</span>
            {' '}{bday.years > 0 ? `Wishing you an amazing ${bday.years}th celebration!` : 'Have a wonderful day!'}
          </span>
          <PartyPopper className="h-5 w-5 text-pink-500 shrink-0" />
        </div>
      )}
      {workAnniv.match && workAnniv.years > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/30 px-4 py-3">
          <Briefcase className="h-5 w-5 text-blue-500 shrink-0" />
          <span className="text-sm">
            <span className="font-semibold">Happy {workAnniv.years}-year Work Anniversary, {firstName}!</span>
            {' '}Thank you for your dedication and hard work!
          </span>
          <PartyPopper className="h-5 w-5 text-blue-500 shrink-0" />
        </div>
      )}
    </div>
  )
}

// ─── Info Field ───────────────────────────────────────────────────

function InfoField({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string | string[] | null | undefined }) {
  const items = Array.isArray(value) ? value.filter(Boolean) : value ? [value] : []
  return (
    <div className="flex items-start gap-2">
      <Icon className="h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0" />
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{label}</div>
        {items.length === 0 ? (
          <div className="text-muted-foreground/50">—</div>
        ) : items.length === 1 ? (
          <div className="text-foreground">{items[0]}</div>
        ) : (
          <div className="space-y-0.5">
            {items.map((v, i) => (
              <div key={i} className="text-foreground leading-tight">{v}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── CNP → Birthdate extraction ───────────────────────────────────

function birthdateFromCnp(cnp: string): string | null {
  if (cnp.length !== 13 || !/^\d{13}$/.test(cnp)) return null
  const s = parseInt(cnp[0], 10)
  const yy = parseInt(cnp.substring(1, 3), 10)
  const mm = cnp.substring(3, 5)
  const dd = cnp.substring(5, 7)

  let century: number
  if (s === 1 || s === 2) century = 1900
  else if (s === 3 || s === 4) century = 1800
  else if (s === 5 || s === 6) century = 2000
  else return null // 7/8 = foreign residents, 9 = special — skip auto-fill

  const year = century + yy
  const dateStr = `${year}-${mm}-${dd}`
  // Validate it's a real date
  const d = new Date(dateStr)
  if (isNaN(d.getTime()) || d.getMonth() + 1 !== parseInt(mm, 10)) return null
  return dateStr
}

// ─── Signature Section ───────────────────────────────────────────

const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))

function SignatureSection() {
  const { data, refetch } = useQuery({
    queryKey: ['my-signature'],
    queryFn: () => profileApi.getSignature(),
  })
  const saveMutation = useMutation({
    mutationFn: (sig: string) => profileApi.saveSignature(sig),
    onSuccess: () => { toast.success('Signature saved'); refetch() },
  })
  const clearMutation = useMutation({
    mutationFn: () => profileApi.saveSignature(''),
    onSuccess: () => { toast.success('Signature cleared'); refetch() },
  })
  const [editing, setEditing] = useState(false)
  const signature = data?.signature || ''

  return (
    <div className="border-t pt-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground font-medium">Signature</span>
        {signature && !editing && (
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setEditing(true)}>Change</Button>
            <Button variant="ghost" size="sm" className="h-6 text-xs text-destructive" onClick={() => clearMutation.mutate()}>Clear</Button>
          </div>
        )}
      </div>
      {signature && !editing ? (
        <img src={signature} alt="Signature" className="max-h-14 border rounded bg-white p-1" />
      ) : (
        <Suspense fallback={<div className="h-[120px] border rounded animate-pulse bg-muted" />}>
          <SignatureCanvas
            height={120}
            onSave={(base64) => { saveMutation.mutate(base64); setEditing(false) }}
            onClear={() => setEditing(false)}
          />
        </Suspense>
      )}
    </div>
  )
}

// ─── Acorduri Semnate (signed consent documents) ─────────────────

function fmtSignedAt(signedAt: string | null): string {
  if (!signedAt) return 'Nesemnat'
  const d = new Date(signedAt)
  if (Number.isNaN(d.getTime())) return 'Nesemnat'
  return d.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short', year: 'numeric' })
}

function AcorduriSemnateSection() {
  const { data, isLoading } = useQuery({
    queryKey: ['consents', 'mine'],
    queryFn: () => consentsApi.getMine(),
  })
  const documents = data?.documents ?? []

  if (!isLoading && documents.length === 0) return null

  return (
    <div className="border-t pt-3 space-y-2">
      <span className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
        <FileCheck2 className="h-3.5 w-3.5" />
        Acorduri semnate
      </span>
      {isLoading ? (
        <div className="space-y-1.5">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : (
        <div className="space-y-1.5">
          {documents.map((doc) => (
            <div key={doc.doc_key} className="flex items-center justify-between gap-3 text-sm">
              <div className="min-w-0">
                <p className="truncate leading-tight">{doc.title}</p>
                <p className={cn('text-xs leading-tight', doc.signed_at ? 'text-muted-foreground' : 'text-orange-600')}>
                  {doc.signed_at ? `Semnat pe ${fmtSignedAt(doc.signed_at)}` : 'Nesemnat'}
                </p>
              </div>
              <Link
                to={`/app/acord/${doc.doc_key}`}
                className="shrink-0 text-xs font-medium text-primary hover:underline"
              >
                Vezi
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Profile Details Dialog ──────────────────────────────────────

function ProfileDetailsDialog({
  open,
  onOpenChange,
  user,
  orgPaths,
  sincronDepartment,
  onEdit,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  user: NonNullable<ReturnType<typeof profileApi.getSummary> extends Promise<infer T> ? T : never>['user']
  orgPaths: any[]
  sincronDepartment?: string
  onEdit: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
              {user?.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase() || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span>{user?.name}</span>
                {user?.role && <StatusBadge status={user.role} />}
              </div>
              {user?.position && <p className="text-sm font-normal text-muted-foreground">{user.position}</p>}
            </div>
            <Button variant="outline" size="sm" onClick={() => { onOpenChange(false); onEdit() }}>
              <Pencil className="h-3.5 w-3.5 mr-1.5" />
              Edit
            </Button>
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3 text-sm">
            <InfoField icon={Mail} label="Email" value={user?.email} />
            <InfoField icon={Phone} label="Phone" value={user?.phone} />
            <InfoField icon={Building2} label="Department" value={(() => { const depts = orgPaths.map((o: any) => o.sincron_department || o.department).filter(Boolean); return depts.length > 0 ? depts : (sincronDepartment || user?.department); })()} />
            <InfoField icon={Shield} label="Company" value={(() => { const comps = [...new Set(orgPaths.map((o: any) => o.company).filter(Boolean))]; return comps.length > 0 ? comps : user?.company; })()} />
            <InfoField icon={Hash} label="CNP" value={user?.cnp} />
            <InfoField icon={Calendar} label="Birthdate" value={user?.birthdate ? new Date(user.birthdate).toLocaleDateString('ro-RO') : null} />
            <InfoField icon={Briefcase} label="Position" value={user?.position} />
            <InfoField icon={Calendar} label="Contract Start" value={user?.contract_work_date ? new Date(user.contract_work_date).toLocaleDateString('ro-RO') : null} />
          </div>
          <SignatureSection />
          <AcorduriSemnateSection />
          <AnniversaryBanners birthdate={user?.birthdate} contractDate={user?.contract_work_date} name={user?.name ?? ''} />
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─── Edit Profile Dialog ──────────────────────────────────────────

export function EditProfileDialog({
  open,
  onOpenChange,
  user,
  onSaved,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  user: NonNullable<ReturnType<typeof profileApi.getSummary> extends Promise<infer T> ? T : never>['user']
  onSaved: () => void
}) {
  const [form, setForm] = useState<ProfileUpdatePayload>({
    phone: user.phone || '',
    cnp: user.cnp || '',
    birthdate: user.birthdate || '',
    position: user.position || '',
    contract_work_date: user.contract_work_date || '',
  })

  // Contracts from Sincron
  const { data: contractsData } = useQuery({
    queryKey: ['profile', 'contracts'],
    queryFn: () => profileApi.getContracts(),
    staleTime: 10 * 60_000,
    enabled: open,
  })
  const contracts = contractsData?.contracts ?? []

  // Password section state
  const [pwOpen, setPwOpen] = useState(false)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showCurrent, setShowCurrent] = useState(false)
  const [showNew, setShowNew] = useState(false)

  // Reset form when dialog opens with latest user data
  useEffect(() => {
    if (open) {
      setForm({
        phone: user.phone || '',
        cnp: user.cnp || '',
        birthdate: user.birthdate || '',
        position: user.position || '',
        contract_work_date: user.contract_work_date || '',
      })
      setPwOpen(false)
      setCurrentPw('')
      setNewPw('')
      setConfirmPw('')
      setShowCurrent(false)
      setShowNew(false)
    }
  }, [open, user])

  const mutation = useMutation({
    mutationFn: (data: ProfileUpdatePayload) => profileApi.updateProfile(data),
    onSuccess: () => {
      onSaved()
      onOpenChange(false)
    },
  })

  const pwMutation = useMutation({
    mutationFn: () => profileApi.changePassword(currentPw, newPw),
    onSuccess: (data) => {
      if (data.success) {
        toast.success('Password changed')
        setPwOpen(false)
        setCurrentPw('')
        setNewPw('')
        setConfirmPw('')
      }
    },
  })

  const handleSave = () => {
    mutation.mutate(form)
  }

  const pwMatch = newPw === confirmPw
  const pwLong = newPw.length >= 10
  const canSavePw = currentPw.length > 0 && pwLong && pwMatch

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader className="pb-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-bold">
              {user.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase() || '?'}
            </div>
            <div>
              <DialogTitle className="text-base">{user.name}</DialogTitle>
              <p className="text-xs text-muted-foreground">{user.email}</p>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-5 pt-2">
          {/* Info row — read-only chips */}
          <div className="flex flex-wrap gap-2">
            {user.company && <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] text-muted-foreground">{user.company}</span>}
            {user.department && <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] text-muted-foreground">{user.department}</span>}
            {user.position && <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-medium">{user.position}</span>}
          </div>

          {/* Employment Contracts */}
          {contracts.length > 0 && (
            <div className="space-y-2">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Contracts</span>
              <div className="grid gap-2">
                {contracts.map((c, i) => {
                  const startDate = c.start_date ? new Date(c.start_date + 'T00:00').toLocaleDateString('ro-RO') : '—'
                  return (
                    <div key={i} className="flex items-center justify-between rounded-lg border bg-muted/20 px-3 py-2">
                      <div className="min-w-0">
                        <p className="text-xs font-medium truncate">{c.company}</p>
                        <p className="text-[10px] text-muted-foreground">Nr. {c.contract_number || '—'} &middot; {startDate}</p>
                      </div>
                      {c.years_employed != null && (
                        <span className="text-xs font-semibold text-primary tabular-nums shrink-0 ml-3">{c.years_employed} yr</span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Editable fields */}
          <div className="space-y-3">
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">Personal Info</span>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label htmlFor="edit-phone" className="text-[11px]">Phone</Label>
                <Input
                  id="edit-phone"
                  value={form.phone}
                  onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                  placeholder="+40..."
                  className="h-8 text-sm"
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="edit-cnp" className="text-[11px]">CNP</Label>
                <Input
                  id="edit-cnp"
                  value={form.cnp}
                  onChange={(e) => {
                    const cnp = e.target.value
                    setForm((f) => {
                      const next = { ...f, cnp }
                      const extracted = birthdateFromCnp(cnp)
                      if (extracted) next.birthdate = extracted
                      return next
                    })
                  }}
                  placeholder="1234567890123"
                  maxLength={13}
                  className="h-8 text-sm"
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="edit-position" className="text-[11px]">Position</Label>
                <Input
                  id="edit-position"
                  value={form.position}
                  onChange={(e) => setForm((f) => ({ ...f, position: e.target.value }))}
                  placeholder="e.g. Software Engineer"
                  className="h-8 text-sm"
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="edit-birthdate" className="text-[11px]">Birthdate</Label>
                <DateField value={form.birthdate ?? ''} onChange={(v) => setForm((f) => ({ ...f, birthdate: v }))} className="w-full h-8 text-sm" />
              </div>
            </div>
          </div>

          {/* Signature */}
          <SignatureSection />

          {/* Change Password */}
          <div className="border-t pt-3">
            <button
              type="button"
              className="flex items-center gap-2 text-xs font-medium hover:text-foreground text-muted-foreground transition-colors"
              onClick={() => setPwOpen(!pwOpen)}
            >
              <Key className="h-3 w-3" />
              Change Password
              {pwOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
            {pwOpen && (
              <div className="grid grid-cols-3 gap-3 mt-3">
                <div className="grid gap-1">
                  <Label className="text-[11px]">Current Password</Label>
                  <div className="relative">
                    <Input
                      type={showCurrent ? 'text' : 'password'}
                      value={currentPw}
                      onChange={(e) => setCurrentPw(e.target.value)}
                      placeholder="Current password"
                      className="h-8 text-sm"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-0 top-0 h-full px-2 hover:bg-transparent"
                      onClick={() => setShowCurrent(!showCurrent)}
                    >
                      {showCurrent ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                </div>
                <div className="grid gap-1">
                  <Label className="text-[11px]">New Password</Label>
                  <div className="relative">
                    <Input
                      type={showNew ? 'text' : 'password'}
                      value={newPw}
                      onChange={(e) => setNewPw(e.target.value)}
                      placeholder="Min. 10 characters"
                      className="h-8 text-sm"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-0 top-0 h-full px-2 hover:bg-transparent"
                      onClick={() => setShowNew(!showNew)}
                    >
                      {showNew ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                  {newPw.length > 0 && !pwLong && (
                    <p className="text-[10px] text-destructive">Min. 10 characters</p>
                  )}
                </div>
                <div className="grid gap-1">
                  <Label className="text-[11px]">Confirm Password</Label>
                  <Input
                    type={showNew ? 'text' : 'password'}
                    value={confirmPw}
                    onChange={(e) => setConfirmPw(e.target.value)}
                    placeholder="Re-enter password"
                    className="h-8 text-sm"
                  />
                  {confirmPw.length > 0 && !pwMatch && (
                    <p className="text-xs text-destructive">Passwords do not match</p>
                  )}
                  {confirmPw.length > 0 && pwMatch && pwLong && (
                    <p className="text-xs text-green-600 flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" /> Passwords match
                    </p>
                  )}
                </div>
                {pwMutation.isError && (
                  <p className="text-sm text-destructive col-span-3">Current password is incorrect</p>
                )}
                <div className="col-span-3 flex justify-end">
                  <Button size="sm" onClick={() => pwMutation.mutate()} disabled={!canSavePw || pwMutation.isPending}>
                    {pwMutation.isPending ? 'Changing...' : 'Change Password'}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={handleSave} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


// ─── Pontaje Helpers ───────────────────────────────────────────────

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function daysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

function fmtTime(dt: string | null) {
  // Punch times are Romania-local wall-clock stored with a +00:00 zone; format
  // via fmtPunchTime so `new Date` doesn't shift them by the viewer's offset (+3h).
  return fmtPunchTime(dt, { empty: '-' })
}

function fmtDuration(seconds: number | null) {
  if (!seconds || seconds <= 0) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${m}m`
  return `${h}h ${m}m`
}

function fmtDate(dateStr: string) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric', month: 'short' })
}

function netSec(durationSec: number | null, lunchMin: number) {
  if (!durationSec || durationSec <= 0) return 0
  const lunchSec = lunchMin * 60
  return durationSec > lunchSec ? durationSec - lunchSec : durationSec
}

// ─── Quick Check-in Card ───────────────────────────────────────────

function QuickCheckinCard() {
  const qc = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ['checkin', 'status'],
    queryFn: async () => {
      const res = await checkinApi.getStatus()
      return (res as any).data ?? res
    },
    refetchInterval: 60_000,
  })

  const punchMut = useMutation({
    mutationFn: async () => {
      // Try GPS first
      const pos = await new Promise<GeolocationPosition | null>((resolve) => {
        if (!navigator.geolocation) return resolve(null)
        navigator.geolocation.getCurrentPosition(resolve, () => resolve(null), {
          enableHighAccuracy: true, timeout: 5000, maximumAge: 0,
        })
      })
      const payload: { lat?: number; lng?: number; direction?: string } = {}
      if (pos) { payload.lat = pos.coords.latitude; payload.lng = pos.coords.longitude }
      payload.direction = status?.next_direction ?? 'IN'
      const res = await checkinApi.punch(payload)
      return (res as any).data ?? res
    },
    onSuccess: (res) => {
      if (res.success) {
        qc.invalidateQueries({ queryKey: ['checkin', 'status'] })
        qc.invalidateQueries({ queryKey: ['profile', 'pontaje'] })
      }
    },
  })

  if (!status?.mapped) return null

  const dir = status.next_direction ?? 'IN'
  const isIn = dir === 'IN'
  const todayPunchCount = status.punches?.length ?? 0
  const lastPunch = todayPunchCount > 0 ? status.punches[todayPunchCount - 1] : null

  return (
    <Card className={cn(
      'border-2 transition-colors',
      isIn ? 'border-green-500/30 bg-green-500/5' : 'border-red-500/30 bg-red-500/5',
    )}>
      <CardContent className="flex items-center gap-4 p-4">
        <MapPin className={cn('h-8 w-8 shrink-0', isIn ? 'text-green-500' : 'text-red-500')} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">
            {todayPunchCount === 0
              ? 'No punches today'
              : `${todayPunchCount} punch${todayPunchCount !== 1 ? 'es' : ''} today`}
          </p>
          {lastPunch && (
            <p className="text-xs text-muted-foreground">
              Last: {lastPunch.direction} at{' '}
              {fmtPunchTime(lastPunch.event_datetime)}
            </p>
          )}
          {punchMut.isSuccess && punchMut.data?.success && (
            <p className="text-xs text-green-600 font-medium mt-0.5">
              {punchMut.data.direction} at {punchMut.data.time} — {punchMut.data.location}
            </p>
          )}
          {punchMut.isError && (
            <p className="text-xs text-red-500 mt-0.5">Punch failed — try the Check In page</p>
          )}
          {punchMut.isSuccess && !punchMut.data?.success && (
            <p className="text-xs text-red-500 mt-0.5">{punchMut.data?.error}</p>
          )}
        </div>
        <Button
          size="sm"
          className={cn(
            'shrink-0 font-semibold',
            isIn
              ? 'bg-green-600 hover:bg-green-700 text-white'
              : 'bg-red-600 hover:bg-red-700 text-white',
          )}
          onClick={() => punchMut.mutate()}
          disabled={punchMut.isPending}
        >
          {punchMut.isPending ? '...' : isIn ? 'Check In' : 'Check Out'}
        </Button>
      </CardContent>
    </Card>
  )
}

// ─── Pontaje Panel (My Attendance) ─────────────────────────────────

function PontajePanel() {
  const today = todayStr()
  const [chartView, setChartView] = useState<'week' | 'month' | '3m'>('month')

  const { data, isLoading } = useQuery({
    queryKey: ['profile', 'pontaje'],
    queryFn: () => profileApi.getPontaje(),
  })

  const mapped = data?.mapped ?? false
  const employee = data?.employee
  const history: BioStarDayHistory[] = data?.history ?? []
  const todayPunches: BioStarPunchLog[] = data?.today_punches ?? []

  const stats = useMemo(() => {
    if (!history.length) return { daysPresent: 0, avgHours: 0, totalHours: 0, maxHours: 0 }
    const nets = history.map((d) => netSec(d.duration_seconds, d.lunch_break_minutes ?? 60))
    const totalSec = nets.reduce((acc, s) => acc + s, 0)
    const maxSec = Math.max(...nets)
    return {
      daysPresent: history.length,
      avgHours: totalSec / history.length / 3600,
      totalHours: totalSec / 3600,
      maxHours: maxSec / 3600,
    }
  }, [history])

  const chartDays = chartView === 'week' ? 7 : chartView === 'month' ? 30 : 90
  const dailyChartData = useMemo(() => {
    const result: { date: string; label: string; hours: number; expected: number }[] = []
    for (let i = chartDays - 1; i >= 0; i--) {
      const dateStr = daysAgo(i)
      const d = new Date(dateStr + 'T00:00:00')
      const dow = d.getDay()
      if (dow === 0 || dow === 6) continue
      const found = history.find((h) => h.date === dateStr)
      const net = found ? netSec(found.duration_seconds, found.lunch_break_minutes ?? 60) : 0
      const expected = found?.working_hours ?? employee?.working_hours ?? 8
      result.push({
        date: dateStr,
        label: chartView === 'week'
          ? d.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric' })
          : d.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' }),
        hours: net / 3600,
        expected: Number(expected),
      })
    }
    return result
  }, [history, chartDays, chartView, employee?.working_hours])

  const last7 = useMemo(() => {
    const days: BioStarDayHistory[] = []
    for (let i = 0; i < 7; i++) {
      const dateStr = daysAgo(i)
      const found = history.find((h) => h.date === dateStr)
      if (found) {
        days.push(found)
      } else {
        days.push({ date: dateStr, first_punch: '', last_punch: '', total_punches: 0, duration_seconds: null })
      }
    }
    return days
  }, [history])

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="space-y-3">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!mapped) {
    return (
      <Card>
        <CardContent className="p-6">
          <EmptyState
            title="No Biostar mapping"
            description="Your account is not linked to a Biostar employee. Contact your administrator to set up the mapping."
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Quick Check-in */}
      <QuickCheckinCard />

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard title="Days Present (90d)" value={stats.daysPresent} icon={<Fingerprint className="h-4 w-4" />} />
        <StatCard title="Avg Hours/Day" value={stats.avgHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Total Hours (90d)" value={stats.totalHours.toFixed(0)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Max Hours" value={stats.maxHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
      </div>

      {/* Daily chart */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Hours per Day</CardTitle>
            <div className="flex gap-1">
              {([['week', 'Week'], ['month', 'Month'], ['3m', '3 Months']] as const).map(([key, label]) => (
                <Button
                  key={key}
                  variant={chartView === key ? 'default' : 'outline'}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setChartView(key)}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {dailyChartData.length === 0 ? (
            <p className="text-sm text-muted-foreground">No attendance data in this period.</p>
          ) : (
            <DailyChart data={dailyChartData} compact={chartView !== 'week'} />
          )}
        </CardContent>
      </Card>

      {/* Last 7 days */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Last 7 Days</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Day</TableHead>
                  <TableHead className="text-center">Check In</TableHead>
                  <TableHead className="text-center">Check Out</TableHead>
                  <TableHead className="text-center">Duration</TableHead>
                  <TableHead className="text-center">Punches</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {last7.map((day) => {
                  const isToday = day.date === today
                  const lunch = day.lunch_break_minutes ?? 60
                  const net = netSec(day.duration_seconds, lunch)
                  const netH = net / 3600
                  const expectedH = day.working_hours ?? 8
                  const isShort = netH > 0 && netH < expectedH
                  const isAbsent = day.total_punches === 0
                  return (
                    <TableRow key={day.date} className={cn(isToday && 'bg-muted/30')}>
                      <TableCell className="font-medium">
                        {fmtDate(day.date)}
                        {isToday && <Badge variant="secondary" className="ml-2 text-[10px]">Today</Badge>}
                      </TableCell>
                      <TableCell className="text-center">
                        {isAbsent ? (
                          <span className="text-sm text-muted-foreground">—</span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-sm">
                            <LogIn className="h-3 w-3 text-green-600" />
                            {fmtTime(day.first_punch)}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {isAbsent ? (
                          <span className="text-sm text-muted-foreground">—</span>
                        ) : day.total_punches === 1 ? (
                          <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-sm">
                            <LogOut className="h-3 w-3 text-red-500" />
                            {fmtTime(day.last_punch)}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {isAbsent ? (
                          <Badge variant="outline" className="text-xs text-muted-foreground">Absent</Badge>
                        ) : day.total_punches === 1 ? (
                          <span className="text-sm text-muted-foreground">—</span>
                        ) : (
                          <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
                            {fmtDuration(net)}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {isAbsent ? (
                          <span className="text-sm text-muted-foreground">—</span>
                        ) : (
                          <Badge variant="secondary" className="text-xs">{day.total_punches}</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Today's punch timeline */}
      {todayPunches.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Today's Punches ({todayPunches.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="relative ml-4 border-l-2 border-muted-foreground/20 pl-4 space-y-2">
              {todayPunches.map((p, i) => (
                <PunchLine key={p.id} punch={p} isFirst={i === 0} isLast={i === todayPunches.length - 1} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ─── Team Pontaje Panel ────────────────────────────────────────────

function TeamPontajePanel() {
  const isMobile = useIsMobile()
  const [search, setSearch] = useState('')
  const [mode, setMode] = useState<'daily' | 'range'>('daily')
  const [date, setDate] = useState(todayStr())
  const [range, setRange] = useState<'week' | 'month' | '3m'>('month')
  const [nodeId, setNodeId] = useState<number | undefined>(undefined)

  const rangeStart = range === 'week' ? daysAgo(7) : range === 'month' ? daysAgo(30) : daysAgo(90)
  const rangeEnd = todayStr()

  const queryParams = mode === 'daily'
    ? { mode: 'daily' as const, date, node_id: nodeId }
    : { mode: 'range' as const, start: rangeStart, end: rangeEnd, node_id: nodeId }

  const { data, isLoading } = useQuery({
    queryKey: ['profile', 'team-pontaje', queryParams],
    queryFn: () => profileApi.getTeamPontaje(queryParams),
  })

  const isManager = data?.is_manager ?? false
  const summary = data?.summary ?? []
  const tree = data?.tree

  // Build filter options from the tree
  const filterOptions = useMemo(() => {
    if (!tree) return []
    const opts: { value: string; label: string; level: number }[] = []
    // L0 companies
    for (const c of tree.companies) {
      opts.push({ value: `company-${c.company_id}`, label: c.name, level: 0 })
    }
    // Organigram nodes — build indented list
    const nodeMap = new Map<number | string, OrgTreeNode>()
    for (const n of tree.nodes) nodeMap.set(n.id, n)

    // Find root nodes (those whose parent_id is not in the visible set)
    const visibleIds = new Set(tree.nodes.map((n) => n.id))
    const roots = tree.nodes.filter((n) => !n.parent_id || !visibleIds.has(n.parent_id))

    const addChildren = (parentId: number | string | null, depth: number) => {
      for (const n of tree.nodes) {
        if (n.parent_id === parentId || (!parentId && roots.includes(n) && depth === 0)) continue
        if (n.parent_id && n.parent_id === parentId) {
          opts.push({ value: String(n.id), label: '\u00A0'.repeat(depth * 2) + n.name, level: n.level })
          addChildren(n.id, depth + 1)
        }
      }
    }

    for (const root of roots) {
      opts.push({ value: String(root.id), label: root.name, level: root.level })
      addChildren(root.id, 1)
    }
    return opts
  }, [tree])

  const filtered = useMemo(() => {
    if (!search) return summary
    const q = search.toLowerCase()
    return summary.filter((r) => {
      const row = r as BioStarDailySummary & BioStarRangeSummary
      return (
        row.name?.toLowerCase().includes(q) ||
        row.email?.toLowerCase().includes(q) ||
        row.mapped_jarvis_user_name?.toLowerCase().includes(q)
      )
    })
  }, [summary, search])

  const shiftDay = (offset: number) => {
    const [y, m, d] = date.split('-').map(Number)
    const dt = new Date(y, m - 1, d + offset)
    const str = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
    if (str <= todayStr()) setDate(str)
  }
  const isToday = date === todayStr()

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="space-y-3">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!isManager) {
    return (
      <Card>
        <CardContent className="p-6">
          <EmptyState
            title="Not a manager"
            description="You don't have team members assigned to you in the organigram."
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="text-base">
              Team Attendance
              <span className="ml-2 text-sm font-normal text-muted-foreground">({filtered.length})</span>
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              {/* Mode toggle */}
              <div className="flex gap-1">
                <Button variant={mode === 'daily' ? 'default' : 'outline'} size="sm" className="h-7 text-xs" onClick={() => setMode('daily')}>
                  Today
                </Button>
                <Button variant={mode === 'range' ? 'default' : 'outline'} size="sm" className="h-7 text-xs" onClick={() => setMode('range')}>
                  Period
                </Button>
              </div>
              {/* Date nav for daily mode */}
              {mode === 'daily' && (
                <div className="flex items-center gap-1">
                  <Button variant="outline" size="sm" className="h-7 w-7 p-0" onClick={() => shiftDay(-1)}>
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </Button>
                  <span className="text-xs font-medium min-w-[90px] text-center">
                    {new Date(date + 'T12:00:00').toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric', month: 'short' })}
                  </span>
                  <Button variant="outline" size="sm" className="h-7 w-7 p-0" onClick={() => shiftDay(1)} disabled={isToday}>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
              {/* Range selector for range mode */}
              {mode === 'range' && (
                <div className="flex gap-1">
                  {([['week', 'Week'], ['month', 'Month'], ['3m', '3 Months']] as const).map(([key, label]) => (
                    <Button
                      key={key}
                      variant={range === key ? 'default' : 'outline'}
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => setRange(key)}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          </div>
          {/* Filter row: node selector + search */}
          <div className="flex flex-wrap items-center gap-2">
            {filterOptions.length > 0 && (
              <Select
                value={nodeId ? String(nodeId) : 'all'}
                onValueChange={(v) => setNodeId(v === 'all' ? undefined : Number(v))}
              >
                <SelectTrigger className="h-8 w-full sm:w-56 text-xs">
                  <SelectValue placeholder="All teams" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All teams</SelectItem>
                  {filterOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <SearchInput
              placeholder="Search team..."
              value={search}
              onChange={setSearch}
              className="w-full sm:w-48"
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {filtered.length === 0 ? (
          <EmptyState title="No team data" description={mode === 'daily' ? 'No attendance data for your team members on this day.' : 'No attendance data for your team members in this period.'} />
        ) : mode === 'daily' ? (
          <TeamDailyTable data={filtered as BioStarDailySummary[]} isMobile={isMobile} date={date} />
        ) : (
          <TeamRangeTable data={filtered as BioStarRangeSummary[]} isMobile={isMobile} />
        )}
      </CardContent>
    </Card>
  )
}

// ── Team Daily Table ──

function groupByCompany<T extends { jarvis_company?: string | null }>(data: T[]): { company: string; rows: T[] }[] {
  const map = new Map<string, T[]>()
  for (const r of data) {
    const key = r.jarvis_company || 'Unmapped'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(r)
  }
  return Array.from(map.entries()).map(([company, rows]) => ({ company, rows }))
}

function TeamDailyTable({ data, isMobile, date }: { data: BioStarDailySummary[]; isMobile: boolean; date: string }) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const groups = useMemo(() => groupByCompany(data), [data])
  const hasMultipleCompanies = groups.length > 1

  const toggle = (id: string) => setExpandedId((prev) => (prev === id ? null : id))

  if (isMobile) {
    return (
      <MobileCardList
        data={data}
        fields={[
          { key: 'name', label: 'Name', isPrimary: true, render: (r) => r.mapped_jarvis_user_name || r.name },
          { key: 'checkin', label: 'Check In', isSecondary: true, render: (r) => r.total_punches > 0 ? fmtTime(r.adjusted_first_punch || r.first_punch) : 'Absent' },
          { key: 'checkout', label: 'Check Out', render: (r) => r.total_punches > 1 ? fmtTime(r.adjusted_last_punch || r.last_punch) : '-' },
          { key: 'duration', label: 'Duration', render: (r) => {
            const net = netSec(r.duration_seconds, r.lunch_break_minutes ?? 60)
            return net > 0 ? fmtDuration(net) : '-'
          }},
          { key: 'corrected', label: 'Corrected', expandOnly: true, render: (r) => r.adjustment_type ? `${r.adjustment_type}` : 'No' },
          { key: 'punches', label: 'Punches', expandOnly: true, render: (r) => String(r.total_punches) },
          { key: 'schedule', label: 'Schedule', expandOnly: true, render: (r) => `${r.schedule_start || '08:00'} - ${r.schedule_end || '17:00'}` },
        ] satisfies MobileCardField<BioStarDailySummary>[]}
        getRowId={(r) => Number(r.biostar_user_id) || 0}
      />
    )
  }

  const renderRow = (r: BioStarDailySummary) => {
    const lunch = r.lunch_break_minutes ?? 60
    const net = netSec(r.duration_seconds, lunch)
    const netH = net / 3600
    const expectedH = Number(r.working_hours ?? 8)
    const isShort = netH > 0 && netH < expectedH
    const isAbsent = r.total_punches === 0
    const isExpanded = expandedId === r.biostar_user_id
    const hasAdjustment = !!r.adjustment_type

    return (
      <>
        <TableRow
          key={r.biostar_user_id}
          className={cn('cursor-pointer hover:bg-muted/50', isExpanded && 'bg-muted/30')}
          onClick={() => !isAbsent && toggle(r.biostar_user_id)}
        >
          <TableCell className="px-2">
            {!isAbsent && (
              <ChevronDown className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform', isExpanded && 'rotate-180')} />
            )}
          </TableCell>
          <TableCell className="font-medium">{r.mapped_jarvis_user_name || r.name}</TableCell>
          <TableCell className="text-sm text-muted-foreground">{r.user_group_name || '-'}</TableCell>
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-sm text-muted-foreground">—</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-sm">
                <LogIn className="h-3 w-3 text-green-600" />
                {fmtTime(hasAdjustment ? r.adjusted_first_punch : r.first_punch)}
                {hasAdjustment && (
                  <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300 ml-0.5">C</Badge>
                )}
              </span>
            )}
          </TableCell>
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-sm text-muted-foreground">—</span>
            ) : r.total_punches === 1 ? (
              <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
            ) : (
              <span className="inline-flex items-center gap-1 text-sm">
                <LogOut className="h-3 w-3 text-red-500" />
                {fmtTime(hasAdjustment ? r.adjusted_last_punch : r.last_punch)}
                {hasAdjustment && (
                  <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300 ml-0.5">C</Badge>
                )}
              </span>
            )}
          </TableCell>
          <TableCell className="text-center">
            {isAbsent ? (
              <Badge variant="outline" className="text-xs text-muted-foreground">Absent</Badge>
            ) : r.total_punches === 1 ? (
              <span className="text-sm text-muted-foreground">—</span>
            ) : (
              <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
                {fmtDuration(net)}
              </span>
            )}
          </TableCell>
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-sm text-muted-foreground">—</span>
            ) : (
              <Badge variant="secondary" className="text-xs">{r.total_punches}</Badge>
            )}
          </TableCell>
          <TableCell className="text-center text-sm text-muted-foreground">
            {r.schedule_start || '08:00'} - {r.schedule_end || '17:00'}
          </TableCell>
        </TableRow>
        {isExpanded && (
          <TableRow key={`${r.biostar_user_id}-detail`}>
            <TableCell colSpan={8} className="p-0">
              <PunchDetailRow biostarUserId={r.biostar_user_id} date={date} row={r} />
            </TableCell>
          </TableRow>
        )}
      </>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8"></TableHead>
            <TableHead>Employee</TableHead>
            <TableHead>Group</TableHead>
            <TableHead className="text-center">Check In</TableHead>
            <TableHead className="text-center">Check Out</TableHead>
            <TableHead className="text-center">Duration</TableHead>
            <TableHead className="text-center">Punches</TableHead>
            <TableHead className="text-center">Schedule</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {hasMultipleCompanies
            ? groups.map((g) => (
                <>
                  <TableRow key={`company-${g.company}`} className="bg-muted/40 hover:bg-muted/40">
                    <TableCell colSpan={8} className="py-1.5 px-4">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        <Building2 className="h-3 w-3" />
                        {g.company} <span className="font-normal">({g.rows.length})</span>
                      </span>
                    </TableCell>
                  </TableRow>
                  {g.rows.map(renderRow)}
                </>
              ))
            : data.map(renderRow)
          }
        </TableBody>
      </Table>
    </div>
  )
}

// ── Punch Detail (expanded row) ──

function PunchDetailRow({ biostarUserId, date, row }: { biostarUserId: string; date: string; row: BioStarDailySummary }) {
  const { data, isLoading } = useQuery({
    queryKey: ['team-pontaje-punches', biostarUserId, date],
    queryFn: () => profileApi.getTeamPontajePunches(biostarUserId, date),
  })

  const punches = data?.punches ?? []
  const hasAdj = !!row.adjustment_type

  return (
    <div className="bg-muted/20 border-t px-6 py-3">
      <div className="flex flex-wrap gap-6">
        {/* Punch log */}
        <div className="flex-1 min-w-[200px]">
          <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">All Punches</p>
          {isLoading ? (
            <div className="space-y-1.5">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-5 w-32" />)}
            </div>
          ) : punches.length === 0 ? (
            <p className="text-xs text-muted-foreground">No punch data</p>
          ) : (
            <div className="space-y-1">
              {punches.map((p, i) => (
                <div key={p.id || i} className="flex items-center gap-2 text-sm">
                  <span className="w-5 text-center text-xs text-muted-foreground">{i + 1}.</span>
                  <Clock className="h-3 w-3 text-muted-foreground" />
                  <span className="font-medium">{fmtTime(p.event_datetime)}</span>
                  {p.device_name && <span className="text-xs text-muted-foreground">({p.device_name})</span>}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Corrected punch info */}
        {hasAdj && (
          <div className="min-w-[200px]">
            <p className="text-xs font-semibold text-blue-600 mb-2 uppercase tracking-wider">Corrected Punch</p>
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <LogIn className="h-3 w-3 text-blue-600" />
                <span className="text-muted-foreground">In:</span>
                <span className="font-medium">{fmtTime(row.adjusted_first_punch)}</span>
                <span className="text-xs text-muted-foreground">(was {fmtTime(row.first_punch)})</span>
              </div>
              <div className="flex items-center gap-2">
                <LogOut className="h-3 w-3 text-blue-600" />
                <span className="text-muted-foreground">Out:</span>
                <span className="font-medium">{fmtTime(row.adjusted_last_punch)}</span>
                <span className="text-xs text-muted-foreground">(was {fmtTime(row.last_punch)})</span>
              </div>
              <div className="flex items-center gap-1 text-xs text-blue-600">
                <Badge variant="outline" className="text-[10px] border-blue-300 text-blue-600">{row.adjustment_type}</Badge>
              </div>
            </div>
          </div>
        )}

        {/* Original times (when corrected) */}
        {!hasAdj && (
          <div className="min-w-[160px]">
            <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">Summary</p>
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <LogIn className="h-3 w-3 text-green-600" />
                <span className="text-muted-foreground">First:</span>
                <span className="font-medium">{fmtTime(row.first_punch)}</span>
              </div>
              <div className="flex items-center gap-2">
                <LogOut className="h-3 w-3 text-red-500" />
                <span className="text-muted-foreground">Last:</span>
                <span className="font-medium">{fmtTime(row.last_punch)}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Team Range Table ──

function TeamRangeTable({ data, isMobile }: { data: BioStarRangeSummary[]; isMobile: boolean }) {
  const groups = useMemo(() => groupByCompany(data), [data])
  const hasMultipleCompanies = groups.length > 1

  if (isMobile) {
    return (
      <MobileCardList
        data={data}
        fields={[
          { key: 'name', label: 'Name', isPrimary: true, render: (r) => r.mapped_jarvis_user_name || r.name },
          { key: 'days', label: 'Days Present', isSecondary: true, render: (r) => `${r.days_present} days` },
          { key: 'avg', label: 'Avg Hours/Day', render: (r) => {
            const lunch = r.lunch_break_minutes ?? 60
            const avgNet = r.avg_duration_seconds ? netSec(r.avg_duration_seconds, lunch * 60) / 3600 : 0
            return avgNet > 0 ? `${avgNet.toFixed(1)}h` : '-'
          }},
          { key: 'total', label: 'Total Hours', render: (r) => {
            const lunch = r.lunch_break_minutes ?? 60
            const totalNet = r.total_duration_seconds
              ? (r.total_duration_seconds - r.days_present * lunch * 60) / 3600
              : 0
            return totalNet > 0 ? `${totalNet.toFixed(0)}h` : '-'
          }},
          { key: 'group', label: 'Group', expandOnly: true, render: (r) => r.user_group_name || '-' },
          { key: 'schedule', label: 'Schedule', expandOnly: true, render: (r) => `${r.schedule_start || '08:00'} - ${r.schedule_end || '17:00'}` },
        ] satisfies MobileCardField<BioStarRangeSummary>[]}
        getRowId={(r) => Number(r.biostar_user_id) || 0}
      />
    )
  }

  const renderRow = (r: BioStarRangeSummary) => {
    const lunch = r.lunch_break_minutes ?? 60
    const avgNet = r.avg_duration_seconds
      ? netSec(r.avg_duration_seconds, lunch * 60) / 3600
      : 0
    const totalNet = r.total_duration_seconds
      ? (r.total_duration_seconds - r.days_present * lunch * 60) / 3600
      : 0
    const expectedH = Number(r.working_hours ?? 8)
    const isShort = avgNet > 0 && avgNet < expectedH

    return (
      <TableRow key={r.biostar_user_id}>
        <TableCell className="font-medium">{r.mapped_jarvis_user_name || r.name}</TableCell>
        <TableCell className="text-sm text-muted-foreground">{r.user_group_name || '-'}</TableCell>
        <TableCell className="text-center">
          <Badge variant="secondary" className="text-xs">{r.days_present}</Badge>
        </TableCell>
        <TableCell className="text-center">
          <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
            {avgNet > 0 ? `${avgNet.toFixed(1)}h` : '-'}
          </span>
        </TableCell>
        <TableCell className="text-center text-sm">{totalNet > 0 ? `${totalNet.toFixed(0)}h` : '-'}</TableCell>
        <TableCell className="text-center text-sm text-muted-foreground">
          {r.schedule_start || '08:00'} - {r.schedule_end || '17:00'}
        </TableCell>
      </TableRow>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Employee</TableHead>
            <TableHead>Group</TableHead>
            <TableHead className="text-center">Days Present</TableHead>
            <TableHead className="text-center">Avg Hours/Day</TableHead>
            <TableHead className="text-center">Total Hours</TableHead>
            <TableHead className="text-center">Schedule</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {hasMultipleCompanies
            ? groups.map((g) => (
                <>
                  <TableRow key={`company-${g.company}`} className="bg-muted/40 hover:bg-muted/40">
                    <TableCell colSpan={6} className="py-1.5 px-4">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        <Building2 className="h-3 w-3" />
                        {g.company} <span className="font-normal">({g.rows.length})</span>
                      </span>
                    </TableCell>
                  </TableRow>
                  {g.rows.map(renderRow)}
                </>
              ))
            : data.map(renderRow)
          }
        </TableBody>
      </Table>
    </div>
  )
}

// ─── Daily Bar Chart (SVG) ─────────────────────────────────────────

function DailyChart({ data, compact }: { data: { date: string; label: string; hours: number; expected: number }[]; compact: boolean }) {
  const maxHours = Math.max(...data.map((d) => d.hours), ...data.map((d) => d.expected), 1)
  const w = Math.max(700, data.length * (compact ? 14 : 50))
  const h = 180
  const pad = { t: 16, b: compact ? 30 : 28, l: 32, r: 10 }
  const iw = w - pad.l - pad.r
  const ih = h - pad.t - pad.b

  const barWidth = Math.min(iw / data.length - (compact ? 2 : 4), compact ? 10 : 32)
  const gap = (iw - barWidth * data.length) / (data.length + 1)

  const yMax = Math.ceil(maxHours + 1)
  const ySteps = [0, Math.floor(yMax / 2), yMax]
  const expectedLine = data[0]?.expected ?? 8

  return (
    <div className="overflow-x-auto">
      <svg width={w} viewBox={`0 0 ${w} ${h}`} className="text-foreground" style={{ minWidth: w }}>
        {ySteps.map((v, i) => {
          const y = pad.t + ih - (v / yMax) * ih
          return (
            <g key={i}>
              <line x1={pad.l} x2={w - pad.r} y1={y} y2={y} stroke="currentColor" strokeOpacity={0.08} />
              <text x={pad.l - 4} y={y + 3} textAnchor="end" className="fill-muted-foreground" fontSize={9}>
                {v}h
              </text>
            </g>
          )
        })}
        {expectedLine > 0 && (
          <line
            x1={pad.l}
            x2={w - pad.r}
            y1={pad.t + ih - (expectedLine / yMax) * ih}
            y2={pad.t + ih - (expectedLine / yMax) * ih}
            stroke="hsl(142, 76%, 36%)"
            strokeOpacity={0.3}
            strokeDasharray="4 3"
          />
        )}
        {data.map((d, i) => {
          const x = pad.l + gap + i * (barWidth + gap)
          const barH = (d.hours / yMax) * ih
          const y = pad.t + ih - barH
          const color = d.hours === 0
            ? 'hsl(0, 0%, 80%)'
            : d.hours >= d.expected
              ? 'hsl(142, 76%, 36%)'
              : d.hours >= d.expected * 0.75
                ? 'hsl(38, 92%, 50%)'
                : 'hsl(0, 72%, 51%)'

          return (
            <g key={i}>
              {d.hours === 0 && (
                <rect x={x} y={pad.t + ih - 2} width={barWidth} height={2} rx={1} fill="currentColor" fillOpacity={0.1} />
              )}
              {d.hours > 0 && (
                <rect x={x} y={y} width={barWidth} height={Math.max(barH, 1)} rx={2} fill={color} fillOpacity={0.8} />
              )}
              {(!compact || d.hours > 0) && (
                <text
                  x={x + barWidth / 2}
                  y={d.hours > 0 ? y - 3 : pad.t + ih - 6}
                  textAnchor="middle"
                  className="fill-muted-foreground"
                  fontSize={compact ? 7 : 9}
                >
                  {d.hours > 0 ? d.hours.toFixed(1) : ''}
                </text>
              )}
              <text
                x={x + barWidth / 2}
                y={h - (compact ? 4 : 4)}
                textAnchor="middle"
                className="fill-muted-foreground"
                fontSize={compact ? 6.5 : 8}
                transform={compact ? `rotate(-45, ${x + barWidth / 2}, ${h - 4})` : undefined}
              >
                {d.label}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// ─── Punch Timeline Line ───────────────────────────────────────────

function PunchLine({ punch, isFirst, isLast }: { punch: BioStarPunchLog; isFirst: boolean; isLast: boolean }) {
  const time = fmtPunchTime(punch.event_datetime, { seconds: true })

  const dirIcon = punch.direction === 'IN'
    ? <LogIn className="h-3.5 w-3.5 text-green-600" />
    : punch.direction === 'OUT'
      ? <LogOut className="h-3.5 w-3.5 text-red-500" />
      : <Clock className="h-3.5 w-3.5 text-muted-foreground" />

  return (
    <div className="relative flex items-center gap-3">
      <div className={cn(
        'absolute -left-[22px] top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full border-2 border-background',
        isFirst ? 'bg-green-500' : isLast ? 'bg-red-500' : 'bg-muted-foreground/40',
      )} />
      <span className="font-mono font-medium text-sm w-16">{time}</span>
      <span className="flex items-center gap-1">
        {dirIcon}
        <span className={cn(
          'text-xs font-medium',
          punch.direction === 'IN' ? 'text-green-600' : punch.direction === 'OUT' ? 'text-red-500' : 'text-muted-foreground',
        )}>
          {punch.direction || 'ACCESS'}
        </span>
      </span>
      {punch.device_name && (
        <span className="text-xs text-muted-foreground truncate max-w-[200px]" title={punch.device_name}>
          {punch.device_name}
        </span>
      )}
    </div>
  )
}

// ─── Invoices Panel ─────────────────────────────────────────────────

function InvoicesPanel({ orgDepartments, isOrgResponsable }: { orgDepartments: string[]; isOrgResponsable: boolean }) {
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
  const [perPage, setPerPage] = usePersistedState('profile-invoices-page-size', 25)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editInvoice, setEditInvoice] = useState<Invoice | null>(null)
  const [previewId, setPreviewId] = useState<number | null>(null)

  const isArchivedView = archiveView === 'archived'
  const canEdit = isArchivedView ? false : (user?.can_edit_invoices || (user?.permissions?.['invoices.records.edit'] ?? false) || isOrgResponsable)

  const handleDownloadPdf = async (inv: ProfileInvoice) => {
    const url = inv.drive_link?.startsWith('/efactura/')
      ? `/profile/api/invoices/${inv.id}/pdf`
      : inv.drive_link
    if (!url) return
    // For non-efactura links, open normally
    if (!inv.drive_link?.startsWith('/efactura/')) {
      window.open(url, '_blank', 'noopener')
      return
    }
    // Fetch as blob for reliable Edge/browser download
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
      // Fallback: direct navigation
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

  const uniqueDepts = useMemo(() => [...new Set(orgDepartments)], [orgDepartments])

  const { data, isLoading } = useQuery({
    queryKey: ['profile', 'invoices', { search, department, status, startDate, endDate, page, perPage, archiveView }],
    queryFn: () => profileApi.getInvoices({ search: search || undefined, department: department || undefined, status: status || undefined, start_date: startDate || undefined, end_date: endDate || undefined, page, per_page: perPage, archive_view: archiveView }),
  })

  // Fetch full invoice data when a row is expanded (via profile endpoint — no accounting perm needed)
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

  const filterFields: FilterField[] = useMemo(() => {
    const fields: FilterField[] = [
      { key: 'status', label: 'Status', type: 'select' as const, options: statusOptions },
    ]
    if (uniqueDepts.length > 1) {
      fields.unshift({ key: 'department', label: 'Department', type: 'select' as const, options: uniqueDepts.map(d => ({ value: d, label: d })) })
    }
    return fields
  }, [statusOptions, uniqueDepts])

  const filterValues: Record<string, string> = useMemo(() => ({
    department: department,
    status: status,
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
                      // For per_line invoices, the same logical allocation is replicated
                      // per merged line item index — collapse them so the +N badge and
                      // "split" indicator reflect the real number of distinct destinations.
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
                                <ProfileInvoiceExpansion
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

            <Pagination page={page} totalPages={totalPages} total={total} perPage={perPage} onPageChange={setPage} onPerPageChange={(n) => { setPerPage(n); setPage(1) }} />
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
          invalidateQueryKeys={[['profile', 'invoices'], ['profile', 'invoice-detail'], ['invoices']]}
        />
      )}

      {previewId !== null && (
        <InvoicePreviewModal invoiceId={previewId} onClose={() => setPreviewId(null)} />
      )}
    </Card>
  )
}

function ProfileInvoiceExpansion({
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
  // Collapse merged per-line allocations the same way the Accounting list does,
  // so the Profile invoice view shows merged groups as single rows instead of
  // duplicating the entry per line item index.
  const allocations = (
    isPerLine
      ? (dedupeMergedAllocations(rawAllocations as unknown as never) as unknown as Array<Record<string, unknown>>)
      : rawAllocations
  )
  const effectiveValue = (inv.net_value ?? inv.invoice_value) as number
  const currency = inv.currency as string

  if (isEditing) {
    // Per-line edit is not supported inline in Profile (edit via Edit Invoice
    // modal which uses LineItemAllocations). Fall through to whole-mode editor
    // for the rare case of editing a per-line invoice from Profile inline.
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

  // Per-line invoice: render the grouped read-only view that mirrors the
  // Edit Invoice dialog's merged-group UX (collapsible "N items merged").
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

// ─── HR Events Panel ────────────────────────────────────────────────

function HrEventsPanel() {
  const isMobile = useIsMobile()
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
            Bonuses
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
          <EmptyState title="No bonuses" description="No bonuses assigned to you." />
        ) : (
          <>
            {isMobile ? (
              <MobileCardList
                data={bonuses}
                fields={[
                  { key: 'event_name', label: 'Event', isPrimary: true, render: (b) => b.event_name },
                  { key: 'period', label: 'Period', isSecondary: true, render: (b) => `${String(b.month).padStart(2, '0')}/${b.year}` },
                  { key: 'bonus_net', label: 'Net Bonus', render: (b) => b.bonus_net != null ? <CurrencyDisplay value={b.bonus_net} currency="RON" className="text-xs" /> : '-' },
                  { key: 'bonus_days', label: 'Days', render: (b) => b.bonus_days ?? '-' },
                  { key: 'company', label: 'Company', expandOnly: true, render: (b) => b.company || '-' },
                  { key: 'hours_free', label: 'Hours', expandOnly: true, render: (b) => b.hours_free ?? '-' },
                  { key: 'details', label: 'Details', expandOnly: true, render: (b) => b.details || '-' },
                ] satisfies MobileCardField<ProfileBonus>[]}
                getRowId={(b) => b.id}
              />
            ) : (
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
            )}

            <Pagination page={page} totalPages={totalPages} total={total} perPage={perPage} onPageChange={setPage} onPerPageChange={(n) => { setPerPage(n); setPage(1) }} />
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Sincron Panel ──────────────────────────────────────────────────

const SINCRON_MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const SINCRON_CODE_LABELS: Record<string, { label: string; color: string }> = {
  OZ: { label: 'Work Hours', color: 'text-blue-600 dark:text-blue-400' },
  CO: { label: 'Annual Leave', color: 'text-green-600 dark:text-green-400' },
  CM: { label: 'Medical Leave', color: 'text-red-600 dark:text-red-400' },
  OS: { label: 'Overtime', color: 'text-orange-600 dark:text-orange-400' },
  CIC: { label: 'Child Care', color: 'text-purple-600 dark:text-purple-400' },
  CES: { label: 'Unpaid Leave', color: 'text-gray-600 dark:text-gray-400' },
  DLG: { label: 'Delegation', color: 'text-yellow-600 dark:text-yellow-400' },
  CMS: { label: 'Sick Family', color: 'text-pink-600 dark:text-pink-400' },
}

function SincronPanel() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const { data, isLoading } = useQuery({
    queryKey: ['profile', 'sincron-timesheet', year, month],
    queryFn: () => sincronApi.getMyTimesheet(year, month),
  })

  const ts: SincronTimesheetData | null = data?.data ?? null
  const days = ts?.days ?? {}
  const summary = ts?.summary ?? []
  const employee = ts?.employee

  // All activity codes present this month
  const allCodes = useMemo(() => {
    const codes = new Set<string>()
    Object.values(days).forEach((entries) => entries.forEach((e) => codes.add(e.short_code)))
    const arr = [...codes]
    arr.sort((a, b) => {
      if (a === 'OZ') return -1
      if (b === 'OZ') return 1
      return a.localeCompare(b)
    })
    return arr
  }, [days])

  const sortedDays = useMemo(() => Object.keys(days).sort(), [days])

  // Stats
  const stats = useMemo(() => {
    const oz = summary.find((s) => s.short_code === 'OZ')
    const co = summary.find((s) => s.short_code === 'CO')
    const os = summary.find((s) => s.short_code === 'OS')
    const cm = summary.find((s) => s.short_code === 'CM')
    return {
      workHours: oz?.total_value ?? 0,
      leaveDays: co?.day_count ?? 0,
      overtime: os?.total_value ?? 0,
      sickDays: cm?.day_count ?? 0,
    }
  }, [summary])

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear((y) => y - 1) }
    else setMonth((m) => m - 1)
  }
  function nextMonth() {
    if (month === 12) { setMonth(1); setYear((y) => y + 1) }
    else setMonth((m) => m + 1)
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="space-y-3">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!employee) {
    return (
      <EmptyState
        icon={<FileSpreadsheet className="h-10 w-10" />}
        title="Sincron Not Linked"
        description="Your profile is not mapped to a Sincron employee. Contact your administrator to set up the mapping in Settings > Connectors."
      />
    )
  }

  return (
    <div className="space-y-4">
      {/* Month navigation */}
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={prevMonth}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <h3 className="text-sm font-semibold">
          {SINCRON_MONTHS[month - 1]} {year}
        </h3>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={nextMonth}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Work Hours" value={stats.workHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Leave Days" value={stats.leaveDays} icon={<Calendar className="h-4 w-4" />} />
        <StatCard title="Overtime" value={stats.overtime.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Sick Days" value={stats.sickDays} icon={<Calendar className="h-4 w-4" />} />
      </div>

      {/* Summary badges */}
      {summary.length > 0 && (
        <Card>
          <CardContent className="p-4">
            <div className="flex flex-wrap gap-2">
              {summary.map((s) => (
                <Badge key={s.short_code} variant="outline" className="text-xs px-2.5 py-1">
                  <span className={`font-semibold ${SINCRON_CODE_LABELS[s.short_code]?.color ?? ''}`}>
                    {s.short_code}
                  </span>
                  <span className="ml-1.5 text-muted-foreground">
                    {SINCRON_CODE_LABELS[s.short_code]?.label ?? s.short_code_en ?? s.short_code}
                  </span>
                  <span className="ml-1.5 font-medium">
                    {s.total_value.toFixed(s.unit === 'hour' ? 1 : 0)} ({s.day_count}d)
                  </span>
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Daily grid */}
      {sortedDays.length > 0 ? (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-24">Date</TableHead>
                    <TableHead className="w-12">Day</TableHead>
                    {allCodes.map((c) => (
                      <TableHead key={c} className="text-center">
                        <span className={`text-xs font-semibold ${SINCRON_CODE_LABELS[c]?.color ?? ''}`}>{c}</span>
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedDays.map((day) => {
                    const d = new Date(day + 'T00:00:00')
                    const dow = d.getDay()
                    const isWeekend = dow === 0 || dow === 6
                    const entries = days[day]
                    const byCode: Record<string, number> = {}
                    entries.forEach((e) => { byCode[e.short_code] = e.value })

                    return (
                      <TableRow key={day} className={isWeekend ? 'bg-muted/40' : ''}>
                        <TableCell className="tabular-nums text-xs">{day}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {d.toLocaleDateString('ro-RO', { weekday: 'short' })}
                        </TableCell>
                        {allCodes.map((c) => (
                          <TableCell key={c} className="text-center tabular-nums text-sm">
                            {byCode[c] !== undefined
                              ? <span className={SINCRON_CODE_LABELS[c]?.color ?? ''}>{byCode[c].toFixed(byCode[c] % 1 === 0 ? 0 : 1)}</span>
                              : <span className="text-muted-foreground">-</span>}
                          </TableCell>
                        ))}
                      </TableRow>
                    )
                  })}
                  {/* Totals */}
                  <TableRow className="font-semibold border-t-2">
                    <TableCell colSpan={2}>Total</TableCell>
                    {allCodes.map((c) => {
                      const s = summary.find((x) => x.short_code === c)
                      return (
                        <TableCell key={c} className="text-center tabular-nums">
                          {s ? s.total_value.toFixed(s.unit === 'hour' ? 1 : 0) : '-'}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ) : (
        <EmptyState
          icon={<FileSpreadsheet className="h-8 w-8" />}
          title="No Data"
          description={`No timesheet entries for ${SINCRON_MONTHS[month - 1]} ${year}. Data is synced from Sincron HR.`}
        />
      )}
    </div>
  )
}

// ─── Leave Permits Panel ────────────────────────────────────────────

const LEAVE_MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

function LeavePermitsPanel({ userId }: { userId: number }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [showForm, setShowForm] = useState(false)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['connecteam', 'submissions', userId, year, month],
    queryFn: () => connecteamApi.getEmployeeSubmissions(userId, year, month),
  })

  const submissions: ConnecteamSubmission[] = data?.data ?? []

  const prevMonth = () => {
    if (month === 1) { setMonth(12); setYear(y => y - 1) }
    else setMonth(m => m - 1)
  }
  const nextMonth = () => {
    if (month === 12) { setMonth(1); setYear(y => y + 1) }
    else setMonth(m => m + 1)
  }

  return (
    <div className="space-y-4 pt-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={prevMonth}><ChevronLeft className="h-4 w-4" /></Button>
          <span className="text-sm font-medium w-36 text-center">{LEAVE_MONTHS[month - 1]} {year}</span>
          <Button variant="ghost" size="icon" onClick={nextMonth}><ChevronRight className="h-4 w-4" /></Button>
        </div>
        <Button size="sm" onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-1" />New Request
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : submissions.length === 0 ? (
        <EmptyState icon={<ClipboardList className="h-8 w-8" />} title="No Leave Permits" description={`No leave permits found for ${LEAVE_MONTHS[month - 1]} ${year}.`} />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Start</TableHead>
                    <TableHead>End</TableHead>
                    <TableHead>Hours</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Destination</TableHead>
                    <TableHead>Approved By</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Submitted</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {submissions.map((s) => (
                    <TableRow key={`${s.source ?? 'ct'}-${s.id}`}>
                      <TableCell className="font-medium text-sm whitespace-nowrap">
                        {s.leave_date ? new Date(s.leave_date).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' }) : '-'}
                      </TableCell>
                      <TableCell className="text-sm">{s.leave_start_time ?? '-'}</TableCell>
                      <TableCell className="text-sm">{s.leave_end_time ?? '-'}</TableCell>
                      <TableCell className="text-sm font-medium">{s.leave_hours != null ? `${s.leave_hours}h` : '-'}</TableCell>
                      <TableCell className="text-sm max-w-48 truncate" title={s.leave_reason ?? ''}>
                        {s.leave_reason ?? '-'}
                      </TableCell>
                      <TableCell className="text-sm">{s.leave_destination ?? '-'}</TableCell>
                      <TableCell className="text-sm">{s.approved_by ?? '-'}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn('text-xs',
                          s.source === 'jarvis' ? 'border-blue-200 bg-blue-50 text-blue-700' : 'border-indigo-200 bg-indigo-50 text-indigo-700'
                        )}>
                          {s.source === 'jarvis' ? 'JARVIS' : 'Connecteam'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {s.submission_timestamp ? new Date(s.submission_timestamp).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {showForm && (
        <InvoireForm
          onClose={() => setShowForm(false)}
          onSubmitted={() => queryClient.invalidateQueries({ queryKey: ['connecteam', 'submissions', userId] })}
        />
      )}
    </div>
  )
}

// ─── Activity Panel (kept for potential future use) ─────────────────

export function ActivityPanel() {
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
