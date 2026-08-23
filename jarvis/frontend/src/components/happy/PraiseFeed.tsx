import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { praiseApi } from '@/api/happy'

/** Short relative time, e.g. "acum 3 zile". */
function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(ms / 60_000)
  if (mins < 1) return 'acum'
  if (mins < 60) return `acum ${mins} min`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `acum ${hrs} h`
  const days = Math.floor(hrs / 24)
  return `acum ${days} ${days === 1 ? 'zi' : 'zile'}`
}

interface PraiseFeedProps {
  limit?: number
}

/**
 * The caller's received kudos — value-tag chip, note and relative date.
 * Self-contained list (no outer Card) so it can be embedded anywhere.
 */
export function PraiseFeed({ limit = 10 }: PraiseFeedProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['happy', 'praise', 'received', limit],
    queryFn: () => praiseApi.getReceived(limit),
    staleTime: 30_000,
  })

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  const items = data?.items ?? []
  if (items.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Încă nu ai primit aprecieri.
      </p>
    )
  }

  return (
    <div className="space-y-2">
      {items.map((k) => (
        <div key={k.id} className="rounded-lg border p-3">
          <div className="mb-1 flex items-center justify-between gap-2">
            {k.value_label ? (
              <Badge variant="secondary">{k.value_label}</Badge>
            ) : (
              <span />
            )}
            <span className="whitespace-nowrap text-xs text-muted-foreground">
              {timeAgo(k.created_at)}
            </span>
          </div>
          <p className="text-sm">{k.note}</p>
          <p className="mt-1 text-xs text-muted-foreground">de la {String(k.from_user)}</p>
        </div>
      ))}
    </div>
  )
}

export default PraiseFeed
