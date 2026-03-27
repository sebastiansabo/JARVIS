import { useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Send, Reply, X } from 'lucide-react'
import { digestApi } from '@/api/digest'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { DigestChannel, DigestPost } from '@/types/digest'
import PostItem from './PostItem'

interface Props {
  channel: DigestChannel
  parentPost: DigestPost
  onBack: () => void
}

export default function ThreadView({ channel, parentPost, onBack }: Props) {
  const queryClient = useQueryClient()
  const [content, setContent] = useState('')
  const [replyTo, setReplyTo] = useState<DigestPost | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: repliesRes, isLoading } = useQuery({
    queryKey: ['digest-thread', channel.id, parentPost.id],
    queryFn: () => digestApi.getPosts(channel.id, { parent_id: parentPost.id, limit: 200 }),
    refetchInterval: 10_000,
  })
  const replies = repliesRes?.data ?? []

  const createReply = useMutation({
    mutationFn: (data: { content: string; parent_id: number; reply_to_id?: number }) =>
      digestApi.createPost(channel.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-thread', channel.id, parentPost.id] })
      queryClient.invalidateQueries({ queryKey: ['digest-posts', channel.id] })
      setContent('')
      setReplyTo(null)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    },
  })

  const handleSubmit = useCallback(() => {
    if (!content.trim()) return
    createReply.mutate({
      content: content.trim(),
      parent_id: parentPost.id,
      reply_to_id: replyTo?.id,
    })
  }, [content, replyTo, parentPost.id])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b pb-3 mb-3">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold">Thread</h2>
          <p className="text-xs text-muted-foreground truncate">
            {parentPost.user_name} · {replies.length} {replies.length === 1 ? 'reply' : 'replies'}
          </p>
        </div>
      </div>

      {/* Parent post + Replies */}
      <div className="flex-1 overflow-y-auto space-y-1 pr-1">
        <PostItem
          post={parentPost}
          channelId={channel.id}
          onReply={(p) => setReplyTo(p)}
          onThread={() => {}}
          isThreadReply
        />
        <div className="border-t my-2" />
        {isLoading ? (
          <div className="space-y-3">
            {[1,2].map(i => <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />)}
          </div>
        ) : (
          replies.map((reply) => (
            <PostItem
              key={reply.id}
              post={reply}
              channelId={channel.id}
              onReply={(p) => setReplyTo(p)}
              onThread={() => {}}
              isThreadReply
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Reply indicator */}
      {replyTo && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-accent/50 rounded-t-lg border-l-2 border-primary text-sm">
          <Reply className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">Replying to</span>
          <span className="font-medium truncate">{replyTo.user_name}</span>
          <Button variant="ghost" size="icon" className="ml-auto h-5 w-5" onClick={() => setReplyTo(null)}>
            <X className="h-3 w-3" />
          </Button>
        </div>
      )}

      {/* Composer */}
      <div className="flex items-end gap-2 pt-3 border-t">
        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Reply in thread..."
          rows={1}
          className="min-h-[40px] max-h-32 resize-none"
        />
        <Button
          size="icon"
          className="shrink-0 mb-0.5"
          disabled={!content.trim() || createReply.isPending}
          onClick={handleSubmit}
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
