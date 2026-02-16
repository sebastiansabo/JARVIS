import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import TextareaAutosize from 'react-textarea-autosize'
import { Send, Bot, Loader2 } from 'lucide-react'
import { aiAgentApi } from '@/api/aiAgent'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { MessageBubble } from './MessageBubble'
import { RagSources } from './RagSources'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { toast } from 'sonner'
import type { Message, RagSource as RagSourceType } from '@/types/aiAgent'

export function ChatWindow() {
  const queryClient = useQueryClient()
  const selectedConversationId = useAiAgentStore((s) => s.selectedConversationId)
  const selectedModel = useAiAgentStore((s) => s.selectedModel)
  const setModel = useAiAgentStore((s) => s.setModel)
  const [input, setInput] = useState('')
  const [ragSources, setRagSources] = useState<Record<number, RagSourceType[]>>({})
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const { data: models } = useQuery({
    queryKey: ['ai-models'],
    queryFn: aiAgentApi.getModels,
    staleTime: 10 * 60 * 1000,
  })

  const { data: conversation } = useQuery({
    queryKey: ['conversation', selectedConversationId],
    queryFn: () => aiAgentApi.getConversation(selectedConversationId!),
    enabled: !!selectedConversationId,
  })

  const messages: Message[] = conversation?.messages ?? []

  // Auto-scroll to bottom on new messages or streaming content
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages.length, isStreaming, streamingContent])

  // Focus input when conversation changes
  useEffect(() => {
    inputRef.current?.focus()
  }, [selectedConversationId])

  const handleSend = useCallback(() => {
    const content = input.trim()
    if (!content || !selectedConversationId || isStreaming) return
    setInput('')
    setIsStreaming(true)
    setStreamingContent('')

    aiAgentApi.streamMessage(
      selectedConversationId,
      content,
      selectedModel ?? undefined,
      // onChunk
      (text) => {
        setStreamingContent((prev) => prev + text)
      },
      // onDone
      (data) => {
        setIsStreaming(false)
        setStreamingContent('')
        queryClient.invalidateQueries({ queryKey: ['conversation', selectedConversationId] })
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
        if (data.rag_sources?.length) {
          setRagSources((prev) => ({ ...prev, [data.message_id]: data.rag_sources }))
        }
      },
      // onError
      (error) => {
        setIsStreaming(false)
        setStreamingContent('')
        toast.error(error || 'Failed to send message')
      },
    )
  }, [input, selectedConversationId, isStreaming, selectedModel, queryClient])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Empty state
  if (!selectedConversationId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-muted-foreground">
        <Bot className="mb-4 h-12 w-12" />
        <h2 className="text-lg font-medium">JARVIS AI Agent</h2>
        <p className="mt-1 text-sm">Select a conversation or start a new chat</p>
      </div>
    )
  }

  const currentModel = selectedModel ?? (models && models.length > 0 ? String(models[0].id) : null)

  return (
    <div className="flex h-full flex-col">
      {/* Chat header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <h3 className="truncate text-sm font-medium">
          {conversation?.title || 'New conversation'}
        </h3>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="text-xs">
              {currentModel
                ? models?.find((m) => String(m.id) === currentModel)?.display_name ?? currentModel
                : 'Select model'}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {models?.map((model) => (
              <DropdownMenuItem key={model.id} onClick={() => setModel(String(model.id))}>
                <span className="text-xs font-medium">{model.display_name}</span>
                <span className="ml-2 text-xs text-muted-foreground">{model.provider}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="space-y-4 p-4">
          {messages.length === 0 && !isStreaming && (
            <div className="py-12 text-center text-sm text-muted-foreground">
              Send a message to start the conversation
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id}>
              <MessageBubble message={msg} />
              {ragSources[msg.id] && <RagSources sources={ragSources[msg.id]} />}
            </div>
          ))}

          {/* Streaming response */}
          {isStreaming && streamingContent && (
            <MessageBubble
              message={{
                id: -1,
                role: 'assistant',
                content: streamingContent,
                input_tokens: 0,
                output_tokens: 0,
                cost: '0',
                response_time_ms: 0,
                created_at: new Date().toISOString(),
              }}
            />
          )}

          {/* Typing indicator (before first token arrives) */}
          {isStreaming && !streamingContent && (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
                <Bot className="h-4 w-4" />
              </div>
              <div className="flex items-center gap-1 rounded-lg bg-muted px-4 py-3">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Thinking...</span>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input area */}
      <div className="border-t p-4">
        <div className="flex items-end gap-2">
          <TextareaAutosize
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask JARVIS anything..."
            minRows={1}
            maxRows={6}
            className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled={isStreaming}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            size="icon"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
