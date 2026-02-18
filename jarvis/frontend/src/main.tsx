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
