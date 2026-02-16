import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardCheck, Clock, CheckCircle, XCircle, RotateCcw, Send, ChevronDown, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { approvalsApi } from '@/api/approvals'
import { toast } from 'sonner'
import type { ApprovalRequest } from '@/types/approvals'

interface ApprovalWidgetProps {
  entityType: string
  entityId: number
  context?: Record<string, unknown>
  className?: string
  compact?: boolean
}

const STATUS_CONFIG: Record<string, { label: string; icon: React.ElementType; className: string }> = {
  pending: { label: 'Pending Approval', icon: Clock, className: 'text-yellow-600 dark:text-yellow-400' },
  approved: { label: 'Approved', icon: CheckCircle, className: 'text-green-600 dark:text-green-400' },
  rejected: { label: 'Rejected', icon: XCircle, className: 'text-red-600 dark:text-red-400' },
  returned: { label: 'Returned', icon: RotateCcw, className: 'text-blue-600 dark:text-blue-400' },
  cancelled: { label: 'Cancelled', icon: XCircle, className: 'text-muted-foreground' },
  expired: { label: 'Expired', icon: Clock, className: 'text-red-600 dark:text-red-400' },
}

export function ApprovalWidget({ entityType, entityId, context, className, compact = false }: ApprovalWidgetProps) {
  const queryClient = useQueryClient()
  const [showSubmit, setShowSubmit] = useState(false)
  const [note, setNote] = useState('')
  const [expanded, setExpanded] = useState(false)

  const { data: historyData, isLoading } = useQuery({
    queryKey: ['approval-entity-history', entityType, entityId],
    queryFn: () => approvalsApi.getEntityHistory(entityType, entityId),
  })

  const submitMutation = useMutation({
    mutationFn: () => approvalsApi.submit({
      entity_type: entityType,
      entity_id: entityId,
      context,
      note: note || undefined,
    }),
    onSuccess: () => {
      toast.success('Submitted for approval')
      setShowSubmit(false)
      setNote('')
      queryClient.invalidateQueries({ queryKey: ['approval-entity-history', entityType, entityId] })
      queryClient.invalidateQueries({ queryKey: ['approval-queue'] })
      queryClient.invalidateQueries({ queryKey: ['approval-queue-count'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Failed to submit'
      toast.error(msg)
    },
  })

  const history = historyData?.history ?? []
  const latestRequest = history[0] as ApprovalRequest | undefined
  const hasPending = history.some((r: ApprovalRequest) => r.status === 'pending')

  if (isLoading) {
    return (
      <div className={cn('flex items-center gap-2 text-sm text-muted-foreground', className)}>
        <ClipboardCheck className="h-4 w-4 animate-pulse" />
        Loading approval status...
      </div>
    )
  }

  // Compact mode: single line badge
  if (compact) {
    if (!latestRequest) return null
    const config = STATUS_CONFIG[latestRequest.status] || STATUS_CONFIG.pending
    const Icon = config.icon
    return (
      <Badge variant="outline" className={cn('gap-1', config.className, className)}>
        <Icon className="h-3 w-3" />
        {config.label}
      </Badge>
    )
  }

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <ClipboardCheck className="h-4 w-4" />
          Approval
        </div>
        {!hasPending && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => setShowSubmit(!showSubmit)}
          >
            <Send className="mr-1 h-3 w-3" />
            Submit for Approval
          </Button>
        )}
      </div>

      {/* Submit form */}
      {showSubmit && (
        <div className="space-y-2 rounded-md border p-3">
          <Textarea
            placeholder="Add a note (optional)..."
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className="text-sm"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => submitMutation.mutate()}
              disabled={submitMutation.isPending}
            >
              Submit
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowSubmit(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Latest status */}
      {latestRequest && (
        <div className="rounded-md border p-2">
          <StatusLine request={latestRequest} />
        </div>
      )}

      {/* History (collapsible if >1) */}
      {history.length > 1 && (
        <div>
          <button
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {history.length - 1} previous request{history.length > 2 ? 's' : ''}
          </button>
          {expanded && (
            <div className="mt-1 space-y-1">
              {history.slice(1).map((req: ApprovalRequest) => (
                <div key={req.id} className="rounded-md border p-2 opacity-60">
                  <StatusLine request={req} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* No history */}
      {history.length === 0 && !showSubmit && (
        <p className="text-xs text-muted-foreground">No approval history for this item.</p>
      )}
    </div>
  )
}

function StatusLine({ request }: { request: ApprovalRequest }) {
  const config = STATUS_CONFIG[request.status] || STATUS_CONFIG.pending
  const Icon = config.icon
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <Icon className={cn('h-4 w-4', config.className)} />
        <span className={cn('font-medium', config.className)}>{config.label}</span>
        {request.flow_name && (
          <span className="text-xs text-muted-foreground">via {request.flow_name}</span>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {request.current_step_name && request.status === 'pending' && (
          <span>Step: {request.current_step_name}</span>
        )}
        {request.requested_at && (
          <span>{new Date(request.requested_at).toLocaleDateString('ro-RO')}</span>
        )}
      </div>
    </div>
  )
}
