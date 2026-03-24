import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Plus, Trash2, Search, ChevronRight, UserCheck, Phone, Mail, MapPin } from 'lucide-react'
import { cn, useDebounce } from '@/lib/utils'
import { marketingApi } from '@/api/marketing'
import type { CrmClientSearchResult, CrmDeal } from '@/types/marketing'
import { fmt, fmtDate } from './utils'

/* ── Expanded row: client deals ─────────────────────────── */

function ClientExpandedDeals({ projectId, clientId }: { projectId: number; clientId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['mkt-client-deals', projectId, clientId],
    queryFn: () => marketingApi.getClientDeals(projectId, clientId),
  })
  const deals: CrmDeal[] = data?.deals ?? []

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Loading deals...</div>

  return (
    <div className="px-6 py-4 space-y-3 bg-muted/30">
      <p className="text-sm font-medium">Deals ({deals.length})</p>
      {deals.length === 0 ? (
        <div className="text-sm text-muted-foreground">No deals recorded for this client.</div>
      ) : (
        <div className="rounded-md border bg-background overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Brand</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="text-right">Price (net)</TableHead>
                <TableHead className="text-right">Profit</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Sales Person</TableHead>
                <TableHead>VIN</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {deals.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="text-sm font-medium">{d.brand ?? '—'}</TableCell>
                  <TableCell className="text-sm">{d.model_name ?? '—'}</TableCell>
                  <TableCell className="text-sm">
                    {d.source ? <Badge variant="outline" className="text-xs">{d.source}</Badge> : '—'}
                  </TableCell>
                  <TableCell className="text-sm text-right tabular-nums">
                    {d.sale_price_net != null ? fmt(d.sale_price_net, 'EUR') : '—'}
                  </TableCell>
                  <TableCell className="text-sm text-right tabular-nums">
                    {d.gross_profit != null ? fmt(d.gross_profit, 'EUR') : '—'}
                  </TableCell>
                  <TableCell className="text-sm">{fmtDate(d.contract_date)}</TableCell>
                  <TableCell className="text-sm">
                    {d.dossier_status ? <Badge variant="secondary" className="text-xs">{d.dossier_status}</Badge> : '—'}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{d.sales_person ?? '—'}</TableCell>
                  <TableCell className="text-sm font-mono text-xs text-muted-foreground">{d.vin ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

/* ── Main tab ───────────────────────────────────────────── */

export function ClientsTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [showLink, setShowLink] = useState(false)
  const [clientSearch, setClientSearch] = useState('')
  const debouncedClientSearch = useDebounce(clientSearch, 300)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  const { data } = useQuery({
    queryKey: ['mkt-project-clients', projectId],
    queryFn: () => marketingApi.getProjectClients(projectId),
  })
  const clients = data?.clients ?? []

  const linkMut = useMutation({
    mutationFn: (clientId: number) => marketingApi.linkClient(projectId, clientId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-clients', projectId] })
      setShowLink(false)
      setClientSearch('')
    },
  })

  const unlinkMut = useMutation({
    mutationFn: (clientId: number) => marketingApi.unlinkClient(projectId, clientId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-project-clients', projectId] })
      if (expandedRow) setExpandedRow(null)
    },
  })

  const { data: searchData, isLoading: isSearching } = useQuery({
    queryKey: ['mkt-client-search', debouncedClientSearch],
    queryFn: () => marketingApi.searchCrmClients(debouncedClientSearch),
    enabled: showLink && debouncedClientSearch.length >= 1,
  })
  const clientResults: CrmClientSearchResult[] = searchData?.clients ?? []

  const linkedIds = new Set(clients.map((c) => c.client_id))

  function toggleExpand(clientId: number) {
    setExpandedRow(expandedRow === clientId ? null : clientId)
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => { setShowLink(true); setClientSearch('') }}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Link Client
        </Button>
      </div>

      {clients.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <UserCheck className="mx-auto h-8 w-8 mb-2 opacity-40" />
          <div>No CRM clients linked</div>
          <div className="text-xs mt-1">Link clients to track their deals against project KPIs.</div>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Client</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>City</TableHead>
                <TableHead>Responsible</TableHead>
                <TableHead className="text-right">Deals</TableHead>
                <TableHead className="text-right">Revenue</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.map((c) => (
                <>
                  <TableRow
                    key={c.id}
                    className="cursor-pointer"
                    onClick={() => toggleExpand(c.client_id)}
                  >
                    <TableCell className="w-8 px-2">
                      <ChevronRight className={cn('h-4 w-4 transition-transform', expandedRow === c.client_id ? 'rotate-90' : '')} />
                    </TableCell>
                    <TableCell>
                      <div className="text-sm font-medium">{c.display_name}</div>
                    </TableCell>
                    <TableCell className="text-sm">
                      {c.client_type ? (
                        <Badge variant="outline" className="text-xs">{c.client_type}</Badge>
                      ) : '—'}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-0.5">
                        {c.phone && (
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Phone className="h-3 w-3" /> {c.phone}
                          </span>
                        )}
                        {c.email && (
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Mail className="h-3 w-3" /> {c.email}
                          </span>
                        )}
                        {!c.phone && !c.email && <span className="text-xs text-muted-foreground">—</span>}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">
                      {c.city ? (
                        <span className="flex items-center gap-1">
                          <MapPin className="h-3 w-3 text-muted-foreground" /> {c.city}
                        </span>
                      ) : '—'}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{c.responsible ?? '—'}</TableCell>
                    <TableCell className="text-sm text-right tabular-nums font-medium">{Number(c.deal_count)}</TableCell>
                    <TableCell className="text-sm text-right tabular-nums">
                      {Number(c.total_revenue) > 0 ? fmt(c.total_revenue, 'EUR') : '—'}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost" size="icon" className="h-7 w-7"
                        onClick={(ev) => { ev.stopPropagation(); unlinkMut.mutate(c.client_id) }}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </TableCell>
                  </TableRow>
                  {expandedRow === c.client_id && (
                    <TableRow key={`${c.id}-deals`}>
                      <TableCell colSpan={9} className="p-0">
                        <ClientExpandedDeals projectId={projectId} clientId={c.client_id} />
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Link Client Dialog */}
      <Dialog open={showLink} onOpenChange={setShowLink}>
        <DialogContent className="sm:max-w-2xl" aria-describedby={undefined}>
          <DialogHeader><DialogTitle>Link CRM Client</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search clients by name, phone, email..."
                value={clientSearch}
                onChange={(e) => setClientSearch(e.target.value)}
                autoFocus
              />
            </div>
            {isSearching && <div className="text-center text-sm text-muted-foreground py-2">Searching...</div>}
            {clientResults.length > 0 && (
              <div className="rounded-md border max-h-64 overflow-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Client</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>City</TableHead>
                      <TableHead className="text-right">Deals</TableHead>
                      <TableHead className="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {clientResults.map((cl) => (
                      <TableRow key={cl.id}>
                        <TableCell>
                          <div className="text-sm font-medium">{cl.display_name}</div>
                          {cl.email && <div className="text-xs text-muted-foreground">{cl.email}</div>}
                        </TableCell>
                        <TableCell className="text-sm">
                          {cl.client_type ? <Badge variant="outline" className="text-xs">{cl.client_type}</Badge> : '—'}
                        </TableCell>
                        <TableCell className="text-sm">{cl.city ?? '—'}</TableCell>
                        <TableCell className="text-sm text-right tabular-nums">{Number(cl.deal_count)}</TableCell>
                        <TableCell>
                          {linkedIds.has(cl.id) ? (
                            <Badge variant="secondary" className="text-xs">Linked</Badge>
                          ) : (
                            <Button size="sm" variant="outline" className="h-7"
                              disabled={linkMut.isPending}
                              onClick={() => linkMut.mutate(cl.id)}>
                              Link
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {debouncedClientSearch.length >= 1 && !isSearching && clientResults.length === 0 && (
              <div className="text-center text-sm text-muted-foreground py-4">No clients found.</div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
