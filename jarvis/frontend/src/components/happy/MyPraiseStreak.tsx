import { Flame } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { useMyPraise } from '@/api/happy'
import { cn } from '@/lib/utils'
import type { HappyPraiseTrendPoint } from '@/types/happy'

/**
 * Align two trend series onto the same set of week buckets (last N weeks), so the
 * bars line up column-for-column even if one series is missing a week.
 */
function mergeWeeks(
  sent: HappyPraiseTrendPoint[],
  received: HappyPraiseTrendPoint[],
  weeks = 12,
): { wk: string; sent: number; received: number }[] {
  const sentMap = new Map(sent.map((p) => [p.wk, p.n]))
  const recvMap = new Map(received.map((p) => [p.wk, p.n]))
  const allWeeks = Array.from(new Set([...sentMap.keys(), ...recvMap.keys()])).sort()
  return allWeeks.slice(-weeks).map((wk) => ({
    wk,
    sent: sentMap.get(wk) ?? 0,
    received: recvMap.get(wk) ?? 0,
  }))
}

/**
 * The caller's OWN recognition streak + a 12-week sent/received trend.
 * Personal feedback only — no ranking, no peer comparison, no leaderboard.
 */
export function MyPraiseStreak() {
  const { data, isLoading } = useMyPraise()

  if (isLoading) {
    return <Skeleton className="h-20 w-full" />
  }
  if (!data) return null

  const series = mergeWeeks(data.sent ?? [], data.received ?? [])
  const max = Math.max(1, ...series.map((s) => Math.max(s.sent, s.received)))

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <Flame className="h-4 w-4 text-orange-500" />
          {data.streak_weeks} {data.streak_weeks === 1 ? 'săptămână' : 'săptămâni'} la rând
        </span>
        <span className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm bg-primary" /> trimise
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm bg-muted-foreground/40" /> primite
          </span>
        </span>
      </div>

      {series.length > 0 && (
        <div className="flex h-16 items-end gap-1">
          {series.map((s) => (
            <div key={s.wk} className="flex flex-1 items-end justify-center gap-0.5" title={s.wk}>
              <div
                className={cn('w-1.5 rounded-sm bg-primary')}
                style={{ height: `${Math.max(2, (s.sent / max) * 100)}%` }}
                aria-hidden
              />
              <div
                className={cn('w-1.5 rounded-sm bg-muted-foreground/40')}
                style={{ height: `${Math.max(2, (s.received / max) * 100)}%` }}
                aria-hidden
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default MyPraiseStreak
