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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { carparkDispoApi } from '@/api/carparkDispo'
import { STATUS_LABELS, type DispoRow, type VehicleStatus } from '@/types/carpark'
import { apiErrorMessage } from './dispoApiError'

// Legal reopen destinations per starting status, mirroring
// VehicleService.TRANSITIONS (vehicle_service.py) for the two statuses
// DispoRowActions offers Reopen from. First entry is the "natural" default:
// a SOLD sale falling through most often means "put it back up for sale"
// (LISTED); DELIVERED only has one legal backward move (RETURNED).
const REOPEN_TARGETS: Partial<Record<VehicleStatus, VehicleStatus[]>> = {
  SOLD: ['LISTED', 'RESERVED'],
  DELIVERED: ['RETURNED'],
}

export function ReopenDialog({
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
  const targets = REOPEN_TARGETS[row.status] ?? []
  const [targetStatus, setTargetStatus] = useState<VehicleStatus | ''>(targets[0] ?? '')
  const [reason, setReason] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      carparkDispoApi.reopen(row.id, { reason: reason.trim(), target_status: targetStatus as string }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
      toast.success('Vehicul redeschis')
      onSuccess?.()
      onClose()
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Eroare la redeschidere')),
  })

  const canSubmit = reason.trim() !== '' && targetStatus !== ''

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Redeschide {row.brand} {row.model}</DialogTitle>
          <DialogDescription>
            VIN {row.vin} — status curent: {STATUS_LABELS[row.status] ?? row.status}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>Status nou *</Label>
            <Select value={targetStatus} onValueChange={(v) => setTargetStatus(v as VehicleStatus)}>
              <SelectTrigger><SelectValue placeholder="Selectează..." /></SelectTrigger>
              <SelectContent>
                {targets.map((s) => (
                  <SelectItem key={s} value={s}>{STATUS_LABELS[s] ?? s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Motiv *</Label>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="ex: vânzare anulată de client"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button onClick={() => mutation.mutate()} disabled={!canSubmit || mutation.isPending}>
            {mutation.isPending ? 'Se salvează...' : 'Redeschide'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
