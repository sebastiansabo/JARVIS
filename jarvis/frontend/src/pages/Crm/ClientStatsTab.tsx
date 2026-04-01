import { useState, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, ChevronsUpDown, Download, Pencil, Trash2, Car, FilterX, Ban, ShieldCheck, SlidersHorizontal, MapPin, Building2, RefreshCw, Search, Truck, MessageSquare, Star, Loader2 } from 'lucide-react'
import { crmApi, type CrmClient, type CrmDeal, type CrmVisit, type FleetVehicle, type ClientInteraction } from '@/api/crm'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { ColumnToggle, useColumnState, type ColumnDef } from '@/components/shared/ColumnToggle'
import { usePersistedState } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { DateField as DatePicker } from '@/components/ui/date-field'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { toast } from 'sonner'

function EditClientDialog({ client, open, onOpenChange }: { client: CrmClient | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Record<string, string>>({})

  const mutation = useMutation({
    mutationFn: (data: Record<string, string>) => crmApi.updateClient(client!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-clients'] })
      toast.success('Client updated')
      onOpenChange(false)
    },
  })

  const set = (k: string, v: string) => setForm(prev => ({ ...prev, [k]: v }))

  // Reset form when dialog opens
  if (open && client && Object.keys(form).length === 0) {
    const init: Record<string, string> = {}
    for (const k of ['display_name', 'client_type', 'phone', 'email', 'street', 'city', 'region', 'company_name', 'responsible']) {
      init[k] = (client as unknown as Record<string, unknown>)[k] as string ?? ''
    }
    setTimeout(() => setForm(init), 0)
  }

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) setForm({}); onOpenChange(o) }}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Edit Client</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Label>Display Name</Label>
            <Input value={form.display_name ?? ''} onChange={e => set('display_name', e.target.value)} />
          </div>
          <div>
            <Label>Type</Label>
            <Select value={form.client_type || 'person'} onValueChange={v => set('client_type', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="person">Person</SelectItem>
                <SelectItem value="company">Company</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Phone</Label>
            <Input value={form.phone ?? ''} onChange={e => set('phone', e.target.value)} />
          </div>
          <div>
            <Label>Email</Label>
            <Input value={form.email ?? ''} onChange={e => set('email', e.target.value)} />
          </div>
          <div>
            <Label>Company</Label>
            <Input value={form.company_name ?? ''} onChange={e => set('company_name', e.target.value)} />
          </div>
          <div>
            <Label>City</Label>
            <Input value={form.city ?? ''} onChange={e => set('city', e.target.value)} />
          </div>
          <div>
            <Label>Region</Label>
            <Input value={form.region ?? ''} onChange={e => set('region', e.target.value)} />
          </div>
          <div className="col-span-2">
            <Label>Street</Label>
            <Input value={form.street ?? ''} onChange={e => set('street', e.target.value)} />
          </div>
          <div className="col-span-2">
            <Label>Responsible</Label>
            <Input value={form.responsible ?? ''} onChange={e => set('responsible', e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => mutation.mutate(form)} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ── Column definitions ── */

const ALL_COLUMNS: ColumnDef<CrmClient>[] = [
  { key: 'display_name', label: 'Name', render: (c) => (
    <span className="font-medium flex items-center gap-1.5">
      {c.is_blacklisted && <Ban className="h-3.5 w-3.5 text-destructive shrink-0" />}
      <span className={c.is_blacklisted ? 'line-through text-muted-foreground' : ''}>{c.display_name}</span>
    </span>
  )},
  { key: 'nr_reg', label: 'Nr.Reg', className: 'font-mono text-xs whitespace-nowrap', render: (c) => c.nr_reg || '—' },
  { key: 'client_type', label: 'Type', render: (c) => (
    <Badge variant={c.client_type === 'company' ? 'default' : 'secondary'} className="text-xs">{c.client_type}</Badge>
  )},
  { key: 'phone', label: 'Phone', className: 'font-mono text-xs', render: (c) => c.phone || '—' },
  { key: 'email', label: 'Email', className: 'text-xs', render: (c) => c.email || '—' },
  { key: 'city', label: 'City', className: 'text-sm', render: (c) => c.city || '—' },
  { key: 'region', label: 'Region', className: 'text-sm', render: (c) => c.region || '—' },
  { key: 'responsible', label: 'Responsible', className: 'text-sm', render: (c) => c.responsible || '—' },
  { key: 'company_name', label: 'Company', className: 'text-sm', render: (c) => c.company_name || '—' },
  { key: 'street', label: 'Street', className: 'text-xs', render: (c) => c.street || '—' },
  { key: 'country', label: 'Country', className: 'text-sm', render: (c) => c.country || '—' },
  { key: 'client_since', label: 'Client Since', className: 'text-xs', render: (c) => c.client_since ? new Date(c.client_since).toLocaleDateString() : '—' },
  { key: 'created_at', label: 'Created', className: 'text-xs', render: (c) => c.created_at ? new Date(c.created_at).toLocaleDateString() : '—' },
]

const DEFAULT_VISIBLE = ['display_name', 'nr_reg', 'client_type', 'phone', 'email', 'city', 'region', 'responsible', 'client_since']
const ALL_KEYS = ALL_COLUMNS.map(c => c.key)
const LOCKED = new Set(['display_name'])

export default function ClientStatsTab({ blacklistOnly, search = '' }: { blacklistOnly?: boolean; search?: string } = {}) {
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const [clientType, setClientType] = useState('')
  const [responsible, setResponsible] = useState('')
  const [city, setCity] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sortBy, setSortBy] = useState('')
  const [sortOrder, setSortOrder] = useState<'ASC' | 'DESC' | ''>('')
  const [showBlacklisted, setShowBlacklisted] = useState(blacklistOnly ? 'only' : '')
  const [page, setPage] = useState(0)
  const [limit, setLimit] = usePersistedState('crm-clients-page-size', 30)

  const toggleSort = (key: string) => {
    if (sortBy === key) {
      if (sortOrder === 'ASC') { setSortOrder('DESC') }
      else if (sortOrder === 'DESC') { setSortBy(''); setSortOrder('') }
      else { setSortOrder('ASC') }
    } else {
      setSortBy(key)
      setSortOrder('ASC')
    }
    setPage(0)
  }

  const hasFilters = !!(search || clientType || responsible || city || dateFrom || dateTo || sortBy || showBlacklisted)
  const filterCount = [clientType, city, responsible, dateFrom, dateTo, showBlacklisted].filter(Boolean).length
  const clearFilters = () => {
    setClientType(''); setResponsible(''); setCity('')
    setDateFrom(''); setDateTo(''); setSortBy(''); setSortOrder(''); setShowBlacklisted(''); setPage(0)
  }

  const isMobile = useIsMobile()
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [massAction, setMassAction] = useState<'blacklist' | 'unblacklist' | 'delete' | null>(null)

  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [editClient, setEditClient] = useState<CrmClient | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { visibleColumns, setVisibleColumns, defaultColumns } = useColumnState(
    'crm-clients-columns', DEFAULT_VISIBLE, ALL_KEYS, 'crm_clients',
  )

  const activeColumns = ALL_COLUMNS.filter(c => visibleColumns.includes(c.key))
    .sort((a, b) => visibleColumns.indexOf(a.key) - visibleColumns.indexOf(b.key))
  const colSpan = activeColumns.length + 2 // +1 chevron +1 checkbox

  // Metadata for filter dropdowns
  const { data: citiesData } = useQuery({ queryKey: ['crm-client-cities'], queryFn: () => crmApi.getClientCities(), staleTime: 10 * 60_000 })
  const { data: responsiblesData } = useQuery({ queryKey: ['crm-client-responsibles'], queryFn: () => crmApi.getClientResponsibles(), staleTime: 10 * 60_000 })

  const params: Record<string, string> = { limit: String(limit), offset: String(page * limit) }
  if (search) params.name = search
  if (clientType) params.client_type = clientType
  if (responsible) params.responsible = responsible
  if (city) params.city = city
  if (dateFrom) params.date_from = dateFrom
  if (dateTo) params.date_to = dateTo
  if (sortBy) params.sort_by = sortBy
  if (sortOrder) params.sort_order = sortOrder
  if (showBlacklisted) params.show_blacklisted = showBlacklisted

  const { data, isLoading } = useQuery({
    queryKey: ['crm-clients', params],
    queryFn: () => crmApi.getClients(params),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => crmApi.deleteClient(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-clients'] })
      toast.success('Client deleted')
      setDeleteId(null)
      setExpandedRow(null)
    },
  })

  const blacklistMutation = useMutation({
    mutationFn: ({ id, blacklisted }: { id: number; blacklisted: boolean }) => crmApi.toggleBlacklist(id, blacklisted),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: ['crm-clients'] })
      toast.success(vars.blacklisted ? 'Client blacklisted' : 'Client removed from blacklist')
    },
  })

  const batchBlacklistMutation = useMutation({
    mutationFn: ({ ids, blacklisted }: { ids: number[]; blacklisted: boolean }) => crmApi.batchBlacklist(ids, blacklisted),
    onSuccess: (data, vars) => {
      queryClient.invalidateQueries({ queryKey: ['crm-clients'] })
      queryClient.invalidateQueries({ queryKey: ['crm-stats'] })
      toast.success(`${data.affected} client${data.affected !== 1 ? 's' : ''} ${vars.blacklisted ? 'blacklisted' : 'removed from blacklist'}`)
      setSelected(new Set())
      setMassAction(null)
    },
  })

  const batchDeleteMutation = useMutation({
    mutationFn: (ids: number[]) => crmApi.batchDeleteClients(ids),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['crm-clients'] })
      queryClient.invalidateQueries({ queryKey: ['crm-stats'] })
      toast.success(`${data.affected} client${data.affected !== 1 ? 's' : ''} deleted`)
      setSelected(new Set())
      setMassAction(null)
    },
  })

  const toggleSelect = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selected.size === clients.length) setSelected(new Set())
    else setSelected(new Set(clients.map(c => c.id)))
  }

  const canExport = user?.can_export_crm
  const exportParams: Record<string, string> = {}
  if (search) exportParams.name = search
  if (clientType) exportParams.client_type = clientType
  if (responsible) exportParams.responsible = responsible
  if (city) exportParams.city = city
  if (dateFrom) exportParams.date_from = dateFrom
  if (dateTo) exportParams.date_to = dateTo

  const clients = data?.clients ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / limit)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{blacklistOnly ? 'Blacklisted Clients' : 'Clients'}</CardTitle>
          <div className="flex items-center gap-2">
            <ColumnToggle
              visibleColumns={visibleColumns}
              defaultColumns={defaultColumns}
              columnDefs={ALL_COLUMNS as ColumnDef<never>[]}
              lockedColumns={LOCKED}
              onChange={setVisibleColumns}
            />
            {canExport && (
              <Button variant="outline" size="sm" className="hidden md:inline-flex" asChild>
                <a href={crmApi.exportClientsUrl(exportParams)} download><Download className="h-4 w-4 mr-1" />Export CSV</a>
              </Button>
            )}
          </div>
        </div>

        {/* Filters */}
        {isMobile ? (
          <>
            <div className="flex items-center gap-2 mt-3">
              <Button variant="outline" size="icon" className="h-9 w-9 shrink-0 relative" onClick={() => setFiltersOpen(true)}>
                <SlidersHorizontal className="h-4 w-4" />
                {filterCount > 0 && (
                  <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">{filterCount}</span>
                )}
              </Button>
            </div>
            <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
              <SheetContent side="bottom" className="max-h-[80vh] overflow-y-auto px-4">
                <SheetHeader><SheetTitle>Filters</SheetTitle></SheetHeader>
                <div className="grid grid-cols-2 gap-2 py-4">
                  <Select value={clientType || '_all'} onValueChange={v => { setClientType(v === '_all' ? '' : v); setPage(0) }}>
                    <SelectTrigger className="w-full h-9"><SelectValue placeholder="Type" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_all">All Types</SelectItem>
                      <SelectItem value="person">Person</SelectItem>
                      <SelectItem value="company">Company</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={city || '_all'} onValueChange={v => { setCity(v === '_all' ? '' : v); setPage(0) }}>
                    <SelectTrigger className="w-full h-9"><SelectValue placeholder="City" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_all">All Cities</SelectItem>
                      {(citiesData?.cities ?? []).map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={responsible || '_all'} onValueChange={v => { setResponsible(v === '_all' ? '' : v); setPage(0) }}>
                    <SelectTrigger className="w-full h-9"><SelectValue placeholder="Responsible" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="_all">All Responsibles</SelectItem>
                      {(responsiblesData?.responsibles ?? []).map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {!blacklistOnly && (
                    <Select value={showBlacklisted || '_default'} onValueChange={v => { setShowBlacklisted(v === '_default' ? '' : v); setPage(0) }}>
                      <SelectTrigger className="w-full h-9"><SelectValue placeholder="Status" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_default">Active Only</SelectItem>
                        <SelectItem value="all">All Clients</SelectItem>
                        <SelectItem value="only">Blacklisted</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                  <DatePicker value={dateFrom} onChange={v => { setDateFrom(v); setPage(0) }} placeholder="From date" className="w-full" />
                  <DatePicker value={dateTo} onChange={v => { setDateTo(v); setPage(0) }} placeholder="To date" className="w-full" />
                  <Button className="col-span-2" onClick={() => setFiltersOpen(false)}>Apply</Button>
                  {filterCount > 0 && (
                    <Button variant="ghost" className="col-span-2" onClick={() => { clearFilters(); setFiltersOpen(false) }}>Clear All</Button>
                  )}
                </div>
              </SheetContent>
            </Sheet>
          </>
        ) : (
          <div className="flex flex-wrap gap-1.5 mt-3">
            <Select value={clientType || '_all'} onValueChange={v => { setClientType(v === '_all' ? '' : v); setPage(0) }}>
              <SelectTrigger className="w-[130px] h-9"><SelectValue placeholder="Type" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">All Types</SelectItem>
                <SelectItem value="person">Person</SelectItem>
                <SelectItem value="company">Company</SelectItem>
              </SelectContent>
            </Select>
            <Select value={city || '_all'} onValueChange={v => { setCity(v === '_all' ? '' : v); setPage(0) }}>
              <SelectTrigger className="w-[150px] h-9"><SelectValue placeholder="City" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">All Cities</SelectItem>
                {(citiesData?.cities ?? []).map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={responsible || '_all'} onValueChange={v => { setResponsible(v === '_all' ? '' : v); setPage(0) }}>
              <SelectTrigger className="w-[160px] h-9"><SelectValue placeholder="Responsible" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">All Responsibles</SelectItem>
                {(responsiblesData?.responsibles ?? []).map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
              </SelectContent>
            </Select>
            <DatePicker value={dateFrom} onChange={v => { setDateFrom(v); setPage(0) }} placeholder="From date" className="w-[155px]" />
            <DatePicker value={dateTo} onChange={v => { setDateTo(v); setPage(0) }} placeholder="To date" className="w-[155px]" />
            {!blacklistOnly && (
              <Select value={showBlacklisted || '_default'} onValueChange={v => { setShowBlacklisted(v === '_default' ? '' : v); setPage(0) }}>
                <SelectTrigger className="w-[140px] h-9"><SelectValue placeholder="Status" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_default">Active Only</SelectItem>
                  <SelectItem value="all">All Clients</SelectItem>
                  <SelectItem value="only">Blacklisted</SelectItem>
                </SelectContent>
              </Select>
            )}
            {hasFilters && (
              <Button variant="ghost" size="sm" className="h-9 px-2 text-muted-foreground hover:text-foreground" onClick={clearFilters}>
                <FilterX className="h-4 w-4 mr-1" />Clear
              </Button>
            )}
          </div>
        )}
      </CardHeader>
      <CardContent>
        {/* Mass action bar */}
        {selected.size > 0 && (
          <div className="flex items-center gap-2 mb-3 rounded-md border bg-muted/50 px-3 py-2">
            <span className="text-sm font-medium">{selected.size} selected</span>
            <div className="flex-1" />
            {!blacklistOnly && (
              <Button size="sm" variant="secondary" onClick={() => setMassAction('blacklist')}>
                <Ban className="h-3.5 w-3.5 mr-1" />Blacklist
              </Button>
            )}
            {blacklistOnly && (
              <Button size="sm" variant="outline" onClick={() => setMassAction('unblacklist')}>
                <ShieldCheck className="h-3.5 w-3.5 mr-1" />Remove from Blacklist
              </Button>
            )}
            <Button size="sm" variant="destructive" onClick={() => setMassAction('delete')}>
              <Trash2 className="h-3.5 w-3.5 mr-1" />Delete
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
          </div>
        )}

        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8 px-2">
                  <Checkbox
                    checked={clients.length > 0 && selected.size === clients.length}
                    onCheckedChange={toggleSelectAll}
                  />
                </TableHead>
                <TableHead className="w-8" />
                {activeColumns.map(col => (
                  <TableHead
                    key={col.key}
                    className="cursor-pointer select-none hover:bg-muted/50"
                    onClick={() => toggleSort(col.key)}
                  >
                    <div className="flex items-center gap-1">
                      {col.label}
                      {sortBy === col.key ? (
                        sortOrder === 'ASC' ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />
                      ) : (
                        <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground/40" />
                      )}
                    </div>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={colSpan} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>
              ) : clients.length === 0 ? (
                <TableRow><TableCell colSpan={colSpan} className="text-center py-8 text-muted-foreground">No clients found</TableCell></TableRow>
              ) : clients.map(c => (
                <Fragment key={c.id}>
                  <TableRow
                    className={`cursor-pointer hover:bg-muted/50 ${selected.has(c.id) ? 'bg-primary/5' : ''}`}
                    onClick={() => setExpandedRow(expandedRow === c.id ? null : c.id)}
                  >
                    <TableCell className="px-2" onClick={e => e.stopPropagation()}>
                      <Checkbox
                        checked={selected.has(c.id)}
                        onCheckedChange={() => toggleSelect(c.id)}
                      />
                    </TableCell>
                    <TableCell className="px-2">
                      <ChevronDown className={`h-4 w-4 transition-transform ${expandedRow === c.id ? 'rotate-180' : ''}`} />
                    </TableCell>
                    {activeColumns.map(col => (
                      <TableCell key={col.key} className={col.className}>{col.render(c)}</TableCell>
                    ))}
                  </TableRow>
                  {expandedRow === c.id && (
                    <TableRow>
                      <TableCell colSpan={colSpan} className="bg-muted/30 p-4">
                        <ClientExpandedDetails
                          client={c}
                          onEdit={() => setEditClient(c)}
                          onDelete={() => setDeleteId(c.id)}
                          onToggleBlacklist={() => blacklistMutation.mutate({ id: c.id, blacklisted: !c.is_blacklisted })}
                        />
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>{total.toLocaleString()} clients</span>
            <Select value={String(limit)} onValueChange={v => { setLimit(Number(v)); setPage(0) }}>
              <SelectTrigger className="w-[70px] h-8"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[20, 30, 50, 100].map(n => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
              </SelectContent>
            </Select>
            <span>per page</span>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" className="h-8 w-8" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm px-2">{page + 1} / {totalPages || 1}</span>
            <Button variant="outline" size="icon" className="h-8 w-8" disabled={page + 1 >= totalPages} onClick={() => setPage(p => p + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>

      <EditClientDialog client={editClient} open={!!editClient} onOpenChange={o => { if (!o) setEditClient(null) }} />
      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={o => { if (!o) setDeleteId(null) }}
        title="Delete Client"
        description="This will permanently delete this client record. This action cannot be undone."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
      />
      <ConfirmDialog
        open={massAction === 'blacklist'}
        onOpenChange={o => { if (!o) setMassAction(null) }}
        title="Blacklist Clients"
        description={`This will blacklist ${selected.size} client${selected.size !== 1 ? 's' : ''}. They will be hidden from Sales, Statistics, and AI indexing.`}
        confirmLabel="Blacklist"
        variant="destructive"
        onConfirm={() => batchBlacklistMutation.mutate({ ids: [...selected], blacklisted: true })}
      />
      <ConfirmDialog
        open={massAction === 'unblacklist'}
        onOpenChange={o => { if (!o) setMassAction(null) }}
        title="Remove from Blacklist"
        description={`This will remove ${selected.size} client${selected.size !== 1 ? 's' : ''} from the blacklist.`}
        confirmLabel="Remove"
        onConfirm={() => batchBlacklistMutation.mutate({ ids: [...selected], blacklisted: false })}
      />
      <ConfirmDialog
        open={massAction === 'delete'}
        onOpenChange={o => { if (!o) setMassAction(null) }}
        title="Delete Clients"
        description={`This will permanently delete ${selected.size} client${selected.size !== 1 ? 's' : ''}. This action cannot be undone.`}
        confirmLabel="Delete All"
        variant="destructive"
        onConfirm={() => batchDeleteMutation.mutate([...selected])}
      />
    </Card>
  )
}

function ClientExpandedDetails({ client, onEdit, onDelete, onToggleBlacklist }: { client: CrmClient; onEdit: () => void; onDelete: () => void; onToggleBlacklist: () => void }) {
  const queryClient = useQueryClient()
  const [cuiInput, setCuiInput] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['crm-client', client.id],
    queryFn: () => crmApi.getClient(client.id),
  })

  const enrichMutation = useMutation({
    mutationFn: (cui: string) => crmApi.enrichClient(client.id, cui),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-client', client.id] })
      toast.success('ANAF data fetched successfully')
      setCuiInput('')
    },
    onError: () => toast.error('Failed to fetch ANAF data'),
  })

  const deals = data?.deals ?? []
  const visits = data?.visits ?? []
  const profile = data?.profile
  const fleet = data?.fleet ?? []
  const interactions = data?.interactions ?? []
  const renewalCandidates = data?.renewal_candidates ?? []
  const fiscal = data?.fiscal as Record<string, unknown> | null

  const InfoItem = ({ label, value }: { label: string; value: string | number | null | undefined }) => (
    <div className="text-sm">
      <span className="text-muted-foreground">{label}:</span>{' '}
      <span className="font-medium">{value || '—'}</span>
    </div>
  )

  return (
    <div className="space-y-4">
      {/* ── 360 Client Header ── */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-1.5">
          <Building2 className="h-4 w-4 text-primary" />
          360 Client
        </h3>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={e => { e.stopPropagation(); onEdit() }}>
            <Pencil className="h-3.5 w-3.5 mr-1" />Edit
          </Button>
          <Button size="sm" variant={client.is_blacklisted ? 'outline' : 'secondary'} onClick={e => { e.stopPropagation(); onToggleBlacklist() }}>
            {client.is_blacklisted ? <><ShieldCheck className="h-3.5 w-3.5 mr-1" />Unblock</> : <><Ban className="h-3.5 w-3.5 mr-1" />Blacklist</>}
          </Button>
          <Button size="sm" variant="destructive" onClick={e => { e.stopPropagation(); onDelete() }}>
            <Trash2 className="h-3.5 w-3.5 mr-1" />Delete
          </Button>
        </div>
      </div>

      {/* ── Client Info + Profile ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded-lg border p-3 space-y-1.5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Contact Info</p>
          <InfoItem label="Company" value={client.company_name} />
          <InfoItem label="Phone" value={client.phone} />
          <InfoItem label="Email" value={client.email} />
          <InfoItem label="Street" value={client.street} />
          <InfoItem label="City" value={client.city} />
          <InfoItem label="Region" value={client.region} />
          <InfoItem label="Country" value={client.country} />
          <InfoItem label="Nr. Reg" value={client.nr_reg} />
          <InfoItem label="Responsible" value={client.responsible} />
          <InfoItem label="Client Since" value={client.client_since ? new Date(client.client_since).toLocaleDateString() : undefined} />
          <InfoItem label="Sources" value={Object.keys(client.source_flags || {}).filter(k => client.source_flags[k]).join(', ')} />
        </div>

        <div className="rounded-lg border p-3 space-y-1.5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Profile & Scoring</p>
          {isLoading ? (
            <p className="text-xs text-muted-foreground flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" />Loading...</p>
          ) : profile ? (
            <>
              <InfoItem label="CUI" value={profile.cui} />
              <InfoItem label="Client Type" value={profile.client_type} />
              <InfoItem label="Country Code" value={profile.country_code} />
              <InfoItem label="Industry" value={profile.industry} />
              <InfoItem label="Priority" value={profile.priority} />
              <InfoItem label="Renewal Score" value={profile.renewal_score != null ? `${profile.renewal_score}/100` : undefined} />
              <InfoItem label="Fleet Size" value={profile.fleet_size} />
              <InfoItem label="Est. Annual Value" value={profile.estimated_annual_value != null ? `${Number(profile.estimated_annual_value).toLocaleString('ro-RO')} EUR` : undefined} />
              <InfoItem label="Legal Form" value={profile.legal_form} />
            </>
          ) : (
            <p className="text-xs text-muted-foreground">No profile data yet</p>
          )}
        </div>
      </div>

      {/* ── ANAF Fiscal Data ── */}
      <div className="rounded-lg border p-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
            <Building2 className="h-3.5 w-3.5" />ANAF Fiscal Data
          </p>
          {profile?.cui && (
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => enrichMutation.mutate(profile.cui!)} disabled={enrichMutation.isPending}>
              <RefreshCw className={`h-3 w-3 mr-1 ${enrichMutation.isPending ? 'animate-spin' : ''}`} />Refresh
            </Button>
          )}
        </div>
        {fiscal ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1.5 text-sm">
            <InfoItem label="Company Name" value={fiscal.denumire as string} />
            <InfoItem label="CUI" value={fiscal.cui as string} />
            <InfoItem label="Nr. Reg" value={fiscal.nrRegCom as string} />
            <InfoItem label="Address" value={fiscal.adresa as string} />
            <InfoItem label="CAEN Code" value={fiscal.cod_CAEN as string} />
            <InfoItem label="CAEN Activity" value={fiscal.aut as string} />
            <InfoItem label="VAT Registered" value={(fiscal.scpTVA === true || fiscal.tva === true) ? 'Yes' : 'No'} />
            <InfoItem label="Active" value={fiscal.statusInactivi === true ? 'Inactive' : 'Active'} />
            <InfoItem label="Split TVA" value={fiscal.splitTVA === true ? 'Yes' : 'No'} />
            {profile?.anaf_fetched_at && (
              <InfoItem label="Last Fetched" value={new Date(profile.anaf_fetched_at).toLocaleString('ro-RO')} />
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Input
              placeholder="Enter CUI (e.g. 12345678)"
              value={cuiInput}
              onChange={e => setCuiInput(e.target.value)}
              className="w-48 h-8 text-sm"
              onKeyDown={e => e.key === 'Enter' && cuiInput.trim() && enrichMutation.mutate(cuiInput.trim())}
            />
            <Button size="sm" className="h-8" onClick={() => enrichMutation.mutate(cuiInput.trim())} disabled={!cuiInput.trim() || enrichMutation.isPending}>
              {enrichMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Search className="h-3.5 w-3.5 mr-1" />}
              Fetch ANAF
            </Button>
          </div>
        )}
      </div>

      {/* ── Cars Purchased (Deals) ── */}
      <div>
        <p className="text-sm font-medium flex items-center gap-1.5 mb-2">
          <Car className="h-4 w-4" />
          Cars Purchased ({isLoading ? '...' : deals.length})
        </p>
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading deals...</p>
        ) : deals.length === 0 ? (
          <p className="text-xs text-muted-foreground">No deals linked to this client</p>
        ) : (
          <div className="rounded border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="text-xs py-1.5">Source</TableHead>
                  <TableHead className="text-xs py-1.5">Brand</TableHead>
                  <TableHead className="text-xs py-1.5">Model</TableHead>
                  <TableHead className="text-xs py-1.5">VIN</TableHead>
                  <TableHead className="text-xs py-1.5">Contract Date</TableHead>
                  <TableHead className="text-xs py-1.5">Status</TableHead>
                  <TableHead className="text-xs py-1.5 text-right">Sale Price</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deals.map((d: CrmDeal) => (
                  <TableRow key={d.id}>
                    <TableCell className="py-1.5">
                      <Badge variant={d.source === 'nw' ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0">
                        {d.source?.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs py-1.5">{d.brand || '—'}</TableCell>
                    <TableCell className="text-xs py-1.5">{d.model_name || '—'}</TableCell>
                    <TableCell className="text-xs font-mono py-1.5">{d.vin || '—'}</TableCell>
                    <TableCell className="text-xs py-1.5">{d.contract_date ? new Date(d.contract_date).toLocaleDateString() : '—'}</TableCell>
                    <TableCell className="text-xs py-1.5">{d.dossier_status || '—'}</TableCell>
                    <TableCell className="text-xs font-mono py-1.5 text-right">
                      {d.sale_price_net ? Number(d.sale_price_net).toLocaleString('ro-RO') : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* ── Fleet Vehicles ── */}
      {fleet.length > 0 && (
        <div>
          <p className="text-sm font-medium flex items-center gap-1.5 mb-2">
            <Truck className="h-4 w-4" />
            Fleet ({fleet.length})
            {renewalCandidates.length > 0 && (
              <Badge variant="secondary" className="text-[10px] ml-1"><Star className="h-2.5 w-2.5 mr-0.5" />{renewalCandidates.length} renewal</Badge>
            )}
          </p>
          <div className="rounded border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="text-xs py-1.5">Make</TableHead>
                  <TableHead className="text-xs py-1.5">Model</TableHead>
                  <TableHead className="text-xs py-1.5">Year</TableHead>
                  <TableHead className="text-xs py-1.5">VIN</TableHead>
                  <TableHead className="text-xs py-1.5">Plate</TableHead>
                  <TableHead className="text-xs py-1.5">Status</TableHead>
                  <TableHead className="text-xs py-1.5">Renewal</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fleet.map((v: FleetVehicle) => (
                  <TableRow key={v.id}>
                    <TableCell className="text-xs py-1.5 font-medium">{v.vehicle_make || '—'}</TableCell>
                    <TableCell className="text-xs py-1.5">{v.vehicle_model || '—'}</TableCell>
                    <TableCell className="text-xs py-1.5">{v.vehicle_year || '—'}</TableCell>
                    <TableCell className="text-xs font-mono py-1.5">{v.vin || '—'}</TableCell>
                    <TableCell className="text-xs font-mono py-1.5">{v.license_plate || '—'}</TableCell>
                    <TableCell className="py-1.5">
                      <Badge variant={v.status === 'active' ? 'default' : 'secondary'} className="text-[10px] px-1.5 py-0">{v.status || '—'}</Badge>
                    </TableCell>
                    <TableCell className="py-1.5">
                      {v.renewal_candidate ? (
                        <Badge className="text-[10px] px-1.5 py-0 bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                          <Star className="h-2.5 w-2.5 mr-0.5" />Yes
                        </Badge>
                      ) : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* ── Field Sales Visits ── */}
      <div>
        <p className="text-sm font-medium flex items-center gap-1.5 mb-2">
          <MapPin className="h-4 w-4" />
          Field Sales Visits ({isLoading ? '...' : visits.length})
        </p>
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading visits...</p>
        ) : visits.length === 0 ? (
          <p className="text-xs text-muted-foreground">No field sales visits for this client</p>
        ) : (
          <div className="rounded border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="text-xs py-1.5">Date</TableHead>
                  <TableHead className="text-xs py-1.5">KAM</TableHead>
                  <TableHead className="text-xs py-1.5">Type</TableHead>
                  <TableHead className="text-xs py-1.5">Status</TableHead>
                  <TableHead className="text-xs py-1.5">Summary</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visits.map((v: CrmVisit) => (
                  <TableRow key={v.id}>
                    <TableCell className="text-xs py-1.5">
                      {v.planned_date ? new Date(v.planned_date).toLocaleDateString() : '—'}
                    </TableCell>
                    <TableCell className="text-xs py-1.5 font-medium">{v.kam_name || '—'}</TableCell>
                    <TableCell className="py-1.5">
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                        {v.visit_type?.replace(/_/g, ' ') || '—'}
                      </Badge>
                    </TableCell>
                    <TableCell className="py-1.5">
                      <Badge variant={v.status === 'completed' ? 'default' : v.status === 'in_progress' ? 'secondary' : 'outline'} className="text-[10px] px-1.5 py-0">
                        {v.status || '—'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs py-1.5 max-w-[300px] truncate">
                      {v.visit_summary || v.goals || '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* ── Interactions (Visit Notes) ── */}
      {interactions.length > 0 && (
        <div>
          <p className="text-sm font-medium flex items-center gap-1.5 mb-2">
            <MessageSquare className="h-4 w-4" />
            Recent Interactions ({interactions.length})
          </p>
          <div className="space-y-2">
            {interactions.slice(0, 5).map((i: ClientInteraction) => (
              <div key={i.id} className="rounded border p-2.5 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{i.kam_name || 'Unknown'}</span>
                  <span className="text-muted-foreground">{i.created_at ? new Date(i.created_at).toLocaleDateString() : ''}</span>
                </div>
                {i.visit_type && <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{i.visit_type.replace(/_/g, ' ')}</Badge>}
                <p className="text-muted-foreground line-clamp-2">
                  {(i.structured_note as Record<string, string>)?.visit_summary || i.raw_note || '—'}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
