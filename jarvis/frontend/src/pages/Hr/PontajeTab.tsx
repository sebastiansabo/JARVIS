import { useState, useMemo, useRef, useEffect } from 'react'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import {
  Search,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  ArrowUpDown,
  Clock,
  LogIn,
  LogOut,
  UserCheck,
  Users,
  Fingerprint,
  ExternalLink,
  Calendar,
  Columns3,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/shared/EmptyState'
import { StatCard } from '@/components/shared/StatCard'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { biostarApi } from '@/api/biostar'
import { hrApi } from '@/api/hr'
import { cn } from '@/lib/utils'
import type { BioStarDailySummary, BioStarRangeSummary, BioStarPunchLog } from '@/types/biostar'

type SortField = 'name' | 'group' | 'check_in' | 'check_out' | 'duration' | 'punches'
type SortDir = 'asc' | 'desc'
type QuickFilter = 'today' | '3d' | '7d' | 'month' | 'last_month' | 'ytd' | 'custom'
type DailyColKey = 'group' | 'check_in' | 'check_out' | 'adj_in' | 'adj_out' | 'duration' | 'punches'
type RangeColKey = 'group' | 'avg_check_in' | 'avg_check_out' | 'days' | 'total_hours' | 'adj_hours' | 'avg_day' | 'punches'

const DAILY_COL_DEFS: { key: DailyColKey; label: string }[] = [
  { key: 'group', label: 'Group' },
  { key: 'check_in', label: 'Check In' },
  { key: 'check_out', label: 'Check Out' },
  { key: 'adj_in', label: 'In' },
  { key: 'adj_out', label: 'Out' },
  { key: 'duration', label: 'Duration' },
  { key: 'punches', label: 'Punches' },
]

const RANGE_COL_DEFS: { key: RangeColKey; label: string }[] = [
  { key: 'group', label: 'Group' },
  { key: 'avg_check_in', label: 'Avg Check In' },
  { key: 'avg_check_out', label: 'Avg Check Out' },
  { key: 'days', label: 'Days Present' },
  { key: 'total_hours', label: 'Total Hours' },
  { key: 'adj_hours', label: 'Adj. Hours' },
  { key: 'avg_day', label: 'Avg/Day' },
  { key: 'punches', label: 'Punches' },
]

const DEFAULT_DAILY_COLS: DailyColKey[] = ['group', 'check_in', 'check_out', 'adj_in', 'adj_out', 'duration', 'punches']
const DEFAULT_RANGE_COLS: RangeColKey[] = ['group', 'avg_check_in', 'avg_check_out', 'days', 'total_hours', 'adj_hours', 'avg_day', 'punches']

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

function formatEpochTime(epoch: number | null) {
  if (!epoch || epoch <= 0) return '-'
  const h = Math.floor(epoch / 3600)
  const m = Math.floor((epoch % 3600) / 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
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

function dateOffset(days: number) {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function getDateRange(filter: QuickFilter, customStart: string, customEnd: string): { start: string; end: string; isSingleDay: boolean } {
  const now = new Date()
  const today = todayStr()

  switch (filter) {
    case 'today':
      return { start: today, end: today, isSingleDay: true }
    case '3d':
      return { start: dateOffset(2), end: today, isSingleDay: false }
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
  { value: '3d', label: 'Last 3 Days' },
  { value: '7d', label: 'Last 7 Days' },
  { value: 'month', label: 'This Month' },
  { value: 'last_month', label: 'Last Month' },
  { value: 'ytd', label: 'YTD' },
]

export default function PontajeTab({ showStats = false, showFilters = false }: { showStats?: boolean; showFilters?: boolean }) {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const { user } = useAuth()
  const showOriginal = user?.can_view_original_punches ?? false
  const showAdjusted = user?.can_view_adjusted_punches ?? false
  const [search, setSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState<string>('all')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [quickFilter, setQuickFilter] = useState<QuickFilter>('today')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [statFilter, setStatFilter] = useState<'all' | 'late'>('all')

  // Column visibility
  const [visibleDailyCols, setVisibleDailyCols] = useState<Set<DailyColKey>>(new Set(DEFAULT_DAILY_COLS))
  const [visibleRangeCols, setVisibleRangeCols] = useState<Set<RangeColKey>>(new Set(DEFAULT_RANGE_COLS))
  const adjInitRef = useRef(false)

  // Add columns to default once user data loads based on permissions
  useEffect(() => {
    if (!adjInitRef.current && user !== null) {
      adjInitRef.current = true
      setVisibleDailyCols(prev => {
        const n = new Set(prev)
        if (showOriginal) { n.add('check_in'); n.add('check_out') }
        if (showAdjusted) { n.add('adj_in'); n.add('adj_out') }
        return n
      })
    }
  }, [user, showOriginal, showAdjusted])

  const toggleDailyCol = (key: DailyColKey, checked: boolean) => {
    setVisibleDailyCols(prev => { const n = new Set(prev); checked ? n.add(key) : n.delete(key); return n })
  }

  const toggleCheckInOut = () => {
    const bothVisible = visibleDailyCols.has('check_in') && visibleDailyCols.has('check_out')
    setVisibleDailyCols(prev => {
      const n = new Set(prev)
      if (bothVisible) { n.delete('check_in'); n.delete('check_out') }
      else { n.add('check_in'); n.add('check_out') }
      return n
    })
  }

  const toggleAdjInOut = () => {
    const bothVisible = visibleDailyCols.has('adj_in') && visibleDailyCols.has('adj_out')
    setVisibleDailyCols(prev => {
      const n = new Set(prev)
      if (bothVisible) { n.delete('adj_in'); n.delete('adj_out') }
      else { n.add('adj_in'); n.add('adj_out') }
      return n
    })
  }
  const toggleRangeCol = (key: RangeColKey, checked: boolean) => {
    setVisibleRangeCols(prev => { const n = new Set(prev); checked ? n.add(key) : n.delete(key); return n })
  }
  const resetDailyCols = () => {
    const s = new Set<DailyColKey>(DEFAULT_DAILY_COLS)
    if (showOriginal) { s.add('check_in'); s.add('check_out') }
    if (showAdjusted) { s.add('adj_in'); s.add('adj_out') }
    setVisibleDailyCols(s)
  }
  const resetRangeCols = () => setVisibleRangeCols(new Set(DEFAULT_RANGE_COLS))

  // Manager filtering — check if current user is a manager via organigram data
  const { data: orgData } = useQuery({
    queryKey: ['hr-organigram'],
    queryFn: () => hrApi.getOrganigram(),
    staleTime: 5 * 60 * 1000,
  })
  const isUserManager = orgData?.is_manager ?? false

  // Managers default to "My Team", HR admins see toggle too
  const [teamFilter, setTeamFilter] = useState<'team' | 'all'>('team')
  const showTeamToggle = isUserManager
  const managerFilter = showTeamToggle && teamFilter === 'team'

  const is3Day = quickFilter === '3d'
  const { start, end, isSingleDay } = getDateRange(quickFilter, customStart, customEnd)

  const { data: status } = useQuery({
    queryKey: ['biostar', 'status'],
    queryFn: biostarApi.getStatus,
  })

  const connected = !!status?.connected

  // Single day query
  const { data: dailySummary = [], isLoading: loadingDaily } = useQuery({
    queryKey: ['biostar', 'daily-summary', start, managerFilter],
    queryFn: () => biostarApi.getDailySummary(start, managerFilter),
    enabled: isSingleDay && !is3Day,
    refetchInterval: isSingleDay && !is3Day && connected ? 60_000 : false,
  })

  // Range query
  const { data: rangeSummary = [], isLoading: loadingRange } = useQuery({
    queryKey: ['biostar', 'range-summary', start, end, managerFilter],
    queryFn: () => biostarApi.getRangeSummary(start, end, managerFilter),
    enabled: !isSingleDay && !is3Day && !!start && !!end,
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

  // Effective visible cols — strips permission-gated keys regardless of toggle state
  const effectiveDailyCols = useMemo(() => {
    const s = new Set(visibleDailyCols)
    if (!showOriginal) { s.delete('check_in'); s.delete('check_out') }
    if (!showAdjusted) { s.delete('adj_in'); s.delete('adj_out') }
    return s
  }, [visibleDailyCols, showOriginal, showAdjusted])

  // Process single-day data
  const processedDaily = useMemo(() => {
    if (!isSingleDay) return []
    let list = [...dailySummary]
    if (groupFilter !== 'all') list = list.filter((e) => e.user_group_name === groupFilter)
    if (statFilter === 'late') {
      list = list.filter((e) => {
        if (!e.first_punch || !e.schedule_start) return false
        const punchTime = new Date(e.first_punch)
        const [sh, sm] = (e.schedule_start as string).split(':').map(Number)
        const schedDate = new Date(punchTime)
        schedDate.setHours(sh, sm + 15, 0, 0)
        return punchTime > schedDate
      })
    }
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
  }, [dailySummary, groupFilter, search, sortField, sortDir, isSingleDay, statFilter])

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
  const lateArrivals = isSingleDay
    ? dailySummary.filter((e) => {
        if (!e.first_punch || !e.schedule_start) return false
        const punchTime = new Date(e.first_punch)
        const [sh, sm] = (e.schedule_start as string).split(':').map(Number)
        const schedDate = new Date(punchTime)
        schedDate.setHours(sh, sm + 15, 0, 0) // 15min grace
        return punchTime > schedDate
      }).length
    : 0
  const avgCheckIn = useMemo(() => {
    const punches = (isSingleDay ? dailySummary : []).filter(e => e.first_punch)
    if (!punches.length) return '-'
    const avg = punches.reduce((acc, e) => acc + new Date(e.first_punch).getHours() * 3600 + new Date(e.first_punch).getMinutes() * 60, 0) / punches.length
    return formatEpochTime(avg)
  }, [dailySummary, isSingleDay])
  const avgCheckOut = useMemo(() => {
    const punches = (isSingleDay ? dailySummary : []).filter(e => e.total_punches > 1 && e.last_punch)
    if (!punches.length) return '-'
    const avg = punches.reduce((acc, e) => acc + new Date(e.last_punch).getHours() * 3600 + new Date(e.last_punch).getMinutes() * 60, 0) / punches.length
    return formatEpochTime(avg)
  }, [dailySummary, isSingleDay])

  const dailyMobileFields: MobileCardField<BioStarDailySummary>[] = useMemo(() => {
    const fields: MobileCardField<BioStarDailySummary>[] = [
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
    ]
    if (showAdjusted) {
      fields.push(
        {
          key: 'adj_in',
          label: 'In',
          render: (e) => e.adjusted_first_punch
            ? <span className="text-sm font-medium text-green-600">{formatTime(e.adjusted_first_punch)}</span>
            : <span className="text-muted-foreground">—</span>,
        },
        {
          key: 'adj_out',
          label: 'Out',
          render: (e) => e.adjusted_last_punch
            ? <span className="text-sm font-medium text-green-600">{formatTime(e.adjusted_last_punch)}</span>
            : <span className="text-muted-foreground">—</span>,
        },
      )
    }
    fields.push(
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
    )
    return fields
  }, [showAdjusted])

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
      key: 'avg_check_in',
      label: 'Avg Check In',
      render: (e) => (
        <span className="inline-flex items-center gap-1 text-sm">
          <LogIn className="h-3 w-3 text-green-600" />
          {formatEpochTime(e.avg_check_in_epoch)}
        </span>
      ),
    },
    {
      key: 'avg_check_out',
      label: 'Avg Check Out',
      render: (e) => (
        <span className="inline-flex items-center gap-1 text-sm">
          <LogOut className="h-3 w-3 text-red-500" />
          {formatEpochTime(e.avg_check_out_epoch)}
        </span>
      ),
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
      key: 'adj_hours',
      label: 'Adj. Hours',
      render: (e) => {
        if (!e.adjustment_count) return <span className="text-muted-foreground">—</span>
        const lunch = e.lunch_break_minutes ?? 60
        const adjNet = netSeconds(e.adjusted_total_duration_seconds, lunch * e.days_present)
        return <span className="text-sm font-medium text-green-600">{formatDuration(adjNet)}</span>
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

  const stepDay = (delta: number) => {
    const s = new Date(start)
    const e = new Date(end)
    s.setDate(s.getDate() + delta)
    e.setDate(e.getDate() + delta)
    const fmt = (d: Date) => d.toISOString().slice(0, 10)
    setQuickFilter('custom')
    setCustomStart(fmt(s))
    setCustomEnd(fmt(e))
    setExpandedId(null)
  }

  const handleQuickFilter = (f: QuickFilter) => {
    setQuickFilter(f)
    setExpandedId(null)
    setStatFilter('all')
  }

  const SortIcon = ({ field }: { field: SortField }) => (
    <ArrowUpDown className={cn('ml-1 h-3 w-3 inline', sortField === field ? 'opacity-100' : 'opacity-40')} />
  )

  const rangeLabel = isSingleDay
    ? new Date(start).toLocaleDateString('ro-RO', { weekday: 'long', day: 'numeric', month: 'long' })
    : `${new Date(start).toLocaleDateString('ro-RO')} — ${new Date(end).toLocaleDateString('ro-RO')}`

  // Determine which col defs to show in the popover
  const isDaily = isSingleDay || is3Day
  const activeColDefs = isDaily ? DAILY_COL_DEFS : RANGE_COL_DEFS
  const visibleCols: Set<string> = isDaily ? effectiveDailyCols : visibleRangeCols

  return (
    <div className="space-y-4">
      {/* Connection warning */}
      {!connected && (
        <div className="flex items-center gap-2 rounded-md border border-orange-300 bg-orange-50 px-4 py-2 text-sm text-orange-800 dark:border-orange-700 dark:bg-orange-950/30 dark:text-orange-300">
          <Clock className="h-4 w-4 shrink-0" />
          <span>BioStar not connected — showing cached data. Configure connection in Settings &gt; Connectors.</span>
        </div>
      )}

      {/* Stats */}
      <div className={`grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6 ${showStats ? '' : 'hidden'}`}>
        <StatCard title={isSingleDay ? 'Present Today' : 'Employees'} value={totalPresent} icon={<UserCheck className="h-4 w-4" />} />
        <StatCard title="Total Hours" value={totalHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        <StatCard title={isSingleDay ? 'Avg Hours' : 'Avg Hours / Employee'} value={avgHours.toFixed(1)} icon={<Clock className="h-4 w-4" />} />
        {isSingleDay ? (
          <>
            <StatCard title="Early (<8:00)" value={earlyBirds} icon={<LogIn className="h-4 w-4" />} />
            <div
              className={cn('cursor-pointer rounded-lg transition-colors', statFilter === 'late' && 'ring-2 ring-orange-500')}
              onClick={() => setStatFilter(statFilter === 'late' ? 'all' : 'late')}
            >
              <StatCard title="Late (>15m)" value={lateArrivals} icon={<Clock className="h-4 w-4 text-orange-500" />} />
            </div>
            <StatCard title="Avg In / Out" value={`${avgCheckIn} / ${avgCheckOut}`} icon={<LogOut className="h-4 w-4" />} />
          </>
        ) : (
          <>
            <StatCard title="Avg Days Present" value={totalPresent > 0 ? (rangeSummary.reduce((a, e) => a + e.days_present, 0) / totalPresent).toFixed(1) : '0'} icon={<Calendar className="h-4 w-4" />} />
          </>
        )}
      </div>

      {/* Filters */}
      {showFilters && <div className="flex flex-wrap items-center gap-2">
        {/* Quick filter dropdown */}
        <Select value={quickFilter === 'custom' ? 'custom' : quickFilter} onValueChange={(v) => handleQuickFilter(v as QuickFilter)}>
          <SelectTrigger className="h-8 w-36 shrink-0 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {QUICK_FILTERS.map((f) => (
              <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
            ))}
            {quickFilter === 'custom' && <SelectItem value="custom">Custom</SelectItem>}
          </SelectContent>
        </Select>
        {/* Day navigation + Date pickers */}
        <Button variant="outline" size="icon" className="h-8 w-8 shrink-0" onClick={() => stepDay(-1)} title="Previous day">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Input
          type="date"
          className="h-8 w-32 text-xs shrink-0"
          value={quickFilter === 'custom' ? customStart : start}
          onChange={(e) => { setQuickFilter('custom'); setCustomStart(e.target.value); if (!customEnd || e.target.value > customEnd) setCustomEnd(e.target.value) }}
        />
        <span className="text-xs text-muted-foreground">—</span>
        <Input
          type="date"
          className="h-8 w-32 text-xs shrink-0"
          value={quickFilter === 'custom' ? customEnd : end}
          onChange={(e) => { setQuickFilter('custom'); setCustomEnd(e.target.value); if (!customStart || e.target.value < customStart) setCustomStart(e.target.value) }}
        />
        <Button variant="outline" size="icon" className="h-8 w-8 shrink-0" onClick={() => stepDay(1)} title="Next day">
          <ChevronRight className="h-4 w-4" />
        </Button>
        <span className="text-xs text-muted-foreground hidden md:inline">{rangeLabel}</span>
        <div className="h-5 w-px bg-border hidden md:block mx-1" />
        {showTeamToggle && (
          <div className="flex rounded-md border shrink-0">
            <button
              onClick={() => setTeamFilter('team')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
                teamFilter === 'team'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Users className="h-3.5 w-3.5" />
              My Team
            </button>
            <button
              onClick={() => setTeamFilter('all')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
                teamFilter === 'all'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              All
            </button>
          </div>
        )}
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

        {/* Quick column group toggles (daily view only) */}
        {!isMobile && isDaily && (showOriginal || showAdjusted) && (
          <div className="flex items-center gap-1">
            {showOriginal && (
              <Button
                variant="outline"
                size="sm"
                className={cn('h-9 text-xs px-2.5', (visibleDailyCols.has('check_in') || visibleDailyCols.has('check_out')) && 'border-primary text-primary')}
                onClick={toggleCheckInOut}
                title="Toggle Check In / Check Out columns"
              >
                Check In/Out
              </Button>
            )}
            {showAdjusted && (
              <Button
                variant="outline"
                size="sm"
                className={cn('h-9 text-xs px-2.5', (visibleDailyCols.has('adj_in') || visibleDailyCols.has('adj_out')) && 'border-primary text-primary')}
                onClick={toggleAdjInOut}
                title="Toggle In / Out (adjusted) columns"
              >
                In/Out
              </Button>
            )}
          </div>
        )}

        {/* Column toggle */}
        {!isMobile && (
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                className={cn('h-9 w-9 shrink-0', visibleCols.size < (isDaily ? DAILY_COL_DEFS.filter(c => showAdjusted || !['adj_in', 'adj_out'].includes(c.key)).length : RANGE_COL_DEFS.length) && 'text-primary border-primary')}
              >
                <Columns3 className="h-4 w-4" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-52 p-3">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Columns</span>
                <button
                  onClick={isDaily ? resetDailyCols : resetRangeCols}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  Reset
                </button>
              </div>
              <div className="space-y-0.5">
                {activeColDefs
                  .filter(c => !(['check_in', 'check_out'] as string[]).includes(c.key) || showOriginal)
                  .filter(c => !(['adj_in', 'adj_out'] as string[]).includes(c.key) || showAdjusted)
                  .map(c => {
                    const checked = isDaily
                      ? visibleDailyCols.has(c.key as DailyColKey)
                      : visibleRangeCols.has(c.key as RangeColKey)
                    return (
                      <label
                        key={c.key}
                        className="flex items-center gap-2.5 px-1 py-1.5 text-sm cursor-pointer hover:bg-accent rounded-md select-none"
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(v) => {
                            if (isDaily) toggleDailyCol(c.key as DailyColKey, !!v)
                            else toggleRangeCol(c.key as RangeColKey, !!v)
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
      </div>}

      {/* Last 3 Days: stacked per-day sections */}
      {is3Day && (
        <div className="space-y-6">
          {[0, 1, 2].map((offset) => (
            <DaySection
              key={offset}
              date={dateOffset(offset)}
              managerFilter={managerFilter}
              visibleCols={visibleDailyCols}
              connected={connected}
            />
          ))}
        </div>
      )}

      {/* Table / Card list — loading */}
      {!is3Day && isLoading && (
        isMobile
          ? <MobileCardList data={[]} fields={dailyMobileFields} getRowId={() => 0} isLoading />
          : <div className="space-y-2">{Array.from({ length: 10 }).map((_, i) => <div key={i} className="h-10 animate-pulse rounded bg-muted" />)}</div>
      )}

      {/* Single-day table */}
      {!is3Day && !isLoading && isSingleDay && (
        processedDaily.length === 0
          ? <EmptyState title="No attendance data" description={search ? 'Try a different search term.' : 'No punch logs found for this date.'} />
          : isMobile
            ? <MobileCardList data={processedDaily} fields={dailyMobileFields} getRowId={(e) => Number(e.biostar_user_id)} onRowClick={(e) => navigate(`/app/hr/pontaje/${e.biostar_user_id}`)} />
            : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8" />
                      <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                        Employee <SortIcon field="name" />
                      </TableHead>
                      {visibleDailyCols.has('group') && (
                        <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
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
                      {showAdjusted && visibleDailyCols.has('adj_in') && (
                        <TableHead className="text-center hidden lg:table-cell">In</TableHead>
                      )}
                      {showAdjusted && visibleDailyCols.has('adj_out') && (
                        <TableHead className="text-center hidden lg:table-cell">Out</TableHead>
                      )}
                      {visibleDailyCols.has('duration') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('duration')}>
                          Duration <SortIcon field="duration" />
                        </TableHead>
                      )}
                      {visibleDailyCols.has('punches') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('punches')}>
                          Punches <SortIcon field="punches" />
                        </TableHead>
                      )}
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
                        visibleCols={effectiveDailyCols}
                      />
                    ))}
                  </TableBody>
                </Table>
              </div>
            )
      )}

      {/* Range table */}
      {!is3Day && !isLoading && !isSingleDay && (
        processedRange.length === 0
          ? <EmptyState title="No attendance data" description={search ? 'Try a different search term.' : 'No punch logs found for this period.'} />
          : isMobile
            ? <MobileCardList data={processedRange} fields={rangeMobileFields} getRowId={(e) => Number(e.biostar_user_id)} onRowClick={(e) => navigate(`/app/hr/pontaje/${e.biostar_user_id}`)} />
            : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                        Employee <SortIcon field="name" />
                      </TableHead>
                      {visibleRangeCols.has('group') && (
                        <TableHead className="hidden md:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                          Group <SortIcon field="group" />
                        </TableHead>
                      )}
                      {visibleRangeCols.has('avg_check_in') && <TableHead className="text-center">Avg Check In</TableHead>}
                      {visibleRangeCols.has('avg_check_out') && <TableHead className="text-center">Avg Check Out</TableHead>}
                      {visibleRangeCols.has('days') && <TableHead className="text-center">Days</TableHead>}
                      {visibleRangeCols.has('total_hours') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('duration')}>
                          Total Hours <SortIcon field="duration" />
                        </TableHead>
                      )}
                      {visibleRangeCols.has('adj_hours') && <TableHead className="text-center">Adj. Hours</TableHead>}
                      {visibleRangeCols.has('avg_day') && <TableHead className="text-center">Avg/Day</TableHead>}
                      {visibleRangeCols.has('punches') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('punches')}>
                          Punches <SortIcon field="punches" />
                        </TableHead>
                      )}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {processedRange.map((emp) => (
                      <RangeEmployeeRow
                        key={emp.biostar_user_id}
                        employee={emp}
                        onProfile={() => navigate(`/app/hr/pontaje/${emp.biostar_user_id}`)}
                        visibleCols={visibleRangeCols}
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
  visibleCols,
}: {
  employee: BioStarRangeSummary
  onProfile: () => void
  visibleCols: Set<RangeColKey>
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
      {visibleCols.has('group') && (
        <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
          {employee.user_group_name || '-'}
        </TableCell>
      )}
      {visibleCols.has('avg_check_in') && (
        <TableCell className="text-center">
          <span className="inline-flex items-center gap-1 text-sm">
            <LogIn className="h-3 w-3 text-green-600" />
            {formatEpochTime(employee.avg_check_in_epoch)}
          </span>
        </TableCell>
      )}
      {visibleCols.has('avg_check_out') && (
        <TableCell className="text-center">
          <span className="inline-flex items-center gap-1 text-sm">
            <LogOut className="h-3 w-3 text-red-500" />
            {formatEpochTime(employee.avg_check_out_epoch)}
          </span>
        </TableCell>
      )}
      {visibleCols.has('days') && (
        <TableCell className="text-center">
          <Badge variant="secondary" className="text-xs">{employee.days_present}</Badge>
        </TableCell>
      )}
      {visibleCols.has('total_hours') && (
        <TableCell className="text-center">
          <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
            {formatDuration(totalNet)}
          </span>
        </TableCell>
      )}
      {visibleCols.has('adj_hours') && (
        <TableCell className="text-center">
          {employee.adjustment_count > 0 ? (
            <span className="text-sm font-medium text-green-600">
              {formatDuration(netSeconds(employee.adjusted_total_duration_seconds, lunch * employee.days_present))}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          )}
        </TableCell>
      )}
      {visibleCols.has('avg_day') && (
        <TableCell className="text-center">
          <span className="text-sm">{avgH.toFixed(1)}h</span>
        </TableCell>
      )}
      {visibleCols.has('punches') && (
        <TableCell className="text-center">
          <Badge variant="secondary" className="text-xs">{employee.total_punches}</Badge>
        </TableCell>
      )}
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
  visibleCols,
}: {
  employee: BioStarDailySummary
  date: string
  isExpanded: boolean
  onToggle: () => void
  onProfile: () => void
  visibleCols: Set<DailyColKey>
}) {
  const lunch = employee.lunch_break_minutes ?? 60
  const expectedH = employee.working_hours ?? 8
  const net = netSeconds(employee.duration_seconds, lunch)
  const netH = net / 3600
  const isShort = netH > 0 && netH < expectedH

  // colSpan = 2 (chevron + employee) + number of visible optional columns that actually render
  const colSpan = 2 + Array.from(visibleCols).length

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
        {visibleCols.has('group') && (
          <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
            {employee.user_group_name || '-'}
          </TableCell>
        )}
        {visibleCols.has('check_in') && (
          <TableCell className="text-center">
            <span className="inline-flex items-center gap-1 text-sm">
              <LogIn className="h-3 w-3 text-green-600" />
              {formatTime(employee.first_punch)}
            </span>
          </TableCell>
        )}
        {visibleCols.has('check_out') && (
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
            {employee.total_punches === 1 ? (
              <span className="text-sm text-muted-foreground">—</span>
            ) : (
              <span className={cn('text-sm font-medium', isShort ? 'text-orange-600' : 'text-foreground')}>
                {formatDuration(net)}
              </span>
            )}
            {net > 0 && lunch > 0 && (
              <span className="block text-[10px] text-muted-foreground">-{lunch}m lunch</span>
            )}
          </TableCell>
        )}
        {visibleCols.has('punches') && (
          <TableCell className="text-center">
            <Badge variant="secondary" className="text-xs">
              {employee.total_punches}
            </Badge>
          </TableCell>
        )}
      </TableRow>
      {isExpanded && (
        <TableRow>
          <TableCell colSpan={colSpan} className="bg-muted/30 p-0">
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

// ── Last 3 Days: per-day section ──

function DaySection({
  date,
  managerFilter,
  visibleCols,
  connected,
}: {
  date: string
  managerFilter: boolean
  visibleCols: Set<DailyColKey>
  connected: boolean
}) {
  const navigate = useNavigate()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const { data: summary = [], isLoading } = useQuery({
    queryKey: ['biostar', 'daily-summary', date, managerFilter],
    queryFn: () => biostarApi.getDailySummary(date, managerFilter),
    refetchInterval: connected ? 60_000 : false,
  })

  const label = new Date(`${date}T12:00:00`).toLocaleDateString('ro-RO', {
    weekday: 'long', day: 'numeric', month: 'long',
  })
  const presentCount = summary.length
  const earlyCount = summary.filter((e) => e.first_punch && new Date(e.first_punch).getHours() < 8).length

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 px-1">
        <h3 className="text-sm font-semibold capitalize">{label}</h3>
        <span className="text-xs text-muted-foreground">{presentCount} present</span>
        {earlyCount > 0 && (
          <span className="text-xs text-muted-foreground">{earlyCount} early</span>
        )}
      </div>
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : summary.length === 0 ? (
        <p className="text-sm text-muted-foreground px-1">No attendance data for this date.</p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Employee</TableHead>
                {visibleCols.has('group') && (
                  <TableHead className="hidden md:table-cell">Group</TableHead>
                )}
                {visibleCols.has('check_in') && (
                  <TableHead className="text-center">Check In</TableHead>
                )}
                {visibleCols.has('check_out') && (
                  <TableHead className="text-center">Check Out</TableHead>
                )}
                {visibleCols.has('adj_in') && (
                  <TableHead className="text-center hidden lg:table-cell">In</TableHead>
                )}
                {visibleCols.has('adj_out') && (
                  <TableHead className="text-center hidden lg:table-cell">Out</TableHead>
                )}
                {visibleCols.has('duration') && (
                  <TableHead className="text-center">Duration</TableHead>
                )}
                {visibleCols.has('punches') && (
                  <TableHead className="text-center">Punches</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.map((emp) => (
                <EmployeeRow
                  key={emp.biostar_user_id}
                  employee={emp}
                  date={date}
                  isExpanded={expandedId === emp.biostar_user_id}
                  onToggle={() => setExpandedId(expandedId === emp.biostar_user_id ? null : emp.biostar_user_id)}
                  onProfile={() => navigate(`/app/hr/pontaje/${emp.biostar_user_id}`)}
                  visibleCols={visibleCols}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
