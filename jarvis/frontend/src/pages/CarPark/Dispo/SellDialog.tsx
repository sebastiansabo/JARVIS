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
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ClientSearchSelect, type ClientSearchSelection } from '@/components/shared/ClientSearchSelect'
import { carparkDispoApi } from '@/api/carparkDispo'
import type { DispoRow, SaleType } from '@/types/carpark'
import { apiErrorMessage } from './dispoApiError'

const SALE_TYPE_OPTIONS: SaleType[] = ['PLR', 'CASH', 'CREDIT PLR', 'BT LEASING', 'BRD', 'BCR', 'AW NEXT']

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

export function SellDialog({
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
  const [salePrice, setSalePrice] = useState(row.current_price != null ? String(row.current_price) : '')
  const [saleType, setSaleType] = useState<SaleType | ''>('')
  const [buyer, setBuyer] = useState<ClientSearchSelection | null>(
    row.buyer_name ? { id: row.buyer_client_id, name: row.buyer_name } : null,
  )
  const [saleDate, setSaleDate] = useState(todayStr())
  const [lowMarginMsg, setLowMarginMsg] = useState<string | null>(null)
  const [confirmLowMargin, setConfirmLowMargin] = useState(false)

  // Any field edit after a LOW_MARGIN warning invalidates the confirmation
  // — re-check the guard against the new values instead of silently
  // pushing through a stale confirm on a price the backend never saw.
  function resetWarning() {
    setLowMarginMsg(null)
    setConfirmLowMargin(false)
  }

  const mutation = useMutation({
    mutationFn: (confirm: boolean) =>
      carparkDispoApi.sell(row.id, {
        sale_price: Number(salePrice),
        sale_type: saleType as SaleType,
        buyer_name: buyer?.name,
        // Explicit null, never undefined: a free-text buyer (id null) must
        // reach the backend as null so sell() clears any prior CRM link
        // rather than JSON.stringify dropping the key and leaving it stale.
        buyer_client_id: buyer?.id ?? null,
        sale_date: saleDate,
        confirm_low_margin: confirm || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
      toast.success('Vehicul vândut')
      onSuccess?.()
      onClose()
    },
    onError: (err) => {
      const msg = apiErrorMessage(err, 'Eroare la vânzare')
      if (msg.startsWith('LOW_MARGIN:')) {
        setLowMarginMsg(msg.replace(/^LOW_MARGIN:\s*/, ''))
      } else {
        setLowMarginMsg(null)
        toast.error(msg)
      }
    },
  })

  const canSubmit = salePrice !== '' && saleType !== '' && !!buyer?.name.trim() && saleDate !== ''
  const blockedByLowMargin = lowMarginMsg !== null && !confirmLowMargin

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Vinde {row.brand} {row.model}</DialogTitle>
          <DialogDescription>VIN {row.vin}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>Preț vânzare *</Label>
            <Input
              type="number"
              step="0.01"
              value={salePrice}
              onChange={(e) => { setSalePrice(e.target.value); resetWarning() }}
            />
          </div>
          <div>
            <Label>Tip vânzare *</Label>
            <Select value={saleType} onValueChange={(v) => { setSaleType(v as SaleType); resetWarning() }}>
              <SelectTrigger><SelectValue placeholder="Selectează..." /></SelectTrigger>
              <SelectContent>
                {SALE_TYPE_OPTIONS.map((t) => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Cumpărător *</Label>
            <ClientSearchSelect
              value={buyer ?? undefined}
              companyId={row.company_id ?? undefined}
              onSelect={setBuyer}
              placeholder="Caută sau adaugă cumpărător..."
            />
          </div>
          <div>
            <Label>Data vânzării *</Label>
            <Input
              type="date"
              value={saleDate}
              onChange={(e) => { setSaleDate(e.target.value); resetWarning() }}
            />
          </div>

          {lowMarginMsg && (
            <div className="rounded-md border border-amber-500 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
              <p className="font-medium">Marjă scăzută</p>
              <p className="mt-0.5">{lowMarginMsg}</p>
              <label className="mt-2 flex items-center gap-2 cursor-pointer">
                <Checkbox checked={confirmLowMargin} onCheckedChange={(v) => setConfirmLowMargin(v === true)} />
                <span>Confirmă vânzarea oricum</span>
              </label>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button
            onClick={() => mutation.mutate(confirmLowMargin)}
            disabled={!canSubmit || blockedByLowMargin || mutation.isPending}
          >
            {mutation.isPending ? 'Se salvează...' : 'Vinde'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
