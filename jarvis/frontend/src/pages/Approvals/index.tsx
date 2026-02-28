import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTabParam } from '@/hooks/useTabParam'
import { ClipboardCheck, Inbox, Send, Clock, CheckCircle, XCircle, RotateCcw, AlertTriangle, Users2, Plus, Trash2, LayoutDashboard } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/PageHeader'
import { StatCard } from '@/components/shared/StatCard'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDashboardWidgetToggle } from '@/hooks/useDashboardWidgetToggle'
import { approvalsApi } from '@/api/approvals'
import { usersApi } from '@/api/users'
import { QueryError } from '@/components/QueryError'
import { toast } from 'sonner'
import RequestDetail from './RequestDetail'
import type { ApprovalRequest, ApprovalQueueItem, ApprovalDelegation } from '@/types/approvals'
import type { UserDetail } from '@/types/users'

type Tab = 'queue' | 'my-requests' | 'all' | 'delegations'

const STATUS_CONFIG: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; icon: React.ElementType }> = {
  pending: { label: 'Pending', variant: 'outline', icon: Clock },
  approved: { label: 'Approved', variant: 'default', icon: CheckCircle },
  rejected: { label: 'Rejected', variant: 'destructive', icon: XCircle },
  returned: { label: 'Returned', variant: 'secondary', icon: RotateCcw },
  cancelled: { label: 'Cancelled', variant: 'secondary', icon: XCircle },
  expired: { label: 'Expired', variant: 'destructive', icon: AlertTriangle },
}

const PRIORITY_CONFIG: Record<string, { label: string; className: string }> = {
  low: { label: 'Low', className: 'text-muted-foreground' },
  normal: { label: 'Normal', className: '' },
  high: { label: 'High', className: 'text-orange-600 dark:text-orange-400 font-medium' },
  urgent: { label: 'Urgent', className: 'text-red-600 dark:text-red-400 font-semibold' },
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export default function Approvals() {
  const { isOnDashboard, toggleDashboardWidget } = useDashboardWidgetToggle('approvals_queue')
  const [activeTab, setActiveTab] = useTabParam<Tab>('queue')
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [showDelegationDialog, setShowDelegationDialog] = useState(false)
  const [newDelegation, setNewDelegation] = useState({ delegate_id: '', starts_at: '', ends_at: '', reason: '' })
  const queryClient = useQueryClient()

  const { data: queueData, isLoading: queueLoading, isError: queueError, refetch: refetchQueue } = useQuery({
    queryKey: ['approval-queue'],
    queryFn: () => approvalsApi.getMyQueue(),
  })

  const { data: myRequestsData, isLoading: myRequestsLoading, isError: myRequestsError, refetch: refetchMyRequests } = useQuery({
    queryKey: ['approval-my-requests'],
    queryFn: () => approvalsApi.getMyRequests(),
  })

  const { data: allRequestsData, isLoading: allLoading, isError: allError, refetch: refetchAll } = useQuery({
    queryKey: ['approval-all-requests', statusFilter],
    queryFn: () => approvalsApi.listRequests({ status: statusFilter || undefined }),
    enabled: activeTab === 'all',
  })

  const { data: countData } = useQuery({
    queryKey: ['approval-queue-count'],
    queryFn: () => approvalsApi.getMyQueueCount(),
    refetchInterval: 30000,
  })

  const { data: delegationsData, isLoading: delegationsLoading } = useQuery({
    queryKey: ['approval-delegations'],
    queryFn: () => approvalsApi.getDelegations(),
    enabled: activeTab === 'delegations',
  })

  const { data: usersData } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    enabled: showDelegationDialog,
  })

  const decideMutation = useMutation({
    mutationFn: ({ requestId, decision, comment }: { requestId: number; decision: string; comment?: string }) =>
      approvalsApi.decide(requestId, { decision, comment }),
    onSuccess: () => {
      toast.success('Decision recorded')
      queryClient.invalidateQueries({ queryKey: ['approval-queue'] })
      queryClient.invalidateQueries({ queryKey: ['approval-queue-count'] })
      queryClient.invalidateQueries({ queryKey: ['approval-my-requests'] })
      queryClient.invalidateQueries({ queryKey: ['approval-all-requests'] })
    },
    onError: () => toast.error('Failed to record decision'),
  })

  const createDelegationMutation = useMutation({
    mutationFn: (data: { delegate_id: number; starts_at: string; ends_at: string; reason?: string }) =>
      approvalsApi.createDelegation(data),
    onSuccess: () => {
      toast.success('Delegation created')
      setShowDelegationDialog(false)
      setNewDelegation({ delegate_id: '', starts_at: '', ends_at: '', reason: '' })
      queryClient.invalidateQueries({ queryKey: ['approval-delegations'] })
    },
    onError: () => toast.error('Failed to create delegation'),
  })

  const deleteDelegationMutation = useMutation({
    mutationFn: (id: number) => approvalsApi.deleteDelegation(id),
    onSuccess: () => {
      toast.success('Delegation revoked')
      queryClient.invalidateQueries({ queryKey: ['approval-delegations'] })
    },
    onError: () => toast.error('Failed to revoke delegation'),
  })

  const queueCount = countData?.count ?? 0
  const queue = queueData?.queue ?? []
  const myRequests = myRequestsData?.requests ?? []
  const allRequests = allRequestsData?.requests ?? []
  const delegations = delegationsData?.delegations ?? []
  const users: UserDetail[] = (usersData as UserDetail[] | undefined) ?? []

  const pendingMyRequests = myRequests.filter(r => r.status === 'pending').length
  const approvedMyRequests = myRequests.filter(r => r.status === 'approved').length

  const tabs: { key: Tab; label: string; icon: React.ElementType; count?: number }[] = [
    { key: 'queue', label: 'My Queue', icon: Inbox, count: queueCount },
    { key: 'my-requests', label: 'My Requests', icon: Send },
    { key: 'all', label: 'All Requests', icon: ClipboardCheck },
    { key: 'delegations', label: 'Delegations', icon: Users2 },
  ]

  const renderStatusBadge = (status: string) => {
    const config = STATUS_CONFIG[status] || STATUS_CONFIG.pending
    const Icon = config.icon
    return (
      <Badge variant={config.variant} className="gap-1">
        <Icon className="h-3 w-3" />
        {config.label}
      </Badge>
    )
  }

  const renderPriority = (priority: string) => {
    const config = PRIORITY_CONFIG[priority] || PRIORITY_CONFIG.normal
    return <span className={config.className}>{config.label}</span>
  }

  const renderQueueRow = (item: ApprovalQueueItem) => (
    <tr
      key={item.id}
      className="cursor-pointer border-b transition-colors hover:bg-muted/50"
      onClick={() => setSelectedRequestId(item.id)}
    >
      <td className="px-3 py-2.5 text-sm font-medium">{item.title}</td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">{item.entity_type}</td>
      <td className="px-3 py-2.5 text-sm">{item.current_step_name}</td>
      <td className="px-3 py-2.5 text-sm">{renderPriority(item.priority)}</td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">{item.requested_by?.name}</td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">{item.waiting_hours}h waiting</td>
      <td className="px-3 py-2.5">
        <div className="flex gap-1.5">
          <Button
            size="sm"
            variant="default"
            className="h-7 px-2 text-xs"
            onClick={(e) => { e.stopPropagation(); decideMutation.mutate({ requestId: item.id, decision: 'approved' }) }}
            disabled={decideMutation.isPending}
          >
            <CheckCircle className="mr-1 h-3 w-3" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className="h-7 px-2 text-xs"
            onClick={(e) => { e.stopPropagation(); setSelectedRequestId(item.id) }}
          >
            <XCircle className="mr-1 h-3 w-3" />
            Reject
          </Button>
        </div>
      </td>
    </tr>
  )

  const renderRequestRow = (item: ApprovalRequest) => {
    const ctx = item.context_snapshot || {}
    const title = (ctx.title as string) || `${item.entity_type}/${item.entity_id}`
    return (
      <tr
        key={item.id}
        className="cursor-pointer border-b transition-colors hover:bg-muted/50"
        onClick={() => setSelectedRequestId(item.id)}
      >
        <td className="px-3 py-2.5 text-sm font-medium">{title}</td>
        <td className="px-3 py-2.5 text-sm text-muted-foreground">{item.entity_type}</td>
        <td className="px-3 py-2.5 text-sm">{item.current_step_name || '—'}</td>
        <td className="px-3 py-2.5">{renderStatusBadge(item.status)}</td>
        <td className="px-3 py-2.5 text-sm">{renderPriority(item.priority)}</td>
        <td className="px-3 py-2.5 text-sm text-muted-foreground">
          {item.requested_by?.name}
        </td>
        <td className="px-3 py-2.5 text-sm text-muted-foreground">
          {timeAgo(item.requested_at)}
        </td>
      </tr>
    )
  }

  const renderDelegationRow = (d: ApprovalDelegation) => (
    <tr key={d.id} className="border-b">
      <td className="px-3 py-2.5 text-sm font-medium">{d.delegate_name || `User #${d.delegate_id}`}</td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">{formatDate(d.starts_at)}</td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">{formatDate(d.ends_at)}</td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">{d.entity_type || 'All'}</td>
      <td className="px-3 py-2.5 text-sm text-muted-foreground">{d.reason || '—'}</td>
      <td className="px-3 py-2.5">
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs text-destructive hover:text-destructive"
          onClick={() => deleteDelegationMutation.mutate(d.id)}
          disabled={deleteDelegationMutation.isPending}
        >
          <Trash2 className="mr-1 h-3 w-3" />
          Revoke
        </Button>
      </td>
    </tr>
  )

  const handleCreateDelegation = () => {
    if (!newDelegation.delegate_id || !newDelegation.starts_at || !newDelegation.ends_at) {
      toast.error('Delegate, start date, and end date are required')
      return
    }
    createDelegationMutation.mutate({
      delegate_id: Number(newDelegation.delegate_id),
      starts_at: newDelegation.starts_at,
      ends_at: newDelegation.ends_at,
      reason: newDelegation.reason || undefined,
    })
  }

  const isLoading = activeTab === 'queue' ? queueLoading
    : activeTab === 'my-requests' ? myRequestsLoading
    : activeTab === 'all' ? allLoading
    : delegationsLoading

  const tabError = activeTab === 'queue' ? queueError
    : activeTab === 'my-requests' ? myRequestsError
    : activeTab === 'all' ? allError
    : false
  const tabRefetch = activeTab === 'queue' ? refetchQueue
    : activeTab === 'my-requests' ? refetchMyRequests
    : activeTab === 'all' ? refetchAll
    : undefined

  return (
    <div className="space-y-4">
      <PageHeader
        title="Approvals"
        breadcrumbs={[
          { label: 'Approvals' },
          { label: tabs.find(t => t.key === activeTab)?.label ?? 'My Queue' },
        ]}
        actions={
          <Button variant="ghost" size="icon" className="md:size-auto md:px-3" onClick={toggleDashboardWidget}>
            <LayoutDashboard className="h-3.5 w-3.5 md:mr-1.5" />
            <span className="hidden md:inline">{isOnDashboard() ? 'Hide from Dashboard' : 'Show on Dashboard'}</span>
          </Button>
        }
      />

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          title="Pending Queue"
          value={queueCount}
          icon={<Inbox className="h-4 w-4" />}
          isLoading={queueLoading}
        />
        <StatCard
          title="My Pending"
          value={pendingMyRequests}
          icon={<Clock className="h-4 w-4" />}
          isLoading={myRequestsLoading}
        />
        <StatCard
          title="My Approved"
          value={approvedMyRequests}
          icon={<CheckCircle className="h-4 w-4" />}
          isLoading={myRequestsLoading}
        />
        <StatCard
          title="Total Requests"
          value={allRequests.length || myRequests.length}
          icon={<ClipboardCheck className="h-4 w-4" />}
          isLoading={allLoading || myRequestsLoading}
        />
      </div>

      {/* Tab nav */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)}>
        <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:overflow-visible md:px-0">
        <TabsList className="w-max md:w-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <TabsTrigger key={tab.key} value={tab.key}>
                <Icon className="h-4 w-4" />
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <Badge variant="default" className="ml-1 h-5 min-w-5 px-1.5 text-xs">
                    {tab.count}
                  </Badge>
                )}
              </TabsTrigger>
            )
          })}
        </TabsList>
        </div>
      </Tabs>

      {/* Status filter for All tab */}
      {activeTab === 'all' && (
        <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 md:mx-0 md:px-0">
          {['', 'pending', 'approved', 'rejected', 'returned', 'cancelled'].map((s) => (
            <Button
              key={s}
              size="sm"
              variant={statusFilter === s ? 'default' : 'outline'}
              className="h-7 text-xs"
              onClick={() => setStatusFilter(s)}
            >
              {s || 'All'}
            </Button>
          ))}
        </div>
      )}

      {/* Add delegation button */}
      {activeTab === 'delegations' && (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setShowDelegationDialog(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            New Delegation
          </Button>
        </div>
      )}

      {/* Table */}
      {tabError ? (
        <QueryError message="Failed to load approval data" onRetry={() => tabRefetch?.()} />
      ) : isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : activeTab === 'delegations' ? (
        <div className="rounded-md border overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Delegate</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">From</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Until</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Scope</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Reason</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {delegations.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-sm text-muted-foreground">No active delegations</td></tr>
              )}
              {delegations.map(renderDelegationRow)}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-md border overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                {activeTab === 'queue' ? (
                  <>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Title</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Type</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Step</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Priority</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Requester</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Waiting</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Actions</th>
                  </>
                ) : (
                  <>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Title</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Type</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Step</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Status</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Priority</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Requester</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Submitted</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {activeTab === 'queue' && queue.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-8 text-center text-sm text-muted-foreground">No pending approvals in your queue</td></tr>
              )}
              {activeTab === 'queue' && queue.map(renderQueueRow)}

              {activeTab === 'my-requests' && myRequests.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-8 text-center text-sm text-muted-foreground">You haven't submitted any requests</td></tr>
              )}
              {activeTab === 'my-requests' && myRequests.map(renderRequestRow)}

              {activeTab === 'all' && allRequests.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-8 text-center text-sm text-muted-foreground">No approval requests found</td></tr>
              )}
              {activeTab === 'all' && allRequests.map(renderRequestRow)}
            </tbody>
          </table>
        </div>
      )}

      {/* Request detail dialog */}
      {selectedRequestId !== null && (
        <RequestDetail
          requestId={selectedRequestId}
          open={true}
          onClose={() => setSelectedRequestId(null)}
        />
      )}

      {/* New delegation dialog */}
      <Dialog open={showDelegationDialog} onOpenChange={setShowDelegationDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>New Delegation</DialogTitle>
            <DialogDescription>
              Delegate your approval responsibilities to another user while you're away.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <label className="mb-1 block text-sm font-medium">Delegate to</label>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={newDelegation.delegate_id}
                onChange={(e) => setNewDelegation(prev => ({ ...prev, delegate_id: e.target.value }))}
              >
                <option value="">Select a user...</option>
                {users.filter(u => u.is_active).map(u => (
                  <option key={u.id} value={u.id}>{u.name} ({u.role_name})</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Start date</label>
                <input
                  type="date"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={newDelegation.starts_at}
                  onChange={(e) => setNewDelegation(prev => ({ ...prev, starts_at: e.target.value }))}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">End date</label>
                <input
                  type="date"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  value={newDelegation.ends_at}
                  onChange={(e) => setNewDelegation(prev => ({ ...prev, ends_at: e.target.value }))}
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Reason (optional)</label>
              <input
                type="text"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                placeholder="e.g., On vacation"
                value={newDelegation.reason}
                onChange={(e) => setNewDelegation(prev => ({ ...prev, reason: e.target.value }))}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDelegationDialog(false)}>Cancel</Button>
            <Button
              onClick={handleCreateDelegation}
              disabled={createDelegationMutation.isPending || !newDelegation.delegate_id || !newDelegation.starts_at || !newDelegation.ends_at}
            >
              Create Delegation
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
