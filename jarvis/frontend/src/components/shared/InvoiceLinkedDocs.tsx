import { useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText, Link2, Paperclip, Search, X, Upload, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn, useDebounce } from '@/lib/utils'
import { toast } from 'sonner'
import type { InvoiceDmsLink, DmsDocSearchResult } from '@/types/invoices'

export interface DmsApiCallbacks {
  getDocs: (invoiceId: number) => Promise<{ documents: InvoiceDmsLink[] }>
  unlinkDoc: (invoiceId: number, docId: number) => Promise<{ success: boolean }>
  searchDocs: (q?: string, limit?: number) => Promise<{ documents: DmsDocSearchResult[] }>
  linkDoc: (invoiceId: number, documentId: number) => Promise<{ success: boolean; id: number }>
  uploadAndLink?: (invoiceId: number, files: File[]) => Promise<{ success: boolean; documents: Array<{ document_id: number; title: string; file: string }>; errors: Array<{ file: string; error: string }> }>
}

const DMS_STATUS_COLORS: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  archived: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'gif']
const MAX_FILE_SIZE = 25 * 1024 * 1024

export function InvoiceLinkedDocs({ invoiceId, isBin, canEdit, api }: {
  invoiceId: number
  isBin: boolean
  canEdit: boolean
  api: DmsApiCallbacks
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)

  const { data: dmsData } = useQuery({
    queryKey: ['invoice-dms-docs', invoiceId],
    queryFn: () => api.getDocs(invoiceId),
  })
  const linkedDocs: InvoiceDmsLink[] = dmsData?.documents ?? []

  const unlinkMut = useMutation({
    mutationFn: (docId: number) => api.unlinkDoc(invoiceId, docId),
    onSuccess: () => {
      toast.success('Document unlinked')
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-docs', invoiceId] })
    },
    onError: () => toast.error('Failed to unlink document'),
  })

  return (
    <div className="mt-3 pt-3 border-t border-border/50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium flex items-center gap-1.5 text-muted-foreground">
          <Link2 className="h-3.5 w-3.5" />
          Linked Documents{linkedDocs.length > 0 && ` (${linkedDocs.length})`}
        </span>
        {!isBin && canEdit && (
          <Button variant="ghost" size="sm" className="h-6 text-[11px] px-2" onClick={() => setLinkDialogOpen(true)}>
            <Link2 className="h-3 w-3 mr-1" />Link
          </Button>
        )}
      </div>

      {linkedDocs.length > 0 && (
        <div className="space-y-1">
          {linkedDocs.map((doc) => (
            <div key={doc.id} className="flex items-center gap-2 text-xs rounded-md border px-2.5 py-1.5 hover:bg-muted/50 group">
              <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span
                className="font-medium truncate cursor-pointer hover:underline text-blue-600 dark:text-blue-400"
                onClick={() => navigate(`/app/dms/documents/${doc.document_id}`)}
              >
                {doc.title}
              </span>
              {doc.category_name && (
                <Badge variant="outline" className="text-[10px] px-1 py-0 shrink-0" style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}>
                  {doc.category_name}
                </Badge>
              )}
              <Badge className={cn('text-[10px] px-1 py-0 shrink-0', DMS_STATUS_COLORS[doc.status])}>{doc.status}</Badge>
              {doc.file_count > 0 && (
                <span className="inline-flex items-center gap-0.5 text-muted-foreground shrink-0">
                  <Paperclip className="h-3 w-3" />{doc.file_count}
                </span>
              )}
              <span className="flex-1" />
              {!isBin && canEdit && (
                <Button
                  variant="ghost" size="icon" className="h-5 w-5 opacity-0 group-hover:opacity-100"
                  onClick={() => unlinkMut.mutate(doc.document_id)}
                >
                  <X className="h-3 w-3 text-destructive" />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      <InvoiceLinkDocumentDialog
        open={linkDialogOpen}
        onOpenChange={setLinkDialogOpen}
        invoiceId={invoiceId}
        linkedDocIds={linkedDocs.map((d) => d.document_id)}
        api={api}
      />
    </div>
  )
}

function InvoiceLinkDocumentDialog({
  open,
  onOpenChange,
  invoiceId,
  linkedDocIds,
  api,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  invoiceId: number
  linkedDocIds: number[]
  api: DmsApiCallbacks
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragOver, setIsDragOver] = useState(false)

  const { data } = useQuery({
    queryKey: ['invoice-dms-search', debouncedSearch],
    queryFn: () => api.searchDocs(debouncedSearch || undefined),
    enabled: open,
  })
  const results: DmsDocSearchResult[] = data?.documents ?? []

  const linkMut = useMutation({
    mutationFn: (documentId: number) => api.linkDoc(invoiceId, documentId),
    onSuccess: () => {
      toast.success('Document linked')
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-docs', invoiceId] })
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-search'] })
    },
    onError: () => toast.error('Failed to link document'),
  })

  const uploadMut = useMutation({
    mutationFn: (files: File[]) => {
      if (!api.uploadAndLink) throw new Error('Upload not supported')
      return api.uploadAndLink(invoiceId, files)
    },
    onSuccess: (res) => {
      const count = res.documents?.length ?? 0
      if (count > 0) toast.success(`${count} file${count > 1 ? 's' : ''} uploaded & linked to DMS`)
      if (res.errors?.length) toast.error(`${res.errors.length} file${res.errors.length > 1 ? 's' : ''} failed`)
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-docs', invoiceId] })
      queryClient.invalidateQueries({ queryKey: ['invoice-dms-search'] })
      queryClient.invalidateQueries({ queryKey: ['dms-documents'] })
    },
    onError: (err: Error) => toast.error(`Upload failed: ${err.message}`),
  })

  const validateAndUpload = useCallback((fileList: FileList | File[]) => {
    const files = Array.from(fileList)
    const valid: File[] = []
    for (const f of files) {
      const ext = f.name.split('.').pop()?.toLowerCase() || ''
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        toast.error(`${f.name}: unsupported file type`)
        continue
      }
      if (f.size > MAX_FILE_SIZE) {
        toast.error(`${f.name}: exceeds 25MB limit`)
        continue
      }
      valid.push(f)
    }
    if (valid.length > 0) uploadMut.mutate(valid)
  }, [uploadMut])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
    if (e.dataTransfer.files.length > 0) validateAndUpload(e.dataTransfer.files)
  }, [validateAndUpload])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[1080px]" aria-describedby={undefined}>
        <DialogHeader><DialogTitle>Link DMS Document</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {/* Quick Upload Zone */}
          {api.uploadAndLink && (
            <div
              className={cn(
                'border-2 border-dashed rounded-lg p-4 text-center transition-colors cursor-pointer',
                isDragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-primary/50',
                uploadMut.isPending && 'opacity-60 pointer-events-none',
              )}
              onDragOver={(e) => { e.preventDefault(); setIsDragOver(true) }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={ALLOWED_EXTENSIONS.map(e => `.${e}`).join(',')}
                className="hidden"
                onChange={(e) => { if (e.target.files?.length) validateAndUpload(e.target.files); e.target.value = '' }}
              />
              {uploadMut.isPending ? (
                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Uploading & linking to DMS...
                </div>
              ) : (
                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Upload className="h-4 w-4" />
                  Drop files here or click to upload — creates DMS document & links to invoice
                </div>
              )}
            </div>
          )}

          {/* Divider */}
          {api.uploadAndLink && (
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <div className="flex-1 border-t" />
              or link existing document
              <div className="flex-1 border-t" />
            </div>
          )}

          {/* Search existing documents */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search documents by title or number..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              autoFocus={!api.uploadAndLink}
            />
          </div>

          <div className="max-h-[400px] overflow-y-auto space-y-1">
            {results.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No documents found</p>
            ) : results.map((doc) => {
              const isLinked = linkedDocIds.includes(doc.id)
              return (
                <div
                  key={doc.id}
                  className={cn(
                    'grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-4 rounded-md border px-3 py-2',
                    isLinked ? 'opacity-50' : 'hover:bg-muted/50 cursor-pointer',
                  )}
                  onClick={() => !isLinked && linkMut.mutate(doc.id)}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{doc.title}</div>
                      {doc.doc_number && <div className="text-xs text-muted-foreground">{doc.doc_number}</div>}
                    </div>
                  </div>
                  {doc.category_name ? (
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0" style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}>
                      {doc.category_name}
                    </Badge>
                  ) : <span />}
                  <Badge className={cn('text-[10px] px-1.5 py-0 shrink-0', DMS_STATUS_COLORS[doc.status])}>{doc.status}</Badge>
                  {doc.file_count > 0 ? (
                    <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground shrink-0"><Paperclip className="h-3 w-3" />{doc.file_count}</span>
                  ) : <span />}
                  {isLinked ? (
                    <span className="text-xs text-muted-foreground shrink-0">Linked</span>
                  ) : (
                    <Button variant="ghost" size="sm" className="h-7 shrink-0" disabled={linkMut.isPending}>
                      <Link2 className="h-3.5 w-3.5 mr-1" />Link
                    </Button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
