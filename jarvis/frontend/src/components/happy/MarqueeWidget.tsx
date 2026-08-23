import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useHappySurface } from '@/api/happy'
import { MarqueeCard } from './MarqueeCard'
import type { HappyPlacement } from '@/types/happy'

interface MarqueeWidgetProps {
  enabled?: boolean
  placement?: HappyPlacement
  route?: string
}

/**
 * Renders up to 3 Marquee items for a placement with a MANUAL pager (‹ 1/3 ›) —
 * no autoplay, no carousel timer (§6.3/§6.4). Collapses to null when empty.
 */
export function MarqueeWidget({
  enabled = true,
  placement = 'dash_banner',
  route = '/app/dashboard',
}: MarqueeWidgetProps) {
  const { data, isLoading } = useHappySurface(placement, route, enabled)
  const [page, setPage] = useState(0)
  const [dismissed, setDismissed] = useState<Set<number>>(new Set())

  if (!enabled) return null
  if (isLoading) return <Skeleton className="h-32 w-full rounded-xl" />

  const items = (data?.items ?? []).filter((i) => !dismissed.has(i.id)).slice(0, 3)
  if (items.length === 0) return null

  const idx = Math.min(page, items.length - 1)
  const current = items[idx]

  const handleDismiss = (id: number) => {
    setDismissed((prev) => new Set(prev).add(id))
    setPage(0)
  }

  return (
    <div className="space-y-1.5">
      <MarqueeCard item={current} onDismiss={handleDismiss} />

      {items.length > 1 && (
        <div className="flex items-center justify-end gap-1 text-xs text-muted-foreground">
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Anterior"
            disabled={idx === 0}
            onClick={() => setPage(Math.max(0, idx - 1))}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <span>
            {idx + 1}/{items.length}
          </span>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Următor"
            disabled={idx === items.length - 1}
            onClick={() => setPage(Math.min(items.length - 1, idx + 1))}
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  )
}

export default MarqueeWidget
