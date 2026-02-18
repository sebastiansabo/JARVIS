import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { Pencil, Trash2, ClipboardCheck } from 'lucide-react'
import { marketingApi } from '@/api/marketing'
import { approvalsApi } from '@/api/approvals'
import { fmtDatetime } from './utils'

export function CommentsTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [newComment, setNewComment] = useState('')
  const [isInternal, setIsInternal] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editContent, setEditContent] = useState('')

  const { data } = useQuery({
    queryKey: ['mkt-comments', projectId],
    queryFn: () => marketingApi.getComments(projectId, true),
  })
  const comments = data?.comments ?? []

  // Fetch approval history to show decision comments
  const { data: approvalHistory } = useQuery({
    queryKey: ['approval-entity-history', 'mkt_project', projectId],
    queryFn: () => approvalsApi.getEntityHistory('mkt_project', projectId),
  })

  // Build unified timeline: project comments + approval decisions with comments
  type TimelineItem =
    | { kind: 'comment'; data: (typeof comments)[0] }
    | { kind: 'decision'; data: { id: string; user_name: string; decision: string; comment: string; decided_at: string; step_name?: string } }

  const timeline: TimelineItem[] = []
  for (const c of comments) {
    timeline.push({ kind: 'comment', data: c })
  }
  for (const req of approvalHistory?.history ?? []) {
    for (const d of req.decisions ?? []) {
      if (d.comment) {
        timeline.push({
          kind: 'decision',
          data: {
            id: `decision-${d.id}`,
            user_name: d.decided_by?.name ?? 'Unknown',
            decision: d.decision,
            comment: d.comment,
            decided_at: d.decided_at ?? '',
            step_name: d.step_name ?? undefined,
          },
        })
      }
    }
  }
  timeline.sort((a, b) => {
    const da = a.kind === 'comment' ? a.data.created_at : a.data.decided_at
    const db = b.kind === 'comment' ? b.data.created_at : b.data.decided_at
    return new Date(db).getTime() - new Date(da).getTime()
  })

  const decisionColors: Record<string, string> = {
    approved: 'border-green-300 bg-green-50/50 dark:border-green-800 dark:bg-green-950/20',
    rejected: 'border-red-300 bg-red-50/50 dark:border-red-800 dark:bg-red-950/20',
    returned: 'border-orange-300 bg-orange-50/50 dark:border-orange-800 dark:bg-orange-950/20',
  }
  const decisionBadgeColors: Record<string, string> = {
    approved: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    rejected: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    returned: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  }

  const addMut = useMutation({
    mutationFn: () => marketingApi.createComment(projectId, { content: newComment, is_internal: isInternal }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-comments', projectId] })
      setNewComment('')
    },
  })

  const updateMut = useMutation({
    mutationFn: () => marketingApi.updateComment(editingId!, { content: editContent }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-comments', projectId] })
      setEditingId(null)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => marketingApi.deleteComment(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-comments', projectId] }),
  })

  return (
    <div className="space-y-4">
      {/* New comment */}
      <div className="space-y-2">
        <Textarea
          placeholder="Write a comment..."
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          rows={3}
        />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isInternal}
              onChange={(e) => setIsInternal(e.target.checked)}
              className="rounded"
            />
            Internal note
          </label>
          <Button
            size="sm"
            disabled={!newComment.trim() || addMut.isPending}
            onClick={() => addMut.mutate()}
          >
            {addMut.isPending ? 'Posting...' : 'Post'}
          </Button>
        </div>
      </div>

      <Separator />

      {/* Unified timeline */}
      {timeline.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">No comments yet.</div>
      ) : (
        <div className="space-y-4">
          {timeline.map((item) => {
            if (item.kind === 'decision') {
              const d = item.data
              return (
                <div key={d.id} className={cn('rounded-lg border p-3 space-y-2', decisionColors[d.decision] ?? '')}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <ClipboardCheck className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className="text-sm font-medium">{d.user_name}</span>
                    <Badge className={cn('text-[10px] h-5 px-1.5', decisionBadgeColors[d.decision] ?? '')}>
                      {d.decision}
                    </Badge>
                    {d.step_name && <span className="text-xs text-muted-foreground">Step: {d.step_name}</span>}
                    <span className="text-xs text-muted-foreground ml-auto">{fmtDatetime(d.decided_at)}</span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{d.comment}</p>
                </div>
              )
            }
            const c = item.data
            return (
              <div key={c.id} className={cn('rounded-lg border p-3 space-y-2', c.is_internal && 'border-yellow-300 bg-yellow-50/50 dark:bg-yellow-900/10')}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{c.user_name}</span>
                    <span className="text-xs text-muted-foreground">{fmtDatetime(c.created_at)}</span>
                    {c.is_internal && <Badge variant="outline" className="text-xs text-yellow-600">Internal</Badge>}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={() => { setEditingId(c.id); setEditContent(c.content) }}
                    >
                      <Pencil className="h-3 w-3 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => deleteMut.mutate(c.id)}>
                      <Trash2 className="h-3 w-3 text-muted-foreground" />
                    </Button>
                  </div>
                </div>
                {editingId === c.id ? (
                  <div className="space-y-2">
                    <Textarea value={editContent} onChange={(e) => setEditContent(e.target.value)} rows={2} />
                    <div className="flex justify-end gap-2">
                      <Button variant="outline" size="sm" onClick={() => setEditingId(null)}>Cancel</Button>
                      <Button size="sm" disabled={!editContent.trim() || updateMut.isPending} onClick={() => updateMut.mutate()}>
                        Save
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm whitespace-pre-wrap">{c.content}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
