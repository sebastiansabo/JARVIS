import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Send, Reply, BarChart3, X, Users, Settings, ImagePlus, Plus } from 'lucide-react'
import { digestApi } from '@/api/digest'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { DigestChannel, DigestPost } from '@/types/digest'
import PostItem from './PostItem'
import PollCreator from './PollCreator'
import ThreadView from './ThreadView'
import ChannelSettings from './ChannelSettings'

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
  const [showSettings, setShowSettings] = useState(false)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [plusMenuOpen, setPlusMenuOpen] = useState(false)
  const [mentionState, setMentionState] = useState<{ query: string; startPos: number } | null>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const cursorPosRef = useRef(0)

  const { data: mentionResults } = useQuery({
    queryKey: ['digest-user-search', mentionState?.query],
    queryFn: () => digestApi.searchUsers(mentionState!.query),
    enabled: !!mentionState && mentionState.query.length >= 2,
  })

  const insertMention = (userId: number, name: string) => {
    if (!mentionState) return
    const before = content.slice(0, mentionState.startPos)
    const after = content.slice(cursorPosRef.current)
    const newContent = `${before}@[${name}](${userId}) ${after}`
    setContent(newContent)
    setMentionState(null)
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    const cursorPos = e.target.selectionStart ?? value.length
    cursorPosRef.current = cursorPos
    setContent(value)

    // @poll shortcut
    if (value.trim().toLowerCase() === '@poll') {
      setContent('')
      setShowPollCreator(true)
      setMentionState(null)
      return
    }

    // Detect @mention while typing
    const textBeforeCursor = value.slice(0, cursorPos)
    const mentionMatch = textBeforeCursor.match(/@([\w\s]*)$/)
    if (mentionMatch && mentionMatch.index !== undefined) {
      setMentionState({ query: mentionMatch[1].trim(), startPos: mentionMatch.index })
    } else {
      setMentionState(null)
    }
  }

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
    mutationFn: async (data: { content: string; type?: string; reply_to_id?: number; poll?: { question: string; options: string[]; is_multiple_choice?: boolean } }) => {
      let finalContent = data.content
      // Upload image if attached
      if (imageFile) {
        const formData = new FormData()
        formData.append('file', imageFile)
        const uploadRes = await fetch('/api/digest/upload', { method: 'POST', body: formData })
        const uploadJson = await uploadRes.json()
        if (uploadJson.success && uploadJson.data?.url) {
          finalContent = finalContent ? `${finalContent}\n![image](${uploadJson.data.url})` : `![image](${uploadJson.data.url})`
        }
      }
      return digestApi.createPost(channel.id, { ...data, content: finalContent })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-posts', channel.id] })
      setContent('')
      setReplyTo(null)
      setShowPollCreator(false)
      setImageFile(null)
      setImagePreview(null)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    },
  })

  const handleSubmit = useCallback(() => {
    if (!content.trim() && !imageFile) return
    createPost.mutate({
      content: content.trim(),
      reply_to_id: replyTo?.id,
    })
  }, [content, replyTo, imageFile])

  const handlePollSubmit = (question: string, options: string[], isMultiple: boolean) => {
    createPost.mutate({
      content: question,
      type: 'poll',
      poll: { question, options, is_multiple_choice: isMultiple },
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && mentionState) {
      e.preventDefault()
      setMentionState(null)
      return
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      setMentionState(null)
      handleSubmit()
    }
  }

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setImageFile(file)
      const reader = new FileReader()
      reader.onload = () => setImagePreview(reader.result as string)
      reader.readAsDataURL(file)
    }
  }

  if (showSettings) {
    return <ChannelSettings channel={channel} onBack={() => setShowSettings(false)} />
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
        <Button variant="ghost" size="icon" onClick={() => setShowSettings(true)} title="Channel settings">
          <Settings className="h-4 w-4" />
        </Button>
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

      {/* Image preview */}
      {imagePreview && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-accent/30 rounded-t-lg">
          <img src={imagePreview} alt="preview" className="h-16 w-16 object-cover rounded-md" />
          <span className="text-xs text-muted-foreground truncate">{imageFile?.name}</span>
          <Button variant="ghost" size="icon" className="ml-auto h-5 w-5" onClick={() => { setImageFile(null); setImagePreview(null) }}>
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
        <div className="relative pt-3 border-t">
          {/* @mention suggestions */}
          {mentionState && mentionState.query.length >= 2 && (mentionResults?.data ?? []).length > 0 && (
            <div className="absolute bottom-full mb-1 left-0 right-0 z-10 rounded-lg border bg-popover p-1 shadow-md max-h-48 overflow-y-auto">
              {(mentionResults?.data ?? []).map((u) => (
                <button
                  key={u.id}
                  onClick={() => insertMention(u.id, u.name)}
                  className="w-full text-left px-3 py-2 rounded-md text-sm hover:bg-accent transition-colors flex items-center gap-3"
                >
                  <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary shrink-0">
                    {u.name.charAt(0)}
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium truncate">{u.name}</div>
                    <div className="text-xs text-muted-foreground truncate">{u.email}</div>
                  </div>
                </button>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2">
            {/* + menu */}
            <Popover open={plusMenuOpen} onOpenChange={setPlusMenuOpen}>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="icon" className="shrink-0 mb-0.5">
                  <Plus className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-44 p-1" side="top" align="start">
                <input
                  ref={imageInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleImageSelect}
                />
                <button
                  onClick={() => { imageInputRef.current?.click(); setPlusMenuOpen(false) }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm hover:bg-accent transition-colors"
                >
                  <ImagePlus className="h-4 w-4" /> Picture
                </button>
                <button
                  onClick={() => { setShowPollCreator(true); setPlusMenuOpen(false) }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm hover:bg-accent transition-colors"
                >
                  <BarChart3 className="h-4 w-4" /> Poll
                </button>
              </PopoverContent>
            </Popover>

            <Textarea
              ref={textareaRef}
              value={content}
              onChange={handleContentChange}
              onKeyDown={handleKeyDown}
              placeholder="Write a message... (@ to mention, @poll for poll)"
              rows={1}
              className="min-h-[40px] max-h-32 resize-none"
            />

            <Button
              size="icon"
              className="shrink-0 mb-0.5"
              disabled={(!content.trim() && !imageFile) || createPost.isPending}
              onClick={handleSubmit}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
