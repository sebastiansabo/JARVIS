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
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, ChevronsUpDown, Search, Download, Pencil, Trash2, Car, FilterX } from 'lucide-react'
import { crmApi, type CrmClient, type CrmDeal } from '@/api/crm'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { ColumnToggle, useColumnState, type ColumnDef } from '@/components/shared/ColumnToggle'
import { usePersistedState } from '@/lib/utils'
import { useAuthStore } from '@/stores/authStore'
import { DatePicker } from '@/components/ui/date-picker'
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
  { key: 'display_name', label: 'Name', render: (c) => <span className="font-medium">{c.display_name}</span> },
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

export default function ClientStatsTab() {
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [clientType, setClientType] = useState('')
  const [responsible, setResponsible] = useState('')
  const [city, setCity] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sortBy, setSortBy] = useState('')
  const [sortOrder, setSortOrder] = useState<'ASC' | 'DESC' | ''>('')
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

  const hasFilters = !!(search || clientType || responsible || city || dateFrom || dateTo || sortBy)
  const clearFilters = () => {
    setSearch(''); setClientType(''); setResponsible(''); setCity('')
    setDateFrom(''); setDateTo(''); setSortBy(''); setSortOrder(''); setPage(0)
  }

  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [editClient, setEditClient] = useState<CrmClient | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { visibleColumns, setVisibleColumns, defaultColumns } = useColumnState(
    'crm-clients-columns', DEFAULT_VISIBLE, ALL_KEYS,
  )

  const activeColumns = ALL_COLUMNS.filter(c => visibleColumns.includes(c.key))
    .sort((a, b) => visibleColumns.indexOf(a.key) - visibleColumns.indexOf(b.key))
  const colSpan = activeColumns.length + 1 // +1 for chevron column

  // Metadata for filter dropdowns
  const { data: citiesData } = useQuery({ queryKey: ['crm-client-cities'], queryFn: () => crmApi.getClientCities() })
  const { data: responsiblesData } = useQuery({ queryKey: ['crm-client-responsibles'], queryFn: () => crmApi.getClientResponsibles() })

  const params: Record<string, string> = { limit: String(limit), offset: String(page * limit) }
  if (search) params.name = search
  if (clientType) params.client_type = clientType
  if (responsible) params.responsible = responsible
  if (city) params.city = city
  if (dateFrom) params.date_from = dateFrom
  if (dateTo) params.date_to = dateTo
  if (sortBy) params.sort_by = sortBy
  if (sortOrder) params.sort_order = sortOrder

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
          <CardTitle className="text-base">Clients</CardTitle>
          <div className="flex items-center gap-2">
            <ColumnToggle
              visibleColumns={visibleColumns}
              defaultColumns={defaultColumns}
              columnDefs={ALL_COLUMNS as ColumnDef<never>[]}
              lockedColumns={LOCKED}
              onChange={setVisibleColumns}
            />
            {canExport && (
              <Button variant="outline" size="sm" asChild>
                <a href={crmApi.exportClientsUrl(exportParams)} download><Download className="h-4 w-4 mr-1" />Export CSV</a>
              </Button>
            )}
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-1.5 mt-3">
          <div className="relative flex-1 min-w-[180px]">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search name..." value={search} onChange={e => { setSearch(e.target.value); setPage(0) }} className="pl-8 h-9" />
          </div>
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
          {hasFilters && (
            <Button variant="ghost" size="sm" className="h-9 px-2 text-muted-foreground hover:text-foreground" onClick={clearFilters}>
              <FilterX className="h-4 w-4 mr-1" />Clear
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
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
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setExpandedRow(expandedRow === c.id ? null : c.id)}
                  >
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
    </Card>
  )
}

function ClientExpandedDetails({ client, onEdit, onDelete }: { client: CrmClient; onEdit: () => void; onDelete: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['crm-client', client.id],
    queryFn: () => crmApi.getClient(client.id),
  })

  const deals = data?.deals ?? []

  return (
    <div className="space-y-3">
      {/* Client info */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div><span className="text-muted-foreground">Company:</span> {client.company_name || '—'}</div>
        <div><span className="text-muted-foreground">Street:</span> {client.street || '—'}</div>
        <div><span className="text-muted-foreground">Country:</span> {client.country || '—'}</div>
        <div><span className="text-muted-foreground">Created:</span> {client.created_at ? new Date(client.created_at).toLocaleDateString() : '—'}</div>
        <div><span className="text-muted-foreground">Sources:</span> {Object.keys(client.source_flags || {}).filter(k => client.source_flags[k]).join(', ') || '—'}</div>
      </div>

      {/* Linked deals */}
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

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={e => { e.stopPropagation(); onEdit() }}>
          <Pencil className="h-3.5 w-3.5 mr-1" />Edit
        </Button>
        <Button size="sm" variant="destructive" onClick={e => { e.stopPropagation(); onDelete() }}>
          <Trash2 className="h-3.5 w-3.5 mr-1" />Delete
        </Button>
      </div>
    </div>
  )
}
