import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/hooks/useAuth'
import { hrApi } from '@/api/hr'
import { biostarApi } from '@/api/biostar'
import { sincronApi, type SincronTimesheetData } from '@/api/sincron'
import { connecteamApi, type ConnecteamSubmission } from '@/api/connecteam'
import { formsApi } from '@/api/forms'
import { InvoireForm } from '@/components/forms/InvoireForm'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  User, Building2, Mail, Phone, Fingerprint, FileSpreadsheet, FileText,
  Award, ClipboardList, ChevronLeft, ChevronRight, Clock, Plus,
  CalendarDays, Timer, Briefcase, ArrowLeft, CheckCircle2, RotateCcw,
} from 'lucide-react'
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
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const canEditEmployee = user?.permissions?.['hr.employees.edit'] ?? false

  const { data: overviewRes, isLoading } = useQuery({
    queryKey: ['hr', 'employee-overview', uid],
    queryFn: () => hrApi.getEmployeeOverview(uid),
    enabled: !!uid,
  })

  const overview = overviewRes?.data ?? null

  const statusMutation = useMutation({
    mutationFn: (status: string) => hrApi.updateEmployee(uid, { contract_status: status } as Partial<import('@/types/hr').HrEmployee>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hr', 'employee-overview', uid] })
      queryClient.invalidateQueries({ queryKey: ['hr', 'employees'] })
      toast.success('Contract status updated')
    },
    onError: () => toast.error('Failed to update contract status'),
  })

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
                {canEditEmployee ? (
                  <Select
                    value={emp.contract_status ?? 'active'}
                    onValueChange={(v) => statusMutation.mutate(v)}
                    disabled={statusMutation.isPending}
                  >
                    <SelectTrigger className="h-6 w-[120px] text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="suspended">Suspended</SelectItem>
                      <SelectItem value="closed">Closed</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Badge className={cn('text-xs', emp.contract_status === 'suspended' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200' : emp.contract_status === 'closed' ? 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200' : '')}>
                    {emp.contract_status === 'active' ? 'Active' : emp.contract_status === 'suspended' ? 'Suspended' : 'Closed'}
                  </Badge>
                )}
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
          <OverviewPanel overview={overview} userId={uid} />
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

function OverviewPanel({ overview, userId }: { overview: NonNullable<Awaited<ReturnType<typeof hrApi.getEmployeeOverview>>['data']>; userId: number }) {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)

  // Fetch monthly data for selected month
  const { data: monthRes, isLoading: monthLoading } = useQuery({
    queryKey: ['hr', 'employee-overview', userId, year, month],
    queryFn: () => hrApi.getEmployeeOverview(userId, year, month),
    enabled: !!userId,
  })

  const md = monthRes?.data ?? overview
  const { biostar: bio, sincron: sinc, connecteam: ct, org, bonuses, month_stats: ms, leave_balance: lb } = md
  const leaveCodes = (md as any).leave_codes as string[] | undefined
  const monthName = ms ? new Date(ms.year, ms.month - 1).toLocaleString('en-US', { month: 'long', year: 'numeric' }) : ''

  // Hours per day (norma) for day→hours conversion
  const norm = bio?.working_hours ?? 8
  const dToH = (days: number) => Math.round(days * norm * 10) / 10
  const fmtH = (hours: number, days?: number) => {
    const d = days ?? Math.round(hours / norm * 10) / 10
    return d > 0 ? `${hours}h (${d}d)` : `${hours}h`
  }

  // Compute Sincron totals — normalise day-based codes to hours
  const tsEntries = ms ? Object.entries(ms.timesheet) : []
  const overtimeHours = ms?.timesheet?.OSW?.value ?? 0
  const annualLeaveH = dToH(ms?.timesheet?.CO?.value ?? 0)
  const sickLeaveH = dToH(ms?.timesheet?.CM?.value ?? 0)
  const _leaveCodes: string[] = leaveCodes ?? ['CO', 'CM', 'CES', 'CIC', 'CMS', 'DLG']
  const totalLeaveH = tsEntries
    .filter(([code]) => _leaveCodes.includes(code))
    .reduce((s, [, v]) => s + (v.unit === 'hour' ? v.value : dToH(v.value)), 0)

  // Leave balance — in hours
  const lbUsedH = lb ? dToH(lb.annual_used) : 0
  const lbEntH = lb ? dToH(lb.annual_entitlement) : 0
  const lbRemH = lb ? dToH(lb.annual_remaining) : 0
  const annualPct = lb && lb.annual_entitlement > 0 ? Math.min(100, Math.round((lb.annual_used / lb.annual_entitlement) * 100)) : 0

  // Daily chart data
  const dailyData = ms?.daily_hours ?? []
  const missingPunchDays: string[] = ms?.missing_punch_days ?? []
  const missingPunchDayNums = new Set(missingPunchDays.map(d => parseInt(d.split('-')[2], 10)))
  const holidayDayNums = new Set((ms?.holidays ?? []).map((h: { date: string }) => parseInt(h.date.split('-')[2], 10)))

  // Leave donut data — in hours
  const donutSlices = useMemo(() => {
    if (!lb) return []
    const items = [
      { label: 'Used Annual', value: dToH(lb.annual_used), color: '#10b981' },
      { label: 'Remaining', value: dToH(lb.annual_remaining), color: '#d1d5db' },
      { label: 'Sick Leave', value: dToH(lb.sick_leave), color: '#ef4444' },
      { label: 'Unpaid', value: dToH(lb.unpaid_leave), color: '#6b7280' },
      { label: 'Child Care', value: dToH(lb.child_care), color: '#8b5cf6' },
      { label: 'Delegation', value: dToH(lb.delegation), color: '#f59e0b' },
    ].filter(s => s.value > 0)
    return items
  }, [lb, norm])

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
      {/* Month navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={prevMonth}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium capitalize w-44 text-center">{monthName}</span>
          <Button variant="ghost" size="icon" onClick={nextMonth}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        {monthLoading && <span className="text-xs text-muted-foreground animate-pulse">Loading...</span>}
      </div>

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
        {sinc && <StatCard title="Annual Leave" value={fmtH(annualLeaveH)} icon={<CalendarDays className="h-4 w-4" />} />}
        {sinc && <StatCard title="Sick Leave" value={fmtH(sickLeaveH)} icon={<CheckCircle2 className="h-4 w-4" />} />}
      </div>

      {/* Bonuses row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Bonuses" value={bonuses.count} icon={<Award className="h-4 w-4" />} />
        <StatCard title="Bonus Days" value={bonuses.total_days} icon={<CalendarDays className="h-4 w-4" />} />
        <StatCard title="Form Submissions" value={md.forms_count} icon={<ClipboardList className="h-4 w-4" />} />
        {sinc && <StatCard title="Overtime" value={`${overtimeHours}h`} icon={<Timer className="h-4 w-4" />} />}
      </div>

      {/* Missing Punch Alert */}
      {missingPunchDays.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-4 py-3 flex items-start gap-2">
          <Clock className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div className="text-sm text-amber-800 dark:text-amber-200">
            <span className="font-medium">{missingPunchDays.length} missing punch {missingPunchDays.length === 1 ? 'day' : 'days'}</span>
            {' — '}
            {missingPunchDays.map(d => {
              const [y, m, day] = d.split('-').map(Number)
              return new Date(y, m - 1, day).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
            }).join(', ')}
          </div>
        </div>
      )}

      {/* Daily Attendance Chart */}
      {bio && dailyData.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Daily Attendance — {monthName}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <AttendanceBarChart data={dailyData} missingDays={missingPunchDayNums} holidayDays={holidayDayNums} />
          </CardContent>
        </Card>
      )}

      {/* Leave Balance + Donut chart */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {lb && sinc && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">{lb.year} — Leave Balance (YTD)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-6">
                {/* Donut */}
                {donutSlices.length > 0 && (
                  <LeaveDonut slices={donutSlices} centerLabel={`${lbEntH}h`} centerSub="entitlement" />
                )}
                {/* Legend */}
                <div className="flex-1 space-y-1.5 min-w-0">
                  {donutSlices.map((s, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                      <span className="truncate flex-1">{s.label}</span>
                      <span className="tabular-nums font-medium shrink-0">{fmtH(s.value)}</span>
                    </div>
                  ))}
                </div>
              </div>
              {/* Annual Leave progress bar */}
              <div>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-muted-foreground">Annual Leave (CO)</span>
                  <span className="font-medium tabular-nums">{lbUsedH}h / {lbEntH}h <span className="text-muted-foreground text-xs">({lb.annual_used}d / {lb.annual_entitlement}d)</span></span>
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
                  <span>{lbRemH}h remaining ({lb.annual_remaining}d)</span>
                  <span>{annualPct}% used</span>
                </div>
              </div>
              {lb.ytd_permits.count > 0 && (
                <div className="flex items-center justify-between text-sm pt-1 border-t">
                  <span className="text-muted-foreground">Leave Permits (YTD)</span>
                  <span className="font-medium tabular-nums">{lb.ytd_permits.count} permits — {lb.ytd_permits.total_hours}h</span>
                </div>
              )}
            </CardContent>
          </Card>
        )}

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
                        {data.unit === 'hour'
                          ? `${data.value}h`
                          : fmtH(dToH(data.value), data.value)}
                      </span>
                    </div>
                  )
                })}
              {totalLeaveH > 0 && (
                <div className="flex items-center justify-between pt-1 border-t text-xs">
                  <span className="text-muted-foreground font-medium">Total Leave</span>
                  <span className="font-bold">{fmtH(totalLeaveH)}</span>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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

// ── Attendance Bar Chart (SVG) ──

function AttendanceBarChart({ data, missingDays = new Set(), holidayDays = new Set() }: { data: { day: number; date: string; hours: number; expected: number; weekend: boolean; holiday?: boolean; holiday_name?: string | null }[]; missingDays?: Set<number>; holidayDays?: Set<number> }) {
  const maxHours = Math.max(...data.map(d => d.hours), ...data.map(d => d.expected), 1)
  const yMax = Math.ceil(maxHours + 1)
  const w = Math.max(700, data.length * 26)
  const h = 180
  const pad = { t: 14, b: 28, l: 28, r: 8 }
  const iw = w - pad.l - pad.r
  const ih = h - pad.t - pad.b
  const barWidth = Math.min(iw / data.length - 3, 18)
  const gap = (iw - barWidth * data.length) / (data.length + 1)
  const expectedLine = data.find(d => d.expected > 0)?.expected ?? 8
  const ySteps = [0, Math.floor(yMax / 2), yMax]

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${h}`} className="text-foreground w-full" style={{ minWidth: w }}>
        {/* Grid */}
        {ySteps.map((v, i) => {
          const y = pad.t + ih - (v / yMax) * ih
          return (
            <g key={i}>
              <line x1={pad.l} x2={w - pad.r} y1={y} y2={y} stroke="currentColor" strokeOpacity={0.08} />
              <text x={pad.l - 4} y={y + 3} textAnchor="end" className="fill-muted-foreground" fontSize={8}>{v}h</text>
            </g>
          )
        })}
        {/* Expected hours reference */}
        {expectedLine > 0 && (
          <line
            x1={pad.l} x2={w - pad.r}
            y1={pad.t + ih - (expectedLine / yMax) * ih}
            y2={pad.t + ih - (expectedLine / yMax) * ih}
            stroke="hsl(142, 76%, 36%)" strokeOpacity={0.3} strokeDasharray="4 3"
          />
        )}
        {/* Bars */}
        {data.map((d, i) => {
          const x = pad.l + gap + i * (barWidth + gap)
          const barH = (d.hours / yMax) * ih
          const y = pad.t + ih - barH
          const isHoliday = holidayDays.has(d.day) || d.holiday
          const isMissing = missingDays.has(d.day) && !isHoliday
          const color = isHoliday
            ? 'hsl(217, 91%, 60%)'
            : isMissing
              ? 'hsl(0, 72%, 51%)'
              : d.weekend && d.hours === 0
                ? 'hsl(0, 0%, 90%)'
                : d.hours === 0
                  ? 'hsl(0, 0%, 80%)'
                  : d.hours >= d.expected
                    ? 'hsl(142, 76%, 36%)'
                    : d.hours >= d.expected * 0.75
                      ? 'hsl(38, 92%, 50%)'
                      : 'hsl(0, 72%, 51%)'
          return (
            <g key={i}>
              {isHoliday && d.hours === 0 && (
                <rect x={x} y={pad.t + ih - 6} width={barWidth} height={6} rx={1} fill="hsl(217, 91%, 60%)" fillOpacity={0.6} />
              )}
              {isMissing && d.hours === 0 && (
                <rect x={x} y={pad.t + ih - 6} width={barWidth} height={6} rx={1} fill="hsl(0, 72%, 51%)" fillOpacity={0.7} />
              )}
              {!isMissing && !isHoliday && d.hours === 0 && (
                <rect x={x} y={pad.t + ih - 2} width={barWidth} height={2} rx={1} fill="currentColor" fillOpacity={d.weekend ? 0.03 : 0.1} />
              )}
              {d.hours > 0 && (
                <rect x={x} y={y} width={barWidth} height={Math.max(barH, 1)} rx={2} fill={color} fillOpacity={0.8} />
              )}
              {d.hours > 0 && (
                <text x={x + barWidth / 2} y={y - 3} textAnchor="middle" className="fill-muted-foreground" fontSize={7}>
                  {d.hours.toFixed(1)}
                </text>
              )}
              <text
                x={x + barWidth / 2} y={pad.t + ih + 14}
                textAnchor="middle"
                className={d.weekend ? 'fill-muted-foreground/50' : 'fill-muted-foreground'}
                fontSize={8}
              >
                {d.day}
              </text>
            </g>
          )
        })}
      </svg>
      {/* Legend */}
      <div className="flex items-center gap-4 text-[10px] text-muted-foreground mt-1 px-1">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: 'hsl(142, 76%, 36%)' }} />On target</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: 'hsl(38, 92%, 50%)' }} />Below target</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: 'hsl(0, 72%, 51%)' }} />Undertime</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm border" style={{ background: 'transparent' }} />Absent</span>
        {holidayDays.size > 0 && <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: 'hsl(217, 91%, 60%)', opacity: 0.6 }} />Holiday</span>}
        {missingDays.size > 0 && <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: 'hsl(0, 72%, 51%)', opacity: 0.7 }} />Missing punch</span>}
      </div>
    </div>
  )
}

// ── Leave Donut Chart (SVG) ──

function LeaveDonut({ slices, centerLabel, centerSub }: { slices: { label: string; value: number; color: string }[]; centerLabel: string; centerSub: string }) {
  const total = slices.reduce((s, sl) => s + sl.value, 0)
  if (total <= 0) return null

  const size = 120
  const cx = size / 2
  const cy = size / 2
  const r = 40
  const strokeWidth = 18

  let cumulative = 0
  const arcs = slices.map((sl) => {
    const pct = sl.value / total
    const startAngle = cumulative * 2 * Math.PI - Math.PI / 2
    cumulative += pct
    const endAngle = cumulative * 2 * Math.PI - Math.PI / 2
    const largeArc = pct > 0.5 ? 1 : 0
    const x1 = cx + r * Math.cos(startAngle)
    const y1 = cy + r * Math.sin(startAngle)
    const x2 = cx + r * Math.cos(endAngle)
    const y2 = cy + r * Math.sin(endAngle)
    const d = pct >= 0.999
      ? `M ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx + r - 0.001} ${cy}`
      : `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`
    return { ...sl, d }
  })

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      {arcs.map((a, i) => (
        <path key={i} d={a.d} fill="none" stroke={a.color} strokeWidth={strokeWidth} strokeLinecap="butt" />
      ))}
      <text x={cx} y={cy - 4} textAnchor="middle" className="fill-foreground text-sm font-bold">{centerLabel}</text>
      <text x={cx} y={cy + 10} textAnchor="middle" className="fill-muted-foreground" fontSize={9}>{centerSub}</text>
    </svg>
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

  const { data: _histResp, isLoading } = useQuery({
    queryKey: ['biostar', 'daily-history', biostarUserId, startDate, endDate],
    queryFn: () => biostarApi.getEmployeeDailyHistory(biostarUserId, startDate, endDate),
  })

  const history = _histResp?.history ?? []
  const holidays: Set<string> = useMemo(() => new Set(_histResp?.holidays ?? []), [_histResp?.holidays])

  const adjustDayMut = useMutation({
    mutationFn: (day: BioStarDayHistory) => {
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
        original_first_punch: day.first_punch || '',
        original_last_punch: day.last_punch || day.first_punch || '',
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

  // Build full list of weekdays in the period (including absent days)
  const periodDays = useMemo(() => {
    const result: (BioStarDayHistory & { isHoliday?: boolean })[] = []
    for (let i = 0; i < days; i++) {
      const d = new Date(now.getTime() - i * 86400000)
      const dateStr = d.toISOString().split('T')[0]
      const dow = d.getDay()
      if (dow === 0 || dow === 6) continue // skip weekends
      const isHol = holidays.has(dateStr)
      const found = history.find((h) => h.date === dateStr)
      if (found) {
        result.push({ ...found, isHoliday: isHol })
      } else {
        result.push({ date: dateStr, first_punch: '', last_punch: '', total_punches: 0, duration_seconds: null, isHoliday: isHol })
      }
    }
    return result
  }, [history, holidays, days])

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
      ) : periodDays.length === 0 ? (
        <EmptyState icon={<Fingerprint className="h-8 w-8" />} title="No Attendance Data" description="No working days in this period." />
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
                  {periodDays.map((d) => {
                    const dt = new Date(d.date + 'T00:00:00')
                    const isHoliday = d.isHoliday ?? false
                    const isToday = d.date === today
                    const rawSec = d.duration_seconds ?? 0
                    const netSec = rawSec > lunchBreak * 60 ? rawSec - lunchBreak * 60 : rawSec
                    const netH = netSec / 3600
                    const isAbsent = !d.total_punches || d.total_punches === 0
                    const notExited = d.total_punches === 1
                    const isShort = netH > 0 && netH < workingHours
                    return (
                      <TableRow key={d.date} className={cn(isHoliday && 'bg-blue-50 dark:bg-blue-950/20', isToday && 'bg-muted/30')}>
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
                          {isAbsent && isHoliday ? (
                            <Badge variant="outline" className="text-[10px] text-blue-600 border-blue-300">Holiday</Badge>
                          ) : isAbsent && d.adjusted_first_punch ? (
                            <Badge variant="outline" className="text-[10px] text-green-600 border-green-300">Adjusted</Badge>
                          ) : isAbsent ? (
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
                            {!isToday && !isHoliday && (
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

  // Holidays for this month
  const { data: holidayData } = useQuery({
    queryKey: ['holidays', 'year', year],
    queryFn: () => import('@/api/client').then(m => m.api.get<{ success: boolean; holidays: { date: string; name: string; type: string }[] }>(`/api/holidays/year/${year}`)),
  })
  const holidaySet: Set<string> = useMemo(() => {
    const s = new Set<string>()
    const prefix = `${year}-${String(month).padStart(2, '0')}`
    for (const h of holidayData?.holidays ?? []) {
      if (h.date.startsWith(prefix)) s.add(h.date)
    }
    return s
  }, [holidayData, year, month])
  const holidayNames: Record<string, string> = useMemo(() => {
    const m: Record<string, string> = {}
    for (const h of holidayData?.holidays ?? []) m[h.date] = h.name
    return m
  }, [holidayData])

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
                      const isHoliday = holidaySet.has(day)
                      const entries = days[day]
                      const byCode: Record<string, number> = {}
                      entries.forEach((e) => { byCode[e.short_code] = e.value })

                      return (
                        <TableRow key={day} className={cn(isWeekend && 'bg-muted/40', isHoliday && 'bg-blue-50 dark:bg-blue-950/20')}>
                          <TableCell className="tabular-nums text-xs">
                            {day}
                            {isHoliday && (
                              <Badge variant="outline" className="ml-1.5 text-[9px] text-blue-600 border-blue-300 py-0">{holidayNames[day] ?? 'Holiday'}</Badge>
                            )}
                          </TableCell>
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
        <InvoireForm
          onClose={() => setShowForm(false)}
          onSubmitted={() => queryClient.invalidateQueries({ queryKey: ['connecteam', 'submissions', userId] })}
        />
      )}
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
