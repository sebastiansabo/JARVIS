import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

export function DeliverDialog({
  row,
  onClose,
  onSuccess,
}: {
  row: DispoRow
  onClose: () => void
  // See ReserveDialog.tsx's onSuccess for why this is optional.
  onSuccess?: () => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [deliveryDate, setDeliveryDate] = useState(todayStr())
  const [missingPv, setMissingPv] = useState(false)

  const mutation = useMutation({
    mutationFn: () => carparkDispoApi.deliver(row.id, { delivery_date: deliveryDate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
      toast.success('Vehicul livrat')
      onSuccess?.()
      onClose()
    },
    onError: (err) => {
      const msg = apiErrorMessage(err, 'Eroare la livrare')
      if (msg.includes('MISSING_PV_LIVRARE')) {
        setMissingPv(true)
      } else {
        setMissingPv(false)
        toast.error(msg)
      }
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Livrează {row.brand} {row.model}</DialogTitle>
          <DialogDescription>VIN {row.vin}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>Data livrării *</Label>
            <Input
              type="date"
              value={deliveryDate}
              onChange={(e) => { setDeliveryDate(e.target.value); setMissingPv(false) }}
            />
          </div>

          {missingPv && (
            <div className="rounded-md border border-red-500 bg-red-50 p-3 text-sm text-red-900 dark:bg-red-950/30 dark:text-red-300">
              <p className="font-medium">Lipsește PV de livrare</p>
              <p className="mt-0.5">Încarcă documentul înainte de livrare.</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => { onClose(); navigate(`/app/carpark/${row.id}`) }}
              >
                Deschide fișa vehiculului
              </Button>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button onClick={() => mutation.mutate()} disabled={!deliveryDate || mutation.isPending}>
            {mutation.isPending ? 'Se salvează...' : 'Livrează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
