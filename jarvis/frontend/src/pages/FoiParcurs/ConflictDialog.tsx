import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle } from 'lucide-react'
import type { VehicleConflict } from '@/types/foiParcurs'

const STATUS_LABEL: Record<string, string> = {
  PLANNED: 'Planificat',
  FILLED: 'În desfășurare',
  COMPLETED: 'Finalizat',
}

/** Soft-block warning shown when a VIN has overlapping PLANNED/live TD
 *  sessions in the chosen window. Never hard-blocks — "Continuă oricum"
 *  always lets the user proceed with the pending action. */
export function ConflictDialog({
  open,
  conflicts,
  onContinue,
  onCancel,
}: {
  open: boolean
  conflicts: VehicleConflict[]
  onContinue: () => void
  onCancel: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            Mașina este deja rezervată
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            {conflicts.length === 1
              ? 'Există o sesiune care se suprapune cu intervalul ales:'
              : `Există ${conflicts.length} sesiuni care se suprapun cu intervalul ales:`}
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {conflicts.map((c) => (
              <div key={c.id} className="rounded-md border p-2 text-sm space-y-0.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{c.client_name || '—'}</span>
                  <Badge variant="outline" className="text-xs">{STATUS_LABEL[c.status] ?? c.status}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">Consilier: {c.advisor_name || '—'}</p>
                <p className="text-xs text-muted-foreground">
                  {c.departure_datetime ? new Date(c.departure_datetime).toLocaleString('ro-RO') : '—'}
                  {' → '}
                  {c.return_datetime ? new Date(c.return_datetime).toLocaleString('ro-RO') : '—'}
                </p>
              </div>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>Anulează</Button>
          <Button onClick={onContinue}>Continuă oricum</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
