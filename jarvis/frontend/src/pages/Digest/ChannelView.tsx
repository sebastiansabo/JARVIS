import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Send, Reply, BarChart3, X, Users } from 'lucide-react'
import { digestApi } from '@/api/digest'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import type { DigestChannel, DigestPost } from '@/types/digest'
import PostItem from './PostItem'
import PollCreator from './PollCreator'
import ThreadView from './ThreadView'

interface Props {
  channel: DigestChannel
  onBack: () => void
}

export default function ChannelView({ channel, onBack }: Props) {
  const queryClient = useQueryClient()
  const [content, setContent] = useState('')
  const [replyTo, setReplyTo] = useState<DigestPost | null>(null)
  const [showPollCreator, setShowPollCreator] = useState(false)
  const [activeThread, setActiveThread] = useState<DigestPost | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: postsRes, isLoading } = useQuery({
    queryKey: ['digest-posts', channel.id],
    queryFn: () => digestApi.getPosts(channel.id, { limit: 100 }),
    refetchInterval: 10_000,
  })
  const posts = postsRes?.data ?? []

  // Mark as read when viewing
  useEffect(() => {
    if (posts.length > 0) {
      const maxId = Math.max(...posts.map(p => p.id))
      digestApi.markRead(channel.id, maxId)
      queryClient.invalidateQueries({ queryKey: ['digest-channels'] })
    }
  }, [posts.length, channel.id])

  const createPost = useMutation({
    mutationFn: (data: { content: string; type?: string; reply_to_id?: number; poll?: { question: string; options: string[]; is_multiple_choice?: boolean } }) =>
      digestApi.createPost(channel.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-posts', channel.id] })
      setContent('')
      setReplyTo(null)
      setShowPollCreator(false)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    },
  })

  const handleSubmit = useCallback(() => {
    if (!content.trim()) return
    createPost.mutate({
      content: content.trim(),
      reply_to_id: replyTo?.id,
    })
  }, [content, replyTo])

  const handlePollSubmit = (question: string, options: string[], isMultiple: boolean) => {
    createPost.mutate({
      content: question,
      type: 'poll',
      poll: { question, options, is_multiple_choice: isMultiple },
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  if (activeThread) {
    return (
      <ThreadView
        channel={channel}
        parentPost={activeThread}
        onBack={() => setActiveThread(null)}
      />
    )
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b pb-3 mb-3">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-semibold truncate">{channel.name}</h2>
          {channel.description && (
            <p className="text-xs text-muted-foreground truncate">{channel.description}</p>
          )}
        </div>
        <Badge variant="outline" className="shrink-0">
          <Users className="h-3 w-3 mr-1" /> {channel.member_count}
        </Badge>
      </div>

      {/* Posts */}
      <div className="flex-1 overflow-y-auto space-y-1 pr-1">
        {isLoading ? (
          <div className="space-y-3">
            {[1,2,3].map(i => <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />)}
          </div>
        ) : posts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
            <p className="text-sm">No posts yet. Start the conversation!</p>
          </div>
        ) : (
          [...posts].reverse().map((post) => (
            <PostItem
              key={post.id}
              post={post}
              channelId={channel.id}
              onReply={(p) => setReplyTo(p)}
              onThread={(p) => setActiveThread(p)}
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

      {/* Poll Creator */}
      {showPollCreator && (
        <PollCreator
          onSubmit={handlePollSubmit}
          onCancel={() => setShowPollCreator(false)}
          isPending={createPost.isPending}
        />
      )}

      {/* Composer */}
      {!showPollCreator && (
        <div className="flex items-end gap-2 pt-3 border-t">
          <Button variant="ghost" size="icon" className="shrink-0 mb-0.5" onClick={() => setShowPollCreator(true)} title="Create poll">
            <BarChart3 className="h-4 w-4" />
          </Button>
          <Textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Write a message..."
            rows={1}
            className="min-h-[40px] max-h-32 resize-none"
          />
          <Button
            size="icon"
            className="shrink-0 mb-0.5"
            disabled={!content.trim() || createPost.isPending}
            onClick={handleSubmit}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}
