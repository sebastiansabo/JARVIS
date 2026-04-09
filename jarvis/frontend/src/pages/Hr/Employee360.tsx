import { useState, useMemo, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { hrApi } from '@/api/hr'
import { biostarApi } from '@/api/biostar'
import { sincronApi, type SincronTimesheetData } from '@/api/sincron'
import { connecteamApi, type ConnecteamSubmission } from '@/api/connecteam'
import { formsApi } from '@/api/forms'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  User, Building2, Mail, Phone, Fingerprint, FileSpreadsheet, FileText,
  Award, ClipboardList, ChevronLeft, ChevronRight, Clock, Plus,
  CalendarDays, Timer, Briefcase, ArrowLeft, CheckCircle2, RotateCcw,
} from 'lucide-react'
import { DateField, todayStr, shiftDate } from '@/components/ui/date-field'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { BioStarDayHistory } from '@/types/biostar'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const CODE_LABELS: Record<string, { label: string; color: string }> = {
  OZ: { label: 'Work Hours', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  CO: { label: 'Annual Leave', color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  CM: { label: 'Medical Leave', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
  OS: { label: 'Overtime', color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200' },
  CIC: { label: 'Child Care', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200' },
  CES: { label: 'Unpaid Leave', color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200' },
  DLG: { label: 'Delegation', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
  CMS: { label: 'Sick Family', color: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200' },
}

const NORM_HOURS = 8

export default function Employee360() {
  const { userId } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const uid = Number(userId)

  const { data: overviewRes, isLoading } = useQuery({
    queryKey: ['hr', 'employee-overview', uid],
    queryFn: () => hrApi.getEmployeeOverview(uid),
    enabled: !!uid,
  })

  const overview = overviewRes?.data ?? null

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  if (!overview?.employee) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Employee"
          breadcrumbs={[
            { label: 'HR', href: '/app/hr/pontaje' },
            { label: 'Employees', href: '/app/hr/employees' },
            { label: 'Not Found' },
          ]}
        />
        <EmptyState icon={<User className="h-10 w-10" />} title="Employee Not Found" description="This employee does not exist." />
      </div>
    )
  }

  const emp = overview.employee
  const bio = overview.biostar
  const sinc = overview.sincron
  const ct = overview.connecteam

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title={emp.name}
        breadcrumbs={[
          { label: 'HR', href: '/app/hr/pontaje' },
          { label: 'Employees', href: '/app/hr/employees' },
          { label: emp.name },
        ]}
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate('/app/hr/employees')}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Back
          </Button>
        }
      />

      {/* Header card */}
      <Card>
        <CardContent className="py-4">
          <div className="flex flex-col md:flex-row md:items-start gap-4">
            {/* Avatar */}
            <div className="flex-shrink-0 w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary text-xl font-bold">
              {emp.name.split(' ').map((w: string) => w[0]).join('').slice(0, 2).toUpperCase()}
            </div>
            {/* Info */}
            <div className="flex-1 min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold">{emp.name}</h2>
                {bio && <Badge variant="outline" className="text-xs bg-blue-50 dark:bg-blue-950"><Fingerprint className="h-3 w-3 mr-1" />BioStar</Badge>}
                {sinc && <Badge variant="outline" className="text-xs bg-green-50 dark:bg-green-950"><FileSpreadsheet className="h-3 w-3 mr-1" />Sincron</Badge>}
                {ct && <Badge variant="outline" className="text-xs bg-indigo-50 dark:bg-indigo-950"><FileText className="h-3 w-3 mr-1" />Connecteam</Badge>}
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
                {emp.email && <span className="flex items-center gap-1"><Mail className="h-3.5 w-3.5" />{emp.email}</span>}
                {emp.phone && <span className="flex items-center gap-1"><Phone className="h-3.5 w-3.5" />{emp.phone}</span>}
                {emp.company && <span className="flex items-center gap-1"><Building2 className="h-3.5 w-3.5" />{emp.company}</span>}
                {emp.departments && <span className="flex items-center gap-1"><Briefcase className="h-3.5 w-3.5" />{emp.departments}</span>}
              </div>
              {sinc && (
                <div className="text-xs text-muted-foreground">
                  Contract #{sinc.nr_contract} {sinc.data_incepere_contract && `(from ${sinc.data_incepere_contract})`}
                </div>
              )}
            </div>
            {/* Quick stats */}
            <div className="flex flex-wrap gap-3">
              <div className="text-center px-3">
                <div className="text-2xl font-bold">{overview.bonuses.count}</div>
                <div className="text-xs text-muted-foreground">Bonuses</div>
              </div>
              <div className="text-center px-3">
                <div className="text-2xl font-bold">{overview.forms_count}</div>
                <div className="text-xs text-muted-foreground">Forms</div>
              </div>
              {bio && (
                <div className="text-center px-3">
                  <div className="text-2xl font-bold">{bio.working_hours}h</div>
                  <div className="text-xs text-muted-foreground">Norma</div>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="overview">
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="overview"><User className="h-4 w-4 mr-1" />Overview</TabsTrigger>
          {bio && <TabsTrigger value="pontaj"><Fingerprint className="h-4 w-4 mr-1" />Pontaj</TabsTrigger>}
          {sinc && <TabsTrigger value="timesheet"><FileSpreadsheet className="h-4 w-4 mr-1" />Timesheet</TabsTrigger>}
          <TabsTrigger value="leave-permits"><FileText className="h-4 w-4 mr-1" />Leave Permits</TabsTrigger>
          <TabsTrigger value="bonuses"><Award className="h-4 w-4 mr-1" />Bonuses</TabsTrigger>
          <TabsTrigger value="forms"><ClipboardList className="h-4 w-4 mr-1" />Forms</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewPanel overview={overview} />
        </TabsContent>
        {bio && (
          <TabsContent value="pontaj">
            <PontajPanel
              biostarUserId={bio.biostar_user_id}
              workingHours={bio.working_hours}
              lunchBreak={bio.lunch_break_minutes}
              scheduleStart={bio.schedule_start}
              scheduleEnd={bio.schedule_end}
            />
          </TabsContent>
        )}
        {sinc && (
          <TabsContent value="timesheet">
            <TimesheetPanel userId={uid} />
          </TabsContent>
        )}
        <TabsContent value="leave-permits">
          <LeavePermitsPanel userId={uid} />
        </TabsContent>
        <TabsContent value="bonuses">
          <BonusesPanel userId={uid} />
        </TabsContent>
        <TabsContent value="forms">
          <FormsPanel userId={uid} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ── Overview Panel ──

const TS_CODE_LABELS: Record<string, { label: string; color: string }> = {
  OZ: { label: 'Work Hours', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200' },
  CO: { label: 'Annual Leave', color: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200' },
  CM: { label: 'Medical Leave', color: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200' },
  OSW: { label: 'Overtime', color: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200' },
  CIC: { label: 'Child Care', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200' },
  CES: { label: 'Unpaid Leave', color: 'bg-gray-100 text-gray-800 dark:bg-gray-900/40 dark:text-gray-200' },
  DLG: { label: 'Delegation', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200' },
  CMS: { label: 'Sick Family', color: 'bg-pink-100 text-pink-800 dark:bg-pink-900/40 dark:text-pink-200' },
  X: { label: 'Day Off', color: 'bg-slate-100 text-slate-800 dark:bg-slate-900/40 dark:text-slate-200' },
  ZLC: { label: 'Legal Holiday', color: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200' },
  ZLS: { label: 'Sat/Sun Off', color: 'bg-slate-100 text-slate-600 dark:bg-slate-900/40 dark:text-slate-300' },
}

function OverviewPanel({ overview }: { overview: NonNullable<Awaited<ReturnType<typeof hrApi.getEmployeeOverview>>['data']> }) {
  const { biostar: bio, sincron: sinc, connecteam: ct, org, bonuses, month_stats: ms, leave_balance: lb } = overview
  const monthName = ms ? new Date(ms.year, ms.month - 1).toLocaleString('en-US', { month: 'long', year: 'numeric' }) : ''

  // Compute Sincron totals
  const tsEntries = ms ? Object.entries(ms.timesheet) : []
  const overtimeHours = ms?.timesheet?.OSW?.value ?? 0
  const annualLeaveDays = ms?.timesheet?.CO?.value ?? 0
  const sickLeaveDays = ms?.timesheet?.CM?.value ?? 0
  const totalLeaveDays = tsEntries
    .filter(([code]) => ['CO', 'CM', 'CES', 'CIC', 'CMS', 'DLG'].includes(code))
    .reduce((s, [, v]) => s + v.value, 0)

  // Leave balance
  const annualPct = lb ? Math.min(100, Math.round((lb.annual_used / lb.annual_entitlement) * 100)) : 0

  return (
    <div className="space-y-4 pt-2">
      {/* Monthly stats header */}
      {ms && (
        <div className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
          {monthName} — Monthly Summary
        </div>
      )}

      {/* Top stat cards — attendance & work time */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {bio && <StatCard title="Days Present" value={ms?.attendance.days_present ?? 0} icon={<Fingerprint className="h-4 w-4" />} />}
        {bio && <StatCard title="Hours Worked" value={`${ms?.attendance.total_hours ?? 0}h`} icon={<Clock className="h-4 w-4" />} />}
        {bio && <StatCard title="Avg Daily" value={`${ms?.attendance.avg_daily_hours ?? 0}h`} icon={<Timer className="h-4 w-4" />} />}
        {bio && <StatCard title="Schedule" value={`${bio.working_hours}h/day`} icon={<CalendarDays className="h-4 w-4" />} />}
      </div>

      {/* Leave & absence stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Leave Permits" value={ms?.leave_permits.count ?? 0} icon={<FileText className="h-4 w-4" />} />
        <StatCard title="Permit Hours" value={`${ms?.leave_permits.total_hours ?? 0}h`} icon={<Clock className="h-4 w-4" />} />
        {sinc && <StatCard title="Annual Leave" value={`${annualLeaveDays}d`} icon={<CalendarDays className="h-4 w-4" />} />}
        {sinc && <StatCard title="Sick Leave" value={`${sickLeaveDays}d`} icon={<CheckCircle2 className="h-4 w-4" />} />}
      </div>

      {/* Bonuses row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Bonuses" value={bonuses.count} icon={<Award className="h-4 w-4" />} />
        <StatCard title="Bonus Days" value={bonuses.total_days} icon={<CalendarDays className="h-4 w-4" />} />
        <StatCard title="Form Submissions" value={overview.forms_count} icon={<ClipboardList className="h-4 w-4" />} />
        {sinc && <StatCard title="Overtime" value={`${overtimeHours}h`} icon={<Timer className="h-4 w-4" />} />}
      </div>

      {/* Leave Balance — YTD */}
      {lb && sinc && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">{lb.year} — Leave Balance (YTD)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Annual Leave progress */}
            <div>
              <div className="flex items-center justify-between text-sm mb-1">
                <span className="text-muted-foreground">Annual Leave (CO)</span>
                <span className="font-medium tabular-nums">{lb.annual_used}d / {lb.annual_entitlement}d</span>
              </div>
              <div className="h-2.5 bg-muted rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all',
                    annualPct >= 90 ? 'bg-red-500' : annualPct >= 70 ? 'bg-amber-500' : 'bg-green-500',
                  )}
                  style={{ width: `${annualPct}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-muted-foreground mt-0.5">
                <span>{lb.annual_remaining}d remaining</span>
                <span>{annualPct}% used</span>
              </div>
            </div>

            {/* Other leave types */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-1">
              <div className="text-center p-2 rounded-md bg-red-50 dark:bg-red-950/30">
                <div className="text-lg font-bold text-red-600 dark:text-red-400">{lb.sick_leave}d</div>
                <div className="text-[10px] text-muted-foreground">Sick Leave</div>
              </div>
              <div className="text-center p-2 rounded-md bg-gray-50 dark:bg-gray-900/30">
                <div className="text-lg font-bold">{lb.unpaid_leave}d</div>
                <div className="text-[10px] text-muted-foreground">Unpaid Leave</div>
              </div>
              <div className="text-center p-2 rounded-md bg-purple-50 dark:bg-purple-950/30">
                <div className="text-lg font-bold text-purple-600 dark:text-purple-400">{lb.child_care}d</div>
                <div className="text-[10px] text-muted-foreground">Child Care</div>
              </div>
              <div className="text-center p-2 rounded-md bg-yellow-50 dark:bg-yellow-950/30">
                <div className="text-lg font-bold text-yellow-600 dark:text-yellow-400">{lb.delegation}d</div>
                <div className="text-[10px] text-muted-foreground">Delegation</div>
              </div>
            </div>

            {/* YTD Permits */}
            {lb.ytd_permits.count > 0 && (
              <div className="flex items-center justify-between text-sm pt-1 border-t">
                <span className="text-muted-foreground">Leave Permits (YTD)</span>
                <span className="font-medium tabular-nums">{lb.ytd_permits.count} permits — {lb.ytd_permits.total_hours}h</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Sincron Timesheet Breakdown */}
        {sinc && tsEntries.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Timesheet Breakdown — {monthName}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5 text-sm">
              {tsEntries
                .filter(([code]) => code !== 'ZLS')
                .map(([code, data]) => {
                  const meta = TS_CODE_LABELS[code] || { label: code, color: 'bg-gray-100 text-gray-800' }
                  return (
                    <div key={code} className="flex items-center justify-between py-0.5">
                      <div className="flex items-center gap-2">
                        <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-mono font-bold', meta.color)}>{code}</span>
                        <span className="text-muted-foreground">{meta.label}</span>
                      </div>
                      <span className="font-medium tabular-nums">
                        {data.value}{data.unit === 'hour' ? 'h' : 'd'}
                      </span>
                    </div>
                  )
                })}
              {totalLeaveDays > 0 && (
                <div className="flex items-center justify-between pt-1 border-t text-xs">
                  <span className="text-muted-foreground font-medium">Total Leave Days</span>
                  <span className="font-bold">{totalLeaveDays}d</span>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Organization */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Organization</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <InfoRow label="Company" value={org.company} />
            <InfoRow label="Brand" value={org.brand} />
            <InfoRow label="Department" value={org.department} />
            <InfoRow label="Subdepartment" value={org.subdepartment} />
          </CardContent>
        </Card>

        {/* Connectors */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Connector Mappings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">BioStar</span>
              {bio ? (
                <Badge variant="outline" className="bg-blue-50 dark:bg-blue-950 text-xs">
                  {bio.user_name} ({bio.user_group_name})
                </Badge>
              ) : (
                <Badge variant="secondary" className="text-xs">Not mapped</Badge>
              )}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Sincron</span>
              {sinc ? (
                <Badge variant="outline" className="bg-green-50 dark:bg-green-950 text-xs">
                  {sinc.nume} {sinc.prenume} — {sinc.company_name}
                </Badge>
              ) : (
                <Badge variant="secondary" className="text-xs">Not mapped</Badge>
              )}
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Connecteam</span>
              {ct ? (
                <Badge variant="outline" className="bg-indigo-50 dark:bg-indigo-950 text-xs">
                  {ct.connecteam_user_name} ({ct.submission_count} permits)
                </Badge>
              ) : (
                <Badge variant="secondary" className="text-xs">Not mapped</Badge>
              )}
            </div>
            {sinc && (
              <>
                <InfoRow label="Contract #" value={sinc.nr_contract} />
                <InfoRow label="Contract Start" value={sinc.data_incepere_contract} />
                <InfoRow label="Mapping" value={`${sinc.mapping_method} (${sinc.mapping_confidence}%)`} />
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value || '-'}</span>
    </div>
  )
}

// ── Pontaj Panel ──

function PontajPanel({
  biostarUserId,
  workingHours,
  lunchBreak,
  scheduleStart,
  scheduleEnd,
}: {
  biostarUserId: string
  workingHours: number
  lunchBreak: number
  scheduleStart?: string | null
  scheduleEnd?: string | null
}) {
  const qc = useQueryClient()
  const { user: authUser } = useAuth()
  const showAdjusted = authUser?.can_view_adjusted_punches ?? false
  const canAdjust = authUser?.can_adjust_punches ?? false
  const today = new Date().toISOString().split('T')[0]

  const now = new Date()
  const [days, setDays] = useState(30)
  const endDate = now.toISOString().split('T')[0]
  const startDate = new Date(now.getTime() - days * 86400000).toISOString().split('T')[0]

  const { data: historyData, isLoading } = useQuery({
    queryKey: ['biostar', 'daily-history', biostarUserId, startDate, endDate],
    queryFn: () => biostarApi.getEmployeeDailyHistory(biostarUserId, startDate, endDate),
  })

  const history = historyData ?? []

  const adjustDayMut = useMutation({
    mutationFn: (day: BioStarDayHistory) => {
      if (!day.first_punch) throw new Error('No data')
      const datePart = day.date
      const wh = workingHours ?? 8
      const lunch = lunchBreak ?? 60
      const schedStart = scheduleStart ? scheduleStart.slice(0, 5) : '08:00'
      const whMin = Math.round(wh * 60)
      const targetWorked = whMin + Math.floor(Math.random() * 11)
      const targetSpan = targetWorked + lunch
      const startOffset = Math.floor(Math.random() * 11) - 5
      const [sh, sm] = schedStart.split(':').map(Number)
      const startMin = sh * 60 + sm + startOffset
      const endMin = startMin + targetSpan
      const fmtMins = (m: number) => {
        const hh = Math.floor(m / 60).toString().padStart(2, '0')
        const mm = (m % 60).toString().padStart(2, '0')
        return `${datePart}T${hh}:${mm}:00`
      }
      return biostarApi.adjustEmployee({
        biostar_user_id: biostarUserId,
        date: datePart,
        adjusted_first_punch: fmtMins(startMin),
        adjusted_last_punch: fmtMins(endMin),
        original_first_punch: day.first_punch,
        original_last_punch: day.last_punch || day.first_punch,
        schedule_start: schedStart,
        schedule_end: scheduleEnd?.slice(0, 5),
        lunch_break_minutes: lunch,
        working_hours: wh,
        original_duration_seconds: day.duration_seconds ?? undefined,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'daily-history', biostarUserId] })
      toast.success('Day adjusted')
    },
    onError: () => toast.error('Failed to adjust day'),
  })

  const revertDayMut = useMutation({
    mutationFn: (day: BioStarDayHistory) =>
      biostarApi.revertAdjustment(biostarUserId, day.date),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['biostar', 'daily-history', biostarUserId] })
      toast.success('Adjustment reverted')
    },
    onError: () => toast.error('Failed to revert'),
  })

  const stats = useMemo(() => {
    const lunchSec = lunchBreak * 60
    const daysPresent = history.filter((d) => (d.total_punches ?? 0) >= 2).length
    const totalSec = history.reduce((s, d) => {
      const raw = d.duration_seconds ?? 0
      if (raw <= 0 || (d.total_punches ?? 0) < 2) return s
      return s + (raw > lunchSec ? raw - lunchSec : raw)
    }, 0)
    const totalHours = totalSec / 3600
    const avgHours = daysPresent > 0 ? totalHours / daysPresent : 0
    return { daysPresent, totalHours, avgHours }
  }, [history, lunchBreak])

  const fmtTime = (t: string | null) => t ? new Date(t).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' }) : '—'
  const fmtDur = (sec: number) => {
    if (sec <= 0) return '—'
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    return h === 0 ? `${m}m` : `${h}h ${m}m`
  }

  return (
    <div className="space-y-4 pt-2">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Period:</span>
        {[7, 30, 90].map((d) => (
          <Button key={d} variant={days === d ? 'default' : 'outline'} size="sm" className="h-7 text-xs" onClick={() => setDays(d)}>
            {d}d
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Days Present" value={stats.daysPresent} icon={<CalendarDays className="h-4 w-4" />} />
        <StatCard title="Total Hours" value={stats.totalHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Avg Hours/Day" value={stats.avgHours.toFixed(1)} icon={<Timer className="h-4 w-4" />} />
        <StatCard title="Work Schedule" value={`${workingHours}h (${lunchBreak}m lunch)`} icon={<Briefcase className="h-4 w-4" />} />
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : history.length === 0 ? (
        <EmptyState icon={<Fingerprint className="h-8 w-8" />} title="No Attendance Data" description="No BioStar records for this period." />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Day</TableHead>
                    <TableHead>Check In</TableHead>
                    <TableHead>Check Out</TableHead>
                    {showAdjusted && (
                      <>
                        <TableHead className="text-center">Adj. In</TableHead>
                        <TableHead className="text-center">Adj. Out</TableHead>
                      </>
                    )}
                    <TableHead className="text-right">Duration</TableHead>
                    <TableHead className="text-center">Punches</TableHead>
                    {canAdjust && <TableHead className="w-20" />}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {history.map((d) => {
                    const dt = new Date(d.date + 'T00:00:00')
                    const isWeekend = dt.getDay() === 0 || dt.getDay() === 6
                    const isToday = d.date === today
                    const rawSec = d.duration_seconds ?? 0
                    const netSec = rawSec > lunchBreak * 60 ? rawSec - lunchBreak * 60 : rawSec
                    const netH = netSec / 3600
                    const isAbsent = !d.total_punches || d.total_punches === 0
                    const notExited = d.total_punches === 1
                    const isShort = netH > 0 && netH < workingHours
                    return (
                      <TableRow key={d.date} className={cn(isWeekend && 'bg-muted/40', isToday && 'bg-muted/30')}>
                        <TableCell className="tabular-nums text-xs">
                          {d.date}
                          {isToday && <Badge variant="secondary" className="ml-2 text-[10px]">Today</Badge>}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {dt.toLocaleDateString('ro-RO', { weekday: 'short' })}
                        </TableCell>
                        <TableCell className="text-xs">
                          {isAbsent ? <span className="text-muted-foreground">—</span> : fmtTime(d.first_punch)}
                        </TableCell>
                        <TableCell className="text-xs">
                          {isAbsent ? (
                            <span className="text-muted-foreground">—</span>
                          ) : notExited ? (
                            <Badge variant="outline" className="text-[10px] text-orange-600 border-orange-300">Not exited</Badge>
                          ) : fmtTime(d.last_punch)}
                        </TableCell>
                        {showAdjusted && (
                          <>
                            <TableCell className="text-center text-xs">
                              {d.adjusted_first_punch
                                ? <span className="font-medium text-green-600">{fmtTime(d.adjusted_first_punch)}</span>
                                : <span className="text-muted-foreground">—</span>}
                            </TableCell>
                            <TableCell className="text-center text-xs">
                              {d.adjusted_last_punch
                                ? <span className="font-medium text-green-600">{fmtTime(d.adjusted_last_punch)}</span>
                                : <span className="text-muted-foreground">—</span>}
                            </TableCell>
                          </>
                        )}
                        <TableCell className="text-right tabular-nums text-xs font-medium">
                          {isAbsent ? (
                            <Badge variant="outline" className="text-[10px] text-muted-foreground">Absent</Badge>
                          ) : notExited ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <span className={cn(isShort && 'text-orange-600')}>{fmtDur(netSec)}</span>
                          )}
                        </TableCell>
                        <TableCell className="text-center text-xs">
                          {isAbsent ? <span className="text-muted-foreground">—</span> : <Badge variant="secondary" className="text-xs">{d.total_punches}</Badge>}
                        </TableCell>
                        {canAdjust && (
                          <TableCell className="text-center">
                            {!isAbsent && !isToday && (
                              d.adjusted_first_punch ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 text-[10px] text-muted-foreground"
                                  onClick={() => revertDayMut.mutate(d)}
                                  disabled={revertDayMut.isPending}
                                >
                                  <RotateCcw className="mr-1 h-3 w-3" />
                                  Revert
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-6 text-[10px]"
                                  onClick={() => adjustDayMut.mutate(d)}
                                  disabled={adjustDayMut.isPending}
                                >
                                  <CheckCircle2 className="mr-1 h-3 w-3" />
                                  Adjust
                                </Button>
                              )
                            )}
                          </TableCell>
                        )}
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Timesheet Panel (Sincron) ──

function TimesheetPanel({ userId }: { userId: number }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  const { data, isLoading } = useQuery({
    queryKey: ['sincron', 'employee-timesheet', userId, year, month],
    queryFn: () => sincronApi.getEmployeeTimesheet(userId, year, month),
  })

  const ts: SincronTimesheetData | null = data?.data ?? null
  const days = ts?.days ?? {}
  const summary = ts?.summary ?? []

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

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear((y) => y - 1) }
    else setMonth((m) => m - 1)
  }
  function nextMonth() {
    if (month === 12) { setMonth(1); setYear((y) => y + 1) }
    else setMonth((m) => m + 1)
  }

  return (
    <div className="space-y-4 pt-2">
      {/* Month nav */}
      <div className="flex items-center gap-2">
        <Button variant="outline" size="icon" className="h-8 w-8" onClick={prevMonth}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="text-sm font-medium w-36 text-center">{MONTHS[month - 1]} {year}</span>
        <Button variant="outline" size="icon" className="h-8 w-8" onClick={nextMonth}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : !ts || sortedDays.length === 0 ? (
        <EmptyState icon={<FileSpreadsheet className="h-8 w-8" />} title="No Data" description={`No timesheet data for ${MONTHS[month - 1]} ${year}.`} />
      ) : (
        <>
          {/* Summary badges — show both hours and days */}
          <div className="flex flex-wrap gap-2">
            {summary.map((s) => {
              const isHour = s.unit === 'hour'
              const primary = isHour ? `${s.total_value.toFixed(1)}h` : `${s.total_value.toFixed(0)}d`
              const secondary = isHour ? `${(s.total_value / NORM_HOURS).toFixed(1)}d` : `${(s.total_value * NORM_HOURS).toFixed(0)}h`
              return (
                <Badge key={s.short_code} variant="outline" className={`text-xs px-2.5 py-1 ${CODE_LABELS[s.short_code]?.color ?? ''}`}>
                  {s.short_code}: {primary} ({secondary}) — {s.day_count}d active
                </Badge>
              )
            })}
          </div>

          {/* Daily table */}
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-28">Date</TableHead>
                      <TableHead className="w-16">Day</TableHead>
                      {allCodes.map((c) => (
                        <TableHead key={c} className="text-center">
                          <Badge variant="outline" className={`text-xs ${CODE_LABELS[c]?.color ?? ''}`}>{c}</Badge>
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedDays.map((day) => {
                      const d = new Date(day + 'T00:00:00')
                      const isWeekend = d.getDay() === 0 || d.getDay() === 6
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
                                ? byCode[c].toFixed(byCode[c] % 1 === 0 ? 0 : 1)
                                : <span className="text-muted-foreground">-</span>}
                            </TableCell>
                          ))}
                        </TableRow>
                      )
                    })}
                    {/* Totals row */}
                    <TableRow className="font-semibold border-t-2">
                      <TableCell colSpan={2}>Total</TableCell>
                      {allCodes.map((c) => {
                        const s = summary.find((x) => x.short_code === c)
                        if (!s) return <TableCell key={c} className="text-center">-</TableCell>
                        const isHour = s.unit === 'hour'
                        const primary = isHour ? `${s.total_value.toFixed(1)}h` : `${s.total_value.toFixed(0)}d`
                        const secondary = isHour ? `(${(s.total_value / NORM_HOURS).toFixed(1)}d)` : `(${(s.total_value * NORM_HOURS).toFixed(0)}h)`
                        return (
                          <TableCell key={c} className="text-center tabular-nums">
                            {primary} <span className="text-muted-foreground text-xs">{secondary}</span>
                          </TableCell>
                        )
                      })}
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

// ── Bonuses Panel ──

function BonusesPanel({ userId }: { userId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['hr', 'bonuses', 'employee', userId],
    queryFn: () => hrApi.getBonuses({ employee_id: userId }),
  })

  const bonuses = data ?? []

  return (
    <div className="space-y-4 pt-2">
      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : bonuses.length === 0 ? (
        <EmptyState icon={<Award className="h-8 w-8" />} title="No Bonuses" description="No bonuses recorded for this employee." />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Event</TableHead>
                    <TableHead>Period</TableHead>
                    <TableHead className="text-right">Bonus Days</TableHead>
                    <TableHead className="text-right">Hours Free</TableHead>
                    <TableHead className="text-right">Net Amount</TableHead>
                    <TableHead>Details</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {bonuses.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell className="font-medium text-sm">{b.event_name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {b.participation_start && b.participation_end
                          ? `${b.participation_start} → ${b.participation_end}`
                          : `${b.year}/${String(b.month).padStart(2, '0')}`}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{b.bonus_days ?? '-'}</TableCell>
                      <TableCell className="text-right tabular-nums">{b.hours_free ?? '-'}</TableCell>
                      <TableCell className="text-right tabular-nums">{b.bonus_net != null ? `${b.bonus_net} RON` : '-'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-48 truncate">{b.details ?? '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Leave Permits Panel (Connecteam + JARVIS Form) ──

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
      {/* Header with month nav + new request button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={prevMonth}><ChevronLeft className="h-4 w-4" /></Button>
          <span className="text-sm font-medium w-36 text-center">{MONTHS[month - 1]} {year}</span>
          <Button variant="ghost" size="icon" onClick={nextMonth}><ChevronRight className="h-4 w-4" /></Button>
        </div>
        <Button size="sm" onClick={() => setShowForm(true)}>
          <Plus className="h-4 w-4 mr-1" />New Request
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : submissions.length === 0 ? (
        <EmptyState icon={<FileText className="h-8 w-8" />} title="No Leave Permits" description={`No leave permits found for ${MONTHS[month - 1]} ${year}.`} />
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

      {/* New Leave Request Dialog */}
      {showForm && (
        <LeaveRequestDialog
          onClose={() => setShowForm(false)}
          onSubmitted={() => {
            setShowForm(false)
            queryClient.invalidateQueries({ queryKey: ['connecteam', 'submissions', userId] })
            toast.success('Leave request submitted')
          }}
        />
      )}
    </div>
  )
}

// ── Leave Request Dialog (JARVIS Form) ──

// Generate 30-min interval time slots (07:00 – 19:00)
const TIME_SLOTS = Array.from({ length: 25 }, (_, i) => {
  const totalMin = 7 * 60 + i * 30
  const h = String(Math.floor(totalMin / 60)).padStart(2, '0')
  const m = String(totalMin % 60).padStart(2, '0')
  return `${h}:${m}`
})

function addMinutesToTime(time: string, minutes: number): string {
  const [h, m] = time.split(':').map(Number)
  const total = h * 60 + m + minutes
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

function timeDiffHours(start: string, end: string): number {
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  return (eh * 60 + em - (sh * 60 + sm)) / 60
}

function LeaveRequestDialog({ onClose, onSubmitted }: {
  onClose: () => void
  onSubmitted: () => void
}) {
  const [formData, setFormData] = useState({
    leave_date: '',
    start_time: '',
    end_time: '',
    hours: '',
    reason: '',
    destination: '',
    notes: '',
    approved_by: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [approvers, setApprovers] = useState<{ id: number; name: string }[]>([])

  // Fetch approvers on mount
  useEffect(() => {
    connecteamApi.getApprovers().then(res => {
      setApprovers(res?.data ?? [])
    }).catch(() => {})
  }, [])

  // Auto-calculate hours when start/end time changes
  useEffect(() => {
    if (formData.start_time && formData.end_time) {
      const diff = timeDiffHours(formData.start_time, formData.end_time)
      if (diff > 0) {
        setFormData(p => ({ ...p, hours: String(Math.round(diff * 10) / 10) }))
      } else {
        setFormData(p => ({ ...p, hours: '' }))
      }
    }
  }, [formData.start_time, formData.end_time])

  const handleDurationPreset = (minutes: number) => {
    if (!formData.start_time) return
    const endTime = addMinutesToTime(formData.start_time, minutes)
    if (endTime <= '19:00') {
      setFormData(p => ({ ...p, end_time: endTime }))
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const formsRes = await formsApi.listForms({ search: 'Bilet de Invoire', limit: 1 })
      const forms = formsRes?.forms ?? []
      if (forms.length === 0) {
        toast.error('Leave permission form not found. Contact admin.')
        return
      }
      const formId = forms[0].id

      const answers: Record<string, string> = {
        f_bi_leave_date: formData.leave_date,
        f_bi_start_time: formData.start_time,
        f_bi_end_time: formData.end_time,
        f_bi_hours: formData.hours,
        f_bi_reason: formData.reason,
      }
      if (formData.destination) answers.f_bi_destination = formData.destination
      if (formData.notes) answers.f_bi_notes = formData.notes
      if (formData.approved_by) answers.f_bi_approved_by = formData.approved_by

      await formsApi.submitInternal(formId, answers, 'web_internal')
      onSubmitted()
    } catch (err: any) {
      toast.error(err?.response?.data?.error || 'Failed to submit request')
    } finally {
      setSubmitting(false)
    }
  }

  const reasons = ['Personal', 'Medical', 'Familial', 'Oficial', 'Altul']
  const today = todayStr()
  const tomorrow = shiftDate(today, 1)

  // Filter end_time slots to only show times after start_time
  const endTimeSlots = formData.start_time
    ? TIME_SLOTS.filter(t => t > formData.start_time)
    : TIME_SLOTS

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <Card className="w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <CardHeader>
          <CardTitle className="text-lg">New Leave Request</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Date picker + quick buttons */}
            <div>
              <label className="text-sm font-medium">Data *</label>
              <div className="flex items-center gap-2 mt-1">
                <DateField
                  value={formData.leave_date}
                  onChange={v => setFormData(p => ({ ...p, leave_date: v }))}
                  placeholder="Selectati data"
                  className="flex-1"
                  required
                />
                <button
                  type="button"
                  onClick={() => setFormData(p => ({ ...p, leave_date: today }))}
                  className={cn(
                    'px-3 py-1.5 text-xs rounded-md border transition-colors',
                    formData.leave_date === today
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'hover:bg-accent'
                  )}
                >
                  Today
                </button>
                <button
                  type="button"
                  onClick={() => setFormData(p => ({ ...p, leave_date: tomorrow }))}
                  className={cn(
                    'px-3 py-1.5 text-xs rounded-md border transition-colors',
                    formData.leave_date === tomorrow
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'hover:bg-accent'
                  )}
                >
                  Tomorrow
                </button>
              </div>
            </div>

            {/* Time selectors */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium">Ora de inceput *</label>
                <select
                  required
                  className="w-full mt-1 px-3 py-2 border rounded-md text-sm"
                  value={formData.start_time}
                  onChange={e => setFormData(p => ({ ...p, start_time: e.target.value }))}
                >
                  <option value="">-- : --</option>
                  {TIME_SLOTS.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Ora de sfarsit *</label>
                <select
                  required
                  className="w-full mt-1 px-3 py-2 border rounded-md text-sm"
                  value={formData.end_time}
                  onChange={e => setFormData(p => ({ ...p, end_time: e.target.value }))}
                >
                  <option value="">-- : --</option>
                  {endTimeSlots.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </div>

            {/* Duration presets */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Quick:</span>
              {[
                { label: '30 min', minutes: 30 },
                { label: '1 ora', minutes: 60 },
                { label: '2 ore', minutes: 120 },
              ].map(p => (
                <button
                  key={p.minutes}
                  type="button"
                  disabled={!formData.start_time}
                  onClick={() => handleDurationPreset(p.minutes)}
                  className={cn(
                    'px-2.5 py-1 text-xs rounded-md border transition-colors',
                    !formData.start_time
                      ? 'opacity-40 cursor-not-allowed'
                      : formData.start_time && formData.end_time === addMinutesToTime(formData.start_time, p.minutes)
                        ? 'bg-primary text-primary-foreground border-primary'
                        : 'hover:bg-accent'
                  )}
                >
                  {p.label}
                </button>
              ))}
              {formData.hours && (
                <span className="ml-auto text-sm font-medium">{formData.hours}h</span>
              )}
            </div>

            {/* Reason */}
            <div>
              <label className="text-sm font-medium">Motivul *</label>
              <select required className="w-full mt-1 px-3 py-2 border rounded-md text-sm" value={formData.reason} onChange={e => setFormData(p => ({ ...p, reason: e.target.value }))}>
                <option value="">Selectati motivul</option>
                {reasons.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>

            {/* Destination */}
            <div>
              <label className="text-sm font-medium">Destinatia</label>
              <input type="text" className="w-full mt-1 px-3 py-2 border rounded-md text-sm" placeholder="Unde va deplasati" value={formData.destination} onChange={e => setFormData(p => ({ ...p, destination: e.target.value }))} />
            </div>

            {/* Approver */}
            <div>
              <label className="text-sm font-medium">Aprobat de *</label>
              {approvers.length > 0 ? (
                <select
                  required
                  className="w-full mt-1 px-3 py-2 border rounded-md text-sm"
                  value={formData.approved_by}
                  onChange={e => setFormData(p => ({ ...p, approved_by: e.target.value }))}
                >
                  <option value="">Selectati persoana</option>
                  {approvers.map(a => <option key={a.id} value={a.name}>{a.name}</option>)}
                </select>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">No approvers available</p>
              )}
            </div>

            {/* Notes */}
            <div>
              <label className="text-sm font-medium">Detalii suplimentare</label>
              <textarea className="w-full mt-1 px-3 py-2 border rounded-md text-sm" rows={2} placeholder="Adaugati orice detalii relevante" value={formData.notes} onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))} />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Submitting...' : 'Submit Request'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

// ── Forms Panel ──

function FormsPanel({ userId }: { userId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['forms', 'by-user', userId],
    queryFn: () => formsApi.getUserSubmissions(userId),
  })

  const submissions = data?.submissions ?? []

  const statusColor: Record<string, string> = {
    new: 'bg-blue-100 text-blue-800',
    read: 'bg-gray-100 text-gray-800',
    flagged: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
  }

  return (
    <div className="space-y-4 pt-2">
      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : submissions.length === 0 ? (
        <EmptyState icon={<ClipboardList className="h-8 w-8" />} title="No Form Submissions" description="No form submissions found for this employee." />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Form</TableHead>
                    <TableHead>Submitted</TableHead>
                    <TableHead>Source</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {submissions.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell className="font-medium text-sm">{s.form_name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {s.created_at ? new Date(s.created_at).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-'}
                      </TableCell>
                      <TableCell className="text-xs">{s.source}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`text-xs ${statusColor[s.status] ?? ''}`}>
                          {s.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
