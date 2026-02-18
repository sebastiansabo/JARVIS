import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { marketingApi } from '@/api/marketing'
import { fmtDatetime } from './utils'

export function ActivityTab({ projectId }: { projectId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['mkt-activity', projectId],
    queryFn: () => marketingApi.getActivity(projectId, 100),
  })
  const items = data?.activity ?? []

  if (isLoading) return <Skeleton className="h-32 w-full" />

  return (
    <div className="space-y-1">
      {items.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No activity yet.</div>
      ) : (
        <div className="space-y-0">
          {items.map((a) => (
            <div key={a.id} className="flex items-start gap-3 py-2.5 border-b last:border-0">
              <div className="mt-0.5 h-2 w-2 rounded-full bg-primary shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{a.actor_name ?? 'System'}</span>
                  <span className="text-sm text-muted-foreground">{a.action.replace('_', ' ')}</span>
                </div>
                {a.details && Object.keys(a.details).length > 0 && (
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {Object.entries(a.details).map(([k, v]) => `${k}: ${v}`).join(' · ')}
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
