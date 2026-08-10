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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { carparkDispoApi } from '@/api/carparkDispo'
import type { DispoRow } from '@/types/carpark'
import { apiErrorMessage } from './dispoApiError'

export function ReserveDialog({ row, onClose }: { row: DispoRow; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [clientName, setClientName] = useState(row.reservation_client_name ?? '')
  const [reservationEnd, setReservationEnd] = useState('')
  const [depositAmount, setDepositAmount] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      carparkDispoApi.reserve(row.id, {
        client_name: clientName.trim(),
        reservation_end: reservationEnd,
        deposit_amount: depositAmount ? Number(depositAmount) : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
      toast.success('Vehicul rezervat')
      onClose()
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Eroare la rezervare')),
  })

  const canSubmit = clientName.trim() !== '' && reservationEnd !== ''

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Rezervă {row.brand} {row.model}</DialogTitle>
          <DialogDescription>VIN {row.vin}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>Client *</Label>
            <Input
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              placeholder="Nume client"
            />
          </div>
          <div>
            <Label>Rezervare până la *</Label>
            <Input
              type="date"
              value={reservationEnd}
              onChange={(e) => setReservationEnd(e.target.value)}
            />
          </div>
          <div>
            <Label>Avans (opțional)</Label>
            <Input
              type="number"
              step="0.01"
              value={depositAmount}
              onChange={(e) => setDepositAmount(e.target.value)}
              placeholder="0"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button onClick={() => mutation.mutate()} disabled={!canSubmit || mutation.isPending}>
            {mutation.isPending ? 'Se salvează...' : 'Rezervă'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
