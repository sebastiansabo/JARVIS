// Measured-result dialog -- the Îngrijire -> Finalizat move gate (Task 10
// of the spine plan). Collects the 2 fields jarvis/logistics/services/
// moves.py::_require_measured_fields requires before it'll accept the
// move (value/unit, e.g. a 12V battery check), mirroring Kanban.tsx's
// BlockTaskDialog / ConfirmReceptionDialog pattern for the other two move
// gates.
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { KanbanCard } from '@/api/logistics'
import { isMeasuredFormValid, type MeasuredFormState } from '../Kanban.helpers'

/** The card currently pending the measured-result dialog -- null when the
 * dialog is closed. Only ever opened for an `Îngrijire` card moving to
 * `Finalizat` (see Kanban.tsx's onMove). */
export interface PendingMeasured {
  card: KanbanCard
}

export function MeasuredResultDialog({
  pending,
  form,
  isPending,
  onFieldChange,
  onCancel,
  onConfirm,
}: {
  pending: PendingMeasured | null
  form: MeasuredFormState
  isPending: boolean
  onFieldChange: (field: keyof MeasuredFormState, value: string) => void
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog open={pending !== null} onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Rezultat măsurare</DialogTitle>
        </DialogHeader>

        {pending && (
          <p className="-mt-2 text-xs text-muted-foreground">
            {pending.card.vehicle_model ?? pending.card.order_ref} · {pending.card.title}
          </p>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="measured-value">Valoare</Label>
            <Input
              id="measured-value"
              type="number"
              value={form.value}
              onChange={(e) => onFieldChange('value', e.target.value)}
              placeholder="ex. 12.4"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="measured-unit">Unitate</Label>
            <Input
              id="measured-unit"
              value={form.unit}
              onChange={(e) => onFieldChange('unit', e.target.value)}
              placeholder="ex. V"
            />
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onCancel} disabled={isPending}>
            Anulează
          </Button>
          <Button
            type="button"
            onClick={onConfirm}
            disabled={!isMeasuredFormValid(form) || isPending}
          >
            Finalizează
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
