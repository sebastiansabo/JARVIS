import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { happyApi } from '@/api/happy'
import { SpotlightDialog } from './SpotlightDialog'
import type { HappySurfaceItem } from '@/types/happy'

/** Routes where an interstitial may interrupt — never mid-task. See §5.2. */
const ELIGIBLE_ROUTES = new Set(['/app/hub', '/app/dashboard'])

/** Delay after a route settles before we even ask for a Spotlight (§5.2: first 3s blocked). */
const MOUNT_DELAY_MS = 3_000

/** Dwell after which an open interstitial counts as read (§4/§6.4). */
const READ_DWELL_MS = 8_000

// At most one Spotlight per browser session — module scope, no localStorage.
let shownThisSession = false

/**
 * Mounts once in the authenticated app tree. On navigation to an eligible route
 * it waits 3s, asks the resolver for one interstitial, and renders the Spotlight.
 * All show/read/interaction telemetry is fired here; the dialog stays presentational.
 */
export function SpotlightProvider() {
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [item, setItem] = useState<HappySurfaceItem | null>(null)
  const [open, setOpen] = useState(false)
  const readTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (shownThisSession) return
    if (!ELIGIBLE_ROUTES.has(location.pathname)) return

    let cancelled = false
    const path = location.pathname

    const delay = setTimeout(async () => {
      try {
        const res = await happyApi.getSurface('interstitial', path)
        const first = res.items?.[0]
        if (cancelled || !first || shownThisSession) return

        shownThisSession = true
        setItem(first)
        setOpen(true)

        happyApi
          .postEvent({ impression_token: first.impression_token, type: 'impression' })
          .catch(() => {})

        readTimerRef.current = setTimeout(() => {
          happyApi
            .postEvent({ impression_token: first.impression_token, type: 'read', dwell_ms: READ_DWELL_MS })
            .catch(() => {})
        }, READ_DWELL_MS)
      } catch {
        /* surface unavailable — silently skip */
      }
    }, MOUNT_DELAY_MS)

    return () => {
      cancelled = true
      clearTimeout(delay)
    }
  }, [location.pathname])

  // Clear any pending read timer on unmount.
  useEffect(() => () => {
    if (readTimerRef.current) clearTimeout(readTimerRef.current)
  }, [])

  if (!item) return null

  const close = () => {
    setOpen(false)
    if (readTimerRef.current) clearTimeout(readTimerRef.current)
  }

  const handleCta = () => {
    happyApi.postEvent({ impression_token: item.impression_token, type: 'click' }).catch(() => {})
    close()
    if (item.cta?.href) navigate(item.cta.href)
  }

  const handleAck = () => {
    happyApi.ack(item.id, item.impression_token, 'interstitial').catch(() => {})
    close()
    queryClient.invalidateQueries({ queryKey: ['happy'] })
  }

  const handleSnooze = () => {
    happyApi.snooze(item.id, item.impression_token).catch(() => {})
    close()
  }

  const handleDismiss = () => {
    happyApi.dismiss(item.id, item.impression_token).catch(() => {})
    close()
  }

  return (
    <SpotlightDialog
      item={item}
      open={open}
      onOpenChange={(next) => {
        // Close attempts (X, Esc, outside click) map to a dismiss — but only
        // when the campaign allows it; non-dismissible content stays put.
        if (!next && item.dismissible) handleDismiss()
      }}
      onCta={handleCta}
      onAck={handleAck}
      onSnooze={handleSnooze}
    />
  )
}

export default SpotlightProvider
