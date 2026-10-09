import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Car, List as ListIcon, LayoutGrid, Trash2, ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import type { BuybackRecord } from '@/types/buyback'
import { useAuth } from '@/hooks/useAuth'
import { recordStatus, STATUS_FILTER_OPTIONS } from './recordStatus'
import { usePermissions } from './usePermissions'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { SearchInput } from '@/components/shared/SearchInput'

const ACQUISITION_TYPE_OPTIONS = [
  { value: 'buyback', label: 'Buyback' },
  { value: 'tradein', label: 'Trade-in' },
]

// Terminal ("resolved") statuses live under the Arhivă tab; everything else
// (the in-progress workflow) lives under Active. A freshly-resolved request
// also lingers on the Active side for 72h so the team sees the outcome before
// it drops to Arhivă only.
const PAGE_SIZE = 25 // list-view rows per page (Kanban shows all)
const RESOLVED_STATUSES = ['BOUGHT', 'LOST', 'CANCELLED']
const isResolved = (s: string) => RESOLVED_STATUSES.includes(s)
const RESOLVED_ACTIVE_WINDOW_MS = 72 * 60 * 60 * 1000

// Best-available resolution timestamp: closed_at (LOST/CANCELLED) → bought_at
// (BOUGHT) → updated_at (always bumped on the terminal transition).
function resolutionTime(r: { closed_at: string | null; bought_at: string | null; updated_at: string }): number | null {
  const ts = r.closed_at ?? r.bought_at ?? r.updated_at
  return ts ? new Date(ts).getTime() : null
}
// Resolved but within the 72h window → still shown on Active.
function lingersOnActive(r: { status: string; closed_at: string | null; bought_at: string | null; updated_at: string }, now: number): boolean {
  const t = resolutionTime(r)
  return t != null && now - t <= RESOLVED_ACTIVE_WINDOW_MS
}

// ── Sorting (client-side, over the loaded set) ──
type SortKey =
  | 'record_code' | 'vehicle' | 'vin' | 'seller_name'
  | 'client_asking_price_eur' | 'purchase_price_eur' | 'status' | 'advisor_name' | 'created_at'

// Lifecycle progression order so sorting by Status is meaningful, not alphabetical.
const STATUS_ORDER: Record<string, number> = {
  PENDING_EVALUATION: 0, INITIAL_OFFER: 1, INSPECTION: 2, FINAL_OFFER: 3, BOUGHT: 4, LOST: 5, CANCELLED: 6,
}

function sortValue(r: BuybackRecord, key: SortKey): string | number | null {
  switch (key) {
    case 'vehicle': return `${r.brand} ${r.model}`.trim()
    case 'created_at': return new Date(r.created_at).getTime()
    case 'status': return STATUS_ORDER[r.status] ?? 99
    case 'client_asking_price_eur': return r.client_asking_price_eur
    case 'purchase_price_eur': return r.purchase_price_eur
    default: return r[key] as string | null
  }
}

function compareRecords(a: BuybackRecord, b: BuybackRecord, key: SortKey, dir: 'asc' | 'desc'): number {
  const av = sortValue(a, key)
  const bv = sortValue(b, key)
  const aEmpty = av === null || av === undefined || av === ''
  const bEmpty = bv === null || bv === undefined || bv === ''
  if (aEmpty && bEmpty) return 0
  if (aEmpty) return 1 // empties always last, regardless of direction
  if (bEmpty) return -1
  let cmp: number
  if (typeof av === 'number' && typeof bv === 'number') cmp = av - bv
  else cmp = String(av).localeCompare(String(bv), 'ro')
  return dir === 'asc' ? cmp : -cmp
}

// Statuses a record may be deleted in (mirrors the backend's _DELETABLE_STATUSES).
const DELETABLE_STATUSES = ['PENDING_EVALUATION', 'LOST', 'CANCELLED']

// List-view columns, in display order, each sortable by its key.
const COLUMNS: { key: SortKey; label: string; align?: 'right' }[] = [
  { key: 'record_code', label: 'Cod' },
  { key: 'vehicle', label: 'Vehicul' },
  { key: 'vin', label: 'VIN' },
  { key: 'seller_name', label: 'Vânzător' },
  { key: 'client_asking_price_eur', label: 'Preț cerut €', align: 'right' },
  { key: 'purchase_price_eur', label: 'Preț achiziție €', align: 'right' },
  { key: 'status', label: 'Status' },
  { key: 'advisor_name', label: 'Consilier' },
  { key: 'created_at', label: 'Creat' },
]

// Tenant-switcher selection, persisted across refreshes. 'all' = every company
// the caller may see; a numeric id = that one company; null = default (own).
const COMPANY_STORAGE_KEY = 'buyback.companyFilter'
const ALL_COMPANIES = 'all'

function readStoredCompany(): typeof ALL_COMPANIES | number | null {
  try {
    const raw = localStorage.getItem(COMPANY_STORAGE_KEY)
    if (raw === ALL_COMPANIES) return ALL_COMPANIES
    if (raw) {
      const n = Number(raw)
      if (Number.isFinite(n)) return n
    }
  } catch {
    /* localStorage unavailable — fall back to the default view */
  }
  return null
}

export default function BuyBack() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [status, setStatus] = useState('all')
  const [acquisitionType, setAcquisitionType] = useState('all')
  const [q, setQ] = useState('')
  const [companySel, setCompanySel] = useState<typeof ALL_COMPANIES | number | null>(readStoredCompany)
  const [view, setView] = useState<'list' | 'kanban'>('list')
  const [tab, setTab] = useState<'active' | 'archive'>('active')
  const [page, setPage] = useState(1)
  const [sortBy, setSortBy] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [deleteTarget, setDeleteTarget] = useState<BuybackRecord | null>(null)

  const { can } = usePermissions()
  const canCreate = can('buyback.record.create')
  const canDelete = can('buyback.record.delete')
  // Global admins may hard-delete ANY archived record (incl. BOUGHT /
  // CarPark-linked) — mirrors the backend's can_access_settings exception.
  const isAdmin = !!user?.can_access_settings
  const canDeleteAny = canDelete || isAdmin
  const queryClient = useQueryClient()

  // Tenant switcher: the companies the caller may see (own + org-responsable;
  // a global admin sees all). The dropdown is shown only when there's >1.
  const { data: companiesData } = useQuery({
    queryKey: ['buyback-companies'],
    queryFn: () => buybackApi.getCompanies(),
    staleTime: 60_000,
  })
  const companies = companiesData?.companies ?? []
  const ownCompanyId = user?.company_id ?? null

  const selectCompany = (sel: typeof ALL_COMPANIES | number) => {
    setCompanySel(sel)
    try {
      localStorage.setItem(COMPANY_STORAGE_KEY, String(sel))
    } catch {
      /* ignore — persistence is best-effort */
    }
  }

  // Drop a persisted company id the caller can no longer see (access changed)
  // once the list loads — fall back to the default (own-company) view.
  useEffect(() => {
    if (typeof companySel === 'number' && companies.length > 0 && !companies.some((c) => c.id === companySel)) {
      setCompanySel(null)
      try {
        localStorage.removeItem(COMPANY_STORAGE_KEY)
      } catch {
        /* ignore */
      }
    }
  }, [companies, companySel])

  // Companies to pull records for: 'all' → every permitted company (fan-out,
  // merged client-side — the backend lists one company per call and each call
  // is independently authorized); a specific pick → just that one; default →
  // own. Falls back to own while the companies list is still loading.
  const companyIds = useMemo<(number | null)[]>(() => {
    if (companySel === ALL_COMPANIES) {
      // Fan out once companies load; until then fall back to the default query.
      return companies.length > 0 ? companies.map((c) => c.id) : [ownCompanyId]
    }
    // Default/specific: always one query. `null` → company_id omitted, letting
    // the backend resolve scope (own company, or all for a global admin) —
    // identical to the pre-fan-out single-query behavior.
    return [companySel ?? ownCompanyId]
  }, [companySel, companies, ownCompanyId])

  // One query per target company (cached/reused across selection changes),
  // combined into a single merged record set. Fetch the full set per company:
  // the Active/Arhivă split, status chips and client paging below all count
  // over `records`. Backend caps per_page at 1000.
  const { records, isLoading, isError } = useQueries({
    queries: companyIds.map((cid) => ({
      queryKey: ['buyback-records', { status, acquisition_type: acquisitionType, q, company_id: cid }],
      queryFn: () =>
        buybackApi.listRecords({
          status: status !== 'all' ? status : undefined,
          acquisition_type: acquisitionType !== 'all' ? acquisitionType : undefined,
          q: q || undefined,
          company_id: cid ?? undefined,
          per_page: 1000,
          sort_by: 'created_at',
          sort_dir: 'DESC',
        }),
      staleTime: 30_000,
    })),
    combine: (results) => ({
      records: results.flatMap((r) => r.data?.records ?? []),
      isLoading: results.some((r) => r.isLoading),
      isError: results.some((r) => r.isError),
    }),
  })
  // Active vs Arhivă split. Active = in-progress + resolved-within-72h; Arhivă =
  // all resolved (the permanent history).
  const activeCount = useMemo(() => {
    const now = Date.now()
    return records.filter((r) => !isResolved(r.status) || lingersOnActive(r, now)).length
  }, [records])
  const archiveCount = useMemo(() => records.filter((r) => isResolved(r.status)).length, [records])
  const visibleRecords = useMemo(() => {
    const now = Date.now()
    return records.filter((r) => {
      if (tab === 'archive') return isResolved(r.status)
      return !isResolved(r.status) || lingersOnActive(r, now)
    })
  }, [records, tab])
  // Group once by status; both the count chips and the Kanban columns read
  // from these buckets (avoids a filter pass per status + per column).
  const recordsByStatus = useMemo(() => {
    const buckets: Record<string, typeof records> = {}
    for (const r of visibleRecords) {
      const bucket = buckets[r.status] ?? []
      bucket.push(r)
      buckets[r.status] = bucket
    }
    return buckets
  }, [visibleRecords])

  // Status columns/options relevant to the current tab. On Active, a resolved
  // status appears only while it still has lingering (≤72h) records.
  const tabStatusOptions = STATUS_FILTER_OPTIONS.filter((o) =>
    tab === 'archive'
      ? isResolved(o.value)
      : !isResolved(o.value) || (recordsByStatus[o.value]?.length ?? 0) > 0,
  )

  // Client-side sort of the list view (Kanban stays grouped by status).
  const sortedVisible = useMemo(
    () => [...visibleRecords].sort((a, b) => compareRecords(a, b, sortBy, sortDir)),
    [visibleRecords, sortBy, sortDir],
  )
  const toggleSort = (key: SortKey) => {
    if (sortBy === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortBy(key); setSortDir('asc') }
  }

  // Client-side pagination of the list view (Kanban renders all columns).
  const pageCount = Math.max(1, Math.ceil(sortedVisible.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const pagedRecords = view === 'list'
    ? sortedVisible.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)
    : sortedVisible
  // Reset to page 1 whenever the filtered set or the sort changes.
  useEffect(() => { setPage(1) }, [status, acquisitionType, q, companySel, tab, view, sortBy, sortDir])

  const isDeletable = (r: BuybackRecord) =>
    DELETABLE_STATUSES.includes(r.status) && r.carpark_vehicle_id == null
  // A global admin may delete ANY record from the Archive (backend allows it
  // for can_access_settings); everyone else keeps the status/CarPark gate.
  const canDeleteRecord = (r: BuybackRecord) =>
    isDeletable(r) || (isAdmin && tab === 'archive')

  const deleteMutation = useMutation({
    mutationFn: (id: number) => buybackApi.deleteRecord(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
      toast.success('Solicitarea a fost ștearsă')
      setDeleteTarget(null)
    },
    onError: (e) => toast.error((e as { data?: { error?: string } })?.data?.error || 'Ștergerea a eșuat'),
  })

  const goToRecord = (id: number) => navigate(`/app/buyback/${id}`)
  const onRecordKeyDown = (e: React.KeyboardEvent, id: number) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      goToRecord(id)
    }
  }

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">BuyBack / TradeIn</h1>
        <div className="flex items-center gap-2">
          {companies.length > 1 && (
            <Select
              value={companySel === ALL_COMPANIES ? ALL_COMPANIES : String(companySel ?? ownCompanyId ?? '')}
              onValueChange={(v) => selectCompany(v === ALL_COMPANIES ? ALL_COMPANIES : Number(v))}
            >
              <SelectTrigger className="h-9 w-[200px]">
                <SelectValue placeholder="Companie" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_COMPANIES}>Toate companiile</SelectItem>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <div className="flex items-center rounded-md border p-0.5">
            <Button
              variant={view === 'list' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 px-2"
              onClick={() => setView('list')}
              title="Vizualizare listă"
            >
              <ListIcon className="h-4 w-4" />
            </Button>
            <Button
              variant={view === 'kanban' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 px-2"
              onClick={() => setView('kanban')}
              title="Vizualizare Kanban"
            >
              <LayoutGrid className="h-4 w-4" />
            </Button>
          </div>
          {canCreate && (
            <Button size="sm" onClick={() => navigate('/app/buyback/new')}>
              <Plus className="h-4 w-4" />
              Solicitare nouă
            </Button>
          )}
        </div>
      </div>

      {/* Active vs Arhivă (resolved) tabs. Switching resets the status filter
          so a status from the other tab can't leave the list empty. */}
      <div className="flex w-fit items-center gap-1 rounded-md border p-0.5">
        <Button
          variant={tab === 'active' ? 'secondary' : 'ghost'}
          size="sm"
          className="h-7"
          onClick={() => { setTab('active'); setStatus('all') }}
        >
          Active <span className="ml-1 text-xs text-muted-foreground">{activeCount}</span>
        </Button>
        <Button
          variant={tab === 'archive' ? 'secondary' : 'ghost'}
          size="sm"
          className="h-7"
          onClick={() => { setTab('archive'); setStatus('all') }}
        >
          Arhivă <span className="ml-1 text-xs text-muted-foreground">{archiveCount}</span>
        </Button>
      </div>

      {/* Toolbar: count chips on the left, filters aligned right, all inline. */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{visibleRecords.length} solicitări</Badge>
          {/* Per-status chips only make sense with no status filter — a selected
              status collapses them to one chip that just repeats the total. */}
          {status === 'all' &&
            tabStatusOptions.map((opt) => {
              const count = recordsByStatus[opt.value]?.length ?? 0
              if (!count) return null
              return (
                <Badge key={opt.value} className={recordStatus(opt.value).badgeClass}>
                  {count} {opt.label.toLowerCase()}
                </Badge>
              )
            })}
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-9 w-[180px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toate stările</SelectItem>
              {tabStatusOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={acquisitionType} onValueChange={setAcquisitionType}>
            <SelectTrigger className="h-9 w-[160px]">
              <SelectValue placeholder="Tip achiziție" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toate tipurile</SelectItem>
              {ACQUISITION_TYPE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="w-[200px] sm:w-[240px]">
            <SearchInput value={q} onChange={setQ} placeholder="Caută cod, VIN, vânzător..." />
          </div>
        </div>
      </div>

      {isLoading ? (
        <TableSkeleton rows={8} columns={8} />
      ) : isError ? (
        <EmptyState
          icon={<Car className="h-10 w-10" />}
          title="Eroare la încărcarea solicitărilor"
          description="Nu am putut încărca lista. Verifică conexiunea și încearcă din nou."
        />
      ) : !visibleRecords.length ? (
        <EmptyState icon={<Car className="h-10 w-10" />} title={tab === 'archive' ? 'Arhivă goală' : 'Nicio solicitare'} description={tab === 'archive' ? 'Nu există solicitări rezolvate (achiziționate, pierdute sau anulate) pentru filtrele curente.' : 'Nu există solicitări BuyBack / TradeIn active pentru filtrele curente.'} />
      ) : view === 'kanban' ? (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {tabStatusOptions.map((col) => {
            const colRecords = recordsByStatus[col.value] ?? []
            const rs = recordStatus(col.value)
            return (
              <div key={col.value} className="w-72 shrink-0">
                <div className="mb-2 flex items-center justify-between px-1">
                  <Badge className={rs.badgeClass}>{col.label}</Badge>
                  <span className="text-xs text-muted-foreground">{colRecords.length}</span>
                </div>
                <div className={`min-h-[80px] space-y-2 rounded-md border p-2 ${rs.rowClass}`}>
                  {colRecords.map((r) => (
                    <Card
                      key={r.id}
                      role="button"
                      tabIndex={0}
                      className="cursor-pointer space-y-1 p-3 hover:bg-muted/40"
                      onClick={() => goToRecord(r.id)}
                      onKeyDown={(e) => onRecordKeyDown(e, r.id)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium leading-tight">{`${r.brand} ${r.model}`}</span>
                        <span className="font-mono text-[10px] text-muted-foreground">{r.record_code}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">{r.seller_name || '—'}</div>
                      <div className="flex items-center justify-between text-xs">
                        <span>{r.client_asking_price_eur != null ? `${r.client_asking_price_eur.toLocaleString('ro-RO')} €` : '—'}</span>
                        {r.purchase_price_eur != null && (
                          <span className="font-medium text-green-600">{r.purchase_price_eur.toLocaleString('ro-RO')} €</span>
                        )}
                      </div>
                    </Card>
                  ))}
                  {!colRecords.length && <div className="py-6 text-center text-xs text-muted-foreground">—</div>}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <Card className="overflow-hidden py-0">
          <Table>
            <TableHeader>
              <TableRow>
                {COLUMNS.map((col) => (
                  <TableHead key={col.key} className={col.align === 'right' ? 'text-right' : undefined}>
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      className="inline-flex items-center gap-1 whitespace-nowrap font-medium hover:text-foreground"
                    >
                      {col.label}
                      {sortBy === col.key ? (
                        sortDir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
                      ) : (
                        <ArrowUpDown className="h-3 w-3 opacity-30" />
                      )}
                    </button>
                  </TableHead>
                ))}
                {canDeleteAny && <TableHead className="w-10" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {pagedRecords.map((r) => {
                const rs = recordStatus(r.status)
                return (
                  <TableRow
                    key={r.id}
                    role="button"
                    tabIndex={0}
                    className={`cursor-pointer hover:bg-muted/40 ${rs.rowClass}`}
                    onClick={() => goToRecord(r.id)}
                    onKeyDown={(e) => onRecordKeyDown(e, r.id)}
                  >
                    <TableCell className="font-mono text-xs">{r.record_code}</TableCell>
                    <TableCell className="text-sm font-medium">{`${r.brand} ${r.model}`}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{r.vin}</TableCell>
                    <TableCell className="text-sm">{r.seller_name || '—'}</TableCell>
                    <TableCell className="text-right text-sm whitespace-nowrap">
                      {r.client_asking_price_eur != null ? r.client_asking_price_eur.toLocaleString('ro-RO') : '—'}
                    </TableCell>
                    <TableCell className="text-right text-sm whitespace-nowrap">
                      {r.purchase_price_eur != null ? r.purchase_price_eur.toLocaleString('ro-RO') : '—'}
                    </TableCell>
                    <TableCell>
                      <Badge className={rs.badgeClass}>{rs.label}</Badge>
                    </TableCell>
                    <TableCell className="text-sm">{r.advisor_name || '—'}</TableCell>
                    <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
                      {new Date(r.created_at).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })}
                    </TableCell>
                    {canDeleteAny && (
                      <TableCell className="w-10 text-right" onClick={(e) => e.stopPropagation()}>
                        {canDeleteRecord(r) && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-muted-foreground hover:text-destructive"
                            onClick={() => setDeleteTarget(r)}
                            title="Șterge solicitarea"
                            aria-label="Șterge solicitarea"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* Pagination — list view only (Kanban shows all). */}
      {view === 'list' && !isLoading && !isError && visibleRecords.length > PAGE_SIZE && (
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="text-muted-foreground">
            {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, visibleRecords.length)} din {visibleRecords.length}
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={safePage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              Înapoi
            </Button>
            <span className="text-muted-foreground">{safePage} / {pageCount}</span>
            <Button variant="outline" size="sm" disabled={safePage >= pageCount} onClick={() => setPage((p) => Math.min(pageCount, p + 1))}>
              Înainte
            </Button>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      <Dialog open={!!deleteTarget} onOpenChange={(o) => { if (!o) setDeleteTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Șterge solicitarea</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Sigur ștergi solicitarea <span className="font-mono">{deleteTarget?.record_code}</span>
            {deleteTarget ? ` (${deleteTarget.brand} ${deleteTarget.model})` : ''}? Acțiunea este permanentă.
          </p>
          {deleteTarget?.carpark_vehicle_id != null && (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-700 dark:text-amber-400">
              Această solicitare a fost predată în CarPark. Se șterge doar înregistrarea BuyBack (ofertele, pozele și istoricul ei); vehiculul din CarPark rămâne neatins.
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Renunță</Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            >
              Șterge
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
