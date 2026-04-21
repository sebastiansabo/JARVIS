import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTabParam } from '@/hooks/useTabParam'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PageHeader } from '@/components/shared/PageHeader'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Pencil, BarChart3, DollarSign, Users, FolderOpen,
  Award, Clock, Trash2, RotateCcw, CheckCircle, Send,
} from 'lucide-react'
import { coursesApi } from '@/api/courses'
import { toast } from 'sonner'
import CourseForm from './CourseForm'
import {
  CourseOverviewTab, ParticipantsTab, CostsTab,
  CourseDocumentsTab, CourseCertificationsTab, CourseActivityTab,
  courseStatusColors,
} from './tabs'

type Tab = 'overview' | 'participants' | 'costs' | 'documents' | 'certifications' | 'activity'

const tabConfig: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: 'overview', label: 'Overview', icon: BarChart3 },
  { key: 'participants', label: 'Participants', icon: Users },
  { key: 'costs', label: 'Costs', icon: DollarSign },
  { key: 'documents', label: 'Documents', icon: FolderOpen },
  { key: 'certifications', label: 'Certifications', icon: Award },
  { key: 'activity', label: 'Activity', icon: Clock },
]

export default function CourseDetail() {
  const { courseId } = useParams<{ courseId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const id = Number(courseId)

  const [activeTab, setActiveTab] = useTabParam<Tab>('overview')
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)

  const { data: course, isLoading } = useQuery({
    queryKey: ['course', id],
    queryFn: () => coursesApi.getCourse(id),
    enabled: !!id,
  })

  const deleteMutation = useMutation({
    mutationFn: () => coursesApi.deleteCourse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success('Course moved to bin')
      navigate('/app/hr/courses')
    },
    onError: () => toast.error('Failed to delete course'),
  })

  const restoreMutation = useMutation({
    mutationFn: () => coursesApi.restoreCourse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course', id] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success('Course restored')
    },
    onError: () => toast.error('Failed to restore course'),
  })

  const approvalMutation = useMutation({
    mutationFn: () => coursesApi.submitApproval(id),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['course', id] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success(`Course ${res.status === 'approved' ? 'approved' : 'submitted for approval'}`)
    },
    onError: () => toast.error('Failed to submit for approval'),
  })

  const statusMutation = useMutation({
    mutationFn: (status: string) => coursesApi.updateCourse(id, { status } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course', id] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      toast.success('Status updated')
    },
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!course) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        Course not found.
        <Button variant="link" onClick={() => navigate('/app/hr/courses')}>Back to courses</Button>
      </div>
    )
  }

  const isDeleted = !!course.deleted_at

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title={course.name}
        breadcrumbs={[
          { label: 'HR', shortLabel: 'HR', href: '/app/hr/employees' },
          { label: 'Courses', shortLabel: 'Courses', href: '/app/hr/courses' },
          { label: course.name },
        ]}
        description={
          <div className="flex flex-col gap-1 md:flex-row md:flex-wrap md:items-center md:gap-x-2 md:gap-y-0">
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium w-fit ${courseStatusColors[course.status ?? 'draft'] ?? ''}`}>
              {(course.status ?? 'draft').replace(/_/g, ' ')}
            </span>
            <span className="text-sm text-muted-foreground">
              {course.course_type_name ?? ''}
              {course.company_name ? ` · ${course.company_name}` : ''}
              {course.trainer_name ? ` · Trainer: ${course.trainer_name}` : ''}
            </span>
          </div>
        }
        actions={
          <div className="flex items-center gap-2">
            {isDeleted ? (
              <Button variant="outline" size="sm" onClick={() => restoreMutation.mutate()} disabled={restoreMutation.isPending}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Restore
              </Button>
            ) : (
              <>
                <Button variant="outline" size="icon" className="h-10 w-10 md:h-8 md:w-8"
                  onClick={() => setShowEditDialog(true)} title="Edit">
                  <Pencil className="h-4 w-4 md:h-3.5 md:w-3.5" />
                </Button>

                {/* Status actions */}
                {course.status === 'draft' && (
                  <Button size="sm" variant="outline" onClick={() => approvalMutation.mutate()}
                    disabled={approvalMutation.isPending}>
                    <Send className="mr-1.5 h-3.5 w-3.5" /> Submit Approval
                  </Button>
                )}
                {course.status === 'approved' && (
                  <Button size="sm" variant="outline" onClick={() => statusMutation.mutate('in_progress')}>
                    <CheckCircle className="mr-1.5 h-3.5 w-3.5" /> Start
                  </Button>
                )}
                {course.status === 'in_progress' && (
                  <Button size="sm" variant="outline" onClick={() => statusMutation.mutate('completed')}>
                    <CheckCircle className="mr-1.5 h-3.5 w-3.5" /> Complete
                  </Button>
                )}

                <Button variant="outline" size="icon" className="h-10 w-10 md:h-8 md:w-8 text-destructive"
                  onClick={() => setShowDeleteDialog(true)} title="Delete">
                  <Trash2 className="h-4 w-4 md:h-3.5 md:w-3.5" />
                </Button>
              </>
            )}
          </div>
        }
      />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
          <TabsList className="w-full md:w-auto">
            {tabConfig.map((tab) => {
              const Icon = tab.icon
              return (
                <TabsTrigger key={tab.key} value={tab.key} className="flex-1 md:flex-initial">
                  <Icon className="h-3.5 w-3.5" />
                  <span className="hidden md:inline">{tab.label}</span>
                </TabsTrigger>
              )
            })}
          </TabsList>
        </div>
      </Tabs>

      {/* Tab Content */}
      {activeTab === 'overview' && <CourseOverviewTab course={course} />}
      {activeTab === 'participants' && <ParticipantsTab courseId={id} currency={course.currency} />}
      {activeTab === 'costs' && <CostsTab course={course} />}
      {activeTab === 'documents' && <CourseDocumentsTab courseId={id} />}
      {activeTab === 'certifications' && <CourseCertificationsTab courseId={id} />}
      {activeTab === 'activity' && <CourseActivityTab courseId={id} />}

      {/* Edit Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="sm:max-w-[900px] max-h-[90vh] overflow-y-auto" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Edit Course</DialogTitle>
          </DialogHeader>
          <CourseForm
            course={course}
            onSuccess={() => {
              setShowEditDialog(false)
              queryClient.invalidateQueries({ queryKey: ['course', id] })
              queryClient.invalidateQueries({ queryKey: ['courses'] })
            }}
            onCancel={() => setShowEditDialog(false)}
          />
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <ConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        title="Delete Course"
        description="This course will be moved to the bin. You can restore it later."
        onConfirm={() => {
          deleteMutation.mutate()
          setShowDeleteDialog(false)
        }}
        destructive
      />
    </div>
  )
}
