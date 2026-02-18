import { AlertCircle, RefreshCw } from 'lucide-react'
import { Button } from './ui/button'

interface QueryErrorProps {
  message?: string
  onRetry?: () => void
}

export function QueryError({ message = 'Failed to load data', onRetry }: QueryErrorProps) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      <AlertCircle className="size-4 shrink-0" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-destructive hover:text-destructive" onClick={onRetry}>
          <RefreshCw className="size-3.5" />
          Retry
        </Button>
      )}
    </div>
  )
}
