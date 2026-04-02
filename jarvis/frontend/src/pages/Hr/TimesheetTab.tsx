import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { sincronApi, type SincronTeamMember, type SincronTimesheetData } from '@/api/sincron'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import {
  Users, Clock, CalendarDays, Timer, ArrowUpDown,
  ChevronLeft, ChevronRight, FileSpreadsheet,
} from 'lucide-react'

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

interface Props {
  search: string
}

type SortField = 'name' | 'company' | 'total_hours'

export default function TimesheetTab({ search }: Props) {
  const now = new Date()
  const isMobile = useIsMobile()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [detailUser, setDetailUser] = useState<{ id: number; name: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['sincron', 'team-timesheet', year, month],
    queryFn: () => sincronApi.getTeamTimesheet(year, month),
  })

  const team: SincronTeamMember[] = data?.data ?? []
  const isManager = data?.is_manager ?? false

  // Collect all activity codes across team
  const allCodes = useMemo(() => {
    const codes = new Set<string>()
    team.forEach((m) => Object.keys(m.codes).forEach((c) => codes.add(c)))
    // Sort: OZ first, then alphabetically
    const arr = [...codes]
    arr.sort((a, b) => {
      if (a === 'OZ') return -1
      if (b === 'OZ') return 1
      return a.localeCompare(b)
    })
    return arr
  }, [team])

  // Search + sort
  const filtered = useMemo(() => {
    let rows = team
    if (search) {
      const q = search.toLowerCase()
      rows = rows.filter((m) => m.name.toLowerCase().includes(q) || m.company.toLowerCase().includes(q))
    }
    rows = [...rows].sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1
      if (sortField === 'name') return a.name.localeCompare(b.name) * dir
      if (sortField === 'company') return a.company.localeCompare(b.company) * dir
      return (a.total_hours - b.total_hours) * dir
    })
    return rows
  }, [team, search, sortField, sortDir])

  // Stats
  const stats = useMemo(() => {
    const totalOZ = team.reduce((s, m) => s + (m.codes['OZ']?.value ?? 0), 0)
    const totalCO = team.reduce((s, m) => s + (m.codes['CO']?.days ?? 0), 0)
    const totalOS = team.reduce((s, m) => s + (m.codes['OS']?.value ?? 0), 0)
    return { employees: team.length, workHours: totalOZ, leaveDays: totalCO, overtimeHours: totalOS }
  }, [team])

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortField(field); setSortDir('asc') }
  }

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear((y) => y - 1) }
    else setMonth((m) => m - 1)
  }
  function nextMonth() {
    if (month === 12) { setMonth(1); setYear((y) => y + 1) }
    else setMonth((m) => m + 1)
  }

  const mobileFields: MobileCardField<SincronTeamMember>[] = useMemo(() => [
    { key: 'name', label: 'Name', render: (r) => <span className="font-medium">{r.name}</span> },
    { key: 'company', label: 'Company', render: (r) => <span className="text-xs text-muted-foreground">{r.company}</span> },
    ...allCodes.map((code) => ({
      key: code as keyof SincronTeamMember,
      label: code,
      render: (r: SincronTeamMember) => {
        const v = r.codes[code]
        return v ? <span>{v.value.toFixed(v.unit === 'hour' ? 1 : 0)}</span> : <span className="text-muted-foreground">-</span>
      },
    })),
    { key: 'total_hours', label: 'Total Hours', render: (r) => <span className="font-semibold">{r.total_hours.toFixed(1)}h</span> },
  ], [allCodes])

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  if (!isManager) {
    return <EmptyState icon={<Users className="h-10 w-10" />} title="Team Timesheets" description="You need manager access to view team timesheets." />
  }

  return (
    <div className="space-y-4">
      {/* Month picker */}
      <div className="flex items-center gap-2">
        <Button variant="outline" size="icon" className="h-8 w-8" onClick={prevMonth}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Select value={String(month)} onValueChange={(v) => setMonth(Number(v))}>
          <SelectTrigger className="h-8 w-32 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MONTHS.map((m, i) => (
              <SelectItem key={i + 1} value={String(i + 1)}>{m}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="number"
          className="h-8 w-20 text-xs"
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          min={2020}
          max={2100}
        />
        <Button variant="outline" size="icon" className="h-8 w-8" onClick={nextMonth}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Employees" value={stats.employees} icon={<Users className="h-4 w-4" />} />
        <StatCard title="Work Hours (OZ)" value={stats.workHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Leave Days (CO)" value={stats.leaveDays} icon={<CalendarDays className="h-4 w-4" />} />
        <StatCard title="Overtime (OS)" value={stats.overtimeHours.toFixed(1)} icon={<Timer className="h-4 w-4" />} />
      </div>

      {/* Data */}
      {team.length === 0 ? (
        <EmptyState
          icon={<FileSpreadsheet className="h-10 w-10" />}
          title="No Timesheet Data"
          description={`No Sincron timesheet data found for ${MONTHS[month - 1]} ${year}. Sync timesheets from Settings > Connectors.`}
        />
      ) : isMobile ? (
        <MobileCardList
          data={filtered}
          fields={mobileFields}
          getRowId={(r) => r.user_id}
          onRowClick={(r) => setDetailUser({ id: r.user_id, name: r.name })}
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('name')}>
                      <span className="flex items-center gap-1">Name <ArrowUpDown className="h-3 w-3" /></span>
                    </TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('company')}>
                      <span className="flex items-center gap-1">Company <ArrowUpDown className="h-3 w-3" /></span>
                    </TableHead>
                    {allCodes.map((code) => (
                      <TableHead key={code} className="text-center">
                        <Badge variant="outline" className={`text-xs ${CODE_LABELS[code]?.color ?? ''}`}>
                          {code}
                        </Badge>
                      </TableHead>
                    ))}
                    <TableHead className="text-right cursor-pointer select-none" onClick={() => toggleSort('total_hours')}>
                      <span className="flex items-center justify-end gap-1">Total <ArrowUpDown className="h-3 w-3" /></span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((m) => (
                    <TableRow
                      key={m.user_id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setDetailUser({ id: m.user_id, name: m.name })}
                    >
                      <TableCell className="font-medium">{m.name}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">{m.company}</TableCell>
                      {allCodes.map((code) => {
                        const v = m.codes[code]
                        return (
                          <TableCell key={code} className="text-center tabular-nums">
                            {v ? v.value.toFixed(v.unit === 'hour' ? 1 : 0) : <span className="text-muted-foreground">-</span>}
                          </TableCell>
                        )
                      })}
                      <TableCell className="text-right font-semibold tabular-nums">{m.total_hours.toFixed(1)}h</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Detail dialog */}
      {detailUser && (
        <EmployeeTimesheetDialog
          userId={detailUser.id}
          userName={detailUser.name}
          year={year}
          month={month}
          open={!!detailUser}
          onOpenChange={(open) => { if (!open) setDetailUser(null) }}
        />
      )}
    </div>
  )
}

// ── Employee Detail Dialog ──

function EmployeeTimesheetDialog({
  userId, userName, year, month, open, onOpenChange,
}: {
  userId: number; userName: string; year: number; month: number
  open: boolean; onOpenChange: (open: boolean) => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['sincron', 'employee-timesheet', userId, year, month],
    queryFn: () => sincronApi.getEmployeeTimesheet(userId, year, month),
    enabled: open,
  })

  const ts: SincronTimesheetData | null = data?.data ?? null
  const days = ts?.days ?? {}
  const summary = ts?.summary ?? []

  // Collect all codes from daily data
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

  // Build sorted day list
  const sortedDays = useMemo(() => Object.keys(days).sort(), [days])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{userName} — {MONTHS[month - 1]} {year}</DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3 py-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : !ts || Object.keys(days).length === 0 ? (
          <EmptyState
            icon={<FileSpreadsheet className="h-8 w-8" />}
            title="No Data"
            description="No timesheet entries found for this employee and period."
          />
        ) : (
          <div className="space-y-4">
            {/* Summary cards */}
            <div className="flex flex-wrap gap-2">
              {summary.map((s) => (
                <Badge key={s.short_code} variant="outline" className={`text-xs px-2.5 py-1 ${CODE_LABELS[s.short_code]?.color ?? ''}`}>
                  {s.short_code}: {s.total_value.toFixed(s.unit === 'hour' ? 1 : 0)} ({s.day_count}d)
                </Badge>
              ))}
            </div>

            {/* Daily breakdown */}
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
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
