import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Trash2,
  Pencil,
  Search,
  Users,
  CalendarDays,
  Lock,
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
import { EmptyState } from '@/components/shared/EmptyState'
import { hrApi } from '@/api/hr'
import { useHrStore } from '@/stores/hrStore'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { EventBonus, BonusSummaryByEmployee, BonusSummaryByEvent } from '@/types/hr'

const MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const MONTH_SHORT = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export default function BonusesTab({ canViewAmounts }: { canViewAmounts: boolean }) {
  const queryClient = useQueryClient()
  const filters = useHrStore((s) => s.filters)
  const updateFilter = useHrStore((s) => s.updateFilter)
  const selectedBonusIds = useHrStore((s) => s.selectedBonusIds)
  const setSelectedBonusIds = useHrStore((s) => s.setSelectedBonusIds)
  const toggleBonusSelected = useHrStore((s) => s.toggleBonusSelected)
  const clearSelected = useHrStore((s) => s.clearSelected)
  const [subTab, setSubTab] = useState<'list' | 'by-employee' | 'by-event'>('list')
  const [search, setSearch] = useState('')
  const [editBonus, setEditBonus] = useState<EventBonus | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [deleteIds, setDeleteIds] = useState<number[] | null>(null)

  // Data
  const { data: bonuses = [], isLoading } = useQuery({
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
        <Select value={String(filters.year ?? '')} onValueChange={(v) => updateFilter('year', v ? Number(v) : undefined)}>
          <SelectTrigger className="w-24">
            <SelectValue placeholder="Year" />
          </SelectTrigger>
          <SelectContent>
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
      {subTab === 'list' && (
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
          onEdit={(b) => { setEditBonus(b); setAddOpen(true) }}
          onDelete={(id) => setDeleteIds([id])}
          canViewAmounts={canViewAmounts}
        />
      )}

      {subTab === 'by-employee' && (
        <ByEmployeeTable data={byEmployee} canViewAmounts={canViewAmounts} />
      )}

      {subTab === 'by-event' && (
        <ByEventTable data={byEvent} canViewAmounts={canViewAmounts} />
      )}

      {/* Add/Edit Bonus Dialog */}
      <BonusDialog
        open={addOpen}
        bonus={editBonus}
        events={events}
        employees={employees}
        onClose={() => { setAddOpen(false); setEditBonus(null) }}
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
  onToggleSelect, onSelectAll, onEdit, onDelete, canViewAmounts,
}: {
  bonuses: EventBonus[]
  isLoading: boolean
  selectedIds: number[]
  allSelected: boolean
  someSelected: boolean
  onToggleSelect: (id: number) => void
  onSelectAll: () => void
  onEdit: (b: EventBonus) => void
  onDelete: (id: number) => void
  canViewAmounts: boolean
}) {
  if (isLoading) {
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
              <TableHead>Event</TableHead>
              <TableHead className="text-right">Days</TableHead>
              <TableHead className="text-right">Hours</TableHead>
              {canViewAmounts && <TableHead className="text-right">Bonus (Net)</TableHead>}
              <TableHead>Details</TableHead>
              <TableHead className="w-20">Actions</TableHead>
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
                <TableCell className="text-sm">{b.event_name}</TableCell>
                <TableCell className="text-right text-sm">{b.bonus_days ?? '—'}</TableCell>
                <TableCell className="text-right text-sm">{b.hours_free ?? '—'}</TableCell>
                {canViewAmounts && (
                  <TableCell className="text-right text-sm font-medium">
                    {b.bonus_net != null ? `${b.bonus_net.toFixed(0)} RON` : '—'}
                  </TableCell>
                )}
                <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">{b.details ?? ''}</TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onEdit(b)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => onDelete(b.id)}>
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

/* ──── By Employee Table ──── */

function ByEmployeeTable({ data, canViewAmounts }: { data: BonusSummaryByEmployee[]; canViewAmounts: boolean }) {
  if (data.length === 0) return <EmptyState icon={<Users className="h-8 w-8" />} title="No data" description="Adjust filters." />

  return (
    <Card>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
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
              <TableRow key={row.id}>
                <TableCell className="text-sm font-medium">{row.name}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{row.department ?? '—'}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{row.company ?? '—'}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{row.brand ?? '—'}</TableCell>
                <TableCell className="text-right text-sm">{row.bonus_count}</TableCell>
                <TableCell className="text-right text-sm">{row.total_days}</TableCell>
                <TableCell className="text-right text-sm">{row.total_hours}</TableCell>
                {canViewAmounts && (
                  <TableCell className="text-right text-sm font-medium text-green-600">
                    {row.total_bonus.toFixed(0)} RON
                  </TableCell>
                )}
              </TableRow>
            ))}
            {/* Footer totals */}
            <TableRow className="bg-muted/50 font-medium">
              <TableCell className="text-sm">Total ({data.length})</TableCell>
              <TableCell />
              <TableCell />
              <TableCell />
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.bonus_count, 0)}</TableCell>
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.total_days, 0)}</TableCell>
              <TableCell className="text-right text-sm">{data.reduce((s, r) => s + r.total_hours, 0)}</TableCell>
              {canViewAmounts && (
                <TableCell className="text-right text-sm text-green-600">
                  {data.reduce((s, r) => s + r.total_bonus, 0).toFixed(0)} RON
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

function ByEventTable({ data, canViewAmounts }: { data: BonusSummaryByEvent[]; canViewAmounts: boolean }) {
  if (data.length === 0) return <EmptyState icon={<CalendarDays className="h-8 w-8" />} title="No data" description="Adjust filters." />

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
                    {row.total_bonus.toFixed(0)} RON
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
                  {data.reduce((s, r) => s + r.total_bonus, 0).toFixed(0)} RON
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
  open, bonus, events, employees, onClose,
}: {
  open: boolean
  bonus: EventBonus | null
  events: { id: number; name: string }[]
  employees: { id: number; name: string; company?: string | null }[]
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const isEdit = !!bonus

  const [employeeId, setEmployeeId] = useState('')
  const [eventId, setEventId] = useState('')
  const [year, setYear] = useState(String(new Date().getFullYear()))
  const [month, setMonth] = useState(String(new Date().getMonth() + 1))
  const [partStart, setPartStart] = useState('')
  const [partEnd, setPartEnd] = useState('')
  const [bonusDays, setBonusDays] = useState('')
  const [hoursFree, setHoursFree] = useState('')
  const [bonusNet, setBonusNet] = useState('')
  const [details, setDetails] = useState('')

  // Load values when bonus changes
  const resetForm = () => {
    if (bonus) {
      setEmployeeId(String(bonus.employee_id))
      setEventId(String(bonus.event_id))
      setYear(String(bonus.year))
      setMonth(String(bonus.month))
      setPartStart(bonus.participation_start ?? '')
      setPartEnd(bonus.participation_end ?? '')
      setBonusDays(bonus.bonus_days != null ? String(bonus.bonus_days) : '')
      setHoursFree(bonus.hours_free != null ? String(bonus.hours_free) : '')
      setBonusNet(bonus.bonus_net != null ? String(bonus.bonus_net) : '')
      setDetails(bonus.details ?? '')
    } else {
      setEmployeeId('')
      setEventId('')
      setYear(String(new Date().getFullYear()))
      setMonth(String(new Date().getMonth() + 1))
      setPartStart('')
      setPartEnd('')
      setBonusDays('')
      setHoursFree('')
      setBonusNet('')
      setDetails('')
    }
  }

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
    const data: Partial<EventBonus> = {
      employee_id: Number(employeeId),
      event_id: Number(eventId),
      year: Number(year),
      month: Number(month),
      participation_start: partStart || null,
      participation_end: partEnd || null,
      bonus_days: bonusDays ? Number(bonusDays) : null,
      hours_free: hoursFree ? Number(hoursFree) : null,
      bonus_net: bonusNet ? Number(bonusNet) : null,
      details: details || null,
    }
    if (isEdit && bonus) {
      updateMutation.mutate({ id: bonus.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-lg" onOpenAutoFocus={(e) => { e.preventDefault(); resetForm() }}>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Bonus' : 'Add Bonus'}</DialogTitle>
          <DialogDescription>
            {isEdit ? 'Update bonus record.' : 'Create a new bonus entry.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Employee *</Label>
              <Select value={employeeId} onValueChange={setEmployeeId}>
                <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                <SelectContent>
                  {employees.map((e) => (
                    <SelectItem key={e.id} value={String(e.id)}>
                      {e.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Event *</Label>
              <Select value={eventId} onValueChange={setEventId}>
                <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                <SelectContent>
                  {events.map((ev) => (
                    <SelectItem key={ev.id} value={String(ev.id)}>
                      {ev.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Year</Label>
              <Input type="number" min={2020} max={2030} value={year} onChange={(e) => setYear(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Month</Label>
              <Select value={month} onValueChange={setMonth}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {MONTHS.slice(1).map((m, i) => (
                    <SelectItem key={i + 1} value={String(i + 1)}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Participation Start</Label>
              <Input type="date" value={partStart} onChange={(e) => setPartStart(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Participation End</Label>
              <Input type="date" value={partEnd} onChange={(e) => setPartEnd(e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Bonus Days</Label>
              <Input type="number" step="0.5" min={0} max={31} value={bonusDays} onChange={(e) => setBonusDays(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Hours Free</Label>
              <Input type="number" min={0} max={100} value={hoursFree} onChange={(e) => setHoursFree(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Bonus Net (RON)</Label>
              <Input type="number" step="0.01" value={bonusNet} onChange={(e) => setBonusNet(e.target.value)} />
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
            {isEdit ? 'Update' : 'Create'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
