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

// A reservation may span at most 3 days (mirrors the backend rule in
// carpark/services/reservation_rules.py: MAX_RESERVATION_DAYS = 3).
const MAX_RESERVATION_DAYS = 3

function addDays(isoDate: string, days: number): string {
  // Work entirely in UTC so the readback via toISOString() matches: building
  // the Date at LOCAL midnight and reading it back as UTC shifts the result a
  // day in positive-offset timezones (e.g. Europe/Bucharest, UTC+2/+3).
  const d = new Date(isoDate + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function ReserveDialog({
  row,
  onClose,
  onSuccess,
}: {
  row: DispoRow
  onClose: () => void
  // Optional extra hook fired after a successful mutation, in addition to
  // the ['carpark', 'dispo'] invalidation below — lets callers outside the
  // Dispo workspace (e.g. the vehicle Detail page's Vânzare tab) refresh
  // their own queries without this dialog knowing about them.
  onSuccess?: () => void
}) {
  const queryClient = useQueryClient()
  const today = new Date().toISOString().slice(0, 10)
  const [clientName, setClientName] = useState(row.reservation_client_name ?? '')
  const [reservationStart, setReservationStart] = useState(today)
  const [reservationEnd, setReservationEnd] = useState('')
  const [depositAmount, setDepositAmount] = useState('')

  // End is bounded to start + 3 days. If the user moves the start past the
  // current end, clear the stale end so the 3-day window re-applies.
  const maxEnd = reservationStart ? addDays(reservationStart, MAX_RESERVATION_DAYS) : undefined

  const mutation = useMutation({
    mutationFn: () =>
      carparkDispoApi.reserve(row.id, {
        client_name: clientName.trim(),
        reservation_start: reservationStart || undefined,
        reservation_end: reservationEnd,
        deposit_amount: depositAmount ? Number(depositAmount) : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
      toast.success('Vehicul rezervat')
      onSuccess?.()
      onClose()
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Eroare la rezervare')),
  })

  const withinMax = !reservationStart || !reservationEnd || (reservationEnd >= reservationStart && (!maxEnd || reservationEnd <= maxEnd))
  const canSubmit = clientName.trim() !== '' && reservationEnd !== '' && withinMax

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
            <Label>Rezervare de la</Label>
            <Input
              type="date"
              value={reservationStart}
              min={today}
              onChange={(e) => {
                const next = e.target.value
                setReservationStart(next)
                // Drop a now-out-of-window end so the 3-day cap re-applies.
                if (next && reservationEnd && (reservationEnd < next || reservationEnd > addDays(next, MAX_RESERVATION_DAYS))) {
                  setReservationEnd('')
                }
              }}
            />
          </div>
          <div>
            <Label>Rezervare până la *</Label>
            <Input
              type="date"
              value={reservationEnd}
              min={reservationStart || today}
              max={maxEnd}
              onChange={(e) => setReservationEnd(e.target.value)}
            />
            <p className="mt-1 text-xs text-muted-foreground">Maxim {MAX_RESERVATION_DAYS} zile.</p>
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
