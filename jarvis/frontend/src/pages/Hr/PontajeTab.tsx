import { useState, useMemo, useCallback } from 'react'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import {
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  ArrowUpDown,
  LogIn,
  LogOut,
  Columns3,
  Download,
  Wand2,
  RotateCcw,
  ExternalLink,
  UserCheck,
  UserX,
  DatabaseZap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/shared/EmptyState'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { DateField } from '@/components/ui/date-field'
import { Skeleton } from '@/components/ui/skeleton'
import { biostarApi } from '@/api/biostar'
import { sincronApi } from '@/api/sincron'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { AttendanceRow, BioStarDayHistory } from '@/types/biostar'

type SortField = 'name' | 'company' | 'group' | 'check_in' | 'check_out' | 'duration' | 'punches'
type SortDir = 'asc' | 'desc'

type ColKey = 'group' | 'official_in' | 'official_out' | 'actual_in' | 'actual_out' | 'duration' | 'punches' | 'schedule' | 'company'

const COL_DEFS: { key: ColKey; label: string }[] = [
  { key: 'official_in', label: 'Official In' },
  { key: 'official_out', label: 'Official Out' },
  { key: 'actual_in', label: 'Actual In' },
  { key: 'actual_out', label: 'Actual Out' },
  { key: 'duration', label: 'Duration' },
  { key: 'punches', label: 'Punches' },
  { key: 'schedule', label: 'Schedule' },
  { key: 'company', label: 'Company' },
  { key: 'group', label: 'Group' },
]

const DEFAULT_COLS: ColKey[] = ['official_in', 'official_out', 'duration', 'punches', 'schedule']

function fmtScheduleTime(t: string | null) {
  if (!t) return '08:00'
  return t.slice(0, 5)
}

function randomizeAdjustedTimes(
  datePart: string, scheduleStart: string | null, lunchMin: number, workingHours: number,
): { adjFirst: string; adjLast: string } {
  const whMin = Math.round(workingHours * 60)
  const targetWorked = whMin + Math.floor(Math.random() * 11) // e.g. 480–490
  const targetSpan = targetWorked + lunchMin
  const startOffset = Math.floor(Math.random() * 11) - 5 // -5..+5
  const baseStart = fmtScheduleTime(scheduleStart)
  const [sh, sm] = baseStart.split(':').map(Number)
  const startMin = sh * 60 + sm + startOffset
  const endMin = startMin + targetSpan
  const fmtMins = (m: number) => {
    const clamped = Math.max(0, m)
    const hh = Math.floor(clamped / 60).toString().padStart(2, '0')
    const mm = (clamped % 60).toString().padStart(2, '0')
    return `${datePart}T${hh}:${mm}:00`
  }
  return { adjFirst: fmtMins(startMin), adjLast: fmtMins(endMin) }
}

function fmtTime(dt: string | null) {
  if (!dt) return '—'
  return new Date(dt).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
}

function fmtDuration(seconds: number | null) {
  if (!seconds || seconds <= 0) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${m}m`
  return `${h}h ${m}m`
}

function netSec(durationSec: number | null | undefined, lunchMin: number) {
  const sec = Number(durationSec)
  if (!sec || sec <= 0 || !isFinite(sec)) return 0
  const lunchSec = (Number(lunchMin) || 0) * 60
  return sec > lunchSec ? sec - lunchSec : sec
}

function timeDiffSec(a: string, b: string): number {
  return Math.max(0, (new Date(b).getTime() - new Date(a).getTime()) / 1000)
}

/** Compute effective duration: use adjusted times if available, else raw duration_seconds */
function effectiveSec(d: BioStarDayHistory, lunchMin: number): number {
  if (d.adjusted_first_punch && d.adjusted_last_punch) {
    return netSec(timeDiffSec(d.adjusted_first_punch, d.adjusted_last_punch), lunchMin)
  }
  return netSec(d.duration_seconds, lunchMin)
}

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatSchedule(start: string | null, end: string | null) {
  if (!start || !end) return '—'
  return `${start.slice(0, 5)}–${end.slice(0, 5)}`
}

export default function PontajeTab({ showFilters = false, managerFilter = false, search = '' }: { showStats?: boolean; showFilters?: boolean; managerFilter?: boolean; search?: string }) {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canAdjust = user?.can_adjust_punches ?? false

  const [date, setDate] = useState(todayStr())
  const [groupFilter, setGroupFilter] = useState<string>('all')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  // Column visibility
  const [visibleCols, setVisibleCols] = useState<Set<ColKey>>(new Set(DEFAULT_COLS))

  const toggleCol = (key: ColKey, checked: boolean) => {
    setVisibleCols(prev => { const n = new Set(prev); checked ? n.add(key) : n.delete(key); return n })
  }
  const resetCols = () => setVisibleCols(new Set(DEFAULT_COLS))

  // ── Data query ──

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ['biostar', 'attendance-today', date, managerFilter],
    queryFn: () => biostarApi.getAttendanceToday(date, managerFilter),
    refetchInterval: date === todayStr() ? 60_000 : false,
  })

  // ── Adjustments ──

  const autoAdjustMut = useMutation({
    mutationFn: () => biostarApi.autoAdjustAll(date),
    onSuccess: (res) => {
      toast.success(`Auto-adjusted ${res.data.adjusted} of ${res.data.total_flagged} employees`)
      queryClient.invalidateQueries({ queryKey: ['biostar', 'attendance-today', date] })
    },
    onError: () => toast.error('Auto-adjust failed'),
  })

  const backfillMut = useMutation({
    mutationFn: () => biostarApi.backfillAdjustments(),
    onSuccess: (res) => {
      toast.success(`Backfill: ${res.data.total_adjusted} adjusted across ${res.data.dates_processed} dates`)
      queryClient.invalidateQueries({ queryKey: ['biostar'] })
    },
    onError: () => toast.error('Backfill failed'),
  })

  // ── Groups ──

  const groups = useMemo(() => {
    const set = new Set<string>()
    rows.forEach((e) => { if (e.user_group_name) set.add(e.user_group_name) })
    return Array.from(set).sort()
  }, [rows])

  // ── Filter + sort ──

  const processed = useMemo(() => {
    let list = [...rows]
    if (groupFilter !== 'all') list = list.filter((e) => e.user_group_name === groupFilter)
    if (search) {
      const s = search.toLowerCase()
      list = list.filter((e) =>
        (e.name || '').toLowerCase().includes(s) ||
        (e.email || '').toLowerCase().includes(s) ||
        (e.user_group_name || '').toLowerCase().includes(s) ||
        (e.company || '').toLowerCase().includes(s),
      )
    }
    list.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'name': cmp = (a.name || '').localeCompare(b.name || ''); break
        case 'company': cmp = (a.company || '').localeCompare(b.company || ''); break
        case 'group': cmp = (a.user_group_name || '').localeCompare(b.user_group_name || ''); break
        case 'check_in': cmp = ((a.adjusted_first_punch ?? a.first_punch) || '').localeCompare((b.adjusted_first_punch ?? b.first_punch) || ''); break
        case 'check_out': cmp = ((a.adjusted_last_punch ?? a.last_punch) || '').localeCompare((b.adjusted_last_punch ?? b.last_punch) || ''); break
        case 'duration': cmp = netSec(a.duration_seconds, a.lunch_break_minutes ?? 60) - netSec(b.duration_seconds, b.lunch_break_minutes ?? 60); break
        case 'punches': cmp = (a.total_punches ?? 0) - (b.total_punches ?? 0); break
        default: cmp = (a.name || '').localeCompare(b.name || '')
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [rows, groupFilter, search, sortField, sortDir])

  // ── Stats ──

  const presentCount = processed.filter(e => e.attendance_status === 'present').length
  const absentCount = processed.filter(e => e.attendance_status === 'absent').length

  // ── Sorting ──

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => (
    <ArrowUpDown className={cn('ml-1 h-3 w-3 inline', sortField === field ? 'opacity-100' : 'opacity-40')} />
  )

  // ── Day navigation ──

  const stepDay = (delta: number) => {
    const d = new Date(date)
    d.setDate(d.getDate() + delta)
    setDate(d.toISOString().slice(0, 10))
    setExpandedId(null)
  }

  // ── CSV Download ──

  const downloadCsv = useCallback(() => {
    const headers = ['Name']
    const cols = visibleCols
    if (cols.has('company')) headers.push('Company')
    if (cols.has('group')) headers.push('Group')
    // Always export official columns (regardless of visibility toggle)
    headers.push('Check In', 'Check Out')
    // actual_in / actual_out are NEVER exported
    if (cols.has('duration')) headers.push('Duration (h)')
    if (cols.has('punches')) headers.push('Punches')
    if (cols.has('schedule')) headers.push('Schedule')
    headers.push('Status')

    const csvRows = [headers]
    for (const e of processed) {
      const row = [e.name]
      if (cols.has('company')) row.push(e.company || '')
      if (cols.has('group')) row.push(e.user_group_name || '')
      // Official times: adjusted if available, otherwise raw
      const officialIn = e.adjusted_first_punch ?? e.first_punch
      const officialOut = e.adjusted_last_punch ?? e.last_punch
      row.push(officialIn ? fmtTime(officialIn) : '')
      row.push(officialOut ? fmtTime(officialOut) : '')
      if (cols.has('duration')) {
        const net = netSec(e.duration_seconds, e.lunch_break_minutes ?? 60)
        row.push(net > 0 ? (net / 3600).toFixed(2) : '')
      }
      if (cols.has('punches')) row.push(String(e.total_punches ?? 0))
      if (cols.has('schedule')) row.push(formatSchedule(e.schedule_start, e.schedule_end))
      row.push(e.attendance_status)
      csvRows.push(row)
    }

    const csvContent = csvRows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `pontaje_${date}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [processed, visibleCols, date])

  // ── Mobile fields ──

  const mobileFields: MobileCardField<AttendanceRow>[] = useMemo(() => [
    { key: 'name', label: 'Employee', isPrimary: true, render: (e) => <span className="font-medium">{e.name}</span> },
    {
      key: 'checkin', label: 'Official In',
      render: (e) => {
        const t = e.adjusted_first_punch ?? e.first_punch
        if (!t) return <span className="text-muted-foreground">—</span>
        return (
          <span className="inline-flex items-center gap-1 text-sm">
            <LogIn className="h-3 w-3 text-green-600" />{fmtTime(t)}
            {e.adjusted_first_punch && <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300">C</Badge>}
          </span>
        )
      },
    },
    {
      key: 'checkout', label: 'Official Out',
      render: (e) => {
        if (!e.first_punch) return <span className="text-muted-foreground">—</span>
        if ((e.total_punches ?? 0) === 1 && !e.adjusted_last_punch) return <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
        const t = e.adjusted_last_punch ?? e.last_punch
        return (
          <span className="inline-flex items-center gap-1 text-sm">
            <LogOut className="h-3 w-3 text-red-500" />{fmtTime(t)}
            {e.adjusted_last_punch && <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300">C</Badge>}
          </span>
        )
      },
    },
    {
      key: 'duration', label: 'Duration',
      render: (e) => {
        if (e.attendance_status === 'absent') return <span className="text-muted-foreground">—</span>
        const net = netSec(e.duration_seconds, e.lunch_break_minutes ?? 60)
        return <span className="text-sm font-medium">{(e.total_punches ?? 0) === 1 ? '—' : fmtDuration(net)}</span>
      },
    },
  ], [])

  const dateLabel = new Date(`${date}T12:00:00`).toLocaleDateString('ro-RO', {
    weekday: 'long', day: 'numeric', month: 'long',
  })

  return (
    <div className="space-y-4">
      {/* Filters */}
      {showFilters && (
        <div className="flex flex-wrap items-center gap-2">
          {/* Day navigation */}
          <Button variant="outline" size="icon" className="h-8 w-8 shrink-0" onClick={() => stepDay(-1)} title="Previous day">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <DateField
            value={date}
            onChange={(v) => { setDate(v); setExpandedId(null) }}
            className="h-8 shrink-0"
          />
          <Button variant="outline" size="icon" className="h-8 w-8 shrink-0" onClick={() => stepDay(1)} title="Next day">
            <ChevronRight className="h-4 w-4" />
          </Button>
          <span className="text-xs text-muted-foreground hidden md:inline capitalize">{dateLabel}</span>

          {/* Group filter */}
          <Select value={groupFilter} onValueChange={setGroupFilter}>
            <SelectTrigger className="w-40 md:w-44 shrink-0">
              <SelectValue placeholder="All Groups" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Groups ({processed.length})</SelectItem>
              {groups.map((g) => (
                <SelectItem key={g} value={g}>{g}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1 ml-auto">
            {/* Adjustment buttons */}
            {canAdjust && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => autoAdjustMut.mutate()}
                  disabled={autoAdjustMut.isPending}
                >
                  <Wand2 className="mr-1 h-3.5 w-3.5" />
                  Auto-adjust
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => { if (confirm('Backfill will adjust all unadjusted past dates. Continue?')) backfillMut.mutate() }}
                  disabled={backfillMut.isPending}
                >
                  <DatabaseZap className="mr-1 h-3.5 w-3.5" />
                  Backfill
                </Button>
              </>
            )}

            {/* Download CSV */}
            <Button variant="outline" size="icon" className="h-8 w-8 shrink-0" onClick={downloadCsv} title="Download CSV">
              <Download className="h-4 w-4" />
            </Button>

            {/* Column toggle */}
            {!isMobile && (
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    className={cn('h-8 w-8 shrink-0', visibleCols.size < COL_DEFS.length && 'text-primary border-primary')}
                  >
                    <Columns3 className="h-4 w-4" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-52 p-3">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Columns</span>
                    <button onClick={resetCols} className="text-xs text-muted-foreground hover:text-foreground">Reset</button>
                  </div>
                  <div className="space-y-0.5">
                    {COL_DEFS.map(c => (
                      <label
                        key={c.key}
                        className="flex items-center gap-2.5 px-1 py-1.5 text-sm cursor-pointer hover:bg-accent rounded-md select-none"
                      >
                        <Checkbox
                          checked={visibleCols.has(c.key)}
                          onCheckedChange={(v) => toggleCol(c.key, !!v)}
                          className="h-3.5 w-3.5"
                        />
                        {c.label}
                      </label>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            )}
          </div>
        </div>
      )}

      {/* Summary badges */}
      <div className="flex items-center gap-3 text-sm">
        <span className="inline-flex items-center gap-1.5">
          <UserCheck className="h-4 w-4 text-green-600" />
          <span className="font-medium">{presentCount}</span>
          <span className="text-muted-foreground">present</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <UserX className="h-4 w-4 text-red-500" />
          <span className="font-medium">{absentCount}</span>
          <span className="text-muted-foreground">absent</span>
        </span>
        <span className="text-muted-foreground">/ {processed.length} total</span>
      </div>

      {/* Loading */}
      {isLoading && (
        isMobile
          ? <MobileCardList data={[]} fields={mobileFields} getRowId={() => 0} isLoading />
          : <div className="space-y-2">{Array.from({ length: 10 }).map((_, i) => <div key={i} className="h-10 animate-pulse rounded bg-muted" />)}</div>
      )}

      {/* Table */}
      {!isLoading && (
        processed.length === 0
          ? <EmptyState title="No employees found" description={search ? 'Try a different search term.' : 'No active employees with BioStar mapping.'} />
          : isMobile
            ? <MobileCardList data={processed} fields={mobileFields} getRowId={(e) => e.jarvis_user_id} onRowClick={(e) => navigate(`/app/hr/pontaje/${e.biostar_user_id}`)} />
            : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8" />
                      <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                        Name <SortIcon field="name" />
                      </TableHead>
                      {visibleCols.has('group') && (
                        <TableHead className="hidden lg:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                          Group <SortIcon field="group" />
                        </TableHead>
                      )}
                      {visibleCols.has('official_in') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_in')}>
                          Official In <SortIcon field="check_in" />
                        </TableHead>
                      )}
                      {visibleCols.has('official_out') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_out')}>
                          Official Out <SortIcon field="check_out" />
                        </TableHead>
                      )}
                      {visibleCols.has('actual_in') && (
                        <TableHead className="text-center hidden lg:table-cell">Actual In</TableHead>
                      )}
                      {visibleCols.has('actual_out') && (
                        <TableHead className="text-center hidden lg:table-cell">Actual Out</TableHead>
                      )}
                      {visibleCols.has('duration') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('duration')}>
                          Duration <SortIcon field="duration" />
                        </TableHead>
                      )}
                      {visibleCols.has('punches') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('punches')}>
                          Punches <SortIcon field="punches" />
                        </TableHead>
                      )}
                      {visibleCols.has('schedule') && (
                        <TableHead className="text-center">Schedule</TableHead>
                      )}
                      {visibleCols.has('company') && (
                        <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('company')}>
                          Company <SortIcon field="company" />
                        </TableHead>
                      )}
                      {canAdjust && <TableHead className="w-10" />}
                      <TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {processed.map((emp) => (
                      <EmployeeRow
                        key={emp.jarvis_user_id}
                        employee={emp}
                        date={date}
                        isExpanded={expandedId === emp.jarvis_user_id}
                        onToggle={() => setExpandedId(expandedId === emp.jarvis_user_id ? null : emp.jarvis_user_id)}
                        onProfile={() => navigate(`/app/hr/pontaje/${emp.biostar_user_id}`)}
                        visibleCols={visibleCols}
                        canAdjust={canAdjust}
                        onAdjust={() => {
                          if (!emp.first_punch) return
                          const { adjFirst, adjLast } = randomizeAdjustedTimes(
                            date, emp.schedule_start, emp.lunch_break_minutes ?? 60, emp.working_hours ?? 8,
                          )
                          biostarApi.adjustEmployee({
                            biostar_user_id: emp.biostar_user_id,
                            date,
                            adjusted_first_punch: adjFirst,
                            adjusted_last_punch: adjLast,
                            original_first_punch: emp.first_punch,
                            original_last_punch: emp.last_punch ?? emp.first_punch,
                            schedule_start: emp.schedule_start ?? undefined,
                            schedule_end: emp.schedule_end ?? undefined,
                            lunch_break_minutes: emp.lunch_break_minutes ?? 60,
                            working_hours: emp.working_hours ?? 8,
                            original_duration_seconds: emp.duration_seconds ?? undefined,
                          }).then(() => {
                            toast.success('Adjusted')
                            queryClient.invalidateQueries({ queryKey: ['biostar', 'attendance-today', date] })
                          }).catch(() => toast.error('Adjust failed'))
                        }}
                        onRevert={() => {
                          biostarApi.revertAdjustment(emp.biostar_user_id, date).then(() => {
                            toast.success('Adjustment reverted')
                            queryClient.invalidateQueries({ queryKey: ['biostar', 'attendance-today', date] })
                          }).catch(() => toast.error('Revert failed'))
                        }}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>
            )
      )}

      <div className="text-sm text-muted-foreground">
        Showing {processed.length} employees
      </div>
    </div>
  )
}

// ── Employee Row ──

function EmployeeRow({
  employee,
  date,
  isExpanded,
  onToggle,
  onProfile,
  visibleCols,
  canAdjust,
  onAdjust,
  onRevert,
}: {
  employee: AttendanceRow
  date: string
  isExpanded: boolean
  onToggle: () => void
  onProfile: () => void
  visibleCols: Set<ColKey>
  canAdjust: boolean
  onAdjust: () => void
  onRevert: () => void
}) {
  const isAbsent = employee.attendance_status === 'absent'
  const lunch = employee.lunch_break_minutes ?? 60
  const net = netSec(employee.duration_seconds, lunch)
  const expectedH = employee.working_hours ?? 8
  const netH = net / 3600
  const isShort = netH > 0 && netH < expectedH
  const hasAdj = !!employee.adjustment_type

  const colSpan = 2 /* chevron + name */
    + (visibleCols.has('group') ? 1 : 0)
    + (visibleCols.has('official_in') ? 1 : 0)
    + (visibleCols.has('official_out') ? 1 : 0)
    + (visibleCols.has('actual_in') ? 1 : 0)
    + (visibleCols.has('actual_out') ? 1 : 0)
    + (visibleCols.has('duration') ? 1 : 0)
    + (visibleCols.has('punches') ? 1 : 0)
    + (visibleCols.has('schedule') ? 1 : 0)
    + (visibleCols.has('company') ? 1 : 0)
    + (canAdjust ? 1 : 0)
    + 1 /* status dot / link */

  return (
    <>
      <TableRow className={cn('cursor-pointer hover:bg-muted/50', isAbsent && 'opacity-60')} onClick={onToggle}>
        <TableCell className="w-8 px-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell>
          <span className="font-medium">{employee.name}</span>
        </TableCell>
        {visibleCols.has('group') && (
          <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
            {employee.user_group_name || '—'}
          </TableCell>
        )}
        {visibleCols.has('official_in') && (
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-sm">
                <LogIn className="h-3 w-3 text-green-600" />
                {fmtTime(employee.adjusted_first_punch ?? employee.first_punch)}
                {hasAdj && <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300">C</Badge>}
              </span>
            )}
          </TableCell>
        )}
        {visibleCols.has('official_out') && (
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-muted-foreground">—</span>
            ) : (employee.total_punches ?? 0) === 1 && !hasAdj ? (
              <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
            ) : (
              <span className="inline-flex items-center gap-1 text-sm">
                <LogOut className="h-3 w-3 text-red-500" />
                {fmtTime(employee.adjusted_last_punch ?? employee.last_punch)}
                {hasAdj && <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300">C</Badge>}
              </span>
            )}
          </TableCell>
        )}
        {visibleCols.has('actual_in') && (
          <TableCell className="text-center hidden lg:table-cell">
            {isAbsent ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <span className="text-sm text-muted-foreground">{fmtTime(employee.first_punch)}</span>
            )}
          </TableCell>
        )}
        {visibleCols.has('actual_out') && (
          <TableCell className="text-center hidden lg:table-cell">
            {isAbsent ? (
              <span className="text-muted-foreground">—</span>
            ) : (employee.total_punches ?? 0) === 1 ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <span className="text-sm text-muted-foreground">{fmtTime(employee.last_punch)}</span>
            )}
          </TableCell>
        )}
        {visibleCols.has('duration') && (
          <TableCell className="text-center">
            {isAbsent || (employee.total_punches ?? 0) === 1 ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
                {fmtDuration(net)}
              </span>
            )}
          </TableCell>
        )}
        {visibleCols.has('punches') && (
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <Badge variant="secondary" className="text-xs">{employee.total_punches}</Badge>
            )}
          </TableCell>
        )}
        {visibleCols.has('schedule') && (
          <TableCell className="text-center text-sm text-muted-foreground">
            {formatSchedule(employee.schedule_start, employee.schedule_end)}
          </TableCell>
        )}
        {visibleCols.has('company') && (
          <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
            {employee.company || '—'}
          </TableCell>
        )}
        {canAdjust && (
          <TableCell className="text-center w-10">
            {!isAbsent && hasAdj && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={(e) => { e.stopPropagation(); onRevert() }}
                title="Revert adjustment"
              >
                <RotateCcw className="h-3 w-3" />
              </Button>
            )}
            {!isAbsent && !hasAdj && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={(e) => { e.stopPropagation(); onAdjust() }}
                title="Auto-adjust"
              >
                <Wand2 className="h-3 w-3" />
              </Button>
            )}
          </TableCell>
        )}
        <TableCell className="w-10 text-right pr-3">
          <div className="flex items-center justify-end gap-2">
            <span className={cn(
              'inline-block h-2.5 w-2.5 rounded-full shrink-0',
              isAbsent ? 'bg-red-400' : 'bg-green-500',
            )} />
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={(e) => { e.stopPropagation(); onProfile() }}
              title="Full profile"
            >
              <ExternalLink className="h-3 w-3" />
            </Button>
          </div>
        </TableCell>
      </TableRow>
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={colSpan} className="bg-muted/30 p-0">
            <MonthHistory biostarUserId={employee.biostar_user_id} jarvisUserId={employee.jarvis_user_id} date={date} lunchMin={lunch} workingHours={employee.working_hours ?? 8} scheduleStart={employee.schedule_start} scheduleEnd={employee.schedule_end} canAdjust={canAdjust} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

// ── Helpers ──

type DayEntry = { date: string; dayLabel: string; data: BioStarDayHistory | null; isHoliday: boolean; isWeekend: boolean; isOutsideMonth: boolean }
type WeekGroup = { weekNum: number; weekLabel: string; days: DayEntry[] }

function getISOWeek(d: Date): number {
  const tmp = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  tmp.setUTCDate(tmp.getUTCDate() + 4 - (tmp.getUTCDay() || 7))
  const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1))
  return Math.ceil(((tmp.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
}

function lastDayOfMonth(dateStr: string): string {
  const [y, m] = dateStr.split('-').map(Number)
  const d = new Date(y, m, 0)
  return d.toISOString().slice(0, 10)
}

/** Monday of the week containing the given date */
function weekMonday(dateStr: string): string {
  const d = new Date(`${dateStr}T12:00:00`)
  const dow = d.getDay() || 7 // Sun=7
  d.setDate(d.getDate() - dow + 1)
  return d.toISOString().slice(0, 10)
}

/** Sunday of the week containing the given date */
function weekSunday(dateStr: string): string {
  const d = new Date(`${dateStr}T12:00:00`)
  const dow = d.getDay() || 7
  d.setDate(d.getDate() + (7 - dow))
  return d.toISOString().slice(0, 10)
}

function groupByWeek(days: DayEntry[]): WeekGroup[] {
  const map = new Map<number, DayEntry[]>()
  for (const day of days) {
    const d = new Date(`${day.date}T12:00:00`)
    const wk = getISOWeek(d)
    if (!map.has(wk)) map.set(wk, [])
    map.get(wk)!.push(day)
  }
  const result: WeekGroup[] = []
  for (const [weekNum, wkDays] of map) {
    const first = wkDays[0].date
    const last = wkDays[wkDays.length - 1].date
    const fmtD = (s: string) => new Date(`${s}T12:00:00`).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })
    result.push({ weekNum, weekLabel: `${fmtD(first)} – ${fmtD(last)}`, days: wkDays })
  }
  return result.sort((a, b) => a.weekNum - b.weekNum)
}

async function adjustDays(
  days: DayEntry[],
  biostarUserId: string,
  scheduleStart: string | null,
  lunchMin: number,
  workingHours: number,
): Promise<number> {
  const unadjusted = days.filter(d => d.data && !d.data.adjusted_first_punch && !d.isWeekend && !d.isHoliday && !d.isOutsideMonth)
  let count = 0
  for (const day of unadjusted) {
    const d = day.data!
    if (!d.first_punch) continue
    const { adjFirst, adjLast } = randomizeAdjustedTimes(day.date, scheduleStart, lunchMin, workingHours)
    await biostarApi.adjustEmployee({
      biostar_user_id: biostarUserId,
      date: day.date,
      adjusted_first_punch: adjFirst,
      adjusted_last_punch: adjLast,
      original_first_punch: d.first_punch,
      original_last_punch: d.last_punch ?? d.first_punch,
      schedule_start: scheduleStart ?? undefined,
      lunch_break_minutes: lunchMin,
      working_hours: workingHours,
      original_duration_seconds: d.duration_seconds ?? undefined,
    })
    count++
  }
  return count
}

// ── Month History (expansion) ──

function MonthHistory({
  biostarUserId, jarvisUserId, date, lunchMin, workingHours, scheduleStart, scheduleEnd: _scheduleEnd, canAdjust,
}: {
  biostarUserId: string; jarvisUserId: number; date: string; lunchMin: number; workingHours: number
  scheduleStart: string | null; scheduleEnd: string | null; canAdjust: boolean
}) {
  const queryClient = useQueryClient()
  const [expandedWeeks, setExpandedWeeks] = useState<Set<number>>(() => {
    const now = new Date(`${date}T12:00:00`)
    return new Set([getISOWeek(now)])
  })
  const [adjusting, setAdjusting] = useState(false)

  // Month range — extend to complete weeks at boundaries
  const monthFirst = `${date.slice(0, 7)}-01`
  const monthLast = lastDayOfMonth(date)
  const rangeStart = weekMonday(monthFirst)  // Mon of first week
  const rangeEnd = weekSunday(monthLast)     // Sun of last week
  const monthLabel = new Date(`${date}T12:00:00`).toLocaleDateString('ro-RO', { month: 'long', year: 'numeric' })

  const { data, isLoading } = useQuery({
    queryKey: ['biostar', 'employee-daily-history', biostarUserId, rangeStart, rangeEnd],
    queryFn: () => biostarApi.getEmployeeDailyHistory(biostarUserId, rangeStart, rangeEnd),
  })

  const history = data?.history ?? []
  const holidays = useMemo(() => new Set(data?.holidays ?? []), [data?.holidays])

  // Sincron leave codes for the month
  const [y, mo] = date.split('-').map(Number)
  const { data: sincronData } = useQuery({
    queryKey: ['sincron', 'employee-timesheet', jarvisUserId, y, mo],
    queryFn: () => sincronApi.getEmployeeTimesheet(jarvisUserId, y, mo),
    enabled: !!jarvisUserId,
  })
  const leaveCodes = useMemo(() => {
    const map = new Map<string, string>()
    if (!sincronData?.data?.days) return map
    for (const [dayKey, codes] of Object.entries(sincronData.data.days)) {
      // dayKey is a full date string like "2026-04-06"
      const leave = codes.find(c => ['CO', 'CM', 'CIC', 'CES', 'CMS', 'DLG', 'ZLS', 'CFP', 'CFS', 'INV'].includes(c.short_code))
      if (leave) {
        map.set(dayKey, leave.short_code)
      }
    }
    return map
  }, [sincronData])

  // Generate all days — full weeks including boundary days from prev/next month
  const allDays = useMemo(() => {
    const result: DayEntry[] = []
    const start = new Date(`${rangeStart}T12:00:00`)
    const end = new Date(`${rangeEnd}T12:00:00`)
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const ds = d.toISOString().slice(0, 10)
      const dow = d.getDay()
      result.push({
        date: ds,
        dayLabel: d.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric', month: 'short' }),
        data: history.find(h => h.date?.slice(0, 10) === ds) ?? null,
        isHoliday: holidays.has(ds),
        isWeekend: dow === 0 || dow === 6,
        isOutsideMonth: ds < monthFirst || ds > monthLast,
      })
    }
    return result
  }, [rangeStart, rangeEnd, monthFirst, monthLast, history, holidays])

  const weeks = useMemo(() => groupByWeek(allDays), [allDays])

  const toggleWeek = (wk: number) => setExpandedWeeks(prev => {
    const n = new Set(prev); n.has(wk) ? n.delete(wk) : n.add(wk); return n
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['biostar', 'employee-daily-history', biostarUserId, rangeStart, rangeEnd] })

  // Stats — only count days within the actual month
  const monthDays = allDays.filter(d => !d.isOutsideMonth)
  const workingDays = monthDays.filter(d => !d.isWeekend && !d.isHoliday).length
  const presentDays = monthDays.filter(d => d.data && !d.isWeekend && !d.isHoliday).length

  const handleAdjustMonth = async () => {
    if (!confirm(`Adjust all unadjusted days in ${monthLabel}?`)) return
    setAdjusting(true)
    try {
      const count = await adjustDays(allDays, biostarUserId, scheduleStart, lunchMin, workingHours)
      toast.success(`Adjusted ${count} days in ${monthLabel}`)
      invalidate()
      queryClient.invalidateQueries({ queryKey: ['biostar', 'attendance-today'] })
    } catch { toast.error('Month adjust failed') }
    finally { setAdjusting(false) }
  }

  if (isLoading) {
    return (
      <div className="p-4 space-y-2">
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-6 w-full" />)}
      </div>
    )
  }

  return (
    <div className="p-4">
      {/* Month header */}
      <div className="mb-3 flex items-center gap-3">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider capitalize">
          {monthLabel} — {presentDays} / {workingDays} working days
        </span>
        {canAdjust && (
          <Button variant="ghost" size="sm" className="h-6 text-[11px] px-2" onClick={handleAdjustMonth} disabled={adjusting}>
            <Wand2 className="mr-1 h-3 w-3" />Adjust Month
          </Button>
        )}
      </div>

      {/* Weeks */}
      <div className="space-y-1">
        {weeks.map((week) => {
          const isOpen = expandedWeeks.has(week.weekNum)
          const wkWorking = week.days.filter(d => !d.isWeekend && !d.isHoliday)
          const wkPresent = wkWorking.filter(d => d.data)
          const wkTotalSec = wkPresent.reduce((sum, d) => sum + effectiveSec(d.data!, d.data!.lunch_break_minutes ?? lunchMin), 0)
          const wkAvg = wkPresent.length > 0 ? fmtDuration(wkTotalSec / wkPresent.length) : '—'

          const handleAdjustWeek = async (e: React.MouseEvent) => {
            e.stopPropagation()
            setAdjusting(true)
            try {
              const count = await adjustDays(week.days, biostarUserId, scheduleStart, lunchMin, workingHours)
              toast.success(`Adjusted ${count} days in week ${week.weekNum}`)
              invalidate()
              queryClient.invalidateQueries({ queryKey: ['biostar', 'attendance-today'] })
            } catch { toast.error('Week adjust failed') }
            finally { setAdjusting(false) }
          }

          return (
            <div key={week.weekNum}>
              {/* Week header */}
              <div
                className="flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer hover:bg-muted/50 select-none"
                onClick={() => toggleWeek(week.weekNum)}
              >
                {isOpen
                  ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />}
                <span className="text-sm font-medium">
                  W{week.weekNum}
                </span>
                <span className="text-xs text-muted-foreground">
                  {week.weekLabel}
                </span>
                <span className="text-xs text-muted-foreground">
                  — {wkPresent.length}/{wkWorking.length} days, avg {wkAvg}
                </span>
                {canAdjust && (
                  <Button variant="ghost" size="sm" className="h-5 text-[10px] px-1.5 ml-auto" onClick={handleAdjustWeek} disabled={adjusting}>
                    <Wand2 className="mr-0.5 h-2.5 w-2.5" />Week
                  </Button>
                )}
              </div>

              {/* Day rows */}
              {isOpen && (
                <div className="ml-6 space-y-0.5 mb-2">
                  {week.days.map((day) => (
                    <DayRow
                      key={day.date}
                      day={day}
                      leaveCode={leaveCodes.get(day.date)}
                      lunchMin={lunchMin}
                      workingHours={workingHours}
                      biostarUserId={biostarUserId}
                      scheduleStart={scheduleStart}
                      canAdjust={canAdjust}
                      adjusting={adjusting}
                      onInvalidate={() => { invalidate(); queryClient.invalidateQueries({ queryKey: ['biostar', 'attendance-today'] }) }}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Day Row (inside week) ──

function DayRow({
  day, leaveCode, lunchMin, workingHours, biostarUserId, scheduleStart, canAdjust, adjusting, onInvalidate,
}: {
  day: DayEntry; leaveCode?: string; lunchMin: number; workingHours: number; biostarUserId: string
  scheduleStart: string | null; canAdjust: boolean; adjusting: boolean; onInvalidate: () => void
}) {
  const d = day.data
  const isToday = day.date === todayStr()
  const isFuture = day.date > todayStr()
  const isOut = day.isOutsideMonth
  const net = d ? effectiveSec(d, d.lunch_break_minutes ?? lunchMin) : 0
  const netH = net / 3600
  const isShort = netH > 0 && netH < workingHours
  const hasAdj = !!d?.adjusted_first_punch

  const handleAdjustDay = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!d?.first_punch) return
    const { adjFirst, adjLast } = randomizeAdjustedTimes(day.date, scheduleStart, lunchMin, workingHours)
    try {
      await biostarApi.adjustEmployee({
        biostar_user_id: biostarUserId, date: day.date,
        adjusted_first_punch: adjFirst, adjusted_last_punch: adjLast,
        original_first_punch: d.first_punch, original_last_punch: d.last_punch ?? d.first_punch,
        schedule_start: scheduleStart ?? undefined, lunch_break_minutes: lunchMin,
        working_hours: workingHours, original_duration_seconds: d.duration_seconds ?? undefined,
      })
      toast.success('Adjusted')
      onInvalidate()
    } catch { toast.error('Adjust failed') }
  }

  const handleRevertDay = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await biostarApi.revertAdjustment(biostarUserId, day.date)
      toast.success('Reverted')
      onInvalidate()
    } catch { toast.error('Revert failed') }
  }

  return (
    <div className={cn(
      'flex items-center gap-3 px-3 py-1.5 rounded-md text-sm',
      isToday && 'bg-primary/5 font-medium',
      isOut && 'opacity-40',
      !isOut && !d && !day.isWeekend && !day.isHoliday && !isFuture && 'opacity-50',
    )}>
      <span className={cn(
        'inline-block h-2 w-2 rounded-full shrink-0',
        d ? 'bg-green-500' : day.isWeekend || day.isHoliday ? 'bg-blue-400' : leaveCode ? 'bg-yellow-500' : isFuture ? 'bg-muted-foreground/30' : 'bg-red-400',
      )} />
      <span className="w-28 shrink-0 capitalize text-muted-foreground">{day.dayLabel}</span>

      {d ? (
        <>
          <span className="w-14 shrink-0 text-center">
            <span className="inline-flex items-center gap-1">
              <LogIn className="h-3 w-3 text-green-600" />
              {fmtTime(d.adjusted_first_punch ?? d.first_punch)}
            </span>
          </span>
          <span className="w-14 shrink-0 text-center">
            {d.total_punches === 1 && !hasAdj ? (
              <span className="text-xs text-orange-600">—</span>
            ) : (
              <span className="inline-flex items-center gap-1">
                <LogOut className="h-3 w-3 text-red-500" />
                {fmtTime(d.adjusted_last_punch ?? d.last_punch)}
              </span>
            )}
          </span>
          <span className={cn('w-16 shrink-0 text-center font-medium', isShort ? 'text-orange-600' : '')}>
            {d.total_punches === 1 && !hasAdj ? '—' : fmtDuration(net)}
          </span>
          {hasAdj && <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300">C</Badge>}
          {canAdjust && !hasAdj && d.first_punch && (
            <Button variant="ghost" size="icon" className="h-5 w-5 ml-auto" onClick={handleAdjustDay} disabled={adjusting} title="Adjust day">
              <Wand2 className="h-2.5 w-2.5" />
            </Button>
          )}
          {canAdjust && hasAdj && (
            <Button variant="ghost" size="icon" className="h-5 w-5 ml-auto" onClick={handleRevertDay} disabled={adjusting} title="Revert">
              <RotateCcw className="h-2.5 w-2.5" />
            </Button>
          )}
        </>
      ) : (
        <span className={cn('text-xs', leaveCode ? 'text-yellow-600' : 'text-muted-foreground')}>
          {day.isWeekend ? 'Weekend' : day.isHoliday ? 'Holiday' : leaveCode ?? (isFuture ? '—' : 'Absent')}
        </span>
      )}
    </div>
  )
}
