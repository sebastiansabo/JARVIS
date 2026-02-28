import { useState, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import {
  Upload,
  FileText,
  Trash2,
  Loader2,
  Search,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { statementsApi } from '@/api/statements'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import type { UploadResult } from '@/types/statements'

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const MAX_TOTAL_SIZE = 50 * 1024 * 1024 // 50MB

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const filesMobileFields: MobileCardField<any>[] = [
  { key: 'filename', label: 'Filename', isPrimary: true, render: (s) => s.filename },
  { key: 'company', label: 'Company', isSecondary: true, render: (s) => s.company_name ?? '—' },
  { key: 'period', label: 'Period', render: (s) => s.period_from && s.period_to ? `${formatDate(s.period_from)} — ${formatDate(s.period_to)}` : '—' },
  { key: 'txns', label: 'Transactions', render: (s) => <span className="text-xs">{s.total_transactions} total / <span className="text-green-500">{s.new_transactions} new</span></span> },
  { key: 'account', label: 'Account', expandOnly: true, render: (s) => <span className="text-xs">{s.account_number ?? '—'}</span> },
  { key: 'uploaded', label: 'Uploaded', expandOnly: true, render: (s) => <span className="text-xs">{formatDateTime(s.uploaded_at)}</span> },
  { key: 'dupes', label: 'Duplicates', expandOnly: true, render: (s) => <span className="text-xs text-muted-foreground">{s.duplicate_transactions}</span> },
]

function formatDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

function formatDateTime(d: string) {
  return new Date(d).toLocaleString('ro-RO', { dateStyle: 'short', timeStyle: 'short' })
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function FilesTab() {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const [search, setSearch] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['statements-files'],
    queryFn: () => statementsApi.getStatements(),
  })

  const statements = data?.statements ?? []

  const filtered = statements.filter((s) => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      s.filename.toLowerCase().includes(q) ||
      (s.company_name?.toLowerCase().includes(q) ?? false) ||
      (s.company_cui?.toLowerCase().includes(q) ?? false)
    )
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => statementsApi.deleteStatement(id),
    onSuccess: () => {
      toast.success('Statement deleted')
      queryClient.invalidateQueries({ queryKey: ['statements-files'] })
      queryClient.invalidateQueries({ queryKey: ['statements-summary'] })
    },
    onError: () => toast.error('Delete failed'),
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-0 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-8" placeholder="Search statements..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <span className="hidden sm:inline text-xs text-muted-foreground">{filtered.length} statements</span>
        <Button size="icon" className="ml-auto md:size-auto md:px-3" onClick={() => setUploadOpen(true)}>
          <Upload className="h-4 w-4 md:mr-1" />
          <span className="hidden md:inline">Upload Statement</span>
        </Button>
      </div>

      {isLoading ? (
        <Card className="p-6">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted mb-2" />
          ))}
        </Card>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-8 w-8" />}
          title="No statements uploaded"
          description="Upload PDF bank statements to start processing transactions."
          action={
            <Button onClick={() => setUploadOpen(true)}>
              <Upload className="mr-1.5 h-4 w-4" />
              Upload Statement
            </Button>
          }
        />
      ) : isMobile ? (
        <MobileCardList
          data={filtered}
          fields={filesMobileFields}
          getRowId={(s) => s.id}
          actions={(s) => (
            <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setDeleteId(s.id)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Filename</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Account</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead className="text-right">Total Txns</TableHead>
                  <TableHead className="text-right">New</TableHead>
                  <TableHead className="text-right">Duplicates</TableHead>
                  <TableHead>Uploaded</TableHead>
                  <TableHead className="w-16">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="text-sm font-medium">{s.filename}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{s.company_name ?? '—'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground truncate max-w-[120px]">{s.account_number ?? '—'}</TableCell>
                    <TableCell className="text-xs whitespace-nowrap">
                      {s.period_from && s.period_to
                        ? `${formatDate(s.period_from)} — ${formatDate(s.period_to)}`
                        : '—'}
                    </TableCell>
                    <TableCell className="text-right text-sm">{s.total_transactions}</TableCell>
                    <TableCell className="text-right text-sm text-green-500">{s.new_transactions}</TableCell>
                    <TableCell className="text-right text-sm text-muted-foreground">{s.duplicate_transactions}</TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatDateTime(s.uploaded_at)}
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setDeleteId(s.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      {/* Upload dialog */}
      <UploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSuccess={() => {
          setUploadOpen(false)
          queryClient.invalidateQueries({ queryKey: ['statements-files'] })
          queryClient.invalidateQueries({ queryKey: ['statements-transactions'] })
          queryClient.invalidateQueries({ queryKey: ['statements-summary'] })
        }}
      />

      {/* Delete confirm */}
      <ConfirmDialog
        open={deleteId !== null}
        title="Delete Statement"
        description="This will remove the statement record. Imported transactions will be preserved."
        onOpenChange={() => setDeleteId(null)}
        onConfirm={() => deleteId !== null && deleteMutation.mutate(deleteId)}
        destructive
      />
    </div>
  )
}

/* ──── Upload Dialog ──── */

function UploadDialog({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [dragActive, setDragActive] = useState(false)
  const [result, setResult] = useState<UploadResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const uploadMutation = useMutation({
    mutationFn: (selectedFiles: File[]) => statementsApi.uploadStatements(selectedFiles),
    onSuccess: (data) => {
      setResult(data)
      toast.success(`Uploaded: ${data.total_new} new, ${data.total_duplicates} duplicates`)
    },
    onError: () => toast.error('Upload failed'),
  })

  const validateFiles = useCallback((fileList: FileList | File[]) => {
    const arr = Array.from(fileList)
    const valid: File[] = []
    let totalSize = files.reduce((s, f) => s + f.size, 0)
    for (const f of arr) {
      if (!f.name.toLowerCase().endsWith('.pdf')) {
        toast.error(`${f.name}: Only PDF files accepted`)
        continue
      }
      if (f.size > MAX_FILE_SIZE) {
        toast.error(`${f.name}: File too large (max 10MB)`)
        continue
      }
      totalSize += f.size
      if (totalSize > MAX_TOTAL_SIZE) {
        toast.error('Total upload size exceeds 50MB')
        break
      }
      valid.push(f)
    }
    setFiles((prev) => [...prev, ...valid])
  }, [files])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    if (e.dataTransfer.files.length) validateFiles(e.dataTransfer.files)
  }

  const reset = () => {
    setFiles([])
    setResult(null)
  }

  const handleClose = () => {
    if (result) onSuccess()
    else onClose()
    reset()
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload Bank Statements</DialogTitle>
          <DialogDescription>Drag-drop or select PDF bank statements to upload and parse.</DialogDescription>
        </DialogHeader>

        {!result ? (
          <div className="space-y-4">
            {/* Drag-drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                'flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors',
                dragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-muted-foreground/50',
              )}
            >
              <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
              <p className="text-sm font-medium">Drop PDF files here or click to browse</p>
              <p className="text-xs text-muted-foreground mt-1">Max 10MB per file, 50MB total</p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                multiple
                className="hidden"
                onChange={(e) => e.target.files && validateFiles(e.target.files)}
              />
            </div>

            {/* File list */}
            {files.length > 0 && (
              <div className="space-y-1">
                {files.map((f, i) => (
                  <div key={i} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span className="truncate max-w-[300px]">{f.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">{formatFileSize(f.size)}</span>
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={handleClose}>Cancel</Button>
              <Button
                disabled={files.length === 0 || uploadMutation.isPending}
                onClick={() => uploadMutation.mutate(files)}
              >
                {uploadMutation.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Upload className="mr-1.5 h-4 w-4" />}
                {uploadMutation.isPending ? 'Uploading...' : `Upload & Parse (${files.length})`}
              </Button>
            </div>
          </div>
        ) : (
          /* Upload results */
          <div className="space-y-3">
            <div className="flex items-center gap-3 text-sm">
              <span className="text-green-500 font-medium">{result.total_new} new transactions</span>
              <span className="text-muted-foreground">{result.total_duplicates} duplicates skipped</span>
            </div>
            {result.statements.map((s, i) => (
              <div key={i} className="rounded-md border p-3 text-sm">
                <div className="font-medium">{s.filename}</div>
                <div className="text-xs text-muted-foreground mt-1">
                  {s.company_name} &middot; {s.total_transactions} txns &middot;
                  {s.new_transactions} new &middot; {s.duplicate_transactions} dupes &middot;
                  {s.vendor_matched_count} vendor-matched &middot; {s.invoice_matched_count} invoice-matched
                </div>
              </div>
            ))}
            <div className="flex justify-end">
              <Button onClick={handleClose}>Done</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
