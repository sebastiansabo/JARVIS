import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, GraduationCap, RotateCcw, BarChart3, List } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ColumnToggle, useColumnState, type ColumnDef } from '@/components/shared/ColumnToggle'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { QueryError } from '@/components/QueryError'
import { useTabParam } from '@/hooks/useTabParam'
import { coursesApi } from '@/api/courses'
import { toast } from 'sonner'
import CourseForm from './CourseForm'
import CoursesOverview from './CoursesOverview'
import type { Course, CourseStatus } from '@/types/courses'

interface Props {
  search: string
}

const MONTHS = [
  'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
  'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie',
]

function formatDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

function statusBadge(status: CourseStatus | null | undefined) {
  if (!status) return <Badge className="bg-gray-100 text-gray-600 border-0">Draft</Badge>
  const map: Record<CourseStatus, string> = {
    draft: 'bg-gray-100 text-gray-600',
    pending_approval: 'bg-yellow-100 text-yellow-700',
    approved: 'bg-blue-100 text-blue-700',
    in_progress: 'bg-indigo-100 text-indigo-700',
    completed: 'bg-green-100 text-green-700',
    cancelled: 'bg-red-100 text-red-700',
  }
  const labels: Record<CourseStatus, string> = {
    draft: 'Draft',
    pending_approval: 'Pending',
    approved: 'Approved',
    in_progress: 'In Progress',
    completed: 'Completed',
    cancelled: 'Cancelled',
  }
  return <Badge className={`${map[status]} border-0`}>{labels[status]}</Badge>
}

// Column definitions for ColumnToggle
const columnDefs: ColumnDef<Course>[] = [
  { key: 'name', label: 'Name', render: (c) => <span className="font-medium">{c.name}</span> },
  { key: 'type', label: 'Type', render: (c) => <span className="text-muted-foreground">{c.course_type_name ?? '—'}</span> },
  { key: 'code', label: 'Code', render: (c) => <span className="text-muted-foreground font-mono text-xs">{c.course_code ?? '—'}</span> },
  { key: 'company', label: 'Company', render: (c) => <span className="text-muted-foreground">{c.company_name ?? '—'}</span> },
  { key: 'dates', label: 'Dates', className: 'whitespace-nowrap', render: (c) => <>{formatDate(c.start_date)} — {formatDate(c.end_date)}</> },
  { key: 'trainer', label: 'Trainer / Supplier', render: (c) => <span className="text-muted-foreground">{c.trainer_name || c.supplier_name || '—'}</span> },
  { key: 'participants', label: 'Participants', className: 'text-center', render: (c) => <Badge variant="secondary" className="text-xs">{c.enrollment_count}</Badge> },
  { key: 'validity', label: 'Validity', className: 'text-center', render: (c) => {
    if (!c.default_validity_months) return <span className="text-muted-foreground">—</span>
    return <Badge variant="outline" className="text-xs">{c.default_validity_months} mo</Badge>
  }},
  { key: 'budget', label: 'Budget', className: 'text-right tabular-nums whitespace-nowrap', render: (c) =>
    c.budget ? `${Number(c.budget).toLocaleString()} ${c.currency}` : '—'
  },
  { key: 'status', label: 'Status', render: (c) => statusBadge(c.status) },
]

const ALL_COLUMN_KEYS = columnDefs.map((c) => c.key)
const DEFAULT_COLUMNS = ['name', 'type', 'code', 'company', 'dates', 'participants', 'budget', 'status']
const LOCKED_COLUMNS = new Set(['name'])

type PageTab = 'overview' | 'list'

export default function CoursesTab({ search }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Page-level tabs: Overview | List
  const [pageTab, setPageTab] = useTabParam<PageTab>('overview', 'view')

  // Year for overview
  const [overviewYear, setOverviewYear] = useState(new Date().getFullYear())

  // Create dialog
  const [showCreateDialog, setShowCreateDialog] = useState(false)

  // Filters
  const [typeFilter, setTypeFilter] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [yearFilter, setYearFilter] = useState<number | null>(null)
  const [monthFilter, setMonthFilter] = useState<number | null>(null)
  const [showDeleted, setShowDeleted] = useState(false)

  // Selection
  const [selected, setSelected] = useState<Set<number>>(new Set())

  // Delete state
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)

  // Column management
  const { visibleColumns, setVisibleColumns, defaultColumns } = useColumnState(
    'hr-courses-columns',
    DEFAULT_COLUMNS,
    ALL_COLUMN_KEYS,
    'hr_courses',
  )

  // Available years for filter
  const { data: availableYears = [] } = useQuery({
    queryKey: ['course-years'],
    queryFn: () => coursesApi.getAvailableYears(),
    staleTime: 5 * 60_000,
  })

  // Course types for filter dropdown
  const { data: courseTypes = [] } = useQuery({
    queryKey: ['course-types'],
    queryFn: () => coursesApi.getCourseTypes(),
    staleTime: 5 * 60_000,
  })

  // Courses list
  const { data, isLoading, error } = useQuery({
    queryKey: ['courses', typeFilter, statusFilter, yearFilter, monthFilter, showDeleted],
    queryFn: () =>
      coursesApi.getCourses({
        course_type_id: typeFilter || undefined,
        status: statusFilter || undefined,
        year: yearFilter || undefined,
        month: monthFilter || undefined,
        include_deleted: showDeleted || undefined,
      }),
    enabled: pageTab === 'list',
  })

  // Mutations
  const deleteMutation = useMutation({
    mutationFn: (id: number) => coursesApi.deleteCourse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success('Course moved to bin')
    },
    onError: () => toast.error('Failed to delete course'),
  })

  const restoreMutation = useMutation({
    mutationFn: (id: number) => coursesApi.restoreCourse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success('Course restored')
    },
    onError: () => toast.error('Failed to restore course'),
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: number[]) => coursesApi.bulkDeleteCourses(ids),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      setSelected(new Set())
      toast.success(`${res.deleted} course(s) moved to bin`)
    },
    onError: () => toast.error('Failed to delete courses'),
  })

  const bulkRestoreMutation = useMutation({
    mutationFn: (ids: number[]) => coursesApi.bulkRestoreCourses(ids),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      setSelected(new Set())
      toast.success(`${res.restored} course(s) restored`)
    },
    onError: () => toast.error('Failed to restore courses'),
  })

  // Filter with search prop
  const filtered = useMemo(() => {
    if (!data?.courses) return []
    if (!search) return data.courses
    const q = search.toLowerCase()
    return data.courses.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.course_type_name ?? '').toLowerCase().includes(q) ||
        (c.supplier_name ?? '').toLowerCase().includes(q) ||
        (c.trainer_name ?? '').toLowerCase().includes(q) ||
        (c.course_code ?? '').toLowerCase().includes(q),
    )
  }, [data, search])

  const allSelected = filtered.length > 0 && filtered.every((c) => selected.has(c.id))

  const toggleAll = () => {
    if (allSelected) setSelected(new Set())
    else setSelected(new Set(filtered.map((c) => c.id)))
  }

  const toggleOne = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Visible column defs for rendering
  const activeColumns = columnDefs.filter((c) => visibleColumns.includes(c.key))

  return (
    <div className="space-y-4">
      {/* Page-level tabs + Add button */}
      <div className="flex items-center justify-between">
        <Tabs value={pageTab} onValueChange={(v) => setPageTab(v as PageTab)}>
          <TabsList>
            <TabsTrigger value="overview">
              <BarChart3 className="h-3.5 w-3.5 mr-1.5" />Overview
            </TabsTrigger>
            <TabsTrigger value="list">
              <List className="h-3.5 w-3.5 mr-1.5" />List
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <Button size="sm" onClick={() => setShowCreateDialog(true)}>
          <Plus className="mr-1.5 h-4 w-4" /> Add Course
        </Button>
      </div>

      {/* Overview Tab */}
      {pageTab === 'overview' && (
        <CoursesOverview year={overviewYear} onYearChange={setOverviewYear} />
      )}

      {/* List Tab */}
      {pageTab === 'list' && (
        <>
          {error && <QueryError message="Failed to load courses" />}

          {/* Filters bar */}
          <div className="flex flex-wrap items-center gap-3">
            <Select value={typeFilter ? String(typeFilter) : 'all'} onValueChange={(v) => setTypeFilter(v === 'all' ? null : Number(v))}>
              <SelectTrigger className="h-8 w-[160px] text-xs"><SelectValue placeholder="All types" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                {courseTypes.map((ct) => <SelectItem key={ct.id} value={String(ct.id)}>{ct.name}</SelectItem>)}
              </SelectContent>
            </Select>

            <Select value={statusFilter || 'all'} onValueChange={(v) => setStatusFilter(v === 'all' ? '' : v)}>
              <SelectTrigger className="h-8 w-[140px] text-xs"><SelectValue placeholder="All statuses" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="draft">Draft</SelectItem>
                <SelectItem value="pending_approval">Pending</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="in_progress">In Progress</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="cancelled">Cancelled</SelectItem>
              </SelectContent>
            </Select>

            <Select value={yearFilter ? String(yearFilter) : 'all'} onValueChange={(v) => { setYearFilter(v === 'all' ? null : Number(v)); if (v === 'all') setMonthFilter(null) }}>
              <SelectTrigger className="h-8 w-[110px] text-xs"><SelectValue placeholder="All years" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All years</SelectItem>
                {availableYears.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
              </SelectContent>
            </Select>

            {yearFilter && (
              <Select value={monthFilter ? String(monthFilter) : 'all'} onValueChange={(v) => setMonthFilter(v === 'all' ? null : Number(v))}>
                <SelectTrigger className="h-8 w-[130px] text-xs"><SelectValue placeholder="All months" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All months</SelectItem>
                  {MONTHS.map((m, i) => <SelectItem key={i + 1} value={String(i + 1)}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            )}

            <Button size="sm" variant={showDeleted ? 'secondary' : 'ghost'} className="h-8 text-xs"
              onClick={() => { setShowDeleted(!showDeleted); setSelected(new Set()) }}>
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              {showDeleted ? 'Showing Bin' : 'Bin'}
            </Button>

            <div className="ml-auto flex items-center gap-2">
              {selected.size > 0 && (
                <>
                  {showDeleted ? (
                    <Button size="sm" variant="outline" className="h-8 text-xs"
                      onClick={() => bulkRestoreMutation.mutate(Array.from(selected))}>
                      <RotateCcw className="mr-1 h-3.5 w-3.5" /> Restore ({selected.size})
                    </Button>
                  ) : (
                    <Button size="sm" variant="destructive" className="h-8 text-xs"
                      onClick={() => setBulkDeleteOpen(true)}>
                      <Trash2 className="mr-1 h-3.5 w-3.5" /> Delete ({selected.size})
                    </Button>
                  )}
                </>
              )}

              <ColumnToggle
                visibleColumns={visibleColumns}
                defaultColumns={defaultColumns}
                columnDefs={columnDefs}
                lockedColumns={LOCKED_COLUMNS}
                onChange={setVisibleColumns}
              />
            </div>
          </div>

          {/* Table */}
          <Card>
            {isLoading ? (
              <div className="p-4 space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : filtered.length === 0 ? (
              <EmptyState
                icon={<GraduationCap className="h-8 w-8" />}
                title={showDeleted ? 'Bin is empty' : 'No courses found'}
                description={showDeleted ? 'No deleted courses.' : 'Create your first course.'}
              />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10">
                        <Checkbox checked={allSelected} onCheckedChange={toggleAll} />
                      </TableHead>
                      {activeColumns.map((col) => (
                        <TableHead key={col.key} className={col.className}>{col.label}</TableHead>
                      ))}
                      <TableHead className="w-20">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filtered.map((c) => (
                      <TableRow key={c.id} className="cursor-pointer"
                        onClick={() => !showDeleted && navigate(`/app/hr/courses/${c.id}`)}>
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <Checkbox checked={selected.has(c.id)} onCheckedChange={() => toggleOne(c.id)} />
                        </TableCell>
                        {activeColumns.map((col) => (
                          <TableCell key={col.key} className={`text-sm ${col.className ?? ''}`}>
                            {col.render(c)}
                          </TableCell>
                        ))}
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <div className="flex gap-1">
                            {showDeleted ? (
                              <Button variant="ghost" size="icon" className="h-7 w-7"
                                onClick={() => restoreMutation.mutate(c.id)} title="Restore">
                                <RotateCcw className="h-3.5 w-3.5" />
                              </Button>
                            ) : (
                              <>
                                <Button variant="ghost" size="icon" className="h-7 w-7"
                                  onClick={() => navigate(`/app/hr/courses/${c.id}`)}>
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive"
                                  onClick={() => setDeleteId(c.id)}>
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </Card>

          {/* Delete dialogs */}
          <ConfirmDialog
            open={deleteId !== null}
            onOpenChange={(open) => { if (!open) setDeleteId(null) }}
            title="Delete Course"
            description="This course will be moved to the bin."
            onConfirm={() => { if (deleteId) deleteMutation.mutate(deleteId); setDeleteId(null) }}
            destructive
          />
          <ConfirmDialog
            open={bulkDeleteOpen}
            onOpenChange={setBulkDeleteOpen}
            title={`Delete ${selected.size} Course(s)`}
            description="These courses will be moved to the bin."
            onConfirm={() => { bulkDeleteMutation.mutate(Array.from(selected)); setBulkDeleteOpen(false) }}
            destructive
          />
        </>
      )}

      {/* Create Course Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-[900px] max-h-[90vh] overflow-y-auto" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Add Course</DialogTitle>
          </DialogHeader>
          <CourseForm
            onSuccess={(id) => {
              setShowCreateDialog(false)
              queryClient.invalidateQueries({ queryKey: ['courses'] })
              navigate(`/app/hr/courses/${id}`)
            }}
            onCancel={() => setShowCreateDialog(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  )
}
