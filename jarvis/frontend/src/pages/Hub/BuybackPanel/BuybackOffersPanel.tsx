import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { buybackApi } from '@/api/buyback'
import { usePermissions } from '@/pages/BuyBack/usePermissions'
import { pickLatestOffer } from '@/pages/BuyBack/offerUtils'
import type { BuybackOffer, BuybackRecord } from '@/types/buyback'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

function errMsg(e: unknown, fallback: string): string {
  const data = (e as { data?: { error?: string } } | undefined)?.data
  if (data?.error) return data.error
  if (e instanceof Error && e.message) return e.message
  return fallback
}

/** Offer/decision actions for the Hub in-panel detail — functionally identical
 *  to the mobile app's OffersPanel: post an offer (PENDING_EVALUATION →
 *  'initial', INSPECTION → 'final') and record the client's accept/decline on
 *  the pending offer (INITIAL_OFFER / FINAL_OFFER). Gated on the web's v2
 *  permissions (buyback.offer.manage / buyback.record.edit), consistent with
 *  the full ActionPanel. No inspection / finalize / cancel / reopen — those
 *  stay in the /app/buyback console. */
export default function BuybackOffersPanel({
  id,
  record,
  offers,
}: {
  id: number
  record: BuybackRecord
  offers: BuybackOffer[]
}) {
  const queryClient = useQueryClient()
  const { can } = usePermissions()

  const { data: opts } = useQuery({
    queryKey: ['buyback-options'],
    queryFn: () => buybackApi.getLookupOptions(),
    staleTime: 300_000,
  })

  const showPostOffer =
    (record.status === 'PENDING_EVALUATION' || record.status === 'INSPECTION') && can('buyback.offer.manage')
  const showDecision =
    (record.status === 'INITIAL_OFFER' || record.status === 'FINAL_OFFER') && can('buyback.record.edit')
  const pending = pickLatestOffer(offers, (o) => o.client_decision === 'pending')

  const [offerOpen, setOfferOpen] = useState(false)
  const [amount, setAmount] = useState('')
  const [vat, setVat] = useState('')
  const [validUntil, setValidUntil] = useState('')
  const [notes, setNotes] = useState('')
  const [offerError, setOfferError] = useState<string | null>(null)

  const [declineOpen, setDeclineOpen] = useState(false)
  const [declineReason, setDeclineReason] = useState('')
  const [decisionError, setDecisionError] = useState<string | null>(null)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['buyback-record', id] })
    queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
  }

  const resetOffer = () => {
    setAmount('')
    setVat('')
    setValidUntil('')
    setNotes('')
  }

  // Open/close reset both dialogs fully so a cancelled attempt never leaves a
  // stale amount, decline reason, or error behind on the next open.
  const openOfferDialog = () => {
    resetOffer()
    setOfferError(null)
    setOfferOpen(true)
  }
  const closeOfferDialog = () => {
    setOfferOpen(false)
    setOfferError(null)
    resetOffer()
  }
  const openDeclineDialog = () => {
    setDeclineReason('')
    setDecisionError(null)
    setDeclineOpen(true)
  }
  const closeDeclineDialog = () => {
    setDeclineOpen(false)
    setDeclineReason('')
    setDecisionError(null)
  }

  const postOfferMutation = useMutation({
    mutationFn: () =>
      buybackApi.postOffer(id, {
        offer_type: record.status === 'INSPECTION' ? 'final' : 'initial',
        amount_eur: Number(amount),
        vat_status: vat || undefined,
        valid_until: validUntil || undefined,
        notes: notes.trim() || undefined,
      }),
    onSuccess: () => {
      invalidate()
      setOfferOpen(false)
      resetOffer()
    },
    onError: (e) => setOfferError(errMsg(e, 'Postarea ofertei a eșuat.')),
  })

  const decisionMutation = useMutation({
    mutationFn: (data: { decision: 'accepted' | 'declined'; decline_reason?: string }) => {
      if (!pending) throw new Error('Nicio ofertă în așteptare.')
      return buybackApi.recordDecision(id, pending.id, data)
    },
    onSuccess: () => {
      invalidate()
      setDeclineOpen(false)
      setDeclineReason('')
    },
    onError: (e) => setDecisionError(errMsg(e, 'Înregistrarea deciziei a eșuat.')),
  })

  if (!showPostOffer && !showDecision) return null

  const submitOffer = () => {
    const n = Number(amount)
    if (!amount.trim() || Number.isNaN(n) || n <= 0) {
      setOfferError('Introdu o sumă validă.')
      return
    }
    setOfferError(null)
    postOfferMutation.mutate()
  }

  return (
    <section className="rounded-lg border bg-card p-4">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Oferte / Acțiuni</p>

      {showPostOffer && (
        <Button size="sm" onClick={openOfferDialog}>
          Postează ofertă
        </Button>
      )}

      {showDecision && (
        <div className="space-y-2">
          {!pending && <p className="text-xs text-muted-foreground">Nicio ofertă în așteptare.</p>}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={!pending || decisionMutation.isPending}
              onClick={() => {
                setDecisionError(null)
                decisionMutation.mutate({ decision: 'accepted' })
              }}
            >
              Client a acceptat
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!pending || decisionMutation.isPending}
              onClick={openDeclineDialog}
            >
              Client a refuzat
            </Button>
          </div>
          {decisionError && <p className="text-xs text-destructive">{decisionError}</p>}
        </div>
      )}

      {/* Post-offer dialog */}
      <Dialog open={offerOpen} onOpenChange={(o) => { if (!o) closeOfferDialog() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Postează ofertă</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Sumă (€)</Label>
              <Input type="number" inputMode="numeric" min={0} value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Status TVA</Label>
              <Select value={vat} onValueChange={setVat}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Alege statusul TVA" />
                </SelectTrigger>
                <SelectContent>
                  {(opts?.vat_statuses ?? []).map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Valabilă până la</Label>
              <Input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Note</Label>
              <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            {offerError && <p className="text-xs text-destructive">{offerError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeOfferDialog}>
              Renunță
            </Button>
            <Button disabled={postOfferMutation.isPending || !amount} onClick={submitOffer}>
              Trimite oferta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Decline dialog */}
      <Dialog open={declineOpen} onOpenChange={(o) => { if (!o) closeDeclineDialog() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Client a refuzat oferta</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label className="text-xs">Motiv (opțional)</Label>
            <Textarea rows={3} value={declineReason} onChange={(e) => setDeclineReason(e.target.value)} />
          </div>
          {decisionError && <p className="text-xs text-destructive">{decisionError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={closeDeclineDialog}>
              Renunță
            </Button>
            <Button
              variant="destructive"
              disabled={decisionMutation.isPending}
              onClick={() => {
                setDecisionError(null)
                decisionMutation.mutate({ decision: 'declined', decline_reason: declineReason.trim() || undefined })
              }}
            >
              Confirmă refuzul
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
