import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle, XCircle, RotateCcw, Clock, ArrowUpRight, MessageSquare,
  ShieldAlert, TrendingUp, TrendingDown, Target, Calendar, Building2,
  Tag, Users, BarChart3, Layers,
} from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { approvalsApi } from '@/api/approvals'
import { marketingApi } from '@/api/marketing'
import { usersApi } from '@/api/users'
import { toast } from 'sonner'
import type { ApprovalDecision, ApprovalAuditEntry, ApprovalStep } from '@/types/approvals'
import type { MktProjectKpi } from '@/types/marketing'
import type { UserDetail } from '@/types/users'

interface RequestDetailProps {
  requestId: number
  open: boolean
  onClose: () => void
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  approved: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  on_hold: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  returned: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  cancelled: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  expired: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  in_progress: 'In Progress',
  approved: 'Approved',
  rejected: 'Rejected',
  on_hold: 'Returned for Changes',
  returned: 'Returned',
  cancelled: 'Cancelled',
  expired: 'Expired',
}

const DECISION_ICONS: Record<string, React.ElementType> = {
  approved: CheckCircle,
  rejected: XCircle,
  returned: RotateCcw,
  delegated: ArrowUpRight,
  abstained: Clock,
}

const KPI_STATUS_COLORS: Record<string, string> = {
  on_track: 'text-green-600 dark:text-green-400',
  exceeded: 'text-emerald-600 dark:text-emerald-400',
  at_risk: 'text-yellow-600 dark:text-yellow-400',
  behind: 'text-red-600 dark:text-red-400',
  no_data: 'text-gray-400 dark:text-gray-500',
}

const KPI_STATUS_BG: Record<string, string> = {
  on_track: 'bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-800',
  exceeded: 'bg-emerald-50 border-emerald-200 dark:bg-emerald-900/20 dark:border-emerald-800',
  at_risk: 'bg-yellow-50 border-yellow-200 dark:bg-yellow-900/20 dark:border-yellow-800',
  behind: 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800',
  no_data: 'bg-gray-50 border-gray-200 dark:bg-gray-900/20 dark:border-gray-700',
}

function formatDate(dateStr: string | null, short = false): string {
  if (!dateStr) return '—'
  if (short) {
    return new Date(dateStr).toLocaleDateString('ro-RO', {
      day: '2-digit', month: 'short', year: 'numeric',
    })
  }
  return new Date(dateStr).toLocaleString('ro-RO', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function formatMoney(val: number | string | null | undefined, currency = 'RON'): string {
  if (val === null || val === undefined || val === '') return '—'
  const num = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(num)) return String(val)
  return new Intl.NumberFormat('ro-RO', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(num) + ' ' + currency
}

function formatKpiValue(val: number | null | undefined, unit: string | null): string {
  if (val === null || val === undefined) return '—'
  if (unit === 'percentage') return val.toFixed(1) + '%'
  if (unit === 'currency') return formatMoney(val)
  if (unit === 'ratio') return val.toFixed(2)
  return new Intl.NumberFormat('ro-RO').format(val)
}

function KpiProgressBar({ current, target, status }: { current: number | null; target: number | null; status: string }) {
  if (!target || target === 0) return null
  const pct = Math.min(100, Math.round(((current ?? 0) / target) * 100))
  const barColor =
    status === 'exceeded' || status === 'on_track' ? 'bg-green-500 dark:bg-green-400'
    : status === 'at_risk' ? 'bg-yellow-500 dark:bg-yellow-400'
    : status === 'behind' ? 'bg-red-500 dark:bg-red-400'
    : 'bg-gray-300 dark:bg-gray-600'

  return (
    <div className="mt-1.5">
      <div className="mb-0.5 flex items-center justify-between text-[10px] text-muted-foreground">
        <span>{pct}%</span>
        <span>target</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
        <div className={cn('h-full rounded-full transition-all', barColor)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

interface BudgetLine {
  category?: string
  channel?: string
  amount?: number | string
  currency?: string
  description?: string
}

function BudgetBreakdown({ lines, totalCurrency }: { lines: BudgetLine[]; totalCurrency?: string }) {
  if (!lines || lines.length === 0) return null
  const total = lines.reduce((sum, l) => sum + (parseFloat(String(l.amount ?? 0)) || 0), 0)
  const currency = totalCurrency || lines[0]?.currency || 'RON'

  return (
    <div className="space-y-1.5">
      {lines.map((line, i) => {
        const amt = parseFloat(String(line.amount ?? 0)) || 0
        const pct = total > 0 ? Math.round((amt / total) * 100) : 0
        return (
          <div key={i} className="group relative">
            <div className="mb-0.5 flex items-center justify-between text-xs">
              <span className="font-medium text-foreground">
                {line.channel || line.category || `Line ${i + 1}`}
                {line.description && (
                  <span className="ml-1 text-muted-foreground font-normal">— {line.description}</span>
                )}
              </span>
              <span className="text-muted-foreground">{formatMoney(amt, line.currency || currency)} <span className="text-[10px]">({pct}%)</span></span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
              <div
                className="h-full rounded-full bg-primary/60 transition-all group-hover:bg-primary"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )
      })}
      <div className="flex items-center justify-between border-t pt-1.5 text-xs font-semibold">
        <span>Total Budget</span>
        <span>{formatMoney(total, currency)}</span>
      </div>
    </div>
  )
}

function MktProjectSummary({
  ctx,
  entityId,
}: {
  ctx: Record<string, unknown>
  entityId: number | null
}) {
  const { data: kpisData, isLoading: kpisLoading } = useQuery({
    queryKey: ['mkt-project-kpis-approval', entityId],
    queryFn: () => marketingApi.getProjectKpis(entityId!),
    enabled: !!entityId,
  })
  const kpis: MktProjectKpi[] = kpisData?.kpis ?? []

  const title = (ctx.title as string) || '—'
  const company = (ctx.company as string) || null
  const brand = (ctx.brand as string) || null
  const owner = (ctx.owner as string) || null
  const projectType = (ctx.project_type as string) || null
  const startDate = (ctx.start_date as string) || null
  const endDate = (ctx.end_date as string) || null
  const objective = (ctx.objective as string) || null
  const amount = ctx.amount as number | null
  const currency = (ctx.currency as string) || 'RON'
  const channels = ctx.channels as string[] | string | null
  const budgetBreakdown = ctx.budget_breakdown as BudgetLine[] | null

  const channelList: string[] = Array.isArray(channels)
    ? channels
    : typeof channels === 'string' && channels
    ? channels.split(',').map((s) => s.trim())
    : []

  return (
    <div className="space-y-5">
      {/* Project header card */}
      <div className="rounded-xl border bg-gradient-to-br from-primary/5 via-background to-background p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h3 className="text-base font-semibold leading-tight text-foreground">{title}</h3>
            {objective && (
              <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{objective}</p>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              {projectType && (
                <Badge variant="secondary" className="gap-1 text-xs">
                  <Tag className="h-3 w-3" />
                  {projectType}
                </Badge>
              )}
              {channelList.map((ch) => (
                <Badge key={ch} variant="outline" className="text-xs">{ch}</Badge>
              ))}
            </div>
          </div>
          <div className="shrink-0 rounded-lg border bg-background px-4 py-2 text-right shadow-sm">
            <div className="text-xs text-muted-foreground">Total Budget</div>
            <div className="text-xl font-bold text-primary">{formatMoney(amount, currency)}</div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          {company && (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Building2 className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{company}</span>
            </div>
          )}
          {brand && (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Layers className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{brand}</span>
            </div>
          )}
          {owner && (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Users className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{owner}</span>
            </div>
          )}
          {(startDate || endDate) && (
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Calendar className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">
                {formatDate(startDate, true)}{endDate ? ` → ${formatDate(endDate, true)}` : ''}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Budget + KPIs two-column grid */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Budget breakdown */}
        {budgetBreakdown && budgetBreakdown.length > 0 && (
          <div className="rounded-xl border p-4">
            <div className="mb-3 flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-primary" />
              <h4 className="text-sm font-semibold">Budget Breakdown</h4>
            </div>
            <BudgetBreakdown lines={budgetBreakdown} totalCurrency={currency} />
          </div>
        )}

        {/* KPI scoreboard */}
        <div className={cn('rounded-xl border p-4', (!budgetBreakdown || budgetBreakdown.length === 0) && 'lg:col-span-2')}>
          <div className="mb-3 flex items-center gap-2">
            <Target className="h-4 w-4 text-primary" />
            <h4 className="text-sm font-semibold">KPI Overview</h4>
          </div>
          {kpisLoading ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-20 w-full rounded-lg" />
              ))}
            </div>
          ) : kpis.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">No KPIs defined for this project.</p>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {kpis.map((kpi) => {
                const displayVal = kpi.aggregation === 'average' ? kpi.average_value : kpi.aggregation === 'cumulative' ? kpi.cumulative_value : kpi.latest_value
                const status = kpi.status || 'no_data'
                const TrendIcon = kpi.direction === 'higher' ? TrendingUp : TrendingDown
                return (
                  <div
                    key={kpi.id}
                    className={cn('rounded-lg border p-2.5 transition-colors', KPI_STATUS_BG[status] || KPI_STATUS_BG.no_data)}
                  >
                    <div className="flex items-start justify-between gap-1">
                      <span className="text-[11px] font-medium leading-tight text-foreground line-clamp-2">
                        {kpi.kpi_name}
                      </span>
                      <TrendIcon className={cn('h-3 w-3 shrink-0 mt-0.5', KPI_STATUS_COLORS[status] || KPI_STATUS_COLORS.no_data)} />
                    </div>
                    {kpi.channel && (
                      <span className="text-[10px] text-muted-foreground">{kpi.channel}</span>
                    )}
                    <div className={cn('mt-1 text-base font-bold', KPI_STATUS_COLORS[status] || KPI_STATUS_COLORS.no_data)}>
                      {formatKpiValue(displayVal, kpi.unit)}
                    </div>
                    {kpi.target_value && (
                      <div className="text-[10px] text-muted-foreground">
                        Target: {formatKpiValue(kpi.target_value, kpi.unit)}
                      </div>
                    )}
                    <KpiProgressBar current={displayVal ?? null} target={kpi.target_value} status={status} />
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
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
  const isActive = detail?.status === 'pending' || detail?.status === 'in_progress'
  const isOwnRequest = detail?.requested_by?.id === currentUser?.id
  const ctx = detail?.context_snapshot || {}
  const title = (ctx.title as string) || `${detail?.entity_type}/${detail?.entity_id}`
  const isMktProject = detail?.entity_type === 'mkt_project'

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className={cn(
        'max-h-[90vh] overflow-y-auto',
        isMktProject ? 'max-w-[1080px]' : 'max-w-2xl',
      )}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            {title}
            {detail && (
              <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', STATUS_STYLES[detail.status] || '')}>
                {STATUS_LABELS[detail.status] || detail.status}
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
            <Skeleton className="h-48 w-full" />
          </div>
        ) : detail ? (
          <div className="space-y-5 py-2">
            {/* Meta info row */}
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-4">
              <div>
                <span className="text-muted-foreground">Requested by</span>
                <div className="font-medium">{detail.requested_by?.name || '—'}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Priority</span>
                <div className={cn('font-medium',
                  detail.priority === 'urgent' && 'text-red-600 dark:text-red-400',
                  detail.priority === 'high' && 'text-orange-600 dark:text-orange-400',
                )}>
                  {detail.priority}
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">Submitted</span>
                <div className="font-medium">{formatDate(detail.requested_at)}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Due</span>
                <div className="font-medium">{formatDate(detail.due_by)}</div>
              </div>
              {detail.current_step_name && (
                <div className="col-span-2 sm:col-span-4">
                  <span className="text-muted-foreground">Current Step: </span>
                  <span className="font-medium">{detail.current_step_name}</span>
                </div>
              )}
              {detail.resolution_note && (
                <div className="col-span-2 sm:col-span-4">
                  <span className="text-muted-foreground">Resolution: </span>
                  {detail.resolution_note}
                </div>
              )}
            </div>

            <Separator />

            {/* Marketing project rich summary OR generic context */}
            {isMktProject ? (
              <MktProjectSummary ctx={ctx} entityId={detail.entity_id} />
            ) : Object.keys(ctx).length > 0 ? (
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
            ) : null}

            {/* Steps progress */}
            {detail.steps && detail.steps.length > 0 && (
              <>
                <Separator />
                <div>
                  <h4 className="mb-2 text-sm font-medium">Approval Steps</h4>
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
            {isActive && isOwnRequest && (
              <>
                <Separator />
                <div className="flex items-center gap-2 rounded-md border border-yellow-300 bg-yellow-50 p-3 text-sm dark:border-yellow-700 dark:bg-yellow-900/20">
                  <ShieldAlert className="h-4 w-4 shrink-0 text-yellow-600 dark:text-yellow-400" />
                  <span className="text-yellow-800 dark:text-yellow-300">You cannot approve your own request. Another approver must review it.</span>
                </div>
              </>
            )}

            {/* Action area */}
            {isActive && !isOwnRequest && (
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
