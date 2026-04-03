import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { hrApi } from '@/api/hr'
import { biostarApi } from '@/api/biostar'
import { sincronApi, type SincronTimesheetData } from '@/api/sincron'
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
  User, Building2, Mail, Phone, Fingerprint, FileSpreadsheet,
  Award, ClipboardList, ChevronLeft, ChevronRight, Clock,
  CalendarDays, Timer, Briefcase, ArrowLeft,
} from 'lucide-react'
import { cn } from '@/lib/utils'

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
          <TabsTrigger value="bonuses"><Award className="h-4 w-4 mr-1" />Bonuses</TabsTrigger>
          <TabsTrigger value="forms"><ClipboardList className="h-4 w-4 mr-1" />Forms</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewPanel overview={overview} />
        </TabsContent>
        {bio && (
          <TabsContent value="pontaj">
            <PontajPanel biostarUserId={bio.biostar_user_id} workingHours={bio.working_hours} lunchBreak={bio.lunch_break_minutes} />
          </TabsContent>
        )}
        {sinc && (
          <TabsContent value="timesheet">
            <TimesheetPanel userId={uid} />
          </TabsContent>
        )}
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

function OverviewPanel({ overview }: { overview: NonNullable<Awaited<ReturnType<typeof hrApi.getEmployeeOverview>>['data']> }) {
  const { biostar: bio, sincron: sinc, org, bonuses } = overview

  return (
    <div className="space-y-4 pt-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Bonuses" value={bonuses.count} icon={<Award className="h-4 w-4" />} />
        <StatCard title="Bonus Days" value={bonuses.total_days} icon={<CalendarDays className="h-4 w-4" />} />
        <StatCard title="Form Submissions" value={overview.forms_count} icon={<ClipboardList className="h-4 w-4" />} />
        {bio && <StatCard title="Work Schedule" value={`${bio.working_hours}h/day`} icon={<Clock className="h-4 w-4" />} />}
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
}: {
  biostarUserId: string
  workingHours: number
  lunchBreak: number
}) {
  const now = new Date()
  const [days, setDays] = useState(30)
  const endDate = now.toISOString().split('T')[0]
  const startDate = new Date(now.getTime() - days * 86400000).toISOString().split('T')[0]

  const { data: historyData, isLoading } = useQuery({
    queryKey: ['biostar', 'daily-history', biostarUserId, startDate, endDate],
    queryFn: () => biostarApi.getEmployeeDailyHistory(biostarUserId, startDate, endDate),
  })

  const history = historyData ?? []

  const stats = useMemo(() => {
    const daysPresent = history.filter((d) => (d.duration_seconds ?? 0) > 0).length
    const totalHours = history.reduce((s, d) => s + (d.duration_seconds ?? 0) / 3600, 0)
    const avgHours = daysPresent > 0 ? totalHours / daysPresent : 0
    return { daysPresent, totalHours, avgHours }
  }, [history])

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
                    <TableHead className="text-right">Duration</TableHead>
                    <TableHead className="text-center">Punches</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {history.map((d) => {
                    const dt = new Date(d.date + 'T00:00:00')
                    const isWeekend = dt.getDay() === 0 || dt.getDay() === 6
                    const hours = (d.duration_seconds ?? 0) / 3600
                    const belowNorm = hours > 0 && hours < workingHours * 0.75
                    return (
                      <TableRow key={d.date} className={cn(isWeekend && 'bg-muted/40', belowNorm && 'text-orange-600')}>
                        <TableCell className="tabular-nums text-xs">{d.date}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {dt.toLocaleDateString('ro-RO', { weekday: 'short' })}
                        </TableCell>
                        <TableCell className="text-xs">{d.first_punch ? new Date(d.first_punch).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' }) : '-'}</TableCell>
                        <TableCell className="text-xs">{d.last_punch ? new Date(d.last_punch).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' }) : '-'}</TableCell>
                        <TableCell className="text-right tabular-nums text-xs font-medium">
                          {hours > 0 ? `${hours.toFixed(1)}h` : '-'}
                        </TableCell>
                        <TableCell className="text-center text-xs">{d.total_punches || '-'}</TableCell>
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
