import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { buybackApi } from '@/api/buyback'
import { useAuth } from '@/hooks/useAuth'
import type { BuybackRecord, BuybackOffer } from '@/types/buyback'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const TERMINAL_STATUSES = ['BOUGHT', 'LOST', 'CANCELLED']

function errMsg(e: unknown, fallback: string): string {
  const data = (e as { data?: { error?: string } } | undefined)?.data
  if (data?.error) return data.error
  if (e instanceof Error && e.message) return e.message
  return fallback
}

function latestPendingOffer(offers: BuybackOffer[]): BuybackOffer | undefined {
  const pending = offers.filter((o) => o.client_decision === 'pending')
  if (!pending.length) return undefined
  return pending.reduce((latest, o) => {
    const oTime = new Date(o.created_at).getTime()
    const latestTime = new Date(latest.created_at).getTime()
    if (oTime !== latestTime) return oTime > latestTime ? o : latest
    return o.id > latest.id ? o : latest
  })
}

export default function ActionPanel({ record, offers }: { record: BuybackRecord; offers: BuybackOffer[] }) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const isAdmin = ['admin', 'superadmin'].includes((user?.role_name ?? '').toLowerCase())
  const can = (k: string) => isAdmin || !!user?.permissions?.[k]

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['buyback-record', record.id] })
    queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
  }

  const status = record.status
  const showInitialOffer = status === 'PENDING_EVALUATION' && can('buyback.offer.manage')
  const showDecision = (status === 'INITIAL_OFFER' || status === 'FINAL_OFFER') && can('buyback.record.edit')
  const showInspection = status === 'INSPECTION' && can('buyback.inspection.manage')
  const showFinalOfferButton = status === 'INSPECTION' && can('buyback.offer.manage')
  const showFinalize = status === 'BOUGHT' && !record.carpark_vehicle_id && can('buyback.record.finalize')
  const showCarparkLabel = status === 'BOUGHT' && !!record.carpark_vehicle_id
  const showCancel = can('buyback.record.edit') && !TERMINAL_STATUSES.includes(status)
  const showReopen = status === 'LOST' && (isAdmin || can('buyback.record.finalize'))

  const nothingToShow =
    !showInitialOffer &&
    !showDecision &&
    !showInspection &&
    !showFinalOfferButton &&
    !showFinalize &&
    !showCarparkLabel &&
    !showCancel &&
    !showReopen

  // ── offer dialog (shared by "initial" + "final") ──
  const [offerDialogType, setOfferDialogType] = useState<'initial' | 'final' | null>(null)
  const [offerAmount, setOfferAmount] = useState('')
  const [offerVat, setOfferVat] = useState('')
  const [offerValidUntil, setOfferValidUntil] = useState('')
  const [offerNotes, setOfferNotes] = useState('')

  const { data: opts } = useQuery({
    queryKey: ['buyback-options'],
    queryFn: () => buybackApi.getLookupOptions(),
    staleTime: 5 * 60_000,
    enabled: offerDialogType !== null,
  })

  const resetOfferForm = () => {
    setOfferAmount('')
    setOfferVat('')
    setOfferValidUntil('')
    setOfferNotes('')
  }

  const postOfferMutation = useMutation({
    mutationFn: () =>
      buybackApi.postOffer(record.id, {
        offer_type: offerDialogType as 'initial' | 'final',
        amount_eur: Number(offerAmount),
        vat_status: offerVat || undefined,
        valid_until: offerValidUntil || undefined,
        notes: offerNotes || undefined,
      }),
    onSuccess: () => {
      toast.success('Oferta a fost postată')
      invalidate()
      setOfferDialogType(null)
      resetOfferForm()
    },
    onError: (e) => toast.error(errMsg(e, 'Postarea ofertei a eșuat')),
  })

  // ── client decision (accept / decline) ──
  const [declineDialogOpen, setDeclineDialogOpen] = useState(false)
  const [declineReason, setDeclineReason] = useState('')
  const pendingOffer = latestPendingOffer(offers)

  const decisionMutation = useMutation({
    mutationFn: (data: { decision: 'accepted' | 'declined'; decline_reason?: string }) => {
      if (!pendingOffer) throw new Error('Nicio ofertă în așteptare')
      return buybackApi.recordDecision(record.id, pendingOffer.id, data)
    },
    onSuccess: () => {
      toast.success('Decizia a fost înregistrată')
      invalidate()
      setDeclineDialogOpen(false)
      setDeclineReason('')
    },
    onError: (e) => toast.error(errMsg(e, 'Înregistrarea deciziei a eșuat')),
  })

  // ── inspection ──
  const [rating, setRating] = useState(record.inspection_rating != null ? String(record.inspection_rating) : '')
  const [reconditioningCost, setReconditioningCost] = useState(
    record.reconditioning_cost_eur != null ? String(record.reconditioning_cost_eur) : ''
  )
  const [inspectionNotes, setInspectionNotes] = useState(record.inspection_notes ?? '')

  const saveInspectionMutation = useMutation({
    mutationFn: () =>
      buybackApi.saveInspection(record.id, {
        inspection_rating: rating ? Number(rating) : undefined,
        reconditioning_cost_eur: reconditioningCost ? Number(reconditioningCost) : undefined,
        inspection_notes: inspectionNotes || undefined,
      }),
    onSuccess: () => {
      toast.success('Inspecția a fost salvată')
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Salvarea inspecției a eșuat')),
  })

  const uploadReportMutation = useMutation({
    mutationFn: (file: File) => buybackApi.uploadInspectionReport(record.id, file),
    onSuccess: () => {
      toast.success('Raportul a fost încărcat')
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Încărcarea raportului a eșuat')),
  })

  // ── finalize / handoff retry ──
  const [handoffError, setHandoffError] = useState<string | null>(null)

  const finalizeMutation = useMutation({
    mutationFn: () => buybackApi.finalize(record.id),
    onSuccess: (res) => {
      invalidate()
      if (res?.handoff_error) {
        setHandoffError(res.handoff_error)
        toast.error(res.handoff_error)
      } else {
        setHandoffError(null)
        toast.success('Vehiculul a fost transferat în CarPark')
      }
    },
    onError: (e) => toast.error(errMsg(e, 'Finalizarea a eșuat')),
  })

  const retryHandoffMutation = useMutation({
    mutationFn: () => buybackApi.retryHandoff(record.id),
    onSuccess: () => {
      toast.success('Transferul a fost reîncercat')
      setHandoffError(null)
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Reîncercarea transferului a eșuat')),
  })

  // ── cancel ──
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false)
  const [cancelReason, setCancelReason] = useState('')

  const cancelMutation = useMutation({
    mutationFn: () => buybackApi.cancelRecord(record.id, cancelReason || undefined),
    onSuccess: () => {
      toast.success('Solicitarea a fost anulată')
      invalidate()
      setCancelDialogOpen(false)
      setCancelReason('')
    },
    onError: (e) => toast.error(errMsg(e, 'Anularea a eșuat')),
  })

  // ── reopen ──
  const reopenMutation = useMutation({
    mutationFn: () => buybackApi.reopenRecord(record.id),
    onSuccess: () => {
      toast.success('Solicitarea a fost redeschisă')
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Redeschiderea a eșuat')),
  })

  const offerDialogTitle = offerDialogType === 'final' ? 'Ofertă finală' : 'Ofertă inițială'

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Acțiuni</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {nothingToShow && <p className="text-sm text-muted-foreground">Nicio acțiune disponibilă.</p>}

        {showInitialOffer && (
          <Button size="sm" onClick={() => setOfferDialogType('initial')}>
            Postează ofertă inițială
          </Button>
        )}

        {showDecision && (
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={!pendingOffer || decisionMutation.isPending}
              onClick={() => decisionMutation.mutate({ decision: 'accepted' })}
            >
              Client a acceptat
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!pendingOffer || decisionMutation.isPending}
              onClick={() => setDeclineDialogOpen(true)}
            >
              Client a refuzat
            </Button>
          </div>
        )}

        {showInspection && (
          <div className="space-y-2 rounded-md border border-border p-3">
            <p className="text-sm font-medium">Inspecție</p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">Rating (1-5)</Label>
                <Input
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={5}
                  value={rating}
                  onChange={(e) => setRating(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Cost recondiționare (€)</Label>
                <Input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  value={reconditioningCost}
                  onChange={(e) => setReconditioningCost(e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Note inspecție</Label>
              <Textarea rows={2} value={inspectionNotes} onChange={(e) => setInspectionNotes(e.target.value)} />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" disabled={saveInspectionMutation.isPending} onClick={() => saveInspectionMutation.mutate()}>
                Salvează inspecția
              </Button>
              <Label className="text-xs">
                Raport PDF
                <Input
                  type="file"
                  accept="application/pdf"
                  className="mt-1"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) uploadReportMutation.mutate(file)
                    e.target.value = ''
                  }}
                />
              </Label>
            </div>
          </div>
        )}

        {showFinalOfferButton && (
          <Button size="sm" onClick={() => setOfferDialogType('final')}>
            Postează ofertă finală
          </Button>
        )}

        {showFinalize && (
          <div className="space-y-2">
            <Button size="sm" disabled={finalizeMutation.isPending} onClick={() => finalizeMutation.mutate()}>
              Finalizează → CarPark
            </Button>
            {handoffError && (
              <div className="space-y-1 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-sm text-destructive">
                <p>{handoffError}</p>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={retryHandoffMutation.isPending}
                  onClick={() => retryHandoffMutation.mutate()}
                >
                  Reîncearcă transferul
                </Button>
              </div>
            )}
          </div>
        )}

        {showCarparkLabel && (
          <p className="text-sm text-muted-foreground">Vehicul creat în CarPark #{record.carpark_vehicle_id}</p>
        )}

        {showReopen && (
          <Button size="sm" disabled={reopenMutation.isPending} onClick={() => reopenMutation.mutate()}>
            Redeschide
          </Button>
        )}

        {showCancel && (
          <Button size="sm" variant="destructive" onClick={() => setCancelDialogOpen(true)}>
            Anulează
          </Button>
        )}
      </CardContent>

      {/* Offer dialog (initial or final, shares the same fields) */}
      <Dialog
        open={offerDialogType !== null}
        onOpenChange={(o) => {
          if (!o) setOfferDialogType(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{offerDialogTitle}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Sumă (€)</Label>
              <Input type="number" inputMode="numeric" min={0} value={offerAmount} onChange={(e) => setOfferAmount(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Status TVA</Label>
              <Select value={offerVat} onValueChange={setOfferVat}>
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
              <Input type="date" value={offerValidUntil} onChange={(e) => setOfferValidUntil(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Note</Label>
              <Textarea rows={2} value={offerNotes} onChange={(e) => setOfferNotes(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOfferDialogType(null)}>
              Renunță
            </Button>
            <Button
              disabled={postOfferMutation.isPending || !offerAmount}
              onClick={() => postOfferMutation.mutate()}
            >
              Trimite oferta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Decline dialog */}
      <Dialog
        open={declineDialogOpen}
        onOpenChange={(o) => {
          setDeclineDialogOpen(o)
          if (!o) setDeclineReason('')
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Client a refuzat oferta</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label className="text-xs">Motiv (opțional)</Label>
            <Textarea rows={3} value={declineReason} onChange={(e) => setDeclineReason(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeclineDialogOpen(false)}>
              Renunță
            </Button>
            <Button
              variant="destructive"
              disabled={decisionMutation.isPending}
              onClick={() => decisionMutation.mutate({ decision: 'declined', decline_reason: declineReason || undefined })}
            >
              Confirmă refuzul
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cancel dialog */}
      <Dialog
        open={cancelDialogOpen}
        onOpenChange={(o) => {
          setCancelDialogOpen(o)
          if (!o) setCancelReason('')
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Anulează solicitarea</DialogTitle>
          </DialogHeader>
          <div className="space-y-1">
            <Label className="text-xs">Motiv (opțional)</Label>
            <Textarea rows={3} value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelDialogOpen(false)}>
              Renunță
            </Button>
            <Button variant="destructive" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
              Confirmă anularea
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
