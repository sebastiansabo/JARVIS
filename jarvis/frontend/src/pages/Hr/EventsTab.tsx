import { useState, useMemo } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Trash2,
  Pencil,
  Search,
  CalendarDays,
  Users,
  ChevronRight,
  Calendar,
  Banknote,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { QueryError } from '@/components/QueryError'
import { hrApi } from '@/api/hr'
import { marketingApi } from '@/api/marketing'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { TagBadgeList } from '@/components/shared/TagBadge'
import { TagPicker, TagPickerButton } from '@/components/shared/TagPicker'
import { TagFilter } from '@/components/shared/TagFilter'
import { tagsApi } from '@/api/tags'
import { cn } from '@/lib/utils'
import type { HrEvent } from '@/types/hr'
import AddEventPage from './AddEventPage'

function formatDate(d: string) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

function fmtCurrency(v: number | string | null) {
  if (v == null) return '—'
  return Number(v).toLocaleString('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' RON'
}

/* ──── Expanded row: participants ──── */

function EventParticipants({ eventId }: { eventId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['event-participants', eventId],
    queryFn: () => marketingApi.getEventParticipants(eventId),
  })
  const participants = data?.participants ?? []

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Loading participants...</div>

  return (
    <div className="px-6 py-4 space-y-3 bg-muted/30">
      <p className="text-sm font-medium flex items-center gap-1.5">
        <Users className="h-4 w-4" /> Participants ({participants.length})
      </p>
      {participants.length === 0 ? (
        <div className="text-sm text-muted-foreground">No participants recorded for this event.</div>
      ) : (
        <div className="rounded-md border bg-background overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Period</TableHead>
                <TableHead className="text-right">Days</TableHead>
                <TableHead className="text-right">Free Hours</TableHead>
                <TableHead className="text-right">Bonus (RON)</TableHead>
                <TableHead>Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {participants.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="text-sm font-medium">{p.user_name}</TableCell>
                  <TableCell className="text-sm">
                    {p.bonus_type_name ? (
                      <Badge variant="secondary" className="text-xs">{p.bonus_type_name}</Badge>
                    ) : '—'}
                  </TableCell>
                  <TableCell className="text-sm">
                    {p.participation_start && p.participation_end ? (
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3 text-muted-foreground" />
                        {formatDate(p.participation_start)} — {formatDate(p.participation_end)}
                      </span>
                    ) : '—'}
                  </TableCell>
                  <TableCell className="text-sm text-right tabular-nums">{p.bonus_days ?? '—'}</TableCell>
                  <TableCell className="text-sm text-right tabular-nums">{p.hours_free ?? '—'}</TableCell>
                  <TableCell className="text-sm text-right tabular-nums">
                    {p.bonus_net != null && Number(p.bonus_net) > 0 ? (
                      <span className="flex items-center justify-end gap-1">
                        <Banknote className="h-3 w-3 text-green-600" />
                        {fmtCurrency(p.bonus_net)}
                      </span>
                    ) : '—'}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground truncate max-w-[200px]">{p.details ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

/* ──── Events List ──── */

function EventsList() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [filterTagIds, setFilterTagIds] = useState<number[]>([])
  const [selected, setSelected] = useState<number[]>([])
  const [editEvent, setEditEvent] = useState<HrEvent | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteIds, setDeleteIds] = useState<number[] | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  const { data: events = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['hr-events'],
    queryFn: () => hrApi.getEvents(),
  })

  const filtered = useMemo(() => {
    if (!search) return events
    const q = search.toLowerCase()
    return events.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        (e.company?.toLowerCase().includes(q) ?? false) ||
        (e.description?.toLowerCase().includes(q) ?? false),
    )
  }, [events, search])

  // Entity tags for events
  const eventIds = useMemo(() => filtered.map((e) => e.id), [filtered])
  const { data: eventTagsMap = {} } = useQuery({
    queryKey: ['entity-tags', 'event', eventIds],
    queryFn: () => tagsApi.getEntityTagsBulk('event', eventIds),
    enabled: eventIds.length > 0,
  })

  // Apply tag filter client-side
  const displayedEvents = useMemo(() => {
    if (filterTagIds.length === 0) return filtered
    return filtered.filter((e) => {
      const tags = eventTagsMap[String(e.id)] ?? []
      return tags.some((t) => filterTagIds.includes(t.id))
    })
  }, [filtered, filterTagIds, eventTagsMap])

  const deleteMutation = useMutation({
    mutationFn: (ids: number[]) => hrApi.bulkDeleteEvents(ids),
    onSuccess: () => {
      toast.success('Events deleted')
      setSelected([])
      queryClient.invalidateQueries({ queryKey: ['hr-events'] })
      queryClient.invalidateQueries({ queryKey: ['hr-summary'] })
    },
    onError: () => toast.error('Delete failed'),
  })

  const allSelected = displayedEvents.length > 0 && displayedEvents.every((e) => selected.includes(e.id))
  const someSelected = displayedEvents.some((e) => selected.includes(e.id))

  const toggleSelect = (id: number) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-8" placeholder="Search events..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <span className="text-xs text-muted-foreground">{displayedEvents.length} events</span>
        <TagFilter selectedTagIds={filterTagIds} onChange={setFilterTagIds} />
        <div className="ml-auto flex items-center gap-2">
          {selected.length > 0 && (
            <>
              <TagPickerButton
                entityType="event"
                entityIds={selected}
                onTagsChanged={() => queryClient.invalidateQueries({ queryKey: ['entity-tags'] })}
              />
              <Button variant="destructive" size="sm" onClick={() => setDeleteIds(selected)}>
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                Delete ({selected.length})
              </Button>
            </>
          )}
          <Button size="sm" variant="outline" onClick={() => { setEditEvent(null); setDialogOpen(true) }}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Quick Add
          </Button>
          <Button size="sm" onClick={() => navigate('new')}>
            <Users className="mr-1 h-3.5 w-3.5" />
            Add Event + Employees
          </Button>
        </div>
      </div>

      {isError ? (
        <QueryError message="Failed to load events" onRetry={() => refetch()} />
      ) : isLoading ? (
        <Card className="p-6">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted mb-2" />
          ))}
        </Card>
      ) : displayedEvents.length === 0 ? (
        <EmptyState icon={<CalendarDays className="h-8 w-8" />} title="No events" description="Create your first event." />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={allSelected ? true : someSelected ? 'indeterminate' : false}
                      onCheckedChange={() => {
                        if (allSelected) setSelected([])
                        else setSelected(displayedEvents.map((e) => e.id))
                      }}
                    />
                  </TableHead>
                  <TableHead className="w-8" />
                  <TableHead>Event Name</TableHead>
                  <TableHead>Start Date</TableHead>
                  <TableHead>End Date</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Brand</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Created By</TableHead>
                  <TableHead>Tags</TableHead>
                  <TableHead className="w-20">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {displayedEvents.map((ev) => (
                  <>
                    <TableRow
                      key={ev.id}
                      className={cn('cursor-pointer', selected.includes(ev.id) && 'bg-muted/50')}
                      onClick={() => setExpandedRow(expandedRow === ev.id ? null : ev.id)}
                    >
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Checkbox checked={selected.includes(ev.id)} onCheckedChange={() => toggleSelect(ev.id)} />
                      </TableCell>
                      <TableCell className="w-8 px-2">
                        <ChevronRight className={cn('h-4 w-4 transition-transform', expandedRow === ev.id ? 'rotate-90' : '')} />
                      </TableCell>
                      <TableCell className="text-sm font-medium">{ev.name}</TableCell>
                      <TableCell className="text-sm whitespace-nowrap">{formatDate(ev.start_date)}</TableCell>
                      <TableCell className="text-sm whitespace-nowrap">{formatDate(ev.end_date)}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{ev.company ?? '—'}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{ev.brand ?? '—'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[180px] truncate">{ev.description ?? ''}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{ev.created_by_name ?? '—'}</TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <TagPicker entityType="event" entityId={ev.id} currentTags={eventTagsMap[String(ev.id)] ?? []} onTagsChanged={() => {}}>
                          <TagBadgeList tags={eventTagsMap[String(ev.id)] ?? []} />
                        </TagPicker>
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setEditEvent(ev); setDialogOpen(true) }}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setDeleteIds([ev.id])}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {expandedRow === ev.id && (
                      <TableRow key={`${ev.id}-detail`}>
                        <TableCell colSpan={11} className="p-0">
                          <EventParticipants eventId={ev.id} />
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      <EventDialog
        open={dialogOpen}
        event={editEvent}
        onClose={() => { setDialogOpen(false); setEditEvent(null) }}
      />

      <ConfirmDialog
        open={!!deleteIds}
        title="Delete Events"
        description={`Delete ${deleteIds?.length ?? 0} event(s)? Associated bonuses will also be deleted.`}
        onOpenChange={() => setDeleteIds(null)}
        onConfirm={() => deleteIds && deleteMutation.mutate(deleteIds)}
        destructive
      />
    </div>
  )
}

/* ──── Event Dialog (Quick Add/Edit) ──── */

function EventDialog({ open, event, onClose }: { open: boolean; event: HrEvent | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const isEdit = !!event

  const [name, setName] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [company, setCompany] = useState('')
  const [brand, setBrand] = useState('')
  const [description, setDescription] = useState('')

  const { data: companies = [] } = useQuery({
    queryKey: ['hr-structure-companies'],
    queryFn: () => hrApi.getStructureCompanies(),
  })

  const { data: brands = [] } = useQuery({
    queryKey: ['hr-structure-brands', company],
    queryFn: () => hrApi.getStructureBrands(company),
    enabled: !!company,
  })

  const resetForm = () => {
    if (event) {
      setName(event.name)
      setStartDate(event.start_date)
      setEndDate(event.end_date)
      setCompany(event.company ?? '')
      setBrand(event.brand ?? '')
      setDescription(event.description ?? '')
    } else {
      setName('')
      setStartDate('')
      setEndDate('')
      setCompany('')
      setBrand('')
      setDescription('')
    }
  }

  const createMutation = useMutation({
    mutationFn: (data: Partial<HrEvent>) => hrApi.createEvent(data),
    onSuccess: () => {
      toast.success('Event created')
      queryClient.invalidateQueries({ queryKey: ['hr-events'] })
      onClose()
    },
    onError: () => toast.error('Failed to create event'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<HrEvent> }) => hrApi.updateEvent(id, data),
    onSuccess: () => {
      toast.success('Event updated')
      queryClient.invalidateQueries({ queryKey: ['hr-events'] })
      onClose()
    },
    onError: () => toast.error('Failed to update event'),
  })

  const handleSave = () => {
    if (!name.trim()) return toast.error('Event name is required')
    if (!startDate) return toast.error('Start date is required')
    if (!endDate) return toast.error('End date is required')

    const data: Partial<HrEvent> = {
      name: name.trim(),
      start_date: startDate,
      end_date: endDate,
      company: company || null,
      brand: brand || null,
      description: description || null,
    }

    if (isEdit && event) {
      updateMutation.mutate({ id: event.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-md" onOpenAutoFocus={(e) => { e.preventDefault(); resetForm() }}>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Event' : 'Add Event'}</DialogTitle>
          <DialogDescription>{isEdit ? 'Update event details.' : 'Create a new event.'}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Event Name *</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g., Toyota Family Day" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Start Date *</Label>
              <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">End Date *</Label>
              <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
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

/* ──── Router Wrapper ──── */

export default function EventsTab() {
  return (
    <Routes>
      <Route index element={<EventsList />} />
      <Route path="new" element={<AddEventPage />} />
    </Routes>
  )
}
