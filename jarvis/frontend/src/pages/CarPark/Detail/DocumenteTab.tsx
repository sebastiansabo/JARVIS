// CarPark vehicle Detail — "Documente" tab: required-doc checklist, an
// upload form (multipart when Google Drive is enabled, else a link/URL
// fallback — see carpark/routes/documents.py's module docstring), and the
// document list with delete. This is what unblocks the Dispo Deliver flow
// (deliver() 400s with MISSING_PV_LIVRARE until a pv_livrare doc exists —
// see DeliverDialog.tsx).
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Upload,
  Link2,
  Trash2,
  ExternalLink,
  FileText,
} from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { useAuthStore } from '@/stores/authStore'
import { carparkDispoApi } from '@/api/carparkDispo'
import { ApiError } from '@/api/client'
import { apiErrorMessage } from '../Dispo/dispoApiError'
import {
  DOCUMENT_TYPES,
  DOCUMENT_TYPE_LABELS,
  type DocumentType,
} from '@/types/carpark'

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('ro-RO')
}

// XSS guard: file_url is user-supplied (link-mode upload accepts an
// arbitrary URL), so it must never go into an <a href> unchecked — a
// `javascript:` / `data:text/html,...` value would execute on click.
// Only http(s) absolute URLs are allowed to become clickable links;
// anything else is rendered as inert text instead.
export function safeHref(url?: string | null): string | null {
  if (!url) return null
  const u = url.trim()
  return /^https?:\/\//i.test(u) ? u : null
}

type UploadMode = 'file' | 'link'

export function DocumenteTab({ vehicleId, status }: { vehicleId: number; status?: string }) {
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.can_edit_carpark ?? false
  const canDelete = user?.can_delete_carpark ?? false
  // Once a vehicle is DELIVERED, the "can't deliver without PV" banner is
  // moot — the delivery already happened — so it's suppressed past that
  // point instead of nagging on a closed vehicle.
  const alreadyDelivered = status === 'DELIVERED'

  const { data: checklist } = useQuery({
    queryKey: ['carpark', 'documents-checklist', vehicleId],
    queryFn: () => carparkDispoApi.getChecklist(vehicleId),
    enabled: !!vehicleId,
  })

  const { data: docsData, isLoading } = useQuery({
    queryKey: ['carpark', 'documents', vehicleId],
    queryFn: () => carparkDispoApi.getDocuments(vehicleId),
    enabled: !!vehicleId,
  })
  const documents = docsData?.documents ?? []

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['carpark', 'documents', vehicleId] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'documents-checklist', vehicleId] })
    // Best-effort: refresh the Dispo pipeline table/KPIs if the user has
    // that view open elsewhere (doc_types / blocking flags live there too).
    queryClient.invalidateQueries({ queryKey: ['carpark', 'dispo'] })
  }

  // ── Upload form state ──────────────────────────────────
  const [documentType, setDocumentType] = useState<DocumentType | ''>('')
  const [title, setTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileUrl, setFileUrl] = useState('')
  const [dmsDocumentId, setDmsDocumentId] = useState('')
  const [mode, setMode] = useState<UploadMode>('file')
  const [driveDisabledHint, setDriveDisabledHint] = useState(false)

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
      invalidateAll()
      toast.success('Document adăugat')
      setDocumentType('')
      setTitle('')
      setFile(null)
      setFileUrl('')
      setDmsDocumentId('')
      setDriveDisabledHint(false)
    },
    onError: (err) => {
      const msg = apiErrorMessage(err, 'Eroare la încărcarea documentului')
      // Multipart upload 400s with a message telling the caller Drive is
      // disabled and to use link mode instead (documents.py's
      // _create_via_upload) — surface that as an inline hint and switch
      // the form to link mode rather than a generic toast.
      if (mode === 'file' && err instanceof ApiError && err.status === 400 && /drive|disabled/i.test(msg)) {
        setDriveDisabledHint(true)
        setMode('link')
      } else {
        toast.error(msg)
      }
    },
  })

  const canSubmit = !!documentType && (mode === 'file' ? !!file : !!fileUrl || !!dmsDocumentId)

  // ── Delete ──────────────────────────────────────────────
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const deleteMutation = useMutation({
    mutationFn: (docId: number) => carparkDispoApi.deleteDocument(docId),
    onSuccess: () => {
      invalidateAll()
      toast.success('Document șters')
      setDeleteId(null)
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Eroare la ștergerea documentului')),
  })

  return (
    <div className="space-y-6">
      {/* Checklist card */}
      {checklist && (
        <Card className="p-4">
          <h3 className="text-sm font-semibold mb-3">Checklist documente</h3>
          {checklist.blocks_delivery && !alreadyDelivered && (
            <div className="mb-3 flex items-start gap-2 rounded-md border border-red-500 bg-red-50 p-3 text-sm text-red-900 dark:bg-red-950/30 dark:text-red-300">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>Lipsește PV de livrare — nu se poate livra fără el.</span>
            </div>
          )}
          {checklist.required.length === 0 ? (
            <p className="text-sm text-muted-foreground">Niciun document obligatoriu pentru acest vehicul.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {checklist.required.map((docType) => {
                const present = checklist.present.includes(docType)
                return (
                  <Badge
                    key={docType}
                    variant="outline"
                    className={
                      present
                        ? 'gap-1 border-green-500 text-green-700 dark:text-green-400'
                        : 'gap-1 border-red-500 text-red-700 dark:text-red-400'
                    }
                  >
                    {present ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                    {DOCUMENT_TYPE_LABELS[docType]}
                  </Badge>
                )
              })}
            </div>
          )}
        </Card>
      )}

      {/* Upload card */}
      {canEdit && (
        <Card className="p-4 space-y-4">
          <h3 className="text-sm font-semibold">Adaugă document</h3>

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
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ex. PV livrare semnat" />
            </div>
          </div>

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
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>URL fișier</Label>
                <Input value={fileUrl} onChange={(e) => setFileUrl(e.target.value)} placeholder="https://..." />
              </div>
              <div className="space-y-1.5">
                <Label>ID document DMS (opțional)</Label>
                <Input value={dmsDocumentId} onChange={(e) => setDmsDocumentId(e.target.value)} placeholder="ex. 1234" />
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <Button disabled={!canSubmit || uploadMutation.isPending} onClick={() => uploadMutation.mutate()}>
              {uploadMutation.isPending ? 'Se încarcă...' : 'Adaugă document'}
            </Button>
          </div>
        </Card>
      )}

      {/* Documents list */}
      <Card className="p-4">
        <h3 className="text-sm font-semibold mb-3">Documente ({documents.length})</h3>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Se încarcă...</p>
        ) : documents.length === 0 ? (
          <EmptyState icon={<FileText className="h-8 w-8" />} title="Niciun document" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tip</TableHead>
                <TableHead>Titlu</TableHead>
                <TableHead>Fișier</TableHead>
                <TableHead>Data</TableHead>
                {canDelete && <TableHead className="w-[60px]" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell>
                    <Badge variant="outline">{DOCUMENT_TYPE_LABELS[doc.document_type] ?? doc.document_type}</Badge>
                  </TableCell>
                  <TableCell>{doc.title ?? '-'}</TableCell>
                  <TableCell>
                    {safeHref(doc.file_url) ? (
                      <a
                        href={safeHref(doc.file_url)!}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        Deschide <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : doc.file_url ? (
                      <span className="text-xs text-muted-foreground" title={doc.file_url}>
                        Link invalid
                      </span>
                    ) : doc.dms_document_id ? (
                      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                        <FileText className="h-3 w-3" /> DMS #{doc.dms_document_id}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell>{formatDate(doc.upload_date)}</TableCell>
                  {canDelete && (
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        title="Șterge document"
                        onClick={() => setDeleteId(doc.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(open) => { if (!open) setDeleteId(null) }}
        title="Șterge document"
        description="Sigur vrei să ștergi acest document? Această acțiune nu poate fi anulată."
        confirmLabel="Șterge"
        variant="destructive"
        onConfirm={() => { if (deleteId != null) deleteMutation.mutate(deleteId) }}
      />
    </div>
  )
}

export default DocumenteTab
