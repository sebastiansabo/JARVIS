import type React from 'react'
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

// Matches images: ![alt](url) and mentions: @[Name](id)
const TOKEN_RE = /!\[([^\]]*)\]\(([^)]+)\)|@\[([^\]]+)\]\((\d+)\)/g

function renderContent(content: string) {
  const parts: (string | React.ReactElement)[] = []
  let last = 0
  let match: RegExpExecArray | null
  const re = new RegExp(TOKEN_RE)
  while ((match = re.exec(content)) !== null) {
    if (match.index > last) parts.push(content.slice(last, match.index))
    if (match[1] !== undefined || match[2] !== undefined) {
      // Image: ![alt](url)
      parts.push(
        <img
          key={`img-${match.index}`}
          src={match[2]}
          alt={match[1] || 'image'}
          className="mt-1 max-w-xs max-h-64 rounded-lg border cursor-pointer hover:opacity-90 transition-opacity"
          onClick={() => window.open(match![2], '_blank')}
        />
      )
    } else {
      // Mention: @[Name](id)
      parts.push(
        <span key={`mention-${match.index}`} className="inline-flex items-center rounded bg-primary/15 text-primary font-medium px-1 text-[13px]">
          @{match[3]}
        </span>
      )
    }
    last = re.lastIndex
  }
  if (last < content.length) parts.push(content.slice(last))
  return parts.length > 0 ? parts : content
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })
}

// Stable per-sender colour (name + avatar), Connecteam-style.
const SENDER_HUES = [
  { name: 'text-pink-600 dark:text-pink-400', av: 'bg-pink-500/20 text-pink-700 dark:text-pink-300' },
  { name: 'text-red-600 dark:text-red-400', av: 'bg-red-500/20 text-red-700 dark:text-red-300' },
  { name: 'text-orange-600 dark:text-orange-400', av: 'bg-orange-500/20 text-orange-700 dark:text-orange-300' },
  { name: 'text-amber-600 dark:text-amber-400', av: 'bg-amber-500/20 text-amber-700 dark:text-amber-300' },
  { name: 'text-emerald-600 dark:text-emerald-400', av: 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300' },
  { name: 'text-teal-600 dark:text-teal-400', av: 'bg-teal-500/20 text-teal-700 dark:text-teal-300' },
  { name: 'text-cyan-600 dark:text-cyan-400', av: 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-300' },
  { name: 'text-indigo-600 dark:text-indigo-400', av: 'bg-indigo-500/20 text-indigo-700 dark:text-indigo-300' },
  { name: 'text-violet-600 dark:text-violet-400', av: 'bg-violet-500/20 text-violet-700 dark:text-violet-300' },
  { name: 'text-fuchsia-600 dark:text-fuchsia-400', av: 'bg-fuchsia-500/20 text-fuchsia-700 dark:text-fuchsia-300' },
]

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
  const hue = SENDER_HUES[post.user_id % SENDER_HUES.length]
  const initials = post.user_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()

  return (
    <div className={cn('group relative py-1', isOwn ? 'flex justify-end' : 'flex justify-start')}>
      <div className={cn('max-w-[80%]', isOwn ? 'flex flex-row-reverse gap-2' : 'flex gap-2')}>
        {/* Avatar */}
        <div className={cn(
          'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold mt-0.5',
          isOwn ? 'bg-green-500/20 text-green-700 dark:text-green-400' : hue.av,
        )}>
          {initials}
        </div>

        <div className="min-w-0">
          {/* Pinned indicator */}
          {post.is_pinned && (
            <div className={cn('flex items-center gap-1 text-[10px] text-yellow-600 mb-0.5', isOwn && 'justify-end')}>
              <Pin className="h-2.5 w-2.5" /> Pinned
            </div>
          )}

          {/* Reply reference */}
          {post.reply_to_post_id && post.reply_to_content && (
            <div className={cn(
              'flex items-center gap-1.5 mb-1 text-[11px] text-muted-foreground px-2.5 py-1 rounded-md bg-muted/50',
              isOwn && 'flex-row-reverse text-right',
            )}>
              <Reply className="h-2.5 w-2.5 shrink-0" />
              <span className="font-medium">{post.reply_to_user_name}:</span>
              <span className="truncate max-w-[180px]">{post.reply_to_content}</span>
            </div>
          )}

          {/* Bubble */}
          <div className={cn(
            'relative rounded-2xl border px-3 py-2',
            isOwn
              ? 'bg-green-500/10 border-green-500/20 rounded-tr-sm'
              : 'bg-blue-500/10 border-blue-500/20 rounded-tl-sm',
            post.type === 'announcement' && 'border-blue-500/40 bg-blue-500/15',
          )}>
            {/* Name + time + actions */}
            <div className={cn('flex items-center gap-2 mb-0.5', isOwn && 'flex-row-reverse')}>
              <span className={cn('text-xs font-semibold', isOwn ? 'text-green-700 dark:text-green-400' : hue.name)}>
                {post.user_name}
              </span>
              {post.type === 'announcement' && <Badge variant="secondary" className="text-[9px] px-1 py-0">Anunț</Badge>}
              <span className="text-[10px] text-muted-foreground">{formatTime(post.created_at)}</span>
              {post.updated_at !== post.created_at && (
                <span className="text-[10px] text-muted-foreground">(edited)</span>
              )}

              {/* Actions */}
              <div className={cn('flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity', !isOwn && 'ml-auto', isOwn && 'mr-auto')}>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-5 w-5">
                      <Smile className="h-3 w-3" />
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

                <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => onReply(post)} title="Reply">
                  <Reply className="h-3 w-3" />
                </Button>

                {!isThreadReply && post.reply_count > 0 && (
                  <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => onThread(post)} title="View thread">
                    <MessageSquare className="h-3 w-3" />
                  </Button>
                )}

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-5 w-5">
                      <MoreVertical className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align={isOwn ? 'start' : 'end'}>
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
            <div className="text-sm whitespace-pre-wrap break-words">
              {renderContent(post.content)}
            </div>

            {/* Poll */}
            {post.type === 'poll' && post.poll && (
              <PollDisplay poll={post.poll} channelId={channelId} />
            )}
          </div>

          {/* Reactions — outside bubble */}
          {post.reactions && post.reactions.length > 0 && (
            <div className={cn('flex flex-wrap gap-1 mt-1 px-1', isOwn && 'justify-end')}>
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
              className={cn('mt-0.5 px-1 text-xs text-primary hover:underline', isOwn && 'block text-right')}
            >
              {post.reply_count} {post.reply_count === 1 ? 'reply' : 'replies'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
