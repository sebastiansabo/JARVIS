import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sincronApi, type SincronTeamMember, type SincronTimesheetData } from '@/api/sincron'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { useHrStore } from '@/stores/hrStore'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Users, Clock, CalendarDays, Timer, ArrowUpDown,
  ChevronLeft, ChevronRight, FileSpreadsheet, Building2, RefreshCw,
} from 'lucide-react'
import { toast } from 'sonner'

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const SHORT_MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

const CODE_LABELS: Record<string, { label: string; description: string; color: string }> = {
  OZ: { label: 'Work Hours', description: 'Ore Zilnice — Ore lucrate în ziua respectivă', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' },
  CO: { label: 'Annual Leave', description: 'Concediu de Odihnă — Zile de vacanță', color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  CM: { label: 'Medical Leave', description: 'Concediu Medical — Zile de boală', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
  OS: { label: 'Overtime', description: 'Ore Suplimentare — Ore lucrate peste program', color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200' },
  OSW: { label: 'Weekend Overtime', description: 'Ore Suplimentare Weekend — Ore lucrate în weekend', color: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200' },
  CIC: { label: 'Child Care', description: 'Concediu Îngrijire Copil — Concediu parental', color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200' },
  CES: { label: 'Unpaid Leave', description: 'Concediu fără Salariu — Zile libere neplătite', color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200' },
  DLG: { label: 'Delegation', description: 'Delegație — Deplasare în interes de serviciu', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' },
  CMS: { label: 'Sick Family', description: 'Concediu Medical Sarcină — Concediu medical maternitate', color: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200' },
  X: { label: 'Absent', description: 'Absent Nemotivat — Absență fără justificare', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
  ZLS: { label: 'Extra Days Off', description: 'Zile Libere Suplimentare — Zile libere acordate suplimentar', color: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200' },
  ZLC: { label: 'Compensatory Days', description: 'Zile Libere Compensatorii — Zile libere compensatorii pentru ore suplimentare', color: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200' },
}

/** Build month-year options for the combined selector (current year ± 1) */
function buildMonthYearOptions() {
  const now = new Date()
  const currentYear = now.getFullYear()
  const options: { value: string; label: string; year: number; month: number }[] = []
  for (let y = currentYear - 1; y <= currentYear + 1; y++) {
    for (let m = 1; m <= 12; m++) {
      options.push({
        value: `${y}-${m}`,
        label: `${SHORT_MONTHS[m - 1]} ${y}`,
        year: y,
        month: m,
      })
    }
  }
  return options
}

const MONTH_YEAR_OPTIONS = buildMonthYearOptions()

interface Props {
  search: string
}

type SortField = 'name' | 'company' | 'total_hours'

export default function TimesheetTab({ search }: Props) {
  const isMobile = useIsMobile()
  const filters = useHrStore((s) => s.filters)
  const updateFilter = useHrStore((s) => s.updateFilter)

  const year = filters.timesheetYear!
  const month = filters.timesheetMonth!
  const nodeId = filters.timesheetNodeId ?? undefined

  const setYear = (y: number) => updateFilter('timesheetYear', y)
  const setMonth = (m: number) => updateFilter('timesheetMonth', m)
  const setNodeId = (id: number | null) => updateFilter('timesheetNodeId', id)

  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [detailUser, setDetailUser] = useState<{ id: number; name: string } | null>(null)

  const queryClient = useQueryClient()

  const { data: lastRun, refetch: refetchLastRun } = useQuery({
    queryKey: ['sincron', 'sync-last-run', year, month],
    queryFn: () => sincronApi.getSyncLastRun(year, month),
    staleTime: 30 * 1000,
  })

  const syncMutation = useMutation({
    mutationFn: () => sincronApi.syncTimesheets({ year, month }),
    onSuccess: () => {
      toast.success('Sync started', { description: `Sincron timesheet sync for ${MONTHS[month - 1]} ${year} started in background.` })
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['sincron', 'team-timesheet'] })
        refetchLastRun()
      }, 5000)
    },
    onError: () => toast.error('Sync failed', { description: 'Could not start Sincron sync. Try again.' }),
  })

  // Fetch tree for node filter
  const { data: treeData } = useQuery({
    queryKey: ['sincron', 'timesheet-tree'],
    queryFn: () => sincronApi.getTimesheetTree(),
    staleTime: 5 * 60 * 1000,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['sincron', 'team-timesheet', year, month, nodeId],
    queryFn: () => sincronApi.getTeamTimesheet(year, month, nodeId),
  })

  const team: SincronTeamMember[] = data?.data ?? []

  // Build node filter options from tree data
  const nodeOptions = useMemo(() => {
    if (!treeData) return []
    const companies = treeData.companies ?? []
    const nodes = treeData.nodes ?? []
    const opts: { value: string; label: string; indent: number }[] = []

    // Group nodes by company_id
    const nodesByCompany = new Map<number, typeof nodes>()
    nodes.forEach((n) => {
      if (!nodesByCompany.has(n.company_id)) nodesByCompany.set(n.company_id, [])
      nodesByCompany.get(n.company_id)!.push(n)
    })

    companies.forEach((c) => {
      opts.push({ value: `company-${c.company_id}`, label: c.name, indent: 0 })
      const companyNodes = nodesByCompany.get(c.company_id) ?? []
      companyNodes.forEach((n) => {
        opts.push({ value: `node-${n.id}`, label: n.name, indent: n.level })
      })
    })

    return opts
  }, [treeData])

  // Collect all activity codes across team
  const allCodes = useMemo(() => {
    const codes = new Set<string>()
    team.forEach((m) => Object.keys(m.codes).forEach((c) => codes.add(c)))
    const arr = [...codes]
    arr.sort((a, b) => {
      if (a === 'OZ') return -1
      if (b === 'OZ') return 1
      return a.localeCompare(b)
    })
    return arr
  }, [team])

  // Determine active company filter (for client-side company filtering)
  const selectedCompanyName = useMemo(() => {
    if (!nodeId) return null
    const key = `company-${nodeId}`
    // nodeId is numeric but company selections use company_id
    // Check if current filter is a company-level selection
    const match = nodeOptions.find((o) => o.value === key)
    return match ? match.label : null
  }, [nodeId, nodeOptions])

  // Search + sort + company filter
  const filtered = useMemo(() => {
    let rows = team
    if (selectedCompanyName) {
      rows = rows.filter((m) => m.company === selectedCompanyName)
    }
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
  }, [team, search, sortField, sortDir, selectedCompanyName])

  // Stats (based on filtered data)
  const stats = useMemo(() => {
    const totalOZ = filtered.reduce((s, m) => s + (m.codes['OZ']?.value ?? 0), 0)
    const totalCO = filtered.reduce((s, m) => s + (m.codes['CO']?.days ?? 0), 0)
    const totalOS = filtered.reduce((s, m) => s + (m.codes['OS']?.value ?? 0), 0)
    return { employees: filtered.length, workHours: totalOZ, leaveDays: totalCO, overtimeHours: totalOS }
  }, [filtered])

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortField(field); setSortDir('asc') }
  }

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear(year - 1) }
    else setMonth(month - 1)
  }
  function nextMonth() {
    if (month === 12) { setMonth(1); setYear(year + 1) }
    else setMonth(month + 1)
  }

  function handleMonthYearChange(value: string) {
    const [y, m] = value.split('-').map(Number)
    setYear(y)
    setMonth(m)
  }

  function handleNodeChange(value: string) {
    if (value === '__all__') {
      setNodeId(null)
      return
    }
    if (value.startsWith('node-')) {
      setNodeId(Number(value.replace('node-', '')))
    } else {
      // company-level → client-side filtering, no backend node_id
      // Store the company_id as nodeId for state tracking (will be used for client-side filtering)
      setNodeId(Number(value.replace('company-', '')))
    }
  }

  // Check if current nodeId selection is a company-level filter
  const isCompanyFilter = useMemo(() => {
    if (!nodeId) return false
    return nodeOptions.some((o) => o.value === `company-${nodeId}`)
  }, [nodeId, nodeOptions])

  // Active filter display value
  const activeNodeFilterValue = useMemo(() => {
    if (!nodeId) return '__all__'
    if (isCompanyFilter) return `company-${nodeId}`
    return `node-${nodeId}`
  }, [nodeId, isCompanyFilter])

  const mobileFields: MobileCardField<SincronTeamMember>[] = useMemo(() => [
    { key: 'name', label: 'Name', render: (r) => <span className="font-medium">{r.name}</span> },
    { key: 'company', label: 'Company', render: (r) => <span className="text-xs text-muted-foreground">{r.company}</span> },
    ...allCodes.map((code) => ({
      key: code as keyof SincronTeamMember,
      label: CODE_LABELS[code]?.label ?? code,
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

  return (
    <div className="space-y-4">
      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Month-Year combined picker */}
        <Button variant="outline" size="icon" className="h-8 w-8" onClick={prevMonth}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Select value={`${year}-${month}`} onValueChange={handleMonthYearChange}>
          <SelectTrigger className="h-8 w-36 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-64">
            {(() => {
              const now = new Date()
              const currentYear = now.getFullYear()
              const years = [currentYear - 1, currentYear, currentYear + 1]
              return years.map((y) => (
                <SelectGroup key={y}>
                  <SelectLabel className="text-xs font-semibold text-muted-foreground">{y}</SelectLabel>
                  {MONTH_YEAR_OPTIONS.filter((o) => o.year === y).map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectGroup>
              ))
            })()}
          </SelectContent>
        </Select>
        <Button variant="outline" size="icon" className="h-8 w-8" onClick={nextMonth}>
          <ChevronRight className="h-4 w-4" />
        </Button>

        {/* Node / Company filter */}
        {nodeOptions.length > 0 && (
          <>
            <div className="w-px h-6 bg-border mx-1" />
            <Building2 className="h-4 w-4 text-muted-foreground" />
            <Select value={activeNodeFilterValue} onValueChange={handleNodeChange}>
              <SelectTrigger className="h-8 w-auto min-w-[160px] max-w-[260px] text-xs gap-1">
                <SelectValue placeholder="All Companies" />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                <SelectItem value="__all__">All Companies</SelectItem>
                {nodeOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    <span style={{ paddingLeft: `${opt.indent * 12}px` }} className="flex items-center gap-1">
                      {opt.indent === 0 ? <Building2 className="h-3 w-3 inline-block shrink-0" /> : null}
                      {opt.label}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        )}

        {/* Sync button + last run status — top-right */}
        <div className="ml-auto flex items-center gap-2">
          {lastRun && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={`h-2 w-2 rounded-full shrink-0 ${
                lastRun.status === 'completed' ? 'bg-green-500' :
                lastRun.status === 'failed' ? 'bg-red-500' : 'bg-yellow-400'
              }`} />
              <span className="hidden sm:inline">
                {lastRun.status === 'completed'
                  ? `${lastRun.employees_synced ?? 0} emp · ${lastRun.records_created ?? 0} rec`
                  : lastRun.status === 'failed'
                  ? (lastRun.error_message ?? 'Failed')
                  : 'Running…'}
              </span>
              <span className="hidden md:inline text-muted-foreground/60">
                · {lastRun.finished_at
                    ? new Date(lastRun.finished_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    : new Date(lastRun.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          )}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5"
                  onClick={() => syncMutation.mutate()}
                  disabled={syncMutation.isPending}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
                  {syncMutation.isPending ? 'Syncing…' : 'Sync'}
                </Button>
              </TooltipTrigger>
              <TooltipContent>Sync Sincron timesheets for {MONTHS[month - 1]} {year}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard title="Employees" value={stats.employees} icon={<Users className="h-4 w-4" />} />
        <StatCard title="Work Hours (OZ)" value={`${stats.workHours.toFixed(1)}h (${(stats.workHours / 8).toFixed(1)}d)`} icon={<Clock className="h-4 w-4" />} />
        <StatCard title="Leave Days (CO)" value={`${stats.leaveDays}d (${(stats.leaveDays * 8)}h)`} icon={<CalendarDays className="h-4 w-4" />} />
        <StatCard title="Overtime (OS)" value={`${stats.overtimeHours.toFixed(1)}h (${(stats.overtimeHours / 8).toFixed(1)}d)`} icon={<Timer className="h-4 w-4" />} />
      </div>

      {/* Data */}
      {team.length === 0 ? (
        <EmptyState
          icon={<FileSpreadsheet className="h-10 w-10" />}
          title="No Timesheet Data"
          description={`No Sincron timesheet data found for ${MONTHS[month - 1]} ${year}. Sync timesheets from Settings > Connectors.`}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<FileSpreadsheet className="h-10 w-10" />}
          title="No Matching Employees"
          description="No employees match the current filters. Try adjusting your search or node filter."
        />
      ) : isMobile ? (
        <MobileCardList
          data={filtered}
          fields={mobileFields}
          getRowId={(r) => r.user_id}
          onRowClick={(r) => setDetailUser({ id: r.user_id, name: r.name })}
        />
      ) : (
        <TooltipProvider>
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
                      {allCodes.map((code) => {
                        const info = CODE_LABELS[code]
                        return (
                          <TableHead key={code} className="text-center">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge variant="outline" className={`text-xs cursor-help ${info?.color ?? ''}`}>
                                  {code}
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent side="bottom" className="max-w-xs">
                                <p className="font-semibold">{info?.label ?? code}</p>
                                <p className="text-xs text-muted-foreground">{info?.description ?? code}</p>
                              </TooltipContent>
                            </Tooltip>
                          </TableHead>
                        )
                      })}
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
        </TooltipProvider>
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
          <TooltipProvider>
            <div className="space-y-4">
              {/* Summary cards */}
              <div className="flex flex-wrap gap-2">
                {summary.map((s) => {
                  const isHour = s.unit === 'hour'
                  const primary = isHour ? `${s.total_value.toFixed(1)}h` : `${s.total_value.toFixed(0)}d`
                  const secondary = isHour ? `${(s.total_value / 8).toFixed(1)}d` : `${(s.total_value * 8).toFixed(0)}h`
                  const info = CODE_LABELS[s.short_code]
                  return (
                    <Tooltip key={s.short_code}>
                      <TooltipTrigger asChild>
                        <Badge variant="outline" className={`text-xs px-2.5 py-1 cursor-help ${info?.color ?? ''}`}>
                          {s.short_code}: {primary} ({secondary}) — {s.day_count}d active
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="font-semibold">{info?.label ?? s.short_code}</p>
                        <p className="text-xs text-muted-foreground">{info?.description ?? s.short_code}</p>
                      </TooltipContent>
                    </Tooltip>
                  )
                })}
              </div>

              {/* Daily breakdown */}
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-28">Date</TableHead>
                      <TableHead className="w-16">Day</TableHead>
                      {allCodes.map((c) => {
                        const info = CODE_LABELS[c]
                        return (
                          <TableHead key={c} className="text-center">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge variant="outline" className={`text-xs cursor-help ${info?.color ?? ''}`}>{c}</Badge>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p className="font-semibold">{info?.label ?? c}</p>
                                <p className="text-xs text-muted-foreground">{info?.description ?? c}</p>
                              </TooltipContent>
                            </Tooltip>
                          </TableHead>
                        )
                      })}
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
                        if (!s) return <TableCell key={c} className="text-center">-</TableCell>
                        const isHour = s.unit === 'hour'
                        const primary = isHour ? `${s.total_value.toFixed(1)}h` : `${s.total_value.toFixed(0)}d`
                        const secondary = isHour ? `(${(s.total_value / 8).toFixed(1)}d)` : `(${(s.total_value * 8).toFixed(0)}h)`
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
            </div>
          </TooltipProvider>
        )}
      </DialogContent>
    </Dialog>
  )
}
