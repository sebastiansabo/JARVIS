import { Fragment, useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FolderOpen, FileText, Plus, Search, Trash2, RotateCcw,
  Paperclip, Users as ChildrenIcon, ChevronRight,
  Download, Calendar, Bell, Edit2, File, FileSpreadsheet,
  Image as ImageIcon, PenTool, Tags, Shield, X,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/useAuth'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { TagPicker } from '@/components/shared/TagPicker'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { ColumnToggle, type ColumnDef } from '@/components/shared/ColumnToggle'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import { tagsApi } from '@/api/tags'
import { useDmsStore } from '@/stores/dmsStore'
import type { DmsDocument, DmsFile, DmsCategory, DmsRelationshipTypeConfig } from '@/types/dms'
import UploadDialog from './UploadDialog'
const STATUS_COLORS: Record<string, string> = {
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

export { formatDate, formatSize }

const ALL_COLUMN_KEYS = [
  'title', 'category_name', 'file_count', 'children_count', 'status',
  'expiry_date', 'doc_number', 'doc_date', 'company_name', 'created_by_name', 'created_at',
]

const DEFAULT_COLUMNS = [
  'title', 'category_name', 'file_count', 'children_count', 'status',
  'expiry_date', 'created_by_name', 'created_at',
]

const LOCKED_COLUMNS = new Set(['title'])

export default function Dms() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const { filters, updateFilter, clearFilters, selectedIds, toggleSelected, selectAll, clearSelected, visibleColumns, setVisibleColumns } = useDmsStore()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => {
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(debounceRef.current)
  }, [search])
  const [uploadOpen, setUploadOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  const companyId = filters.company_id || user?.company_id || undefined

  // Queries
  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ['dms-stats', companyId],
    queryFn: () => dmsApi.getStats(companyId),
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['dms-categories', companyId],
    queryFn: () => dmsApi.listCategories(companyId),
  })

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ['dms-documents', { ...filters, search: debouncedSearch, company_id: companyId }],
    queryFn: () => dmsApi.listDocuments({ ...filters, search: debouncedSearch, company_id: companyId }),
  })

  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)
  const [batchCategoryOpen, setBatchCategoryOpen] = useState(false)
  const [batchStatusOpen, setBatchStatusOpen] = useState(false)
  const [, setBatchCategoryId] = useState<number | null>(null)
  const [, setBatchStatusValue] = useState<string | null>(null)

  const deleteMutation = useMutation({
    mutationFn: (id: number) => dmsApi.deleteDocument(id),
    onSuccess: () => {
      toast.success('Document deleted')
      queryClient.invalidateQueries({ queryKey: ['dms-documents'] })
      queryClient.invalidateQueries({ queryKey: ['dms-stats'] })
      setDeleteId(null)
    },
    onError: () => toast.error('Failed to delete document'),
  })

  const batchDeleteMutation = useMutation({
    mutationFn: (ids: number[]) => dmsApi.batchDelete(ids),
    onSuccess: (res) => {
      toast.success(`${res.affected} document(s) deleted`)
      queryClient.invalidateQueries({ queryKey: ['dms-documents'] })
      queryClient.invalidateQueries({ queryKey: ['dms-stats'] })
      clearSelected()
      setBatchDeleteOpen(false)
    },
    onError: () => toast.error('Batch delete failed'),
  })

  const batchCategoryMutation = useMutation({
    mutationFn: ({ ids, categoryId }: { ids: number[]; categoryId: number }) => dmsApi.batchCategory(ids, categoryId),
    onSuccess: (res) => {
      toast.success(`${res.affected} document(s) updated`)
      queryClient.invalidateQueries({ queryKey: ['dms-documents'] })
      clearSelected()
      setBatchCategoryOpen(false)
      setBatchCategoryId(null)
    },
    onError: () => toast.error('Batch category update failed'),
  })

  const batchStatusMutation = useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: string }) => dmsApi.batchStatus(ids, status),
    onSuccess: (res) => {
      toast.success(`${res.affected} document(s) updated`)
      queryClient.invalidateQueries({ queryKey: ['dms-documents'] })
      queryClient.invalidateQueries({ queryKey: ['dms-stats'] })
      clearSelected()
      setBatchStatusOpen(false)
      setBatchStatusValue(null)
    },
    onError: () => toast.error('Batch status update failed'),
  })

  // Tags for batch tagging
  const { data: allTags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => tagsApi.getTags(),
    staleTime: 60_000,
  })

  const categories: DmsCategory[] = categoriesData?.categories || []
  const documents: DmsDocument[] = docsData?.documents || []
  const total = docsData?.total || 0
  const stats = statsData?.by_status

  // Bulk entity tags for visible documents
  const docIds = useMemo(() => documents.map((d) => d.id), [documents])
  const { data: entityTagsMap = {} } = useQuery({
    queryKey: ['entity-tags', 'dms_document', docIds],
    queryFn: () => tagsApi.getEntityTagsBulk('dms_document', docIds),
    enabled: docIds.length > 0,
  })

  // Column definitions for dynamic table
  const columnDefs: ColumnDef<DmsDocument>[] = useMemo(() => [
    {
      key: 'title', label: 'Title',
      render: (doc: DmsDocument) => (
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="font-medium">{doc.title}</span>
          {doc.visibility === 'restricted' && (
            <span title="Restricted visibility"><Shield className="h-3 w-3 text-amber-500 shrink-0" /></span>
          )}
          {(entityTagsMap[String(doc.id)] || []).map((t) => (
            <span
              key={t.id}
              className="inline-block rounded px-1 py-0 text-[10px] font-medium whitespace-nowrap"
              style={{ backgroundColor: (t.color ?? '#6c757d') + '20', color: t.color ?? '#6c757d' }}
            >
              {t.name}
            </span>
          ))}
        </div>
      ),
    },
    {
      key: 'category_name', label: 'Category',
      render: (doc: DmsDocument) => doc.category_name ? (
        <Badge variant="outline" style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}>
          {doc.category_name}
        </Badge>
      ) : <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'file_count', label: 'Files', className: 'text-center',
      render: (doc: DmsDocument) => (doc.file_count ?? 0) > 0 ? (
        <span className="inline-flex items-center gap-1 text-sm"><Paperclip className="h-3.5 w-3.5" />{doc.file_count}</span>
      ) : <span>—</span>,
    },
    {
      key: 'children_count', label: 'Annexes', className: 'text-center',
      render: (doc: DmsDocument) => (doc.children_count ?? 0) > 0 ? (
        <span className="inline-flex items-center gap-1 text-sm"><ChildrenIcon className="h-3.5 w-3.5" />{doc.children_count}</span>
      ) : <span>—</span>,
    },
    {
      key: 'status', label: 'Status',
      render: (doc: DmsDocument) => <Badge className={cn('text-xs', STATUS_COLORS[doc.status])}>{doc.status}</Badge>,
    },
    {
      key: 'expiry_date', label: 'Expiry',
      render: (doc: DmsDocument) => doc.expiry_date ? (
        <span className={cn('text-sm font-medium', expiryColor(doc.days_to_expiry))}>
          {formatDate(doc.expiry_date)}
          {doc.days_to_expiry != null && (
            <span className="block text-xs font-normal">
              {doc.days_to_expiry < 0 ? `${Math.abs(doc.days_to_expiry)}d expired` : doc.days_to_expiry === 0 ? 'Expires today' : `${doc.days_to_expiry}d left`}
            </span>
          )}
        </span>
      ) : <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'doc_number', label: 'Number',
      render: (doc: DmsDocument) => <span className="text-sm text-muted-foreground">{doc.doc_number || '—'}</span>,
    },
    {
      key: 'doc_date', label: 'Doc Date',
      render: (doc: DmsDocument) => <span className="text-sm text-muted-foreground">{formatDate(doc.doc_date)}</span>,
    },
    {
      key: 'company_name', label: 'Company',
      render: (doc: DmsDocument) => <span className="text-sm text-muted-foreground">{doc.company_name || '—'}</span>,
    },
    {
      key: 'created_by_name', label: 'Created By',
      render: (doc: DmsDocument) => <span className="text-sm text-muted-foreground">{doc.created_by_name || '—'}</span>,
    },
    {
      key: 'created_at', label: 'Date',
      render: (doc: DmsDocument) => <span className="text-sm text-muted-foreground">{formatDate(doc.created_at)}</span>,
    },
  ], [entityTagsMap])

  const safeVisibleColumns = visibleColumns.length > 0 ? visibleColumns.filter((k) => ALL_COLUMN_KEYS.includes(k)) : DEFAULT_COLUMNS
  const activeColumnDefs = safeVisibleColumns.map((key) => columnDefs.find((c) => c.key === key)).filter(Boolean) as ColumnDef<DmsDocument>[]
  const colSpanTotal = activeColumnDefs.length + 3 // checkbox + chevron + actions

  const allSelected = documents.length > 0 && documents.every((d) => selectedIds.includes(d.id))

  // Mobile card fields for responsive table→card view
  const mobileFields: MobileCardField<DmsDocument>[] = useMemo(() => [
    {
      key: 'title', label: 'Title', isPrimary: true,
      render: (doc) => (
        <span className="flex items-center gap-1.5">
          <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          {doc.title}
          {doc.visibility === 'restricted' && <Shield className="h-3 w-3 text-amber-500 shrink-0" />}
        </span>
      ),
    },
    {
      key: 'category_status', label: 'Category & Status', isSecondary: true,
      render: (doc) => (
        <span className="flex items-center gap-2">
          {doc.category_name && (
            <Badge variant="outline" className="text-[10px] px-1 py-0" style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}>
              {doc.category_name}
            </Badge>
          )}
          <Badge className={cn('text-[10px] px-1 py-0', STATUS_COLORS[doc.status])}>{doc.status}</Badge>
        </span>
      ),
    },
    {
      key: 'expiry_date', label: 'Expiry',
      render: (doc) => doc.expiry_date ? (
        <span className={cn('text-xs font-medium', expiryColor(doc.days_to_expiry))}>
          {formatDate(doc.expiry_date)}
          {doc.days_to_expiry != null && (
            <span className="ml-1 text-[10px]">
              ({doc.days_to_expiry < 0 ? `${Math.abs(doc.days_to_expiry)}d ago` : `${doc.days_to_expiry}d`})
            </span>
          )}
        </span>
      ) : <span className="text-muted-foreground">—</span>,
    },
    {
      key: 'files', label: 'Files',
      render: (doc) => <span className="text-xs">{doc.file_count ?? 0} files, {doc.children_count ?? 0} annexes</span>,
    },
    {
      key: 'created_at', label: 'Created', expandOnly: true,
      render: (doc) => <span className="text-xs">{formatDate(doc.created_at)}</span>,
    },
    {
      key: 'created_by', label: 'By', expandOnly: true,
      render: (doc) => <span className="text-xs">{doc.created_by_name || '—'}</span>,
    },
    {
      key: 'company', label: 'Company', expandOnly: true,
      render: (doc) => <span className="text-xs">{doc.company_name || '—'}</span>,
    },
  ], [entityTagsMap])

  const handleBatchTag = (tagId: number, action: 'add' | 'remove') => {
    tagsApi.bulkEntityTags('dms_document', selectedIds, tagId, action).then((res) => {
      toast.success(`${action === 'add' ? 'Added' : 'Removed'} tag on ${res.count} document(s)`)
      queryClient.invalidateQueries({ queryKey: ['entity-tags'] })
      clearSelected()
    }).catch(() => toast.error('Tag operation failed'))
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documents"
        breadcrumbs={[{ label: 'Documents' }]}
        actions={
          <div className="flex items-center gap-2">
            <Button size="icon" className="md:size-auto md:px-4" onClick={() => setUploadOpen(true)}>
              <Plus className="h-4 w-4 md:mr-2" />
              <span className="hidden md:inline">Upload Document</span>
            </Button>
          </div>
        }
      />

      {/* Stats — compact gap */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatCard title="Total" value={stats?.total ?? 0} isLoading={statsLoading} />
            <StatCard title="Draft" value={stats?.draft ?? 0} isLoading={statsLoading} />
            <StatCard title="Active" value={stats?.active ?? 0} isLoading={statsLoading} />
            <StatCard title="Archived" value={stats?.archived ?? 0} isLoading={statsLoading} />
          </div>

          {/* Filters + Column Toggle */}
          <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-center md:gap-3">
            <div className="relative w-full md:flex-1 md:min-w-[200px] md:max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search documents..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>

            <div className="flex items-center gap-2 md:ml-auto md:gap-3">
              <Select
                value={filters.category_id?.toString() || 'all'}
                onValueChange={(v) => updateFilter('category_id', v === 'all' ? undefined : Number(v))}
              >
                <SelectTrigger className="w-full md:w-[180px]">
                  <SelectValue placeholder="Category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={c.id.toString()}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select
                value={filters.status || 'all'}
                onValueChange={(v) => updateFilter('status', v === 'all' ? undefined : v)}
              >
                <SelectTrigger className="w-full md:w-[140px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="archived">Archived</SelectItem>
                </SelectContent>
              </Select>

              {(filters.category_id || filters.status || search) && (
                <Button variant="ghost" size="sm" onClick={() => { clearFilters(); setSearch(''); setDebouncedSearch('') }}>
                  <RotateCcw className="h-3.5 w-3.5 mr-1" />
                  Clear
                </Button>
              )}

              {!isMobile && (
                <ColumnToggle
                  visibleColumns={safeVisibleColumns}
                  defaultColumns={DEFAULT_COLUMNS}
                  columnDefs={columnDefs as ColumnDef<never>[]}
                  lockedColumns={LOCKED_COLUMNS}
                  onChange={setVisibleColumns}
                />
              )}
            </div>
          </div>

          {/* Batch Action Bar */}
          {selectedIds.length > 0 && (
            <div className={cn(
              'flex items-center gap-2 rounded-md border bg-muted/50 px-3 py-2',
              isMobile && 'fixed inset-x-0 bottom-14 z-40 mx-2 rounded-lg border bg-background shadow-lg',
            )}>
              <span className="text-sm font-medium">{selectedIds.length} selected</span>
              <div className="h-4 w-px bg-border" />

              {/* Batch Category */}
              <Popover open={batchCategoryOpen} onOpenChange={setBatchCategoryOpen}>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="sm">Category</Button>
                </PopoverTrigger>
                <PopoverContent className="w-48 p-2" align="start">
                  <p className="text-xs font-medium text-muted-foreground mb-1">Set category</p>
                  {categories.map((c) => (
                    <button
                      key={c.id}
                      className="w-full text-left text-sm px-2 py-1 rounded hover:bg-accent"
                      onClick={() => { setBatchCategoryId(c.id); batchCategoryMutation.mutate({ ids: selectedIds, categoryId: c.id }) }}
                    >
                      {c.name}
                    </button>
                  ))}
                </PopoverContent>
              </Popover>

              {!isMobile && (
                <>
                  {/* Batch Status */}
                  <Popover open={batchStatusOpen} onOpenChange={setBatchStatusOpen}>
                    <PopoverTrigger asChild>
                      <Button variant="outline" size="sm">Status</Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-36 p-2" align="start">
                      <p className="text-xs font-medium text-muted-foreground mb-1">Set status</p>
                      {['draft', 'active', 'archived'].map((s) => (
                        <button
                          key={s}
                          className="w-full text-left text-sm px-2 py-1 rounded hover:bg-accent capitalize"
                          onClick={() => { setBatchStatusValue(s); batchStatusMutation.mutate({ ids: selectedIds, status: s }) }}
                        >
                          {s}
                        </button>
                      ))}
                    </PopoverContent>
                  </Popover>

                  {/* Batch Tag */}
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button variant="outline" size="sm"><Tags className="h-3.5 w-3.5 mr-1" />Tag</Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-48 p-2" align="start">
                      <p className="text-xs font-medium text-muted-foreground mb-1">Add tag</p>
                      {allTags.map((t) => (
                        <button
                          key={t.id}
                          className="w-full text-left text-sm px-2 py-1 rounded hover:bg-accent flex items-center gap-1.5"
                          onClick={() => handleBatchTag(t.id, 'add')}
                        >
                          <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: t.color || '#6c757d' }} />
                          {t.name}
                        </button>
                      ))}
                      {allTags.length === 0 && <p className="text-xs text-muted-foreground">No tags available</p>}
                    </PopoverContent>
                  </Popover>
                </>
              )}

              <Button variant="destructive" size="sm" onClick={() => setBatchDeleteOpen(true)}>
                <Trash2 className="h-3.5 w-3.5 mr-1" />{!isMobile && 'Delete'}
              </Button>

              <Button variant="ghost" size="sm" onClick={clearSelected}>
                <X className="h-3.5 w-3.5 mr-1" />{!isMobile && 'Clear'}
              </Button>
            </div>
          )}

          {/* Table / Card List */}
          {docsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : documents.length === 0 ? (
            <EmptyState
              icon={<FolderOpen className="h-12 w-12" />}
              title="No documents yet"
              description="Upload your first document to get started."
              action={
                <Button onClick={() => setUploadOpen(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Upload Document
                </Button>
              }
            />
          ) : isMobile ? (
            <>
              <MobileCardList
                data={documents}
                fields={mobileFields}
                getRowId={(doc) => doc.id}
                onRowClick={(doc) => navigate(`/app/dms/documents/${doc.id}`)}
                selectable
                selectedIds={selectedIds}
                onToggleSelect={toggleSelected}
                actions={(doc) => (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 text-destructive"
                    onClick={() => setDeleteId(doc.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-1" />Delete
                  </Button>
                )}
              />
              <div className="text-sm text-muted-foreground">
                Showing {documents.length} of {total} documents
              </div>
            </>
          ) : (
            <>
              <div className="rounded-md border overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8 px-2">
                        <Checkbox
                          checked={allSelected}
                          onCheckedChange={() => allSelected ? clearSelected() : selectAll(docIds)}
                        />
                      </TableHead>
                      <TableHead className="w-8 px-2" />
                      {activeColumnDefs.map((col) => (
                        <TableHead key={col.key} className={col.className}>{col.label}</TableHead>
                      ))}
                      <TableHead className="w-[60px]" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.map((doc) => (
                      <Fragment key={doc.id}>
                        <TableRow
                          className={cn(
                            'cursor-pointer hover:bg-muted/50',
                            selectedIds.includes(doc.id) && 'bg-primary/5',
                          )}
                          onClick={() => setExpandedRow(expandedRow === doc.id ? null : doc.id)}
                        >
                          <TableCell className="px-2" onClick={(e) => e.stopPropagation()}>
                            <Checkbox
                              checked={selectedIds.includes(doc.id)}
                              onCheckedChange={() => toggleSelected(doc.id)}
                            />
                          </TableCell>
                          <TableCell className="px-2">
                            <ChevronRight className={cn('h-4 w-4 transition-transform', expandedRow === doc.id ? 'rotate-90' : '')} />
                          </TableCell>
                          {activeColumnDefs.map((col) => (
                            <TableCell key={col.key} className={col.className}>
                              {col.render(doc)}
                            </TableCell>
                          ))}
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              onClick={(e) => { e.stopPropagation(); setDeleteId(doc.id) }}
                            >
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                            </Button>
                          </TableCell>
                        </TableRow>
                        {expandedRow === doc.id && (
                          <TableRow>
                            <TableCell colSpan={colSpanTotal} className="bg-muted/30 p-4">
                              <DocumentExpandedDetails
                                doc={doc}
                                tags={entityTagsMap[String(doc.id)] || []}
                                onViewDetail={() => navigate(`/app/dms/documents/${doc.id}`)}
                                onDelete={() => setDeleteId(doc.id)}
                                onTagsChanged={() => queryClient.invalidateQueries({ queryKey: ['entity-tags'] })}
                                navigate={navigate}
                              />
                            </TableCell>
                          </TableRow>
                        )}
                      </Fragment>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination info */}
              <div className="text-sm text-muted-foreground">
                Showing {documents.length} of {total} documents
              </div>
            </>
          )}

      {/* Upload Dialog */}
      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        companyId={companyId}
        categories={categories}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(open) => !open && setDeleteId(null)}
        title="Delete Document"
        description="This will move the document to trash. You can restore it later."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
      />

      {/* Batch Delete Confirmation */}
      <ConfirmDialog
        open={batchDeleteOpen}
        onOpenChange={(open) => !open && setBatchDeleteOpen(false)}
        title="Delete Selected Documents"
        description={`This will move ${selectedIds.length} document(s) to trash. You can restore them later.`}
        confirmLabel="Delete All"
        variant="destructive"
        onConfirm={() => batchDeleteMutation.mutate(selectedIds)}
      />
    </div>
  )
}

function fileIcon(mimeType: string | null) {
  if (!mimeType) return <File className="h-4 w-4 text-muted-foreground" />
  if (mimeType.startsWith('image/')) return <ImageIcon className="h-4 w-4 text-blue-500" />
  if (mimeType.includes('spreadsheet') || mimeType.includes('excel'))
    return <FileSpreadsheet className="h-4 w-4 text-green-600" />
  if (mimeType.includes('pdf')) return <FileText className="h-4 w-4 text-red-500" />
  return <File className="h-4 w-4 text-muted-foreground" />
}

function ChildDocRow({ child, navigate, onDelete }: {
  child: DmsDocument
  navigate: (path: string) => void
  onDelete: () => void
}) {
  const queryClient = useQueryClient()
  const { data: childTags = [] } = useQuery({
    queryKey: ['entity-tags', 'dms_document', child.id],
    queryFn: () => tagsApi.getEntityTags('dms_document', child.id),
  })

  return (
    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={() => navigate(`/app/dms/documents/${child.id}`)}>
      <TableCell className="py-1.5">
        <span className="text-xs font-medium">{child.title}</span>
      </TableCell>
      <TableCell className="text-xs py-1.5 text-muted-foreground">{child.doc_number || '—'}</TableCell>
      <TableCell className="py-1.5">
        <Badge className={cn('text-[10px] px-1.5 py-0', STATUS_COLORS[child.status])}>
          {child.status}
        </Badge>
      </TableCell>
      <TableCell className="py-1.5" onClick={(e) => e.stopPropagation()}>
        <TagPicker
          entityType="dms_document"
          entityId={child.id}
          currentTags={childTags}
          onTagsChanged={() => queryClient.invalidateQueries({ queryKey: ['entity-tags', 'dms_document', child.id] })}
        >
          <button className="inline-flex items-center gap-0.5 rounded-md border px-1.5 py-0.5 text-xs hover:bg-accent/50">
            <Tags className="h-3 w-3" />
            {childTags.length > 0 ? (
              childTags.map((t) => (
                <span
                  key={t.id}
                  className="inline-flex rounded px-1 py-0 text-[10px] font-medium"
                  style={{ backgroundColor: (t.color ?? '#6c757d') + '20', color: t.color ?? '#6c757d' }}
                >
                  {t.name}
                </span>
              ))
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </button>
        </TagPicker>
      </TableCell>
      <TableCell className="text-xs py-1.5 text-center">{child.file_count ?? 0}</TableCell>
      <TableCell className="text-xs py-1.5 text-muted-foreground">{formatDate(child.created_at)}</TableCell>
      <TableCell className="py-1.5" onClick={(e) => e.stopPropagation()}>
        <div className="flex gap-1 justify-end">
          <Button variant="ghost" size="icon" className="h-7 w-7" title="View" onClick={() => navigate(`/app/dms/documents/${child.id}`)}>
            <FileText className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" title="Edit" onClick={() => navigate(`/app/dms/documents/${child.id}?edit=1`)}>
            <Edit2 className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:text-destructive" title="Delete" onClick={onDelete}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

function DocumentExpandedDetails({
  doc,
  tags,
  onViewDetail,
  onDelete,
  onTagsChanged,
  navigate,
}: {
  doc: DmsDocument
  tags: import('@/types/tags').EntityTag[]
  onViewDetail: () => void
  onDelete: () => void
  onTagsChanged: () => void
  navigate: (path: string) => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['dms-document', doc.id],
    queryFn: () => dmsApi.getDocument(doc.id),
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
        {doc.notify_user_name && (
          <div className="flex items-center gap-1">
            <Bell className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Notify:</span> {doc.notify_user_name}
          </div>
        )}
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
                        {fileIcon(f.mime_type)}
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
                      <TableHead className="text-xs py-1.5">Tags</TableHead>
                      <TableHead className="text-xs py-1.5 text-center">Files</TableHead>
                      <TableHead className="text-xs py-1.5">Date</TableHead>
                      <TableHead className="text-xs py-1.5 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {children[rt.slug]!.map((child) => (
                      <ChildDocRow key={child.id} child={child} navigate={navigate} onDelete={onDelete} />
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Actions for parent doc */}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); onViewDetail() }}>
          <Edit2 className="h-3.5 w-3.5 mr-1" />View / Edit
        </Button>
        <TagPicker
          entityType="dms_document"
          entityId={doc.id}
          currentTags={tags}
          onTagsChanged={onTagsChanged}
        >
          <Button size="sm" variant="outline" onClick={(e) => e.stopPropagation()}>
            <Tags className="h-3.5 w-3.5 mr-1" />Tags
          </Button>
        </TagPicker>
        <Button size="sm" variant="destructive" onClick={(e) => { e.stopPropagation(); onDelete() }}>
          <Trash2 className="h-3.5 w-3.5 mr-1" />Delete
        </Button>
      </div>
    </div>
  )
}
