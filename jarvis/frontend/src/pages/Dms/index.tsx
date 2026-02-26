import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FolderOpen, FileText, Plus, Search, Trash2, RotateCcw,
  Settings2, Paperclip, Users as ChildrenIcon,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/useAuth'
import { useTabParam } from '@/hooks/useTabParam'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import { useDmsStore } from '@/stores/dmsStore'
import type { DmsDocument, DmsCategory } from '@/types/dms'
import UploadDialog from './UploadDialog'
import CategoryManager from './CategoryManager'

type MainTab = 'documents' | 'categories'

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

export default function Dms() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [mainTab, setMainTab] = useTabParam<MainTab>('documents')
  const { filters, updateFilter, clearFilters } = useDmsStore()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => {
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(debounceRef.current)
  }, [search])
  const [uploadOpen, setUploadOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const companyId = filters.company_id || user?.company_id || undefined

  // Queries
  const { data: statsData, isLoading: statsLoading } = useQuery({
    queryKey: ['dms-stats', companyId],
    queryFn: () => dmsApi.getStats(companyId),
    enabled: mainTab === 'documents',
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['dms-categories', companyId],
    queryFn: () => dmsApi.listCategories(companyId),
  })

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ['dms-documents', { ...filters, search: debouncedSearch, company_id: companyId }],
    queryFn: () => dmsApi.listDocuments({ ...filters, search: debouncedSearch, company_id: companyId }),
    enabled: mainTab === 'documents',
  })

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

  const categories: DmsCategory[] = categoriesData?.categories || []
  const documents: DmsDocument[] = docsData?.documents || []
  const total = docsData?.total || 0
  const stats = statsData?.by_status

  const isAdmin = user?.can_access_settings

  return (
    <div className="space-y-6">
      <PageHeader
        title="Documents"
        description="Document Management System"
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={() => setUploadOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Upload Document
            </Button>
          </div>
        }
      />

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b">
        <button
          onClick={() => setMainTab('documents')}
          className={cn(
            'flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors',
            mainTab === 'documents'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground',
          )}
        >
          <FolderOpen className="h-3.5 w-3.5" />
          Documents
          {stats?.total ? <Badge variant="secondary" className="ml-1 text-xs">{stats.total}</Badge> : null}
        </button>
        {isAdmin && (
          <button
            onClick={() => setMainTab('categories')}
            className={cn(
              'flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              mainTab === 'categories'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <Settings2 className="h-3.5 w-3.5" />
            Categories
          </button>
        )}
      </div>

      {mainTab === 'documents' && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard title="Total Documents" value={stats?.total ?? 0} isLoading={statsLoading} />
            <StatCard title="Draft" value={stats?.draft ?? 0} isLoading={statsLoading} />
            <StatCard title="Active" value={stats?.active ?? 0} isLoading={statsLoading} />
            <StatCard title="Archived" value={stats?.archived ?? 0} isLoading={statsLoading} />
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search documents..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>

            <Select
              value={filters.category_id?.toString() || 'all'}
              onValueChange={(v) => updateFilter('category_id', v === 'all' ? undefined : Number(v))}
            >
              <SelectTrigger className="w-[180px]">
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
              <SelectTrigger className="w-[140px]">
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
          </div>

          {/* Table */}
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
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Title</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead className="text-center">Files</TableHead>
                      <TableHead className="text-center">Annexes</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Expiry</TableHead>
                      <TableHead>Created By</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead className="w-[60px]" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.map((doc) => (
                      <TableRow
                        key={doc.id}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => navigate(`/app/dms/documents/${doc.id}`)}
                      >
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                            <span className="font-medium">{doc.title}</span>
                          </div>
                        </TableCell>
                        <TableCell>
                          {doc.category_name ? (
                            <Badge
                              variant="outline"
                              style={{ borderColor: doc.category_color || undefined, color: doc.category_color || undefined }}
                            >
                              {doc.category_name}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          {(doc.file_count ?? 0) > 0 ? (
                            <span className="inline-flex items-center gap-1 text-sm">
                              <Paperclip className="h-3.5 w-3.5" />
                              {doc.file_count}
                            </span>
                          ) : '—'}
                        </TableCell>
                        <TableCell className="text-center">
                          {(doc.children_count ?? 0) > 0 ? (
                            <span className="inline-flex items-center gap-1 text-sm">
                              <ChildrenIcon className="h-3.5 w-3.5" />
                              {doc.children_count}
                            </span>
                          ) : '—'}
                        </TableCell>
                        <TableCell>
                          <Badge className={cn('text-xs', STATUS_COLORS[doc.status])}>
                            {doc.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {doc.expiry_date ? (
                            <span className={cn('text-sm font-medium', expiryColor(doc.days_to_expiry))}>
                              {formatDate(doc.expiry_date)}
                              {doc.days_to_expiry != null && (
                                <span className="block text-xs font-normal">
                                  {doc.days_to_expiry < 0
                                    ? `${Math.abs(doc.days_to_expiry)}d expired`
                                    : doc.days_to_expiry === 0
                                      ? 'Expires today'
                                      : `${doc.days_to_expiry}d left`}
                                </span>
                              )}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {doc.created_by_name || '—'}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatDate(doc.created_at)}
                        </TableCell>
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
        </>
      )}

      {mainTab === 'categories' && isAdmin && (
        <CategoryManager companyId={companyId} />
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
    </div>
  )
}
