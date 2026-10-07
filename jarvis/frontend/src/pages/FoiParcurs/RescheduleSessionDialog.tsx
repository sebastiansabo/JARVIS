import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { naiveDate } from '@/lib/naiveDate'
import type { FoiContract } from '@/types/foiParcurs'

const toLocalInput = (iso?: string | null) => (iso ? iso.slice(0, 16) : '')

export interface ReschedulePayload {
  departure_datetime: string
  return_datetime?: string
}

// Move a PLANNED (or late) or MISSED (Ratat) session to a new time, reviving a
// no-show back to Planificat. New departure required and not in the past; the
// return is optional and must be ≥ departure — the same rules the backend
// enforces. Available to everyone (no admin gate), unlike Corectează.
export default function RescheduleSessionDialog({ session, onClose, onSubmit, submitting }: {
  session: FoiContract
  onClose: () => void
  onSubmit: (payload: ReschedulePayload) => void
  submitting: boolean
}) {
  const [dep, setDep] = useState(toLocalInput(session.departure_datetime))
  const [ret, setRet] = useState(toLocalInput(session.return_datetime))
  const today = new Date().toISOString().slice(0, 10)

  const error = !dep
    ? 'Alege data plecării'
    : dep.slice(0, 10) < today
      ? 'Plecarea nu poate fi în trecut'
      : ret && ret < dep
        ? 'Returul nu poate fi înaintea plecării'
        : null
  const canSave = !error && !submitting

  const submit = () => {
    if (!canSave) return
    onSubmit(ret ? { departure_datetime: dep, return_datetime: ret } : { departure_datetime: dep })
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>Replanifică sesiunea</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">
          {session.client_name || session.driver_name || session.advisor_name || '—'}
          {session.departure_datetime && <> · plecare curentă {naiveDate(session.departure_datetime)?.toLocaleString('ro-RO') ?? '—'}</>}
        </p>
        <div className="space-y-1.5 pt-1">
          <Label className="text-xs">Nouă plecare</Label>
          <Input type="datetime-local" aria-label="Nouă plecare" value={dep} min={`${today}T00:00`}
            onChange={(e) => setDep(e.target.value)} className="text-sm" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Nou retur (opțional)</Label>
          <Input type="datetime-local" aria-label="Nou retur" value={ret} min={dep || undefined}
            onChange={(e) => setRet(e.target.value)} className="text-sm" />
        </div>
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button onClick={submit} disabled={!canSave}>
            {submitting ? 'Se salvează…' : 'Replanifică'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
