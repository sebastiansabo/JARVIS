import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, GraduationCap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { QueryError } from '@/components/QueryError'
import { coursesApi } from '@/api/courses'
import { toast } from 'sonner'
import type { CourseStatus } from '@/types/courses'

interface Props {
  search: string
}

function formatDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

function statusBadge(status: CourseStatus) {
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

export default function CoursesTab({ search }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Filters
  const [typeFilter, setTypeFilter] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')

  // Delete state
  const [deleteId, setDeleteId] = useState<number | null>(null)

  // Course types for filter dropdown
  const { data: courseTypes = [] } = useQuery({
    queryKey: ['course-types'],
    queryFn: () => coursesApi.getCourseTypes(),
    staleTime: 5 * 60_000,
  })

  // Courses list
  const { data, isLoading, error } = useQuery({
    queryKey: ['courses', typeFilter, statusFilter],
    queryFn: () =>
      coursesApi.getCourses({
        course_type_id: typeFilter || undefined,
        status: statusFilter || undefined,
      }),
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: number) => coursesApi.deleteCourse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success('Course deleted')
    },
    onError: () => toast.error('Failed to delete course'),
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
        (c.trainer_name ?? '').toLowerCase().includes(q),
    )
  }, [data, search])

  if (error) return <QueryError message="Failed to load courses" />

  return (
    <div className="space-y-4">
      {/* Filters bar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Type filter */}
        <Select
          value={typeFilter ? String(typeFilter) : 'all'}
          onValueChange={(v) => setTypeFilter(v === 'all' ? null : Number(v))}
        >
          <SelectTrigger className="h-8 w-[160px] text-xs">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {courseTypes.map((ct) => (
              <SelectItem key={ct.id} value={String(ct.id)}>
                {ct.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Status filter */}
        <Select
          value={statusFilter || 'all'}
          onValueChange={(v) => setStatusFilter(v === 'all' ? '' : v)}
        >
          <SelectTrigger className="h-8 w-[140px] text-xs">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
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

        <div className="ml-auto">
          <Button size="sm" onClick={() => navigate('/app/hr/courses/add')}>
            <Plus className="mr-1.5 h-4 w-4" /> Add Course
          </Button>
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
            title="No courses found"
            description="Create your first course."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Dates</TableHead>
                  <TableHead>Trainer / Supplier</TableHead>
                  <TableHead className="text-center">Participants</TableHead>
                  <TableHead className="text-right">Budget</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-20">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((c) => (
                  <TableRow
                    key={c.id}
                    className="cursor-pointer"
                    onClick={() => navigate(`/app/hr/courses/${c.id}/edit`)}
                  >
                    <TableCell className="text-sm font-medium">{c.name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {c.course_type_name ?? '—'}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {c.company_name ?? '—'}
                    </TableCell>
                    <TableCell className="text-sm whitespace-nowrap">
                      {formatDate(c.start_date)} — {formatDate(c.end_date)}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {c.trainer_name || c.supplier_name || '—'}
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge variant="secondary" className="text-xs">
                        {c.enrollment_count}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-right tabular-nums whitespace-nowrap">
                      {c.budget
                        ? `${Number(c.budget).toLocaleString()} ${c.currency}`
                        : '—'}
                    </TableCell>
                    <TableCell>{statusBadge(c.status)}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => navigate(`/app/hr/courses/${c.id}/edit`)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          onClick={() => setDeleteId(c.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>

      {/* Delete confirm dialog */}
      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteId(null)
        }}
        title="Delete Course"
        description="This will permanently delete this course and all enrollments."
        onConfirm={() => {
          if (deleteId) deleteMutation.mutate(deleteId)
          setDeleteId(null)
        }}
        destructive
      />
    </div>
  )
}
