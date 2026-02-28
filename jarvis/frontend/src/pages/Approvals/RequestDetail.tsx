import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, RotateCcw, Clock, ArrowUpRight, MessageSquare, ShieldAlert } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { approvalsApi } from '@/api/approvals'
import { usersApi } from '@/api/users'
import { toast } from 'sonner'
import type { ApprovalDecision, ApprovalAuditEntry, ApprovalStep } from '@/types/approvals'
import type { UserDetail } from '@/types/users'

interface RequestDetailProps {
  requestId: number
  open: boolean
  onClose: () => void
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  approved: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  returned: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  cancelled: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  expired: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
}

const DECISION_ICONS: Record<string, React.ElementType> = {
  approved: CheckCircle,
  rejected: XCircle,
  returned: RotateCcw,
  delegated: ArrowUpRight,
  abstained: Clock,
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('ro-RO', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function RequestDetail({ requestId, open, onClose }: RequestDetailProps) {
  const [comment, setComment] = useState('')
  const [showEscalateUser, setShowEscalateUser] = useState(false)
  const [escalateToUserId, setEscalateToUserId] = useState('')
  const queryClient = useQueryClient()

  const { data: detail, isLoading } = useQuery({
    queryKey: ['approval-request', requestId],
    queryFn: () => approvalsApi.getRequest(requestId),
    enabled: open,
  })

  const decideMutation = useMutation({
    mutationFn: (decision: string) =>
      approvalsApi.decide(requestId, { decision, comment: comment || undefined }),
    onSuccess: () => {
      toast.success('Decision recorded')
      setComment('')
      queryClient.invalidateQueries({ queryKey: ['approval-queue'] })
      queryClient.invalidateQueries({ queryKey: ['approval-queue-count'] })
      queryClient.invalidateQueries({ queryKey: ['approval-my-requests'] })
      queryClient.invalidateQueries({ queryKey: ['approval-all-requests'] })
      queryClient.invalidateQueries({ queryKey: ['approval-request', requestId] })
      onClose()
    },
    onError: () => toast.error('Failed to record decision'),
  })

  const cancelMutation = useMutation({
    mutationFn: () => approvalsApi.cancel(requestId, comment || undefined),
    onSuccess: () => {
      toast.success('Request cancelled')
      queryClient.invalidateQueries({ queryKey: ['approval-queue'] })
      queryClient.invalidateQueries({ queryKey: ['approval-queue-count'] })
      queryClient.invalidateQueries({ queryKey: ['approval-my-requests'] })
      queryClient.invalidateQueries({ queryKey: ['approval-all-requests'] })
      onClose()
    },
    onError: () => toast.error('Failed to cancel request'),
  })

  const { data: usersData } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    enabled: showEscalateUser,
  })
  const users: UserDetail[] = (usersData as UserDetail[] | undefined) ?? []

  const escalateMutation = useMutation({
    mutationFn: (escalateTo?: number) =>
      approvalsApi.escalate(requestId, {
        reason: comment || 'manual',
        escalate_to: escalateTo,
      }),
    onSuccess: () => {
      toast.success('Request escalated')
      setShowEscalateUser(false)
      setEscalateToUserId('')
      queryClient.invalidateQueries({ queryKey: ['approval-queue'] })
      queryClient.invalidateQueries({ queryKey: ['approval-queue-count'] })
      queryClient.invalidateQueries({ queryKey: ['approval-request', requestId] })
    },
    onError: (err: unknown) => {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Failed to escalate'
      toast.error(msg)
    },
  })

  const currentUser = useAuthStore((s) => s.user)
  const isPending = detail?.status === 'pending'
  const isOwnRequest = detail?.requested_by?.id === currentUser?.id
  const ctx = detail?.context_snapshot || {}
  const title = (ctx.title as string) || `${detail?.entity_type}/${detail?.entity_id}`

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {title}
            {detail && (
              <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', STATUS_STYLES[detail.status] || '')}>
                {detail.status}
              </span>
            )}
          </DialogTitle>
          <DialogDescription>
            {detail ? `${detail.entity_type} #${detail.entity_id} — Flow: ${detail.flow_name || 'N/A'}` : 'Loading...'}
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3 py-4">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : detail ? (
          <div className="space-y-4 py-2">
            {/* Info grid */}
            <div className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">Requester:</span>{' '}
                <span className="font-medium">{detail.requested_by?.name || '—'}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Priority:</span>{' '}
                <span className={cn('font-medium', detail.priority === 'urgent' && 'text-red-600 dark:text-red-400', detail.priority === 'high' && 'text-orange-600 dark:text-orange-400')}>
                  {detail.priority}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Submitted:</span>{' '}
                {formatDate(detail.requested_at)}
              </div>
              <div>
                <span className="text-muted-foreground">Due:</span>{' '}
                {formatDate(detail.due_by)}
              </div>
              {detail.current_step_name && (
                <div className="col-span-2">
                  <span className="text-muted-foreground">Current Step:</span>{' '}
                  <span className="font-medium">{detail.current_step_name}</span>
                </div>
              )}
              {detail.resolution_note && (
                <div className="col-span-2">
                  <span className="text-muted-foreground">Resolution:</span>{' '}
                  {detail.resolution_note}
                </div>
              )}
            </div>

            {/* Context snapshot */}
            {Object.keys(ctx).length > 0 && (
              <>
                <Separator />
                <div>
                  <h4 className="mb-2 text-sm font-medium">Context</h4>
                  <div className="rounded-md bg-muted/50 p-3 text-sm">
                    {Object.entries(ctx).map(([key, value]) => (
                      <div key={key} className="flex justify-between py-0.5">
                        <span className="text-muted-foreground">{key}:</span>
                        <span className="font-medium">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* Steps progress */}
            {detail.steps && detail.steps.length > 0 && (
              <>
                <Separator />
                <div>
                  <h4 className="mb-2 text-sm font-medium">Steps</h4>
                  <div className="flex gap-2">
                    {detail.steps
                      .sort((a, b) => (a.step_order ?? 0) - (b.step_order ?? 0))
                      .map((step: ApprovalStep) => {
                        const isCurrentStep = step.id === detail.current_step_id
                        const stepDecisions = detail.decisions.filter(d => d.step_id === step.id)
                        const isDone = stepDecisions.some(d => d.decision === 'approved')
                        return (
                          <div
                            key={step.id}
                            className={cn(
                              'flex-1 rounded-md border p-2 text-center text-xs',
                              isCurrentStep && 'border-primary bg-primary/10',
                              isDone && 'border-green-500 bg-green-50 dark:bg-green-900/20',
                            )}
                          >
                            <div className="font-medium">{step.name}</div>
                            <div className="text-muted-foreground">
                              {isDone ? 'Done' : isCurrentStep ? 'Current' : 'Pending'}
                            </div>
                          </div>
                        )
                      })}
                  </div>
                </div>
              </>
            )}

            {/* Decisions timeline */}
            {detail.decisions && detail.decisions.length > 0 && (
              <>
                <Separator />
                <div>
                  <h4 className="mb-2 text-sm font-medium">Decisions</h4>
                  <div className="space-y-2">
                    {detail.decisions.map((d: ApprovalDecision) => {
                      const Icon = DECISION_ICONS[d.decision] || Clock
                      return (
                        <div key={d.id} className="flex items-start gap-2 rounded-md border p-2">
                          <Icon className={cn('mt-0.5 h-4 w-4 shrink-0',
                            d.decision === 'approved' && 'text-green-600',
                            d.decision === 'rejected' && 'text-red-600',
                            d.decision === 'returned' && 'text-blue-600',
                          )} />
                          <div className="min-w-0 flex-1 text-sm">
                            <div className="flex items-center justify-between">
                              <span className="font-medium">{d.decided_by?.name || 'Unknown'}</span>
                              <span className="text-xs text-muted-foreground">{formatDate(d.decided_at)}</span>
                            </div>
                            <div className="text-muted-foreground">
                              <Badge variant="outline" className="mr-1 text-xs">{d.decision}</Badge>
                              {d.step_name && <span>on {d.step_name}</span>}
                            </div>
                            {d.comment && (
                              <p className="mt-1 text-muted-foreground">{d.comment}</p>
                            )}
                            {d.delegated_to && (
                              <p className="mt-1 text-xs text-muted-foreground">
                                Delegated to: {d.delegated_to.name}
                              </p>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </>
            )}

            {/* Audit log */}
            {detail.audit && detail.audit.length > 0 && (
              <>
                <Separator />
                <div>
                  <h4 className="mb-2 text-sm font-medium">Audit Trail</h4>
                  <div className="space-y-1">
                    {detail.audit.map((a: ApprovalAuditEntry) => (
                      <div key={a.id} className="flex items-center justify-between text-xs">
                        <span>
                          <span className="font-medium">{a.actor_name || 'System'}</span>
                          {' '}
                          <span className="text-muted-foreground">{a.action}</span>
                        </span>
                        <span className="text-muted-foreground">{formatDate(a.created_at)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* Self-approval warning */}
            {isPending && isOwnRequest && (
              <>
                <Separator />
                <div className="flex items-center gap-2 rounded-md border border-yellow-300 bg-yellow-50 p-3 text-sm dark:border-yellow-700 dark:bg-yellow-900/20">
                  <ShieldAlert className="h-4 w-4 shrink-0 text-yellow-600 dark:text-yellow-400" />
                  <span className="text-yellow-800 dark:text-yellow-300">You cannot approve your own request. Another approver must review it.</span>
                </div>
              </>
            )}

            {/* Action area */}
            {isPending && !isOwnRequest && (
              <>
                <Separator />
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Comment</span>
                  </div>
                  <Textarea
                    placeholder="Add a comment (required for reject/return)..."
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    rows={2}
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      onClick={() => decideMutation.mutate('approved')}
                      disabled={decideMutation.isPending}
                    >
                      <CheckCircle className="mr-1.5 h-4 w-4" />
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => decideMutation.mutate('rejected')}
                      disabled={decideMutation.isPending || !comment.trim()}
                    >
                      <XCircle className="mr-1.5 h-4 w-4" />
                      Reject
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => decideMutation.mutate('returned')}
                      disabled={decideMutation.isPending || !comment.trim()}
                    >
                      <RotateCcw className="mr-1.5 h-4 w-4" />
                      Return
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setShowEscalateUser(!showEscalateUser)}
                      disabled={escalateMutation.isPending}
                    >
                      <ArrowUpRight className="mr-1.5 h-4 w-4" />
                      Escalate
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => cancelMutation.mutate()}
                      disabled={cancelMutation.isPending}
                    >
                      Cancel Request
                    </Button>
                  </div>

                  {/* Escalation user picker */}
                  {showEscalateUser && (
                    <div className="flex items-center gap-2 rounded-md border bg-muted/30 p-3">
                      <select
                        className="flex-1 rounded-md border bg-background px-3 py-1.5 text-sm"
                        value={escalateToUserId}
                        onChange={(e) => setEscalateToUserId(e.target.value)}
                      >
                        <option value="">Select user to escalate to...</option>
                        {users.filter(u => u.is_active).map(u => (
                          <option key={u.id} value={u.id}>{u.name} ({u.role_name})</option>
                        ))}
                      </select>
                      <Button
                        size="sm"
                        onClick={() => escalateMutation.mutate(Number(escalateToUserId))}
                        disabled={!escalateToUserId || escalateMutation.isPending}
                      >
                        Confirm
                      </Button>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
