import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardCheck, Clock, CheckCircle, XCircle, RotateCcw, Send, ChevronDown, ChevronRight, MessageSquare } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { approvalsApi } from '@/api/approvals'
import { usersApi } from '@/api/users'
import { useAuth } from '@/hooks/useAuth'
import { toast } from 'sonner'
import type { ApprovalRequest, ApprovalRequestDetail, ApprovalDecision } from '@/types/approvals'

interface ApprovalWidgetProps {
  entityType: string
  entityId: number
  context?: Record<string, unknown>
  className?: string
  compact?: boolean
  /** Show a user picker for selecting the approver */
  showApproverPicker?: boolean
  /** Custom submit handler — overrides default approvalsApi.submit() */
  onSubmit?: (opts: { approverId?: number; note?: string }) => Promise<unknown>
}

const STATUS_CONFIG: Record<string, { label: string; icon: React.ElementType; className: string }> = {
  pending: { label: 'Pending Approval', icon: Clock, className: 'text-yellow-600 dark:text-yellow-400' },
  approved: { label: 'Approved', icon: CheckCircle, className: 'text-green-600 dark:text-green-400' },
  rejected: { label: 'Rejected', icon: XCircle, className: 'text-red-600 dark:text-red-400' },
  returned: { label: 'Returned', icon: RotateCcw, className: 'text-blue-600 dark:text-blue-400' },
  cancelled: { label: 'Cancelled', icon: XCircle, className: 'text-muted-foreground' },
  expired: { label: 'Expired', icon: Clock, className: 'text-red-600 dark:text-red-400' },
}

export function ApprovalWidget({ entityType, entityId, context, className, compact = false, showApproverPicker = false, onSubmit }: ApprovalWidgetProps) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [showSubmit, setShowSubmit] = useState(false)
  const [note, setNote] = useState('')
  const [approverId, setApproverId] = useState<number | undefined>()
  const [expanded, setExpanded] = useState(false)
  const [decisionAction, setDecisionAction] = useState<'approved' | 'rejected' | 'returned' | null>(null)
  const [decisionComment, setDecisionComment] = useState('')

  const { data: historyData, isLoading } = useQuery({
    queryKey: ['approval-entity-history', entityType, entityId],
    queryFn: () => approvalsApi.getEntityHistory(entityType, entityId),
  })

  const history = historyData?.history ?? []
  const latestRequest = history[0] as ApprovalRequest | undefined
  const hasPending = history.some((r: ApprovalRequest) => r.status === 'pending')
  const pendingRequest = history.find((r: ApprovalRequest) => r.status === 'pending') as ApprovalRequest | undefined

  // Check if current user is an approver for the pending request
  const { data: queueData } = useQuery({
    queryKey: ['approval-queue'],
    queryFn: () => approvalsApi.getMyQueue(),
    enabled: !!pendingRequest,
  })
  const isApprover = !!pendingRequest && (queueData?.queue ?? []).some(
    (q) => q.entity_type === entityType && q.entity_id === entityId,
  )

  // Fetch request detail for decisions (comments, who decided)
  const { data: requestDetail } = useQuery({
    queryKey: ['approval-request', latestRequest?.id],
    queryFn: () => approvalsApi.getRequest(latestRequest!.id),
    enabled: !!latestRequest,
  })

  // Fetch users when approver picker is needed
  const { data: users } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    enabled: showApproverPicker && showSubmit,
  })

  // Reset forms when closed
  useEffect(() => {
    if (!showSubmit) { setApproverId(undefined); setNote('') }
  }, [showSubmit])

  useEffect(() => {
    if (!decisionAction) setDecisionComment('')
  }, [decisionAction])

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (onSubmit) {
        return onSubmit({ approverId, note: note || undefined })
      }
      const ctx = { ...context }
      if (approverId) ctx.approver_user_id = approverId
      return approvalsApi.submit({
        entity_type: entityType,
        entity_id: entityId,
        context: ctx,
        note: note || undefined,
      })
    },
    onSuccess: () => {
      toast.success('Submitted for approval')
      setShowSubmit(false)
      setNote('')
      setApproverId(undefined)
      _invalidateAll()
    },
    onError: (err: unknown) => {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Failed to submit'
      toast.error(msg)
    },
  })

  const decideMutation = useMutation({
    mutationFn: async ({ decision, comment }: { decision: string; comment: string }) => {
      return approvalsApi.decide(pendingRequest!.id, { decision, comment: comment || undefined })
    },
    onSuccess: (_data, vars) => {
      const labels: Record<string, string> = { approved: 'Approved', rejected: 'Rejected', returned: 'Returned' }
      toast.success(labels[vars.decision] || 'Decision recorded')
      setDecisionAction(null)
      setDecisionComment('')
      _invalidateAll()
    },
    onError: (err: unknown) => {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Failed to record decision'
      toast.error(msg)
    },
  })

  const resubmitMutation = useMutation({
    mutationFn: async () => {
      return approvalsApi.resubmit(latestRequest!.id, context)
    },
    onSuccess: () => {
      toast.success('Resubmitted for approval')
      _invalidateAll()
    },
    onError: (err: unknown) => {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Failed to resubmit'
      toast.error(msg)
    },
  })

  function _invalidateAll() {
    queryClient.invalidateQueries({ queryKey: ['approval-entity-history', entityType, entityId] })
    queryClient.invalidateQueries({ queryKey: ['approval-queue'] })
    queryClient.invalidateQueries({ queryKey: ['approval-queue-count'] })
    queryClient.invalidateQueries({ queryKey: ['approval-request', latestRequest?.id] })
    queryClient.invalidateQueries({ queryKey: ['mkt-project', entityId] })
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }

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

  const canSubmit = !showApproverPicker || !!approverId
  const canResubmit = latestRequest && (latestRequest.status === 'returned' || latestRequest.status === 'rejected')
    && latestRequest.requested_by?.id === user?.id
  const decisions = (requestDetail as ApprovalRequestDetail | undefined)?.decisions ?? []
  const latestDecision = decisions[0] as ApprovalDecision | undefined

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <ClipboardCheck className="h-4 w-4" />
          Approval
        </div>
        {!hasPending && !canResubmit && (
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
        {canResubmit && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => resubmitMutation.mutate()}
            disabled={resubmitMutation.isPending}
          >
            <Send className="mr-1 h-3 w-3" />
            Resubmit
          </Button>
        )}
      </div>

      {/* Submit form */}
      {showSubmit && (
        <div className="space-y-2 rounded-md border p-3">
          {showApproverPicker && (
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Approver *</label>
              <select
                className="w-full rounded-md border bg-background px-3 py-1.5 text-sm"
                value={approverId ?? ''}
                onChange={(e) => setApproverId(e.target.value ? Number(e.target.value) : undefined)}
              >
                <option value="">Select approver...</option>
                {(users ?? []).map((u) => (
                  <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
                ))}
              </select>
            </div>
          )}
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
              disabled={submitMutation.isPending || !canSubmit}
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

      {/* Decision comment — shown prominently for returned/rejected */}
      {latestDecision && (latestRequest?.status === 'returned' || latestRequest?.status === 'rejected') && (
        <div className={cn(
          'rounded-md border p-3 text-sm',
          latestRequest.status === 'returned' ? 'border-blue-300 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-950/20' : 'border-red-300 bg-red-50/50 dark:border-red-800 dark:bg-red-950/20',
        )}>
          <div className="flex items-start gap-2">
            <MessageSquare className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              {latestDecision.comment && (
                <p className="italic">&ldquo;{latestDecision.comment}&rdquo;</p>
              )}
              {latestRequest.resolution_note && !latestDecision.comment && (
                <p className="italic">&ldquo;{latestRequest.resolution_note}&rdquo;</p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                &mdash; {latestDecision.decided_by?.name ?? 'Unknown'}
                {latestDecision.decided_at && (
                  <>, {new Date(latestDecision.decided_at).toLocaleDateString('ro-RO')}</>
                )}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Approver actions — only when user is an approver for a pending request */}
      {isApprover && pendingRequest && (
        <div className="space-y-2">
          {!decisionAction && (
            <div className="flex gap-2">
              <Button
                size="sm"
                className="bg-green-600 hover:bg-green-700 text-white"
                onClick={() => setDecisionAction('approved')}
              >
                <CheckCircle className="mr-1 h-3.5 w-3.5" />
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="border-blue-400 text-blue-600 hover:bg-blue-50 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-950"
                onClick={() => setDecisionAction('returned')}
              >
                <RotateCcw className="mr-1 h-3.5 w-3.5" />
                Return
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="border-red-400 text-red-600 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-950"
                onClick={() => setDecisionAction('rejected')}
              >
                <XCircle className="mr-1 h-3.5 w-3.5" />
                Reject
              </Button>
            </div>
          )}

          {decisionAction && (
            <div className={cn(
              'rounded-md border p-3 space-y-2',
              decisionAction === 'approved' && 'border-green-300 dark:border-green-800',
              decisionAction === 'returned' && 'border-blue-300 dark:border-blue-800',
              decisionAction === 'rejected' && 'border-red-300 dark:border-red-800',
            )}>
              <p className="text-xs font-medium">
                {decisionAction === 'approved' && 'Approve this request'}
                {decisionAction === 'returned' && 'Return for changes'}
                {decisionAction === 'rejected' && 'Reject this request'}
              </p>
              <Textarea
                placeholder={decisionAction === 'approved' ? 'Add a comment (optional)...' : 'Reason (required)...'}
                value={decisionComment}
                onChange={(e) => setDecisionComment(e.target.value)}
                rows={2}
                className="text-sm"
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant={decisionAction === 'rejected' ? 'destructive' : 'default'}
                  className={decisionAction === 'approved' ? 'bg-green-600 hover:bg-green-700 text-white' : undefined}
                  onClick={() => decideMutation.mutate({ decision: decisionAction, comment: decisionComment })}
                  disabled={decideMutation.isPending || (decisionAction !== 'approved' && !decisionComment.trim())}
                >
                  Confirm
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDecisionAction(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Decision history */}
      {decisions.length > 0 && latestRequest?.status !== 'returned' && latestRequest?.status !== 'rejected' && (
        <div className="space-y-1">
          {decisions.map((d: ApprovalDecision) => (
            <DecisionLine key={d.id} decision={d} />
          ))}
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

function DecisionLine({ decision }: { decision: ApprovalDecision }) {
  const label = decision.decision === 'approved' ? 'Approved' : decision.decision === 'rejected' ? 'Rejected' : decision.decision === 'returned' ? 'Returned' : decision.decision
  const color = decision.decision === 'approved' ? 'text-green-600 dark:text-green-400' : decision.decision === 'rejected' ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400'
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className={cn('font-medium', color)}>{label}</span>
      <span>by {decision.decided_by?.name ?? 'Unknown'}</span>
      {decision.comment && <span className="italic truncate max-w-[200px]">&ldquo;{decision.comment}&rdquo;</span>}
      {decision.decided_at && <span>{new Date(decision.decided_at).toLocaleDateString('ro-RO')}</span>}
    </div>
  )
}
