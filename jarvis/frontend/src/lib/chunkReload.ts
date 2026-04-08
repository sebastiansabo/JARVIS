// Auto-reload helper for stale-bundle errors after a deploy.
//
// Vite emits content-hashed chunk filenames. When we deploy a new build, the
// user's still-running tab keeps its old `index-OLDHASH.js` in memory and tries
// to lazy-load chunks with the OLD hash — those files no longer exist on the
// server, so the dynamic import throws "Importing a module script failed" /
// "Failed to fetch dynamically imported module".
//
// We detect those specific errors and force a reload with a cache-busting
// query param so the browser bypasses its HTTP disk cache and pulls the fresh
// `index.html` (and therefore the fresh chunk filenames).
//
// To prevent reload loops we use a session-scoped attempt counter:
//   - 1st failure: silent reload with `?_v=<ts>`
//   - 2nd failure: same, in case the first reload still hit a stale cache
//   - 3rd+ failure: give up and let the ErrorBoundary UI show

const ATTEMPT_KEY = 'chunk_reload_attempt'
const MAX_ATTEMPTS = 2

export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false
  const msg = error.message || ''
  return (
    msg.includes('Importing a module script failed') ||
    msg.includes('Failed to fetch dynamically imported module') ||
    msg.includes('error loading dynamically imported module') ||
    msg.includes('Unable to preload CSS') ||
    // Some browsers report a generic TypeError for the same condition
    (error.name === 'TypeError' && msg.includes('dynamically imported'))
  )
}

/**
 * Attempt a cache-busted reload. Returns true if a reload was scheduled,
 * false if we've exceeded MAX_ATTEMPTS and the caller should fall back to
 * showing an error UI.
 */
export function tryChunkReload(): boolean {
  let attempts = 0
  try {
    attempts = parseInt(sessionStorage.getItem(ATTEMPT_KEY) || '0', 10) || 0
  } catch {
    // sessionStorage may be unavailable (private mode, sandboxed iframes)
  }

  if (attempts >= MAX_ATTEMPTS) {
    return false
  }

  try {
    sessionStorage.setItem(ATTEMPT_KEY, String(attempts + 1))
  } catch {
    // ignore
  }

  // Bust both browser HTTP cache and any intermediate proxy by injecting a
  // unique query param. Use replace() so the cache-busted URL doesn't pollute
  // the back/forward history.
  const url = new URL(window.location.href)
  url.searchParams.set('_v', String(Date.now()))
  window.location.replace(url.toString())
  return true
}

/**
 * Clear the attempt counter once the app has booted successfully. Called once
 * from main.tsx after the React tree mounts so that future deploys get a
 * fresh attempt budget.
 */
export function resetChunkReloadAttempts(): void {
  try {
    sessionStorage.removeItem(ATTEMPT_KEY)
  } catch {
    // ignore
  }
  // Also strip the cache-busting query param from the URL so it doesn't
  // linger in bookmarks / shares.
  try {
    const url = new URL(window.location.href)
    if (url.searchParams.has('_v')) {
      url.searchParams.delete('_v')
      window.history.replaceState({}, '', url.toString())
    }
  } catch {
    // ignore
  }
}
