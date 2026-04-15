import { useState, useMemo, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { hrApi } from '@/api/hr'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { ColumnToggle, useColumnState, type ColumnDef } from '@/components/shared/ColumnToggle'
import { FilterBar, type FilterField } from '@/components/shared/FilterBar'
import { DateField } from '@/components/ui/date-field'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import {
  Users, ArrowUpDown, ChevronDown, ChevronRight,
  Mail, Phone, Fingerprint, FileSpreadsheet, ExternalLink,
  UserCheck, UserMinus, Archive, Bell, BellOff, UserX, Clock, TrendingUp,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { HrEmployee, ContractStatus, StructureCompany, EmployeeWorkStats } from '@/types/hr'

/** Default date range: 1st of current month → today */
function defaultDateRange(): { start: string; end: string } {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return { start: `${y}-${m}-01`, end: `${y}-${m}-${d}` }
}

const LEAVE_LABELS: Record<string, string> = {
  CO: 'Annual Leave', CM: 'Medical', CES: 'Unpaid', CIC: 'Child Care',
  CMS: 'Sick Family', DLG: 'Delegation', PERMIT: 'Leave Permit',
}

interface Props {
  search: string
}

type SortField = 'name' | 'company' | 'department'
type SortDir = 'asc' | 'desc'

const SORTABLE_FIELDS = new Set<string>(['name', 'company', 'department'])

export default function EmployeesTab({ search }: Props) {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const isMobile = useIsMobile()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canEditEmployee = user?.permissions?.['hr.employees.edit'] ?? false
  const [statusTab, setStatusTab] = useState<ContractStatus>('active')
  const [filterValues, setFilterValues] = useState<Record<string, string>>({
    company: '', department: '', brand: '',
  })
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  // Date range — persisted in URL search params so it survives back navigation
  const defaults = useMemo(() => defaultDateRange(), [])
  const dateFrom = searchParams.get('from') || defaults.start
  const dateTo = searchParams.get('to') || defaults.end

  const handleDateChange = (start: string, end: string) => {
    const next = new URLSearchParams(searchParams)
    if (start) next.set('from', start); else next.delete('from')
    if (end) next.set('to', end); else next.delete('to')
    setSearchParams(next, { replace: true })
  }

  // Fetch all employees (not just active) to populate all tabs
  const { data: employeesData, isLoading: loadingEmployees } = useQuery({
    queryKey: ['hr', 'employees', 'all-statuses'],
    queryFn: () => hrApi.getEmployees(false),
  })

  const { data: companiesData } = useQuery({
    queryKey: ['hr', 'companies-full'],
    queryFn: () => hrApi.getCompaniesFull(),
  })

  const { data: absentData } = useQuery({
    queryKey: ['hr', 'employees', 'absent-today'],
    queryFn: () => hrApi.getAbsentToday(),
    refetchInterval: 5 * 60 * 1000,
  })

  const { data: workStats } = useQuery({
    queryKey: ['hr', 'employees', 'work-stats', dateFrom, dateTo],
    queryFn: () => hrApi.getEmployeeWorkStats(dateFrom, dateTo),
    staleTime: 5 * 60 * 1000,
    enabled: !!dateFrom && !!dateTo,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ employeeId, enabled }: { employeeId: number; enabled: boolean }) =>
      hrApi.updateEmployee(employeeId, { notify_missing_punch: enabled } as Partial<HrEmployee>),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hr', 'employees'] }),
    onError: () => toast.error('Failed to toggle notification'),
  })

  const bulkToggleMutation = useMutation({
    mutationFn: ({ userIds, enabled }: { userIds?: number[]; enabled: boolean }) =>
      hrApi.bulkToggleMissingPunch(userIds, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hr', 'employees'] })
      toast.success('Missing punch notifications updated')
    },
    onError: () => toast.error('Failed to update notifications'),
  })

  const allEmployees: HrEmployee[] = employeesData ?? []
  const companies: StructureCompany[] = companiesData ?? []

  // Split by contract_status
  const statusCounts = useMemo(() => ({
    active: allEmployees.filter((e) => e.contract_status === 'active').length,
    suspended: allEmployees.filter((e) => e.contract_status === 'suspended').length,
    closed: allEmployees.filter((e) => e.contract_status === 'closed').length,
  }), [allEmployees])

  // Employees for current tab
  const employees = useMemo(
    () => allEmployees.filter((e) => e.contract_status === statusTab),
    [allEmployees, statusTab],
  )

  // FilterBar field definitions
  const filterFields: FilterField[] = useMemo(() => [
    {
      key: 'company', label: 'Company', type: 'select' as const,
      options: companies.map(c => ({ value: c.company, label: c.company })),
    },
    {
      key: 'department', label: 'Department', type: 'select' as const,
      options: [...new Set(allEmployees.map(e => e.departments).filter(Boolean))].sort()
        .map(d => ({ value: d!, label: d! })),
    },
    {
      key: 'brand', label: 'Brand', type: 'select' as const,
      options: [...new Set(allEmployees.map(e => e.brand).filter(Boolean))].sort()
        .map(b => ({ value: b!, label: b! })),
    },
  ], [companies, allEmployees])

  // Filter + search + sort
  const filtered = useMemo(() => {
    let rows = employees
    if (filterValues.company) rows = rows.filter((e) => e.company === filterValues.company)
    if (filterValues.department) rows = rows.filter((e) => e.departments === filterValues.department)
    if (filterValues.brand) rows = rows.filter((e) => e.brand === filterValues.brand)
    if (search) {
      const q = search.toLowerCase()
      rows = rows.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          (e.email ?? '').toLowerCase().includes(q) ||
          (e.departments ?? '').toLowerCase().includes(q) ||
          (e.company ?? '').toLowerCase().includes(q),
      )
    }
    rows = [...rows].sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1
      if (sortField === 'name') return a.name.localeCompare(b.name) * dir
      if (sortField === 'company') return (a.company ?? '').localeCompare(b.company ?? '') * dir
      return (a.departments ?? '').localeCompare(b.departments ?? '') * dir
    })
    return rows
  }, [employees, filterValues, search, sortField, sortDir])

  // Stats
  const stats = useMemo(() => {
    const byCompany = new Map<string, number>()
    employees.forEach((e) => {
      const c = e.company || 'Unknown'
      byCompany.set(c, (byCompany.get(c) ?? 0) + 1)
    })
    // Aggregate work stats for visible employees
    // Gross = all employees with stats; Net = only employees who actually worked (days_present > 0)
    const ws = workStats ?? {} as Record<number, EmployeeWorkStats>
    let totalHours = 0, totalExpected = 0, empWithStats = 0
    let netExpected = 0, netEmpCount = 0, netScoreSum = 0, netScoreCount = 0
    let grossScoreSum = 0, grossScoreCount = 0
    let varianceSum = 0, varianceCount = 0
    filtered.forEach((e) => {
      const s = ws[e.id]
      if (!s) return
      totalHours += s.total_hours
      totalExpected += s.expected_hours
      empWithStats++
      grossScoreSum += s.productivity_score; grossScoreCount++
      if (s.days_present >= 2) { varianceSum += s.variance_minutes; varianceCount++ }
      // Net: only employees who actually punched in
      if (s.days_present > 0) {
        netExpected += s.expected_hours
        netEmpCount++
        netScoreSum += s.productivity_score; netScoreCount++
      }
    })
    // Gross averages (includes 0-hour absent employees)
    const grossAvgScore = grossScoreCount > 0 ? Math.round(grossScoreSum / grossScoreCount) : 0
    const grossAvgProductivity = totalExpected > 0 ? Math.min(Math.round(totalHours / totalExpected * 100), 100) : 0
    const grossAvgHoursPerMan = empWithStats > 0 ? Math.round(totalHours / empWithStats * 10) / 10 : 0
    // Net averages (only employees who actually worked)
    const netAvgScore = netScoreCount > 0 ? Math.round(netScoreSum / netScoreCount) : 0
    const netAvgProductivity = netExpected > 0 ? Math.min(Math.round(totalHours / netExpected * 100), 100) : 0
    const netAvgHoursPerMan = netEmpCount > 0 ? Math.round(totalHours / netEmpCount * 10) / 10 : 0
    const avgVariance = varianceCount > 0 ? Math.round(varianceSum / varianceCount) : 0
    return {
      total: employees.length,
      companies: byCompany.size,
      filtered: filtered.length,
      totalHours: Math.round(totalHours),
      netAvgScore, grossAvgScore,
      netAvgProductivity, grossAvgProductivity,
      netAvgHoursPerMan, grossAvgHoursPerMan,
      avgVariance,
    }
  }, [employees, filtered, workStats])

  // Absence stats (for active tab)
  const absenceCounts = useMemo(() => {
    if (!absentData) return { absent: 0, onLeave: 0, present: 0 }
    let absent = 0, onLeave = 0, present = 0
    for (const v of Object.values(absentData)) {
      if (v.status === 'absent') absent++
      else if (v.status === 'on_leave') onLeave++
      else if (v.status === 'present') present++
    }
    return { absent, onLeave, present }
  }, [absentData])

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  // Column definitions — all possible columns for the table
  const columnDefs: ColumnDef<HrEmployee>[] = useMemo(() => {
    const ws = workStats ?? ({} as Record<number, EmployeeWorkStats>)
    const cols: ColumnDef<HrEmployee>[] = [
      { key: 'name', label: 'Name', render: (e) => <span className="font-medium">{e.name}</span> },
      { key: 'company', label: 'Company', className: 'text-xs text-muted-foreground', render: (e) => <>{e.company ?? '-'}</> },
      { key: 'department', label: 'Department', className: 'text-xs', render: (e) => <>{e.departments ?? '-'}</> },
      { key: 'brand', label: 'Brand', className: 'text-xs text-muted-foreground', render: (e) => <>{e.brand ?? '-'}</> },
      {
        key: 'status', label: 'Status', className: 'text-center', render: (e) => (
          <Badge
            variant={e.contract_status === 'active' ? 'default' : e.contract_status === 'suspended' ? 'outline' : 'secondary'}
            className={cn('text-xs', e.contract_status === 'suspended' && 'border-amber-500 text-amber-600')}
          >
            {e.contract_status === 'active' ? 'Active' : e.contract_status === 'suspended' ? 'Suspended' : 'Closed'}
          </Badge>
        ),
      },
      {
        key: 'norm', label: 'Norm', className: 'text-center text-xs tabular-nums',
        render: (e) => {
          const s = ws[e.id]
          if (!s) return <span className="text-muted-foreground">—</span>
          return <>{s.hours_per_day}h/day</>
        },
      },
      {
        key: 'lunch', label: 'Lunch', className: 'text-center text-xs tabular-nums',
        render: (e) => {
          const s = ws[e.id]
          if (!s) return <span className="text-muted-foreground">—</span>
          return <>{s.lunch_break_minutes}min</>
        },
      },
      {
        key: 'schedule', label: 'Schedule', className: 'text-center text-xs tabular-nums',
        render: (e) => {
          const s = ws[e.id]
          if (!s || !s.schedule_start) return <span className="text-muted-foreground">—</span>
          return <>{s.schedule_start}–{s.schedule_end}</>
        },
      },
      {
        key: 'presence', label: 'Presence', className: 'text-center text-xs tabular-nums',
        render: (e) => {
          const s = ws[e.id]
          if (!s) return <span className="text-muted-foreground">—</span>
          return <>{s.days_present}/{s.working_days}</>
        },
      },
      {
        key: 'total_hours', label: 'Worked Hours', className: 'text-right text-xs tabular-nums',
        render: (e) => {
          const s = ws[e.id]
          return s ? <>{s.total_hours}h</> : <span className="text-muted-foreground">—</span>
        },
      },
      {
        key: 'avg_daily', label: 'Avg/Day', className: 'text-right text-xs tabular-nums',
        render: (e) => {
          const s = ws[e.id]
          return s && s.avg_daily_hours > 0 ? <>{s.avg_daily_hours}h</> : <span className="text-muted-foreground">—</span>
        },
      },
      {
        key: 'variance', label: 'Variance', className: 'text-center text-xs',
        render: (e) => {
          const s = ws[e.id]
          if (!s || s.days_present === 0) return <span className="text-muted-foreground">—</span>
          const v = s.variance_minutes
          // Bar width: clamp 0-60min range to 0-100%
          const barPct = Math.min(v / 60 * 100, 100)
          const barColor = v <= 10
            ? 'bg-green-500 dark:bg-green-400'
            : v <= 25
              ? 'bg-yellow-500 dark:bg-yellow-400'
              : 'bg-red-500 dark:bg-red-400'
          const trackColor = v <= 10
            ? 'bg-green-100 dark:bg-green-950/40'
            : v <= 25
              ? 'bg-yellow-100 dark:bg-yellow-950/40'
              : 'bg-red-100 dark:bg-red-950/40'
          const textColor = v <= 10
            ? 'text-green-600 dark:text-green-400'
            : v <= 25
              ? 'text-yellow-600 dark:text-yellow-400'
              : 'text-red-600 dark:text-red-400'
          return (
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1.5 cursor-help min-w-[80px]">
                    <div className={cn('h-1.5 rounded-full flex-1', trackColor)}>
                      <div className={cn('h-full rounded-full transition-all', barColor)} style={{ width: `${barPct}%` }} />
                    </div>
                    <span className={cn('tabular-nums text-[10px] w-[38px] text-right shrink-0', textColor)}>{`\u00B1${v}min`}</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-[220px] text-xs">
                  <p className="font-semibold mb-0.5">Schedule Variance</p>
                  <p className="text-muted-foreground">Average deviation from usual check-in/out times. Lower = more consistent schedule.</p>
                  <p className="mt-1">{v <= 10 ? 'Very consistent' : v <= 25 ? 'Moderate variation' : 'High variation'}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )
        },
      },
      {
        key: 'productivity_pct', label: 'Productivity', className: 'text-center text-xs',
        render: (e) => {
          const s = ws[e.id]
          if (!s || s.expected_hours === 0) return <span className="text-muted-foreground">—</span>
          const pct = Math.min(Math.round(s.total_hours / s.expected_hours * 100), 100)
          const color = pct >= 90
            ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-950/40 dark:text-green-400'
            : pct >= 70
              ? 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400'
              : 'bg-red-100 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-400'
          return <Badge variant="outline" className={cn('text-[10px] tabular-nums', color)}>{pct}%</Badge>
        },
      },
      {
        key: 'today', label: 'Today', className: 'text-center',
        render: (e) => <AbsenceBadge status={absentData?.[e.id]} />,
      },
      {
        key: 'productivity', label: 'Efficiency', className: 'text-center',
        render: (e) => {
          const s = ws[e.id]
          if (!s) return <span className="text-muted-foreground">—</span>
          const score = s.productivity_score
          const color = score >= 80
            ? 'bg-green-100 text-green-700 border-green-200 dark:bg-green-950/40 dark:text-green-400'
            : score >= 60
              ? 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-950/40 dark:text-yellow-400'
              : 'bg-red-100 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-400'
          const util = s.expected_hours > 0 ? Math.min(s.total_hours / s.expected_hours * 100, 100) : 0
          const attend = s.effective_days > 0 ? Math.min(s.days_present / s.effective_days * 100, 100) : 0
          const punct = Math.max(0, 100 - s.variance_minutes * 1.5)
          return (
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant="outline" className={cn('text-[10px] tabular-nums cursor-help', color)}>{score}%</Badge>
                </TooltipTrigger>
                <TooltipContent side="left" avoidCollisions className="max-w-[320px] text-xs leading-snug">
                  <p className="font-semibold mb-1">Efficiency: {score}%</p>
                  {(s.leave_days > 0 || s.permit_count > 0) && (
                    <p className="mb-1 text-blue-500 dark:text-blue-400">
                      {s.leave_days > 0 && <>{s.leave_days}d leave ({s.leave_types})</>}
                      {s.leave_days > 0 && s.permit_count > 0 && ' + '}
                      {s.permit_count > 0 && <>{s.permit_count} permits ({s.permit_hours}h)</>}
                      {' '}<span className="text-muted-foreground">= {s.effective_days} effective days</span>
                    </p>
                  )}
                  <div className="space-y-0.5">
                    <p>Utilization 50%: <span className="font-medium">{util.toFixed(0)}%</span> <span className="text-muted-foreground">({s.total_hours}h / {s.expected_hours}h) = {(util * 0.5).toFixed(1)}pts</span></p>
                    <p>Attendance 30%: <span className="font-medium">{attend.toFixed(0)}%</span> <span className="text-muted-foreground">({s.days_present}d / {s.effective_days}d) = {(attend * 0.3).toFixed(1)}pts</span></p>
                    <p>Punctuality 20%: <span className="font-medium">{punct.toFixed(0)}%</span> <span className="text-muted-foreground">({`\u00B1${s.variance_minutes}min`}) = {(punct * 0.2).toFixed(1)}pts</span></p>
                  </div>
                  <hr className="my-1 border-border/50" />
                  <p className="text-muted-foreground">{(util * 0.5).toFixed(1)} + {(attend * 0.3).toFixed(1)} + {(punct * 0.2).toFixed(1)} = <span className="font-semibold text-foreground">{score}</span></p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )
        },
      },
    ]
    if (canEditEmployee) {
      cols.push({
        key: 'punch_alert', label: 'Punch Alert', className: 'text-center w-20',
        render: (e) => (
          <Switch
            checked={e.notify_missing_punch ?? true}
            disabled={toggleMutation.isPending}
            aria-label={`Toggle missing punch alert for ${e.name}`}
            onCheckedChange={(checked) => toggleMutation.mutate({ employeeId: e.id, enabled: checked })}
            onClick={(ev) => ev.stopPropagation()}
            className="scale-75"
          />
        ),
      })
    }
    return cols
  }, [workStats, absentData, canEditEmployee, toggleMutation])

  // Column visibility
  const defaultVisible = useMemo(
    () => ['name', 'company', 'department', 'status', 'norm', 'lunch', 'schedule', 'presence', 'total_hours', 'avg_daily', 'productivity', 'variance', 'productivity_pct', 'today', ...(canEditEmployee ? ['punch_alert'] : [])],
    [canEditEmployee],
  )
  const lockedColumns = useMemo(() => new Set(['name']), [])

  const { visibleColumns, setVisibleColumns, defaultColumns } = useColumnState(
    'hr-employees-columns',
    defaultVisible,
    columnDefs.map((c) => c.key),
    'hr_employees',
  )

  // Filter out conditional columns (today only on active tab)
  const activeVisibleColumns = useMemo(() => {
    let cols = visibleColumns
    if (statusTab !== 'active') cols = cols.filter((k) => k !== 'today')
    return cols
  }, [visibleColumns, statusTab])

  const mobileFields: MobileCardField<HrEmployee>[] = useMemo(
    () => {
      const ws = workStats ?? ({} as Record<number, EmployeeWorkStats>)
      return [
        { key: 'name', label: 'Name', render: (r) => <span className="font-medium">{r.name}</span>, isPrimary: true },
        {
          key: 'company',
          label: 'Company',
          render: (r) => <span className="text-xs text-muted-foreground">{r.company ?? '-'}</span>,
          isSecondary: true,
        },
        { key: 'departments', label: 'Department', render: (r) => <span className="text-xs">{r.departments ?? '-'}</span> },
        { key: 'brand', label: 'Brand', render: (r) => <span className="text-xs">{r.brand ?? '-'}</span> },
        {
          key: 'hours', label: 'Hours (Month)', expandOnly: true,
          render: (r) => {
            const s = ws[r.id]
            return <span className="text-xs">{s ? `${s.total_hours}h (avg ${s.avg_daily_hours}h/day)` : '—'}</span>
          },
        },
        {
          key: 'score', label: 'Productivity', expandOnly: true,
          render: (r) => {
            const s = ws[r.id]
            return <span className="text-xs">{s ? `${s.productivity_score}/100` : '—'}</span>
          },
        },
        {
          key: 'email', label: 'Email', expandOnly: true,
          render: (r) => <span className="text-xs text-muted-foreground">{r.email ?? '-'}</span>,
        },
        {
          key: 'phone', label: 'Phone', expandOnly: true,
          render: (r) => <span className="text-xs text-muted-foreground">{r.phone ?? '-'}</span>,
        },
      ]
    },
    [workStats],
  )

  if (loadingEmployees) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
        <Skeleton className="h-96 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Contract status tabs */}
      <Tabs value={statusTab} onValueChange={(v) => { setStatusTab(v as ContractStatus); setExpandedRow(null) }}>
        <TabsList>
          <TabsTrigger value="active" className="gap-1.5">
            <UserCheck className="h-3.5 w-3.5" />
            Active
            <Badge variant="secondary" className="text-[10px] h-4 px-1.5 ml-0.5">{statusCounts.active}</Badge>
          </TabsTrigger>
          <TabsTrigger value="suspended" className="gap-1.5">
            <UserMinus className="h-3.5 w-3.5" />
            Suspended
            <Badge variant="secondary" className="text-[10px] h-4 px-1.5 ml-0.5">{statusCounts.suspended}</Badge>
          </TabsTrigger>
          <TabsTrigger value="closed" className="gap-1.5">
            <Archive className="h-3.5 w-3.5" />
            Closed
            <Badge variant="secondary" className="text-[10px] h-4 px-1.5 ml-0.5">{statusCounts.closed}</Badge>
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Filters + Date range + Column toggle toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <FilterBar fields={filterFields} values={filterValues} onChange={setFilterValues} iconOnly />
        <DateField
          mode="range"
          startDate={dateFrom}
          endDate={dateTo}
          onRangeChange={handleDateChange}
          showPresets
        />
        <span className="text-xs text-muted-foreground">
          {filtered.length} of {stats.total} employees
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          {canEditEmployee && statusTab === 'active' && (
            <>
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 gap-1"
                disabled={bulkToggleMutation.isPending}
                onClick={() => {
                  if (window.confirm(`Turn ON missing punch alerts for ${filtered.length} employees?`))
                    bulkToggleMutation.mutate({ userIds: filtered.map(e => e.id), enabled: true })
                }}
              >
                <Bell className="h-3 w-3" />
                All On
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 gap-1"
                disabled={bulkToggleMutation.isPending}
                onClick={() => {
                  if (window.confirm(`Turn OFF missing punch alerts for ${filtered.length} employees?`))
                    bulkToggleMutation.mutate({ userIds: filtered.map(e => e.id), enabled: false })
                }}
              >
                <BellOff className="h-3 w-3" />
                All Off
              </Button>
            </>
          )}
          <ColumnToggle
            visibleColumns={visibleColumns}
            defaultColumns={defaultColumns}
            columnDefs={columnDefs as ColumnDef<never>[]}
            lockedColumns={lockedColumns}
            onChange={setVisibleColumns}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-4 lg:grid-cols-8">
        <StatCard title="Employees" value={`${filtered.length} / ${stats.total}`} icon={<Users className="h-4 w-4" />} />
        {statusTab === 'active' && (
          <StatCard
            title="Present Today"
            value={`${absenceCounts.present} / ${filtered.length}`}
            icon={<UserCheck className="h-4 w-4" />}
            className={absenceCounts.present >= filtered.length * 0.9 ? '[&_p.text-base]:text-green-600' : absenceCounts.present >= filtered.length * 0.7 ? '[&_p.text-base]:text-yellow-600' : '[&_p.text-base]:text-red-600'}
          />
        )}
        {statusTab === 'active' && (
          <StatCard
            title="Absent / On Leave"
            value={`${absenceCounts.absent} / ${absenceCounts.onLeave}`}
            icon={<UserX className="h-4 w-4" />}
            className={(absenceCounts.absent + absenceCounts.onLeave) === 0 ? '[&_p.text-base]:text-green-600' : (absenceCounts.absent + absenceCounts.onLeave) <= 10 ? '[&_p.text-base]:text-yellow-600' : '[&_p.text-base]:text-red-600'}
          />
        )}
        <StatCard title="Total Hours" value={`${stats.totalHours}h`} icon={<Clock className="h-4 w-4" />} />
        <StatCard
          title="Avg Hours/Man"
          value={`${stats.netAvgHoursPerMan}h`}
          description={`Gross: ${stats.grossAvgHoursPerMan}h`}
          icon={<Clock className="h-4 w-4" />}
        />
        <StatCard
          title="Avg Productivity"
          value={`${stats.netAvgProductivity}%`}
          description={`Gross: ${stats.grossAvgProductivity}%`}
          icon={<TrendingUp className="h-4 w-4" />}
          className={stats.netAvgProductivity >= 90 ? '[&_p.text-base]:text-green-600' : stats.netAvgProductivity >= 70 ? '[&_p.text-base]:text-yellow-600' : '[&_p.text-base]:text-red-600'}
        />
        <StatCard
          title="Avg Efficiency"
          value={`${stats.netAvgScore}%`}
          description={`Gross: ${stats.grossAvgScore}%`}
          icon={<TrendingUp className="h-4 w-4" />}
          className={stats.netAvgScore >= 80 ? '[&_p.text-base]:text-green-600' : stats.netAvgScore >= 60 ? '[&_p.text-base]:text-yellow-600' : '[&_p.text-base]:text-red-600'}
        />
        {/* Avg Variance — graphical card with bar + hover tooltip */}
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Card className="gap-0 py-0 cursor-help">
                <CardContent className="px-3 py-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-muted-foreground">Avg Variance</p>
                    <div className="text-muted-foreground"><Clock className="h-3 w-3" /></div>
                  </div>
                  <p className={cn('text-base font-semibold leading-snug', stats.avgVariance <= 10 ? 'text-green-600' : stats.avgVariance <= 25 ? 'text-yellow-600' : 'text-red-600')}>
                    {`\u00B1${stats.avgVariance}min`}
                  </p>
                  <div className={cn('h-1.5 rounded-full mt-1', stats.avgVariance <= 10 ? 'bg-green-100 dark:bg-green-950/40' : stats.avgVariance <= 25 ? 'bg-yellow-100 dark:bg-yellow-950/40' : 'bg-red-100 dark:bg-red-950/40')}>
                    <div
                      className={cn('h-full rounded-full transition-all', stats.avgVariance <= 10 ? 'bg-green-500' : stats.avgVariance <= 25 ? 'bg-yellow-500' : 'bg-red-500')}
                      style={{ width: `${Math.min(stats.avgVariance / 60 * 100, 100)}%` }}
                    />
                  </div>
                </CardContent>
              </Card>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[240px] text-xs">
              <p className="font-semibold mb-0.5">Schedule Variance</p>
              <p className="text-muted-foreground">Average deviation from usual check-in/out times across all employees. Lower = more consistent schedules.</p>
              <p className="mt-1">{stats.avgVariance <= 10 ? 'Very consistent' : stats.avgVariance <= 25 ? 'Moderate variation' : 'High variation'}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* Data */}
      {employees.length === 0 ? (
        <EmptyState icon={<Users className="h-10 w-10" />} title="No Employees" description="No employees found." />
      ) : isMobile ? (
        <MobileCardList
          data={filtered}
          fields={mobileFields}
          getRowId={(r) => r.id}
          onRowClick={(r) => navigate(`/app/hr/employees/${r.id}`)}
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    {activeVisibleColumns.map((key) => {
                      const col = columnDefs.find((c) => c.key === key)
                      if (!col) return null
                      const sortable = SORTABLE_FIELDS.has(key)
                      return (
                        <TableHead
                          key={key}
                          className={cn(col.className, sortable && 'cursor-pointer select-none')}
                          onClick={sortable ? () => toggleSort(key as SortField) : undefined}
                        >
                          {sortable ? (
                            <span className="flex items-center gap-1">
                              {col.label} <ArrowUpDown className="h-3 w-3" />
                            </span>
                          ) : col.label}
                        </TableHead>
                      )
                    })}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((e) => {
                    const isExpanded = expandedRow === e.id
                    return (
                      <Fragment key={e.id}>
                        <TableRow
                          className={cn('cursor-pointer hover:bg-muted/40', isExpanded && 'bg-muted/50')}
                          onClick={() => setExpandedRow(isExpanded ? null : e.id)}
                          aria-expanded={isExpanded}
                        >
                          <TableCell className="w-8 px-2">
                            {isExpanded
                              ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                              : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
                          </TableCell>
                          {activeVisibleColumns.map((key) => {
                            const col = columnDefs.find((c) => c.key === key)
                            if (!col) return null
                            return <TableCell key={key} className={col.className}>{col.render(e)}</TableCell>
                          })}
                        </TableRow>
                        {isExpanded && (
                          <TableRow>
                            <TableCell colSpan={activeVisibleColumns.length + 1} className="p-0">
                              <ExpandedEmployeeRow employee={e} onNavigate={() => navigate(`/app/hr/employees/${e.id}`)} />
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
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

function AbsenceBadge({ status }: { status?: { status: string; leave_code?: string } }) {
  if (!status) return <span className="text-xs text-muted-foreground">—</span>
  switch (status.status) {
    case 'present':
      return <span className="inline-flex items-center gap-1 text-xs text-green-600"><span className="w-1.5 h-1.5 rounded-full bg-green-500" />Present</span>
    case 'on_leave':
      return (
        <Badge variant="outline" className="text-[10px] border-orange-300 text-orange-600 bg-orange-50 dark:bg-orange-950/30">
          {LEAVE_LABELS[status.leave_code ?? ''] ?? status.leave_code ?? 'Leave'}
        </Badge>
      )
    case 'absent':
      return <span className="inline-flex items-center gap-1 text-xs text-red-600"><span className="w-1.5 h-1.5 rounded-full bg-red-500" />Absent</span>
    case 'holiday':
      return <Badge variant="outline" className="text-[10px] border-blue-300 text-blue-600 bg-blue-50 dark:bg-blue-950/30">Holiday</Badge>
    default:
      return <span className="text-xs text-muted-foreground">—</span>
  }
}

function ExpandedEmployeeRow({ employee: e, onNavigate }: { employee: HrEmployee; onNavigate: () => void }) {
  const { data: overviewRes, isLoading } = useQuery({
    queryKey: ['hr', 'employee-overview', e.id],
    queryFn: () => hrApi.getEmployeeOverview(e.id),
  })

  const overview = overviewRes?.data ?? null

  return (
    <div className="px-8 py-3 border-l-2 border-l-primary/50 bg-muted/30 shadow-[inset_0_1px_0_0_hsl(var(--border)),inset_0_-1px_0_0_hsl(var(--border))]">
      {isLoading ? (
        <div className="flex gap-4">
          <Skeleton className="h-16 w-48" />
          <Skeleton className="h-16 w-48" />
          <Skeleton className="h-16 w-48" />
        </div>
      ) : (
        <div className="flex flex-wrap gap-x-8 gap-y-3 items-start">
          {/* Contact */}
          <div className="space-y-1 min-w-[180px]">
            <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Contact</div>
            <div className="flex items-center gap-1.5 text-xs">
              <Mail className="h-3 w-3 text-muted-foreground" />
              {e.email || '-'}
            </div>
            <div className="flex items-center gap-1.5 text-xs">
              <Phone className="h-3 w-3 text-muted-foreground" />
              {e.phone || '-'}
            </div>
          </div>

          {/* Organization */}
          <div className="space-y-1 min-w-[160px]">
            <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Organization</div>
            <div className="text-xs">{e.company ?? '-'}</div>
            <div className="text-xs text-muted-foreground">
              {[e.brand, e.departments, e.subdepartment].filter(Boolean).join(' > ') || '-'}
            </div>
          </div>

          {/* Connectors */}
          {overview && (
            <div className="space-y-1 min-w-[140px]">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Connectors</div>
              <div className="flex items-center gap-1.5 text-xs">
                <Fingerprint className="h-3 w-3" />
                BioStar:
                {overview.biostar
                  ? <Badge variant="default" className="text-[10px] h-4 ml-1">Mapped</Badge>
                  : <Badge variant="secondary" className="text-[10px] h-4 ml-1">Unmapped</Badge>}
              </div>
              <div className="flex items-center gap-1.5 text-xs">
                <FileSpreadsheet className="h-3 w-3" />
                Sincron:
                {overview.sincron
                  ? <Badge variant="default" className="text-[10px] h-4 ml-1">Mapped</Badge>
                  : <Badge variant="secondary" className="text-[10px] h-4 ml-1">Unmapped</Badge>}
              </div>
            </div>
          )}

          {/* Quick stats */}
          {overview && (
            <div className="space-y-1 min-w-[120px]">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Stats</div>
              <div className="text-xs">Bonuses: <span className="font-medium">{overview.bonuses.count}</span></div>
              <div className="text-xs">Forms: <span className="font-medium">{overview.forms_count}</span></div>
              {overview.biostar && (
                <div className="text-xs">Schedule: <span className="font-medium">{overview.biostar.working_hours}h/day</span></div>
              )}
            </div>
          )}

          {/* Sincron contract */}
          {overview?.sincron && (
            <div className="space-y-1 min-w-[140px]">
              <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Contract</div>
              <div className="text-xs">Nr: <span className="font-medium">{overview.sincron.nr_contract || '-'}</span></div>
              <div className="text-xs text-muted-foreground">
                From: {overview.sincron.data_incepere_contract
                  ? new Date(overview.sincron.data_incepere_contract).toLocaleDateString('ro-RO')
                  : '-'}
              </div>
            </div>
          )}

          {/* View full profile button */}
          <div className="flex items-end ml-auto">
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7 gap-1"
              onClick={(ev) => { ev.stopPropagation(); onNavigate() }}
            >
              <ExternalLink className="h-3 w-3" />
              Full Profile
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
