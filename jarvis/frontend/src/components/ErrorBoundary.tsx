import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack)
    // Auto-reload on chunk-load failures (stale cache after deploy)
    if (
      error instanceof TypeError && (
        error.message.includes('Importing a module script failed') ||
        error.message.includes('Failed to fetch') ||
        error.message.includes('dynamically imported module') ||
        error.message.includes('Unable to preload CSS')
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
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[50vh] items-center justify-center p-8">
          <div className="max-w-md space-y-4 text-center">
            <h2 className="text-lg font-semibold">Something went wrong</h2>
            <p className="text-sm text-muted-foreground">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <div className="flex justify-center gap-3">
              <button
                onClick={() => this.setState({ hasError: false, error: null })}
                className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent"
              >
                Try Again
              </button>
              <button
                onClick={() => window.location.assign('/app/dashboard')}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                Go to Dashboard
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
