import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, FileText, Paperclip, Download, Trash2, Plus,
  Image as ImageIcon, File, FileSpreadsheet, FolderOpen,
  Edit2, Check, X, Calendar, Bell, ExternalLink,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import { usersApi } from '@/api/users'
import type { DmsDocument, DmsFile, DmsRelationshipType, DmsRelationshipTypeConfig } from '@/types/dms'
import UploadDialog from './UploadDialog'
import { formatDate, formatSize } from './index'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  archived: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

function expiryColor(daysToExpiry: number | null) {
  if (daysToExpiry == null) return 'text-muted-foreground'
  if (daysToExpiry < 0) return 'text-red-600 dark:text-red-400'
  if (daysToExpiry <= 30) return 'text-amber-600 dark:text-amber-400'
  return 'text-green-600 dark:text-green-400'
}

function fileIcon(mimeType: string | null) {
  if (!mimeType) return <File className="h-4 w-4 text-muted-foreground" />
  if (mimeType.startsWith('image/')) return <ImageIcon className="h-4 w-4 text-blue-500" />
  if (mimeType.includes('spreadsheet') || mimeType.includes('excel'))
    return <FileSpreadsheet className="h-4 w-4 text-green-600" />
  if (mimeType.includes('pdf')) return <FileText className="h-4 w-4 text-red-500" />
  return <File className="h-4 w-4 text-muted-foreground" />
}

export default function DocumentDetail() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const docId = Number(documentId)

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadRelType, setUploadRelType] = useState<DmsRelationshipType | undefined>()
  const [deleteFileId, setDeleteFileId] = useState<number | null>(null)
  const [deleteChildId, setDeleteChildId] = useState<number | null>(null)
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editStatus, setEditStatus] = useState('')
  const [editDocNumber, setEditDocNumber] = useState('')
  const [editDocDate, setEditDocDate] = useState('')
  const [editExpiryDate, setEditExpiryDate] = useState('')
  const [editNotifyUserId, setEditNotifyUserId] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['dms-document', docId],
    queryFn: () => dmsApi.getDocument(docId),
    enabled: !!docId,
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['dms-categories'],
    queryFn: () => dmsApi.listCategories(),
  })

  const { data: usersData } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
  })

  const { data: relTypesData } = useQuery({
    queryKey: ['dms-rel-types'],
    queryFn: () => dmsApi.listRelationshipTypes(),
    staleTime: 60_000,
  })

  const doc: DmsDocument | undefined = data?.document
  const files: DmsFile[] = doc?.files || []
  const children: Partial<Record<string, DmsDocument[]>> = doc?.children || {}
  const categories = categoriesData?.categories || []
  const relTypes: DmsRelationshipTypeConfig[] = relTypesData?.types || []

  const uploadFilesMutation = useMutation({
    mutationFn: ({ files: fileList }: { files: File[] }) => dmsApi.uploadFiles(docId, fileList),
    onSuccess: (res) => {
      const count = res.uploaded?.length || 0
      toast.success(`${count} file(s) uploaded`)
      queryClient.invalidateQueries({ queryKey: ['dms-document', docId] })
    },
    onError: () => toast.error('Upload failed'),
  })

  const deleteFileMutation = useMutation({
    mutationFn: (fid: number) => dmsApi.deleteFile(fid),
    onSuccess: () => {
      toast.success('File deleted')
      queryClient.invalidateQueries({ queryKey: ['dms-document', docId] })
      setDeleteFileId(null)
    },
    onError: () => toast.error('Failed to delete file'),
  })

  const deleteChildMutation = useMutation({
    mutationFn: (childId: number) => dmsApi.deleteDocument(childId),
    onSuccess: () => {
      toast.success('Child document deleted')
      queryClient.invalidateQueries({ queryKey: ['dms-document', docId] })
      queryClient.invalidateQueries({ queryKey: ['dms-documents'] })
      setDeleteChildId(null)
    },
    onError: () => toast.error('Failed to delete document'),
  })

  const updateMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => dmsApi.updateDocument(docId, data),
    onSuccess: () => {
      toast.success('Document updated')
      queryClient.invalidateQueries({ queryKey: ['dms-document', docId] })
      queryClient.invalidateQueries({ queryKey: ['dms-documents'] })
      setEditing(false)
    },
    onError: () => toast.error('Update failed'),
  })

  const startEdit = () => {
    if (!doc) return
    setEditTitle(doc.title)
    setEditDesc(doc.description || '')
    setEditStatus(doc.status)
    setEditDocNumber(doc.doc_number || '')
    setEditDocDate(doc.doc_date || '')
    setEditExpiryDate(doc.expiry_date || '')
    setEditNotifyUserId(doc.notify_user_id?.toString() || '')
    setEditing(true)
  }

  const saveEdit = () => {
    updateMutation.mutate({
      title: editTitle.trim(),
      description: editDesc.trim() || null,
      status: editStatus,
      doc_number: editDocNumber.trim() || null,
      doc_date: editDocDate || null,
      expiry_date: editExpiryDate || null,
      notify_user_id: editNotifyUserId ? Number(editNotifyUserId) : null,
    })
  }

  const openChildUpload = (relType: DmsRelationshipType) => {
    setUploadRelType(relType)
    setUploadOpen(true)
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-48" />
      </div>
    )
  }

  if (!doc) {
    return (
      <EmptyState
        icon={<FolderOpen className="h-12 w-12" />}
        title="Document not found"
        action={<Button onClick={() => navigate('/app/dms')}>Back to Documents</Button>}
      />
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <PageHeader
        title={
          editing ? (
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="text-lg font-semibold h-9 w-80"
            />
          ) : (
            doc.title
          )
        }
        description={
          <span className="inline-flex items-center gap-2 flex-wrap">
            {doc.category_name && (
              <Badge
                variant="outline"
                style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}
              >
                {doc.category_name}
              </Badge>
            )}
            {editing ? (
              <Select value={editStatus} onValueChange={setEditStatus}>
                <SelectTrigger className="h-7 w-28"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="archived">Archived</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <Badge className={cn('text-xs', STATUS_COLORS[doc.status])}>{doc.status}</Badge>
            )}
            <span className="text-sm text-muted-foreground">by {doc.created_by_name}</span>
            <span className="text-sm text-muted-foreground">{formatDate(doc.created_at)}</span>
          </span>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => navigate('/app/dms')}>
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back
            </Button>
            {editing ? (
              <>
                <Button size="sm" onClick={saveEdit} disabled={updateMutation.isPending}>
                  <Check className="h-4 w-4 mr-1" />
                  Save
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  <X className="h-4 w-4 mr-1" />
                  Cancel
                </Button>
              </>
            ) : (
              <Button variant="outline" size="sm" onClick={startEdit}>
                <Edit2 className="h-4 w-4 mr-1" />
                Edit
              </Button>
            )}
          </div>
        }
      />

      {/* Description (edit mode) */}
      {editing && (
        <Textarea
          value={editDesc}
          onChange={(e) => setEditDesc(e.target.value)}
          placeholder="Description..."
          rows={2}
        />
      )}

      {/* Edit fields (compact grid) */}
      {editing && (
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
          <div className="space-y-1">
            <Label htmlFor="edit-doc-number" className="text-xs">Doc Number</Label>
            <Input id="edit-doc-number" placeholder="CTR-2025-0001" value={editDocNumber} onChange={(e) => setEditDocNumber(e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="edit-doc-date" className="text-xs">Doc Date</Label>
            <Input id="edit-doc-date" type="date" value={editDocDate} onChange={(e) => setEditDocDate(e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="edit-expiry-date" className="text-xs">Expiry Date</Label>
            <Input id="edit-expiry-date" type="date" value={editExpiryDate} onChange={(e) => setEditExpiryDate(e.target.value)} className="h-8 text-sm" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Notify</Label>
            <Select value={editNotifyUserId || 'none'} onValueChange={(v) => setEditNotifyUserId(v === 'none' ? '' : v)}>
              <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Select..." /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {(usersData || []).map((u) => (
                  <SelectItem key={u.id} value={u.id.toString()}>{u.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {/* Document details (view mode) — compact inline */}
      {!editing && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm border-b pb-3">
          {doc.description && (
            <span className="text-muted-foreground basis-full mb-1">{doc.description}</span>
          )}
          {doc.doc_number && (
            <span><span className="text-muted-foreground">Nr:</span> <span className="font-medium">{doc.doc_number}</span></span>
          )}
          {doc.doc_date && (
            <span className="inline-flex items-center gap-1">
              <Calendar className="h-3 w-3 text-muted-foreground" />
              <span className="text-muted-foreground">Doc:</span> {formatDate(doc.doc_date)}
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <Calendar className="h-3 w-3 text-muted-foreground" />
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
          </span>
          <span className="inline-flex items-center gap-1">
            <Bell className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">Notify:</span> {doc.notify_user_name || '—'}
          </span>
          {doc.company_name && (
            <span><span className="text-muted-foreground">Company:</span> {doc.company_name}</span>
          )}
        </div>
      )}

      {/* Files table */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium flex items-center gap-1.5">
            <Paperclip className="h-4 w-4" />
            Files ({files.length})
          </h3>
          <div>
            <input
              type="file"
              multiple
              id="dms-quick-upload"
              className="hidden"
              accept=".pdf,.docx,.xlsx,.jpg,.jpeg,.png,.tiff,.tif,.gif"
              onChange={(e) => {
                if (e.target.files?.length) {
                  uploadFilesMutation.mutate({ files: Array.from(e.target.files) })
                  e.target.value = ''
                }
              }}
            />
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => document.getElementById('dms-quick-upload')?.click()}>
              <Plus className="h-3 w-3 mr-1" />
              Add Files
            </Button>
          </div>
        </div>
        {files.length === 0 ? (
          <p className="text-xs text-muted-foreground py-3">No files uploaded yet.</p>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">File</TableHead>
                  <TableHead className="text-xs hidden sm:table-cell">Type</TableHead>
                  <TableHead className="text-xs text-right">Size</TableHead>
                  <TableHead className="text-xs hidden sm:table-cell">Uploaded By</TableHead>
                  <TableHead className="text-xs hidden md:table-cell">Date</TableHead>
                  <TableHead className="text-xs w-20">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {files.map((f) => (
                  <TableRow key={f.id}>
                    <TableCell className="py-2">
                      <div className="flex items-center gap-2">
                        {fileIcon(f.mime_type)}
                        <span className="text-sm truncate max-w-[240px]">{f.file_name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground py-2 hidden sm:table-cell">{f.file_type || '—'}</TableCell>
                    <TableCell className="text-xs py-2 text-right">{formatSize(f.file_size)}</TableCell>
                    <TableCell className="text-xs text-muted-foreground py-2 hidden sm:table-cell">{f.uploaded_by_name || '—'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground py-2 hidden md:table-cell">{formatDate(f.created_at)}</TableCell>
                    <TableCell className="py-2">
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-6 w-6" asChild>
                          <a href={dmsApi.downloadFileUrl(f.id)} target="_blank" rel="noreferrer">
                            <Download className="h-3.5 w-3.5" />
                          </a>
                        </Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setDeleteFileId(f.id)}>
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Children by Relationship Type — tables with row actions */}
      {relTypes.map((rt) => {
        const items: DmsDocument[] = children[rt.slug] || []
        return (
          <div key={rt.slug}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium">{rt.label} ({items.length})</h3>
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => openChildUpload(rt.slug)}>
                <Plus className="h-3 w-3 mr-1" />
                Add
              </Button>
            </div>
            {items.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">No {rt.label.toLowerCase()} added.</p>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Title</TableHead>
                      <TableHead className="text-xs hidden sm:table-cell">Number</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs text-center">Files</TableHead>
                      <TableHead className="text-xs hidden sm:table-cell">Date</TableHead>
                      <TableHead className="text-xs w-20">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((child) => (
                      <TableRow key={child.id} className="cursor-pointer hover:bg-muted/50" onClick={() => navigate(`/app/dms/documents/${child.id}`)}>
                        <TableCell className="py-2">
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                            <span className="text-sm font-medium">{child.title}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground py-2 hidden sm:table-cell">{child.doc_number || '—'}</TableCell>
                        <TableCell className="py-2">
                          <Badge className={cn('text-[10px] px-1.5 py-0', STATUS_COLORS[child.status])}>{child.status}</Badge>
                        </TableCell>
                        <TableCell className="text-xs py-2 text-center">
                          {(child.file_count ?? 0) > 0 ? (
                            <span className="inline-flex items-center gap-1">
                              <Paperclip className="h-3 w-3" />
                              {child.file_count}
                            </span>
                          ) : '—'}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground py-2 hidden sm:table-cell">{formatDate(child.created_at)}</TableCell>
                        <TableCell className="py-2" onClick={(e) => e.stopPropagation()}>
                          <div className="flex gap-1">
                            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => navigate(`/app/dms/documents/${child.id}`)}>
                              <ExternalLink className="h-3.5 w-3.5" />
                            </Button>
                            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setDeleteChildId(child.id)}>
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        )
      })}

      {/* Upload child dialog */}
      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        companyId={doc.company_id}
        categories={categories}
        parentId={docId}
        defaultRelType={uploadRelType}
      />

      {/* Delete file confirmation */}
      <ConfirmDialog
        open={deleteFileId !== null}
        onOpenChange={(open) => !open && setDeleteFileId(null)}
        title="Delete File"
        description="This file will be permanently deleted."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => deleteFileId && deleteFileMutation.mutate(deleteFileId)}
      />

      {/* Delete child confirmation */}
      <ConfirmDialog
        open={deleteChildId !== null}
        onOpenChange={(open) => !open && setDeleteChildId(null)}
        title="Delete Document"
        description="This will move the child document to trash."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => deleteChildId && deleteChildMutation.mutate(deleteChildId)}
      />
    </div>
  )
}
