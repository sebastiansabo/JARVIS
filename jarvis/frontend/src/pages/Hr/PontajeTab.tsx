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
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { AttendanceRow, BioStarDayHistory } from '@/types/biostar'

type SortField = 'name' | 'company' | 'group' | 'check_in' | 'check_out' | 'duration' | 'punches'
type SortDir = 'asc' | 'desc'

type ColKey = 'group' | 'check_in' | 'check_out' | 'duration' | 'punches' | 'schedule' | 'company' | 'adj_in' | 'adj_out'

const COL_DEFS: { key: ColKey; label: string }[] = [
  { key: 'check_in', label: 'Check In' },
  { key: 'check_out', label: 'Check Out' },
  { key: 'duration', label: 'Duration' },
  { key: 'punches', label: 'Punches' },
  { key: 'schedule', label: 'Schedule' },
  { key: 'company', label: 'Company' },
  { key: 'group', label: 'Group' },
  { key: 'adj_in', label: 'Adj. In' },
  { key: 'adj_out', label: 'Adj. Out' },
]

const DEFAULT_COLS: ColKey[] = ['check_in', 'check_out', 'duration', 'punches', 'schedule']

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
        case 'check_in': cmp = (a.first_punch || '').localeCompare(b.first_punch || ''); break
        case 'check_out': cmp = (a.last_punch || '').localeCompare(b.last_punch || ''); break
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
    if (cols.has('check_in')) headers.push('Check In')
    if (cols.has('check_out')) headers.push('Check Out')
    if (cols.has('adj_in')) headers.push('Adj. In')
    if (cols.has('adj_out')) headers.push('Adj. Out')
    if (cols.has('duration')) headers.push('Duration (h)')
    if (cols.has('punches')) headers.push('Punches')
    if (cols.has('schedule')) headers.push('Schedule')
    headers.push('Status')

    const csvRows = [headers]
    for (const e of processed) {
      const row = [e.name]
      if (cols.has('company')) row.push(e.company || '')
      if (cols.has('group')) row.push(e.user_group_name || '')
      if (cols.has('check_in')) row.push(e.first_punch ? fmtTime(e.first_punch) : '')
      if (cols.has('check_out')) row.push(e.last_punch ? fmtTime(e.last_punch) : '')
      if (cols.has('adj_in')) row.push(e.adjusted_first_punch ? fmtTime(e.adjusted_first_punch) : '')
      if (cols.has('adj_out')) row.push(e.adjusted_last_punch ? fmtTime(e.adjusted_last_punch) : '')
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
      key: 'checkin', label: 'Check In',
      render: (e) => e.first_punch ? (
        <span className="inline-flex items-center gap-1 text-sm">
          <LogIn className="h-3 w-3 text-green-600" />{fmtTime(e.first_punch)}
        </span>
      ) : <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'checkout', label: 'Check Out',
      render: (e) => {
        if (!e.first_punch) return <span className="text-muted-foreground">—</span>
        if ((e.total_punches ?? 0) === 1) return <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
        return (
          <span className="inline-flex items-center gap-1 text-sm">
            <LogOut className="h-3 w-3 text-red-500" />{fmtTime(e.last_punch)}
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
            {/* Auto-adjust button */}
            {canAdjust && (
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
                      {visibleCols.has('check_in') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_in')}>
                          Check In <SortIcon field="check_in" />
                        </TableHead>
                      )}
                      {visibleCols.has('check_out') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_out')}>
                          Check Out <SortIcon field="check_out" />
                        </TableHead>
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
                      {visibleCols.has('adj_in') && (
                        <TableHead className="text-center hidden lg:table-cell">Adj. In</TableHead>
                      )}
                      {visibleCols.has('adj_out') && (
                        <TableHead className="text-center hidden lg:table-cell">Adj. Out</TableHead>
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
  onRevert,
}: {
  employee: AttendanceRow
  date: string
  isExpanded: boolean
  onToggle: () => void
  onProfile: () => void
  visibleCols: Set<ColKey>
  canAdjust: boolean
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
    + (visibleCols.has('check_in') ? 1 : 0)
    + (visibleCols.has('check_out') ? 1 : 0)
    + (visibleCols.has('duration') ? 1 : 0)
    + (visibleCols.has('punches') ? 1 : 0)
    + (visibleCols.has('schedule') ? 1 : 0)
    + (visibleCols.has('company') ? 1 : 0)
    + (visibleCols.has('adj_in') ? 1 : 0)
    + (visibleCols.has('adj_out') ? 1 : 0)
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
        {visibleCols.has('check_in') && (
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-sm">
                <LogIn className="h-3 w-3 text-green-600" />
                {fmtTime(employee.first_punch)}
                {hasAdj && <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300">C</Badge>}
              </span>
            )}
          </TableCell>
        )}
        {visibleCols.has('check_out') && (
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-muted-foreground">—</span>
            ) : (employee.total_punches ?? 0) === 1 ? (
              <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
            ) : (
              <span className="inline-flex items-center gap-1 text-sm">
                <LogOut className="h-3 w-3 text-red-500" />
                {fmtTime(employee.last_punch)}
                {hasAdj && <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300">C</Badge>}
              </span>
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
        {visibleCols.has('adj_in') && (
          <TableCell className="text-center hidden lg:table-cell">
            {employee.adjusted_first_punch
              ? <span className="text-sm font-medium text-blue-600">{fmtTime(employee.adjusted_first_punch)}</span>
              : <span className="text-muted-foreground">—</span>}
          </TableCell>
        )}
        {visibleCols.has('adj_out') && (
          <TableCell className="text-center hidden lg:table-cell">
            {employee.adjusted_last_punch
              ? <span className="text-sm font-medium text-blue-600">{fmtTime(employee.adjusted_last_punch)}</span>
              : <span className="text-muted-foreground">—</span>}
          </TableCell>
        )}
        {canAdjust && (
          <TableCell className="text-center w-10">
            {hasAdj && (
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
            <WeekHistory biostarUserId={employee.biostar_user_id} date={date} lunchMin={lunch} workingHours={employee.working_hours ?? 8} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

// ── 7-Day History (expansion) ──

function WeekHistory({ biostarUserId, date, lunchMin, workingHours }: { biostarUserId: string; date: string; lunchMin: number; workingHours: number }) {
  // Calculate 7-day range ending at `date`
  const endDate = date
  const startDate = useMemo(() => {
    const d = new Date(`${date}T12:00:00`)
    d.setDate(d.getDate() - 6)
    return d.toISOString().slice(0, 10)
  }, [date])

  const { data, isLoading } = useQuery({
    queryKey: ['biostar', 'employee-daily-history', biostarUserId, startDate, endDate],
    queryFn: () => biostarApi.getEmployeeDailyHistory(biostarUserId, startDate, endDate),
  })

  const history = data?.history ?? []
  const holidays = useMemo(() => new Set(data?.holidays ?? []), [data?.holidays])

  // Generate all 7 days
  const days = useMemo(() => {
    const result: { date: string; dayLabel: string; data: BioStarDayHistory | null; isHoliday: boolean; isWeekend: boolean }[] = []
    for (let i = 0; i < 7; i++) {
      const d = new Date(`${startDate}T12:00:00`)
      d.setDate(d.getDate() + i)
      const ds = d.toISOString().slice(0, 10)
      const dayOfWeek = d.getDay()
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6
      const dayLabel = d.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric', month: 'short' })
      const dayData = history.find(h => h.date?.slice(0, 10) === ds) ?? null
      result.push({ date: ds, dayLabel, data: dayData, isHoliday: holidays.has(ds), isWeekend })
    }
    return result
  }, [startDate, history, holidays])

  if (isLoading) {
    return (
      <div className="p-4 space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-6 w-full" />
        ))}
      </div>
    )
  }

  const daysPresent = days.filter(d => d.data).length

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
        Last 7 days — {daysPresent} present
      </div>
      <div className="space-y-1">
        {days.map((day) => {
          const d = day.data
          const isToday = day.date === todayStr()
          const net = d ? netSec(d.duration_seconds, d.lunch_break_minutes ?? lunchMin) : 0
          const netH = net / 3600
          const isShort = netH > 0 && netH < workingHours
          const hasAdj = !!d?.adjusted_first_punch

          return (
            <div
              key={day.date}
              className={cn(
                'flex items-center gap-3 px-3 py-1.5 rounded-md text-sm',
                isToday && 'bg-primary/5 font-medium',
                !d && !day.isWeekend && !day.isHoliday && 'opacity-50',
              )}
            >
              {/* Status dot */}
              <span className={cn(
                'inline-block h-2 w-2 rounded-full shrink-0',
                d ? 'bg-green-500' : day.isWeekend || day.isHoliday ? 'bg-blue-400' : 'bg-red-400',
              )} />

              {/* Date */}
              <span className="w-28 shrink-0 capitalize text-muted-foreground">
                {day.dayLabel}
              </span>

              {d ? (
                <>
                  {/* Check In */}
                  <span className="w-14 shrink-0 text-center">
                    <span className="inline-flex items-center gap-1">
                      <LogIn className="h-3 w-3 text-green-600" />
                      {fmtTime(d.first_punch)}
                    </span>
                  </span>

                  {/* Check Out */}
                  <span className="w-14 shrink-0 text-center">
                    {d.total_punches === 1 ? (
                      <span className="text-xs text-orange-600">—</span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <LogOut className="h-3 w-3 text-red-500" />
                        {fmtTime(d.last_punch)}
                      </span>
                    )}
                  </span>

                  {/* Duration */}
                  <span className={cn('w-16 shrink-0 text-center font-medium', isShort ? 'text-orange-600' : '')}>
                    {d.total_punches === 1 ? '—' : fmtDuration(net)}
                  </span>

                  {/* Adjustment badge */}
                  {hasAdj && (
                    <Badge variant="outline" className="text-[10px] px-1 py-0 text-blue-600 border-blue-300">C</Badge>
                  )}
                </>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {day.isWeekend ? 'Weekend' : day.isHoliday ? 'Holiday' : 'Absent'}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
