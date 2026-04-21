import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { Award } from 'lucide-react'
import { coursesApi } from '@/api/courses'
import { cn } from '@/lib/utils'
import { fmtDate } from './utils'
import type { Certification, Enrollment } from '@/types/courses'

function expiryColor(days: number | null) {
  if (days === null) return ''
  if (days <= 0) return 'text-red-600 bg-red-50 dark:bg-red-900/30'
  if (days <= 30) return 'text-red-600 bg-red-50 dark:bg-red-900/30'
  if (days <= 90) return 'text-yellow-700 bg-yellow-50 dark:bg-yellow-900/30'
  return 'text-green-700 bg-green-50 dark:bg-green-900/30'
}

export function CourseCertificationsTab({ courseId }: { courseId: number }) {
  const { data: enrollments = [] } = useQuery({
    queryKey: ['course-enrollments', courseId],
    queryFn: () => coursesApi.getEnrollments(courseId),
  })

  const { data: certifications = [], isLoading } = useQuery({
    queryKey: ['course-certifications', courseId],
    queryFn: () => coursesApi.getCertifications({ employee_id: undefined }),
    select: (data: Certification[]) => {
      const enrolledEmployeeIds = new Set(enrollments.map((e: Enrollment) => e.employee_id))
      return data.filter(c => enrolledEmployeeIds.has(c.employee_id))
    },
  })

  if (isLoading) return <Skeleton className="h-32 w-full" />

  if (certifications.length === 0) {
    return (
      <EmptyState
        icon={<Award className="h-8 w-8" />}
        title="No certifications"
        description="Certifications are auto-created when enrollments are marked as completed."
      />
    )
  }

  return (
    <div className="space-y-1.5">
      {certifications.map((cert) => (
        <div key={cert.id} className="flex items-center justify-between rounded-lg border px-3 py-2.5">
          <div>
            <div className="text-sm font-medium">{cert.employee_name}</div>
            <div className="text-xs text-muted-foreground">
              {cert.course_type_name} — #{cert.certificate_number ?? 'N/A'}
            </div>
            <div className="text-xs text-muted-foreground">
              Issued: {fmtDate(cert.issued_date)} — Expires: {fmtDate(cert.expiry_date)}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {cert.days_until_expiry !== null && (
              <Badge className={cn('text-xs border-0', expiryColor(cert.days_until_expiry))}>
                {cert.days_until_expiry <= 0 ? 'Expired' : `${cert.days_until_expiry}d`}
              </Badge>
            )}
            <Badge variant="outline" className="text-xs">{cert.status}</Badge>
          </div>
        </div>
      ))}
    </div>
  )
}
