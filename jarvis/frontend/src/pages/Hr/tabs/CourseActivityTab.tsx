import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { Clock } from 'lucide-react'
import { coursesApi } from '@/api/courses'
import { fmtDatetime } from './utils'

export function CourseActivityTab({ courseId }: { courseId: number }) {
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['course-activity', courseId],
    queryFn: () => coursesApi.getCourseActivity(courseId, 100),
  })

  if (isLoading) return <Skeleton className="h-32 w-full" />

  return (
    <div className="space-y-1">
      {items.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Clock className="mx-auto h-8 w-8 mb-2 opacity-40" />
          <div>No activity yet</div>
          <div className="text-xs mt-1">Activity will appear as changes are made to this course.</div>
        </div>
      ) : (
        <div className="space-y-0">
          {items.map((a) => (
            <div key={a.id} className="flex items-start gap-3 py-2.5 border-b last:border-0">
              <div className="mt-0.5 h-2 w-2 rounded-full bg-primary shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{a.actor_display_name ?? a.actor_name ?? 'System'}</span>
                  <span className="text-sm text-muted-foreground">{a.action.replace(/_/g, ' ')}</span>
                </div>
                {a.details && Object.keys(a.details).length > 0 && (
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {Object.entries(a.details)
                      .filter(([, v]) => v !== null && v !== undefined)
                      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
                      .join(' · ')}
                  </div>
                )}
              </div>
              <span className="text-xs text-muted-foreground shrink-0">{fmtDatetime(a.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
