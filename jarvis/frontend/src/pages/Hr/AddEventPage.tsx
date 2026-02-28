import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  Plus,
  Trash2,
  Search,
  Loader2,
  Users,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { hrApi } from '@/api/hr'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useFormValidation } from '@/hooks/useFormValidation'
import { FieldError } from '@/components/shared/FieldError'
import type { HrEmployee } from '@/types/hr'

interface EmployeeRow {
  employee: HrEmployee
  partStart: string
  partEnd: string
  bonusDays: string
  hoursFree: string
  bonusTypeId: string
  bonusNet: number | null
}

const MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

export default function AddEventPage() {
  const navigate = useNavigate()

  // Event fields
  const [name, setName] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [company, setCompany] = useState('')
  const [brand, setBrand] = useState('')
  const [description, setDescription] = useState('')
  const [year, setYear] = useState(String(new Date().getFullYear()))
  const [month, setMonth] = useState(String(new Date().getMonth() + 1))

  // Inline validation
  const v = useFormValidation(
    { name, startDate, endDate },
    {
      name: (val) => (!val.trim() ? 'Event name is required' : undefined),
      startDate: (val) => (!val ? 'Start date is required' : undefined),
      endDate: (val) => (!val ? 'End date is required' : undefined),
    },
  )

  // Employees
  const [rows, setRows] = useState<EmployeeRow[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<HrEmployee[]>([])
  const [searching, setSearching] = useState(false)

  // Permissions
  const { data: permissions } = useQuery({
    queryKey: ['hr-permissions'],
    queryFn: () => hrApi.getPermissions(),
    staleTime: 5 * 60 * 1000,
  })
  const canViewAmounts = permissions?.permissions?.['hr.bonuses.view_amounts']?.allowed ?? false

  // Queries
  const { data: companies = [] } = useQuery({
    queryKey: ['hr-structure-companies'],
    queryFn: () => hrApi.getStructureCompanies(),
  })

  const { data: brands = [] } = useQuery({
    queryKey: ['hr-structure-brands', company],
    queryFn: () => hrApi.getStructureBrands(company),
    enabled: !!company,
  })

  const { data: bonusTypes = [] } = useQuery({
    queryKey: ['hr-bonus-types-active'],
    queryFn: () => hrApi.getBonusTypes(true),
  })

  // Employee search
  const handleSearch = async (q: string) => {
    setSearchQuery(q)
    if (q.length < 2) {
      setSearchResults([])
      return
    }
    setSearching(true)
    try {
      const results = await hrApi.searchEmployees(q)
      const selectedIds = new Set(rows.map((r) => r.employee.id))
      setSearchResults(results.filter((e) => !selectedIds.has(e.id)))
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const addEmployee = (emp: HrEmployee) => {
    const defaultType = bonusTypes[0]
    setRows((prev) => [
      ...prev,
      {
        employee: emp,
        partStart: startDate,
        partEnd: endDate,
        bonusDays: '1',
        hoursFree: '6',
        bonusTypeId: defaultType ? String(defaultType.id) : '',
        bonusNet: defaultType ? defaultType.amount / (defaultType.days_per_amount ?? 1) : null,
      },
    ])
    setSearchQuery('')
    setSearchResults([])
  }

  const removeEmployee = (idx: number) => {
    setRows((prev) => prev.filter((_, i) => i !== idx))
  }

  const updateRow = (idx: number, updates: Partial<EmployeeRow>) => {
    setRows((prev) =>
      prev.map((r, i) => {
        if (i !== idx) return r
        const updated = { ...r, ...updates }
        // Recalculate bonus if type or days changed
        if ('bonusTypeId' in updates || 'bonusDays' in updates) {
          const type = bonusTypes.find((t) => String(t.id) === updated.bonusTypeId)
          const days = parseFloat(updated.bonusDays) || 0
          if (type && days > 0) {
            updated.bonusNet = (type.amount / (type.days_per_amount ?? 1)) * days
          } else {
            updated.bonusNet = null
          }
        }
        return updated
      }),
    )
  }

  const maxBonusDays = startDate && endDate
    ? Math.max(1, Math.round((new Date(endDate).getTime() - new Date(startDate).getTime()) / 86400000) + 1)
    : 31

  // Summary
  const totalDays = useMemo(() => rows.reduce((s, r) => s + (parseFloat(r.bonusDays) || 0), 0), [rows])
  const totalBonus = useMemo(() => rows.reduce((s, r) => s + (r.bonusNet ?? 0), 0), [rows])

  // Submit
  const createEventMutation = useMutation({
    mutationFn: async () => {
      // Create event
      const eventRes = await hrApi.createEvent({
        name: name.trim(),
        start_date: startDate,
        end_date: endDate,
        company: company || null,
        brand: brand || null,
        description: description || null,
      })

      if (!eventRes.id) throw new Error('Event creation failed')

      // Create bonuses
      const bonuses = rows
        .filter((r) => parseFloat(r.bonusDays) > 0)
        .map((r) => ({
          employee_id: r.employee.id,
          event_id: eventRes.id,
          year: Number(year),
          month: Number(month),
          participation_start: r.partStart || null,
          participation_end: r.partEnd || null,
          bonus_days: parseFloat(r.bonusDays) || null,
          hours_free: parseFloat(r.hoursFree) || null,
          bonus_net: r.bonusNet,
        }))

      if (bonuses.length > 0) {
        await hrApi.bulkCreateBonuses(bonuses)
      }

      return eventRes
    },
    onSuccess: () => {
      toast.success('Event and bonuses created')
      navigate('/app/hr/events')
    },
    onError: () => toast.error('Failed to create event'),
  })

  const handleSubmit = () => {
    v.touchAll()
    if (!v.isValid) return toast.error('Please fix the highlighted fields')
    if (rows.length === 0) return toast.error('Add at least one employee')
    if (rows.some((r) => (parseFloat(r.bonusDays) || 0) > maxBonusDays))
      return toast.error(`Bonus days cannot exceed ${maxBonusDays} (event duration)`)
    if (rows.some((r) => (parseFloat(r.hoursFree) || 0) > maxBonusDays * 8))
      return toast.error(`Hours free cannot exceed ${maxBonusDays * 8} (${maxBonusDays} days x 8h)`)
    createEventMutation.mutate()
  }

  const onFormSubmit = (e: React.FormEvent) => { e.preventDefault(); handleSubmit() }

  return (
    <form onSubmit={onFormSubmit} className="space-y-4">
      <PageHeader
        title="Add Event + Employees"
        description=""
        breadcrumbs={[
          { label: 'HR', href: '/app/hr/pontaje' },
          { label: 'Events', href: '/app/hr/events' },
          { label: 'Add Event' },
        ]}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* LEFT: Event Details */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Event Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                <Label className="text-xs">Event Name *</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} onBlur={() => v.touch('name')} className={cn(v.error('name') && 'border-destructive')} placeholder="e.g., Toyota Family Day" />
                <FieldError message={v.error('name')} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Start Date *</Label>
                  <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} onBlur={() => v.touch('startDate')} className={cn(v.error('startDate') && 'border-destructive')} />
                  <FieldError message={v.error('startDate')} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">End Date *</Label>
                  <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} onBlur={() => v.touch('endDate')} className={cn(v.error('endDate') && 'border-destructive')} />
                  <FieldError message={v.error('endDate')} />
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
                  <Label className="text-xs">Company</Label>
                  <Select value={company || '__none__'} onValueChange={(v) => { setCompany(v === '__none__' ? '' : v); setBrand('') }}>
                    <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      {(companies as string[]).map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Brand</Label>
                  <Select value={brand || '__none__'} onValueChange={(v) => setBrand(v === '__none__' ? '' : v)} disabled={!company}>
                    <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      {(brands as string[]).map((b) => (
                        <SelectItem key={b} value={b}>{b}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Description</Label>
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* RIGHT: Employee Assignment */}
        <div className="lg:col-span-3">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-sm">Assign Employees</CardTitle>
              <span className="text-xs text-muted-foreground">{rows.length} employees</span>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-8"
                  placeholder="Search employees by name..."
                  value={searchQuery}
                  onChange={(e) => handleSearch(e.target.value)}
                />
                {searchResults.length > 0 && (
                  <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-lg max-h-48 overflow-y-auto">
                    {searchResults.map((emp) => (
                      <button
                        key={emp.id}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent text-sm"
                        onClick={() => addEmployee(emp)}
                      >
                        <Plus className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <div>
                          <div className="font-medium">{emp.name}</div>
                          <div className="text-xs text-muted-foreground">{emp.company ?? ''} {emp.departments ? `— ${emp.departments}` : ''}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
                {searching && <div className="absolute right-3 top-2.5"><Loader2 className="h-4 w-4 animate-spin" /></div>}
              </div>

              {/* Employee rows */}
              {rows.length === 0 ? (
                <EmptyState icon={<Users className="h-8 w-8" />} title="No employees added" description="Search and add employees above." />
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {/* Header */}
                  <div className="grid grid-cols-12 gap-1.5 text-xs font-medium text-muted-foreground px-1 sticky top-0 bg-background pb-1">
                    <div className="col-span-3">Employee</div>
                    <div className="col-span-2">Part. Start</div>
                    <div className="col-span-2">Part. End</div>
                    <div className="col-span-1">Days</div>
                    <div className="col-span-1">Hours</div>
                    <div className="col-span-2">Bonus Type</div>
                    <div className="col-span-1"></div>
                  </div>

                  {rows.map((row, idx) => (
                    <div key={row.employee.id} className="grid grid-cols-12 gap-1.5 items-center rounded-lg border p-1.5">
                      <div className="col-span-3">
                        <div className="text-sm font-medium truncate">{row.employee.name}</div>
                        <div className="text-xs text-muted-foreground truncate">{row.employee.company ?? ''}</div>
                      </div>
                      <div className="col-span-2">
                        <Input
                          type="date"
                          className="h-7 text-xs"
                          value={row.partStart}
                          onChange={(e) => updateRow(idx, { partStart: e.target.value })}
                        />
                      </div>
                      <div className="col-span-2">
                        <Input
                          type="date"
                          className="h-7 text-xs"
                          value={row.partEnd}
                          onChange={(e) => updateRow(idx, { partEnd: e.target.value })}
                        />
                      </div>
                      <div className="col-span-1">
                        <Input
                          type="number"
                          step="0.5"
                          min={0}
                          max={maxBonusDays}
                          className={cn('h-7 text-xs text-right', (parseFloat(row.bonusDays) || 0) > maxBonusDays && 'border-destructive ring-destructive')}
                          value={row.bonusDays}
                          onChange={(e) => updateRow(idx, { bonusDays: e.target.value })}
                        />
                      </div>
                      <div className="col-span-1">
                        <Input
                          type="number"
                          min={0}
                          max={maxBonusDays * 8}
                          className={cn('h-7 text-xs text-right', (parseFloat(row.hoursFree) || 0) > maxBonusDays * 8 && 'border-destructive ring-destructive')}
                          value={row.hoursFree}
                          onChange={(e) => updateRow(idx, { hoursFree: e.target.value })}
                        />
                      </div>
                      <div className="col-span-2">
                        <Select value={row.bonusTypeId || '__none__'} onValueChange={(v) => updateRow(idx, { bonusTypeId: v === '__none__' ? '' : v })}>
                          <SelectTrigger className="h-7 text-xs">
                            <SelectValue placeholder="Type" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">None</SelectItem>
                            {bonusTypes.map((bt) => (
                              <SelectItem key={bt.id} value={String(bt.id)}>
                                {bt.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="col-span-1 flex items-center justify-end gap-1">
                        {canViewAmounts && row.bonusNet != null && (
                          <span className="text-xs font-medium text-green-600 whitespace-nowrap">
                            {row.bonusNet.toFixed(0)}
                          </span>
                        )}
                        <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive shrink-0" onClick={() => removeEmployee(idx)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Summary */}
              {rows.length > 0 && (
                <div className="flex items-center gap-6 border-t pt-3 text-sm">
                  <span><span className="font-medium">{rows.length}</span> employees</span>
                  <span><span className="font-medium">{totalDays}</span> total days</span>
                  {canViewAmounts && (
                    <span className="text-green-600 font-medium">{totalBonus.toFixed(0)} RON total</span>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Sticky bottom */}
      <div className="sticky bottom-0 -mx-6 -mb-6 z-40 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="flex items-center justify-end gap-3 px-6 py-3">
          <Button variant="outline" onClick={() => navigate('/app/hr/events')}>
            Cancel
          </Button>
          <Button type="submit" disabled={createEventMutation.isPending} className="min-w-[160px]">
            {createEventMutation.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            {createEventMutation.isPending ? 'Saving...' : 'Save Event & Bonuses'}
          </Button>
        </div>
      </div>
    </form>
  )
}
