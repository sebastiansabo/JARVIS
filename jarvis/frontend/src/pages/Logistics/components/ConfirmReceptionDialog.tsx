// "Confirmă recepția" dialog -- the Recepție -> Finalizat move gate (Task 9
// of the spine plan). Collects the 5 fields jarvis/logistics/services/
// moves.py::_require_reception_fields requires before it'll accept the
// move (vin/location_id/position_id/keys/condition), mirroring
// Kanban.tsx's BlockTaskDialog pattern for the Blocat gate.
//
// Locație/Poziție are plain numeric id inputs, not a name-resolving
// <select> -- there's no `/locations` endpoint yet to populate one (see
// Kanban.helpers.ts's filterBoardByLocation docstring for the same
// phase-1 gap), so this intentionally stays simple rather than building a
// lookup the rest of the module doesn't have either.
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
import { isReceptionFormValid, type ReceptionFormState } from '../Kanban.helpers'

/** The card currently pending the "Confirmă recepția" dialog -- null when
 * the dialog is closed. Only ever opened for a `Recepție` card moving to
 * `Finalizat` (see Kanban.tsx's onMove). */
export interface PendingReception {
  card: KanbanCard
}

export function ConfirmReceptionDialog({
  pending,
  form,
  isPending,
  onFieldChange,
  onCancel,
  onConfirm,
}: {
  pending: PendingReception | null
  form: ReceptionFormState
  isPending: boolean
  onFieldChange: (field: keyof ReceptionFormState, value: string) => void
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog open={pending !== null} onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Confirmă recepția</DialogTitle>
        </DialogHeader>

        {pending && (
          <p className="-mt-2 text-xs text-muted-foreground">
            {pending.card.vehicle_model ?? pending.card.order_ref} · {pending.card.title}
          </p>
        )}

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="reception-vin">VIN</Label>
            <Input
              id="reception-vin"
              value={form.vin}
              onChange={(e) => onFieldChange('vin', e.target.value)}
              placeholder="Seria de șasiu"
              autoFocus
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="reception-location">Locație (ID)</Label>
              <Input
                id="reception-location"
                type="number"
                min={1}
                value={form.location_id}
                onChange={(e) => onFieldChange('location_id', e.target.value)}
                placeholder="ID locație"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="reception-position">Poziție (ID)</Label>
              <Input
                id="reception-position"
                type="number"
                min={1}
                value={form.position_id}
                onChange={(e) => onFieldChange('position_id', e.target.value)}
                placeholder="ID poziție"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="reception-keys">Chei</Label>
            <Input
              id="reception-keys"
              type="number"
              min={0}
              value={form.keys}
              onChange={(e) => onFieldChange('keys', e.target.value)}
              placeholder="Număr de chei predate"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="reception-condition">Stare</Label>
            <Input
              id="reception-condition"
              value={form.condition}
              onChange={(e) => onFieldChange('condition', e.target.value)}
              placeholder="Starea mașinii la recepție"
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
            disabled={!isReceptionFormValid(form) || isPending}
          >
            Confirmă recepția
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
