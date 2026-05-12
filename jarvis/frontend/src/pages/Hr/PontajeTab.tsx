import { useState, useEffect, useMemo, useCallback } from 'react'
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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
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
import type { AttendanceRow, BioStarDayHistory, CompanyInterval } from '@/types/biostar'

type SortField = 'name' | 'company' | 'group' | 'check_in' | 'check_out' | 'duration' | 'punches'
type SortDir = 'asc' | 'desc'

type ColKey = 'group' | 'official_in' | 'official_out' | 'actual_in' | 'actual_out' | 'duration' | 'punches' | 'schedule' | 'company' | 'status'

const COL_DEFS: { key: ColKey; label: string }[] = [
  { key: 'status', label: 'Status' },
  { key: 'official_in', label: 'Checked In' },
  { key: 'official_out', label: 'Checked Out' },
  { key: 'actual_in', label: 'Actual In' },
  { key: 'actual_out', label: 'Actual Out' },
  { key: 'duration', label: 'Duration' },
  { key: 'punches', label: 'Punches' },
  { key: 'schedule', label: 'Schedule' },
  { key: 'company', label: 'Company' },
  { key: 'group', label: 'Group' },
]

const DEFAULT_COLS: ColKey[] = ['status', 'official_in', 'official_out', 'duration', 'punches', 'schedule']

const LEAVE_LABELS: Record<string, string> = {
  CO: 'Annual Leave', CM: 'Medical', CES: 'Unpaid', CIC: 'Child Care',
  CMS: 'Sick Family', DLG: 'Delegation', PERMIT: 'Leave Permit',
}

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
  // Extract HH:MM directly — timestamps are stored as Romania local time (naive, no tz offset),
  // so we avoid browser-timezone conversion which can add UTC+2/+3 offset.
  const m = dt.match(/[T ](\d{2}:\d{2})/)
  if (m) return m[1]
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
  const [statusFilter, setStatusFilter] = useState<string>('all')
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

  const [adjusting, setAdjusting] = useState(false)
  const [lastAdjustRange, setLastAdjustRange] = useState<{ start: string; end: string } | null>(null)
  const [undoing, setUndoing] = useState(false)

  const undoLastAdjust = useCallback(async () => {
    if (!lastAdjustRange) return
    setUndoing(true)
    const toastId = toast.loading('Undoing auto-adjust…')
    try {
      await biostarApi.revertAdjustmentsRange(lastAdjustRange.start, lastAdjustRange.end)
      toast.success('Auto-adjustments reverted', { id: toastId })
      setLastAdjustRange(null)
      queryClient.invalidateQueries({ queryKey: ['biostar'] })
    } catch {
      toast.error('Undo failed', { id: toastId })
    } finally {
      setUndoing(false)
    }
  }, [lastAdjustRange, queryClient])

  const autoAdjustRange = useCallback(async (mode: 'day' | 'week' | 'month' | 'quarter' | 'year') => {
    setAdjusting(true)
    const toastId = toast.loading(`Auto-adjusting ${mode}…`)
    try {
      const today = todayStr()
      const ref = new Date(`${date}T12:00:00`)
      let start: string
      let end: string

      if (mode === 'day') {
        start = date
        end = date
      } else if (mode === 'week') {
        const dow = ref.getDay() || 7 // Mon=1 … Sun=7
        const mon = new Date(ref)
        mon.setDate(ref.getDate() - dow + 1)
        start = mon.toISOString().slice(0, 10)
        const sun = new Date(mon)
        sun.setDate(mon.getDate() + 6)
        end = sun.toISOString().slice(0, 10)
      } else if (mode === 'month') {
        const y = ref.getFullYear(), m = ref.getMonth()
        start = `${y}-${String(m + 1).padStart(2, '0')}-01`
        const mld = new Date(y, m + 1, 0)
        end = `${mld.getFullYear()}-${String(mld.getMonth() + 1).padStart(2, '0')}-${String(mld.getDate()).padStart(2, '0')}`
      } else if (mode === 'quarter') {
        const y = ref.getFullYear(), q = Math.floor(ref.getMonth() / 3)
        start = `${y}-${String(q * 3 + 1).padStart(2, '0')}-01`
        const qld = new Date(y, q * 3 + 3, 0)
        end = `${qld.getFullYear()}-${String(qld.getMonth() + 1).padStart(2, '0')}-${String(qld.getDate()).padStart(2, '0')}`
      } else {
        start = `${ref.getFullYear()}-01-01`
        end = `${ref.getFullYear()}-12-31`
      }

      // Collect working days in range up to today
      const days: string[] = []
      for (let d = new Date(`${start}T12:00:00`); d.toISOString().slice(0, 10) <= end; d.setDate(d.getDate() + 1)) {
        const dow = d.getDay()
        if (dow === 0 || dow === 6) continue
        const ds = d.toISOString().slice(0, 10)
        if (ds > today) continue
        days.push(ds)
      }

      if (!days.length) {
        toast.error('No working days in range', { id: toastId })
        return
      }

      let totalAdj = 0, totalFlagged = 0
      for (const ds of days) {
        try {
          const res = await biostarApi.autoAdjustAll(ds)
          totalAdj += res.data.adjusted
          totalFlagged += res.data.total_flagged
        } catch { /* skip failed days */ }
      }

      toast.success(`Auto-adjusted ${totalAdj} of ${totalFlagged} across ${days.length} days`, { id: toastId })
      setLastAdjustRange({ start: days[0], end: days[days.length - 1] })
      queryClient.invalidateQueries({ queryKey: ['biostar'] })
    } catch {
      toast.error('Auto-adjust failed', { id: toastId })
    } finally {
      setAdjusting(false)
    }
  }, [date, queryClient])

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
    if (statusFilter !== 'all') list = list.filter((e) => e.attendance_status === statusFilter)
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
        case 'duration': {
          const aN = a.adjusted_first_punch && a.adjusted_last_punch ? netSec(timeDiffSec(a.adjusted_first_punch, a.adjusted_last_punch), a.lunch_break_minutes ?? 60) : netSec(a.duration_seconds, a.lunch_break_minutes ?? 60)
          const bN = b.adjusted_first_punch && b.adjusted_last_punch ? netSec(timeDiffSec(b.adjusted_first_punch, b.adjusted_last_punch), b.lunch_break_minutes ?? 60) : netSec(b.duration_seconds, b.lunch_break_minutes ?? 60)
          cmp = aN - bN; break
        }
        case 'punches': cmp = (a.total_punches ?? 0) - (b.total_punches ?? 0); break
        default: cmp = (a.name || '').localeCompare(b.name || '')
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return list
  }, [rows, groupFilter, statusFilter, search, sortField, sortDir])

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

  // ── CSV Download (monthly, all employees, official columns only) ──

  const [exporting, setExporting] = useState(false)

  const exportGroups = useMemo(() =>
    [...new Set(rows.map(r => r.user_group_name).filter((g): g is string => !!g && !g.toLowerCase().includes('plecati') && !g.toLowerCase().includes('contracte inchise')))].sort(),
    [rows],
  )

  const downloadXlsx = useCallback(async (mode: 'day' | 'month', raw = false, group?: string) => {
    setExporting(true)
    const isDay = mode === 'day'
    const toastId = toast.loading(isDay ? 'Exporting day pontaje…' : 'Exporting monthly pontaje…')
    try {
      const today = todayStr()
      const monthStr = date.slice(0, 7) // e.g. "2026-04"
      const [y, m] = monthStr.split('-').map(Number)
      const firstDay = `${monthStr}-01`
      const ld = new Date(y, m, 0)
      const lastDay = `${ld.getFullYear()}-${String(ld.getMonth() + 1).padStart(2, '0')}-${String(ld.getDate()).padStart(2, '0')}`

      // Build list of working days — skip future dates
      const workingDays: { date: string; dayLabel: string; weekNum: number }[] = []
      if (isDay) {
        const dd = new Date(`${date}T12:00:00`)
        const dow = dd.getDay()
        if (dow !== 0 && dow !== 6 && date <= today) {
          workingDays.push({
            date,
            dayLabel: dd.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric', month: 'short' }),
            weekNum: getISOWeek(dd),
          })
        }
      } else {
        for (let d = new Date(`${firstDay}T12:00:00`); d.toISOString().slice(0, 10) <= lastDay; d.setDate(d.getDate() + 1)) {
          const dow = d.getDay()
          if (dow === 0 || dow === 6) continue
          const ds = d.toISOString().slice(0, 10)
          if (ds > today) continue // skip future dates
          workingDays.push({
            date: ds,
            dayLabel: d.toLocaleDateString('ro-RO', { weekday: 'short', day: 'numeric', month: 'short' }),
            weekNum: getISOWeek(d),
          })
        }
      }

      if (!workingDays.length) {
        toast.error('No working days to export', { id: toastId })
        return
      }

      // Fetch daily summary for each working day (all employees, no manager filter)
      const dailyData = await Promise.all(
        workingDays.map(async (wd) => {
          const summaries = await biostarApi.getDailySummary(wd.date, false)
          return { ...wd, summaries }
        }),
      )

      // Collect unique employees keyed by (jarvis_user_id + group) to keep multi-company employees as separate rows
      const employeeMap = new Map<string, { name: string; company: string; group: string; schedule: string; jarvisUserId: number | null; biostarIds: Set<string> }>()
      for (const dd of dailyData) {
        for (const s of dd.summaries) {
          const key = s.mapped_jarvis_user_id ? `j${s.mapped_jarvis_user_id}_${s.user_group_name || ''}` : `b${s.biostar_user_id}`
          const existing = employeeMap.get(key)
          if (existing) {
            existing.biostarIds.add(s.biostar_user_id)
          } else {
            employeeMap.set(key, {
              name: s.mapped_jarvis_user_name || s.name,
              company: s.jarvis_company || '',
              group: s.user_group_name || '',
              schedule: formatSchedule(s.schedule_start, s.schedule_end),
              jarvisUserId: s.mapped_jarvis_user_id,
              biostarIds: new Set([s.biostar_user_id]),
            })
          }
        }
      }

      // Also add employees from current attendance rows that might have 0 punches
      for (const r of rows) {
        const key = r.jarvis_user_id ? `j${r.jarvis_user_id}_${r.user_group_name || ''}` : `b${r.biostar_user_id}`
        const existing = employeeMap.get(key)
        if (existing) {
          existing.biostarIds.add(r.biostar_user_id)
        } else {
          employeeMap.set(key, {
            name: r.name,
            company: r.company || '',
            group: r.user_group_name || '',
            schedule: formatSchedule(r.schedule_start, r.schedule_end),
            jarvisUserId: r.jarvis_user_id,
            biostarIds: new Set([r.biostar_user_id]),
          })
        }
      }

      // Fetch Sincron day-level codes for all mapped employees
      const sincronDayCodes = new Map<number, Map<string, string>>()
      const jarvisIds = [...new Set(
        Array.from(employeeMap.values()).map(e => e.jarvisUserId).filter((id): id is number => id != null),
      )]

      // Batch fetch Sincron timesheets (5 concurrent)
      const BATCH = 5
      for (let i = 0; i < jarvisIds.length; i += BATCH) {
        const batch = jarvisIds.slice(i, i + BATCH)
        const results = await Promise.allSettled(
          batch.map(uid => sincronApi.getEmployeeTimesheet(uid, y, m)),
        )
        for (let j = 0; j < batch.length; j++) {
          const r = results[j]
          if (r.status !== 'fulfilled' || !r.value?.data?.days) continue
          const dayMap = new Map<string, string>()
          for (const [dayKey, codes] of Object.entries(r.value.data.days)) {
            const leave = codes.find(c => ['CO', 'CM', 'CIC', 'CES', 'CMS', 'DLG', 'ZLS', 'CFP', 'CFS', 'INV', 'OZ', 'OS'].includes(c.short_code))
            if (leave) dayMap.set(dayKey, leave.short_code)
          }
          sincronDayCodes.set(batch[j], dayMap)
        }
      }

      // Batch-fetch per-company intervals for each working day (multi-contract employees)
      const allBiostarIds = [...new Set(Array.from(employeeMap.values()).flatMap(e => [...e.biostarIds]))]
      const intervalsByDay = new Map<string, Record<string, CompanyInterval[]>>()
      for (const dd of dailyData) {
        try {
          const data = await biostarApi.batchIntervals(dd.date, allBiostarIds)
          if (data && Object.keys(data).length > 0) intervalsByDay.set(dd.date, data)
        } catch { /* ignore — fall back to combined */ }
      }

      // Build CSV: Group before Name, with Company column
      const headers = ['Week', 'Date', 'Day', 'Group', 'Name', 'Company', 'Checked In', 'Checked Out', 'Duration (h)', 'Schedule', 'Sincron Status', 'Status']
      const csvRows: string[][] = [headers]

      const sortedEmployees = Array.from(employeeMap.entries())
        .filter(([, e]) => !group || e.group === group)
        .sort((a, b) =>
          (a[1].group || '').localeCompare(b[1].group || '') || (a[1].name || '').localeCompare(b[1].name || ''),
        )

      for (const dd of dailyData) {
        const dayIntervals = intervalsByDay.get(dd.date) ?? {}
        const multiOutputThisDay = new Set<number>() // dedup multi-contract employees across BioStar groups

        for (const [, emp] of sortedEmployees) {
          const sincronCode = emp.jarvisUserId
            ? (sincronDayCodes.get(emp.jarvisUserId)?.get(dd.date) ?? '')
            : ''

          // Check if multi-contract intervals exist for this employee (try all biostarIds)
          let intervals: CompanyInterval[] | undefined
          for (const bid of emp.biostarIds) {
            const ivs = dayIntervals[bid]
            if (ivs && ivs.length > 1) { intervals = ivs; break }
          }

          if (intervals && intervals.length > 1 && !group) {
            // Deduplicate: skip if this jarvisUserId was already output as multi-contract this day
            if (emp.jarvisUserId && multiOutputThisDay.has(emp.jarvisUserId)) continue
            if (emp.jarvisUserId) multiOutputThisDay.add(emp.jarvisUserId)

            // Multi-contract: output one row per company interval
            for (const iv of intervals) {
              const effectiveIn = raw ? iv.first_punch : (iv.adjusted_first_punch ?? iv.first_punch)
              const effectiveOut = raw ? iv.last_punch : (iv.adjusted_last_punch ?? iv.last_punch)
              const pIn = effectiveIn ?? null
              const pOut = effectiveOut && effectiveOut !== effectiveIn ? effectiveOut : null
              let duration = ''
              if (pIn && pOut) {
                const secs = timeDiffSec(pIn, pOut)
                if (secs > 0) duration = (secs / 3600).toFixed(2)
              }
              const companyShort = iv.group_name || iv.company.replace(/\s*S\.R\.L\.?\s*$/i, '').trim() || iv.company
              csvRows.push([
                `W${dd.weekNum}`,
                dd.date,
                dd.dayLabel,
                emp.group,
                emp.name,
                companyShort,
                pIn ? fmtTime(pIn) : '',
                pOut ? fmtTime(pOut) : '',
                duration,
                `${iv.start || ''}–${iv.end || ''}`,
                sincronCode,
                sincronCode && !['OZ', 'OS'].includes(sincronCode) ? (LEAVE_LABELS[sincronCode] ?? sincronCode) : pIn ? 'Present' : 'Absent',
              ])
            }
          } else if (group && intervals && intervals.length > 1) {
            // Group-filtered multi-contract: use the matching company's interval
            if (emp.jarvisUserId && multiOutputThisDay.has(emp.jarvisUserId)) continue
            const companyIv = intervals.find(iv =>
              iv.company.toLowerCase().trim() === emp.company.toLowerCase().trim(),
            )
            if (companyIv) {
              const effectiveIn = raw ? companyIv.first_punch : (companyIv.adjusted_first_punch ?? companyIv.first_punch)
              const effectiveOut = raw ? companyIv.last_punch : (companyIv.adjusted_last_punch ?? companyIv.last_punch)
              const pIn = effectiveIn ?? null
              const pOut = effectiveOut && effectiveOut !== effectiveIn ? effectiveOut : null
              let duration = ''
              if (pIn && pOut) {
                const secs = timeDiffSec(pIn, pOut)
                if (secs > 0) duration = (secs / 3600).toFixed(2)
              }
              csvRows.push([
                `W${dd.weekNum}`,
                dd.date,
                dd.dayLabel,
                emp.group,
                emp.name,
                emp.company,
                pIn ? fmtTime(pIn) : '',
                pOut ? fmtTime(pOut) : '',
                duration,
                `${companyIv.start || ''}–${companyIv.end || ''}`,
                sincronCode,
                sincronCode && !['OZ', 'OS'].includes(sincronCode) ? (LEAVE_LABELS[sincronCode] ?? sincronCode) : pIn ? 'Present' : 'Absent',
              ])
            } else {
              // No matching interval — fall through to combined data (always raw punches)
              const candidates = dd.summaries.filter(x => emp.biostarIds.has(x.biostar_user_id))
              const s = candidates.find(x => x.first_punch) ?? candidates[0] ?? null
              const punchIn = s?.first_punch ?? null
              const punchOut = s?.last_punch ?? null
              const officialIn = punchIn
              const officialOut = punchOut === punchIn ? null : punchOut
              const lunchMin = s?.lunch_break_minutes ?? 60
              let duration = ''
              if (officialIn && officialOut) {
                const secs = netSec(s?.duration_seconds ?? timeDiffSec(officialIn, officialOut), lunchMin)
                if (secs > 0) duration = (secs / 3600).toFixed(2)
              }
              csvRows.push([
                `W${dd.weekNum}`,
                dd.date,
                dd.dayLabel,
                emp.group,
                emp.name,
                emp.company,
                officialIn ? fmtTime(officialIn) : '',
                officialOut ? fmtTime(officialOut) : '',
                duration,
                emp.schedule,
                sincronCode,
                sincronCode && !['OZ', 'OS'].includes(sincronCode) ? (LEAVE_LABELS[sincronCode] ?? sincronCode) : officialIn ? 'Present' : 'Absent',
              ])
            }
          } else {
            // Single-contract: also skip if already output as multi-contract
            if (emp.jarvisUserId && multiOutputThisDay.has(emp.jarvisUserId)) continue
            const candidates = dd.summaries.filter(x => emp.biostarIds.has(x.biostar_user_id))
            const s = candidates.find(x => x.adjusted_first_punch || x.first_punch) ?? candidates[0] ?? null
            const punchIn = s ? (raw ? s.first_punch : (s.adjusted_first_punch ?? s.first_punch)) : null
            const punchOut = s ? (raw ? s.last_punch : (s.adjusted_last_punch ?? s.last_punch)) : null
            const officialIn = punchIn
            const officialOut = punchOut === punchIn ? null : punchOut
            const lunchMin = s?.lunch_break_minutes ?? 60
            let duration = ''
            if (officialIn && officialOut) {
              const secs = raw
                ? (s?.duration_seconds ?? timeDiffSec(officialIn, officialOut))
                : (s?.adjusted_first_punch && s?.adjusted_last_punch
                    ? netSec(timeDiffSec(s.adjusted_first_punch, s.adjusted_last_punch), lunchMin)
                    : netSec(s?.duration_seconds ?? null, lunchMin))
              if (secs > 0) duration = (secs / 3600).toFixed(2)
            }

            csvRows.push([
              `W${dd.weekNum}`,
              dd.date,
              dd.dayLabel,
              emp.group,
              emp.name,
              emp.company,
              officialIn ? fmtTime(officialIn) : '',
              officialOut ? fmtTime(officialOut) : '',
              duration,
              emp.schedule,
              sincronCode,
              sincronCode && !['OZ', 'OS'].includes(sincronCode) ? (LEAVE_LABELS[sincronCode] ?? sincronCode) : officialIn ? 'Present' : 'Absent',
            ])
          }
        }
      }

      const XLSX = await import('xlsx')
      const ws = XLSX.utils.aoa_to_sheet(csvRows)
      // Column widths
      ws['!cols'] = [
        { wch: 5 },  // Week
        { wch: 12 }, // Date
        { wch: 16 }, // Day
        { wch: 18 }, // Group
        { wch: 24 }, // Name
        { wch: 20 }, // Company
        { wch: 10 }, // Checked In
        { wch: 10 }, // Checked Out
        { wch: 12 }, // Duration
        { wch: 14 }, // Schedule
        { wch: 14 }, // Sincron Status
        { wch: 10 }, // Status
      ]
      const wb = XLSX.utils.book_new()
      XLSX.utils.book_append_sheet(wb, ws, 'Pontaje')
      const groupSuffix = group ? `_${group.replace(/\s+/g, '_')}` : ''
      const fileName = isDay ? `pontaje_${date}${groupSuffix}${raw ? '_raw' : ''}.xlsx` : `pontaje_${monthStr}${groupSuffix}${raw ? '_raw' : ''}.xlsx`
      XLSX.writeFile(wb, fileName)
      toast.success('Export complete', { id: toastId })
      // Refresh attendance data since auto-adjust may have changed it
      queryClient.invalidateQueries({ queryKey: ['biostar', 'attendance-today', date] })
    } catch (err) {
      console.error('[Export] failed:', err)
      toast.error('Export failed', { id: toastId })
    } finally {
      setExporting(false)
    }
  }, [date, rows])

  // ── Mobile fields ──

  const mobileFields: MobileCardField<AttendanceRow>[] = useMemo(() => [
    { key: 'name', label: 'Employee', isPrimary: true, render: (e) => <span className="font-medium">{e.name}</span> },
    {
      key: 'checkin', label: 'Checked In',
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
      key: 'checkout', label: 'Checked Out',
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
        const hasAdj = !!e.adjusted_first_punch
        const net = e.adjusted_first_punch && e.adjusted_last_punch
          ? netSec(timeDiffSec(e.adjusted_first_punch, e.adjusted_last_punch), e.lunch_break_minutes ?? 60)
          : netSec(e.duration_seconds, e.lunch_break_minutes ?? 60)
        return <span className="text-sm font-medium">{(e.total_punches ?? 0) === 1 && !hasAdj ? '—' : fmtDuration(net)}</span>
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

          {/* Status filter */}
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-32 shrink-0">
              <SelectValue placeholder="All Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="present">Present ({presentCount})</SelectItem>
              <SelectItem value="absent">Absent ({absentCount})</SelectItem>
            </SelectContent>
          </Select>

          <div className="flex items-center gap-1 ml-auto">
            {/* Adjustment buttons */}
            {canAdjust && (
              <>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="h-8 text-xs" disabled={adjusting}>
                      <Wand2 className="mr-1 h-3.5 w-3.5" />
                      Auto-adjust
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => autoAdjustRange('day')}>Current Day</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => autoAdjustRange('week')}>Current Week</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => autoAdjustRange('month')}>Current Month</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => autoAdjustRange('quarter')}>Current Quarter</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => autoAdjustRange('year')}>Current Year</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                {lastAdjustRange && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs text-orange-500 border-orange-500/40 hover:bg-orange-500/10"
                    onClick={undoLastAdjust}
                    disabled={undoing}
                    title={`Undo: ${lastAdjustRange.start} → ${lastAdjustRange.end}`}
                  >
                    <RotateCcw className="mr-1 h-3.5 w-3.5" />
                    Undo
                  </Button>
                )}
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

            {/* Export Excel dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8 shrink-0" disabled={exporting} title="Export Excel">
                  <Download className={cn('h-4 w-4', exporting && 'animate-pulse')} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => downloadXlsx('day')}>Export Day</DropdownMenuItem>
                <DropdownMenuItem onClick={() => downloadXlsx('month')}>Export Month</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => downloadXlsx('day', true)}>Export Day (raw)</DropdownMenuItem>
                <DropdownMenuItem onClick={() => downloadXlsx('month', true)}>Export Month (raw)</DropdownMenuItem>
                {exportGroups.length > 0 && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuLabel className="text-[10px] text-muted-foreground font-normal pb-0">By Group</DropdownMenuLabel>
                    {exportGroups.map(g => (
                      <DropdownMenuSub key={g}>
                        <DropdownMenuSubTrigger>{g}</DropdownMenuSubTrigger>
                        <DropdownMenuSubContent>
                          <DropdownMenuItem onClick={() => downloadXlsx('month', false, g)}>Month</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => downloadXlsx('day', false, g)}>Day</DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => downloadXlsx('month', true, g)}>Month (raw)</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => downloadXlsx('day', true, g)}>Day (raw)</DropdownMenuItem>
                        </DropdownMenuSubContent>
                      </DropdownMenuSub>
                    ))}
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>

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
                      {visibleCols.has('status') && (
                        <TableHead className="text-center">Status</TableHead>
                      )}
                      {visibleCols.has('group') && (
                        <TableHead className="hidden lg:table-cell cursor-pointer select-none" onClick={() => handleSort('group')}>
                          Group <SortIcon field="group" />
                        </TableHead>
                      )}
                      {visibleCols.has('official_in') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_in')}>
                          Checked In <SortIcon field="check_in" />
                        </TableHead>
                      )}
                      {visibleCols.has('official_out') && (
                        <TableHead className="cursor-pointer select-none text-center" onClick={() => handleSort('check_out')}>
                          Checked Out <SortIcon field="check_out" />
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
                          const { adjFirst, adjLast } = randomizeAdjustedTimes(
                            date, emp.schedule_start, emp.lunch_break_minutes ?? 60, emp.working_hours ?? 8,
                          )
                          biostarApi.adjustEmployee({
                            biostar_user_id: emp.biostar_user_id,
                            date,
                            adjusted_first_punch: adjFirst,
                            adjusted_last_punch: adjLast,
                            original_first_punch: emp.first_punch ?? undefined,
                            original_last_punch: emp.last_punch ?? emp.first_punch ?? undefined,
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
                          biostarApi.revertAdjustment(emp.biostar_user_id, date, true).then(() => {
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
  const hasLeave = !!employee.sincron_leave_code
  const lunch = employee.lunch_break_minutes ?? 60
  const net = employee.adjusted_first_punch && employee.adjusted_last_punch
    ? netSec(timeDiffSec(employee.adjusted_first_punch, employee.adjusted_last_punch), lunch)
    : netSec(employee.duration_seconds, lunch)
  const expectedH = employee.working_hours ?? 8
  const netH = net / 3600
  const isShort = netH > 0 && netH < expectedH
  const hasAdj = !!employee.adjustment_type

  const colSpan = 2 /* chevron + name */
    + (visibleCols.has('group') ? 1 : 0)
    + (visibleCols.has('status') ? 1 : 0)
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
      <TableRow className={cn('cursor-pointer hover:bg-muted/50', isAbsent && !hasAdj && 'opacity-60')} onClick={onToggle}>
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
        {visibleCols.has('status') && (
          <TableCell className="text-center">
            {employee.sincron_leave_code ? (
              <Badge variant="outline" className="text-[10px] border-orange-300 text-orange-600 bg-orange-50 dark:bg-orange-950/30">
                {LEAVE_LABELS[employee.sincron_leave_code] ?? employee.sincron_leave_code}
              </Badge>
            ) : employee.attendance_status === 'present' || hasAdj ? (
              <span className="inline-flex items-center gap-1 text-xs text-green-600">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                Present
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs text-red-600">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                Absent
              </span>
            )}
          </TableCell>
        )}
        {visibleCols.has('group') && (
          <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
            {employee.user_group_name || '—'}
          </TableCell>
        )}
        {visibleCols.has('official_in') && (
          <TableCell className="text-center">
            {isAbsent && !hasAdj ? (
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
            {isAbsent && !hasAdj ? (
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
            {(isAbsent && !hasAdj) || ((employee.total_punches ?? 0) === 1 && !hasAdj) ? (
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
            {employee.sincron_day_schedule?.length
              ? formatSchedule(
                  employee.sincron_day_schedule.reduce((e, s) => !e || s.start < e ? s.start : e, '' as string),
                  employee.sincron_day_schedule.reduce((l, s) => !l || s.end > l ? s.end : l, '' as string)
                )
              : formatSchedule(employee.schedule_start, employee.schedule_end)}
          </TableCell>
        )}
        {visibleCols.has('company') && (
          <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
            {employee.company || '—'}
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
            {!hasAdj && !hasLeave && (
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
              isAbsent && !hasAdj ? 'bg-red-400' : 'bg-green-500',
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
  const d = new Date(Date.UTC(y, m, 0))
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
  _scheduleStart: string | null,
  _lunchMin: number,
  _workingHours: number,
  leaveCodes?: Map<string, string>,
): Promise<number> {
  const today = todayStr()
  const eligible = days.filter(d =>
    !d.isWeekend && !d.isHoliday && !d.isOutsideMonth
    && d.date <= today
    && !leaveCodes?.has(d.date)
    && !(d.data?.adjusted_first_punch),
  )
  let count = 0
  for (const day of eligible) {
    try {
      await biostarApi.autoAdjustSingle(biostarUserId, day.date)
      count++
    } catch { /* skip — Sincron leave or no schedule */ }
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
      const count = await adjustDays(allDays, biostarUserId, scheduleStart, lunchMin, workingHours, leaveCodes)
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
              const count = await adjustDays(week.days, biostarUserId, scheduleStart, lunchMin, workingHours, leaveCodes)
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
                      scheduleEnd={_scheduleEnd}
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

function IntervalSubRow({
  iv, biostarUserId, date, canAdjust, adjusting, onInvalidate,
}: {
  iv: CompanyInterval; biostarUserId: string; date: string
  canAdjust: boolean; adjusting: boolean; onInvalidate: () => void
}) {
  const hasAdj = !!iv.adjusted_first_punch
  const effectiveIn = iv.adjusted_first_punch ?? iv.first_punch
  const effectiveOut = iv.adjusted_last_punch ?? iv.last_punch
  const dur = effectiveIn && effectiveOut && (iv.punch_count > 1 || hasAdj)
    ? timeDiffSec(effectiveIn, effectiveOut) : null
  const short = iv.group_name || iv.company.replace(/\s*S\.R\.L\.?\s*$/i, '').trim() || iv.company

  const handleAdjust = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      // Use the owning buid for this group's interval, fall back to parent buid
      const targetBuid = iv.biostar_user_id || biostarUserId
      await biostarApi.autoAdjustSingle(targetBuid, date, iv.group_name || undefined)
      toast.success(`Adjusted ${short}`)
      onInvalidate()
    } catch { toast.error('Adjust failed') }
  }

  const handleRevert = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      // Revert the owning buid's adjustment for this group
      const targetBuid = iv.biostar_user_id || biostarUserId
      await biostarApi.revertAdjustment(targetBuid, date)
      toast.success(`Reverted ${short}`)
      onInvalidate()
    } catch { toast.error('Revert failed') }
  }

  return (
    <div className="flex items-center gap-3 px-3 py-0.5 text-xs">
      <span className="w-2 shrink-0" />
      <span className="w-44 shrink-0 text-muted-foreground/70 truncate" title={iv.company}>
        {short}
      </span>
      <span className="w-14 shrink-0 text-center text-muted-foreground">{fmtScheduleTime(iv.start)}</span>
      <span className="w-14 shrink-0 text-center text-muted-foreground">{fmtScheduleTime(iv.end)}</span>
      <span className="w-14 shrink-0 text-center">
        {effectiveIn ? (
          <span className="inline-flex items-center gap-1">
            <LogIn className="h-2.5 w-2.5 text-green-600" />
            {fmtTime(effectiveIn)}
            {hasAdj && <span className="text-[9px] text-blue-500 font-medium">C</span>}
          </span>
        ) : <span className="text-red-400">—</span>}
      </span>
      <span className="w-14 shrink-0 text-center">
        {effectiveOut && (iv.punch_count > 1 || hasAdj) ? (
          <span className="inline-flex items-center gap-1">
            <LogOut className="h-2.5 w-2.5 text-red-500" />
            {fmtTime(effectiveOut)}
            {hasAdj && <span className="text-[9px] text-blue-500 font-medium">C</span>}
          </span>
        ) : <span className="text-orange-600">—</span>}
      </span>
      <span className="w-16 shrink-0 text-center font-medium">
        {dur != null ? fmtDuration(dur) : '—'}
      </span>
      {canAdjust && !hasAdj && (
        <Button variant="ghost" size="icon" className="h-4 w-4 ml-auto" onClick={handleAdjust} disabled={adjusting} title={`Adjust ${short}`}>
          <Wand2 className="h-2 w-2" />
        </Button>
      )}
      {canAdjust && hasAdj && (
        <Button variant="ghost" size="icon" className="h-4 w-4 ml-auto" onClick={handleRevert} disabled={adjusting} title={`Revert ${short}`}>
          <RotateCcw className="h-2 w-2" />
        </Button>
      )}
    </div>
  )
}

function DayRow({
  day, leaveCode, lunchMin, workingHours, biostarUserId, scheduleStart, scheduleEnd, canAdjust, adjusting, onInvalidate,
}: {
  day: DayEntry; leaveCode?: string; lunchMin: number; workingHours: number; biostarUserId: string
  scheduleStart: string | null; scheduleEnd: string | null; canAdjust: boolean; adjusting: boolean; onInvalidate: () => void
}) {
  const d = day.data
  const isToday = day.date === todayStr()
  const isFuture = day.date > todayStr()
  const isOut = day.isOutsideMonth
  const net = d ? effectiveSec(d, d.lunch_break_minutes ?? lunchMin) : 0
  const netH = net / 3600
  const isShort = netH > 0 && netH < workingHours
  const hasAdj = !!d?.adjusted_first_punch
  const isMultiContract = (d?.sincron_day_schedule?.length ?? 0) > 1

  // Per-company interval data (lazy-loaded for multi-contract days)
  const [intervals, setIntervals] = useState<CompanyInterval[] | null>(null)
  const [loadingIntervals, setLoadingIntervals] = useState(false)

  const loadIntervals = useCallback(async () => {
    if (intervals || loadingIntervals || !isMultiContract) return
    setLoadingIntervals(true)
    try {
      const data = await biostarApi.getPunchesByInterval(biostarUserId, day.date)
      setIntervals(data)
    } catch { /* silently fall back to combined view */ }
    setLoadingIntervals(false)
  }, [intervals, loadingIntervals, isMultiContract, biostarUserId, day.date])

  // Auto-load intervals for multi-contract present/absent days (re-fires after invalidation sets intervals=null)
  useEffect(() => {
    if (isMultiContract && !day.isWeekend && !day.isHoliday && !isFuture && !leaveCode) {
      loadIntervals()
    }
  }, [loadIntervals, isMultiContract, day.isWeekend, day.isHoliday, isFuture, leaveCode])

  const handleAdjustDay = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await biostarApi.autoAdjustSingle(biostarUserId, day.date)
      toast.success('Adjusted')
      setIntervals(null) // reset so it reloads
      onInvalidate()
    } catch { toast.error('Adjust failed') }
  }

  const handleRevertDay = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await biostarApi.revertAdjustment(biostarUserId, day.date, true)
      toast.success('Reverted')
      setIntervals(null)
      onInvalidate()
    } catch { toast.error('Revert failed') }
  }

  const handleIntervalInvalidate = useCallback(() => {
    setIntervals(null)
    onInvalidate()
  }, [onInvalidate])

  // Check if any per-company adjustment exists
  const hasCompanyAdj = !!(d?.company_adjustments?.length)
  const anyAdj = hasAdj || hasCompanyAdj

  return (
    <div className={cn(
      isToday && 'bg-primary/5 font-medium',
      isOut && 'opacity-40',
      !isOut && !d && !day.isWeekend && !day.isHoliday && !isFuture && 'opacity-50',
    )}>
      {/* Main summary row */}
      <div className="flex items-center gap-3 px-3 py-1.5 rounded-md text-sm">
        <span className={cn(
          'inline-block h-2 w-2 rounded-full shrink-0',
          d ? 'bg-green-500' : day.isWeekend || day.isHoliday ? 'bg-blue-400' : leaveCode ? 'bg-yellow-500' : isFuture ? 'bg-muted-foreground/30' : (anyAdj ? 'bg-green-500' : 'bg-red-400'),
        )} />
        <span className="w-44 shrink-0 capitalize text-muted-foreground">
          {day.dayLabel}
          {d?.sincron_day_schedule && d.sincron_day_schedule.length > 0 && !intervals ? (
            <span className="block text-[10px] text-muted-foreground/60 normal-case leading-tight">
              {d.sincron_day_schedule.map((s, i) => {
                const label = s.group_name || s.company.replace(/\s*S\.R\.L\.?\s*$/i, '').trim() || s.company;
                return (
                  <span key={i} className="block whitespace-nowrap" title={`${s.group_name ? s.group_name + ' — ' : ''}${s.company} ${s.start}–${s.end}`}>
                    {label} {s.start}–{s.end}
                  </span>
                );
              })}
            </span>
          ) : !intervals && d?.sincron_company ? (
            <span className="block text-[10px] text-muted-foreground/60 normal-case" title={d.sincron_company}>
              {d.sincron_company.replace(/\s*S\.R\.L\.?\s*$/i, '').trim()}
            </span>
          ) : null}
        </span>

        {day.isWeekend || day.isHoliday || isFuture || leaveCode ? (
          <>
            <span className="w-14 shrink-0" />
            <span className="w-14 shrink-0" />
            <span className={cn('text-xs', leaveCode ? 'text-yellow-600' : 'text-muted-foreground')}>
              {day.isWeekend ? 'Weekend' : day.isHoliday ? 'Holiday' : leaveCode ?? '—'}
            </span>
          </>
        ) : d ? (
          <>
            {/* Schedule In/Out — full span across all companies */}
            <span className="w-14 shrink-0 text-center text-xs text-muted-foreground">
              {fmtScheduleTime(d.sincron_day_schedule?.length ? d.sincron_day_schedule.reduce((earliest, s) => !earliest || s.start < earliest ? s.start : earliest, '' as string) : d.schedule_start ?? scheduleStart)}
            </span>
            <span className="w-14 shrink-0 text-center text-xs text-muted-foreground">
              {fmtScheduleTime(d.sincron_day_schedule?.length ? d.sincron_day_schedule.reduce((latest, s) => !latest || s.end > latest ? s.end : latest, '' as string) : d.schedule_end ?? scheduleEnd)}
            </span>
            {/* Actual In/Out — combined view (first/last of entire day) */}
            <span className="w-14 shrink-0 text-center">
              {(d.adjusted_first_punch || d.first_punch) ? (
                <span className="inline-flex items-center gap-1">
                  <LogIn className="h-3 w-3 text-green-600" />
                  {fmtTime(d.adjusted_first_punch ?? d.first_punch)}
                </span>
              ) : (
                <span className="text-xs text-red-400">—</span>
              )}
            </span>
            <span className="w-14 shrink-0 text-center">
              {d.total_punches === 1 && !anyAdj ? (
                <span className="text-xs text-orange-600">—</span>
              ) : (d.adjusted_last_punch || d.last_punch) ? (
                <span className="inline-flex items-center gap-1">
                  <LogOut className="h-3 w-3 text-red-500" />
                  {fmtTime(d.adjusted_last_punch ?? d.last_punch)}
                </span>
              ) : (
                <span className="text-xs text-red-400">—</span>
              )}
            </span>
            <span className={cn('w-16 shrink-0 text-center font-medium', isShort ? 'text-orange-600' : '')}>
              {d.total_punches === 1 && !anyAdj && !d.adjusted_first_punch ? '—' : fmtDuration(net)}
            </span>
            {canAdjust && !anyAdj && (d.first_punch || !d.total_punches) && (
              <Button variant="ghost" size="icon" className="h-5 w-5 ml-auto" onClick={handleAdjustDay} disabled={adjusting} title="Adjust day">
                <Wand2 className="h-2.5 w-2.5" />
              </Button>
            )}
            {canAdjust && anyAdj && !isMultiContract && (
              <Button variant="ghost" size="icon" className="h-5 w-5 ml-auto" onClick={handleRevertDay} disabled={adjusting} title="Revert">
                <RotateCcw className="h-2.5 w-2.5" />
              </Button>
            )}
          </>
        ) : (
          <>
            <span className="w-14 shrink-0 text-center text-xs text-muted-foreground">
              {fmtScheduleTime(scheduleStart)}
            </span>
            <span className="w-14 shrink-0 text-center text-xs text-muted-foreground">
              {fmtScheduleTime(scheduleEnd)}
            </span>
            <span className="text-xs text-red-400">{anyAdj ? '' : 'Absent'}</span>
            {canAdjust && !anyAdj && (
              <Button variant="ghost" size="icon" className="h-5 w-5 ml-auto" onClick={handleAdjustDay} disabled={adjusting} title="Adjust absent day">
                <Wand2 className="h-2.5 w-2.5" />
              </Button>
            )}
          </>
        )}
      </div>

      {/* Per-company sub-rows for multi-contract employees */}
      {intervals && intervals.length > 1 && (
        <div className="border-l-2 border-muted ml-5 mb-1">
          {intervals.map((iv, i) => (
            <IntervalSubRow
              key={i}
              iv={iv}
              biostarUserId={biostarUserId}
              date={day.date}
              canAdjust={canAdjust}
              adjusting={adjusting}
              onInvalidate={handleIntervalInvalidate}
            />
          ))}
        </div>
      )}
    </div>
  )
}
