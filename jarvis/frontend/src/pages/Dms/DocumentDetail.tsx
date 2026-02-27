import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, FileText, Paperclip, Download, Trash2, Plus,
  Image as ImageIcon, File, FileSpreadsheet, FolderOpen,
  Edit2, Check, X, Calendar, Bell, ExternalLink,
  Users, PenTool, FileSearch, Loader2, Cloud, Shield, Tags,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { PageHeader } from '@/components/shared/PageHeader'
import { EmptyState } from '@/components/shared/EmptyState'
import { TagPicker } from '@/components/shared/TagPicker'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import { usersApi } from '@/api/users'
import { rolesApi } from '@/api/roles'
import { tagsApi } from '@/api/tags'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import type {
  DmsDocument, DmsFile, DmsRelationshipType, DmsRelationshipTypeConfig,
  DmsParty, DmsPartyRole, DmsEntityType, DmsSignatureStatus, DmsWmlChunk,
  PartySuggestion, DmsSupplier, DmsSupplierType,
} from '@/types/dms'
import UploadDialog from './UploadDialog'
import PartyPicker from './PartyPicker'
import { formatDate, formatSize } from './index'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  archived: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

const SIG_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  sent: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  signed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  declined: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  expired: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

// Party roles loaded dynamically from API

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
  const [editVisibility, setEditVisibility] = useState<'all' | 'restricted'>('all')
  const [editAllowedRoleIds, setEditAllowedRoleIds] = useState<number[]>([])
  const [editAllowedUserIds, setEditAllowedUserIds] = useState<number[]>([])

  // Party state
  const [addingParty, setAddingParty] = useState(false)
  const [partyRole, setPartyRole] = useState<DmsPartyRole>('')
  const [partyEntityType, setPartyEntityType] = useState<DmsEntityType>('company')
  const [partyName, setPartyName] = useState('')
  const [selectedSuggestion, setSelectedSuggestion] = useState<PartySuggestion | null>(null)
  const [deletePartyId, setDeletePartyId] = useState<number | null>(null)
  const [newSupplierOpen, setNewSupplierOpen] = useState(false)
  const [newSupForm, setNewSupForm] = useState({ name: '', supplier_type: 'company' as DmsSupplierType, cui: '', phone: '', email: '', city: '', county: '', address: '', nr_reg_com: '' })

  // Signature state
  const [sigEditing, setSigEditing] = useState(false)
  const [sigStatus, setSigStatus] = useState<string>('')
  const [sigProvider, setSigProvider] = useState<string>('')

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

  const { data: partyRolesData } = useQuery({
    queryKey: ['dms-party-roles'],
    queryFn: () => dmsApi.listPartyRoles(),
    staleTime: 60_000,
  })
  const partyRoleOptions = (partyRolesData?.roles || []).map((r: { slug: string; label: string }) => ({ value: r.slug, label: r.label }))

  // Parties
  const { data: partiesData } = useQuery({
    queryKey: ['dms-parties', docId],
    queryFn: () => dmsApi.listParties(docId),
    enabled: !!docId,
  })

  // Extraction
  const { data: chunksData } = useQuery({
    queryKey: ['dms-chunks', docId],
    queryFn: () => dmsApi.getChunks(docId),
    enabled: !!docId,
  })

  // Drive sync
  const { data: driveSyncData } = useQuery({
    queryKey: ['dms-drive-sync', docId],
    queryFn: () => dmsApi.getDriveSync(docId),
    enabled: !!docId,
  })

  // Roles (for visibility editing)
  const { data: rolesData } = useQuery({
    queryKey: ['roles'],
    queryFn: () => rolesApi.getRoles(),
    enabled: editing,
  })

  // Tags
  const { data: entityTags = [] } = useQuery({
    queryKey: ['entity-tags', 'dms_document', docId],
    queryFn: () => tagsApi.getEntityTags('dms_document', docId),
    enabled: !!docId,
  })

  const doc: DmsDocument | undefined = data?.document
  const files: DmsFile[] = doc?.files || []
  const children: Partial<Record<string, DmsDocument[]>> = doc?.children || {}
  const categories = categoriesData?.categories || []
  const relTypes: DmsRelationshipTypeConfig[] = relTypesData?.types || []
  const parties: DmsParty[] = partiesData?.parties || []
  const chunks: DmsWmlChunk[] = chunksData?.chunks || []

  const addPartyMutation = useMutation({
    mutationFn: (data: { party_role: DmsPartyRole; entity_type: DmsEntityType; entity_name: string; entity_id?: number; entity_details?: Record<string, unknown> }) =>
      dmsApi.createParty(docId, data),
    onSuccess: () => {
      toast.success('Party added')
      queryClient.invalidateQueries({ queryKey: ['dms-parties', docId] })
      setAddingParty(false)
      setPartyName('')
      setSelectedSuggestion(null)
    },
    onError: () => toast.error('Failed to add party'),
  })

  const createSupplierMutation = useMutation({
    mutationFn: (data: Partial<DmsSupplier>) => dmsApi.createSupplier(data),
    onSuccess: (res) => {
      toast.success('Supplier created')
      queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] })
      queryClient.invalidateQueries({ queryKey: ['dms-party-suggest'] })
      setNewSupplierOpen(false)
      // Auto-select the new supplier
      setPartyName(newSupForm.name)
      setPartyEntityType(newSupForm.supplier_type === 'person' ? 'person' : 'company')
      setSelectedSuggestion({
        id: res.id,
        name: newSupForm.name,
        entity_type: newSupForm.supplier_type === 'person' ? 'person' : 'company',
        source: 'supplier',
        cui: newSupForm.cui || null,
        phone: newSupForm.phone || null,
        email: newSupForm.email || null,
      })
      setNewSupForm({ name: '', supplier_type: 'company', cui: '', phone: '', email: '', city: '', county: '', address: '', nr_reg_com: '' })
    },
    onError: () => toast.error('Failed to create supplier'),
  })

  const deletePartyMutation = useMutation({
    mutationFn: (id: number) => dmsApi.deleteParty(id),
    onSuccess: () => {
      toast.success('Party removed')
      queryClient.invalidateQueries({ queryKey: ['dms-parties', docId] })
      setDeletePartyId(null)
    },
    onError: () => toast.error('Failed to remove party'),
  })

  const sigMutation = useMutation({
    mutationFn: (data: { signature_status: DmsSignatureStatus; signature_provider?: string }) =>
      dmsApi.updateSignatureStatus(docId, data),
    onSuccess: () => {
      toast.success('Signature status updated')
      queryClient.invalidateQueries({ queryKey: ['dms-document', docId] })
      setSigEditing(false)
    },
    onError: () => toast.error('Failed to update signature'),
  })

  const extractMutation = useMutation({
    mutationFn: () => dmsApi.extractText(docId),
    onSuccess: (res) => {
      const count = res.extractions?.length || 0
      toast.success(`Text extracted from ${count} file(s)`)
      queryClient.invalidateQueries({ queryKey: ['dms-chunks', docId] })
    },
    onError: () => toast.error('Extraction failed'),
  })

  const driveSyncMutation = useMutation({
    mutationFn: () => dmsApi.syncToDrive(docId),
    onSuccess: (res) => {
      const count = res.uploaded?.length || 0
      toast.success(`${count} file(s) synced to Drive`)
      queryClient.invalidateQueries({ queryKey: ['dms-drive-sync', docId] })
      queryClient.invalidateQueries({ queryKey: ['dms-document', docId] })
    },
    onError: () => toast.error('Drive sync failed'),
  })

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
    setEditVisibility(doc.visibility || 'all')
    setEditAllowedRoleIds(doc.allowed_role_ids || [])
    setEditAllowedUserIds(doc.allowed_user_ids || [])
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
      visibility: editVisibility,
      allowed_role_ids: editVisibility === 'restricted' && editAllowedRoleIds.length ? editAllowedRoleIds : null,
      allowed_user_ids: editVisibility === 'restricted' && editAllowedUserIds.length ? editAllowedUserIds : null,
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
            {doc.visibility === 'restricted' && (
              <Badge variant="outline" className="text-[10px] border-amber-400 text-amber-700 dark:text-amber-400">
                <Shield className="h-3 w-3 mr-0.5" />
                Restricted
              </Badge>
            )}
            {/* Tags */}
            <TagPicker
              entityType="dms_document"
              entityId={docId}
              currentTags={entityTags}
              onTagsChanged={() => queryClient.invalidateQueries({ queryKey: ['entity-tags', 'dms_document', docId] })}
            >
              <button className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs hover:bg-accent/50">
                <Tags className="h-3 w-3" />
                {entityTags.length > 0 ? (
                  entityTags.map((t) => (
                    <span
                      key={t.id}
                      className="inline-flex items-center gap-0.5 rounded px-1 py-0 text-[10px] font-medium"
                      style={{ backgroundColor: (t.color ?? '#6c757d') + '20', color: t.color ?? '#6c757d' }}
                    >
                      {t.name}
                    </span>
                  ))
                ) : (
                  <span className="text-muted-foreground">Tags</span>
                )}
              </button>
            </TagPicker>
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

      {/* Visibility edit */}
      {editing && (
        <div className="space-y-2">
          <Label className="text-xs flex items-center gap-1">
            <Shield className="h-3 w-3" />
            Visibility
          </Label>
          <div className="flex items-start gap-4">
            <Select value={editVisibility} onValueChange={(v) => setEditVisibility(v as 'all' | 'restricted')}>
              <SelectTrigger className="h-8 w-36 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Everyone</SelectItem>
                <SelectItem value="restricted">Restricted</SelectItem>
              </SelectContent>
            </Select>
            {editVisibility === 'restricted' && (
              <div className="flex-1 space-y-2 rounded border p-2">
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Roles</Label>
                  <div className="flex flex-wrap gap-2">
                    {(rolesData || []).map((r) => (
                      <label key={r.id} className="flex items-center gap-1 text-xs cursor-pointer">
                        <Checkbox
                          checked={editAllowedRoleIds.includes(r.id)}
                          onCheckedChange={(checked) =>
                            setEditAllowedRoleIds((prev) =>
                              checked ? [...prev, r.id] : prev.filter((id) => id !== r.id),
                            )
                          }
                        />
                        {r.name}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">Users</Label>
                  <div className="flex flex-wrap gap-2 max-h-24 overflow-y-auto">
                    {(usersData || []).map((u) => (
                      <label key={u.id} className="flex items-center gap-1 text-xs cursor-pointer">
                        <Checkbox
                          checked={editAllowedUserIds.includes(u.id)}
                          onCheckedChange={(checked) =>
                            setEditAllowedUserIds((prev) =>
                              checked ? [...prev, u.id] : prev.filter((id) => id !== u.id),
                            )
                          }
                        />
                        {u.name}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}
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
          {/* Signature status inline */}
          <span className="inline-flex items-center gap-1">
            <PenTool className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">Signature:</span>{' '}
            {sigEditing ? (
              <span className="inline-flex items-center gap-1">
                <Select value={sigStatus} onValueChange={setSigStatus}>
                  <SelectTrigger className="h-6 w-24 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="sent">Sent</SelectItem>
                    <SelectItem value="signed">Signed</SelectItem>
                    <SelectItem value="declined">Declined</SelectItem>
                    <SelectItem value="expired">Expired</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={sigProvider} onValueChange={setSigProvider}>
                  <SelectTrigger className="h-6 w-20 text-xs"><SelectValue placeholder="Provider" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual</SelectItem>
                    <SelectItem value="docusign">DocuSign</SelectItem>
                    <SelectItem value="validsign">ValidSign</SelectItem>
                  </SelectContent>
                </Select>
                <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => {
                  sigMutation.mutate({
                    signature_status: sigStatus === 'none' ? null : sigStatus as DmsSignatureStatus,
                    signature_provider: sigProvider || undefined,
                  })
                }}>
                  <Check className="h-3 w-3" />
                </Button>
                <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => setSigEditing(false)}>
                  <X className="h-3 w-3" />
                </Button>
              </span>
            ) : doc.signature_status ? (
              <Badge
                className={cn('text-[10px] px-1.5 py-0 cursor-pointer', SIG_COLORS[doc.signature_status])}
                onClick={() => {
                  setSigStatus(doc.signature_status || 'none')
                  setSigProvider(doc.signature_provider || 'manual')
                  setSigEditing(true)
                }}
              >
                {doc.signature_status}
              </Badge>
            ) : (
              <Button variant="ghost" size="sm" className="h-5 text-xs px-1" onClick={() => {
                setSigStatus('pending')
                setSigProvider('manual')
                setSigEditing(true)
              }}>
                Set
              </Button>
            )}
          </span>
        </div>
      )}

      {/* Parties */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium flex items-center gap-1.5">
            <Users className="h-4 w-4" />
            Parties ({parties.length})
          </h3>
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setAddingParty(true)}>
            <Plus className="h-3 w-3 mr-1" />
            Add Party
          </Button>
        </div>
        {addingParty && (
          <div className="flex items-end gap-2 mb-2 p-2 rounded border bg-muted/30">
            <div className="space-y-1">
              <Label className="text-xs">Role</Label>
              <Select value={partyRole || partyRoleOptions[0]?.value || ''} onValueChange={(v) => setPartyRole(v as DmsPartyRole)}>
                <SelectTrigger className="h-7 w-28 text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {partyRoleOptions.map((r: { value: string; label: string }) => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 flex-1">
              <Label className="text-xs">Name</Label>
              <PartyPicker
                value={partyName}
                onChange={(name) => { setPartyName(name); setSelectedSuggestion(null) }}
                onSelect={(s) => {
                  setPartyName(s.name)
                  setPartyEntityType(s.entity_type)
                  setSelectedSuggestion(s)
                }}
                onCreateNew={() => {
                  setNewSupForm({ name: partyName, supplier_type: 'company', cui: '', phone: '', email: '', city: '', county: '', address: '', nr_reg_com: '' })
                  setNewSupplierOpen(true)
                }}
              />
            </div>
            <Button size="sm" className="h-7 text-xs" disabled={!partyName.trim() || addPartyMutation.isPending}
              onClick={() => {
                const payload: { party_role: DmsPartyRole; entity_type: DmsEntityType; entity_name: string; entity_id?: number; entity_details?: Record<string, unknown> } = {
                  party_role: partyRole || partyRoleOptions[0]?.value || 'emitent',
                  entity_type: selectedSuggestion?.entity_type || partyEntityType,
                  entity_name: partyName.trim(),
                }
                if (selectedSuggestion?.id) {
                  payload.entity_id = selectedSuggestion.id
                  payload.entity_details = {
                    source: selectedSuggestion.source,
                    cui: selectedSuggestion.cui,
                    phone: selectedSuggestion.phone,
                    email: selectedSuggestion.email,
                  }
                }
                addPartyMutation.mutate(payload)
              }}>
              Add
            </Button>
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => { setAddingParty(false); setPartyName(''); setSelectedSuggestion(null); setPartyEntityType('company'); setPartyRole('') }}>
              Cancel
            </Button>
          </div>
        )}
        {parties.length > 0 && (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Role</TableHead>
                  <TableHead className="text-xs">Name</TableHead>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-xs w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {parties.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="py-1.5">
                      <Badge variant="outline" className="text-[10px]">{p.party_role}</Badge>
                    </TableCell>
                    <TableCell className="py-1.5 text-sm">{p.entity_name}</TableCell>
                    <TableCell className="py-1.5 text-xs text-muted-foreground">{p.entity_type}</TableCell>
                    <TableCell className="py-1.5">
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setDeletePartyId(p.id)}>
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {parties.length === 0 && !addingParty && (
          <p className="text-xs text-muted-foreground py-2">No parties linked yet.</p>
        )}
      </div>

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

      {/* Google Drive Sync */}
      {driveSyncData?.drive_available && files.length > 0 && (
        <div className="flex items-center gap-3 p-2.5 rounded border bg-muted/20">
          <Cloud className="h-4 w-4 text-blue-500 shrink-0" />
          <div className="flex-1 min-w-0">
            {driveSyncData.sync ? (
              <div className="flex items-center gap-2 flex-wrap">
                <Badge className={cn('text-[10px] px-1.5 py-0', {
                  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400': driveSyncData.sync.status === 'synced',
                  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400': driveSyncData.sync.status === 'partial',
                  'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400': driveSyncData.sync.status === 'error',
                })}>
                  {driveSyncData.sync.status}
                </Badge>
                {driveSyncData.sync.folder_url && (
                  <a href={driveSyncData.sync.folder_url} target="_blank" rel="noreferrer"
                    className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1">
                    <ExternalLink className="h-3 w-3" />
                    Open in Drive
                  </a>
                )}
                {driveSyncData.sync.last_synced_at && (
                  <span className="text-[10px] text-muted-foreground">
                    Last: {formatDate(driveSyncData.sync.last_synced_at)}
                  </span>
                )}
                {driveSyncData.sync.error_message && (
                  <span className="text-[10px] text-red-500 truncate max-w-[300px]" title={driveSyncData.sync.error_message}>{driveSyncData.sync.error_message}</span>
                )}
              </div>
            ) : (
              <span className="text-xs text-muted-foreground">Not synced to Google Drive</span>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs shrink-0"
            disabled={driveSyncMutation.isPending || uploadFilesMutation.isPending}
            onClick={() => driveSyncMutation.mutate()}
          >
            {driveSyncMutation.isPending ? (
              <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Syncing...</>
            ) : driveSyncData.sync?.synced ? (
              <><Cloud className="h-3 w-3 mr-1" />Re-sync</>
            ) : (
              <><Cloud className="h-3 w-3 mr-1" />Sync to Drive</>
            )}
          </Button>
        </div>
      )}

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

      {/* Extracted Content */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium flex items-center gap-1.5">
            <FileSearch className="h-4 w-4" />
            Extracted Text ({chunks.length} chunks)
          </h3>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            disabled={extractMutation.isPending || files.length === 0}
            onClick={() => extractMutation.mutate()}
          >
            {extractMutation.isPending ? (
              <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Extracting...</>
            ) : (
              <><FileSearch className="h-3 w-3 mr-1" />Extract Text</>
            )}
          </Button>
        </div>
        {chunks.length > 0 ? (
          <div className="space-y-2 max-h-60 overflow-y-auto rounded border p-2 bg-muted/20">
            {chunks.map((c) => (
              <div key={c.id} className="text-xs border-b pb-1.5 last:border-0">
                {c.heading && (
                  <p className="font-medium text-foreground mb-0.5">{c.heading}</p>
                )}
                <p className="text-muted-foreground whitespace-pre-wrap line-clamp-4">{c.content}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground py-2">
            {files.length === 0
              ? 'Upload files first, then extract text.'
              : 'No text extracted yet. Click "Extract Text" to process files.'}
          </p>
        )}
      </div>

      {/* Delete party confirmation */}
      <ConfirmDialog
        open={deletePartyId !== null}
        onOpenChange={(open) => !open && setDeletePartyId(null)}
        title="Remove Party"
        description="This party will be removed from the document."
        confirmLabel="Remove"
        variant="destructive"
        onConfirm={() => deletePartyId && deletePartyMutation.mutate(deletePartyId)}
      />

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

      {/* New Supplier inline dialog */}
      <Dialog open={newSupplierOpen} onOpenChange={setNewSupplierOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New Supplier</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-[1fr_120px] gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Name *</Label>
                <Input value={newSupForm.name} onChange={(e) => setNewSupForm((p) => ({ ...p, name: e.target.value }))} placeholder="Supplier name" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Type</Label>
                <Select value={newSupForm.supplier_type} onValueChange={(v) => setNewSupForm((p) => ({ ...p, supplier_type: v as DmsSupplierType }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="company">Company</SelectItem>
                    <SelectItem value="person">Person</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">CUI / CIF</Label>
                <Input value={newSupForm.cui} onChange={(e) => setNewSupForm((p) => ({ ...p, cui: e.target.value }))} placeholder="Tax ID" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Nr. Reg. Com.</Label>
                <Input value={newSupForm.nr_reg_com} onChange={(e) => setNewSupForm((p) => ({ ...p, nr_reg_com: e.target.value }))} placeholder="J00/000/0000" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Address</Label>
              <Input value={newSupForm.address} onChange={(e) => setNewSupForm((p) => ({ ...p, address: e.target.value }))} placeholder="Street address" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">City</Label>
                <Input value={newSupForm.city} onChange={(e) => setNewSupForm((p) => ({ ...p, city: e.target.value }))} placeholder="City" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">County</Label>
                <Input value={newSupForm.county} onChange={(e) => setNewSupForm((p) => ({ ...p, county: e.target.value }))} placeholder="County" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Phone</Label>
                <Input value={newSupForm.phone} onChange={(e) => setNewSupForm((p) => ({ ...p, phone: e.target.value }))} placeholder="Phone" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Email</Label>
                <Input value={newSupForm.email} onChange={(e) => setNewSupForm((p) => ({ ...p, email: e.target.value }))} placeholder="Email" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNewSupplierOpen(false)}>Cancel</Button>
            <Button
              disabled={!newSupForm.name.trim() || createSupplierMutation.isPending}
              onClick={() => createSupplierMutation.mutate({
                name: newSupForm.name.trim(),
                supplier_type: newSupForm.supplier_type,
                cui: newSupForm.cui.trim() || undefined,
                nr_reg_com: newSupForm.nr_reg_com.trim() || undefined,
                address: newSupForm.address.trim() || undefined,
                city: newSupForm.city.trim() || undefined,
                county: newSupForm.county.trim() || undefined,
                phone: newSupForm.phone.trim() || undefined,
                email: newSupForm.email.trim() || undefined,
              })}
            >
              Create & Select
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
