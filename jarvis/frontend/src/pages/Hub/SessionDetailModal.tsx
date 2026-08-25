import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { PlayCircle, RotateCcw, FileDown, Trash2, Clock, Pencil, Phone, Gauge, User2, CalendarDays, MessageSquare, Building2, Route, FileText } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { naiveDate } from '@/lib/naiveDate'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { foiParcursApi } from '@/api/foiParcurs'
import { sessionStatus, internalComment } from '@/pages/FoiParcurs/sessionStatus'
import ModifiedBadge from '@/pages/FoiParcurs/ModifiedBadge'
import EventBadge from '@/pages/FoiParcurs/EventBadge'
import CorrectSessionDialog, { type CorrectionPayload } from '@/pages/FoiParcurs/CorrectSessionDialog'
import ExtendSessionDialog from '@/pages/FoiParcurs/ExtendSessionDialog'
import { useAuthStore } from '@/stores/authStore'
import type { FoiContract, FpVehicle } from '@/types/foiParcurs'

/** Short ro-RO date+time read naively (TD datetimes are naive Bucharest
 *  wall-clock strings serialized as timestamptz — naiveDate strips the zone so
 *  they read exactly as stored, matching the rest of the FoiParcurs module). */
function fmtDateTime(iso?: string | null): string {
  const d = naiveDate(iso)
  return d ? d.toLocaleString('ro-RO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
}

function Field({ label, value, icon, mono }: { label: string; value: string; icon?: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground/70">{icon}{label}</dt>
      <dd className={cn('mt-0.5 truncate font-medium', mono && 'font-mono text-[12px]')}>{value}</dd>
    </div>
  )
}

/**
 * Shared session-detail modal for both driving calendars (Hub DrivingCalendar +
 * desktop CalendarTab). Shows the full session detail and the status-appropriate
 * actions, mirroring the Hub list card:
 *   • Planificat            → Începe sesiunea · Corectează* · Renunță
 *   • În desfășurare / Întârziat → Retur · Descarcă PDF · Prelungește · Corectează*
 *   • Finalizat             → Descarcă PDF · Corectează*
 * (* admin-only, matching DrivingSessionsList.) Discard/Extend/Correct are owned
 * here (identical API mutations in both hosts); the host-specific Începe/Retur
 * flows (Hub overlays vs. foi-parcurs navigation) come in as callbacks.
 */
export default function SessionDetailModal({ session: c, vehicle, onClose, onActivate, onReturn }: {
  session: FoiContract
  vehicle?: FpVehicle
  onClose: () => void
  onActivate: () => void
  onReturn: () => void
}) {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const isAdmin = ['admin', 'superadmin'].includes((user?.role_name ?? '').toLowerCase())
  const [correcting, setCorrecting] = useState(false)
  const [extending, setExtending] = useState(false)

  const ss = sessionStatus(c)
  const isPlanned = ss.key === 'planificat'
  const isDone = ss.key === 'finalizat'
  const showRetur = ss.key === 'driving' || ss.key === 'intarziat'

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['foi-contracts-all'] })
  const discardMutation = useMutation({
    mutationFn: () => foiParcursApi.discardTestDrive(c.id),
    onSuccess: () => { invalidate(); onClose() },
  })
  const correctMutation = useMutation({
    mutationFn: (data: CorrectionPayload) => foiParcursApi.correctSession(c.id, data),
    onSuccess: () => { invalidate(); setCorrecting(false); onClose() },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Corectarea a eșuat'),
  })
  const extendMutation = useMutation({
    mutationFn: (return_datetime: string) => foiParcursApi.extendReturn(c.id, { return_datetime }),
    onSuccess: () => { invalidate(); setExtending(false); onClose() },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Prelungirea a eșuat'),
  })
  // Delete an internal driving-log session (any status, any user). Reuses the
  // admin delete endpoint, which the backend opens to non-admins for internal
  // sessions only. Hard delete — session-event history cascades away.
  const deleteMutation = useMutation({
    mutationFn: () => foiParcursApi.deleteContract(c.id),
    onSuccess: () => { invalidate(); onClose() },
    onError: (e: any) => toast.error(e?.data?.error || e?.message || 'Ștergerea a eșuat'),
  })

  const comment = internalComment(c)
  const tester = c.client_name || (c.client_id != null ? `Client #${c.client_id}` : '—')
  const vehicleName = vehicle
    ? [vehicle.mark, vehicle.model].filter(Boolean).join(' ') || vehicle.registration_number || c.vin
    : c.vin || '—'

  return (
    <>
      <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex flex-wrap items-center gap-2">
              Detalii sesiune
              <Badge className={cn('text-xs', ss.badgeClass)}>{ss.label}</Badge>
              <ModifiedBadge session={c} />
              <EventBadge session={c} />
            </DialogTitle>
          </DialogHeader>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
            <Field label="Client" value={tester} />
            {c.driver_name && <Field label="Șofer" value={c.driver_name} icon={<User2 className="h-3 w-3" />} />}
            {c.client_company && <Field label="Companie" value={c.client_company} icon={<Building2 className="h-3 w-3" />} />}
            <Field label="Telefon" value={c.client_phone || '—'} icon={<Phone className="h-3 w-3" />} />
            <Field label="Consilier" value={c.advisor_name || '—'} icon={<User2 className="h-3 w-3" />} />
            <Field label="Vehicul" value={vehicleName} icon={<Gauge className="h-3 w-3" />} />
            <Field label="VIN" value={c.vin || '—'} mono />
            <Field label="Kilometraj" value={`${c.km_start ?? vehicle?.mileage_floor ?? '—'}${isDone && c.km_end != null ? ` → ${c.km_end}` : ''} km`} />
            {c.distance_km != null && <Field label="Km estimat" value={`${c.distance_km} km`} icon={<Route className="h-3 w-3" />} />}
            <div className="col-span-2">
              <Field label="Perioadă" value={`${fmtDateTime(c.departure_datetime)}${c.return_datetime ? ` – ${fmtDateTime(c.return_datetime)}` : ''}`} icon={<CalendarDays className="h-3 w-3" />} />
            </div>
            {/* Free-text comment on an internal session (the "Comentariu" field) —
                wraps rather than truncates so the full note is readable. */}
            {comment && (
              <div className="col-span-2 min-w-0">
                <dt className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground/70">
                  <MessageSquare className="h-3 w-3" />Comentariu
                </dt>
                <dd className="mt-0.5 whitespace-pre-wrap break-words font-medium">{comment}</dd>
              </div>
            )}
            {c.general_observation && (
              <div className="col-span-2 min-w-0">
                <dt className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground/70">
                  <FileText className="h-3 w-3" />Detalii
                </dt>
                <dd className="mt-0.5 whitespace-pre-wrap break-words font-medium">{c.general_observation}</dd>
              </div>
            )}
          </dl>

          {/* Status-appropriate actions — primary (Începe/Retur) leads, then
              secondary tools. Mirrors the Hub list card's button set. */}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {isPlanned && (
              <Button onClick={onActivate}><PlayCircle className="mr-1.5 h-4 w-4" />Începe sesiunea</Button>
            )}
            {showRetur && (
              <Button onClick={onReturn}><RotateCcw className="mr-1.5 h-4 w-4" />Retur</Button>
            )}
            {!isPlanned && (
              <a href={foiParcursApi.getContractPdfUrl(c.id, 'legal')} target="_blank" rel="noopener">
                <Button variant="outline"><FileDown className="mr-1.5 h-4 w-4" />Descarcă PDF</Button>
              </a>
            )}
            {showRetur && (
              <Button
                variant="outline"
                className="text-amber-700 ring-1 ring-amber-300 hover:bg-amber-50 hover:text-amber-800 dark:text-amber-400 dark:ring-amber-800 dark:hover:bg-amber-950/20"
                onClick={() => setExtending(true)}
              >
                <Clock className="mr-1.5 h-4 w-4" />Prelungește
              </Button>
            )}
            {isAdmin && (
              <Button variant="outline" onClick={() => setCorrecting(true)}>
                <Pencil className="mr-1.5 h-4 w-4" />Corectează
              </Button>
            )}
            {isPlanned && (
              <Button
                variant="outline"
                className="text-destructive ring-1 ring-destructive/30 hover:bg-destructive/10 hover:text-destructive"
                disabled={discardMutation.isPending}
                onClick={() => { if (confirm('Renunți la această sesiune planificată? Acțiunea nu poate fi anulată.')) discardMutation.mutate() }}
              >
                <Trash2 className="mr-1.5 h-4 w-4" />Renunță
              </Button>
            )}
            {/* Internal sessions only — delete the internal driving log (any
                status, any user). Regular Test Drives are never deletable here. */}
            {c.is_internal && (
              <Button
                variant="outline"
                className="text-destructive ring-1 ring-destructive/30 hover:bg-destructive/10 hover:text-destructive"
                disabled={deleteMutation.isPending}
                onClick={() => { if (confirm('Ștergi definitiv această sesiune internă? Acțiunea nu poate fi anulată.')) deleteMutation.mutate() }}
              >
                <Trash2 className="mr-1.5 h-4 w-4" />Șterge
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {correcting && (
        <CorrectSessionDialog
          session={c}
          submitting={correctMutation.isPending}
          onClose={() => setCorrecting(false)}
          onSubmit={(d) => correctMutation.mutate(d)}
        />
      )}
      {extending && (
        <ExtendSessionDialog
          session={c}
          submitting={extendMutation.isPending}
          onClose={() => setExtending(false)}
          onSubmit={(rd) => extendMutation.mutate(rd)}
        />
      )}
    </>
  )
}
