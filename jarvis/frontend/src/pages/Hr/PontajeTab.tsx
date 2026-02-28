import { useState, useMemo } from 'react'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Search,
  ChevronDown,
  ChevronRight,
  ArrowUpDown,
  Clock,
  LogIn,
  LogOut,
  UserCheck,
  Fingerprint,
  ExternalLink,
  Calendar,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/shared/EmptyState'
import { StatCard } from '@/components/shared/StatCard'
import { biostarApi } from '@/api/biostar'
import { cn } from '@/lib/utils'
import type { BioStarDailySummary, BioStarRangeSummary, BioStarPunchLog } from '@/types/biostar'

type SortField = 'name' | 'group' | 'check_in' | 'check_out' | 'duration' | 'punches'
type SortDir = 'asc' | 'desc'
type QuickFilter = 'today' | '7d' | 'month' | 'last_month' | 'ytd' | 'custom'

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

function netSeconds(durationSec: number | null, lunchMin: number) {
  if (!durationSec || durationSec <= 0) return 0
  const lunchSec = lunchMin * 60
  return durationSec > lunchSec ? durationSec - lunchSec : durationSec
}

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function getDateRange(filter: QuickFilter, customStart: string, customEnd: string): { start: string; end: string; isSingleDay: boolean } {
  const now = new Date()
  const today = todayStr()

  switch (filter) {
    case 'today':
      return { start: today, end: today, isSingleDay: true }
    case '7d': {
      const d = new Date(now)
      d.setDate(d.getDate() - 6)
      return { start: d.toISOString().slice(0, 10), end: today, isSingleDay: false }
    }
    case 'month': {
      const start = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
      return { start, end: today, isSingleDay: false }
    }
    case 'last_month': {
      const d = new Date(now.getFullYear(), now.getMonth() - 1, 1)
      const last = new Date(now.getFullYear(), now.getMonth(), 0)
      return {
        start: d.toISOString().slice(0, 10),
        end: last.toISOString().slice(0, 10),
        isSingleDay: false,
      }
    }
    case 'ytd': {
      return { start: `${now.getFullYear()}-01-01`, end: today, isSingleDay: false }
    }
    case 'custom':
      if (customStart && customEnd && customStart === customEnd) {
        return { start: customStart, end: customEnd, isSingleDay: true }
      }
      return { start: customStart || today, end: customEnd || today, isSingleDay: false }
  }
}

const QUICK_FILTERS: { value: QuickFilter; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: '7d', label: 'Last 7 Days' },
  { value: 'month', label: 'This Month' },
  { value: 'last_month', label: 'Last Month' },
  { value: 'ytd', label: 'YTD' },
]

export default function PontajeTab({ showStats = false }: { showStats?: boolean }) {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const [search, setSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState<string>('all')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [quickFilter, setQuickFilter] = useState<QuickFilter>('today')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [showDatePickers, setShowDatePickers] = useState(false)

  const { start, end, isSingleDay } = getDateRange(quickFilter, customStart, customEnd)

  const { data: status } = useQuery({
    queryKey: ['biostar', 'status'],
    queryFn: biostarApi.getStatus,
  })

  const connected = !!status?.connected

  // Single day query
  const { data: dailySummary = [], isLoading: loadingDaily } = useQuery({
    queryKey: ['biostar', 'daily-summary', start],
    queryFn: () => biostarApi.getDailySummary(start),
    enabled: isSingleDay,
    refetchInterval: isSingleDay && connected ? 60_000 : false,
  })

  // Range query
  const { data: rangeSummary = [], isLoading: loadingRange } = useQuery({
    queryKey: ['biostar', 'range-summary', start, end],
    queryFn: () => biostarApi.getRangeSummary(start, end),
    enabled: !isSingleDay && !!start && !!end,
  })

  const isLoading = isSingleDay ? loadingDaily : loadingRange

  // Groups from whichever data is active
  const activeData = isSingleDay ? dailySummary : rangeSummary
  const groups = useMemo(() => {
    const set = new Set<string>()
    activeData.forEach((e) => { if (e.user_group_name) set.add(e.user_group_name) })
    return Array.from(set).sort()
  }, [activeData])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  // Process single-day data
  const processedDaily = useMemo(() => {
    if (!isSingleDay) return []
    let list = [...dailySummary]
    if (groupFilter !== 'all') list = list.filter((e) => e.user_group_name === groupFilter)
    if (search) {
      const s = search.toLowerCase()
      list = list.filter((e) =>
        (e.name || '').toLowerCase().includes(s) ||
        (e.email || '').toLowerCase().includes(s) ||
        (e.user_group_name || '').toLowerCase().includes(s) ||
        (e.mapped_jarvis_user_name || '').toLowerCase().includes(s),
      )
    }
    list.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'name': cmp = (a.name || '').localeCompare(b.name || ''); break
        case 'group': cmp = (a.user_group_name || '').localeCompare(b.user_group_name || ''); break
        case 'check_in': cmp = (a.first_punch || '').localeCompare(b.first_punch || ''); break
        case 'check_out': cmp = (a.last_punch || '').localeCompare(b.last_punch || ''); break
        case 'duration': cmp = netSeconds(a.duration_seconds, a.lunch_break_minutes ?? 60) - netSeconds(b.duration_seconds, b.lunch_break_minutes ?? 60); break
        case 'punches': cmp = a.total_punches - b.total_punches; break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [dailySummary, groupFilter, search, sortField, sortDir, isSingleDay])

  // Process range data
  const processedRange = useMemo(() => {
    if (isSingleDay) return []
    let list = [...rangeSummary]
    if (groupFilter !== 'all') list = list.filter((e) => e.user_group_name === groupFilter)
    if (search) {
      const s = search.toLowerCase()
      list = list.filter((e) =>
        (e.name || '').toLowerCase().includes(s) ||
        (e.email || '').toLowerCase().includes(s) ||
        (e.user_group_name || '').toLowerCase().includes(s) ||
        (e.mapped_jarvis_user_name || '').toLowerCase().includes(s),
      )
    }
    list.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'name': cmp = (a.name || '').localeCompare(b.name || ''); break
        case 'group': cmp = (a.user_group_name || '').localeCompare(b.user_group_name || ''); break
        case 'duration': cmp = netSeconds(a.total_duration_seconds, (a.lunch_break_minutes ?? 60) * a.days_present) - netSeconds(b.total_duration_seconds, (b.lunch_break_minutes ?? 60) * b.days_present); break
        case 'punches': cmp = a.total_punches - b.total_punches; break
        default: cmp = (a.name || '').localeCompare(b.name || ''); break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [rangeSummary, groupFilter, search, sortField, sortDir, isSingleDay])

  // Stats
  const totalPresent = isSingleDay ? dailySummary.length : rangeSummary.length
  const totalHours = isSingleDay
    ? dailySummary.reduce((acc, e) => acc + netSeconds(e.duration_seconds, e.lunch_break_minutes ?? 60), 0) / 3600
    : rangeSummary.reduce((acc, e) => acc + netSeconds(e.total_duration_seconds, (e.lunch_break_minutes ?? 60) * e.days_present), 0) / 3600
  const avgHours = totalPresent > 0 ? totalHours / totalPresent : 0
  const earlyBirds = isSingleDay
    ? dailySummary.filter((e) => e.first_punch && new Date(e.first_punch).getHours() < 8).length
    : 0

  const dailyMobileFields: MobileCardField<BioStarDailySummary>[] = useMemo(() => [
    {
      key: 'name',
      label: 'Employee',
      isPrimary: true,
      render: (e) => e.name || '—',
    },
    {
      key: 'group',
      label: 'Group',
      isSecondary: true,
      render: (e) => e.user_group_name || '—',
    },
    {
      key: 'checkin',
      label: 'Check In',
      render: (e) => (
        <span className="inline-flex items-center gap-1 text-sm">
          <LogIn className="h-3 w-3 text-green-600" />
          {formatTime(e.first_punch)}
        </span>
      ),
    },
    {
      key: 'checkout',
      label: 'Check Out',
      render: (e) =>
        e.total_punches === 1
          ? <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
          : (
            <span className="inline-flex items-center gap-1 text-sm">
              <LogOut className="h-3 w-3 text-red-500" />
              {formatTime(e.last_punch)}
            </span>
          ),
    },
    {
      key: 'duration',
      label: 'Duration',
      render: (e) => {
        const net = netSeconds(e.duration_seconds, e.lunch_break_minutes ?? 60)
        const isShort = net / 3600 > 0 && net / 3600 < (e.working_hours ?? 8)
        return (
          <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
            {e.total_punches === 1 ? '—' : formatDuration(net)}
          </span>
        )
      },
    },
    {
      key: 'punches',
      label: 'Punches',
      expandOnly: true,
      render: (e) => <Badge variant="secondary" className="text-xs">{e.total_punches}</Badge>,
    },
    {
      key: 'email',
      label: 'Email',
      expandOnly: true,
      render: (e) => <span className="text-xs text-muted-foreground">{e.email || '—'}</span>,
    },
  ], [])

  const rangeMobileFields: MobileCardField<BioStarRangeSummary>[] = useMemo(() => [
    {
      key: 'name',
      label: 'Employee',
      isPrimary: true,
      render: (e) => e.name || '—',
    },
    {
      key: 'group',
      label: 'Group',
      isSecondary: true,
      render: (e) => e.user_group_name || '—',
    },
    {
      key: 'days',
      label: 'Days Present',
      render: (e) => <Badge variant="secondary" className="text-xs">{e.days_present}</Badge>,
    },
    {
      key: 'total_hours',
      label: 'Total Hours',
      render: (e) => {
        const lunch = e.lunch_break_minutes ?? 60
        const totalNet = netSeconds(e.total_duration_seconds, lunch * e.days_present)
        const expectedH = (e.working_hours ?? 8) * e.days_present
        const isShort = totalNet / 3600 > 0 && totalNet / 3600 < expectedH
        return (
          <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
            {formatDuration(totalNet)}
          </span>
        )
      },
    },
    {
      key: 'avg_day',
      label: 'Avg/Day',
      render: (e) => {
        const lunch = e.lunch_break_minutes ?? 60
        const totalNet = netSeconds(e.total_duration_seconds, lunch * e.days_present)
        const avgH = e.days_present > 0 ? totalNet / e.days_present / 3600 : 0
        return <span className="text-sm">{avgH.toFixed(1)}h</span>
      },
    },
    {
      key: 'punches',
      label: 'Punches',
      expandOnly: true,
      render: (e) => <Badge variant="secondary" className="text-xs">{e.total_punches}</Badge>,
    },
  ], [])

  const handleQuickFilter = (f: QuickFilter) => {
    setQuickFilter(f)
    setExpandedId(null)
  }

  const SortIcon = ({ field }: { field: SortField }) => (
    <ArrowUpDown className={cn('ml-1 h-3 w-3 inline', sortField === field ? 'opacity-100' : 'opacity-40')} />
  )

  const rangeLabel = isSingleDay
    ? new Date(start).toLocaleDateString('ro-RO', { weekday: 'long', day: 'numeric', month: 'long' })
    : `${new Date(start).toLocaleDateString('ro-RO')} — ${new Date(end).toLocaleDateString('ro-RO')}`

  return (
    <div className="space-y-4">
      {/* Connection warning */}
      {!connected && (
        <div className="flex items-center gap-2 rounded-md border border-orange-300 bg-orange-50 px-4 py-2 text-sm text-orange-800 dark:border-orange-700 dark:bg-orange-950/30 dark:text-orange-300">
          <Clock className="h-4 w-4 shrink-0" />
          <span>BioStar not connected — showing cached data. Configure connection in Settings &gt; Connectors.</span>
        </div>
      )}

      {/* Quick filters + date pickers */}
      <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-center">
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 md:mx-0 md:flex-wrap md:px-0">
          {QUICK_FILTERS.map((f) => (
            <Button
              key={f.value}
              size="sm"
              variant={quickFilter === f.value ? 'default' : 'outline'}
              className="h-8 flex-1 md:flex-none shrink-0 text-xs"
              onClick={() => handleQuickFilter(f.value)}
            >
              {f.label}
            </Button>
          ))}
          {isMobile && (
            <Button
              size="icon"
              variant={quickFilter === 'custom' ? 'default' : 'outline'}
              className="h-8 shrink-0"
              onClick={() => { setShowDatePickers((p) => !p); if (quickFilter !== 'custom') { setQuickFilter('custom'); setCustomStart(start); setCustomEnd(end) } }}
            >
              <Calendar className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
        {(!isMobile || showDatePickers) && (
          <div className="flex items-center gap-1.5 md:ml-auto">
            <Calendar className="hidden md:block h-4 w-4 text-muted-foreground" />
            <Input
              type="date"
              className="h-8 w-36 text-xs"
              value={quickFilter === 'custom' ? customStart : start}
              onChange={(e) => {
                setQuickFilter('custom')
                setCustomStart(e.target.value)
                if (!customEnd || e.target.value > customEnd) setCustomEnd(e.target.value)
              }}
            />
            <span className="text-xs text-muted-foreground">—</span>
            <Input
              type="date"
              className="h-8 w-36 text-xs"
              value={quickFilter === 'custom' ? customEnd : end}
              onChange={(e) => {
                setQuickFilter('custom')
                setCustomEnd(e.target.value)
                if (!customStart || e.target.value < customStart) setCustomStart(e.target.value)
              }}
            />
          </div>
        )}
      </div>

      {/* Date label — desktop only */}
      <p className="hidden md:block text-xs text-muted-foreground">{rangeLabel}</p>

      {/* Stats */}
      <div className={`grid grid-cols-2 gap-3 lg:grid-cols-4 ${showStats ? '' : 'hidden md:grid'}`}>
        <StatCard title={isSingleDay ? 'Present Today' : 'Employees'} value={totalPresent} icon={<UserCheck className="h-4 w-4" />} />
        <StatCard title="Total Hours" value={totalHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title={isSingleDay ? 'Avg Hours' : 'Avg Hours / Employee'} value={avgHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        {isSingleDay ? (
          <StatCard title="Early (<8:00)" value={earlyBirds} icon={<LogIn className="h-4 w-4" />} />
        ) : (
          <StatCard title="Avg Days Present" value={totalPresent > 0 ? (rangeSummary.reduce((a, e) => a + e.days_present, 0) / totalPresent).toFixed(1) : '0'} icon={<Calendar className="h-4 w-4" />} />
        )}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search by name, email, group..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={groupFilter} onValueChange={setGroupFilter}>
          <SelectTrigger className="w-40 md:w-44 shrink-0">
            <SelectValue placeholder="All Groups" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Groups ({activeData.length})</SelectItem>
            {groups.map((g) => (
              <SelectItem key={g} value={g}>
                {g} ({activeData.filter((e) => e.user_group_name === g).length})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table / Card list */}
      {isLoading ? (
        isMobile ? (
          <MobileCardList data={[]} fields={dailyMobileFields} getRowId={() => 0} isLoading />
        ) : (
          <div className="space-y-2">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        )
      ) : isSingleDay ? (
        /* Single-day */
        processedDaily.length === 0 ? (
          <EmptyState
            title="No attendance data"
            description={search ? 'Try a different search term.' : 'No punch logs found for this date.'}
          />
        ) : isMobile ? (
          <MobileCardList
            data={processedDaily}
            fields={dailyMobileFields}
            getRowId={(e) => Number(e.biostar_user_id)}
            onRowClick={(e) => navigate(`/app/hr/pontaje/${e.biostar_user_id}`)}
          />
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                    Employee <SortIcon field="name" />
                  </TableHead>
                  <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                    Group <SortIcon field="group" />
                  </TableHead>
                  <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_in')}>
                    Check In <SortIcon field="check_in" />
                  </TableHead>
                  <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_out')}>
                    Check Out <SortIcon field="check_out" />
                  </TableHead>
                  <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('duration')}>
                    Duration <SortIcon field="duration" />
                  </TableHead>
                  <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('punches')}>
                    Punches <SortIcon field="punches" />
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {processedDaily.map((emp) => (
                  <EmployeeRow
                    key={emp.biostar_user_id}
                    employee={emp}
                    date={start}
                    isExpanded={expandedId === emp.biostar_user_id}
                    onToggle={() => setExpandedId(expandedId === emp.biostar_user_id ? null : emp.biostar_user_id)}
                    onProfile={() => navigate(`/app/hr/pontaje/${emp.biostar_user_id}`)}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        )
      ) : (
        /* Range */
        processedRange.length === 0 ? (
          <EmptyState
            title="No attendance data"
            description={search ? 'Try a different search term.' : 'No punch logs found for this period.'}
          />
        ) : isMobile ? (
          <MobileCardList
            data={processedRange}
            fields={rangeMobileFields}
            getRowId={(e) => Number(e.biostar_user_id)}
            onRowClick={(e) => navigate(`/app/hr/pontaje/${e.biostar_user_id}`)}
          />
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                    Employee <SortIcon field="name" />
                  </TableHead>
                  <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                    Group <SortIcon field="group" />
                  </TableHead>
                  <TableHead className="text-center">Days</TableHead>
                  <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('duration')}>
                    Total Hours <SortIcon field="duration" />
                  </TableHead>
                  <TableHead className="text-center">Avg/Day</TableHead>
                  <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('punches')}>
                    Punches <SortIcon field="punches" />
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {processedRange.map((emp) => (
                  <RangeEmployeeRow
                    key={emp.biostar_user_id}
                    employee={emp}
                    onProfile={() => navigate(`/app/hr/pontaje/${emp.biostar_user_id}`)}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        )
      )}

      <div className="text-sm text-muted-foreground">
        Showing {isSingleDay ? processedDaily.length : processedRange.length} of {activeData.length} employees
      </div>
    </div>
  )
}

// ── Range Employee Row ──

function RangeEmployeeRow({
  employee,
  onProfile,
}: {
  employee: BioStarRangeSummary
  onProfile: () => void
}) {
  const lunch = employee.lunch_break_minutes ?? 60
  const expectedH = (employee.working_hours ?? 8) * employee.days_present
  const totalNet = netSeconds(employee.total_duration_seconds, lunch * employee.days_present)
  const totalH = totalNet / 3600
  const avgNet = employee.days_present > 0 ? totalNet / employee.days_present : 0
  const avgH = avgNet / 3600
  const isShort = totalH > 0 && totalH < expectedH

  return (
    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onProfile}>
      <TableCell>
        <div className="min-w-0">
          <button className="font-medium hover:underline text-left" onClick={(e) => { e.stopPropagation(); onProfile() }}>
            {employee.name}
          </button>
          {employee.mapped_jarvis_user_name && (
            <Badge variant="outline" className="ml-2 text-[10px] font-normal">
              {employee.mapped_jarvis_user_name}
            </Badge>
          )}
        </div>
      </TableCell>
      <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
        {employee.user_group_name || '-'}
      </TableCell>
      <TableCell className="text-center">
        <Badge variant="secondary" className="text-xs">{employee.days_present}</Badge>
      </TableCell>
      <TableCell className="text-center">
        <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
          {formatDuration(totalNet)}
        </span>
      </TableCell>
      <TableCell className="text-center">
        <span className="text-sm">{avgH.toFixed(1)}h</span>
      </TableCell>
      <TableCell className="text-center">
        <Badge variant="secondary" className="text-xs">{employee.total_punches}</Badge>
      </TableCell>
    </TableRow>
  )
}

// ── Single-day Employee Row ──

function EmployeeRow({
  employee,
  date,
  isExpanded,
  onToggle,
  onProfile,
}: {
  employee: BioStarDailySummary
  date: string
  isExpanded: boolean
  onToggle: () => void
  onProfile: () => void
}) {
  const lunch = employee.lunch_break_minutes ?? 60
  const expectedH = employee.working_hours ?? 8
  const net = netSeconds(employee.duration_seconds, lunch)
  const netH = net / 3600
  const isShort = netH > 0 && netH < expectedH

  return (
    <>
      <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onToggle}>
        <TableCell className="w-8 px-2">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <div className="min-w-0">
              <button
                className="font-medium hover:underline text-left"
                onClick={(e) => { e.stopPropagation(); onProfile() }}
              >
                {employee.name}
              </button>
              {employee.mapped_jarvis_user_name && (
                <Badge variant="outline" className="ml-2 text-[10px] font-normal">
                  {employee.mapped_jarvis_user_name}
                </Badge>
              )}
              {employee.email && (
                <p className="text-xs text-muted-foreground">{employee.email}</p>
              )}
            </div>
          </div>
        </TableCell>
        <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
          {employee.user_group_name || '-'}
        </TableCell>
        <TableCell className="text-center">
          <span className="inline-flex items-center gap-1 text-sm">
            <LogIn className="h-3 w-3 text-green-600" />
            {formatTime(employee.first_punch)}
          </span>
        </TableCell>
        <TableCell className="text-center">
          {employee.total_punches === 1 ? (
            <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">Not exited</Badge>
          ) : (
            <span className="inline-flex items-center gap-1 text-sm">
              <LogOut className="h-3 w-3 text-red-500" />
              {formatTime(employee.last_punch)}
            </span>
          )}
        </TableCell>
        <TableCell className="text-center">
          {employee.total_punches === 1 ? (
            <span className="text-sm text-muted-foreground">—</span>
          ) : (
          <span className={cn(
            'text-sm font-medium',
            isShort ? 'text-orange-600' : 'text-foreground',
          )}>
            {formatDuration(net)}
          </span>
          )}
          {net > 0 && lunch > 0 && (
            <span className="block text-[10px] text-muted-foreground">-{lunch}m lunch</span>
          )}
        </TableCell>
        <TableCell className="text-center">
          <Badge variant="secondary" className="text-xs">
            {employee.total_punches}
          </Badge>
        </TableCell>
      </TableRow>
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/30 p-0">
            <DayPunches biostarUserId={employee.biostar_user_id} date={date} onProfile={onProfile} />
          </TableCell>
        </TableRow>
      )}
    </>
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
