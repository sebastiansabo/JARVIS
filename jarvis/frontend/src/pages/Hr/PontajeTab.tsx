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
  Clock,
  LogIn,
  LogOut,
  UserCheck,
  UserX,
  Fingerprint,
  ExternalLink,
  Columns3,
  Download,
  Wand2,
  RotateCcw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/shared/EmptyState'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { DateField } from '@/components/ui/date-field'
import { biostarApi } from '@/api/biostar'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { AttendanceRow, AttendanceWeekRow, BioStarPunchLog } from '@/types/biostar'

type ViewMode = 'today' | 'week'
type SortField = 'name' | 'company' | 'group' | 'status' | 'check_in' | 'check_out' | 'duration' | 'punches' | 'days_present' | 'total_hours'
type SortDir = 'asc' | 'desc'

type TodayColKey = 'company' | 'group' | 'status' | 'check_in' | 'check_out' | 'adj_in' | 'adj_out' | 'duration' | 'punches'
type WeekColKey = 'company' | 'group' | 'days_present' | 'days_absent' | 'total_hours' | 'avg_hours' | 'adjustments'

const TODAY_COL_DEFS: { key: TodayColKey; label: string }[] = [
  { key: 'company', label: 'Company' },
  { key: 'group', label: 'Group' },
  { key: 'status', label: 'Status' },
  { key: 'check_in', label: 'Check In' },
  { key: 'check_out', label: 'Check Out' },
  { key: 'adj_in', label: 'Adj. In' },
  { key: 'adj_out', label: 'Adj. Out' },
  { key: 'duration', label: 'Duration' },
  { key: 'punches', label: 'Punches' },
]

const WEEK_COL_DEFS: { key: WeekColKey; label: string }[] = [
  { key: 'company', label: 'Company' },
  { key: 'group', label: 'Group' },
  { key: 'days_present', label: 'Days Present' },
  { key: 'days_absent', label: 'Days Absent' },
  { key: 'total_hours', label: 'Total Hours' },
  { key: 'avg_hours', label: 'Avg Hours/Day' },
  { key: 'adjustments', label: 'Adjustments' },
]

const DEFAULT_TODAY_COLS: TodayColKey[] = ['company', 'status', 'check_in', 'check_out', 'adj_in', 'adj_out', 'duration', 'punches']
const DEFAULT_WEEK_COLS: WeekColKey[] = ['company', 'days_present', 'days_absent', 'total_hours', 'avg_hours', 'adjustments']

function formatTime(dt: string | null) {
  if (!dt) return '-'
  return new Date(dt).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
}

function formatDuration(seconds: number | null) {
  if (!seconds || seconds <= 0) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${m}m`
  return `${h}h ${m}m`
}

function netSeconds(durationSec: number | null | undefined, lunchMin: number) {
  const sec = Number(durationSec)
  if (!sec || sec <= 0 || !isFinite(sec)) return 0
  const lunchSec = (Number(lunchMin) || 0) * 60
  return sec > lunchSec ? sec - lunchSec : sec
}

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function PontajeTab({ showFilters = false, managerFilter = false, search = '' }: { showStats?: boolean; showFilters?: boolean; managerFilter?: boolean; search?: string }) {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canAdjust = user?.can_adjust_punches ?? false

  const [viewMode, setViewMode] = useState<ViewMode>('today')
  const [date, setDate] = useState(todayStr())
  const [groupFilter, setGroupFilter] = useState<string>('all')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Column visibility
  const [visibleTodayCols, setVisibleTodayCols] = useState<Set<TodayColKey>>(new Set(DEFAULT_TODAY_COLS))
  const [visibleWeekCols, setVisibleWeekCols] = useState<Set<WeekColKey>>(new Set(DEFAULT_WEEK_COLS))

  const toggleTodayCol = (key: TodayColKey, checked: boolean) => {
    setVisibleTodayCols(prev => { const n = new Set(prev); checked ? n.add(key) : n.delete(key); return n })
  }
  const toggleWeekCol = (key: WeekColKey, checked: boolean) => {
    setVisibleWeekCols(prev => { const n = new Set(prev); checked ? n.add(key) : n.delete(key); return n })
  }
  const resetTodayCols = () => setVisibleTodayCols(new Set(DEFAULT_TODAY_COLS))
  const resetWeekCols = () => setVisibleWeekCols(new Set(DEFAULT_WEEK_COLS))

  // ── Data queries ──

  const { data: todayData = [], isLoading: loadingToday } = useQuery({
    queryKey: ['biostar', 'attendance-today', date, managerFilter],
    queryFn: () => biostarApi.getAttendanceToday(date, managerFilter),
    enabled: viewMode === 'today',
    refetchInterval: date === todayStr() ? 60_000 : false,
  })

  const { data: weekData = [], isLoading: loadingWeek } = useQuery({
    queryKey: ['biostar', 'attendance-week', date, managerFilter],
    queryFn: () => biostarApi.getAttendanceWeek(date, managerFilter),
    enabled: viewMode === 'week',
  })

  const isLoading = viewMode === 'today' ? loadingToday : loadingWeek

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
    const data = viewMode === 'today' ? todayData : weekData
    const set = new Set<string>()
    data.forEach((e) => { if (e.user_group_name) set.add(e.user_group_name) })
    return Array.from(set).sort()
  }, [viewMode, todayData, weekData])

  // ── Filter + sort for Today view ──

  const processedToday = useMemo(() => {
    if (viewMode !== 'today') return []
    let list = [...todayData]
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
        case 'status': cmp = (a.attendance_status || '').localeCompare(b.attendance_status || ''); break
        case 'check_in': cmp = (a.first_punch || '').localeCompare(b.first_punch || ''); break
        case 'check_out': cmp = (a.last_punch || '').localeCompare(b.last_punch || ''); break
        case 'duration': cmp = netSeconds(a.duration_seconds, a.lunch_break_minutes ?? 60) - netSeconds(b.duration_seconds, b.lunch_break_minutes ?? 60); break
        case 'punches': cmp = (a.total_punches ?? 0) - (b.total_punches ?? 0); break
        default: cmp = (a.name || '').localeCompare(b.name || '')
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [todayData, groupFilter, search, sortField, sortDir, viewMode])

  // ── Filter + sort for Week view ──

  const processedWeek = useMemo(() => {
    if (viewMode !== 'week') return []
    let list = [...weekData]
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
        case 'days_present': cmp = a.days_present - b.days_present; break
        case 'total_hours': cmp = netSeconds(a.total_duration_seconds, (a.lunch_break_minutes ?? 60) * a.days_present) - netSeconds(b.total_duration_seconds, (b.lunch_break_minutes ?? 60) * b.days_present); break
        default: cmp = (a.name || '').localeCompare(b.name || '')
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [weekData, groupFilter, search, sortField, sortDir, viewMode])

  // ── Stats ──

  const presentCount = viewMode === 'today'
    ? processedToday.filter(e => e.attendance_status === 'present').length
    : processedWeek.filter(e => e.days_present > 0).length
  const absentCount = viewMode === 'today'
    ? processedToday.filter(e => e.attendance_status === 'absent').length
    : processedWeek.filter(e => e.days_present === 0).length
  const totalCount = viewMode === 'today' ? processedToday.length : processedWeek.length

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
    const rows: string[][] = []

    if (viewMode === 'today') {
      const headers = ['Name']
      const cols = visibleTodayCols
      if (cols.has('company')) headers.push('Company')
      if (cols.has('group')) headers.push('Group')
      if (cols.has('status')) headers.push('Status')
      if (cols.has('check_in')) headers.push('Check In')
      if (cols.has('check_out')) headers.push('Check Out')
      if (cols.has('adj_in')) headers.push('Adj. In')
      if (cols.has('adj_out')) headers.push('Adj. Out')
      if (cols.has('duration')) headers.push('Duration (h)')
      if (cols.has('punches')) headers.push('Punches')
      rows.push(headers)

      for (const e of processedToday) {
        const row = [e.name]
        if (cols.has('company')) row.push(e.company || '')
        if (cols.has('group')) row.push(e.user_group_name || '')
        if (cols.has('status')) row.push(e.attendance_status)
        if (cols.has('check_in')) row.push(e.first_punch ? formatTime(e.first_punch) : '')
        if (cols.has('check_out')) row.push(e.last_punch ? formatTime(e.last_punch) : '')
        if (cols.has('adj_in')) row.push(e.adjusted_first_punch ? formatTime(e.adjusted_first_punch) : '')
        if (cols.has('adj_out')) row.push(e.adjusted_last_punch ? formatTime(e.adjusted_last_punch) : '')
        if (cols.has('duration')) {
          const net = netSeconds(e.duration_seconds, e.lunch_break_minutes ?? 60)
          row.push(net > 0 ? (net / 3600).toFixed(2) : '')
        }
        if (cols.has('punches')) row.push(String(e.total_punches ?? 0))
        rows.push(row)
      }
    } else {
      const headers = ['Name']
      const cols = visibleWeekCols
      if (cols.has('company')) headers.push('Company')
      if (cols.has('group')) headers.push('Group')
      if (cols.has('days_present')) headers.push('Days Present')
      if (cols.has('days_absent')) headers.push('Days Absent')
      if (cols.has('total_hours')) headers.push('Total Hours')
      if (cols.has('avg_hours')) headers.push('Avg Hours/Day')
      if (cols.has('adjustments')) headers.push('Adjustments')
      rows.push(headers)

      for (const e of processedWeek) {
        const row = [e.name]
        const lunch = e.lunch_break_minutes ?? 60
        if (cols.has('company')) row.push(e.company || '')
        if (cols.has('group')) row.push(e.user_group_name || '')
        if (cols.has('days_present')) row.push(String(e.days_present))
        if (cols.has('days_absent')) row.push(String(e.days_absent))
        if (cols.has('total_hours')) {
          const net = netSeconds(e.total_duration_seconds, lunch * e.days_present)
          row.push((net / 3600).toFixed(2))
        }
        if (cols.has('avg_hours')) {
          const net = netSeconds(e.total_duration_seconds, lunch * e.days_present)
          const avg = e.days_present > 0 ? net / e.days_present / 3600 : 0
          row.push(avg.toFixed(2))
        }
        if (cols.has('adjustments')) row.push(String(e.adjustment_count))
        rows.push(row)
      }
    }

    const csvContent = rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `pontaje_${viewMode}_${date}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [viewMode, processedToday, processedWeek, visibleTodayCols, visibleWeekCols, date])

  // ── Mobile fields ──

  const todayMobileFields: MobileCardField<AttendanceRow>[] = useMemo(() => [
    { key: 'name', label: 'Employee', isPrimary: true, render: (e) => e.name || '—' },
    { key: 'company', label: 'Company', isSecondary: true, render: (e) => e.company || '—' },
    {
      key: 'status', label: 'Status',
      render: (e) => e.attendance_status === 'present'
        ? <Badge variant="outline" className="text-xs text-green-600 border-green-300">Present</Badge>
        : <Badge variant="outline" className="text-xs text-red-600 border-red-300">Absent</Badge>,
    },
    {
      key: 'checkin', label: 'Check In',
      render: (e) => e.first_punch ? (
        <span className="inline-flex items-center gap-1 text-sm">
          <LogIn className="h-3 w-3 text-green-600" />{formatTime(e.first_punch)}
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
            <LogOut className="h-3 w-3 text-red-500" />{formatTime(e.last_punch)}
          </span>
        )
      },
    },
    {
      key: 'duration', label: 'Duration',
      render: (e) => {
        if (e.attendance_status === 'absent') return <span className="text-muted-foreground">—</span>
        const net = netSeconds(e.duration_seconds, e.lunch_break_minutes ?? 60)
        return <span className="text-sm font-medium">{(e.total_punches ?? 0) === 1 ? '—' : formatDuration(net)}</span>
      },
    },
  ], [])

  const weekMobileFields: MobileCardField<AttendanceWeekRow>[] = useMemo(() => [
    { key: 'name', label: 'Employee', isPrimary: true, render: (e) => e.name || '—' },
    { key: 'company', label: 'Company', isSecondary: true, render: (e) => e.company || '—' },
    {
      key: 'days', label: 'Days',
      render: (e) => (
        <span className="text-sm">
          <span className="font-medium">{e.days_present}</span>
          <span className="text-muted-foreground"> / 7</span>
        </span>
      ),
    },
    {
      key: 'hours', label: 'Total Hours',
      render: (e) => {
        const net = netSeconds(e.total_duration_seconds, (e.lunch_break_minutes ?? 60) * e.days_present)
        return <span className="text-sm font-medium">{formatDuration(net)}</span>
      },
    },
  ], [])

  const dateLabel = new Date(`${date}T12:00:00`).toLocaleDateString('ro-RO', {
    weekday: 'long', day: 'numeric', month: 'long',
  })

  // Column defs for popover
  const activeColDefs = viewMode === 'today' ? TODAY_COL_DEFS : WEEK_COL_DEFS
  const visibleCols: Set<string> = viewMode === 'today' ? visibleTodayCols : visibleWeekCols

  return (
    <div className="space-y-4">
      {/* Filters */}
      {showFilters && (
        <div className="flex flex-wrap items-center gap-2">
          {/* View mode toggle */}
          <Select value={viewMode} onValueChange={(v) => { setViewMode(v as ViewMode); setExpandedId(null) }}>
            <SelectTrigger className="h-8 w-28 shrink-0 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="today">Today</SelectItem>
              <SelectItem value="week">Week</SelectItem>
            </SelectContent>
          </Select>

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
              <SelectItem value="all">All Groups ({totalCount})</SelectItem>
              {groups.map((g) => (
                <SelectItem key={g} value={g}>{g}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1 ml-auto">
            {/* Auto-adjust button */}
            {canAdjust && viewMode === 'today' && (
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
                    className={cn('h-8 w-8 shrink-0', visibleCols.size < activeColDefs.length && 'text-primary border-primary')}
                  >
                    <Columns3 className="h-4 w-4" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" className="w-52 p-3">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Columns</span>
                    <button
                      onClick={viewMode === 'today' ? resetTodayCols : resetWeekCols}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      Reset
                    </button>
                  </div>
                  <div className="space-y-0.5">
                    {activeColDefs.map(c => {
                      const checked = viewMode === 'today'
                        ? visibleTodayCols.has(c.key as TodayColKey)
                        : visibleWeekCols.has(c.key as WeekColKey)
                      return (
                        <label
                          key={c.key}
                          className="flex items-center gap-2.5 px-1 py-1.5 text-sm cursor-pointer hover:bg-accent rounded-md select-none"
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(v) => {
                              if (viewMode === 'today') toggleTodayCol(c.key as TodayColKey, !!v)
                              else toggleWeekCol(c.key as WeekColKey, !!v)
                            }}
                            className="h-3.5 w-3.5"
                          />
                          {c.label}
                        </label>
                      )
                    })}
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
        <span className="text-muted-foreground">/ {totalCount} total</span>
      </div>

      {/* Loading */}
      {isLoading && (
        isMobile
          ? <MobileCardList data={[]} fields={todayMobileFields} getRowId={() => 0} isLoading />
          : <div className="space-y-2">{Array.from({ length: 10 }).map((_, i) => <div key={i} className="h-10 animate-pulse rounded bg-muted" />)}</div>
      )}

      {/* ── Today View ── */}
      {!isLoading && viewMode === 'today' && (
        processedToday.length === 0
          ? <EmptyState title="No employees found" description={search ? 'Try a different search term.' : 'No active employees with BioStar mapping.'} />
          : isMobile
            ? <MobileCardList data={processedToday} fields={todayMobileFields} getRowId={(e) => e.jarvis_user_id} onRowClick={(e) => navigate(`/app/hr/pontaje/${e.biostar_user_id}`)} />
            : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8" />
                      <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                        Employee <SortIcon field="name" />
                      </TableHead>
                      {visibleTodayCols.has('company') && (
                        <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('company')}>
                          Company <SortIcon field="company" />
                        </TableHead>
                      )}
                      {visibleTodayCols.has('group') && (
                        <TableHead className="hidden lg:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                          Group <SortIcon field="group" />
                        </TableHead>
                      )}
                      {visibleTodayCols.has('status') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('status')}>
                          Status <SortIcon field="status" />
                        </TableHead>
                      )}
                      {visibleTodayCols.has('check_in') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_in')}>
                          Check In <SortIcon field="check_in" />
                        </TableHead>
                      )}
                      {visibleTodayCols.has('check_out') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_out')}>
                          Check Out <SortIcon field="check_out" />
                        </TableHead>
                      )}
                      {visibleTodayCols.has('adj_in') && (
                        <TableHead className="text-center hidden lg:table-cell">Adj. In</TableHead>
                      )}
                      {visibleTodayCols.has('adj_out') && (
                        <TableHead className="text-center hidden lg:table-cell">Adj. Out</TableHead>
                      )}
                      {visibleTodayCols.has('duration') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('duration')}>
                          Duration <SortIcon field="duration" />
                        </TableHead>
                      )}
                      {visibleTodayCols.has('punches') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('punches')}>
                          Punches <SortIcon field="punches" />
                        </TableHead>
                      )}
                      {canAdjust && <TableHead className="w-10" />}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {processedToday.map((emp) => (
                      <TodayEmployeeRow
                        key={emp.biostar_user_id}
                        employee={emp}
                        date={date}
                        isExpanded={expandedId === emp.biostar_user_id}
                        onToggle={() => setExpandedId(expandedId === emp.biostar_user_id ? null : emp.biostar_user_id)}
                        onProfile={() => navigate(`/app/hr/pontaje/${emp.biostar_user_id}`)}
                        visibleCols={visibleTodayCols}
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

      {/* ── Week View ── */}
      {!isLoading && viewMode === 'week' && (
        processedWeek.length === 0
          ? <EmptyState title="No employees found" description={search ? 'Try a different search term.' : 'No active employees with BioStar mapping.'} />
          : isMobile
            ? <MobileCardList data={processedWeek} fields={weekMobileFields} getRowId={(e) => e.jarvis_user_id} onRowClick={(e) => navigate(`/app/hr/pontaje/${e.biostar_user_id}`)} />
            : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                        Employee <SortIcon field="name" />
                      </TableHead>
                      {visibleWeekCols.has('company') && (
                        <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('company')}>
                          Company <SortIcon field="company" />
                        </TableHead>
                      )}
                      {visibleWeekCols.has('group') && (
                        <TableHead className="hidden lg:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                          Group <SortIcon field="group" />
                        </TableHead>
                      )}
                      {visibleWeekCols.has('days_present') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('days_present')}>
                          Days Present <SortIcon field="days_present" />
                        </TableHead>
                      )}
                      {visibleWeekCols.has('days_absent') && (
                        <TableHead className="text-center">Days Absent</TableHead>
                      )}
                      {visibleWeekCols.has('total_hours') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('total_hours')}>
                          Total Hours <SortIcon field="total_hours" />
                        </TableHead>
                      )}
                      {visibleWeekCols.has('avg_hours') && (
                        <TableHead className="text-center">Avg/Day</TableHead>
                      )}
                      {visibleWeekCols.has('adjustments') && (
                        <TableHead className="text-center">Adj.</TableHead>
                      )}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {processedWeek.map((emp) => (
                      <WeekEmployeeRow
                        key={emp.biostar_user_id}
                        employee={emp}
                        onProfile={() => navigate(`/app/hr/pontaje/${emp.biostar_user_id}`)}
                        visibleCols={visibleWeekCols}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>
            )
      )}

      <div className="text-sm text-muted-foreground">
        Showing {viewMode === 'today' ? processedToday.length : processedWeek.length} of {totalCount} employees
      </div>
    </div>
  )
}

// ── Today Employee Row ──

function TodayEmployeeRow({
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
  visibleCols: Set<TodayColKey>
  canAdjust: boolean
  onRevert: () => void
}) {
  const isAbsent = employee.attendance_status === 'absent'
  const lunch = employee.lunch_break_minutes ?? 60
  const net = netSeconds(employee.duration_seconds, lunch)
  const expectedH = employee.working_hours ?? 8
  const netH = net / 3600
  const isShort = netH > 0 && netH < expectedH

  const colSpan = 2
    + (visibleCols.has('company') ? 1 : 0)
    + (visibleCols.has('group') ? 1 : 0)
    + (visibleCols.has('status') ? 1 : 0)
    + (visibleCols.has('check_in') ? 1 : 0)
    + (visibleCols.has('check_out') ? 1 : 0)
    + (visibleCols.has('adj_in') ? 1 : 0)
    + (visibleCols.has('adj_out') ? 1 : 0)
    + (visibleCols.has('duration') ? 1 : 0)
    + (visibleCols.has('punches') ? 1 : 0)
    + (canAdjust ? 1 : 0)

  return (
    <>
      <TableRow className={cn('cursor-pointer hover:bg-muted/50', isAbsent && 'opacity-60')} onClick={isAbsent ? undefined : onToggle}>
        <TableCell className="w-8 px-2">
          {isAbsent ? (
            <span className="inline-block h-4 w-4" />
          ) : isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell>
          <div className="min-w-0">
            <button
              className="font-medium hover:underline text-left"
              onClick={(e) => { e.stopPropagation(); onProfile() }}
            >
              {employee.name}
            </button>
            {employee.email && (
              <p className="text-xs text-muted-foreground">{employee.email}</p>
            )}
          </div>
        </TableCell>
        {visibleCols.has('company') && (
          <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
            {employee.company || '-'}
          </TableCell>
        )}
        {visibleCols.has('group') && (
          <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
            {employee.user_group_name || '-'}
          </TableCell>
        )}
        {visibleCols.has('status') && (
          <TableCell className="text-center">
            {isAbsent ? (
              <Badge variant="outline" className="text-xs text-red-600 border-red-300">Absent</Badge>
            ) : (
              <Badge variant="outline" className="text-xs text-green-600 border-green-300">Present</Badge>
            )}
          </TableCell>
        )}
        {visibleCols.has('check_in') && (
          <TableCell className="text-center">
            {isAbsent ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-sm">
                <LogIn className="h-3 w-3 text-green-600" />
                {formatTime(employee.first_punch)}
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
                {formatTime(employee.last_punch)}
              </span>
            )}
          </TableCell>
        )}
        {visibleCols.has('adj_in') && (
          <TableCell className="text-center hidden lg:table-cell">
            {employee.adjusted_first_punch
              ? <span className="text-sm font-medium text-green-600">{formatTime(employee.adjusted_first_punch)}</span>
              : <span className="text-muted-foreground">—</span>}
          </TableCell>
        )}
        {visibleCols.has('adj_out') && (
          <TableCell className="text-center hidden lg:table-cell">
            {employee.adjusted_last_punch
              ? <span className="text-sm font-medium text-green-600">{formatTime(employee.adjusted_last_punch)}</span>
              : <span className="text-muted-foreground">—</span>}
          </TableCell>
        )}
        {visibleCols.has('duration') && (
          <TableCell className="text-center">
            {isAbsent || (employee.total_punches ?? 0) === 1 ? (
              <span className="text-muted-foreground">—</span>
            ) : (
              <>
                <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
                  {formatDuration(net)}
                </span>
                {net > 0 && lunch > 0 && (
                  <span className="block text-[10px] text-muted-foreground">-{lunch}m lunch</span>
                )}
              </>
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
        {canAdjust && (
          <TableCell className="text-center w-10">
            {employee.adjustment_type && (
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
      </TableRow>
      {isExpanded && !isAbsent && (
        <TableRow>
          <TableCell colSpan={colSpan} className="bg-muted/30 p-0">
            <DayPunches biostarUserId={employee.biostar_user_id} date={date} onProfile={onProfile} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

// ── Week Employee Row ──

function WeekEmployeeRow({
  employee,
  onProfile,
  visibleCols,
}: {
  employee: AttendanceWeekRow
  onProfile: () => void
  visibleCols: Set<WeekColKey>
}) {
  const lunch = employee.lunch_break_minutes ?? 60
  const totalNet = netSeconds(employee.total_duration_seconds, lunch * employee.days_present)
  const totalH = totalNet / 3600
  const avgH = employee.days_present > 0 ? totalNet / employee.days_present / 3600 : 0
  const expectedH = (employee.working_hours ?? 8) * employee.days_present
  const isShort = totalH > 0 && totalH < expectedH

  return (
    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onProfile}>
      <TableCell>
        <div className="min-w-0">
          <button className="font-medium hover:underline text-left" onClick={(e) => { e.stopPropagation(); onProfile() }}>
            {employee.name}
          </button>
          {employee.email && (
            <p className="text-xs text-muted-foreground">{employee.email}</p>
          )}
        </div>
      </TableCell>
      {visibleCols.has('company') && (
        <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
          {employee.company || '-'}
        </TableCell>
      )}
      {visibleCols.has('group') && (
        <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
          {employee.user_group_name || '-'}
        </TableCell>
      )}
      {visibleCols.has('days_present') && (
        <TableCell className="text-center">
          <span className="text-sm font-medium">{employee.days_present}</span>
          <span className="text-xs text-muted-foreground"> / 7</span>
        </TableCell>
      )}
      {visibleCols.has('days_absent') && (
        <TableCell className="text-center">
          {employee.days_absent > 0 ? (
            <span className="text-sm font-medium text-red-600">{employee.days_absent}</span>
          ) : (
            <span className="text-sm text-muted-foreground">0</span>
          )}
        </TableCell>
      )}
      {visibleCols.has('total_hours') && (
        <TableCell className="text-center">
          <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
            {formatDuration(totalNet)}
          </span>
        </TableCell>
      )}
      {visibleCols.has('avg_hours') && (
        <TableCell className="text-center">
          <span className="text-sm">{avgH.toFixed(1)}h</span>
        </TableCell>
      )}
      {visibleCols.has('adjustments') && (
        <TableCell className="text-center">
          {employee.adjustment_count > 0 ? (
            <Badge variant="secondary" className="text-xs">{employee.adjustment_count}</Badge>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </TableCell>
      )}
    </TableRow>
  )
}

// ── Day's punches inline ──

function DayPunches({ biostarUserId, date, onProfile }: { biostarUserId: string; date: string; onProfile: () => void }) {
  const { data: punches = [], isLoading } = useQuery({
    queryKey: ['biostar', 'employee-punches', biostarUserId, date],
    queryFn: () => biostarApi.getEmployeePunches(biostarUserId, date),
  })

  if (isLoading) {
    return (
      <div className="p-4 space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-6 animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
          <Fingerprint className="h-3.5 w-3.5" />
          {date} — {punches.length} events
        </div>
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onProfile}>
          <ExternalLink className="mr-1 h-3 w-3" />
          Full History
        </Button>
      </div>
      {punches.length === 0 ? (
        <p className="text-sm text-muted-foreground">No punch events found.</p>
      ) : (
        <div className="relative ml-4 border-l-2 border-muted-foreground/20 pl-4 space-y-2">
          {punches.map((p, i) => (
            <PunchEventLine key={p.id} punch={p} isFirst={i === 0} isLast={i === punches.length - 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function PunchEventLine({
  punch,
  isFirst,
  isLast,
}: {
  punch: BioStarPunchLog
  isFirst: boolean
  isLast: boolean
}) {
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
