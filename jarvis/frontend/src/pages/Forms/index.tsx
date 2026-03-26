import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formsApi } from '@/api/forms'
import { useFormsStore } from '@/stores/formsStore'
import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { StatCard } from '@/components/shared/StatCard'
import { TableSkeleton } from '@/components/shared/TableSkeleton'
import { Button } from '@/components/ui/button'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Plus, MoreVertical, Eye, Pencil, Copy, Trash2, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'
import type { FormStatus } from '@/types/forms'

const statusConfig: Record<FormStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  draft: { label: 'Draft', variant: 'secondary' },
  published: { label: 'Published', variant: 'default' },
  disabled: { label: 'Disabled', variant: 'outline' },
  archived: { label: 'Archived', variant: 'destructive' },
}

type Tab = 'all' | 'published' | 'draft' | 'archived'

export default function Forms() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { filters, updateFilter } = useFormsStore()
  const [activeTab, setActiveTab] = useState<Tab>('all')

  const statusFilter = activeTab === 'all' ? undefined : activeTab
  const { data, isLoading } = useQuery({
    queryKey: ['forms', filters, statusFilter],
    queryFn: () => formsApi.listForms({ ...filters, status: statusFilter }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => formsApi.deleteForm(id),
    onSuccess: () => {
      toast.success('Form deleted')
      queryClient.invalidateQueries({ queryKey: ['forms'] })
    },
    onError: () => toast.error('Failed to delete form'),
  })

  const duplicateMutation = useMutation({
    mutationFn: (id: number) => formsApi.duplicateForm(id),
    onSuccess: () => {
      toast.success('Form duplicated')
      queryClient.invalidateQueries({ queryKey: ['forms'] })
    },
    onError: () => toast.error('Failed to duplicate form'),
  })

  const forms = data?.forms ?? []
  const total = data?.total ?? 0
  const publishedCount = forms.filter((f) => f.status === 'published').length
  const draftCount = forms.filter((f) => f.status === 'draft').length

  return (
    <div className="space-y-6">
      <PageHeader
        title="Forms"
        actions={
          <Button onClick={() => navigate('builder')} size="sm">
            <Plus className="h-4 w-4 mr-2" />
            New Form
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard title="Total Forms" value={total} />
        <StatCard title="Published" value={publishedCount} />
        <StatCard title="Drafts" value={draftCount} />
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
            <TabsList>
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="published">Published</TabsTrigger>
              <TabsTrigger value="draft">Drafts</TabsTrigger>
              <TabsTrigger value="archived">Archived</TabsTrigger>
            </TabsList>
          </Tabs>
          <SearchInput
            value={filters.search ?? ''}
            onChange={(q) => updateFilter('search', q)}
            placeholder="Search forms..."
          />
        </div>

        {isLoading ? (
          <TableSkeleton />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Submissions</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Published</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {forms.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                    No forms found. Create your first form to get started.
                  </TableCell>
                </TableRow>
              ) : (
                forms.map((form) => {
                  const sc = statusConfig[form.status] ?? statusConfig.draft
                  return (
                    <TableRow
                      key={form.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`${form.id}`)}
                    >
                      <TableCell className="font-medium">{form.name}</TableCell>
                      <TableCell>{form.company_name}</TableCell>
                      <TableCell>{form.submission_count ?? 0}</TableCell>
                      <TableCell>
                        <Badge variant={sc.variant}>{sc.label}</Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">
                        {form.published_at
                          ? new Date(form.published_at).toLocaleDateString('ro-RO')
                          : '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                            <Button variant="ghost" size="sm">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); navigate(`${form.id}`) }}>
                              <Eye className="h-4 w-4 mr-2" /> View
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); navigate(`builder/${form.id}`) }}>
                              <Pencil className="h-4 w-4 mr-2" /> Edit
                            </DropdownMenuItem>
                            {form.status === 'published' && (
                              <DropdownMenuItem onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(`${window.location.origin}/forms/public/${form.slug}`)
                                toast.success('Public link copied!')
                              }}>
                                <ExternalLink className="h-4 w-4 mr-2" /> Copy Link
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); duplicateMutation.mutate(form.id) }}>
                              <Copy className="h-4 w-4 mr-2" /> Duplicate
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(form.id) }}
                            >
                              <Trash2 className="h-4 w-4 mr-2" /> Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  )
}
