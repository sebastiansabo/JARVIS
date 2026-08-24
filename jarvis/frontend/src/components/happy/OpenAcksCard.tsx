import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Clock, FileCheck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { happyApi } from '@/api/happy'

/** Deadline shown on an open-ack row, e.g. "25 aug, 21:00". */
function formatDeadline(iso: string): string {
  const d = new Date(iso)
  const date = d.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })
  const time = d.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
  return `${date}, ${time}`
}

/**
 * Hub card listing the current user's outstanding acknowledgements, soonest
 * deadline first. Collapses to null when the inbox is empty. Row click routes to
 * the Hub, where the Spotlight surfaces the campaign to acknowledge.
 */
export function OpenAcksCard() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['happy', 'inbox'],
    queryFn: () => happyApi.getInbox(),
    staleTime: 30_000,
  })

  const items = data?.items ?? []
  if (!isLoading && items.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <FileCheck className="h-4 w-4" />
          Confirmări în așteptare
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => navigate('/app/hub')}
              className="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-accent/50"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{item.title}</p>
                {item.ack_deadline_at && (
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    Termen: {formatDeadline(item.ack_deadline_at)}
                  </span>
                )}
              </div>
              {item.tier === 'critical' ? (
                <Badge variant="destructive" className="shrink-0">
                  Obligatoriu
                </Badge>
              ) : item.tier === 'important' ? (
                <Badge variant="secondary" className={cn('shrink-0')}>
                  Important
                </Badge>
              ) : null}
            </button>
          ))
        )}
      </CardContent>
    </Card>
  )
}

export default OpenAcksCard
