import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { toast } from 'sonner'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import './index.css'

function extractErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'data' in error) {
    const data = (error as { data: unknown }).data
    if (data && typeof data === 'object' && 'error' in data) {
      return (data as { error: string }).error
    }
  }
  if (error instanceof Error) return error.message
  return 'An unexpected error occurred'
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
  queryCache: new QueryCache({
    onError: (error, query) => {
      // Skip 401s (handled by api client redirect)
      if (error && typeof error === 'object' && 'status' in error && (error as { status: number }).status === 401) return
      // Only toast for queries that already had data (background refetch failures)
      // Fresh loads show inline QueryError instead
      if (query.state.data !== undefined) {
        toast.error(extractErrorMessage(error))
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      // Skip if mutation has its own onError handler
      if (mutation.options.onError) return
      // Skip 401s
      if (error && typeof error === 'object' && 'status' in error && (error as { status: number }).status === 401) return
      toast.error(extractErrorMessage(error))
    },
  }),
})

// Keep-alive ping every 10 minutes to prevent DO App Platform cold starts
setInterval(() => { fetch('/health').catch(() => {}) }, 10 * 60 * 1000)

// Chunk-load failure handler — after a deploy, lazy-loaded route chunks get new
// content-hash filenames. If the user had the app open, React Router navigates
// without a full reload and tries to fetch the old hash → 404. Detect that and
// force one reload so the browser picks up the fresh index.html + new chunks.
window.addEventListener('unhandledrejection', (event) => {
  const err = event.reason
  if (
    err instanceof TypeError && (
      err.message.includes('Importing a module script failed') ||
      err.message.includes('Failed to fetch') ||
      err.message.includes('dynamically imported module') ||
      err.message.includes('Unable to preload CSS')
    )
  ) {
    const key = 'chunk_reload_at'
    const last = sessionStorage.getItem(key)
    const now = Date.now()
    if (!last || now - parseInt(last) > 15_000) {
      sessionStorage.setItem(key, String(now))
      window.location.reload()
    }
  }
})

// Console easter egg
console.log(
  '%c' +
  '     _   _   ___  __   __ ___  ___  \n' +
  '  _ | | /_\\ | _ \\ \\ \\ / /|_ _|/ __| \n' +
  ' | || |/ _ \\|   /  \\ V /  | | \\__ \\ \n' +
  '  \\__//_/ \\_\\_|_\\   \\_/  |___||___/ \n',
  'color: #6366f1; font-weight: bold; font-size: 12px;',
)
console.log(
  '%cBuilt with %c♥%c by Sebastian',
  'color: #94a3b8; font-size: 11px;',
  'color: #ef4444; font-size: 11px;',
  'color: #94a3b8; font-size: 11px;',
)
console.log(
  '%cHint: There are easter eggs hidden in this app. Good luck finding them all.',
  'color: #64748b; font-style: italic; font-size: 10px;',
)

// Konami code easter egg: ↑↑↓↓←→←→BA
;(() => {
  const seq = ['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a']
  let idx = 0
  document.addEventListener('keydown', (e) => {
    if (e.key === seq[idx]) { idx++ } else { idx = e.key === seq[0] ? 1 : 0 }
    if (idx === seq.length) {
      idx = 0
      const el = document.createElement('div')
      el.innerHTML = `
        <div style="position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.85);cursor:pointer;animation:fadeIn .3s ease" onclick="this.remove()">
          <div style="text-align:center;color:white;font-family:system-ui;max-width:420px;padding:2rem">
            <div style="font-size:3rem;margin-bottom:1rem">🤖</div>
            <div style="font-size:1.5rem;font-weight:700;margin-bottom:.5rem;background:linear-gradient(135deg,#6366f1,#a855f7,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent">J.A.R.V.I.S.</div>
            <div style="font-size:.95rem;color:#94a3b8;line-height:1.6;margin-bottom:1rem">
              <b>J</b>ust <b>A</b>nother <b>R</b>eally <b>V</b>ery <b>I</b>ntelligent <b>S</b>ystem<br/>
              <span style="font-size:.8rem;color:#64748b;font-style:italic">...or as Seba calls it: "Seba's Veeeery Intelligent System"</span>
            </div>
            <div style="font-size:.8rem;color:#475569;margin-top:1rem">Crafted with ♥ by Sebastian</div>
            <div style="font-size:.7rem;color:#334155;margin-top:.5rem">Click anywhere to dismiss</div>
          </div>
        </div>
      `
      document.body.appendChild(el)
    }
  })
})()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
