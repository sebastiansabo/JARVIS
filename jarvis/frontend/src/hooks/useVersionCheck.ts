import { useEffect, useState } from 'react'
import { CURRENT_BUILD, fetchServerBuild, isNewerBuild } from '@/lib/versionCheck'

// How often an active tab re-checks the served build id. Mirrors the existing
// 10-min /health keep-alive cadence in main.tsx, a bit tighter so a deploy is
// noticed within a couple of minutes of the user returning to the tab.
const POLL_MS = 120_000

// Returns true once a newer frontend build has been detected for this tab.
// Latches on (never flips back) — the only cure for a stale tab is a reload,
// which this just signals; UpdateBanner turns it into a prompt. Checks on
// mount, on a steady interval, and whenever the tab regains visibility (the
// moment a returning user is most likely sitting on stale code).
export function useVersionCheck(): boolean {
  const [updateAvailable, setUpdateAvailable] = useState(false)

  useEffect(() => {
    let cancelled = false

    const check = async () => {
      const server = await fetchServerBuild()
      if (!cancelled && isNewerBuild(CURRENT_BUILD, server)) {
        setUpdateAvailable(true)
      }
    }

    const onVisible = () => {
      if (document.visibilityState === 'visible') check()
    }

    check()
    const interval = window.setInterval(check, POLL_MS)
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      cancelled = true
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  return updateAvailable
}
