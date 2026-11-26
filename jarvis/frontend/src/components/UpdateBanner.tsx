import { useEffect, useState } from 'react'
import { RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useVersionCheck } from '@/hooks/useVersionCheck'

// Slim top banner shown when a newer frontend build has shipped while this tab
// stayed open. Manual reload only — never auto-reload — so a half-filled form is
// never lost (the whole reason this exists). Dismiss hides it; it re-surfaces
// the next time the tab regains focus while the update is still pending.
export function UpdateBanner() {
  const updateAvailable = useVersionCheck()
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') setDismissed(false)
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [])

  if (!updateAvailable || dismissed) return null

  return (
    <div
      role="status"
      className="fixed inset-x-0 top-0 z-[100] flex items-center justify-center gap-3 bg-primary px-4 py-2 text-sm text-primary-foreground shadow-md"
    >
      <RefreshCw className="h-4 w-4 shrink-0" />
      <span>Versiune nouă disponibilă</span>
      <Button
        size="sm"
        variant="secondary"
        className="h-7"
        onClick={() => window.location.reload()}
      >
        Reîncarcă
      </Button>
      <button
        type="button"
        aria-label="Închide"
        className="absolute right-3 top-1/2 -translate-y-1/2 opacity-80 hover:opacity-100"
        onClick={() => setDismissed(true)}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
