import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { Trash2, Upload } from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import { fmtDate } from './utils'

export function FilesTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [showUpload, setShowUpload] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileDesc, setFileDesc] = useState('')
  const [isDragging, setIsDragging] = useState(false)

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
    <div className="space-y-4">
      {/* Drop zone */}
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

      {files.length === 0 ? (
        <div className="text-center py-4 text-muted-foreground text-sm">No files attached yet.</div>
      ) : (
        <div className="space-y-2">
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

      {/* Upload Confirmation Dialog */}
      <Dialog open={showUpload} onOpenChange={(open) => { if (!open) { setShowUpload(false); setSelectedFile(null); setFileDesc('') } }}>
        <DialogContent className="max-w-sm">
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
    </div>
  )
}
