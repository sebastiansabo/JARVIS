// CarPark Documente tab — "Adaugă document" form, redesigned as a short
// guided flow (pick type → add the file → submit) so the next action is
// always obvious instead of a silently-disabled button. Owns all upload
// state + the mutation; tells its parent to refresh via onUploaded().
//
// Upload path mirrors the backend contract (carpark/routes/documents.py):
// multipart when Google Drive is enabled, otherwise a link/URL fallback —
// a file upload that 400s with a "drive disabled" message auto-switches the
// form to link mode.
import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Upload, Link2, FileText, X, Info, Receipt } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { carparkDispoApi } from '@/api/carparkDispo'
import { ApiError } from '@/api/client'
import { apiErrorMessage } from '../Dispo/dispoApiError'
import {
  DOCUMENT_TYPE_GROUPS,
  DOCUMENT_TYPE_LABELS,
  isInvoiceDocumentType,
  type DocumentType,
} from '@/types/carpark'

type UploadMode = 'file' | 'link'

function StepHeader({ n, label }: { n: number; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
        {n}
      </span>
      <span className="text-sm font-medium">{label}</span>
    </div>
  )
}

export function DocumentUploadForm({
  vehicleId,
  onUploaded,
}: {
  vehicleId: number
  onUploaded: () => void
}) {
  const [documentType, setDocumentType] = useState<DocumentType | ''>('')
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileUrl, setFileUrl] = useState('')
  const [dmsDocumentId, setDmsDocumentId] = useState('')
  const [mode, setMode] = useState<UploadMode>('file')
  const [driveDisabledHint, setDriveDisabledHint] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setDocumentType('')
    setTitle('')
    setFile(null)
    setFileUrl('')
    setDmsDocumentId('')
    setDriveDisabledHint(false)
  }

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (mode === 'file' && file) {
        const fd = new FormData()
        fd.append('file', file)
        fd.append('document_type', documentType)
        if (title) fd.append('title', title)
        return carparkDispoApi.uploadDocument(vehicleId, fd)
      }
      return carparkDispoApi.uploadDocument(vehicleId, {
        document_type: documentType as DocumentType,
        file_url: fileUrl || undefined,
        dms_document_id: dmsDocumentId || undefined,
        title: title || undefined,
      })
    },
    onSuccess: () => {
      onUploaded()
      toast.success('Document adăugat')
      reset()
    },
    onError: (err) => {
      const msg = apiErrorMessage(err, 'Eroare la încărcarea documentului')
      // A multipart upload 400s with a "drive disabled" message when Google
      // Drive isn't configured — switch to link mode and show an inline hint
      // rather than a dead-end toast.
      if (mode === 'file' && err instanceof ApiError && err.status === 400 && /drive|disabled/i.test(msg)) {
        setDriveDisabledHint(true)
        setMode('link')
      } else {
        toast.error(msg)
      }
    },
  })

  const isInvoice = !!documentType && isInvoiceDocumentType(documentType)

  // What's still needed, in the order the user fills it — drives both the
  // button's enabled state and the hint next to it, so the button is never
  // silently dead.
  const missing =
    !documentType
      ? 'Alege tipul documentului'
      : mode === 'file'
        ? (!file ? 'Alege un fișier' : null)
        : (!fileUrl && !dmsDocumentId ? 'Adaugă un link sau un ID DMS' : null)
  const canSubmit = missing === null

  const switchMode = (m: UploadMode) => {
    setMode(m)
    if (m === 'file') setDriveDisabledHint(false)
  }

  const dropZoneBase =
    'flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring'
  const dropZoneState = dragOver
    ? 'border-primary bg-primary/5'
    : 'border-border hover:border-primary/50 hover:bg-muted/40'

  return (
    <Card className="p-5 space-y-5">
      <div>
        <h3 className="text-sm font-semibold">Adaugă document</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Alege tipul, apoi încarcă fișierul sau lipește un link.
        </p>
      </div>

      {/* Step 1 — what kind of document */}
      <div className="space-y-3">
        <StepHeader n={1} label="Ce fel de document?" />
        <div className="grid gap-3 pl-7 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs">
              Tip document <span className="text-red-500">*</span>
            </Label>
            <Select value={documentType} onValueChange={(v) => setDocumentType(v as DocumentType)}>
              <SelectTrigger>
                <SelectValue placeholder="Selectează tipul" />
              </SelectTrigger>
              <SelectContent>
                {DOCUMENT_TYPE_GROUPS.map((g) => (
                  <SelectGroup key={g.label}>
                    <SelectLabel>{g.label}</SelectLabel>
                    {g.types.map((t) => (
                      <SelectItem key={t} value={t}>
                        {DOCUMENT_TYPE_LABELS[t]}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">
              Titlu <span className="font-normal text-muted-foreground">(opțional)</span>
            </Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ex. PV livrare semnat" />
          </div>
        </div>
        {isInvoice && (
          <div className="flex items-center gap-1.5 pl-7 text-xs text-muted-foreground">
            <Receipt className="h-3.5 w-3.5 shrink-0" />
            După adăugare poți transfera factura în Costuri.
          </div>
        )}
      </div>

      {/* Step 2 — the file or link */}
      <div className="space-y-3">
        <StepHeader n={2} label="Adaugă fișierul" />
        <div className="space-y-3 pl-7">
          {/* Segmented this-or-that toggle */}
          <div className="inline-flex rounded-lg border bg-muted/40 p-0.5 text-sm">
            <button
              type="button"
              onClick={() => switchMode('file')}
              className={`flex items-center gap-1.5 rounded-[7px] px-3 py-1.5 transition-colors ${
                mode === 'file' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Upload className="h-3.5 w-3.5" /> Fișier
            </button>
            <button
              type="button"
              onClick={() => switchMode('link')}
              className={`flex items-center gap-1.5 rounded-[7px] px-3 py-1.5 transition-colors ${
                mode === 'link' ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Link2 className="h-3.5 w-3.5" /> Link
            </button>
          </div>

          {driveDisabledHint && (
            <div className="rounded-md border border-amber-500 bg-amber-50 p-2.5 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
              Încărcarea de fișiere nu e disponibilă pe acest server — lipește un link (URL) în schimb.
            </div>
          )}

          {mode === 'file' ? (
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  fileInputRef.current?.click()
                }
              }}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                const dropped = e.dataTransfer.files?.[0]
                if (dropped) setFile(dropped)
              }}
              className={`${dropZoneBase} ${dropZoneState}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <div
                  className="flex w-full items-center gap-3 rounded-md border bg-background px-3 py-2.5 text-left"
                  onClick={(e) => e.stopPropagation()}
                >
                  <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{file.name}</div>
                    <div className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(0)} KB</div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    title="Elimină fișierul"
                    onClick={(e) => { e.stopPropagation(); setFile(null) }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <>
                  <Upload className="h-6 w-6 text-muted-foreground" />
                  <div className="text-sm">
                    <span className="font-medium text-foreground">Trage un fișier aici</span>{' '}
                    <span className="text-muted-foreground">sau click pentru a alege</span>
                  </div>
                  <div className="text-xs text-muted-foreground">PDF, imagine sau document · max 10 MB</div>
                </>
              )}
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label className="text-xs">URL fișier</Label>
                <Input value={fileUrl} onChange={(e) => setFileUrl(e.target.value)} placeholder="https://..." />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">
                  ID document DMS <span className="font-normal text-muted-foreground">(opțional)</span>
                </Label>
                <Input value={dmsDocumentId} onChange={(e) => setDmsDocumentId(e.target.value)} placeholder="ex. 1234" />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Footer — always say what's missing, never a silent grey button */}
      <div className="flex flex-wrap items-center justify-end gap-3 border-t pt-4">
        {missing && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Info className="h-3.5 w-3.5 shrink-0" />
            {missing}
          </span>
        )}
        <Button disabled={!canSubmit || uploadMutation.isPending} onClick={() => uploadMutation.mutate()}>
          {uploadMutation.isPending ? 'Se încarcă...' : 'Adaugă document'}
        </Button>
      </div>
    </Card>
  )
}

export default DocumentUploadForm
