import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { naiveDate } from '@/lib/naiveDate'
import type { FoiContract } from '@/types/foiParcurs'

const toLocalInput = (iso?: string | null) => (iso ? iso.slice(0, 16) : '')

// Advisor modal to extend/change an OPEN test drive's return time when the
// client keeps the car longer. One field; must be ≥ departure. Status/km stay.
export default function ExtendSessionDialog({ session, onClose, onSubmit, submitting }: {
  session: FoiContract
  onClose: () => void
  onSubmit: (returnDatetime: string) => void
  submitting: boolean
}) {
  const [ret, setRet] = useState(toLocalInput(session.return_datetime))
  const depLocal = toLocalInput(session.departure_datetime)
  const error = !ret
    ? 'Alege data returului'
    : depLocal && ret < depLocal
      ? 'Returul nu poate fi înaintea plecării'
      : null
  const canSave = !error && !submitting

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>Prelungește sesiunea</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">
          {session.client_name || session.advisor_name || '—'}
          {session.departure_datetime && <> · plecare {naiveDate(session.departure_datetime)?.toLocaleString('ro-RO') ?? '—'}</>}
        </p>
        <div className="space-y-1.5 pt-1">
          <Label className="text-xs">Nou retur</Label>
          <Input type="datetime-local" value={ret} min={depLocal || undefined}
            onChange={(e) => setRet(e.target.value)} className="text-sm" />
        </div>
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button onClick={() => canSave && onSubmit(ret)} disabled={!canSave}>
            {submitting ? 'Se salvează…' : 'Prelungește'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
