import { useState, useMemo, useEffect } from 'react'
import { useNavigate, useLocation, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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
import { DateField } from '@/components/ui/date-field'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { PresenceDayPicker, enumerateDays } from '@/components/shared/PresenceDayPicker'
import { hrApi } from '@/api/hr'
import { useAuthStore } from '@/stores/authStore'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useFormValidation } from '@/hooks/useFormValidation'
import { FieldError } from '@/components/shared/FieldError'
import { marketingApi } from '@/api/marketing'
import type { HrEmployee } from '@/types/hr'
import type { EventParticipant } from '@/types/marketing'

interface EmployeeRow {
  bonusId: number | null // existing event_bonus id (edit); null for a newly added row
  userId: number
  userName: string
  company: string | null
  presenceDays: string[] // specific attended days ('YYYY-MM-DD'), source of truth
  hoursFree: string
  bonusTypeId: string
  bonusNet: number | null
}

const MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

export default function AddEventPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const isMarketing = location.pathname.startsWith('/app/marketing')
  const eventsPath = isMarketing ? '/app/marketing/events' : '/app/hr/events'

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
  const user = useAuthStore((s) => s.user)
  const canViewAmounts = user?.permissions?.['hr.bonuses.view_amounts'] ?? false

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

  const { data: bonusTypes = [], isSuccess: bonusTypesLoaded } = useQuery({
    queryKey: ['hr-bonus-types-active'],
    queryFn: () => hrApi.getBonusTypes(true),
    staleTime: 5 * 60_000,
  })

  const { data: hrSettings } = useQuery({
    queryKey: ['settings', 'hrSettings'],
    queryFn: hrApi.getSettings,
    staleTime: 10 * 60_000,
  })
  const maxHoursPerDay = hrSettings?.hr_bonus_max_hours_per_day ?? 8

  // ── Edit mode: /events/:eventId/edit loads the event + its participants ──
  const { eventId: eventIdParam } = useParams()
  const editEventId = eventIdParam ? Number(eventIdParam) : null
  const isEdit = editEventId != null
  const queryClient = useQueryClient()
  const [originalParticipants, setOriginalParticipants] = useState<EventParticipant[]>([])
  const [prefilled, setPrefilled] = useState(false)

  const { data: editEvent } = useQuery({
    queryKey: ['hr-event', editEventId],
    queryFn: () => hrApi.getEvent(editEventId as number),
    enabled: isEdit,
  })
  const { data: editParticipantsData } = useQuery({
    queryKey: ['event-participants', editEventId],
    queryFn: () => marketingApi.getEventParticipants(editEventId as number),
    enabled: isEdit,
  })

  // Prefill the form + employee rows once the event, participants and bonus
  // types have all loaded (bonusTypesLoaded gates the type-name → id mapping).
  useEffect(() => {
    if (!isEdit || prefilled || !editEvent || !editParticipantsData || !bonusTypesLoaded) return
    setName(editEvent.name ?? '')
    setStartDate(editEvent.start_date ?? '')
    setEndDate(editEvent.end_date ?? '')
    setCompany(editEvent.company ?? '')
    setBrand(editEvent.brand ?? '')
    setDescription(editEvent.description ?? '')
    const m = /^(\d{4})-(\d{2})/.exec(editEvent.start_date ?? '')
    if (m) { setYear(m[1]); setMonth(String(Number(m[2]))) }
    const participants = editParticipantsData.participants ?? []
    setOriginalParticipants(participants)
    setRows(participants.map((p) => {
      const type = bonusTypes.find((t) => t.name === p.bonus_type_name)
      const days = p.presence_days?.length
        ? p.presence_days
        : (p.participation_start && p.participation_end
            ? enumerateDays(p.participation_start, p.participation_end)
            : [])
      return {
        bonusId: p.id,
        userId: p.user_id,
        userName: p.user_name,
        company: null,
        presenceDays: days,
        hoursFree: p.hours_free != null ? String(p.hours_free) : '',
        bonusTypeId: type ? String(type.id) : '',
        bonusNet: p.bonus_net != null ? Number(p.bonus_net) : null,
      }
    }))
    setPrefilled(true)
  }, [isEdit, prefilled, editEvent, editParticipantsData, bonusTypes, bonusTypesLoaded])

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
      const selectedIds = new Set(rows.map((r) => r.userId))
      setSearchResults(results.filter((e) => !selectedIds.has(e.id)))
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }

  const addEmployee = (emp: HrEmployee) => {
    const defaultType = bonusTypes[0]
    // Default to attending the whole event; the user deselects days as needed.
    const days = enumerateDays(startDate, endDate)
    const rate = defaultType ? defaultType.amount / (defaultType.days_per_amount ?? 1) : 0
    setRows((prev) => [
      ...prev,
      {
        bonusId: null,
        userId: emp.id,
        userName: emp.name,
        company: emp.company ?? null,
        presenceDays: days,
        hoursFree: '6',
        bonusTypeId: defaultType ? String(defaultType.id) : '',
        bonusNet: defaultType ? rate * days.length : null,
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
        // Recalculate bonus when type or the selected day count changed
        if ('bonusTypeId' in updates || 'presenceDays' in updates) {
          const type = bonusTypes.find((t) => String(t.id) === updated.bonusTypeId)
          const days = updated.presenceDays.length
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
  const totalDays = useMemo(() => rows.reduce((s, r) => s + r.presenceDays.length, 0), [rows])
  const totalBonus = useMemo(() => rows.reduce((s, r) => s + (r.bonusNet ?? 0), 0), [rows])

  // presence_days is the source of truth; the server derives
  // year/month/participation window/bonus_days from it.
  const bonusPayload = (r: EmployeeRow, evId: number) => ({
    employee_id: r.userId,
    event_id: evId,
    year: Number(year),
    month: Number(month),
    presence_days: r.presenceDays,
    hours_free: parseFloat(r.hoursFree) || null,
    bonus_net: r.bonusNet,
    bonus_type_id: r.bonusTypeId ? Number(r.bonusTypeId) : null,
  })

  const eventFields = () => ({
    name: name.trim(),
    start_date: startDate,
    end_date: endDate,
    company: company || null,
    brand: brand || null,
    description: description || null,
  })

  // Submit — creates a new event or, in edit mode, updates it and reconciles
  // its participants (create added / update changed / delete removed).
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (isEdit && editEventId != null) {
        await hrApi.updateEvent(editEventId, eventFields())
        const keptIds = new Set(rows.filter((r) => r.bonusId != null).map((r) => r.bonusId as number))
        for (const r of rows.filter((x) => x.presenceDays.length > 0)) {
          if (r.bonusId == null) await hrApi.createBonus(bonusPayload(r, editEventId))
          else await hrApi.updateBonus(r.bonusId, bonusPayload(r, editEventId))
        }
        for (const p of originalParticipants) {
          if (!keptIds.has(p.id)) await hrApi.deleteBonus(p.id)
        }
        return { id: editEventId }
      }

      const eventRes = await hrApi.createEvent(eventFields())
      if (!eventRes.id) throw new Error('Event creation failed')
      const bonuses = rows.filter((r) => r.presenceDays.length > 0).map((r) => bonusPayload(r, eventRes.id))
      if (bonuses.length > 0) await hrApi.bulkCreateBonuses(bonuses)
      return eventRes
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hr-events'] })
      queryClient.invalidateQueries({ queryKey: ['hr-summary'] })
      if (isEdit && editEventId != null) {
        queryClient.invalidateQueries({ queryKey: ['event-participants', editEventId] })
      }
      toast.success(isEdit ? 'Event updated' : 'Event and bonuses created')
      navigate(eventsPath)
    },
    onError: () => toast.error(isEdit ? 'Failed to update event' : 'Failed to create event'),
  })

  const handleSubmit = () => {
    v.touchAll()
    if (!v.isValid) return toast.error('Please fix the highlighted fields')
    if (rows.length === 0) return toast.error('Add at least one employee')
    if (rows.some((r) => r.presenceDays.length === 0))
      return toast.error('Each employee needs at least one presence day selected')
    if (rows.some((r) => (parseFloat(r.hoursFree) || 0) > maxBonusDays * maxHoursPerDay))
      return toast.error(`Hours free cannot exceed ${maxBonusDays * maxHoursPerDay} (${maxBonusDays} days x ${maxHoursPerDay}h)`)
    saveMutation.mutate()
  }

  const onFormSubmit = (e: React.FormEvent) => { e.preventDefault(); handleSubmit() }

  return (
    <form onSubmit={onFormSubmit} className="space-y-4">
      <PageHeader
        title={isEdit ? 'Edit Event + Participants' : 'Add Event + Employees'}
        description=""
        breadcrumbs={[
          isMarketing
            ? { label: 'Marketing', shortLabel: 'Mkt.', href: '/app/marketing' }
            : { label: 'HR', href: '/app/hr/pontaje' },
          { label: 'Events', href: eventsPath },
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
                  <DateField value={startDate} onChange={setStartDate} className={cn('w-full', v.error('startDate') && 'border-destructive')} />
                  <FieldError message={v.error('startDate')} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">End Date *</Label>
                  <DateField value={endDate} onChange={setEndDate} className={cn('w-full', v.error('endDate') && 'border-destructive')} />
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
                <div className="space-y-2 max-h-[460px] overflow-y-auto">
                  {rows.map((row, idx) => (
                    <div key={row.bonusId ?? `new-${row.userId}`} className="rounded-lg border p-2 space-y-2">
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium truncate">{row.userName}</div>
                          <div className="text-xs text-muted-foreground truncate">{row.company ?? ''}</div>
                        </div>
                        <div className="w-32">
                          <Label className="text-[10px] text-muted-foreground">Bonus Type</Label>
                          <Select value={row.bonusTypeId || '__none__'} onValueChange={(v) => updateRow(idx, { bonusTypeId: v === '__none__' ? '' : v })}>
                            <SelectTrigger className="h-7 text-xs"><SelectValue placeholder="Type" /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__none__">None</SelectItem>
                              {bonusTypes.map((bt) => (
                                <SelectItem key={bt.id} value={String(bt.id)}>{bt.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="w-16">
                          <Label className="text-[10px] text-muted-foreground">Hours</Label>
                          <Input
                            type="number"
                            min={0}
                            max={maxBonusDays * maxHoursPerDay}
                            className={cn('h-7 text-xs text-right', (parseFloat(row.hoursFree) || 0) > maxBonusDays * maxHoursPerDay && 'border-destructive ring-destructive')}
                            value={row.hoursFree}
                            onChange={(e) => updateRow(idx, { hoursFree: e.target.value })}
                          />
                        </div>
                        <div className="flex items-center gap-1 pt-4">
                          {canViewAmounts && row.bonusNet != null && (
                            <span className="text-xs font-medium text-green-600 whitespace-nowrap">{row.bonusNet.toFixed(0)}</span>
                          )}
                          <Button type="button" variant="ghost" size="icon" className="h-6 w-6 text-destructive shrink-0" onClick={() => removeEmployee(idx)}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                      <div>
                        <Label className="text-[10px] text-muted-foreground">Zile prezență</Label>
                        <PresenceDayPicker
                          startDate={startDate}
                          endDate={endDate}
                          value={row.presenceDays}
                          onChange={(days) => updateRow(idx, { presenceDays: days })}
                        />
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
          <Button variant="outline" onClick={() => navigate(eventsPath)}>
            Cancel
          </Button>
          <Button type="submit" disabled={saveMutation.isPending} className="min-w-[160px]">
            {saveMutation.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            {saveMutation.isPending ? 'Saving...' : isEdit ? 'Save Changes' : 'Save Event & Bonuses'}
          </Button>
        </div>
      </div>
    </form>
  )
}
