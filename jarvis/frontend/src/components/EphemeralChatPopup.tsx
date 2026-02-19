import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import TextareaAutosize from 'react-textarea-autosize'
import { Send, Bot, Loader2 } from 'lucide-react'
import { aiAgentApi } from '@/api/aiAgent'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { MessageBubble } from '@/pages/AiAgent/MessageBubble'
import { RagSources } from '@/pages/AiAgent/RagSources'
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

export function EphemeralChatPopup() {
  const selectedModel = useAiAgentStore((s) => s.selectedModel)
  const setModel = useAiAgentStore((s) => s.setModel)

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [ragSources, setRagSources] = useState<Record<number, RagSourceType[]>>({})
  const [toolsUsed, setToolsUsed] = useState<Record<number, string[]>>({})

  const convIdRef = useRef<number | null>(null)
  const streamingRef = useRef('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const { data: models } = useQuery({
    queryKey: ['ai-models'],
    queryFn: aiAgentApi.getModels,
    staleTime: 10 * 60 * 1000,
  })

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages.length, isStreaming, streamingContent])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Cleanup: delete ephemeral conversation on unmount
  useEffect(() => {
    return () => {
      if (convIdRef.current) {
        aiAgentApi.deleteConversation(convIdRef.current).catch(() => {})
      }
    }
  }, [])

  const handleSend = useCallback(async () => {
    const content = input.trim()
    if (!content || isStreaming) return
    setInput('')
    setIsStreaming(true)
    setStreamingContent('')
    streamingRef.current = ''

    // Add user message locally
    const userMsg: Message = {
      id: Date.now(),
      role: 'user',
      content,
      input_tokens: 0,
      output_tokens: 0,
      cost: '0',
      response_time_ms: 0,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])

    try {
      // Lazy-create conversation on first message
      if (!convIdRef.current) {
        const conv = await aiAgentApi.createConversation('Quick Chat')
        convIdRef.current = conv.id
      }

      aiAgentApi.streamMessage(
        convIdRef.current,
        content,
        selectedModel ?? undefined,
        // onChunk
        (text) => {
          streamingRef.current += text
          setStreamingContent(streamingRef.current)
        },
        // onDone
        (data) => {
          const assistantMsg: Message = {
            id: data.message_id,
            role: 'assistant',
            content: streamingRef.current,
            input_tokens: 0,
            output_tokens: 0,
            cost: data.cost,
            response_time_ms: data.response_time_ms,
            created_at: new Date().toISOString(),
          }
          setMessages((prev) => [...prev, assistantMsg])
          setIsStreaming(false)
          setStreamingContent('')
          streamingRef.current = ''
          if (data.rag_sources?.length) {
            setRagSources((prev) => ({ ...prev, [data.message_id]: data.rag_sources }))
          }
          if (data.tools_used?.length) {
            setToolsUsed((prev) => ({ ...prev, [data.message_id]: data.tools_used! }))
          }
        },
        // onError
        (error) => {
          setIsStreaming(false)
          setStreamingContent('')
          streamingRef.current = ''
          toast.error(error || 'Failed to send message')
        },
      )
    } catch {
      setIsStreaming(false)
      setStreamingContent('')
      streamingRef.current = ''
      toast.error('Failed to create conversation')
    }
  }, [input, isStreaming, selectedModel])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const currentModel = selectedModel ?? (models && models.length > 0 ? String(models[0].id) : null)

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">Quick Chat</span>
        </div>
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
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Bot className="mb-3 h-10 w-10" />
              <p className="text-sm font-medium">JARVIS AI</p>
              <p className="mt-1 text-xs">Ask anything — no history saved</p>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id}>
              <MessageBubble message={msg} toolsUsed={toolsUsed[msg.id]} />
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

          {/* Typing indicator */}
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
