// Inline "attach a document" dialog, opened from a Dispo row's ⋯ actions
// menu (DispoRowActions.tsx). Mirrors Detail/DocumenteTab.tsx's upload form
// (same file/link modes, same Drive-disabled 400 handling) but as a compact
// modal so the user never has to leave the Dispo table.
//
// Product decision: attaching a 'factura_achizitie' with an invoice date
// ALSO writes that date onto supplier_payment_date (the "Data plată"
// column) via a follow-up PUT. This is a deliberate, accepted mapping —
// invoice date is being reused as the payment date — not a bug. It's
// optional: an empty date leaves supplier_payment_date untouched.
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
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
import { carparkApi } from '@/api/carpark'
import { ApiError } from '@/api/client'
import { apiErrorMessage } from './dispoApiError'
import {
  DOCUMENT_TYPES,
  DOCUMENT_TYPE_LABELS,
  type DocumentType,
} from '@/types/carpark'

type UploadMode = 'file' | 'link'

// Tags which of the two sequential calls inside the mutation threw, so
// onError can (a) only apply the Drive-disabled heuristic to the upload
// step, and (b) tell the user separately if the document WAS created but
// the follow-up Data plată update failed (rather than a generic error that
// implies nothing happened).
class AttachStageError extends Error {
  constructor(public stage: 'upload' | 'payment-date', public cause: unknown) {
    super('attach-stage-error')
  }
}

export function AttachDocumentDialog({
  vehicleId,
  open,
  onOpenChange,
  onSuccess,
}: {
  vehicleId: number
  open: boolean
  onOpenChange: (open: boolean) => void
  // Extra hook fired after a successful attach, in addition to the query
  // invalidations below — lets the caller (DispoRowActions) do its own
  // bookkeeping without this dialog knowing about it.
  onSuccess?: () => void
}) {
  const queryClient = useQueryClient()

  // 'factura_achizitie' defaults selected since it's the type this dialog
  // exists to make fast (invoice → Data plată in one step).
  const [documentType, setDocumentType] = useState<DocumentType>('factura_achizitie')
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileUrl, setFileUrl] = useState('')
  const [mode, setMode] = useState<UploadMode>('file')
  const [invoiceDate, setInvoiceDate] = useState('')
  const [driveDisabledHint, setDriveDisabledHint] = useState(false)

  const resetForm = () => {
    setDocumentType('factura_achizitie')
    setTitle('')
    setFile(null)
    setFileUrl('')
    setMode('file')
    setInvoiceDate('')
    setDriveDisabledHint(false)
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) resetForm()
    onOpenChange(next)
  }

  const invalidateAll = () => {
    // Summary + kpis: refreshes Data plată and the missing-doc paperclip
    // flag (both computed from carpark_vehicles / doc_types server-side).
    queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'documents', vehicleId] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'documents-checklist', vehicleId] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'timeline', vehicleId] })
  }

  const mutation = useMutation({
    mutationFn: async (): Promise<{ paymentDateSet: boolean }> => {
      try {
        if (mode === 'file' && file) {
          const fd = new FormData()
          fd.append('file', file)
          fd.append('document_type', documentType)
          if (title) fd.append('title', title)
          await carparkDispoApi.uploadDocument(vehicleId, fd)
        } else {
          await carparkDispoApi.uploadDocument(vehicleId, {
            document_type: documentType,
            file_url: fileUrl || undefined,
            title: title || undefined,
          })
        }
      } catch (err) {
        throw new AttachStageError('upload', err)
      }

      if (documentType === 'factura_achizitie' && invoiceDate) {
        try {
          await carparkApi.updateVehicle(vehicleId, { supplier_payment_date: invoiceDate })
        } catch (err) {
          throw new AttachStageError('payment-date', err)
        }
        return { paymentDateSet: true }
      }
      return { paymentDateSet: false }
    },
    onSuccess: ({ paymentDateSet }) => {
      invalidateAll()
      toast.success(paymentDateSet ? 'Document atașat · Data plată actualizată' : 'Document atașat')
      resetForm()
      onSuccess?.()
      onOpenChange(false)
    },
    onError: (err) => {
      if (err instanceof AttachStageError && err.stage === 'payment-date') {
        // The document itself was created successfully — only the Data
        // plată follow-up failed. Still refresh (the new doc is real) and
        // close, but say so distinctly rather than a generic failure toast
        // that would wrongly suggest nothing happened.
        invalidateAll()
        toast.error(
          apiErrorMessage(err.cause, 'Document atașat, dar actualizarea Datei plată a eșuat — setează manual.'),
        )
        resetForm()
        onSuccess?.()
        onOpenChange(false)
        return
      }

      const cause = err instanceof AttachStageError ? err.cause : err
      const msg = apiErrorMessage(cause, 'Eroare la atașarea documentului')
      // Multipart upload 400s when Google Drive is disabled server-side
      // (documents.py's _create_via_upload) — mirror DocumenteTab's
      // handling: surface an inline hint and switch to link mode.
      if (mode === 'file' && cause instanceof ApiError && cause.status === 400 && /drive|disabled/i.test(msg)) {
        setDriveDisabledHint(true)
        setMode('link')
      } else {
        toast.error(msg)
      }
    },
  })

  const canSubmit = !!documentType && (mode === 'file' ? !!file : !!fileUrl)

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Atașează document</DialogTitle>
          <DialogDescription>Documentul apare apoi în fișa vehiculului, tab Documente.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Tip document *</Label>
              <Select value={documentType} onValueChange={(v) => setDocumentType(v as DocumentType)}>
                <SelectTrigger>
                  <SelectValue placeholder="Selectează tip" />
                </SelectTrigger>
                <SelectContent>
                  {DOCUMENT_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>{DOCUMENT_TYPE_LABELS[t]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Titlu (opțional)</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ex. Factură furnizor" />
            </div>
          </div>

          {documentType === 'factura_achizitie' && (
            <div className="space-y-1.5">
              <Label>Data factură (achiziție) — opțional</Label>
              <Input type="date" value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} />
              <p className="text-xs text-muted-foreground">
                Dacă o completezi, actualizează automat Data plată a vehiculului.
              </p>
            </div>
          )}

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
              <Label>Fișier</Label>
              <Input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              {file && (
                <div className="text-xs text-muted-foreground">
                  {file.name} · {(file.size / 1024).toFixed(0)} KB
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label>URL fișier</Label>
              <Input value={fileUrl} onChange={(e) => setFileUrl(e.target.value)} placeholder="https://..." />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>Anulează</Button>
          <Button disabled={!canSubmit || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? 'Se salvează...' : 'Atașează document'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default AttachDocumentDialog
