import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { naiveDate } from '@/lib/naiveDate'
import type { FoiContract } from '@/types/foiParcurs'

// Start a PLANNED *internal* session → FILLED. The internal counterpart to the
// customer activate form: no client/signature/PDF, just capture the real km
// plecare (the draft deferred it) before the car goes out. `defaultKm` is the
// car's live odometer floor, passed by the caller.
export default function InternalStartDialog({ session, vehicleName, defaultKm, onClose, onSubmit, submitting }: {
  session: FoiContract
  vehicleName?: string
  defaultKm?: number | null
  onClose: () => void
  onSubmit: (odometerStart: number) => void
  submitting: boolean
}) {
  const [km, setKm] = useState(defaultKm != null ? String(defaultKm) : (session.km_start != null ? String(session.km_start) : ''))
  const error = km.trim() === '' || !Number.isFinite(Number(km)) ? 'Introdu km la plecare' : null
  const canSave = !error && !submitting

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>Începe sesiunea internă</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">
          {vehicleName || session.vin || '—'}
          {session.advisor_name && <> · {session.advisor_name}</>}
          {session.departure_datetime && <> · plecare {naiveDate(session.departure_datetime)?.toLocaleString('ro-RO') ?? '—'}</>}
        </p>
        <div className="space-y-1.5 pt-1">
          <Label className="text-xs">KM plecare *</Label>
          <Input type="number" inputMode="numeric" value={km} onChange={(e) => setKm(e.target.value)} className="text-sm" />
        </div>
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button onClick={() => canSave && onSubmit(Number(km))} disabled={!canSave}>
            {submitting ? 'Se pornește…' : 'Începe sesiunea'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
