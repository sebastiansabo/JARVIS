import { Fragment, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import {
  Trash2, Upload, FileText, Link2, Search, ChevronRight,
  Paperclip, Calendar, Users as ChildrenIcon, Download, X,
  File, FileSpreadsheet, Image as ImageIcon, PenTool,
} from 'lucide-react'
import { toast } from 'sonner'
import { marketingApi } from '@/api/marketing'
import { dmsApi } from '@/api/dms'
import { fmtDate } from './utils'
import type { MktDmsLink, DmsDocSearchResult } from '@/types/marketing'
import type { DmsFile, DmsDocument, DmsRelationshipTypeConfig } from '@/types/dms'

const DMS_STATUS_COLORS: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  archived: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
}

function formatSize(bytes: number | null | undefined) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function expiryColor(daysToExpiry: number | null) {
  if (daysToExpiry == null) return 'text-muted-foreground'
  if (daysToExpiry < 0) return 'text-red-600 dark:text-red-400'
  if (daysToExpiry <= 30) return 'text-amber-600 dark:text-amber-400'
  return 'text-green-600 dark:text-green-400'
}

function dmsFileIcon(mimeType: string | null) {
  if (!mimeType) return <File className="h-4 w-4 text-muted-foreground" />
  if (mimeType.startsWith('image/')) return <ImageIcon className="h-4 w-4 text-blue-500" />
  if (mimeType.includes('spreadsheet') || mimeType.includes('excel'))
    return <FileSpreadsheet className="h-4 w-4 text-green-600" />
  if (mimeType.includes('pdf')) return <FileText className="h-4 w-4 text-red-500" />
  return <File className="h-4 w-4 text-muted-foreground" />
}

export function FilesTab({ projectId }: { projectId: number }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showUpload, setShowUpload] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileDesc, setFileDesc] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)

  // ── Project files ──
  const { data } = useQuery({
    queryKey: ['mkt-files', projectId],
    queryFn: () => marketingApi.getFiles(projectId),
  })
  const files = data?.files ?? []

  const uploadMut = useMutation({
    mutationFn: () => marketingApi.uploadFile(projectId, selectedFile!, fileDesc || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-files', projectId] })
      setShowUpload(false)
      setSelectedFile(null)
      setFileDesc('')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (fileId: number) => marketingApi.deleteFile(fileId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-files', projectId] }),
  })

  // ── Linked DMS documents ──
  const { data: dmsData } = useQuery({
    queryKey: ['mkt-dms-docs', projectId],
    queryFn: () => marketingApi.getDmsDocuments(projectId),
  })
  const linkedDocs: MktDmsLink[] = dmsData?.documents ?? []

  const unlinkMut = useMutation({
    mutationFn: (documentId: number) => marketingApi.unlinkDmsDocument(projectId, documentId),
    onSuccess: () => {
      toast.success('Document unlinked')
      queryClient.invalidateQueries({ queryKey: ['mkt-dms-docs', projectId] })
    },
    onError: () => toast.error('Failed to unlink document'),
  })

  function fileIcon(name: string) {
    const ext = name.split('.').pop()?.toLowerCase() ?? ''
    if (['pdf'].includes(ext)) return 'PDF'
    if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(ext)) return 'IMG'
    if (['doc', 'docx'].includes(ext)) return 'DOC'
    if (['xls', 'xlsx'].includes(ext)) return 'XLS'
    if (['ppt', 'pptx'].includes(ext)) return 'PPT'
    return 'FILE'
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) { setSelectedFile(f); setShowUpload(true) }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) { setSelectedFile(f); setShowUpload(true) }
  }

  const ACCEPT = '.pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx,.ppt,.pptx'

  return (
    <div className="space-y-6">
      {/* ── Upload zone ── */}
      <div
        className={cn(
          'rounded-lg border-2 border-dashed p-6 text-center transition-colors cursor-pointer',
          isDragging ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/20' : 'border-muted-foreground/25 hover:border-muted-foreground/50',
        )}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('mkt-file-input')?.click()}
      >
        <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
        <div className="text-sm text-muted-foreground">
          Drag & drop a file here, or <span className="text-blue-600 underline">browse</span>
        </div>
        <div className="text-xs text-muted-foreground mt-1">PDF, images, Office documents — max 10 MB</div>
        <input id="mkt-file-input" type="file" accept={ACCEPT} className="hidden" onChange={handleFileSelect} />
      </div>

      {/* ── Project files list ── */}
      {files.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Project Files ({files.length})</p>
          {files.map((f) => (
            <div key={f.id} className="flex items-center gap-3 rounded-lg border p-3">
              <div className="flex h-10 w-10 items-center justify-center rounded bg-muted text-xs font-bold text-muted-foreground">
                {fileIcon(f.file_name)}
              </div>
              <div className="min-w-0 flex-1">
                <a
                  href={f.storage_uri}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium truncate block hover:underline text-blue-600 dark:text-blue-400"
                >
                  {f.file_name}
                </a>
                <div className="text-xs text-muted-foreground">
                  {f.uploaded_by_name ?? 'Unknown'} · {fmtDate(f.created_at)}
                  {f.file_size ? ` · ${(f.file_size / 1024).toFixed(0)} KB` : ''}
                </div>
                {f.description && <div className="text-xs text-muted-foreground mt-0.5">{f.description}</div>}
              </div>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => deleteMut.mutate(f.id)}>
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {files.length === 0 && linkedDocs.length === 0 && (
        <div className="text-center py-4 text-muted-foreground text-sm">No files attached yet.</div>
      )}

      {/* ── Linked DMS Documents ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium flex items-center gap-1.5">
            <Link2 className="h-4 w-4" />
            Linked Documents ({linkedDocs.length})
          </p>
          <Button variant="outline" size="sm" onClick={() => setLinkDialogOpen(true)}>
            <Link2 className="h-3.5 w-3.5 mr-1" />
            Link Document
          </Button>
        </div>

        {linkedDocs.length > 0 && (
          <div className="rounded-md border">
            <LinkedDocumentsTable
              docs={linkedDocs}
              onUnlink={(docId) => unlinkMut.mutate(docId)}
              navigate={navigate}
            />
          </div>
        )}
      </div>

      {/* ── Upload Confirmation Dialog ── */}
      <Dialog open={showUpload} onOpenChange={(open) => { if (!open) { setShowUpload(false); setSelectedFile(null); setFileDesc('') } }}>
        <DialogContent className="max-w-sm" aria-describedby={undefined}>
          <DialogHeader><DialogTitle>Upload to Google Drive</DialogTitle></DialogHeader>
          <div className="space-y-4">
            {selectedFile && (
              <div className="rounded-md border p-3 bg-muted/30">
                <div className="text-sm font-medium truncate">{selectedFile.name}</div>
                <div className="text-xs text-muted-foreground">{(selectedFile.size / 1024).toFixed(0)} KB</div>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Description (optional)</Label>
              <Input value={fileDesc} onChange={(e) => setFileDesc(e.target.value)} placeholder="e.g., Campaign brief Q1" />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { setShowUpload(false); setSelectedFile(null); setFileDesc('') }}>Cancel</Button>
              <Button disabled={!selectedFile || uploadMut.isPending} onClick={() => uploadMut.mutate()}>
                <Upload className="h-3.5 w-3.5 mr-1.5" />
                {uploadMut.isPending ? 'Uploading...' : 'Upload'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ── Link DMS Document Dialog ── */}
      <LinkDocumentDialog
        open={linkDialogOpen}
        onOpenChange={setLinkDialogOpen}
        projectId={projectId}
        linkedDocIds={linkedDocs.map((d) => d.document_id)}
      />
    </div>
  )
}

/* ────────────────────────────────────────────────────────
   Linked Documents Table — with expand/collapse per row
   ──────────────────────────────────────────────────────── */

function LinkedDocumentsTable({
  docs,
  onUnlink,
  navigate,
}: {
  docs: MktDmsLink[]
  onUnlink: (documentId: number) => void
  navigate: (path: string) => void
}) {
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8 px-2" />
          <TableHead>Title</TableHead>
          <TableHead>Category</TableHead>
          <TableHead className="text-center">Files</TableHead>
          <TableHead className="text-center">Annexes</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Expiry</TableHead>
          <TableHead className="w-[60px]" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {docs.map((doc) => (
          <Fragment key={doc.id}>
            <TableRow
              className="cursor-pointer hover:bg-muted/50"
              onClick={() => setExpandedRow(expandedRow === doc.document_id ? null : doc.document_id)}
            >
              <TableCell className="px-2">
                <ChevronRight className={cn('h-4 w-4 transition-transform', expandedRow === doc.document_id ? 'rotate-90' : '')} />
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="font-medium">{doc.title}</span>
                </div>
              </TableCell>
              <TableCell>
                {doc.category_name ? (
                  <Badge variant="outline" style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}>
                    {doc.category_name}
                  </Badge>
                ) : <span className="text-muted-foreground">—</span>}
              </TableCell>
              <TableCell className="text-center">
                {(doc.file_count ?? 0) > 0 ? (
                  <span className="inline-flex items-center gap-1 text-sm"><Paperclip className="h-3.5 w-3.5" />{doc.file_count}</span>
                ) : <span>—</span>}
              </TableCell>
              <TableCell className="text-center">
                {(doc.children_count ?? 0) > 0 ? (
                  <span className="inline-flex items-center gap-1 text-sm"><ChildrenIcon className="h-3.5 w-3.5" />{doc.children_count}</span>
                ) : <span>—</span>}
              </TableCell>
              <TableCell>
                <Badge className={cn('text-xs', DMS_STATUS_COLORS[doc.status])}>{doc.status}</Badge>
              </TableCell>
              <TableCell>
                {doc.expiry_date ? (
                  <span className={cn('text-sm font-medium', expiryColor(doc.days_to_expiry))}>
                    {formatDate(doc.expiry_date)}
                    {doc.days_to_expiry != null && (
                      <span className="block text-xs font-normal">
                        {doc.days_to_expiry < 0 ? `${Math.abs(doc.days_to_expiry)}d expired` : doc.days_to_expiry === 0 ? 'Expires today' : `${doc.days_to_expiry}d left`}
                      </span>
                    )}
                  </span>
                ) : <span className="text-muted-foreground">—</span>}
              </TableCell>
              <TableCell>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  title="Unlink document"
                  onClick={(e) => { e.stopPropagation(); onUnlink(doc.document_id) }}
                >
                  <X className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </TableCell>
            </TableRow>
            {expandedRow === doc.document_id && (
              <TableRow>
                <TableCell colSpan={8} className="bg-muted/30 p-4">
                  <DmsDocExpandedDetails
                    documentId={doc.document_id}
                    doc={doc}
                    navigate={navigate}
                  />
                </TableCell>
              </TableRow>
            )}
          </Fragment>
        ))}
      </TableBody>
    </Table>
  )
}

/* ────────────────────────────────────────────────────────
   Expanded Details for a linked DMS document —
   same format as DMS page DocumentExpandedDetails
   ──────────────────────────────────────────────────────── */

function DmsDocExpandedDetails({
  documentId,
  doc,
  navigate,
}: {
  documentId: number
  doc: MktDmsLink
  navigate: (path: string) => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['dms-document', documentId],
    queryFn: () => dmsApi.getDocument(documentId),
  })

  const { data: relTypesData } = useQuery({
    queryKey: ['dms-rel-types'],
    queryFn: () => dmsApi.listRelationshipTypes(),
    staleTime: 60_000,
  })

  const relTypes: DmsRelationshipTypeConfig[] = relTypesData?.types || []
  const detail = data?.document
  const files: DmsFile[] = detail?.files || []
  const children: Partial<Record<string, DmsDocument[]>> = detail?.children || {}
  const hasChildren = relTypes.some((t) => (children[t.slug]?.length ?? 0) > 0)

  return (
    <div className="space-y-3">
      {/* Document info row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        {doc.doc_number && (
          <div><span className="text-muted-foreground">Number:</span> <span className="font-medium">{doc.doc_number}</span></div>
        )}
        {doc.doc_date && (
          <div className="flex items-center gap-1">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Doc Date:</span> {formatDate(doc.doc_date)}
          </div>
        )}
        <div className="flex items-center gap-1">
          <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Expiry:</span>{' '}
          {doc.expiry_date ? (
            <span className={cn('font-medium', expiryColor(doc.days_to_expiry))}>
              {formatDate(doc.expiry_date)}
              {doc.days_to_expiry != null && (
                <span className="ml-1 text-xs font-normal">
                  ({doc.days_to_expiry < 0 ? `${Math.abs(doc.days_to_expiry)}d expired` : doc.days_to_expiry === 0 ? 'today' : `${doc.days_to_expiry}d left`})
                </span>
              )}
            </span>
          ) : '—'}
        </div>
        {doc.company_name && (
          <div><span className="text-muted-foreground">Company:</span> {doc.company_name}</div>
        )}
        {doc.signature_status && (
          <div className="flex items-center gap-1">
            <PenTool className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Signature:</span>{' '}
            <Badge className={cn('text-[10px] px-1.5 py-0', {
              'bg-yellow-100 text-yellow-800': doc.signature_status === 'pending',
              'bg-blue-100 text-blue-800': doc.signature_status === 'sent',
              'bg-green-100 text-green-800': doc.signature_status === 'signed',
              'bg-red-100 text-red-800': doc.signature_status === 'declined',
              'bg-gray-100 text-gray-600': doc.signature_status === 'expired',
            })}>{doc.signature_status}</Badge>
          </div>
        )}
        <div><span className="text-muted-foreground">Created by:</span> {doc.created_by_name || '—'}</div>
        <div><span className="text-muted-foreground">Linked by:</span> {doc.linked_by_name || '—'}</div>
      </div>

      {/* Files */}
      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading files...</p>
      ) : files.length > 0 && (
        <div>
          <p className="text-sm font-medium flex items-center gap-1.5 mb-2">
            <Paperclip className="h-4 w-4" />
            Files ({files.length})
          </p>
          <div className="rounded border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="text-xs py-1.5">File</TableHead>
                  <TableHead className="text-xs py-1.5">Type</TableHead>
                  <TableHead className="text-xs py-1.5 text-right">Size</TableHead>
                  <TableHead className="text-xs py-1.5">Uploaded</TableHead>
                  <TableHead className="text-xs py-1.5 w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {files.map((f) => (
                  <TableRow key={f.id}>
                    <TableCell className="py-1.5">
                      <div className="flex items-center gap-1.5">
                        {dmsFileIcon(f.mime_type)}
                        <span className="text-xs truncate max-w-[200px]">{f.file_name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs py-1.5 text-muted-foreground">{f.file_type || '—'}</TableCell>
                    <TableCell className="text-xs py-1.5 text-right">{formatSize(f.file_size)}</TableCell>
                    <TableCell className="text-xs py-1.5 text-muted-foreground">{formatDate(f.created_at)}</TableCell>
                    <TableCell className="py-1.5">
                      <a
                        href={dmsApi.downloadFileUrl(f.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex"
                      >
                        <Download className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
                      </a>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Children by type */}
      {!isLoading && hasChildren && (
        <div>
          <p className="text-sm font-medium flex items-center gap-1.5 mb-2">
            <ChildrenIcon className="h-4 w-4" />
            Child Documents
          </p>
          {relTypes.filter((t) => (children[t.slug]?.length ?? 0) > 0).map((rt) => (
            <div key={rt.slug} className="mb-2">
              <p className="text-xs font-medium text-muted-foreground mb-1">{rt.label} ({children[rt.slug]!.length})</p>
              <div className="rounded border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="text-xs py-1.5">Title</TableHead>
                      <TableHead className="text-xs py-1.5">Number</TableHead>
                      <TableHead className="text-xs py-1.5">Status</TableHead>
                      <TableHead className="text-xs py-1.5 text-center">Files</TableHead>
                      <TableHead className="text-xs py-1.5">Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {children[rt.slug]!.map((child) => (
                      <TableRow
                        key={child.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => navigate(`/app/dms/documents/${child.id}`)}
                      >
                        <TableCell className="py-1.5">
                          <span className="text-xs font-medium">{child.title}</span>
                        </TableCell>
                        <TableCell className="text-xs py-1.5 text-muted-foreground">{child.doc_number || '—'}</TableCell>
                        <TableCell className="py-1.5">
                          <Badge className={cn('text-[10px] px-1.5 py-0', DMS_STATUS_COLORS[child.status])}>
                            {child.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs py-1.5 text-center">{child.file_count ?? 0}</TableCell>
                        <TableCell className="text-xs py-1.5 text-muted-foreground">{formatDate(child.created_at)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); navigate(`/app/dms/documents/${documentId}`) }}>
          <FileText className="h-3.5 w-3.5 mr-1" />View in DMS
        </Button>
      </div>
    </div>
  )
}

/* ────────────────────────────────────────────────────────
   Link Document Dialog — search and pick DMS documents
   ──────────────────────────────────────────────────────── */

function LinkDocumentDialog({
  open,
  onOpenChange,
  projectId,
  linkedDocIds,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId: number
  linkedDocIds: number[]
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')

  const { data } = useQuery({
    queryKey: ['mkt-dms-search', search],
    queryFn: () => marketingApi.searchDmsDocuments(search || undefined),
    enabled: open,
  })
  const results: DmsDocSearchResult[] = data?.documents ?? []

  const linkMut = useMutation({
    mutationFn: (documentId: number) => marketingApi.linkDmsDocument(projectId, documentId),
    onSuccess: () => {
      toast.success('Document linked')
      queryClient.invalidateQueries({ queryKey: ['mkt-dms-docs', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-dms-search'] })
    },
    onError: () => toast.error('Failed to link document'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" aria-describedby={undefined}>
        <DialogHeader><DialogTitle>Link DMS Document</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search documents by title or number..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              autoFocus
            />
          </div>

          <div className="max-h-[300px] overflow-y-auto space-y-1">
            {results.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No documents found</p>
            ) : results.map((doc) => {
              const isLinked = linkedDocIds.includes(doc.id)
              return (
                <div
                  key={doc.id}
                  className={cn(
                    'flex items-center gap-3 rounded-md border p-2.5',
                    isLinked ? 'opacity-50' : 'hover:bg-muted/50 cursor-pointer',
                  )}
                  onClick={() => !isLinked && linkMut.mutate(doc.id)}
                >
                  <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{doc.title}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-2">
                      {doc.doc_number && <span>{doc.doc_number}</span>}
                      {doc.category_name && (
                        <Badge variant="outline" className="text-[10px] px-1 py-0" style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}>
                          {doc.category_name}
                        </Badge>
                      )}
                      <Badge className={cn('text-[10px] px-1 py-0', DMS_STATUS_COLORS[doc.status])}>{doc.status}</Badge>
                      {doc.file_count > 0 && (
                        <span className="inline-flex items-center gap-0.5"><Paperclip className="h-3 w-3" />{doc.file_count}</span>
                      )}
                    </div>
                  </div>
                  {isLinked ? (
                    <span className="text-xs text-muted-foreground">Linked</span>
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
