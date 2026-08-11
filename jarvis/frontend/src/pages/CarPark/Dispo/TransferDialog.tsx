// "Transferă" dialog, opened from a Dispo row's ⋯ actions menu
// (DispoRowActions.tsx). Moves a vehicle to a sibling AutoWorld company
// (transfers.py's POST /vehicles/:id/transfer) — on success the car
// disappears from this company's Dispo list and lands at the destination
// as a fresh 'ACQUIRED' intake marked transferred_from_company_id (see
// dispo_service.py's transfer()).
//
// The transfer's backing document is ALWAYS type 'factura_transfer'
// (fixed server-side default — transfers.py's _DEFAULT_DOCUMENT_TYPE), so
// unlike AttachDocumentDialog there's no type picker; only the file/link
// upload-mode split is reused from it (same Drive-disabled 400 handling).
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Upload, Link2 } from 'lucide-react'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { carparkDispoApi } from '@/api/carparkDispo'
import { ApiError } from '@/api/client'
import { apiErrorMessage } from './dispoApiError'
import type { DispoRow } from '@/types/carpark'

type UploadMode = 'file' | 'link'

const CURRENCY_OPTIONS = ['EUR', 'RON', 'USD']

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

export function TransferDialog({
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

  // AutoWorld sibling companies available as a destination for the
  // caller's own company (excludes itself already — group_companies).
  // A non-AutoWorld company gets an empty list back; the dialog still
  // opens (DispoRowActions doesn't pre-check this) and shows a guiding
  // message instead of crashing or silently offering nothing.
  const { data, isLoading } = useQuery({
    queryKey: ['carpark', 'transfer-destinations'],
    queryFn: () => carparkDispoApi.getTransferDestinations(),
  })
  const destinations = data?.companies ?? []

  const [toCompanyId, setToCompanyId] = useState<number | ''>('')
  const [price, setPrice] = useState('')
  const [currency, setCurrency] = useState('EUR')
  const [transferDate, setTransferDate] = useState(todayStr())
  const [notes, setNotes] = useState('')

  const [mode, setMode] = useState<UploadMode>('file')
  const [file, setFile] = useState<File | null>(null)
  const [fileUrl, setFileUrl] = useState('')
  const [driveDisabledHint, setDriveDisabledHint] = useState(false)

  const mutation = useMutation({
    mutationFn: () => {
      const priceNum = Number(price)
      if (mode === 'file' && file) {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('to_company_id', String(toCompanyId))
        fd.append('transfer_price', String(priceNum))
        fd.append('transfer_date', transferDate)
        fd.append('transfer_currency', currency)
        if (notes.trim()) fd.append('notes', notes.trim())
        return carparkDispoApi.transfer(row.id, fd)
      }
      return carparkDispoApi.transfer(row.id, {
        to_company_id: Number(toCompanyId),
        transfer_price: priceNum,
        transfer_date: transferDate,
        transfer_currency: currency,
        notes: notes.trim() || undefined,
        file_url: fileUrl || undefined,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo', 'kpis'] })
      queryClient.invalidateQueries({ queryKey: ['carpark', 'transfers-out'] })
      const destName = destinations.find((c) => c.id === toCompanyId)?.company
      toast.success(destName ? `Vehicul transferat către ${destName}` : 'Vehicul transferat')
      onSuccess?.()
      onClose()
    },
    onError: (err) => {
      const msg = apiErrorMessage(err, 'Eroare la transfer')
      // Multipart upload 400s when Google Drive is disabled server-side
      // (transfers.py's _create_transfer_document_via_upload) — same
      // fallback UX as AttachDocumentDialog: hint + switch to link mode.
      if (mode === 'file' && err instanceof ApiError && err.status === 400 && /drive|disabled/i.test(msg)) {
        setDriveDisabledHint(true)
        setMode('link')
      } else {
        toast.error(msg)
      }
    },
  })

  const hasDocument = mode === 'file' ? !!file : !!fileUrl.trim()
  const canSubmit =
    toCompanyId !== '' && price !== '' && Number(price) > 0 && transferDate !== '' && hasDocument

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Transferă {row.brand} {row.model}</DialogTitle>
          <DialogDescription>VIN {row.vin} · către o companie AutoWorld</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>Companie destinație *</Label>
            {!isLoading && destinations.length === 0 ? (
              <p className="mt-1 rounded-md border border-dashed p-2 text-xs text-muted-foreground">
                Nicio companie disponibilă pentru transfer.
              </p>
            ) : (
              <Select
                value={toCompanyId === '' ? '' : String(toCompanyId)}
                onValueChange={(v) => setToCompanyId(Number(v))}
                disabled={isLoading}
              >
                <SelectTrigger>
                  <SelectValue placeholder={isLoading ? 'Se încarcă...' : 'Selectează companie...'} />
                </SelectTrigger>
                <SelectContent>
                  {destinations.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="grid grid-cols-[1fr_auto] gap-2">
            <div>
              <Label>Preț transfer *</Label>
              <Input
                type="number"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="0"
              />
            </div>
            <div>
              <Label>Monedă</Label>
              <Select value={currency} onValueChange={setCurrency}>
                <SelectTrigger className="w-[5.5rem]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CURRENCY_OPTIONS.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label>Data transferului *</Label>
            <Input type="date" value={transferDate} onChange={(e) => setTransferDate(e.target.value)} />
          </div>

          <div>
            <Label>Note (opțional)</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Observații..." />
          </div>

          <div className="space-y-1.5">
            <Label>Document transfer (factură) *</Label>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant={mode === 'file' ? 'default' : 'outline'}
                size="sm"
                onClick={() => { setMode('file'); setDriveDisabledHint(false) }}
              >
                <Upload className="mr-1.5 h-3.5 w-3.5" /> Fișier
              </Button>
              <Button
                type="button"
                variant={mode === 'link' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setMode('link')}
              >
                <Link2 className="mr-1.5 h-3.5 w-3.5" /> sau adaugă prin link
              </Button>
            </div>

            {driveDisabledHint && (
              <div className="rounded-md border border-amber-500 bg-amber-50 p-2.5 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
                Încărcarea pe Drive nu e disponibilă — folosește un link (URL).
              </div>
            )}

            {mode === 'file' ? (
              <div className="space-y-1.5">
                <Input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                {file && (
                  <div className="text-xs text-muted-foreground">
                    {file.name} · {(file.size / 1024).toFixed(0)} KB
                  </div>
                )}
              </div>
            ) : (
              <Input value={fileUrl} onChange={(e) => setFileUrl(e.target.value)} placeholder="https://..." />
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button onClick={() => mutation.mutate()} disabled={!canSubmit || mutation.isPending}>
            {mutation.isPending ? 'Se transferă...' : 'Transferă'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
