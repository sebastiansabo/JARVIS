/**
 * TelemetryProvider — React wrapper that auto-tracks page views and session lifecycle.
 *
 * Wrap your app with this component inside BrowserRouter:
 *   <BrowserRouter>
 *     <TelemetryProvider>
 *       <App />
 *     </TelemetryProvider>
 *   </BrowserRouter>
 */

import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { telemetry } from '@/lib/telemetry'

export function TelemetryProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const prevPath = useRef<string | null>(null)
  const pageEnteredAt = useRef<number>(Date.now())

  // Initialize telemetry only when authenticated, destroy on logout/unmount
  useEffect(() => {
    if (!user) return
    telemetry.init()
    return () => telemetry.destroy()
  }, [user])

  // Track page views on route changes (only when authenticated)
  useEffect(() => {
    if (!user) return

    const currentPath = location.pathname
    const now = Date.now()
    const durationMs = prevPath.current !== null ? now - pageEnteredAt.current : null

    telemetry.pageView(
      currentPath,
      document.title,
      prevPath.current,
      durationMs,
    )

    prevPath.current = currentPath
    pageEnteredAt.current = now
  }, [location.pathname, user])

  return <>{children}</>
}
