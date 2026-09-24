import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, Plus, Car } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import { recordStatus } from '@/pages/BuyBack/recordStatus'
import BuyBackForm from '@/pages/BuyBack/BuyBackForm'
import type { BuybackRecord } from '@/types/buyback'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/TableSkeleton'

// Compact list of buyback records for the Hub launcher — a lean subset of
// `pages/BuyBack/index.tsx` (no filters) plus a "Solicitare nouă" overlay
// that embeds `BuyBackForm` (mirrors `HubDrivingPanel`'s Overlay pattern,
// just with a single overlay kind since there's only one form here).
type Overlay = null | { kind: 'new' }

export default function HubBuybackPanel({ onBack }: { onBack: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [overlay, setOverlay] = useState<Overlay>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['buyback-records', 'hub'],
    queryFn: () => buybackApi.listRecords({ per_page: 200, sort_by: 'created_at', sort_dir: 'DESC' }),
  })
  const records = data?.records ?? []

  const closeOverlay = () => setOverlay(null)
  const handleDone = (record: BuybackRecord) => {
    queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
    setOverlay(null)
    navigate(`/app/buyback/${record.id}`)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ChevronLeft className="h-4 w-4 mr-1" />Înapoi
        </Button>
        <Button size="sm" onClick={() => setOverlay({ kind: 'new' })}>
          <Plus className="h-4 w-4" />
          Solicitare nouă
        </Button>
      </div>

      {isLoading ? (
        <TableSkeleton rows={6} columns={4} />
      ) : !records.length ? (
        <EmptyState
          icon={<Car className="h-10 w-10" />}
          title="Nicio solicitare"
          description="Nu există solicitări BuyBack / TradeIn încă."
          action={
            <Button size="sm" onClick={() => setOverlay({ kind: 'new' })}>
              <Plus className="h-4 w-4" />
              Solicitare nouă
            </Button>
          }
        />
      ) : (
        <div className="space-y-2">
          {records.map((r) => {
            const rs = recordStatus(r.status)
            return (
              <Card
                key={r.id}
                className={`cursor-pointer p-3 transition-colors hover:bg-muted/40 ${rs.rowClass}`}
                onClick={() => navigate(`/app/buyback/${r.id}`)}
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

      <Dialog open={overlay?.kind === 'new'} onOpenChange={(o) => { if (!o) closeOverlay() }}>
        <DialogContent className="max-w-3xl">
          <DialogTitle className="sr-only">Solicitare nouă BuyBack / TradeIn</DialogTitle>
          <BuyBackForm embedded onDone={handleDone} onCancel={closeOverlay} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
