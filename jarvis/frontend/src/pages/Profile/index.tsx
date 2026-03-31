import React, { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
  ChevronDown,
  BarChart3,
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { EmptyState } from '@/components/shared/EmptyState'
import { SearchInput } from '@/components/shared/SearchInput'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { profileApi, type ProfileUpdatePayload } from '@/api/profile'
import { invoicesApi } from '@/api/invoices'
import { checkinApi } from '@/api/checkin'
import { usersApi } from '@/api/users'
import { useAuth } from '@/hooks/useAuth'
import { AllocationEditor, allocationsToRows, rowsToApiPayload } from '@/pages/Accounting/AllocationEditor'
import { toast } from 'sonner'
import { cn, usePersistedState } from '@/lib/utils'
import type { ProfileInvoice, ProfileActivity, ProfileBonus, OrgTreeNode } from '@/types/profile'
import type { BioStarDayHistory, BioStarPunchLog, BioStarDailySummary, BioStarRangeSummary } from '@/types/biostar'

type Tab = 'invoices' | 'hr-events' | 'pontaje' | 'team-pontaje' | 'activity'

const tabs: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: 'invoices', label: 'My Invoices', icon: FileText },
  { key: 'hr-events', label: 'HR Events', icon: Gift },
  { key: 'pontaje', label: 'Pontaje', icon: Fingerprint },
  { key: 'team-pontaje', label: 'Team Pontaje', icon: Users },
  { key: 'activity', label: 'Activity Log', icon: Activity },
]

export default function Profile() {
  const isMobile = useIsMobile()
  const [activeTab, setActiveTab] = useTabParam<Tab>('invoices')
  const [showStats, setShowStats] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [passwordOpen, setPasswordOpen] = useState(false)

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

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Profile"
        breadcrumbs={[{ label: 'My Profile' }]}
        actions={
          <Button variant="ghost" size="icon" className={showStats ? 'bg-muted' : ''} onClick={() => setShowStats(s => !s)} title="Toggle stats">
            <BarChart3 className="h-4 w-4" />
          </Button>
        }
      />

      {/* User Info Card */}
      <Card>
        <CardContent className="p-6">
          {isLoading ? (
            <div className="space-y-3">
              <div className="flex items-center gap-4">
                <Skeleton className="h-16 w-16 rounded-full shrink-0" />
                <div className="space-y-2">
                  <Skeleton className="h-6 w-48" />
                  <Skeleton className="h-4 w-64" />
                </div>
              </div>
              <Skeleton className="h-20 w-full" />
            </div>
          ) : (
            <>
              {/* Top row: avatar + name + edit */}
              <div className="flex items-center gap-4 mb-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-lg font-bold">
                  {user?.name
                    ?.split(' ')
                    .map((n) => n[0])
                    .join('')
                    .slice(0, 2)
                    .toUpperCase() || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold">{user?.name}</h2>
                    {user?.role && <StatusBadge status={user.role} />}
                    {user?.position && <Badge variant="outline">{user.position}</Badge>}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setPasswordOpen(true)}>
                    <Key className="h-3.5 w-3.5 mr-1.5" />
                    Password
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
                    <Pencil className="h-3.5 w-3.5 mr-1.5" />
                    Edit
                  </Button>
                </div>
              </div>

              {/* Info grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-3 text-sm border-t pt-4">
                <InfoField icon={Mail} label="Email" value={user?.email} />
                <InfoField icon={Phone} label="Phone" value={user?.phone} />
                <InfoField icon={Building2} label="Department" value={(() => { const depts = orgPaths.map(o => o.department).filter(Boolean); return depts.length > 0 ? depts : user?.department; })()} />
                <InfoField icon={Shield} label="Company" value={(() => { const comps = [...new Set(orgPaths.map(o => o.company).filter(Boolean))]; return comps.length > 0 ? comps : user?.company; })()} />
                <InfoField icon={Hash} label="CNP" value={user?.cnp} />
                <InfoField icon={Calendar} label="Birthdate" value={user?.birthdate ? new Date(user.birthdate).toLocaleDateString('ro-RO') : null} />
                <InfoField icon={Briefcase} label="Position" value={user?.position} />
                <InfoField icon={Calendar} label="Contract Start" value={user?.contract_work_date ? new Date(user.contract_work_date).toLocaleDateString('ro-RO') : null} />
              </div>

              {/* Anniversary banners */}
              <AnniversaryBanners birthdate={user?.birthdate} contractDate={user?.contract_work_date} name={user?.name ?? ''} />
            </>
          )}
        </CardContent>
      </Card>

      {/* Edit Profile Dialog */}
      {user && (
        <EditProfileDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          user={user}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ['profile', 'summary'] })}
        />
      )}

      {/* Change Password Dialog */}
      <ChangePasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />

      {/* Stats Row */}
      <div className={`grid grid-cols-2 gap-3 lg:grid-cols-4 ${showStats ? '' : 'hidden'}`}>
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
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
        {isMobile ? (
          <MobileBottomTabs>
            <TabsList className="w-full">
              {tabs.map((tab) => {
                const Icon = tab.icon
                return (
                  <TabsTrigger key={tab.key} value={tab.key}>
                    <Icon className="h-4 w-4" />
                    {tab.label}
                  </TabsTrigger>
                )
              })}
            </TabsList>
          </MobileBottomTabs>
        ) : (
          <TabsList className="w-auto">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <TabsTrigger key={tab.key} value={tab.key}>
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </TabsTrigger>
              )
            })}
          </TabsList>
        )}
      </Tabs>

      {/* Tab Content */}
      {activeTab === 'invoices' && <InvoicesPanel orgDepartments={orgPaths.map(o => o.department).filter(Boolean)} />}
      {activeTab === 'hr-events' && <HrEventsPanel />}
      {activeTab === 'pontaje' && <PontajePanel />}
      {activeTab === 'team-pontaje' && <TeamPontajePanel />}
      {activeTab === 'activity' && <ActivityPanel />}
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

// ─── Edit Profile Dialog ──────────────────────────────────────────

function EditProfileDialog({
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
    }
  }, [open, user])

  const mutation = useMutation({
    mutationFn: (data: ProfileUpdatePayload) => profileApi.updateProfile(data),
    onSuccess: () => {
      onSaved()
      onOpenChange(false)
    },
  })

  const handleSave = () => {
    mutation.mutate(form)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Profile</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="edit-phone">Phone</Label>
            <Input
              id="edit-phone"
              value={form.phone}
              onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              placeholder="+40..."
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="edit-cnp">CNP</Label>
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
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="edit-position">Position</Label>
            <Input
              id="edit-position"
              value={form.position}
              onChange={(e) => setForm((f) => ({ ...f, position: e.target.value }))}
              placeholder="e.g. Software Engineer"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="edit-birthdate">Birthdate</Label>
              <DateField value={form.birthdate ?? ''} onChange={(v) => setForm((f) => ({ ...f, birthdate: v }))} className="w-full" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="edit-contract">Contract Start Date</Label>
              <DateField value={form.contract_work_date ?? ''} onChange={(v) => setForm((f) => ({ ...f, contract_work_date: v }))} className="w-full" />
            </div>
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

// ─── Change Password Dialog ───────────────────────────────────────

function ChangePasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showCurrent, setShowCurrent] = useState(false)
  const [showNew, setShowNew] = useState(false)

  useEffect(() => {
    if (open) { setCurrentPw(''); setNewPw(''); setConfirmPw(''); setShowCurrent(false); setShowNew(false) }
  }, [open])

  const mutation = useMutation({
    mutationFn: () => profileApi.changePassword(currentPw, newPw),
    onSuccess: (data) => {
      if (data.success) {
        onOpenChange(false)
      }
    },
  })

  const pwMatch = newPw === confirmPw
  const pwLong = newPw.length >= 10
  const canSave = currentPw.length > 0 && pwLong && pwMatch

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Change Password</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Current Password</Label>
            <div className="relative">
              <Input
                type={showCurrent ? 'text' : 'password'}
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                placeholder="Enter current password"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                onClick={() => setShowCurrent(!showCurrent)}
              >
                {showCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label>New Password</Label>
            <div className="relative">
              <Input
                type={showNew ? 'text' : 'password'}
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                placeholder="Min. 10 characters"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                onClick={() => setShowNew(!showNew)}
              >
                {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
            {newPw.length > 0 && !pwLong && (
              <p className="text-xs text-destructive">Must be at least 10 characters</p>
            )}
          </div>
          <div className="grid gap-1.5">
            <Label>Confirm New Password</Label>
            <Input
              type={showNew ? 'text' : 'password'}
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              placeholder="Re-enter new password"
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
          {mutation.isError && (
            <p className="text-sm text-destructive">Current password is incorrect</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={!canSave || mutation.isPending}>
            {mutation.isPending ? 'Changing...' : 'Change Password'}
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
  if (!dt) return '-'
  return new Date(dt).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
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
              {new Date(lastPunch.event_datetime).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })}
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
  const time = new Date(punch.event_datetime).toLocaleTimeString('ro-RO', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

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

function InvoicesPanel({ orgDepartments }: { orgDepartments: string[] }) {
  const isMobile = useIsMobile()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [department, setDepartment] = useState('')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = usePersistedState('profile-invoices-page-size', 25)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)

  const canEdit = user?.can_edit_invoices || (user?.permissions?.['invoices.records.edit'] ?? false)

  const uniqueDepts = useMemo(() => [...new Set(orgDepartments)], [orgDepartments])

  const { data, isLoading } = useQuery({
    queryKey: ['profile', 'invoices', { search, department, page, perPage }],
    queryFn: () => profileApi.getInvoices({ search: search || undefined, department: department || undefined, page, per_page: perPage }),
  })

  // Fetch full invoice data when a row is expanded
  const { data: expandedInvoice } = useQuery({
    queryKey: ['invoices', expandedId],
    queryFn: () => invoicesApi.getInvoice(expandedId!),
    enabled: expandedId !== null,
  })

  const saveMutation = useMutation({
    mutationFn: (payload: { invoiceId: number; company: string; rows: import('@/pages/Accounting/AllocationEditor').AllocationRow[] }) =>
      invoicesApi.updateAllocations(payload.invoiceId, {
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

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id)
    if (expandedId === id) setEditingId(null)
  }

  // Deduplicate: multiple allocations rows can share the same invoice_id.
  // We only render expand row after the LAST row for that invoice_id.
  const seenExpanded = new Set<number>()

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">
            My Invoices
            <span className="ml-2 text-sm font-normal text-muted-foreground">({total})</span>
          </CardTitle>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            {uniqueDepts.length > 1 && (
              <Select value={department} onValueChange={(v) => { setDepartment(v === 'all' ? '' : v); setPage(1) }}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="All departments" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All departments</SelectItem>
                  {uniqueDepts.map((d) => (
                    <SelectItem key={d} value={d}>{d}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <SearchInput
              placeholder="Search invoices..."
              value={search}
              onChange={(v) => { setSearch(v); setPage(1) }}
              className="w-full sm:w-64"
            />
          </div>
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
            {isMobile ? (
              <MobileCardList
                data={invoices}
                fields={[
                  { key: 'supplier', label: 'Supplier', isPrimary: true, render: (inv) => inv.supplier },
                  { key: 'invoice_number', label: 'Invoice #', isSecondary: true, render: (inv) => <span className="font-mono">{inv.invoice_number}</span> },
                  { key: 'date', label: 'Date', isSecondary: true, render: (inv) => new Date(inv.invoice_date).toLocaleDateString('ro-RO') },
                  { key: 'value', label: 'Value', render: (inv) => <CurrencyDisplay value={inv.allocation_value} currency={inv.currency} className="text-xs" /> },
                  { key: 'status', label: 'Status', render: (inv) => <StatusBadge status={inv.status} /> },
                  { key: 'company', label: 'Company', expandOnly: true, render: (inv) => inv.company },
                  { key: 'department', label: 'Department', expandOnly: true, render: (inv) => inv.department || '-' },
                  { key: 'percent', label: 'Allocation %', expandOnly: true, render: (inv) => `${inv.allocation_percent}%` },
                ] satisfies MobileCardField<ProfileInvoice>[]}
                getRowId={(inv) => inv.id}
                actions={(inv) => inv.drive_link ? (
                  <a href={inv.drive_link} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-foreground">
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
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
                    {invoices.map((inv: ProfileInvoice, idx: number) => {
                      const isExpanded = expandedId === inv.id
                      // Show expansion row only once per invoice_id (after first occurrence)
                      const showExpansion = isExpanded && !seenExpanded.has(inv.id)
                      if (isExpanded) seenExpanded.add(inv.id)

                      return (
                        <React.Fragment key={`${inv.id}-${idx}`}>
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
                            <TableCell onClick={(e) => e.stopPropagation()}>
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
                          {showExpansion && (
                            <TableRow>
                              <TableCell colSpan={10} className="p-0">
                                <ProfileInvoiceExpansion
                                  invoice={expandedInvoice}
                                  isEditing={editingId === inv.id}
                                  canEdit={canEdit}
                                  onEdit={() => setEditingId(inv.id)}
                                  onCancelEdit={() => setEditingId(null)}
                                  onSave={(company, rows) => saveMutation.mutate({ invoiceId: inv.id, company, rows })}
                                  isSaving={saveMutation.isPending}
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
    </Card>
  )
}

function ProfileInvoiceExpansion({
  invoice,
  isEditing,
  canEdit,
  onEdit,
  onCancelEdit,
  onSave,
  isSaving,
}: {
  invoice: unknown
  isEditing: boolean
  canEdit: boolean
  onEdit: () => void
  onCancelEdit: () => void
  onSave: (company: string, rows: import('@/pages/Accounting/AllocationEditor').AllocationRow[]) => void
  isSaving: boolean
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

  const allocations = (inv.allocations ?? []) as Array<Record<string, unknown>>
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
      <div className="px-8 py-4 bg-muted/30 flex items-center justify-between">
        <span className="text-sm text-muted-foreground">No allocations</span>
        {canEdit && (
          <Button variant="outline" size="sm" onClick={onEdit}>
            <Pencil className="h-3 w-3 mr-1" /> Add Allocation
          </Button>
        )}
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
