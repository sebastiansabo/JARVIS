import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, X, FileText, Image as ImageIcon } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { dmsApi } from '@/api/dms'
import { organizationApi } from '@/api/organization'
import { usersApi } from '@/api/users'
import type { DmsCategory, DmsRelationshipType } from '@/types/dms'

const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'gif']
const MAX_FILE_SIZE = 25 * 1024 * 1024

interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  companyId?: number
  categories: DmsCategory[]
  parentId?: number
  defaultRelType?: DmsRelationshipType
}

interface PendingFile {
  file: File
  preview?: string
  error?: string
}

export default function UploadDialog({
  open, onOpenChange, companyId, categories, parentId, defaultRelType,
}: UploadDialogProps) {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [categoryId, setCategoryId] = useState<string>('')
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>('')
  const [status, setStatus] = useState('draft')
  const [docNumber, setDocNumber] = useState('')
  const [docDate, setDocDate] = useState('')
  const [expiryDate, setExpiryDate] = useState('')
  const [notifyUserId, setNotifyUserId] = useState<string>('')
  const [relType, setRelType] = useState<DmsRelationshipType | ''>(defaultRelType || '')
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
  const [uploading, setUploading] = useState(false)

  const needsCompanyPicker = !companyId

  const { data: companies } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
    enabled: needsCompanyPicker && open,
  })

  const { data: users } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    enabled: open,
  })

  const { data: relTypesData } = useQuery({
    queryKey: ['dms-rel-types'],
    queryFn: () => dmsApi.listRelationshipTypes(),
    staleTime: 60_000,
    enabled: !!parentId && open,
  })

  // Sync relType when defaultRelType changes (e.g. different child type button clicked)
  useEffect(() => {
    setRelType(defaultRelType || '')
  }, [defaultRelType])

  const reset = useCallback(() => {
    setTitle('')
    setDescription('')
    setCategoryId('')
    setSelectedCompanyId('')
    setStatus('draft')
    setDocNumber('')
    setDocDate('')
    setExpiryDate('')
    setNotifyUserId('')
    setRelType(defaultRelType || '')
    // Revoke ObjectURLs to prevent memory leaks
    setPendingFiles((prev) => {
      prev.forEach((f) => { if (f.preview) URL.revokeObjectURL(f.preview) })
      return []
    })
  }, [defaultRelType])

  const handleFiles = useCallback((fileList: FileList | null) => {
    if (!fileList) return
    const newFiles: PendingFile[] = []
    for (const file of Array.from(fileList)) {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      let error: string | undefined
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        error = `Type .${ext} not allowed`
      } else if (file.size > MAX_FILE_SIZE) {
        error = `Too large (${(file.size / (1024 * 1024)).toFixed(1)}MB)`
      }
      const preview = file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined
      newFiles.push({ file, preview, error })
    }
    setPendingFiles((prev) => [...prev, ...newFiles])
  }, [])

  const removeFile = useCallback((idx: number) => {
    setPendingFiles((prev) => {
      const f = prev[idx]
      if (f.preview) URL.revokeObjectURL(f.preview)
      return prev.filter((_, i) => i !== idx)
    })
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  const resolvedCompanyId = companyId || (selectedCompanyId ? Number(selectedCompanyId) : undefined)

  const handleSubmit = async () => {
    if (!title.trim()) {
      toast.error('Title is required')
      return
    }
    if (!resolvedCompanyId) {
      toast.error('Please select a company')
      return
    }
    const validFiles = pendingFiles.filter((f) => !f.error)

    setUploading(true)
    try {
      // Step 1: Create document
      const createPayload: Record<string, unknown> = {
        title: title.trim(),
        description: description.trim() || undefined,
        category_id: categoryId ? Number(categoryId) : undefined,
        company_id: resolvedCompanyId,
        status,
        doc_number: docNumber.trim() || undefined,
        doc_date: docDate || undefined,
        expiry_date: expiryDate || undefined,
        notify_user_id: notifyUserId ? Number(notifyUserId) : undefined,
      }

      let docId: number
      if (parentId) {
        const res = await dmsApi.createChild(parentId, {
          title: title.trim(),
          description: description.trim() || undefined,
          relationship_type: (relType || 'other') as DmsRelationshipType,
          category_id: categoryId ? Number(categoryId) : undefined,
          status,
          doc_number: docNumber.trim() || undefined,
          doc_date: docDate || undefined,
          expiry_date: expiryDate || undefined,
          notify_user_id: notifyUserId ? Number(notifyUserId) : undefined,
        })
        docId = res.id
      } else {
        const res = await dmsApi.createDocument(createPayload)
        docId = res.id
      }

      // Step 2: Upload files
      if (validFiles.length > 0) {
        const uploadRes = await dmsApi.uploadFiles(
          docId,
          validFiles.map((f) => f.file),
        )
        if (uploadRes.errors?.length) {
          toast.warning(`${uploadRes.uploaded?.length || 0} files uploaded, ${uploadRes.errors.length} failed`)
        } else {
          toast.success(`Document created with ${validFiles.length} file(s)`)
        }
      } else {
        toast.success('Document created')
      }

      queryClient.invalidateQueries({ queryKey: ['dms-documents'] })
      queryClient.invalidateQueries({ queryKey: ['dms-stats'] })
      if (parentId) {
        queryClient.invalidateQueries({ queryKey: ['dms-document', parentId] })
      }
      reset()
      onOpenChange(false)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload failed'
      toast.error(msg)
    } finally {
      setUploading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v) }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{parentId ? 'Add Child Document' : 'Upload Document'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Title */}
          <div className="space-y-1.5">
            <Label htmlFor="dms-title">Title *</Label>
            <Input
              id="dms-title"
              placeholder="Document title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label htmlFor="dms-desc">Description</Label>
            <Textarea
              id="dms-desc"
              placeholder="Optional description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>

          {/* Company selector for admin users */}
          {needsCompanyPicker && (
            <div className="space-y-1.5">
              <Label>Company *</Label>
              <Select value={selectedCompanyId} onValueChange={setSelectedCompanyId}>
                <SelectTrigger><SelectValue placeholder="Select company..." /></SelectTrigger>
                <SelectContent>
                  {(companies || []).map((c) => (
                    <SelectItem key={c.id} value={c.id.toString()}>
                      {c.company}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Doc Number */}
          <div className="space-y-1.5">
            <Label htmlFor="dms-doc-number">Document Number</Label>
            <Input
              id="dms-doc-number"
              placeholder="e.g. CTR-2025-0001"
              value={docNumber}
              onChange={(e) => setDocNumber(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Category */}
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Select value={categoryId} onValueChange={setCategoryId}>
                <SelectTrigger><SelectValue placeholder="Select..." /></SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={c.id.toString()}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Status */}
            <div className="space-y-1.5">
              <Label>Status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Dates row */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="dms-doc-date">Document Date</Label>
              <Input
                id="dms-doc-date"
                type="date"
                value={docDate}
                onChange={(e) => setDocDate(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dms-expiry-date">Expiration Date</Label>
              <Input
                id="dms-expiry-date"
                type="date"
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
              />
            </div>
          </div>

          {/* Notify person */}
          <div className="space-y-1.5">
            <Label>Notify Person</Label>
            <Select value={notifyUserId || 'none'} onValueChange={(v) => setNotifyUserId(v === 'none' ? '' : v)}>
              <SelectTrigger><SelectValue placeholder="Select user to notify..." /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {(users || []).map((u) => (
                  <SelectItem key={u.id} value={u.id.toString()}>
                    {u.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Relationship type (only for children) */}
          {parentId && (
            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select value={relType || 'other'} onValueChange={(v) => setRelType(v as DmsRelationshipType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(relTypesData?.types || []).map((rt) => (
                    <SelectItem key={rt.slug} value={rt.slug}>
                      {rt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* File drop zone */}
          <div
            className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary/50 transition-colors"
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
          >
            <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              Drop files here or <span className="text-primary font-medium">browse</span>
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              PDF, DOCX, XLSX, JPG, PNG, TIFF, GIF — max 25MB each
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.xlsx,.jpg,.jpeg,.png,.tiff,.tif,.gif"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </div>

          {/* File list */}
          {pendingFiles.length > 0 && (
            <div className="space-y-2 max-h-40 overflow-y-auto">
              {pendingFiles.map((pf, idx) => (
                <div
                  key={idx}
                  className={cn(
                    'flex items-center gap-2 rounded-md border p-2 text-sm',
                    pf.error && 'border-destructive bg-destructive/5',
                  )}
                >
                  {pf.preview ? (
                    <img src={pf.preview} alt="" className="h-8 w-8 rounded object-cover" />
                  ) : pf.file.type.startsWith('image/') ? (
                    <ImageIcon className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <FileText className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="flex-1 truncate">{pf.file.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {(pf.file.size / 1024).toFixed(0)} KB
                  </span>
                  {pf.error && (
                    <span className="text-xs text-destructive">{pf.error}</span>
                  )}
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeFile(idx)}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => { reset(); onOpenChange(false) }} disabled={uploading}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={uploading || !title.trim() || !resolvedCompanyId}>
            {uploading ? 'Uploading...' : parentId ? 'Add' : 'Create & Upload'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
