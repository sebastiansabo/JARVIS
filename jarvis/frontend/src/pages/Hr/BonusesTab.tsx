import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import {
  Plus,
  Trash2,
  Pencil,
  Copy,
  Search,
  Users,
  CalendarDays,
  ChevronRight,
  Lock,
  CheckSquare,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { QueryError } from '@/components/QueryError'
import { EmptyState } from '@/components/shared/EmptyState'
import { SearchSelect } from '@/components/shared/SearchSelect'
import { hrApi } from '@/api/hr'
import { useHrStore } from '@/stores/hrStore'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { EventBonus, BonusSummaryByEmployee, BonusSummaryByEvent } from '@/types/hr'

const MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const MONTH_SHORT = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export default function BonusesTab({ canViewAmounts }: { canViewAmounts: boolean }) {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const filters = useHrStore((s) => s.filters)
  const updateFilter = useHrStore((s) => s.updateFilter)
  const selectedBonusIds = useHrStore((s) => s.selectedIds)
  const setSelectedBonusIds = useHrStore((s) => s.setSelectedIds)
  const toggleBonusSelected = useHrStore((s) => s.toggleSelected)
  const clearSelected = useHrStore((s) => s.clearSelected)
  const [subTab, setSubTab] = useState<'list' | 'by-employee' | 'by-event'>('list')
  const [search, setSearch] = useState('')
  const [editBonus, setEditBonus] = useState<EventBonus | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [isDuplicate, setIsDuplicate] = useState(false)
  const [deleteIds, setDeleteIds] = useState<number[] | null>(null)
  const [selectMode, setSelectMode] = useState(false)

  // Data
  const { data: bonuses = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['hr-bonuses', filters.year, filters.month],
    queryFn: () => hrApi.getBonuses({ year: filters.year, month: filters.month }),
  })

  const { data: byEmployee = [] } = useQuery({
    queryKey: ['hr-summary-by-employee', filters.year, filters.month],
    queryFn: () => hrApi.getSummaryByEmployee({ year: filters.year, month: filters.month }),
    enabled: subTab === 'by-employee',
  })

  const { data: byEvent = [] } = useQuery({
    queryKey: ['hr-summary-by-event', filters.year, filters.month],
    queryFn: () => hrApi.getSummaryByEvent({ year: filters.year, month: filters.month }),
    enabled: subTab === 'by-event',
  })

  const { data: lockStatus } = useQuery({
    queryKey: ['hr-lock-status', filters.year, filters.month],
    queryFn: () => hrApi.getLockStatus({ year: filters.year, month: filters.month }),
  })

  const { data: events = [] } = useQuery({
    queryKey: ['hr-events'],
    queryFn: () => hrApi.getEvents(),
  })

  const { data: employees = [] } = useQuery({
    queryKey: ['hr-employees'],
    queryFn: () => hrApi.getEmployees(),
  })

  // Filtered list
  const filtered = useMemo(() => {
    if (!search) return bonuses
    const q = search.toLowerCase()
    return bonuses.filter(
      (b) =>
        b.employee_name.toLowerCase().includes(q) ||
        b.event_name.toLowerCase().includes(q) ||
        (b.company?.toLowerCase().includes(q) ?? false) ||
        (b.brand?.toLowerCase().includes(q) ?? false) ||
        (b.department?.toLowerCase().includes(q) ?? false),
    )
  }, [bonuses, search])

  // Mutations
  const deleteMutation = useMutation({
    mutationFn: (ids: number[]) => hrApi.bulkDeleteBonuses(ids),
    onSuccess: () => {
      toast.success('Deleted successfully')
      clearSelected()
      queryClient.invalidateQueries({ queryKey: ['hr-bonuses'] })
      queryClient.invalidateQueries({ queryKey: ['hr-summary'] })
    },
    onError: () => toast.error('Delete failed'),
  })

  // Selection
  const allSelected = filtered.length > 0 && filtered.every((b) => selectedBonusIds.includes(b.id))
  const someSelected = filtered.some((b) => selectedBonusIds.includes(b.id))

  const years = Array.from({ length: 7 }, (_, i) => new Date().getFullYear() - 3 + i)

  return (
    <div className="space-y-4">
      {/* Lock warning */}
      {lockStatus?.locked && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 px-4 py-2 text-sm">
          <Lock className="h-4 w-4 text-amber-500" />
          <span>{lockStatus.message}</span>
          {lockStatus.can_override && (
            <Badge variant="outline" className="ml-auto text-amber-600">Admin override</Badge>
          )}
        </div>
      )}

      {/* Filters + actions */}
      <div className="flex flex-wrap items-center gap-2">
        <Select value={String(filters.year ?? '__all__')} onValueChange={(v) => updateFilter('year', v === '__all__' ? undefined : Number(v))}>
          <SelectTrigger className="w-24">
            <SelectValue placeholder="Year" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All years</SelectItem>
            {years.map((y) => (
              <SelectItem key={y} value={String(y)}>{y}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={String(filters.month ?? '__all__')} onValueChange={(v) => updateFilter('month', v === '__all__' ? undefined : Number(v))}>
          <SelectTrigger className="w-32">
            <SelectValue placeholder="Month" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All months</SelectItem>
            {MONTHS.slice(1).map((m, i) => (
              <SelectItem key={i + 1} value={String(i + 1)}>{m}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {subTab === 'list' && (
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-8"
              placeholder="Search employee, event..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          {selectedBonusIds.length > 0 && (
            <Button variant="destructive" size="sm" onClick={() => setDeleteIds(selectedBonusIds)}>
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              Delete ({selectedBonusIds.length})
            </Button>
          )}
          {isMobile && (
            selectMode ? (
              <Button variant="ghost" size="sm" onClick={() => { clearSelected(); setSelectMode(false) }}>Cancel</Button>
            ) : (
              <Button variant="outline" size="icon" onClick={() => setSelectMode(true)} title="Select">
                <CheckSquare className="h-4 w-4" />
              </Button>
            )
          )}
          <Button size="sm" onClick={() => { setEditBonus(null); setAddOpen(true) }}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Add Bonus
          </Button>
        </div>
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-1">
        {(['list', 'by-employee', 'by-event'] as const).map((t) => (
          <button
            key={t}
            onClick={() => { setSubTab(t); clearSelected() }}
            className={cn(
              'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
              subTab === t ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:text-foreground',
            )}
          >
            {t === 'list' ? 'Bonuses' : t === 'by-employee' ? 'By Employee' : 'By Event'}
          </button>
        ))}
        <span className="ml-2 self-center text-xs text-muted-foreground">
          {subTab === 'list' ? filtered.length : subTab === 'by-employee' ? byEmployee.length : byEvent.length} rows
        </span>
      </div>

      {/* Tables */}
      {isError && (
        <QueryError message="Failed to load bonuses" onRetry={() => refetch()} />
      )}
      {subTab === 'list' && !isError && (
        <BonusListTable
          bonuses={filtered}
          isLoading={isLoading}
          selectedIds={selectedBonusIds}
          allSelected={allSelected}
          someSelected={someSelected}
          onToggleSelect={toggleBonusSelected}
          onSelectAll={() => {
            if (allSelected) clearSelected()
            else setSelectedBonusIds(filtered.map((b) => b.id))
          }}
          onEdit={(b) => { setEditBonus(b); setIsDuplicate(false); setAddOpen(true) }}
          onDuplicate={(b) => { setEditBonus(b); setIsDuplicate(true); setAddOpen(true) }}
          onDelete={(id) => setDeleteIds([id])}
          canViewAmounts={canViewAmounts}
          isMobile={isMobile}
          selectMode={selectMode}
        />
      )}

      {subTab === 'by-employee' && (
        <ByEmployeeTable data={byEmployee} canViewAmounts={canViewAmounts} isMobile={isMobile} />
      )}

      {subTab === 'by-event' && (
        <ByEventTable data={byEvent} canViewAmounts={canViewAmounts} isMobile={isMobile} />
      )}

      {/* Add/Edit/Duplicate Bonus Dialog */}
      <BonusDialog
        open={addOpen}
        bonus={editBonus}
        isDuplicate={isDuplicate}
        events={events}
        employees={employees}
        onClose={() => { setAddOpen(false); setEditBonus(null); setIsDuplicate(false) }}
      />

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteIds}
        title="Delete Bonuses"
        description={`Delete ${deleteIds?.length ?? 0} bonus record(s)? This cannot be undone.`}
        onOpenChange={() => setDeleteIds(null)}
        onConfirm={() => deleteIds && deleteMutation.mutate(deleteIds)}
        destructive
      />
    </div>
  )
}

/* ──── Bonus List Table ──── */

function BonusListTable({
  bonuses, isLoading, selectedIds, allSelected, someSelected,
  onToggleSelect, onSelectAll, onEdit, onDuplicate, onDelete, canViewAmounts, isMobile, selectMode,
}: {
  bonuses: EventBonus[]
  isLoading: boolean
  selectedIds: number[]
  allSelected: boolean
  someSelected: boolean
  onToggleSelect: (id: number) => void
  onSelectAll: () => void
  onEdit: (b: EventBonus) => void
  onDuplicate: (b: EventBonus) => void
  onDelete: (id: number) => void
  canViewAmounts: boolean
  isMobile: boolean
  selectMode?: boolean
}) {
  const mobileFields: MobileCardField<EventBonus>[] = useMemo(() => [
    {
      key: 'employee',
      label: 'Employee',
      isPrimary: true,
      render: (b) => b.employee_name,
    },
    {
      key: 'event',
      label: 'Event',
      isSecondary: true,
      render: (b) => (
        <span className="flex items-center gap-1.5">
          {b.event_name}
          <Badge variant="outline" className="text-[10px]">{MONTH_SHORT[b.month] || b.month} {b.year}</Badge>
        </span>
      ),
    },
    {
      key: 'days',
      label: 'Days',
      render: (b) => <span className="text-xs">{b.bonus_days ?? '—'}</span>,
    },
    {
      key: 'hours',
      label: 'Hours',
      render: (b) => <span className="text-xs">{b.hours_free ?? '—'}</span>,
    },
    ...(canViewAmounts ? [{
      key: 'bonus_net',
      label: 'Bonus (Net)',
      render: (b: EventBonus) => (
        <span className="text-xs font-medium">
          {b.bonus_net != null ? `${Number(b.bonus_net).toFixed(0)} RON` : '—'}
        </span>
      ),
    }] : []),
    {
      key: 'company',
      label: 'Company',
      expandOnly: true,
      render: (b) => <span className="text-xs text-muted-foreground">{b.company ?? '—'}</span>,
    },
    {
      key: 'department',
      label: 'Department',
      expandOnly: true,
      render: (b) => <span className="text-xs text-muted-foreground">{b.department ?? '—'}</span>,
    },
    {
      key: 'brand',
      label: 'Brand',
      expandOnly: true,
      render: (b) => <span className="text-xs text-muted-foreground">{b.brand ?? '—'}</span>,
    },
    {
      key: 'details',
      label: 'Details',
      expandOnly: true,
      render: (b) => <span className="text-xs text-muted-foreground">{b.details || '—'}</span>,
    },
  ] as MobileCardField<EventBonus>[], [canViewAmounts])

  if (isLoading) {
    if (isMobile) {
      return <MobileCardList data={[]} fields={mobileFields} getRowId={() => 0} isLoading />
    }
    return (
      <Card>
        <CardContent className="p-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted mb-2" />
          ))}
        </CardContent>
      </Card>
    )
  }

  if (bonuses.length === 0) {
    return <EmptyState icon={<CalendarDays className="h-8 w-8" />} title="No bonuses found" description="Adjust filters or add a new bonus." />
  }

  if (isMobile) {
    return (
      <>
        <MobileCardList
          data={bonuses}
          fields={mobileFields}
          getRowId={(b) => b.id}
          selectable={selectMode}
          selectedIds={selectedIds}
          onToggleSelect={onToggleSelect}
          actions={(b) => (
            <>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onEdit(b)} title="Edit">
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onDuplicate(b)} title="Duplicate">
                <Copy className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => onDelete(b.id)} title="Delete">
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
        />
        <div className="text-xs text-muted-foreground px-1">
          {bonuses.length} bonus(es)
        </div>
      </>
    )
  }

  return (
    <Card>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox checked={allSelected ? true : someSelected ? 'indeterminate' : false} onCheckedChange={onSelectAll} />
              </TableHead>
              <TableHead>Year</TableHead>
              <TableHead>Month</TableHead>
              <TableHead>Employee</TableHead>
              <TableHead>Department</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Brand</TableHead>
              <TableHead>Event</TableHead>
              <TableHead className="text-right">Days</TableHead>
              <TableHead className="text-right">Hours</TableHead>
              {canViewAmounts && <TableHead className="text-right">Bonus (Net)</TableHead>}
              <TableHead>Details</TableHead>
              <TableHead className="w-28">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {bonuses.map((b) => (
              <TableRow key={b.id} className={cn(selectedIds.includes(b.id) && 'bg-muted/50')}>
                <TableCell>
                  <Checkbox checked={selectedIds.includes(b.id)} onCheckedChange={() => onToggleSelect(b.id)} />
                </TableCell>
                <TableCell className="text-sm">{b.year}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-xs">{MONTH_SHORT[b.month] || b.month}</Badge>
                </TableCell>
                <TableCell className="text-sm font-medium">{b.employee_name}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{b.department ?? '—'}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{b.company ?? '—'}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{b.brand ?? '—'}</TableCell>
                <TableCell className="text-sm">{b.event_name}</TableCell>
                <TableCell className="text-right text-sm">{b.bonus_days ?? '—'}</TableCell>
                <TableCell className="text-right text-sm">{b.hours_free ?? '—'}</TableCell>
                {canViewAmounts && (
                  <TableCell className="text-right text-sm font-medium">
                    {b.bonus_net != null ? `${Number(b.bonus_net).toFixed(0)} RON` : '—'}
                  </TableCell>
                )}
                <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">{b.details ?? ''}</TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onEdit(b)} title="Edit">
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onDuplicate(b)} title="Duplicate">
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => onDelete(b.id)} title="Delete">
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="border-t px-4 py-2 text-xs text-muted-foreground">
        {bonuses.length} bonus(es)
      </div>
    </Card>
  )
}

/* ──── Expanded row: employee's events ──── */

function EmployeeEventsDetail({ employeeId, year, month, canViewAmounts }: {
  employeeId: number; year?: number; month?: number; canViewAmounts: boolean
}) {
  const { data: bonuses = [], isLoading } = useQuery({
    queryKey: ['hr-employee-bonuses', employeeId, year, month],
    queryFn: () => hrApi.getBonuses({ employee_id: employeeId, year, month }),
  })

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Loading events...</div>
  if (bonuses.length === 0) return <div className="p-4 text-sm text-muted-foreground">No events found.</div>

  return (
    <div className="px-6 py-4 space-y-3 bg-muted/30">
      <p className="text-sm font-medium flex items-center gap-1.5">
        <CalendarDays className="h-4 w-4" /> Events ({bonuses.length})
      </p>
      <div className="rounded-md border bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Event</TableHead>
              <TableHead>Year</TableHead>
              <TableHead>Month</TableHead>
              <TableHead>Period</TableHead>
              <TableHead className="text-right">Days</TableHead>
              <TableHead className="text-right">Hours</TableHead>
              {canViewAmounts && <TableHead className="text-right">Bonus (Net)</TableHead>}
              <TableHead>Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {bonuses.map((b) => (
              <TableRow key={b.id}>
                <TableCell className="text-sm font-medium">{b.event_name}</TableCell>
                <TableCell className="text-sm">{b.year}</TableCell>
                <TableCell><Badge variant="outline" className="text-xs">{MONTH_SHORT[b.month] || b.month}</Badge></TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {b.participation_start && b.participation_end
                    ? `${new Date(b.participation_start).toLocaleDateString('ro-RO')} — ${new Date(b.participation_end).toLocaleDateString('ro-RO')}`
                    : '—'}
                </TableCell>
                <TableCell className="text-right text-sm">{b.bonus_days ?? '—'}</TableCell>
                <TableCell className="text-right text-sm">{b.hours_free ?? '—'}</TableCell>
                {canViewAmounts && (
                  <TableCell className="text-right text-sm font-medium text-green-600">
                    {b.bonus_net != null ? `${Number(b.bonus_net).toFixed(0)} RON` : '—'}
                  </TableCell>
                )}
                <TableCell className="text-xs text-muted-foreground max-w-[150px] truncate">{b.details ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

/* ──── By Employee Table ──── */

function ByEmployeeTable({ data, canViewAmounts, isMobile }: { data: BonusSummaryByEmployee[]; canViewAmounts: boolean; isMobile: boolean }) {
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const filters = useHrStore((s) => s.filters)

  const mobileFields: MobileCardField<BonusSummaryByEmployee>[] = useMemo(() => [
    {
      key: 'name',
      label: 'Employee',
      isPrimary: true,
      render: (row) => row.name,
    },
    {
      key: 'company',
      label: 'Company',
      isSecondary: true,
      render: (row) => (
        <span className="flex items-center gap-1.5">
          {row.company ?? '—'}
          {row.department ? <span className="text-muted-foreground">/ {row.department}</span> : null}
        </span>
      ),
    },
    {
      key: 'bonus_count',
      label: '# Bonuses',
      render: (row) => <Badge variant="secondary" className="text-xs">{row.bonus_count}</Badge>,
    },
    {
      key: 'total_days',
      label: 'Total Days',
      render: (row) => <span className="text-xs">{row.total_days}</span>,
    },
    {
      key: 'total_hours',
      label: 'Total Hours',
      render: (row) => <span className="text-xs">{row.total_hours}</span>,
    },
    ...(canViewAmounts ? [{
      key: 'total_bonus',
      label: 'Total Bonus',
      render: (row: BonusSummaryByEmployee) => (
        <span className="text-xs font-medium text-green-600">{Number(row.total_bonus).toFixed(0)} RON</span>
      ),
    }] : []),
    {
      key: 'brand',
      label: 'Brand',
      expandOnly: true,
      render: (row) => <span className="text-xs text-muted-foreground">{row.brand ?? '—'}</span>,
    },
  ] as MobileCardField<BonusSummaryByEmployee>[], [canViewAmounts])

  if (data.length === 0) return <EmptyState icon={<Users className="h-8 w-8" />} title="No data" description="Adjust filters." />

  if (isMobile) {
    return (
      <>
        <MobileCardList
          data={data}
          fields={mobileFields}
          getRowId={(row) => row.id}
        />
        <div className="rounded-md border bg-muted/50 px-3 py-2 text-xs font-medium">
          Total ({data.length}) — {data.reduce((s, r) => s + r.bonus_count, 0)} bonuses, {data.reduce((s, r) => s + r.total_days, 0)} days, {data.reduce((s, r) => s + r.total_hours, 0)} hours
          {canViewAmounts && `, ${data.reduce((s, r) => s + Number(r.total_bonus), 0).toFixed(0)} RON`}
        </div>
      </>
    )
  }

  const colCount = canViewAmounts ? 9 : 8

  return (
    <Card>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>Employee</TableHead>
              <TableHead>Department</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Brand</TableHead>
              <TableHead className="text-right"># Bonuses</TableHead>
              <TableHead className="text-right">Total Days</TableHead>
              <TableHead className="text-right">Total Hours</TableHead>
              {canViewAmounts && <TableHead className="text-right">Total Bonus</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row) => (
              <>
                <TableRow
                  key={row.id}
                  className="cursor-pointer"
                  onClick={() => setExpandedRow(expandedRow === row.id ? null : row.id)}
                >
                  <TableCell className="w-8 px-2">
                    <ChevronRight className={cn('h-4 w-4 transition-transform', expandedRow === row.id ? 'rotate-90' : '')} />
                  </TableCell>
                  <TableCell className="text-sm font-medium">{row.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{row.department ?? '—'}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{row.company ?? '—'}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{row.brand ?? '—'}</TableCell>
                  <TableCell className="text-right text-sm">{row.bonus_count}</TableCell>
                  <TableCell className="text-right text-sm">{row.total_days}</TableCell>
                  <TableCell className="text-right text-sm">{row.total_hours}</TableCell>
                  {canViewAmounts && (
                    <TableCell className="text-right text-sm font-medium text-green-600">
                      {Number(row.total_bonus).toFixed(0)} RON
                    </TableCell>
                  )}
                </TableRow>
                {expandedRow === row.id && (
                  <TableRow key={`${row.id}-detail`}>
                    <TableCell colSpan={colCount} className="p-0">
                      <EmployeeEventsDetail
                        employeeId={row.id}
                        year={filters.year}
                        month={filters.month}
                        canViewAmounts={canViewAmounts}
                      />
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
            {/* Footer totals */}
            <TableRow className="bg-muted/50 font-medium">
              <TableCell />
              <TableCell className="text-sm">Total ({data.length})</TableCell>
              <TableCell />
              <TableCell />
              <TableCell />
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.bonus_count, 0)}</TableCell>
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.total_days, 0)}</TableCell>
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.total_hours, 0)}</TableCell>
              {canViewAmounts && (
                <TableCell className="text-right text-sm text-green-600">
                  {data.reduce((s, r) => s + Number(r.total_bonus), 0).toFixed(0)} RON
                </TableCell>
              )}
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </Card>
  )
}

/* ──── By Event Table ──── */

function ByEventTable({ data, canViewAmounts, isMobile }: { data: BonusSummaryByEvent[]; canViewAmounts: boolean; isMobile: boolean }) {
  const mobileFields: MobileCardField<BonusSummaryByEvent>[] = useMemo(() => [
    {
      key: 'name',
      label: 'Event',
      isPrimary: true,
      render: (row) => row.name,
    },
    {
      key: 'period',
      label: 'Period',
      isSecondary: true,
      render: (row) => (
        <span className="flex items-center gap-1.5">
          <Badge variant="outline" className="text-[10px]">{MONTH_SHORT[row.month] || row.month} {row.year}</Badge>
          <span>{row.start_date} — {row.end_date}</span>
        </span>
      ),
    },
    {
      key: 'employees',
      label: '# Employees',
      render: (row) => <Badge variant="secondary" className="text-xs">{row.employee_count}</Badge>,
    },
    {
      key: 'total_days',
      label: 'Total Days',
      render: (row) => <span className="text-xs">{row.total_days}</span>,
    },
    {
      key: 'total_hours',
      label: 'Total Hours',
      render: (row) => <span className="text-xs">{row.total_hours}</span>,
    },
    ...(canViewAmounts ? [{
      key: 'total_bonus',
      label: 'Total Bonus',
      render: (row: BonusSummaryByEvent) => (
        <span className="text-xs font-medium text-green-600">{Number(row.total_bonus).toFixed(0)} RON</span>
      ),
    }] : []),
    {
      key: 'company',
      label: 'Company',
      expandOnly: true,
      render: (row) => <span className="text-xs text-muted-foreground">{row.company ?? '—'}</span>,
    },
  ] as MobileCardField<BonusSummaryByEvent>[], [canViewAmounts])

  if (data.length === 0) return <EmptyState icon={<CalendarDays className="h-8 w-8" />} title="No data" description="Adjust filters." />

  if (isMobile) {
    return (
      <>
        <MobileCardList
          data={data}
          fields={mobileFields}
          getRowId={(row) => row.id * 10000 + row.year * 100 + row.month}
        />
        <div className="rounded-md border bg-muted/50 px-3 py-2 text-xs font-medium">
          Total ({data.length}) — {data.reduce((s, r) => s + r.employee_count, 0)} employees, {data.reduce((s, r) => s + r.total_days, 0)} days, {data.reduce((s, r) => s + r.total_hours, 0)} hours
          {canViewAmounts && `, ${data.reduce((s, r) => s + Number(r.total_bonus), 0).toFixed(0)} RON`}
        </div>
      </>
    )
  }

  return (
    <Card>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Year</TableHead>
              <TableHead>Month</TableHead>
              <TableHead>Event</TableHead>
              <TableHead>Date Range</TableHead>
              <TableHead>Company</TableHead>
              <TableHead className="text-right"># Employees</TableHead>
              <TableHead className="text-right">Total Days</TableHead>
              <TableHead className="text-right">Total Hours</TableHead>
              {canViewAmounts && <TableHead className="text-right">Total Bonus</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row, i) => (
              <TableRow key={`${row.id}-${row.year}-${row.month}-${i}`}>
                <TableCell className="text-sm">{row.year}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-xs">{MONTH_SHORT[row.month] || row.month}</Badge>
                </TableCell>
                <TableCell className="text-sm font-medium">{row.name}</TableCell>
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {row.start_date} — {row.end_date}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{row.company ?? '—'}</TableCell>
                <TableCell className="text-right text-sm">{row.employee_count}</TableCell>
                <TableCell className="text-right text-sm">{row.total_days}</TableCell>
                <TableCell className="text-right text-sm">{row.total_hours}</TableCell>
                {canViewAmounts && (
                  <TableCell className="text-right text-sm font-medium text-green-600">
                    {Number(row.total_bonus).toFixed(0)} RON
                  </TableCell>
                )}
              </TableRow>
            ))}
            <TableRow className="bg-muted/50 font-medium">
              <TableCell className="text-sm">Total ({data.length})</TableCell>
              <TableCell />
              <TableCell />
              <TableCell />
              <TableCell />
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.employee_count, 0)}</TableCell>
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.total_days, 0)}</TableCell>
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.total_hours, 0)}</TableCell>
              {canViewAmounts && (
                <TableCell className="text-right text-sm text-green-600">
                  {data.reduce((s, r) => s + Number(r.total_bonus), 0).toFixed(0)} RON
                </TableCell>
              )}
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </Card>
  )
}

/* ──── Add/Edit Bonus Dialog ──── */

function BonusDialog({
  open, bonus, isDuplicate, events, employees, onClose,
}: {
  open: boolean
  bonus: EventBonus | null
  isDuplicate?: boolean
  events: { id: number; name: string; start_date?: string; end_date?: string }[]
  employees: { id: number; name: string; company?: string | null }[]
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const isEdit = !!bonus && !isDuplicate

  const { data: bonusTypes = [] } = useQuery({
    queryKey: ['hr-bonus-types-active'],
    queryFn: () => hrApi.getBonusTypes(true),
    enabled: open,
  })

  const [employeeId, setEmployeeId] = useState('')
  const [eventId, setEventId] = useState('')
  const [year, setYear] = useState(String(new Date().getFullYear()))
  const [month, setMonth] = useState(String(new Date().getMonth() + 1))
  const [partStart, setPartStart] = useState('')
  const [partEnd, setPartEnd] = useState('')
  const [bonusTypeId, setBonusTypeId] = useState('')
  const [bonusDays, setBonusDays] = useState('')
  const [hoursFree, setHoursFree] = useState('')
  const [details, setDetails] = useState('')

  const selectedEvent = events.find((e) => String(e.id) === eventId)
  const maxBonusDays = selectedEvent?.start_date && selectedEvent?.end_date
    ? Math.max(1, Math.round((new Date(selectedEvent.end_date).getTime() - new Date(selectedEvent.start_date).getTime()) / 86400000) + 1)
    : 31

  // Sync form state when dialog opens or bonus changes
  useEffect(() => {
    if (!open) return
    if (bonus) {
      setEmployeeId(String(bonus.user_id))
      setEventId(String(bonus.event_id))
      setYear(String(bonus.year))
      setMonth(String(bonus.month))
      setPartStart(bonus.participation_start ?? '')
      setPartEnd(bonus.participation_end ?? '')
      setBonusTypeId((bonus as any).bonus_type_id != null ? String((bonus as any).bonus_type_id) : '')
      setBonusDays(bonus.bonus_days != null ? String(bonus.bonus_days) : '')
      setHoursFree(bonus.hours_free != null ? String(bonus.hours_free) : '')
      setDetails(bonus.details ?? '')
    } else {
      setEmployeeId('')
      setEventId('')
      setYear(String(new Date().getFullYear()))
      setMonth(String(new Date().getMonth() + 1))
      setPartStart('')
      setPartEnd('')
      setBonusTypeId('')
      setBonusDays('')
      setHoursFree('')
      setDetails('')
    }
  }, [open, bonus])

  const createMutation = useMutation({
    mutationFn: (data: Partial<EventBonus>) => hrApi.createBonus(data),
    onSuccess: () => {
      toast.success('Bonus created')
      queryClient.invalidateQueries({ queryKey: ['hr-bonuses'] })
      queryClient.invalidateQueries({ queryKey: ['hr-summary'] })
      onClose()
    },
    onError: () => toast.error('Failed to create bonus'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<EventBonus> }) => hrApi.updateBonus(id, data),
    onSuccess: () => {
      toast.success('Bonus updated')
      queryClient.invalidateQueries({ queryKey: ['hr-bonuses'] })
      queryClient.invalidateQueries({ queryKey: ['hr-summary'] })
      onClose()
    },
    onError: () => toast.error('Failed to update bonus'),
  })

  const handleSave = () => {
    if (!employeeId || !eventId) return toast.error('Employee and event are required')
    if ((parseFloat(bonusDays) || 0) > maxBonusDays) return toast.error(`Bonus days cannot exceed ${maxBonusDays}`)
    if ((parseFloat(hoursFree) || 0) > maxBonusDays * 8) return toast.error(`Hours free cannot exceed ${maxBonusDays * 8}`)
    // Auto-compute bonus_net from type + days
    const type = bonusTypes.find((t) => String(t.id) === bonusTypeId)
    const d = parseFloat(bonusDays) || 0
    const computedNet = type && d > 0 ? Math.round((type.amount / (type.days_per_amount ?? 1)) * d) : null
    const data: Record<string, any> = {
      employee_id: Number(employeeId),
      event_id: Number(eventId),
      year: Number(year),
      month: Number(month),
      participation_start: partStart || null,
      participation_end: partEnd || null,
      bonus_days: bonusDays ? Number(bonusDays) : null,
      hours_free: hoursFree ? Number(hoursFree) : null,
      bonus_net: computedNet,
      details: details || null,
    }
    if (bonusTypeId) data.bonus_type_id = Number(bonusTypeId)
    if (isEdit && bonus) {
      updateMutation.mutate({ id: bonus.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="sm:max-w-lg" onOpenAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Bonus' : isDuplicate ? 'Duplicate Bonus' : 'Add Bonus'}</DialogTitle>
          <DialogDescription>
            {isEdit ? 'Update bonus record.' : isDuplicate ? 'Create a copy of the bonus.' : 'Create a new bonus entry.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Employee *</Label>
              <SearchSelect
                value={employeeId}
                onValueChange={setEmployeeId}
                options={employees.map((e) => ({ value: String(e.id), label: e.name, sublabel: e.company ?? undefined }))}
                placeholder="Select employee..."
                searchPlaceholder="Search employee..."
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Event *</Label>
              <SearchSelect
                value={eventId}
                onValueChange={(v) => {
                  setEventId(v)
                  const ev = events.find((e) => String(e.id) === v)
                  if (ev?.start_date) {
                    setPartStart(ev.start_date)
                    const d = new Date(ev.start_date)
                    setYear(String(d.getFullYear()))
                    setMonth(String(d.getMonth() + 1))
                  }
                  if (ev?.end_date) setPartEnd(ev.end_date)
                }}
                options={events.map((ev) => ({ value: String(ev.id), label: ev.name }))}
                placeholder="Select event..."
                searchPlaceholder="Search event..."
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Participation Start</Label>
              <Input type="date" value={partStart} onChange={(e) => setPartStart(e.target.value)} min={selectedEvent?.start_date} max={selectedEvent?.end_date} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Participation End</Label>
              <Input type="date" value={partEnd} onChange={(e) => setPartEnd(e.target.value)} min={selectedEvent?.start_date} max={selectedEvent?.end_date} />
            </div>
          </div>

          {bonusTypes.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs">Bonus Type</Label>
              <Select
                value={bonusTypeId || '__none__'}
                onValueChange={(v) => {
                  setBonusTypeId(v === '__none__' ? '' : v)
                }}
              >
                <SelectTrigger><SelectValue placeholder="Select type..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— Manual —</SelectItem>
                  {bonusTypes.map((bt) => (
                    <SelectItem key={bt.id} value={String(bt.id)}>
                      {bt.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Bonus Days{selectedEvent ? ` (max ${maxBonusDays})` : ''}</Label>
              <Input
                type="number"
                step="0.5"
                min={0}
                max={maxBonusDays}
                value={bonusDays}
                onChange={(e) => setBonusDays(e.target.value)}
                className={cn((parseFloat(bonusDays) || 0) > maxBonusDays && 'border-destructive ring-destructive')}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Hours Free{selectedEvent ? ` (max ${maxBonusDays * 8})` : ''}</Label>
              <Input
                type="number"
                min={0}
                max={maxBonusDays * 8}
                value={hoursFree}
                onChange={(e) => setHoursFree(e.target.value)}
                className={cn((parseFloat(hoursFree) || 0) > maxBonusDays * 8 && 'border-destructive ring-destructive')}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Details</Label>
            <Input value={details} onChange={(e) => setDetails(e.target.value)} placeholder="Notes..." />
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={createMutation.isPending || updateMutation.isPending}>
            {isEdit ? 'Update' : isDuplicate ? 'Duplicate' : 'Create'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
