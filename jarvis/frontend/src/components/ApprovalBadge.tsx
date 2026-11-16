import { useQuery } from '@tanstack/react-query'
import { approvalsApi } from '@/api/approvals'

export function ApprovalBadge() {
  const { data } = useQuery({
    queryKey: ['approval-queue-count'],
    queryFn: () => approvalsApi.getMyQueueCount(),
    refetchInterval: 60000, // halve badge-poll volume (504 relief); server caches 15s
  })

  const count = data?.count ?? 0
  if (count === 0) return null

  return (
    <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-xs font-medium text-white">
      {count > 99 ? '99+' : count}
    </span>
  )
}
