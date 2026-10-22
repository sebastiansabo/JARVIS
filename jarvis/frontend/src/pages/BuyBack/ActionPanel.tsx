import { lazy, Suspense, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { buybackApi } from '@/api/buyback'
import { usePermissions } from './usePermissions'
import StatusChangeDialog from './StatusChangeDialog'
import { pickLatestOffer } from './offerUtils'
import type { BuybackRecord, BuybackOffer, CustodyAgreementInput } from '@/types/buyback'
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

// Drawn seller signature captured at accept (reused from the Test-Drive flow);
// lazy so its canvas lib doesn't weigh on the panel until the dialog opens.
const SignatureCanvas = lazy(() => import('@/components/shared/SignatureCanvas'))

const TERMINAL_STATUSES = ['BOUGHT', 'CONSIGNAT', 'LOST', 'CANCELLED']

function errMsg(e: unknown, fallback: string): string {
  const data = (e as { data?: { error?: string } } | undefined)?.data
  if (data?.error) return data.error
  if (e instanceof Error && e.message) return e.message
  return fallback
}

// Shared agreement-terms field grid, used by BOTH the custody-transfer dialog
// (LOST → CarPark) and the consignment-proposal dialog (Propune consignație at
// PENDING_EVALUATION) — identical inputs, different submit action.
function AgreementFields({
  value,
  onChange,
}: {
  value: CustodyAgreementInput
  onChange: (v: CustodyAgreementInput) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Label className="text-xs">
        Preț proprietar (€)
        <Input
          type="number"
          value={value.owner_price ?? ''}
          onChange={(e) => onChange({ ...value, owner_price: e.target.value === '' ? null : Number(e.target.value) })}
        />
      </Label>
      <Label className="text-xs">
        Comision
        <Select
          value={value.commission_type}
          onValueChange={(v) => onChange({ ...value, commission_type: v as 'percent' | 'fixed' })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="percent">Procent %</SelectItem>
            <SelectItem value="fixed">Sumă fixă €</SelectItem>
          </SelectContent>
        </Select>
      </Label>
      <Label className="text-xs">
        Valoare comision
        <Input
          type="number"
          value={value.commission_value}
          onChange={(e) => onChange({ ...value, commission_value: Number(e.target.value) })}
        />
      </Label>
      <Label className="text-xs">
        Preț minim (€)
        <Input
          type="number"
          value={value.min_sale_price ?? ''}
          onChange={(e) => onChange({ ...value, min_sale_price: e.target.value === '' ? null : Number(e.target.value) })}
        />
      </Label>
      <Label className="text-xs">
        Nr. contract
        <Input
          value={value.contract_number ?? ''}
          onChange={(e) => onChange({ ...value, contract_number: e.target.value })}
        />
      </Label>
      <Label className="text-xs">
        Data acord
        <Input
          type="date"
          value={value.agreement_date ?? ''}
          onChange={(e) => onChange({ ...value, agreement_date: e.target.value || null })}
        />
      </Label>
      <Label className="text-xs">
        Data expirare
        <Input
          type="date"
          value={value.expiry_date ?? ''}
          onChange={(e) => onChange({ ...value, expiry_date: e.target.value || null })}
        />
      </Label>
    </div>
  )
}

export default function ActionPanel({ record, offers }: { record: BuybackRecord; offers: BuybackOffer[] }) {
  const queryClient = useQueryClient()
  // Reopen mirrors the backend's role-only _is_admin() gate (admin/superadmin/Manager);
  // there is NO buyback.record.reopen permission, so an Acquisition user holding
  // buyback.record.finalize must NOT see it (would 403 on click).
  const { isAdminOrManager, can } = usePermissions()

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['buyback-record', record.id] })
    queryClient.invalidateQueries({ queryKey: ['buyback-records'] })
  }

  const status = record.status
  const showInitialOffer = status === 'PENDING_EVALUATION' && can('buyback.offer.manage')
  // Propose a consignment from PENDING_EVALUATION — same offer-manage authority
  // as posting a buy offer (both are the acquisition advisor's call).
  const showProposeConsignment = status === 'PENDING_EVALUATION' && can('buyback.offer.manage')
  const showDecision =
    (status === 'INITIAL_OFFER' || status === 'FINAL_OFFER' || status === 'CONSIGNMENT_OFFER') &&
    can('buyback.record.edit')
  const showInspection = status === 'INSPECTION' && can('buyback.inspection.manage')
  const showFinalOfferButton = status === 'INSPECTION' && can('buyback.offer.manage')
  // Correct an already-posted final price: re-open the final-offer dialog while
  // the record is still FINAL_OFFER (seller hasn't decided yet). Same
  // offer-manage authority as posting it; the backend supersedes the pending
  // final offer and keeps the record in FINAL_OFFER.
  const showCorrectFinal = status === 'FINAL_OFFER' && can('buyback.offer.manage')
  const showFinalize = status === 'BOUGHT' && !record.carpark_vehicle_id && can('buyback.record.finalize')
  const showCarparkLabel = status === 'BOUGHT' && !!record.carpark_vehicle_id
  const showCancel = can('buyback.record.edit') && !TERMINAL_STATUSES.includes(status)
  // Reopen (→ PENDING_EVALUATION) for the two "didn't buy" outcomes. CANCELLED
  // joins LOST now that the lifecycle allows CANCELLED → PENDING_EVALUATION.
  // A LOST record already transferred into custody (carpark_vehicle_id set)
  // can no longer be reopened — the vehicle now lives in CarPark.
  const showReopen = (status === 'LOST' || status === 'CANCELLED') && isAdminOrManager && !record.carpark_vehicle_id
  // Free status override (any → any, bypassing the state machine) — the
  // admin/manager escape hatch, always available to them regardless of status.
  const showOverride = isAdminOrManager
  // Hold/Resume — only from the "active" statuses, gated by the same
  // explicit permission in both directions.
  const showHold =
    ['PENDING_EVALUATION', 'INITIAL_OFFER', 'INSPECTION', 'FINAL_OFFER'].includes(status) &&
    can('buyback.record.hold')
  const showResume = status === 'ON_HOLD' && can('buyback.record.hold')
  // Custody transfer: a LOST record (client declined / didn't sell) not yet
  // handed off to CarPark can be placed into custody for consignment resale.
  const showCustody = status === 'LOST' && !record.carpark_vehicle_id && can('buyback.record.custody')
  const showCustodyLink = status === 'LOST' && !!record.carpark_vehicle_id
  // Accepted consignment proposal: the car now lives in CarPark on consignment.
  const showConsignatLink = status === 'CONSIGNAT' && !!record.carpark_vehicle_id
  // Render the company×brand contract template into a PDF attached to the
  // record (Documente). Available once there's an agreed price to contract
  // (Contract generation/editing lives in the dedicated ContractCard rendered
  // under this panel in BuyBackDetail, not here.)
  const nothingToShow =
    !showInitialOffer &&
    !showProposeConsignment &&
    !showDecision &&
    !showInspection &&
    !showFinalOfferButton &&
    !showCorrectFinal &&
    !showFinalize &&
    !showCarparkLabel &&
    !showCancel &&
    !showReopen &&
    !showOverride &&
    !showHold &&
    !showResume &&
    !showCustody &&
    !showCustodyLink &&
    !showConsignatLink

  // ── offer dialog (shared by "initial" + "final") ──
  const [offerDialogType, setOfferDialogType] = useState<'initial' | 'final' | null>(null)
  const [offerAmount, setOfferAmount] = useState('')
  const [offerVat, setOfferVat] = useState('')
  const [offerValidUntil, setOfferValidUntil] = useState('')
  const [offerNotes, setOfferNotes] = useState('')
  // Preț Piață (retail) — the acquisition team researches/sets it when posting
  // the offer; pre-filled from the record when the dialog opens.
  const [offerMarketPrice, setOfferMarketPrice] = useState('')
  useEffect(() => {
    if (offerDialogType) {
      setOfferMarketPrice(record.market_price_eur != null ? String(record.market_price_eur) : '')
    }
  }, [offerDialogType, record.market_price_eur])

  // The final-offer dialog is a CORRECTION (not a first post) whenever it's
  // opened while the record is already FINAL_OFFER — the only entry point then
  // is the "Corectează oferta finală" button (the plain post button shows only
  // in INSPECTION). Drives the dialog title + success toast copy.
  const correctingFinal = offerDialogType === 'final' && status === 'FINAL_OFFER'

  // ── hold / resume ──
  const [holdOpen, setHoldOpen] = useState(false)
  const [holdReason, setHoldReason] = useState('')
  const [holdNote, setHoldNote] = useState('')

  const { data: opts } = useQuery({
    queryKey: ['buyback-options'],
    queryFn: () => buybackApi.getLookupOptions(),
    staleTime: 5 * 60_000,
    enabled: offerDialogType !== null || holdOpen,
  })

  const resetOfferForm = () => {
    setOfferAmount('')
    setOfferVat('')
    setOfferValidUntil('')
    setOfferNotes('')
    setOfferMarketPrice('')
  }

  // Open the final-offer dialog pre-filled with the current pending offer's
  // amount/VAT so a manager can correct the agreed price (e.g. after the ETB
  // evaluation changes it) instead of re-typing from scratch.
  const openCorrectFinal = () => {
    setOfferAmount(pendingOffer?.amount_eur != null ? String(pendingOffer.amount_eur) : '')
    setOfferVat(pendingOffer?.vat_status ?? '')
    setOfferValidUntil('')
    setOfferNotes('')
    setOfferDialogType('final')
  }

  const postOfferMutation = useMutation({
    mutationFn: () =>
      buybackApi.postOffer(record.id, {
        offer_type: offerDialogType as 'initial' | 'final',
        amount_eur: Number(offerAmount),
        vat_status: offerVat || undefined,
        valid_until: offerValidUntil || undefined,
        notes: offerNotes || undefined,
        market_price_eur: offerMarketPrice.trim() !== '' ? Number(offerMarketPrice) : undefined,
      }),
    onSuccess: () => {
      toast.success(correctingFinal ? 'Prețul ofertei finale a fost corectat' : 'Oferta a fost postată')
      invalidate()
      setOfferDialogType(null)
      resetOfferForm()
    },
    onError: (e) => toast.error(errMsg(e, correctingFinal ? 'Corectarea prețului a eșuat' : 'Postarea ofertei a eșuat')),
  })

  // ── client decision (accept / decline) ──
  const [declineDialogOpen, setDeclineDialogOpen] = useState(false)
  const [declineReason, setDeclineReason] = useState('')
  const pendingOffer = pickLatestOffer(offers, (o) => o.client_decision === 'pending')
  // A pending consignment proposal drives a slightly different decision UI:
  // the proposed terms are shown and the accept/decline labels name it.
  const isConsignmentDecision = pendingOffer?.offer_type === 'consignment'
  const terms = pendingOffer?.consignment_terms ?? null

  const [acceptSigOpen, setAcceptSigOpen] = useState(false)
  const [acceptSignature, setAcceptSignature] = useState('')

  const decisionMutation = useMutation({
    mutationFn: (data: { decision: 'accepted' | 'declined'; decline_reason?: string; signature?: string }) => {
      if (!pendingOffer) throw new Error('Nicio ofertă în așteptare')
      return buybackApi.recordDecision(record.id, pendingOffer.id, data)
    },
    onSuccess: () => {
      toast.success('Decizia a fost înregistrată')
      invalidate()
      setDeclineDialogOpen(false)
      setDeclineReason('')
      setAcceptSigOpen(false)
      setAcceptSignature('')
    },
    onError: (e) => toast.error(errMsg(e, 'Înregistrarea deciziei a eșuat')),
  })

  // ── inspection ──
  const [rating, setRating] = useState(record.inspection_rating != null ? String(record.inspection_rating) : '')
  const [reconditioningCost, setReconditioningCost] = useState(
    record.reconditioning_cost_eur != null ? String(record.reconditioning_cost_eur) : ''
  )
  const [inspectionNotes, setInspectionNotes] = useState(record.inspection_notes ?? '')

  // Seed the inputs once per record (first mount / navigating to a different
  // record). Deliberately NOT keyed on updated_at: an unrelated refetch that
  // bumps updated_at (e.g. a photo upload, or another user's mutation) must not
  // wipe the inspector's in-progress edits. Our own save reseeds these from the
  // server response in saveInspectionMutation.onSuccess below.
  useEffect(() => {
    setRating(record.inspection_rating != null ? String(record.inspection_rating) : '')
    setReconditioningCost(record.reconditioning_cost_eur != null ? String(record.reconditioning_cost_eur) : '')
    setInspectionNotes(record.inspection_notes ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [record.id])

  const saveInspectionMutation = useMutation({
    mutationFn: () =>
      buybackApi.saveInspection(record.id, {
        inspection_rating: rating ? Number(rating) : undefined,
        reconditioning_cost_eur: reconditioningCost ? Number(reconditioningCost) : undefined,
        inspection_notes: inspectionNotes || undefined,
      }),
    onSuccess: (res) => {
      // Reseed from the server's canonical values (coerced rating / decimals)
      // so the inputs reflect what was persisted — the record.id-only effect
      // above won't resync on the refetch this invalidate triggers.
      const rec = (res as { record?: BuybackRecord }).record
      if (rec) {
        setRating(rec.inspection_rating != null ? String(rec.inspection_rating) : '')
        setReconditioningCost(rec.reconditioning_cost_eur != null ? String(rec.reconditioning_cost_eur) : '')
        setInspectionNotes(rec.inspection_notes ?? '')
      }
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

  // ── custody transfer (LOST → CarPark consignment) ──
  const [custodyOpen, setCustodyOpen] = useState(false)
  const [custody, setCustody] = useState<CustodyAgreementInput>({ commission_type: 'percent', commission_value: 0 })
  const custodyMutation = useMutation({
    mutationFn: () => buybackApi.transferToCustody(record.id, custody),
    onSuccess: (res) => {
      toast.success(`Transferat în custodie → CarPark #${res.vehicle.id}`)
      setCustodyOpen(false)
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Transferul în custodie a eșuat')),
  })

  // ── consignment proposal (Propune consignație, PENDING_EVALUATION → CONSIGNMENT_OFFER) ──
  const [proposeOpen, setProposeOpen] = useState(false)
  const [proposal, setProposal] = useState<CustodyAgreementInput>({ commission_type: 'percent', commission_value: 0 })
  const proposeMutation = useMutation({
    mutationFn: () => buybackApi.proposeConsignment(record.id, proposal),
    onSuccess: () => {
      toast.success('Propunere de consignație trimisă')
      setProposeOpen(false)
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Propunerea de consignație a eșuat')),
  })

  // ── status override (admin/manager escape hatch) ──
  const [overrideOpen, setOverrideOpen] = useState(false)

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

  const holdMutation = useMutation({
    mutationFn: () => buybackApi.hold(record.id, { reason: holdReason, note: holdNote || undefined }),
    onSuccess: () => {
      toast.success('Solicitare suspendată')
      setHoldOpen(false)
      setHoldReason('')
      setHoldNote('')
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Suspendarea a eșuat')),
  })

  const resumeMutation = useMutation({
    mutationFn: () => buybackApi.resume(record.id),
    onSuccess: () => {
      toast.success('Solicitare reluată')
      invalidate()
    },
    onError: (e) => toast.error(errMsg(e, 'Reluarea a eșuat')),
  })

  const offerDialogTitle = correctingFinal
    ? 'Corectează oferta finală'
    : offerDialogType === 'final'
      ? 'Ofertă finală'
      : 'Ofertă inițială'

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Acțiuni</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {nothingToShow && <p className="text-sm text-muted-foreground">Nicio acțiune disponibilă.</p>}

        {(showInitialOffer || showProposeConsignment) && (
          <div className="flex flex-wrap gap-2">
            {showInitialOffer && (
              <Button size="sm" onClick={() => setOfferDialogType('initial')}>
                Postează ofertă inițială
              </Button>
            )}
            {showProposeConsignment && (
              <Button size="sm" variant="outline" onClick={() => setProposeOpen(true)}>
                Propune consignație
              </Button>
            )}
          </div>
        )}

        {showDecision && (
          <div className="space-y-2">
            {isConsignmentDecision && terms && (
              <div className="space-y-0.5 rounded-md border border-border p-2 text-xs">
                <p className="font-medium">Termeni consignație propuși</p>
                <p>Preț proprietar: {terms.owner_price != null ? `${terms.owner_price} €` : '—'}</p>
                <p>
                  Comision:{' '}
                  {terms.commission_type === 'percent'
                    ? `${terms.commission_value}%`
                    : `${terms.commission_value} €`}
                </p>
                <p>Preț minim: {terms.min_sale_price != null ? `${terms.min_sale_price} €` : '—'}</p>
                {terms.contract_number && <p>Nr. contract: {terms.contract_number}</p>}
                {(terms.agreement_date || terms.expiry_date) && (
                  <p>Valabil: {terms.agreement_date ?? '—'} → {terms.expiry_date ?? '—'}</p>
                )}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={!pendingOffer || decisionMutation.isPending}
                onClick={() => setAcceptSigOpen(true)}
              >
                {isConsignmentDecision ? 'Acceptă consignația' : 'Client a acceptat'}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!pendingOffer || decisionMutation.isPending}
                onClick={() => setDeclineDialogOpen(true)}
              >
                {isConsignmentDecision ? 'Refuză consignația' : 'Client a refuzat'}
              </Button>
            </div>
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

        {showCorrectFinal && (
          <Button size="sm" variant="outline" onClick={openCorrectFinal}>
            Corectează oferta finală
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

        {showCustody && (
          <Button size="sm" variant="outline" onClick={() => setCustodyOpen(true)}>
            Transferă în custodie
          </Button>
        )}

        {showCustodyLink && (
          <p className="text-sm text-muted-foreground">Transferat în Custodie → CarPark #{record.carpark_vehicle_id}</p>
        )}

        {showConsignatLink && (
          <p className="text-sm text-muted-foreground">Consignat → CarPark #{record.carpark_vehicle_id}</p>
        )}

        {/* Utility actions — grouped below a divider and kept quiet so they
            don't compete with the primary workflow action. Anulează is the
            only destructive one: a restrained ghost, not a solid red block. */}
        {(showOverride || showHold || showCancel) && (
          <div className="flex flex-wrap items-center gap-2 border-t pt-3">
            {showOverride && (
              <Button size="sm" variant="outline" onClick={() => setOverrideOpen(true)}>
                Schimbă status
              </Button>
            )}
            {showHold && (
              <Button size="sm" variant="outline" onClick={() => setHoldOpen(true)}>
                Suspendă
              </Button>
            )}
            {showCancel && (
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                onClick={() => setCancelDialogOpen(true)}
              >
                Anulează
              </Button>
            )}
          </div>
        )}

        {showResume && (
          <Button size="sm" disabled={resumeMutation.isPending} onClick={() => resumeMutation.mutate()}>
            Reia
          </Button>
        )}
      </CardContent>

      <StatusChangeDialog record={record} open={overrideOpen} onOpenChange={setOverrideOpen} />

      {/* Accept + capture the seller's drawn signature; it's embedded in the
          contract auto-generated on accept. Signature is optional — the advisor
          can continue without it (placeholder in the PDF). */}
      <Dialog
        open={acceptSigOpen}
        onOpenChange={(o) => {
          setAcceptSigOpen(o)
          if (!o) setAcceptSignature('')
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{isConsignmentDecision ? 'Acceptă consignația' : 'Client a acceptat'}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Semnătura vânzătorului (opțional) — se include în contractul generat automat.
          </p>
          <div className="flex justify-center">
            <Suspense fallback={<div className="py-8 text-sm text-muted-foreground">Se încarcă…</div>}>
              <SignatureCanvas
                onSave={setAcceptSignature}
                onClear={() => setAcceptSignature('')}
                width={460}
                height={180}
              />
            </Suspense>
          </div>
          <DialogFooter>
            <Button
              variant="ghost"
              disabled={decisionMutation.isPending}
              onClick={() => decisionMutation.mutate({ decision: 'accepted' })}
            >
              Continuă fără semnătură
            </Button>
            <Button
              disabled={decisionMutation.isPending}
              onClick={() => decisionMutation.mutate({ decision: 'accepted', signature: acceptSignature || undefined })}
            >
              Confirmă acceptarea
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
              <Label className="text-xs">Preț Piață — valoare de piață (€)</Label>
              <Input
                type="number"
                inputMode="numeric"
                min={0}
                value={offerMarketPrice}
                onChange={(e) => setOfferMarketPrice(e.target.value)}
                placeholder="Valoare de piață (retail)"
              />
              <p className="text-xs text-muted-foreground">Apare pe oferta trimisă vânzătorului.</p>
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
            <DialogTitle>{isConsignmentDecision ? 'Client a refuzat consignația' : 'Client a refuzat oferta'}</DialogTitle>
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

      {/* Hold dialog */}
      <Dialog
        open={holdOpen}
        onOpenChange={(o) => {
          setHoldOpen(o)
          if (!o) {
            setHoldReason('')
            setHoldNote('')
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Suspendă solicitarea</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Motiv</Label>
              <Select value={holdReason} onValueChange={setHoldReason}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Alege motivul" />
                </SelectTrigger>
                <SelectContent>
                  {(opts?.hold_reasons ?? []).map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notă (opțional)</Label>
              <Textarea rows={3} value={holdNote} onChange={(e) => setHoldNote(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setHoldOpen(false)}>
              Renunță
            </Button>
            <Button disabled={!holdReason || holdMutation.isPending} onClick={() => holdMutation.mutate()}>
              Suspendă
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Custody transfer agreement dialog */}
      <Dialog open={custodyOpen} onOpenChange={setCustodyOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Transfer în custodie</DialogTitle>
          </DialogHeader>
          <AgreementFields value={custody} onChange={setCustody} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCustodyOpen(false)}>
              Renunță
            </Button>
            <Button size="sm" disabled={custodyMutation.isPending} onClick={() => custodyMutation.mutate()}>
              Transferă
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Consignment proposal dialog (Propune consignație at PENDING_EVALUATION) */}
      <Dialog open={proposeOpen} onOpenChange={setProposeOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Propune consignație</DialogTitle>
          </DialogHeader>
          <AgreementFields value={proposal} onChange={setProposal} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setProposeOpen(false)}>
              Renunță
            </Button>
            <Button size="sm" disabled={proposeMutation.isPending} onClick={() => proposeMutation.mutate()}>
              Trimite propunerea
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
