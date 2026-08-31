import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { foiParcursApi } from '@/api/foiParcurs'
import type { FpVehicle } from '@/types/foiParcurs'
import ScheduleBlockSection from './ScheduleBlockSection'

// Combined vehicle-block modal: a single entry point for BOTH an immediate
// manual lock/unlock ("Blocare imediată") and scheduled future block windows
// ("Blocări programate"). Replaces the previous separate lock + calendar buttons.
export default function LockVehicleDialog({ vehicle, onClose, onSubmit, submitting, onUnlock, unlocking }: {
  vehicle: FpVehicle
  onClose: () => void
  onSubmit: (data: { category: string; note?: string; until?: string | null }) => void
  submitting: boolean
  onUnlock: () => void
  unlocking: boolean
}) {
  // Reasons are configurable (FP Settings → Motive blocare); show only active ones.
  const { data: reasonsData } = useQuery({
    queryKey: ['fp-lockout-reasons', 'active'],
    queryFn: () => foiParcursApi.getLockoutReasons(true),
    staleTime: 60_000,
  })
  const reasons = reasonsData?.reasons ?? []

  // Block/unblock audit trail — who blocked/unblocked this car, when, and why.
  // Refetched each time the modal opens (default staleTime) so it reflects an
  // action just taken from the same dialog.
  const { data: lockEventsData, isLoading: historyLoading } = useQuery({
    queryKey: ['fp-lock-events', vehicle.id],
    queryFn: () => foiParcursApi.getLockEvents(vehicle.id),
  })
  const lockEvents = lockEventsData?.events ?? []

  const [category, setCategory] = useState('')
  const [note, setNote] = useState('')
  const [until, setUntil] = useState('')

  // Default to the first active reason once loaded.
  useEffect(() => {
    if (!category && reasons.length) setCategory(reasons[0].slug)
  }, [reasons]) // eslint-disable-line react-hooks/exhaustive-deps

  const reasonLabel = (slug?: string | null) => reasons.find((r) => r.slug === slug)?.label || slug || '—'

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Blocare parc auto</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {[vehicle.mark, vehicle.model].filter(Boolean).join(' ')} — {vehicle.registration_number || vehicle.vin}
        </p>

        <Tabs defaultValue="now" className="mt-1">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="now">Blocare imediată</TabsTrigger>
            <TabsTrigger value="scheduled">Blocări programate</TabsTrigger>
          </TabsList>

          {/* Immediate manual lock / unlock */}
          <TabsContent value="now" className="space-y-3 pt-1">
            {vehicle.locked_out ? (
              <>
                <div className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
                  <p className="font-semibold">Mașină blocată manual</p>
                  <p>Motiv: {reasonLabel(vehicle.lockout_category)}</p>
                  {vehicle.lockout_note && <p>Detalii: {vehicle.lockout_note}</p>}
                </div>
                <div className="flex justify-end">
                  <Button variant="destructive" onClick={onUnlock} disabled={unlocking}>
                    {unlocking ? 'Se deblochează…' : 'Deblochează'}
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div className="space-y-1.5">
                  <Label className="text-xs">Motiv</Label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger><SelectValue placeholder="Alege motivul" /></SelectTrigger>
                    <SelectContent>
                      {reasons.map((r) => (
                        <SelectItem key={r.slug} value={r.slug}>{r.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Detalii (opțional)</Label>
                  <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
                    placeholder="Ex: bară față avariată, RCA expirat…" className="text-sm" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Blocat până la (opțional)</Label>
                  <Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} className="text-sm" />
                </div>
                <div className="flex justify-end">
                  <Button
                    onClick={() => onSubmit({ category, note: note.trim() || undefined, until: until || null })}
                    disabled={submitting || !category}
                  >
                    {submitting ? 'Se blochează…' : 'Blochează'}
                  </Button>
                </div>
              </>
            )}

            {/* Istoric blocări — who blocked/unblocked, when, and why. Shown for
                both locked and available cars; survives an unlock. */}
            <div className="mt-1 border-t border-border pt-3">
              <p className="mb-1.5 text-xs font-medium text-muted-foreground">Istoric blocări</p>
              {historyLoading ? (
                <p className="py-1 text-sm text-muted-foreground">Se încarcă…</p>
              ) : lockEvents.length === 0 ? (
                <p className="py-1 text-sm text-muted-foreground">Fără istoric înregistrat.</p>
              ) : (
                <ul className="max-h-44 space-y-2 overflow-y-auto pr-1">
                  {lockEvents.map((ev) => (
                    <li key={ev.id} className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="flex items-baseline gap-1.5">
                        <span aria-hidden>{ev.action === 'lock' ? '🔒' : '🔓'}</span>
                        <span className="font-medium">{ev.action === 'lock' ? 'Blocat' : 'Deblocat'}</span>
                        {ev.action === 'lock' && (
                          <span className="text-muted-foreground">
                            · {reasonLabel(ev.category)}{ev.note ? ` · ${ev.note}` : ''}
                          </span>
                        )}
                      </span>
                      <span className="whitespace-nowrap text-right text-xs text-muted-foreground">
                        {ev.actor_name || 'Sistem'} · {new Date(ev.created_at).toLocaleString('ro-RO')}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </TabsContent>

          {/* Scheduled future block windows */}
          <TabsContent value="scheduled" className="pt-1">
            <ScheduleBlockSection vehicle={vehicle} />
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Închide</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
