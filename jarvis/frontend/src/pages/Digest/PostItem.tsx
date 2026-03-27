import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pin, Reply, MessageSquare, MoreVertical, Trash2, Smile } from 'lucide-react'
import { digestApi } from '@/api/digest'
import { useAuthStore } from '@/stores/authStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import type { DigestPost } from '@/types/digest'
import PollDisplay from './PollDisplay'

const EMOJI_QUICK = ['👍', '❤️', '😂', '🎉', '🤔', '👀', '🚀', '💯']

interface Props {
  post: DigestPost
  channelId: number
  onReply: (post: DigestPost) => void
  onThread: (post: DigestPost) => void
  isThreadReply?: boolean
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`
  if (diff < 604800_000) return d.toLocaleDateString('en', { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  return d.toLocaleDateString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function PostItem({ post, channelId, onReply, onThread, isThreadReply }: Props) {
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()

  const toggleReaction = useMutation({
    mutationFn: (emoji: string) => digestApi.toggleReaction(post.id, emoji),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-posts', channelId] })
      queryClient.invalidateQueries({ queryKey: ['digest-thread'] })
    },
  })

  const togglePin = useMutation({
    mutationFn: () => digestApi.togglePin(post.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['digest-posts', channelId] }),
  })

  const deletePost = useMutation({
    mutationFn: () => digestApi.deletePost(post.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-posts', channelId] })
      queryClient.invalidateQueries({ queryKey: ['digest-thread'] })
    },
  })

  const isOwn = user?.id === post.user_id
  const initials = post.user_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()

  return (
    <div className={cn(
      'group relative rounded-lg px-3 py-2 transition-colors hover:bg-accent/40',
      post.is_pinned && 'bg-yellow-500/5 border-l-2 border-yellow-500',
      post.type === 'announcement' && 'bg-blue-500/5 border-l-2 border-blue-500',
    )}>
      {/* Pinned indicator */}
      {post.is_pinned && (
        <div className="flex items-center gap-1 text-[10px] text-yellow-600 mb-1">
          <Pin className="h-2.5 w-2.5" /> Pinned
        </div>
      )}

      {/* Reply reference (swipe-to-reply) */}
      {post.reply_to_post_id && post.reply_to_content && (
        <div className="flex items-center gap-1.5 mb-1 pl-8 text-xs text-muted-foreground border-l-2 border-muted ml-4">
          <Reply className="h-3 w-3 shrink-0" />
          <span className="font-medium">{post.reply_to_user_name}</span>
          <span className="truncate max-w-[200px]">{post.reply_to_content}</span>
        </div>
      )}

      <div className="flex gap-2.5">
        {/* Avatar */}
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
          {initials}
        </div>

        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{post.user_name}</span>
            {post.type === 'announcement' && <Badge variant="secondary" className="text-[10px] px-1.5 py-0">Announcement</Badge>}
            <span className="text-[11px] text-muted-foreground">{formatTime(post.created_at)}</span>
            {post.updated_at !== post.created_at && (
              <span className="text-[10px] text-muted-foreground">(edited)</span>
            )}

            {/* Actions */}
            <div className="ml-auto flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-6 w-6">
                    <Smile className="h-3.5 w-3.5" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-2" side="top">
                  <div className="flex gap-1">
                    {EMOJI_QUICK.map((e) => (
                      <button
                        key={e}
                        onClick={() => toggleReaction.mutate(e)}
                        className="text-lg hover:scale-125 transition-transform p-0.5"
                      >
                        {e}
                      </button>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>

              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onReply(post)} title="Reply">
                <Reply className="h-3.5 w-3.5" />
              </Button>

              {!isThreadReply && post.reply_count > 0 && (
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => onThread(post)} title="View thread">
                  <MessageSquare className="h-3.5 w-3.5" />
                </Button>
              )}

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-6 w-6">
                    <MoreVertical className="h-3.5 w-3.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => togglePin.mutate()}>
                    <Pin className="h-3.5 w-3.5 mr-2" /> {post.is_pinned ? 'Unpin' : 'Pin'}
                  </DropdownMenuItem>
                  {!isThreadReply && (
                    <DropdownMenuItem onClick={() => onThread(post)}>
                      <MessageSquare className="h-3.5 w-3.5 mr-2" /> Thread
                    </DropdownMenuItem>
                  )}
                  {isOwn && (
                    <DropdownMenuItem onClick={() => deletePost.mutate()} className="text-destructive">
                      <Trash2 className="h-3.5 w-3.5 mr-2" /> Delete
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {/* Content */}
          <div className="mt-0.5 text-sm whitespace-pre-wrap break-words">{post.content}</div>

          {/* Poll */}
          {post.type === 'poll' && post.poll && (
            <PollDisplay poll={post.poll} channelId={channelId} />
          )}

          {/* Reactions */}
          {post.reactions && post.reactions.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              <TooltipProvider delayDuration={200}>
                {post.reactions.map((r) => {
                  const hasReacted = r.user_ids?.includes(user?.id ?? 0)
                  return (
                    <Tooltip key={r.emoji}>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => toggleReaction.mutate(r.emoji)}
                          className={cn(
                            'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors',
                            hasReacted ? 'border-primary bg-primary/10' : 'hover:bg-accent',
                          )}
                        >
                          <span>{r.emoji}</span>
                          <span className="font-medium">{r.count}</span>
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        {r.user_names?.join(', ')}
                      </TooltipContent>
                    </Tooltip>
                  )
                })}
              </TooltipProvider>
            </div>
          )}

          {/* Thread indicator */}
          {!isThreadReply && post.reply_count > 0 && (
            <button
              onClick={() => onThread(post)}
              className="mt-1 text-xs text-primary hover:underline"
            >
              {post.reply_count} {post.reply_count === 1 ? 'reply' : 'replies'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
