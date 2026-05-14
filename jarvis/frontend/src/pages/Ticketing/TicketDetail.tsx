import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Send, Trash2, User, Clock, MessageSquare } from 'lucide-react'
import { toast } from 'sonner'

import { ticketingApi } from '@/api/ticketing'
import type { TicketStatus, TicketPriority } from '@/types/ticketing'

import { PageHeader } from '@/components/shared/PageHeader'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { SearchSelect } from '@/components/shared/SearchSelect'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/hooks/useAuth'

const statusLabels: Record<TicketStatus, string> = {
  open: 'Open',
  in_progress: 'In Progress',
  resolved: 'Resolved',
  closed: 'Closed',
}

const priorityColors: Record<TicketPriority, string> = {
  low: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  medium: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
  critical: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
}

const categoryLabels: Record<string, string> = {
  hardware: 'Hardware',
  software: 'Software',
  network: 'Network',
  access: 'Access',
  other: 'Other',
}

function timeAgo(dateStr: string) {
  const d = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return d.toLocaleDateString('ro-RO', { day: '2-digit', month: 'short', year: 'numeric' })
}

function formatDateTime(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('ro-RO', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function TicketDetail() {
  const { ticketId } = useParams<{ ticketId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()

  const [comment, setComment] = useState('')
  const [deleteOpen, setDeleteOpen] = useState(false)

  const id = Number(ticketId)

  const ticketQ = useQuery({
    queryKey: ['ticketing', 'ticket', id],
    queryFn: () => ticketingApi.getTicket(id),
    enabled: !!id,
  })

  const staffQ = useQuery({
    queryKey: ['ticketing', 'it-staff'],
    queryFn: () => ticketingApi.getItStaff(),
  })

  const updateMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => ticketingApi.updateTicket(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ticketing'] })
      toast.success('Ticket updated')
    },
    onError: () => toast.error('Failed to update ticket'),
  })

  const commentMut = useMutation({
    mutationFn: (content: string) => ticketingApi.addComment(id, content),
    onSuccess: () => {
      setComment('')
      queryClient.invalidateQueries({ queryKey: ['ticketing', 'ticket', id] })
      toast.success('Comment added')
    },
    onError: () => toast.error('Failed to add comment'),
  })

  const deleteMut = useMutation({
    mutationFn: () => ticketingApi.deleteTicket(id),
    onSuccess: () => {
      toast.success('Ticket deleted')
      navigate('/app/ticketing')
    },
    onError: () => toast.error('Failed to delete ticket'),
  })

  const deleteCommentMut = useMutation({
    mutationFn: (commentId: number) => ticketingApi.deleteComment(id, commentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ticketing', 'ticket', id] })
      toast.success('Comment deleted')
    },
  })

  if (ticketQ.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  const ticket = ticketQ.data?.ticket
  const comments = ticketQ.data?.comments ?? []

  if (!ticket) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center">
        <p className="text-lg font-medium">Ticket not found</p>
        <Button variant="link" onClick={() => navigate('/app/ticketing')}>
          Back to tickets
        </Button>
      </div>
    )
  }

  const isCreator = ticket.created_by === user?.id
  const isAdmin = user?.can_access_settings || user?.is_admin
  const canManage = isAdmin // Simplified — IT staff = admin for v1
  const canClose = isCreator && ticket.status === 'resolved'

  const staffOptions = (staffQ.data?.users ?? []).map((u) => ({
    value: String(u.id),
    label: u.name,
  }))

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={() => navigate('/app/ticketing')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <span>Ticket #{ticket.id}</span>
          </div>
        }
        breadcrumbs={[
          { label: 'IT Helpdesk', href: '/app/ticketing' },
          { label: `#${ticket.id}` },
        ]}
        actions={
          canManage ? (
            <Button variant="destructive" size="sm" onClick={() => setDeleteOpen(true)}>
              <Trash2 className="mr-1 h-4 w-4" /> Delete
            </Button>
          ) : undefined
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        {/* Main content */}
        <div className="space-y-4 md:col-span-2">
          {/* Ticket info */}
          <Card className="p-4 md:p-6">
            <h2 className="text-xl font-semibold">{ticket.title}</h2>
            {ticket.description && (
              <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">
                {ticket.description}
              </p>
            )}
            <Separator className="my-4" />
            <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
              <div className="flex items-center gap-1">
                <User className="h-3.5 w-3.5" />
                {ticket.created_by_name}
              </div>
              <div className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                {formatDateTime(ticket.created_at)}
              </div>
              {ticket.comment_count > 0 && (
                <div className="flex items-center gap-1">
                  <MessageSquare className="h-3.5 w-3.5" />
                  {comments.length} comments
                </div>
              )}
            </div>
          </Card>

          {/* Comments */}
          <Card className="p-4 md:p-6">
            <h3 className="mb-4 font-semibold">Comments</h3>

            {comments.length === 0 ? (
              <p className="text-sm text-muted-foreground">No comments yet.</p>
            ) : (
              <div className="space-y-4">
                {comments.map((c) => (
                  <div key={c.id} className="flex gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
                      {c.user_name?.charAt(0)?.toUpperCase() ?? '?'}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{c.user_name}</span>
                        <span className="text-xs text-muted-foreground">{timeAgo(c.created_at)}</span>
                        {c.user_id === user?.id && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              deleteCommentMut.mutate(c.id)
                            }}
                            className="ml-auto text-xs text-muted-foreground hover:text-destructive"
                          >
                            delete
                          </button>
                        )}
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-sm">{c.content}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <Separator className="my-4" />

            {/* Add comment */}
            <div className="flex gap-2">
              <Textarea
                placeholder="Write a comment..."
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={2}
                className="min-h-[60px] flex-1"
              />
              <Button
                size="icon"
                disabled={!comment.trim() || commentMut.isPending}
                onClick={() => commentMut.mutate(comment.trim())}
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <Card className="p-4 space-y-4">
            <h3 className="font-semibold text-sm">Details</h3>

            {/* Status */}
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Status</label>
              {canManage ? (
                <Select
                  value={ticket.status}
                  onValueChange={(v) => updateMut.mutate({ status: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">Open</SelectItem>
                    <SelectItem value="in_progress">In Progress</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <div className="flex items-center gap-2">
                  <StatusBadge status={ticket.status} label={statusLabels[ticket.status]} />
                  {canClose && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => updateMut.mutate({ status: 'closed' })}
                    >
                      Close
                    </Button>
                  )}
                </div>
              )}
            </div>

            {/* Priority */}
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Priority</label>
              {canManage ? (
                <Select
                  value={ticket.priority}
                  onValueChange={(v) => updateMut.mutate({ priority: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <Badge className={priorityColors[ticket.priority]}>{ticket.priority}</Badge>
              )}
            </div>

            {/* Category */}
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Category</label>
              {canManage ? (
                <Select
                  value={ticket.category}
                  onValueChange={(v) => updateMut.mutate({ category: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="hardware">Hardware</SelectItem>
                    <SelectItem value="software">Software</SelectItem>
                    <SelectItem value="network">Network</SelectItem>
                    <SelectItem value="access">Access</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <span className="text-sm">{categoryLabels[ticket.category] ?? ticket.category}</span>
              )}
            </div>

            {/* Assignee */}
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Assigned To</label>
              {canManage ? (
                <SearchSelect
                  value={ticket.assigned_to ? String(ticket.assigned_to) : ''}
                  onValueChange={(v) => updateMut.mutate({ assigned_to: v ? Number(v) : null })}
                  options={staffOptions}
                  placeholder="Assign to..."
                />
              ) : (
                <span className="text-sm">
                  {ticket.assigned_to_name ?? <span className="text-muted-foreground">Unassigned</span>}
                </span>
              )}
            </div>

            <Separator />

            {/* Timestamps */}
            <div className="space-y-2 text-xs text-muted-foreground">
              <div>Created: {formatDateTime(ticket.created_at)}</div>
              <div>Updated: {formatDateTime(ticket.updated_at)}</div>
              {ticket.resolved_at && <div>Resolved: {formatDateTime(ticket.resolved_at)}</div>}
              {ticket.closed_at && <div>Closed: {formatDateTime(ticket.closed_at)}</div>}
            </div>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Ticket?"
        description={`This will permanently delete ticket #${ticket.id} and all its comments.`}
        onConfirm={() => deleteMut.mutate()}
      />
    </div>
  )
}
