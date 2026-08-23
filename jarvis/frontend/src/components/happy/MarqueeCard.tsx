import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Megaphone, X } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { happyApi } from '@/api/happy'
import type { HappySurfaceItem } from '@/types/happy'

/** Dwell after which a Marquee item counts as read (≥8s at ≥50% visibility). */
const READ_DWELL_MS = 8_000

/** Event date chip, e.g. "24 sep · 18:00". */
function formatEventDate(iso: string): string {
  const d = new Date(iso)
  const date = d.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' })
  const time = d.toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
  return `${date} · ${time}`
}

interface MarqueeCardProps {
  item?: HappySurfaceItem | null
  onDismiss?: (id: number) => void
}

/**
 * A single ambient Marquee card (§6.3). Content-styled, no gradient, fixed 128px.
 * Owns its own impression/read/click/dismiss telemetry. Renders null with no item.
 */
export function MarqueeCard({ item, onDismiss }: MarqueeCardProps) {
  const navigate = useNavigate()
  const rootRef = useRef<HTMLDivElement>(null)
  const readFiredRef = useRef(false)
  const token = item?.impression_token

  // Impression once per mount (server dedupes by token).
  useEffect(() => {
    if (!token) return
    happyApi.postEvent({ impression_token: token, type: 'impression' }).catch(() => {})
  }, [token])

  // Read after ≥8s of continuous ≥50% visibility.
  useEffect(() => {
    if (!token) return
    const el = rootRef.current
    if (!el || typeof IntersectionObserver === 'undefined') return

    let timer: ReturnType<typeof setTimeout> | null = null
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
          if (!timer && !readFiredRef.current) {
            timer = setTimeout(() => {
              readFiredRef.current = true
              happyApi
                .postEvent({ impression_token: token, type: 'read', dwell_ms: READ_DWELL_MS })
                .catch(() => {})
            }, READ_DWELL_MS)
          }
        } else if (timer) {
          clearTimeout(timer)
          timer = null
        }
      },
      { threshold: [0, 0.5, 1] },
    )
    observer.observe(el)
    return () => {
      observer.disconnect()
      if (timer) clearTimeout(timer)
    }
  }, [token])

  if (!item) return null

  const handleClick = () => {
    happyApi.postEvent({ impression_token: item.impression_token, type: 'click' }).catch(() => {})
    if (item.cta?.href) navigate(item.cta.href)
  }

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation()
    happyApi.dismiss(item.id, item.impression_token).catch(() => {})
    happyApi.postEvent({ impression_token: item.impression_token, type: 'dismiss' }).catch(() => {})
    onDismiss?.(item.id)
  }

  return (
    <div ref={rootRef}>
      <Card className="group relative h-32 flex-row gap-0 overflow-hidden p-0">
        {item.media && (
          <div className="w-1/3 shrink-0">
            <img
              src={item.media.url}
              alt={item.media.alt}
              className="h-full w-full rounded-l-xl object-cover"
            />
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col justify-center gap-1 px-4 py-3">
          <span className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
            <Megaphone className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{item.kicker}</span>
          </span>

          <p className="truncate text-base font-semibold">{item.title}</p>

          {item.summary && (
            <p className="truncate text-sm text-muted-foreground">{item.summary}</p>
          )}

          <div className="flex items-center gap-2 pt-0.5">
            {item.event_at && <Badge variant="outline">{formatEventDate(item.event_at)}</Badge>}
            {item.cta && (
              <Button size="sm" className="ml-auto" onClick={handleClick}>
                {item.cta.label}
              </Button>
            )}
          </div>
        </div>

        {item.dismissible && (
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Închide"
            onClick={handleDismiss}
            className="absolute right-2 top-2 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </Card>
    </div>
  )
}

export default MarqueeCard
