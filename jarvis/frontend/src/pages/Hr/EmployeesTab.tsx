import { useState, useMemo, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { hrApi } from '@/api/hr'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import {
  Users, Building2, ArrowUpDown, Briefcase, ChevronDown, ChevronRight,
  Mail, Phone, Fingerprint, FileSpreadsheet, ExternalLink,
  UserCheck, UserMinus, Archive, Bell, BellOff, UserX,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { HrEmployee, ContractStatus, StructureCompany } from '@/types/hr'

const LEAVE_LABELS: Record<string, string> = {
  CO: 'Annual Leave', CM: 'Medical', CES: 'Unpaid', CIC: 'Child Care',
  CMS: 'Sick Family', DLG: 'Delegation', PERMIT: 'Leave Permit',
}

interface Props {
  search: string
}

type SortField = 'name' | 'company' | 'department'
type SortDir = 'asc' | 'desc'

export default function EmployeesTab({ search }: Props) {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canEditEmployee = user?.permissions?.['hr.employees.edit'] ?? false
  const [statusTab, setStatusTab] = useState<ContractStatus>('active')
  const [companyFilter, setCompanyFilter] = useState<string>('all')
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

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

  // Filter + search + sort
  const filtered = useMemo(() => {
    let rows = employees
    if (companyFilter !== 'all') {
      rows = rows.filter((e) => e.company === companyFilter)
    }
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
  }, [employees, companyFilter, search, sortField, sortDir])

  // Stats
  const stats = useMemo(() => {
    const byCompany = new Map<string, number>()
    employees.forEach((e) => {
      const c = e.company || 'Unknown'
      byCompany.set(c, (byCompany.get(c) ?? 0) + 1)
    })
    return {
      total: employees.length,
      companies: byCompany.size,
      filtered: filtered.length,
    }
  }, [employees, filtered])

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

  const mobileFields: MobileCardField<HrEmployee>[] = useMemo(
    () => [
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
        key: 'email',
        label: 'Email',
        render: (r) => <span className="text-xs text-muted-foreground">{r.email ?? '-'}</span>,
        expandOnly: true,
      },
      {
        key: 'phone',
        label: 'Phone',
        render: (r) => <span className="text-xs text-muted-foreground">{r.phone ?? '-'}</span>,
        expandOnly: true,
      },
    ],
    [],
  )

  if (loadingEmployees) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
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

      {/* Company filter */}
      <div className="flex items-center gap-2">
        <Select value={companyFilter} onValueChange={setCompanyFilter}>
          <SelectTrigger className="h-8 w-56 text-xs">
            <SelectValue placeholder="All Companies" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Companies</SelectItem>
            {companies.map((c) => (
              <SelectItem key={c.id} value={c.company}>
                {c.company}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          {filtered.length} of {stats.total} employees
        </span>
        {canEditEmployee && statusTab === 'active' && (
          <div className="ml-auto flex items-center gap-1.5">
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
          </div>
        )}
      </div>

      {/* Stats */}
      <div className={cn('grid gap-3', statusTab === 'active' ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-2 md:grid-cols-3')}>
        <StatCard title="Total Employees" value={stats.total} icon={<Users className="h-4 w-4" />} />
        <StatCard title="Companies" value={stats.companies} icon={<Building2 className="h-4 w-4" />} />
        <StatCard
          title={companyFilter !== 'all' ? companyFilter : 'Showing'}
          value={filtered.length}
          icon={<Briefcase className="h-4 w-4" />}
        />
        {statusTab === 'active' && (
          <StatCard
            title="Absent / On Leave"
            value={`${absenceCounts.absent} / ${absenceCounts.onLeave}`}
            icon={<UserX className="h-4 w-4" />}
          />
        )}
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
                    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('name')}>
                      <span className="flex items-center gap-1">
                        Name <ArrowUpDown className="h-3 w-3" />
                      </span>
                    </TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('company')}>
                      <span className="flex items-center gap-1">
                        Company <ArrowUpDown className="h-3 w-3" />
                      </span>
                    </TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => toggleSort('department')}>
                      <span className="flex items-center gap-1">
                        Department <ArrowUpDown className="h-3 w-3" />
                      </span>
                    </TableHead>
                    <TableHead>Brand</TableHead>
                    <TableHead className="text-center">Status</TableHead>
                    {statusTab === 'active' && <TableHead className="text-center">Today</TableHead>}
                    {canEditEmployee && <TableHead className="text-center w-20">Punch Alert</TableHead>}
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
                          <TableCell className="font-medium">{e.name}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{e.company ?? '-'}</TableCell>
                          <TableCell className="text-xs">{e.departments ?? '-'}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{e.brand ?? '-'}</TableCell>
                          <TableCell className="text-center">
                            <Badge
                              variant={e.contract_status === 'active' ? 'default' : e.contract_status === 'suspended' ? 'outline' : 'secondary'}
                              className={cn('text-xs', e.contract_status === 'suspended' && 'border-amber-500 text-amber-600')}
                            >
                              {e.contract_status === 'active' ? 'Active' : e.contract_status === 'suspended' ? 'Suspended' : 'Closed'}
                            </Badge>
                          </TableCell>
                          {statusTab === 'active' && (
                            <TableCell className="text-center">
                              <AbsenceBadge status={absentData?.[e.id]} />
                            </TableCell>
                          )}
                          {canEditEmployee && (
                            <TableCell className="text-center">
                              <Switch
                                checked={e.notify_missing_punch ?? true}
                                disabled={toggleMutation.isPending}
                                aria-label={`Toggle missing punch alert for ${e.name}`}
                                onCheckedChange={(checked) => {
                                  toggleMutation.mutate({ employeeId: e.id, enabled: checked })
                                }}
                                onClick={(ev) => ev.stopPropagation()}
                                className="scale-75"
                              />
                            </TableCell>
                          )}
                        </TableRow>
                        {isExpanded && (
                          <TableRow>
                            <TableCell colSpan={6 + (statusTab === 'active' ? 1 : 0) + (canEditEmployee ? 1 : 0)} className="p-0">
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
