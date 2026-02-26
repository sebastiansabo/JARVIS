import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, FileText, Paperclip, Download, Trash2, Plus,
  Image as ImageIcon, File, FileSpreadsheet, FolderOpen,
  Edit2, Check, X, Calendar, Bell,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import { usersApi } from '@/api/users'
import type { DmsDocument, DmsFile, DmsRelationshipType } from '@/types/dms'
import UploadDialog from './UploadDialog'
import { formatDate, formatSize } from './index'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  archived: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

const REL_TYPE_LABELS: Record<string, string> = {
  annex: 'Anexe',
  deviz: 'Devize',
  proof: 'Dovezi / Foto',
  other: 'Altele',
}

const REL_TYPE_ORDER: DmsRelationshipType[] = ['annex', 'deviz', 'proof', 'other']

function expiryColor(daysToExpiry: number | null) {
  if (daysToExpiry == null) return 'text-muted-foreground'
  if (daysToExpiry < 0) return 'text-red-600 dark:text-red-400'
  if (daysToExpiry <= 30) return 'text-amber-600 dark:text-amber-400'
  return 'text-green-600 dark:text-green-400'
}

function fileIcon(mimeType: string | null) {
  if (!mimeType) return <File className="h-5 w-5 text-muted-foreground" />
  if (mimeType.startsWith('image/')) return <ImageIcon className="h-5 w-5 text-blue-500" />
  if (mimeType.includes('spreadsheet') || mimeType.includes('excel'))
    return <FileSpreadsheet className="h-5 w-5 text-green-600" />
  if (mimeType.includes('pdf')) return <FileText className="h-5 w-5 text-red-500" />
  return <File className="h-5 w-5 text-muted-foreground" />
}

export default function DocumentDetail() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const docId = Number(documentId)

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadRelType, setUploadRelType] = useState<DmsRelationshipType | undefined>()
  const [deleteFileId, setDeleteFileId] = useState<number | null>(null)
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

  const doc: DmsDocument | undefined = data?.document
  const files: DmsFile[] = doc?.files || []
  const children: Partial<Record<DmsRelationshipType, DmsDocument[]>> = doc?.children || {}
  const categories = categoriesData?.categories || []

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
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
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
    <div className="space-y-6">
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
          <div className="flex items-center gap-2">
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
          </div>
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

      {/* Description */}
      {editing ? (
        <Textarea
          value={editDesc}
          onChange={(e) => setEditDesc(e.target.value)}
          placeholder="Description..."
          rows={3}
        />
      ) : doc.description ? (
        <p className="text-sm text-muted-foreground">{doc.description}</p>
      ) : null}

      {/* Document Details Card */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Document Details</CardTitle>
        </CardHeader>
        <CardContent>
          {editing ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="edit-doc-number">Document Number</Label>
                <Input
                  id="edit-doc-number"
                  placeholder="e.g. CTR-2025-0001"
                  value={editDocNumber}
                  onChange={(e) => setEditDocNumber(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-doc-date">Document Date</Label>
                <Input
                  id="edit-doc-date"
                  type="date"
                  value={editDocDate}
                  onChange={(e) => setEditDocDate(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-expiry-date">Expiration Date</Label>
                <Input
                  id="edit-expiry-date"
                  type="date"
                  value={editExpiryDate}
                  onChange={(e) => setEditExpiryDate(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Notify Person</Label>
                <Select value={editNotifyUserId || 'none'} onValueChange={(v) => setEditNotifyUserId(v === 'none' ? '' : v)}>
                  <SelectTrigger><SelectValue placeholder="Select user..." /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {(usersData || []).map((u) => (
                      <SelectItem key={u.id} value={u.id.toString()}>
                        {u.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : (
            <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2 text-sm">
              {doc.doc_number && (
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Number:</span>
                  <span className="font-medium">{doc.doc_number}</span>
                </div>
              )}
              {doc.doc_date && (
                <div className="flex items-center gap-2">
                  <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-muted-foreground">Doc Date:</span>
                  <span>{formatDate(doc.doc_date)}</span>
                </div>
              )}
              <div className="flex items-center gap-2">
                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">Expiry:</span>
                {doc.expiry_date ? (
                  <span className={cn('font-medium', expiryColor(doc.days_to_expiry))}>
                    {formatDate(doc.expiry_date)}
                    {doc.days_to_expiry != null && (
                      <span className="ml-1 text-xs font-normal">
                        ({doc.days_to_expiry < 0
                          ? `${Math.abs(doc.days_to_expiry)}d expired`
                          : doc.days_to_expiry === 0
                            ? 'today'
                            : `${doc.days_to_expiry}d left`})
                      </span>
                    )}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Bell className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">Notify:</span>
                <span>{doc.notify_user_name || '—'}</span>
              </div>
              {doc.company_name && (
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Company:</span>
                  <span>{doc.company_name}</span>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Files Section */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Paperclip className="h-4 w-4" />
            Files ({files.length})
          </CardTitle>
          <div className="flex gap-2">
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
            <Button
              variant="outline"
              size="sm"
              onClick={() => document.getElementById('dms-quick-upload')?.click()}
            >
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add Files
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {files.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No files uploaded yet.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {files.map((f) => (
                <div key={f.id} className="flex items-center gap-3 rounded-lg border p-3">
                  {fileIcon(f.mime_type)}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{f.file_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatSize(f.file_size)} &middot; {f.uploaded_by_name}
                    </p>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      asChild
                    >
                      <a href={dmsApi.downloadFileUrl(f.id)} target="_blank" rel="noreferrer">
                        <Download className="h-3.5 w-3.5" />
                      </a>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => setDeleteFileId(f.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Children by Relationship Type */}
      {REL_TYPE_ORDER.map((relType) => {
        const items: DmsDocument[] = children[relType] || []
        return (
          <Card key={relType}>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <CardTitle className="text-base">{REL_TYPE_LABELS[relType]} ({items.length})</CardTitle>
              <Button variant="outline" size="sm" onClick={() => openChildUpload(relType)}>
                <Plus className="h-3.5 w-3.5 mr-1" />
                Add {REL_TYPE_LABELS[relType]?.replace(/\s.*/, '')}
              </Button>
            </CardHeader>
            <CardContent>
              {items.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-3">
                  No {REL_TYPE_LABELS[relType]?.toLowerCase()} added.
                </p>
              ) : (
                <div className="space-y-2">
                  {items.map((child) => (
                    <div
                      key={child.id}
                      className="flex items-center gap-3 rounded-lg border p-3 cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/app/dms/documents/${child.id}`)}
                    >
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">{child.title}</p>
                        {child.description && (
                          <p className="text-xs text-muted-foreground truncate">{child.description}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {(child.file_count ?? 0) > 0 && (
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Paperclip className="h-3 w-3" />
                            {child.file_count}
                          </span>
                        )}
                        <Badge className={cn('text-xs', STATUS_COLORS[child.status])}>{child.status}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
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
    </div>
  )
}
