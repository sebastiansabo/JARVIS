import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, X, FileText, Image as ImageIcon, Shield, Folder, ChevronRight, ChevronDown, Search, Link2 } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DateField } from '@/components/ui/date-field'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { MultiSelectPills } from '@/components/shared/MultiSelectPills'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { dmsApi } from '@/api/dms'
import { organizationApi } from '@/api/organization'
import { usersApi } from '@/api/users'
import { rolesApi } from '@/api/roles'
import { settingsApi } from '@/api/settings'
import type { DmsCategory, DmsFolder, DmsRelationshipType } from '@/types/dms'

const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'gif']
const MAX_FILE_SIZE = 25 * 1024 * 1024

interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  companyId?: number
  categories: DmsCategory[]
  parentId?: number
  defaultRelType?: DmsRelationshipType
  folderId?: number | null
}

interface PendingFile {
  file: File
  preview?: string
  error?: string
}

export default function UploadDialog({
  open, onOpenChange, companyId, categories, parentId, defaultRelType, folderId: propFolderId,
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
  const [visibility, setVisibility] = useState<'all' | 'restricted'>('all')
  const [allowedRoleIds, setAllowedRoleIds] = useState<number[]>([])
  const [allowedUserIds, setAllowedUserIds] = useState<number[]>([])
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [docMode, setDocMode] = useState<'main' | 'child'>(parentId ? 'child' : 'main')
  const [parentSearch, setParentSearch] = useState('')
  const [selectedParentId, setSelectedParentId] = useState<number | null>(parentId ?? null)
  const [selectedParentTitle, setSelectedParentTitle] = useState('')
  const [parentDropdownOpen, setParentDropdownOpen] = useState(false)
  const [selectedFolderId, setSelectedFolderId] = useState<number | null>(propFolderId ?? null)
  const [folderTreeOpen, setFolderTreeOpen] = useState(false)
  const [expandedFolderIds, setExpandedFolderIds] = useState<Set<number>>(new Set())

  // Sync folder when prop changes
  useEffect(() => {
    setSelectedFolderId(propFolderId ?? null)
  }, [propFolderId])

  const needsCompanyPicker = !companyId

  const { data: companies } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
    staleTime: 10 * 60_000,
    enabled: needsCompanyPicker && open,
  })

  const { data: users } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    enabled: open,
  })

  const { data: roles } = useQuery({
    queryKey: ['roles'],
    queryFn: () => rolesApi.getRoles(),
    staleTime: 5 * 60_000,
    enabled: open,
  })

  const { data: relTypesData } = useQuery({
    queryKey: ['dms-rel-types'],
    queryFn: () => dmsApi.listRelationshipTypes(),
    staleTime: 5 * 60_000,
    enabled: (!!parentId || docMode === 'child') && open,
  })

  // Search parent documents for child mode
  const { data: parentDocsData } = useQuery({
    queryKey: ['dms-parent-search', parentSearch],
    queryFn: () => dmsApi.listDocuments({ search: parentSearch, limit: 15 }),
    enabled: open && docMode === 'child' && parentSearch.length >= 2,
    staleTime: 30_000,
  })
  const parentDocs = parentDocsData?.documents || []

  const { data: folderTreeData } = useQuery({
    queryKey: ['dms-folder-tree'],
    queryFn: () => dmsApi.getFolderTree(),
    staleTime: 5 * 60_000,
    enabled: open,
  })
  const allFolders: DmsFolder[] = folderTreeData?.folders || []

  const { data: dmsConfigOpts } = useQuery({
    queryKey: ['settings', 'dropdown-options', 'dms_config'],
    queryFn: () => settingsApi.getDropdownOptions('dms_config'),
    staleTime: 5 * 60_000,
    enabled: open,
  })
  const requireParentForChild = dmsConfigOpts?.find((o) => o.value === 'require_parent_for_child')?.is_active ?? true

  const selectedFolderName = allFolders.find((f) => f.id === selectedFolderId)?.name

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
    setDocMode(parentId ? 'child' : 'main')
    setParentSearch('')
    setSelectedParentId(parentId ?? null)
    setSelectedParentTitle('')
    setParentDropdownOpen(false)
    setSelectedFolderId(propFolderId ?? null)
    setFolderTreeOpen(false)
    setExpandedFolderIds(new Set())
    setVisibility('all')
    setAllowedRoleIds([])
    setAllowedUserIds([])
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

  const effectiveParentId = docMode === 'child' ? (selectedParentId ?? parentId) : null

  const handleSubmit = async () => {
    if (!title.trim()) {
      toast.error('Title is required')
      return
    }
    if (!resolvedCompanyId) {
      toast.error('Please select a company')
      return
    }
    if (docMode === 'child' && !effectiveParentId && requireParentForChild) {
      toast.error('Please select a parent document')
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
        visibility,
        allowed_role_ids: visibility === 'restricted' && allowedRoleIds.length ? allowedRoleIds : null,
        allowed_user_ids: visibility === 'restricted' && allowedUserIds.length ? allowedUserIds : null,
        folder_id: selectedFolderId || undefined,
      }

      let docId: number
      if (effectiveParentId) {
        const res = await dmsApi.createChild(effectiveParentId, {
          title: title.trim(),
          description: description.trim() || undefined,
          relationship_type: (relType || 'other') as DmsRelationshipType,
          category_id: categoryId ? Number(categoryId) : undefined,
          status,
          doc_number: docNumber.trim() || undefined,
          doc_date: docDate || undefined,
          expiry_date: expiryDate || undefined,
          notify_user_id: notifyUserId ? Number(notifyUserId) : undefined,
          visibility,
          allowed_role_ids: visibility === 'restricted' && allowedRoleIds.length ? allowedRoleIds : null,
          allowed_user_ids: visibility === 'restricted' && allowedUserIds.length ? allowedUserIds : null,
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
      queryClient.invalidateQueries({ queryKey: ['dms-folder-tree'] })
      if (effectiveParentId) {
        queryClient.invalidateQueries({ queryKey: ['dms-document', effectiveParentId] })
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

  const isChild = docMode === 'child' || !!parentId

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v) }}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] flex flex-col gap-0 p-0">
        <DialogHeader className="px-6 pt-6 pb-3">
          <DialogTitle>{effectiveParentId ? 'Add Child Document' : 'Upload Document'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3 overflow-y-auto px-6 pb-2">
          {/* ── Document type toggle ── */}
          {!parentId && (
            <div className="flex gap-0.5 rounded-lg bg-muted p-0.5">
              <button
                type="button"
                className={cn(
                  'flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  docMode === 'main' ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground',
                )}
                onClick={() => { setDocMode('main'); setSelectedParentId(null); setSelectedParentTitle(''); setParentSearch('') }}
              >
                Main Document
              </button>
              <button
                type="button"
                className={cn(
                  'flex-1 flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  docMode === 'child' ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground',
                )}
                onClick={() => setDocMode('child')}
              >
                <Link2 className="h-3 w-3" />
                Child Document
              </button>
            </div>
          )}

          {/* ── Parent document picker (child mode) ── */}
          {docMode === 'child' && !parentId && (
            <div className="space-y-1">
              <Label className="text-xs">Parent Document{requireParentForChild ? ' *' : ''}</Label>
              {selectedParentId ? (
                <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-2.5 py-1.5 text-xs">
                  <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <span className="flex-1 truncate font-medium">{selectedParentTitle}</span>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground"
                    onClick={() => { setSelectedParentId(null); setSelectedParentTitle(''); setParentSearch('') }}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <div className="relative">
                  <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder="Search parent document..."
                    value={parentSearch}
                    onChange={(e) => { setParentSearch(e.target.value); setParentDropdownOpen(true) }}
                    onFocus={() => parentSearch.length >= 2 && setParentDropdownOpen(true)}
                    className="pl-8 h-8 text-xs"
                  />
                  {parentDropdownOpen && parentSearch.length >= 2 && (
                    <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md max-h-40 overflow-y-auto">
                      {parentDocs.length === 0 ? (
                        <p className="text-xs text-muted-foreground p-2.5 text-center">No documents found</p>
                      ) : (
                        parentDocs.map((doc) => (
                          <div
                            key={doc.id}
                            className="flex items-center gap-2 px-2.5 py-1.5 text-xs cursor-pointer hover:bg-muted/80 transition-colors"
                            onClick={() => {
                              setSelectedParentId(doc.id)
                              setSelectedParentTitle(doc.title)
                              setParentSearch('')
                              setParentDropdownOpen(false)
                            }}
                          >
                            <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="truncate font-medium">{doc.title}</p>
                              {doc.doc_number && (
                                <p className="text-[10px] text-muted-foreground">{doc.doc_number}</p>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Title + Doc Number row ── */}
          <div className="grid grid-cols-5 gap-2">
            <div className="col-span-3 space-y-1">
              <Label className="text-xs" htmlFor="dms-title">Title *</Label>
              <Input id="dms-title" placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} className="h-8 text-xs" />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs" htmlFor="dms-doc-number">Doc Number</Label>
              <Input id="dms-doc-number" placeholder="CTR-2025-0001" value={docNumber} onChange={(e) => setDocNumber(e.target.value)} className="h-8 text-xs" />
            </div>
          </div>

          {/* ── Description (compact) ── */}
          <div className="space-y-1">
            <Label className="text-xs" htmlFor="dms-desc">Description</Label>
            <Textarea id="dms-desc" placeholder="Optional description" value={description} onChange={(e) => setDescription(e.target.value)} rows={1} className="text-xs min-h-[32px] resize-y" />
          </div>

          {/* ── Company selector for admin users ── */}
          {needsCompanyPicker && (
            <div className="space-y-1">
              <Label className="text-xs">Company *</Label>
              <Select value={selectedCompanyId} onValueChange={setSelectedCompanyId}>
                <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Select company..." /></SelectTrigger>
                <SelectContent>
                  {(companies || []).map((c) => (
                    <SelectItem key={c.id} value={c.id.toString()} className="text-xs">{c.company}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* ── Folder | Category | Status row ── */}
          <div className={cn('grid gap-2', isChild ? 'grid-cols-4' : 'grid-cols-3')}>
            <div className={cn('space-y-1', isChild ? 'col-span-1' : 'col-span-1')}>
              <Label className="text-xs">Folder</Label>
              <div
                className="flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs cursor-pointer hover:bg-muted/50 transition-colors h-8"
                onClick={() => setFolderTreeOpen(!folderTreeOpen)}
              >
                <Folder className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className={cn('flex-1 truncate', !selectedFolderName && 'text-muted-foreground')}>
                  {selectedFolderName || 'Root'}
                </span>
                {selectedFolderId ? (
                  <button type="button" className="text-muted-foreground hover:text-foreground" onClick={(e) => { e.stopPropagation(); setSelectedFolderId(null) }}>
                    <X className="h-3 w-3" />
                  </button>
                ) : (
                  <ChevronDown className={cn('h-3 w-3 text-muted-foreground transition-transform', folderTreeOpen && 'rotate-180')} />
                )}
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Category</Label>
              <Select value={categoryId} onValueChange={setCategoryId}>
                <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Select..." /></SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={c.id.toString()} className="text-xs">{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft" className="text-xs">Draft</SelectItem>
                  <SelectItem value="active" className="text-xs">Active</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {isChild && (
              <div className="space-y-1">
                <Label className="text-xs">Rel. Type</Label>
                <Select value={relType || 'other'} onValueChange={(v) => setRelType(v as DmsRelationshipType)}>
                  <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(relTypesData?.types || []).map((rt) => (
                      <SelectItem key={rt.slug} value={rt.slug} className="text-xs">{rt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* ── Folder tree dropdown (conditionally shown) ── */}
          {folderTreeOpen && (
            <div className="rounded-md border max-h-40 overflow-y-auto p-1 -mt-1">
              {allFolders.length === 0 ? (
                <p className="text-xs text-muted-foreground p-2">No folders available</p>
              ) : (
                <FolderTreePicker
                  folders={allFolders}
                  parentId={null}
                  selectedId={selectedFolderId}
                  expandedIds={expandedFolderIds}
                  onSelect={(id) => { setSelectedFolderId(id); setFolderTreeOpen(false) }}
                  onToggleExpand={(id) =>
                    setExpandedFolderIds((prev) => {
                      const next = new Set(prev)
                      next.has(id) ? next.delete(id) : next.add(id)
                      return next
                    })
                  }
                  depth={0}
                />
              )}
            </div>
          )}

          {/* ── Dates + Notify row ── */}
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Doc Date</Label>
              <DateField value={docDate} onChange={setDocDate} className="w-full h-8 text-xs" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Expiry Date</Label>
              <DateField value={expiryDate} onChange={setExpiryDate} className="w-full h-8 text-xs" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notify</Label>
              <Select value={notifyUserId || 'none'} onValueChange={(v) => setNotifyUserId(v === 'none' ? '' : v)}>
                <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none" className="text-xs">None</SelectItem>
                  {(users || []).map((u) => (
                    <SelectItem key={u.id} value={u.id.toString()} className="text-xs">{u.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* ── Visibility (compact) ── */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Label className="text-xs flex items-center gap-1">
                <Shield className="h-3 w-3" />
                Visibility
              </Label>
              <Select value={visibility} onValueChange={(v) => setVisibility(v as 'all' | 'restricted')}>
                <SelectTrigger className="h-7 text-xs w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" className="text-xs">Everyone</SelectItem>
                  <SelectItem value="restricted" className="text-xs">Restricted</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {visibility === 'restricted' && (
              <div className="space-y-2 rounded-md border border-dashed border-amber-400/50 p-2.5">
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">Allowed Roles</Label>
                  <MultiSelectPills
                    options={(roles || []).map((r) => ({ value: r.id, label: r.name }))}
                    selected={allowedRoleIds}
                    onChange={(v) => setAllowedRoleIds(v as number[])}
                    placeholder="Select roles..."
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">Allowed Users</Label>
                  <MultiSelectPills
                    options={(users || []).map((u) => ({ value: u.id, label: u.name }))}
                    selected={allowedUserIds}
                    onChange={(v) => setAllowedUserIds(v as number[])}
                    placeholder="Search users..."
                  />
                </div>
                {allowedRoleIds.length === 0 && allowedUserIds.length === 0 && (
                  <p className="text-[10px] text-amber-600">No roles/users selected — only you and admins will see this.</p>
                )}
              </div>
            )}
          </div>

          {/* ── File drop zone (compact) ── */}
          <div
            className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-primary/50 transition-colors"
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
          >
            <Upload className="h-5 w-5 mx-auto text-muted-foreground mb-1" />
            <p className="text-xs text-muted-foreground">
              Drop files here or <span className="text-primary font-medium">browse</span>
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              PDF, DOCX, XLSX, JPG, PNG, TIFF, GIF — max 25MB
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

          {/* ── File list ── */}
          {pendingFiles.length > 0 && (
            <div className="space-y-1 max-h-28 overflow-y-auto">
              {pendingFiles.map((pf, idx) => (
                <div
                  key={idx}
                  className={cn(
                    'flex items-center gap-2 rounded-md border p-1.5 text-xs',
                    pf.error && 'border-destructive bg-destructive/5',
                  )}
                >
                  {pf.preview ? (
                    <img src={pf.preview} alt="" className="h-6 w-6 rounded object-cover" />
                  ) : pf.file.type.startsWith('image/') ? (
                    <ImageIcon className="h-3.5 w-3.5 text-muted-foreground" />
                  ) : (
                    <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                  <span className="flex-1 truncate">{pf.file.name}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {(pf.file.size / 1024).toFixed(0)} KB
                  </span>
                  {pf.error && <span className="text-[10px] text-destructive">{pf.error}</span>}
                  <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => removeFile(idx)}>
                    <X className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter className="px-6 py-3 border-t">
          <Button variant="outline" size="sm" onClick={() => { reset(); onOpenChange(false) }} disabled={uploading}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSubmit} disabled={uploading || !title.trim() || !resolvedCompanyId || (docMode === 'child' && !effectiveParentId && requireParentForChild)}>
            {uploading ? 'Uploading...' : effectiveParentId ? 'Add Child' : 'Create & Upload'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ── Compact inline folder tree picker ── */
function FolderTreePicker({
  folders,
  parentId,
  selectedId,
  expandedIds,
  onSelect,
  onToggleExpand,
  depth,
}: {
  folders: DmsFolder[]
  parentId: number | null
  selectedId: number | null
  expandedIds: Set<number>
  onSelect: (id: number) => void
  onToggleExpand: (id: number) => void
  depth: number
}) {
  const children = folders
    .filter((f) => f.parent_id === parentId)
    .sort((a, b) => a.sort_order - b.sort_order)

  if (children.length === 0) return null

  return (
    <>
      {children.map((folder) => {
        const hasChildren = folders.some((f) => f.parent_id === folder.id)
        const isExpanded = expandedIds.has(folder.id)
        const isSelected = selectedId === folder.id

        return (
          <div key={folder.id}>
            <div
              className={cn(
                'flex items-center gap-1 rounded px-1.5 py-1 text-sm cursor-pointer hover:bg-muted/80 transition-colors',
                isSelected && 'bg-primary/10 text-primary font-medium',
              )}
              style={{ paddingLeft: `${depth * 16 + 6}px` }}
              onClick={() => onSelect(folder.id)}
            >
              {hasChildren ? (
                <button
                  type="button"
                  className="p-0.5 hover:bg-muted rounded"
                  onClick={(e) => { e.stopPropagation(); onToggleExpand(folder.id) }}
                >
                  {isExpanded
                    ? <ChevronDown className="h-3 w-3" />
                    : <ChevronRight className="h-3 w-3" />}
                </button>
              ) : (
                <span className="w-4" />
              )}
              <Folder className="h-3.5 w-3.5 shrink-0" style={{ color: folder.color || undefined }} />
              <span className="truncate">{folder.name}</span>
              {folder.document_count > 0 && (
                <span className="text-[10px] text-muted-foreground ml-auto">{folder.document_count}</span>
              )}
            </div>
            {hasChildren && isExpanded && (
              <FolderTreePicker
                folders={folders}
                parentId={folder.id}
                selectedId={selectedId}
                expandedIds={expandedIds}
                onSelect={onSelect}
                onToggleExpand={onToggleExpand}
                depth={depth + 1}
              />
            )}
          </div>
        )
      })}
    </>
  )
}
