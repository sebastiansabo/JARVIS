import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, Plus, Car, X } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import { recordStatus, STATUS_FILTER_OPTIONS } from '@/pages/BuyBack/recordStatus'
import { usePermissions } from '@/pages/BuyBack/usePermissions'
import BuyBackForm from '@/pages/BuyBack/BuyBackForm'
import BuybackPanelDetail from '@/pages/Hub/BuybackPanel/BuybackPanelDetail'
import type { BuybackRecord } from '@/types/buyback'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { SearchInput } from '@/components/shared/SearchInput'
import { cn } from '@/lib/utils'

// BuyBack for the Hub launcher — functionally identical to the mobile app:
// a filterable list → an in-panel read-only detail with offer/decision
// actions → a "Solicitare nouă" intake overlay (reuses `BuyBackForm`). The
// full back-office console (inspection / finalize / reopen / edit) stays at
// /app/buyback. Mirrors `HubDrivingPanel`'s list↔detail↔overlay structure.
type Overlay = null | { kind: 'new' }

export default function HubBuybackPanel({ onBack }: { onBack: () => void }) {
  const queryClient = useQueryClient()
  const [overlay, setOverlay] = useState<Overlay>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [status, setStatus] = useState<string | undefined>(undefined)
  const [q, setQ] = useState('')

  const { can } = usePermissions()
  const canCreate = can('buyback.record.create')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['buyback-records', 'hub', { status, q }],
    queryFn: () =>
      buybackApi.listRecords({
        status,
        q: q.trim() || undefined,
        per_page: 200,
        sort_by: 'created_at',
        sort_dir: 'DESC',
      }),
    staleTime: 30_000,
  })
  const records = data?.records ?? []

  const goToRecord = (id: number) => setSelectedId(id)
  const onRecordKeyDown = (e: React.KeyboardEvent, id: number) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      goToRecord(id)
    }
  }

  const closeOverlay = () => setOverlay(null)
  const handleDone = (record: BuybackRecord) => {
    queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
    setOverlay(null)
    setSelectedId(record.id)
  }

  // In-panel detail (mobile parity): tapping a record opens it here rather
  // than navigating to the full /app/buyback console.
  if (selectedId != null) {
    return <BuybackPanelDetail id={selectedId} onBack={() => setSelectedId(null)} />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ChevronLeft className="h-4 w-4 mr-1" />Înapoi
        </Button>
        {canCreate && (
          <Button size="sm" onClick={() => setOverlay({ kind: 'new' })}>
            <Plus className="h-4 w-4" />
            Solicitare nouă
          </Button>
        )}
      </div>

      {/* Status filter pills + debounced search — mobile parity. */}
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setStatus(undefined)}
            className={cn(
              'rounded-full px-3 py-1 text-xs font-medium transition-colors',
              status === undefined ? 'bg-primary text-primary-foreground' : 'bg-secondary text-muted-foreground'
            )}
          >
            Toate
          </button>
          {STATUS_FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setStatus(opt.value)}
              className={cn(
                'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                status === opt.value ? recordStatus(opt.value).badgeClass : 'bg-secondary text-muted-foreground'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <SearchInput value={q} onChange={setQ} placeholder="Caută cod, VIN, vânzător..." className="max-w-xs" />
      </div>

      {isLoading ? (
        <TableSkeleton rows={6} columns={4} />
      ) : isError ? (
        <EmptyState
          icon={<Car className="h-10 w-10" />}
          title="Eroare la încărcarea solicitărilor"
          description="Nu am putut încărca lista. Verifică conexiunea și încearcă din nou."
        />
      ) : !records.length ? (
        <EmptyState
          icon={<Car className="h-10 w-10" />}
          title="Nicio solicitare"
          description="Nu există solicitări BuyBack / TradeIn încă."
          action={
            canCreate ? (
              <Button size="sm" onClick={() => setOverlay({ kind: 'new' })}>
                <Plus className="h-4 w-4" />
                Solicitare nouă
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-2">
          {records.map((r) => {
            const rs = recordStatus(r.status)
            return (
              <Card
                key={r.id}
                role="button"
                tabIndex={0}
                className={`cursor-pointer p-3 transition-colors hover:bg-muted/40 ${rs.rowClass}`}
                onClick={() => goToRecord(r.id)}
                onKeyDown={(e) => onRecordKeyDown(e, r.id)}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{r.record_code}</span>
                      <span className="truncate text-sm font-medium">{`${r.brand} ${r.model}`}</span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {r.seller_name || '—'} · {r.vin}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <Badge className={rs.badgeClass}>{rs.label}</Badge>
                    {r.client_asking_price_eur != null && (
                      <span className="text-xs text-muted-foreground">
                        {r.client_asking_price_eur.toLocaleString('ro-RO')} €
                      </span>
                    )}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* iOS-style modal sheet — full-screen on phones, a centered floating
          card on desktop. Mirrors HubDrivingPanel's intake overlay. */}
      {overlay?.kind === 'new' && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 backdrop-blur-sm" onClick={closeOverlay}>
          <div
            className="mx-auto min-h-full w-full max-w-2xl bg-background shadow-2xl sm:my-8 sm:min-h-0 sm:rounded-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 z-10 flex items-center justify-end border-b bg-background/95 p-2 backdrop-blur sm:rounded-t-2xl">
              <Button variant="ghost" size="icon" aria-label="Închide" onClick={closeOverlay}>
                <X className="h-5 w-5" />
              </Button>
            </div>
            <BuyBackForm embedded onDone={handleDone} onCancel={closeOverlay} />
          </div>
        </div>
      )}
    </div>
  )
}
