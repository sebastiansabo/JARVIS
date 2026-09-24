import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus, Car } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import { useAuth } from '@/hooks/useAuth'
import { recordStatus, STATUS_FILTER_OPTIONS } from './recordStatus'
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

  const isAdmin = ['admin', 'superadmin'].includes((user?.role_name ?? '').toLowerCase())
  const canCreate = isAdmin || !!user?.permissions?.['buyback.record.create']

  const { data, isLoading } = useQuery({
    queryKey: ['buyback-records', { status, acquisition_type: acquisitionType, q }],
    queryFn: () =>
      buybackApi.listRecords({
        status: status !== 'all' ? status : undefined,
        acquisition_type: acquisitionType !== 'all' ? acquisitionType : undefined,
        q: q || undefined,
        per_page: 500,
        sort_by: 'created_at',
        sort_dir: 'DESC',
      }),
    staleTime: 30_000,
  })

  const records = data?.records ?? []
  const countBy = (s: string) => records.filter((r) => r.status === s).length

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">BuyBack / TradeIn</h1>
        {canCreate && (
          <Button size="sm" onClick={() => navigate('/app/buyback/new')}>
            <Plus className="h-4 w-4" />
            Solicitare nouă
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{records.length} solicitări</Badge>
        {STATUS_FILTER_OPTIONS.map((opt) => {
          const count = countBy(opt.value)
          if (!count) return null
          return (
            <Badge key={opt.value} className={recordStatus(opt.value).badgeClass}>
              {count} {opt.label.toLowerCase()}
            </Badge>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
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
      ) : !records.length ? (
        <EmptyState icon={<Car className="h-10 w-10" />} title="Nicio solicitare" description="Nu există solicitări BuyBack / TradeIn pentru filtrele curente." />
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
                    className={`cursor-pointer hover:bg-muted/40 ${rs.rowClass}`}
                    onClick={() => navigate(`/app/buyback/${r.id}`)}
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
