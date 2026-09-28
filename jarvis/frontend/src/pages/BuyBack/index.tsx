import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, Car, List as ListIcon, LayoutGrid } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import { useAuth } from '@/hooks/useAuth'
import { recordStatus, STATUS_FILTER_OPTIONS } from './recordStatus'
import { usePermissions } from './usePermissions'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { SearchInput } from '@/components/shared/SearchInput'

const ACQUISITION_TYPE_OPTIONS = [
  { value: 'buyback', label: 'Buyback' },
  { value: 'tradein', label: 'Trade-in' },
]

export default function BuyBack() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [status, setStatus] = useState('all')
  const [acquisitionType, setAcquisitionType] = useState('all')
  const [q, setQ] = useState('')
  const [companyId, setCompanyId] = useState<number | null>(null)
  const [view, setView] = useState<'list' | 'kanban'>('list')

  const { can } = usePermissions()
  const canCreate = can('buyback.record.create')

  // Tenant switcher: acting company (defaults to the user's own company).
  const effectiveCompanyId = companyId ?? user?.company_id ?? null
  const { data: companiesData } = useQuery({
    queryKey: ['buyback-companies'],
    queryFn: () => buybackApi.getCompanies(),
    staleTime: 60_000,
  })
  const companies = companiesData?.companies ?? []

  const { data, isLoading, isError } = useQuery({
    queryKey: ['buyback-records', { status, acquisition_type: acquisitionType, q, company_id: effectiveCompanyId }],
    queryFn: () =>
      buybackApi.listRecords({
        status: status !== 'all' ? status : undefined,
        acquisition_type: acquisitionType !== 'all' ? acquisitionType : undefined,
        q: q || undefined,
        company_id: effectiveCompanyId ?? undefined,
        per_page: 500,
        sort_by: 'created_at',
        sort_dir: 'DESC',
      }),
    staleTime: 30_000,
  })

  const records = data?.records ?? []
  // Group once by status; both the count chips and the Kanban columns read
  // from these buckets (avoids a filter pass per status + per column).
  const recordsByStatus = useMemo(() => {
    const buckets: Record<string, typeof records> = {}
    for (const r of records) {
      const bucket = buckets[r.status] ?? []
      bucket.push(r)
      buckets[r.status] = bucket
    }
    return buckets
  }, [records])

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

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{records.length} solicitări</Badge>
        {/* Per-status chips only make sense with no status filter — a selected
            status collapses them to one chip that just repeats the total. */}
        {status === 'all' &&
          STATUS_FILTER_OPTIONS.map((opt) => {
            const count = recordsByStatus[opt.value]?.length ?? 0
            if (!count) return null
            return (
              <Badge key={opt.value} className={recordStatus(opt.value).badgeClass}>
                {count} {opt.label.toLowerCase()}
              </Badge>
            )
          })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {companies.length > 1 && (
          <Select
            value={effectiveCompanyId != null ? String(effectiveCompanyId) : ''}
            onValueChange={(v) => setCompanyId(Number(v))}
          >
            <SelectTrigger className="h-9 w-[220px]">
              <SelectValue placeholder="Companie" />
            </SelectTrigger>
            <SelectContent>
              {companies.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="h-9 w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toate stările</SelectItem>
            {STATUS_FILTER_OPTIONS.map((opt) => (
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
        <div className="min-w-[220px] max-w-xs flex-1">
          <SearchInput value={q} onChange={setQ} placeholder="Caută cod, VIN, vânzător..." />
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
      ) : !records.length ? (
        <EmptyState icon={<Car className="h-10 w-10" />} title="Nicio solicitare" description="Nu există solicitări BuyBack / TradeIn pentru filtrele curente." />
      ) : view === 'kanban' ? (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {STATUS_FILTER_OPTIONS.map((col) => {
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
                <TableHead>Cod</TableHead>
                <TableHead>Vehicul</TableHead>
                <TableHead>VIN</TableHead>
                <TableHead>Vânzător</TableHead>
                <TableHead className="text-right">Preț cerut €</TableHead>
                <TableHead className="text-right">Preț achiziție €</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Consilier</TableHead>
                <TableHead>Creat</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((r) => {
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
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  )
}
