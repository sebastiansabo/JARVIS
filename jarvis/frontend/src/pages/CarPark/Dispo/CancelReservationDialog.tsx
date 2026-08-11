import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { carparkDispoApi } from '@/api/carparkDispo'
import type { DispoRow } from '@/types/carpark'
import { apiErrorMessage } from './dispoApiError'

// The legitimate RESERVED → (previous status) exit. Unlike a plain PUT
// /status (which the inline StatusEditCell dropdown deliberately refuses for
// RESERVED — see StatusEditCell.REOPEN_ONLY_STATUSES), this hits
// DispoService.cancel_reservation, which closes the active
// carpark_reservations row AND restores the pre-RESERVED status server-side.
export function CancelReservationDialog({
  row,
  onClose,
  onSuccess,
}: {
  row: DispoRow
  onClose: () => void
  // See ReserveDialog.tsx's onSuccess for why this is optional.
  onSuccess?: () => void
}) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')

  const mutation = useMutation({
    mutationFn: () => carparkDispoApi.cancelReservation(row.id, { reason: reason.trim() }),
    onSuccess: () => {
      // Summary + kpis (recompute stage_counts/totals) and the vehicle's
      // reservation list (Detail page's Vânzare tab reads this key).
      queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'reservations', row.id] })
      toast.success('Rezervare anulată')
      onSuccess?.()
      onClose()
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Eroare la anularea rezervării')),
  })

  const canSubmit = reason.trim() !== ''

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Anulează rezervarea — {row.brand} {row.model}</DialogTitle>
          <DialogDescription>
            VIN {row.vin}
            {row.reservation_client_name ? ` — rezervat de ${row.reservation_client_name}` : ''}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>Motiv *</Label>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="ex: client s-a răzgândit"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Renunță</Button>
          <Button
            variant="destructive"
            onClick={() => mutation.mutate()}
            disabled={!canSubmit || mutation.isPending}
          >
            {mutation.isPending ? 'Se anulează...' : 'Anulează rezervarea'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
