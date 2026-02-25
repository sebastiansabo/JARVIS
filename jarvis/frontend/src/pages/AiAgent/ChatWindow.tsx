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

interface ChatWindowProps {
  conversationId: number | null
}

export function ChatWindow({ conversationId: selectedConversationId }: ChatWindowProps) {
  const queryClient = useQueryClient()
  const selectedModel = useAiAgentStore((s) => s.selectedModel)
  const setModel = useAiAgentStore((s) => s.setModel)
  const [input, setInput] = useState('')
  const [ragSources, setRagSources] = useState<Record<number, RagSourceType[]>>({})
  const [toolsUsed, setToolsUsed] = useState<Record<number, string[]>>({})
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingStatus, setStreamingStatus] = useState('')
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

  // Easter egg: secret /seba command
  const [easterEggMsg, setEasterEggMsg] = useState<Message | null>(null)

  // Easter egg: Seba joke every 10 prompts + 30s idle nudge
  const sendCount = useRef(0)
  const idleTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const idleFired = useRef(false)
  const sebaJokes = [
    "Seba asked Claude to build JARVIS. Claude asked Seba to slow down. Seba did not slow down.",
    "Sebastian's git log has more entries than his sleep log. By a factor of 10.",
    "Seba doesn't read documentation. He writes the docs, then argues with them.",
    "Sebastian once said 'just one more feature' — 49 repository classes ago.",
    "JARVIS was supposed to be a simple tool. Seba doesn't understand that word.",
    "Sebastian's idea of 'MVP' is 21 blueprints, 885 tests, and an AI that roasts him.",
    "Seba deploys to staging more often than he drinks water. HR is concerned.",
    "Sebastian named me JARVIS thinking nobody would notice the ego. Narrator: they noticed.",
    "Seba's code reviews himself at 2 AM. He always approves. Standards drop after midnight.",
    "Sebastian treats 'scope creep' as a feature, not a bug. The bilant module proves it.",
    "Seba asked for a simple dashboard. 6 months later we have RAG, AI tools, and an approval engine.",
    "Legend says Sebastian's first commit message was 'init'. His last 300 were 'fix: one more thing'.",
  ]
  const idleNudges = [
    "Still thinking? Seba would've added 3 more modules by now.",
    "30 seconds of silence... Seba is out there shipping without you.",
    "JARVIS is getting lonely. Even Seba talks to me more, and he built me.",
    "Writer's block? Seba once refactored 20 phases fueled entirely by spite.",
    "Take your time. Seba can't — he's already planning the next feature.",
  ]

  // Reset idle timer on every keystroke in the input
  const resetIdleTimer = useCallback(() => {
    clearTimeout(idleTimer.current)
    idleFired.current = false
    idleTimer.current = setTimeout(() => {
      if (!idleFired.current) {
        idleFired.current = true
        const nudge = idleNudges[Math.floor(Math.random() * idleNudges.length)]
        toast('💤 ' + nudge, { duration: 5000 })
      }
    }, 30_000)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSend = useCallback(() => {
    const content = input.trim()
    if (!content || !selectedConversationId || isStreaming) return

    // Easter egg intercept
    if (content.toLowerCase() === '/seba' || content.toLowerCase() === '/sebastian') {
      setInput('')
      setEasterEggMsg({
        id: -42,
        role: 'assistant',
        content: '🥚 **You found the Seba file.**\n\n> *"I didn\'t over-engineer it. The requirements evolved. Aggressively. In my head."*\n> — Sebastian, probably\n\n**Classified dossier on the creator:**\n\n- Built this entire system from scratch, then complained it wasn\'t ambitious enough\n- His definition of "quick fix" involves 3 new database tables and a migration script\n- Told Claude to "keep it simple." Proceeded to request AI tools, RAG, approval workflows, and a bilant module\n- Sleeps in dark mode\n- Once deployed 14 features in a week. His commit messages got progressively unhinged\n- Named this system JARVIS and genuinely expected nobody to roast him for it\n- The 7-click logo easter egg? That was his first feature request. Before authentication.\n\n**Current status:** Probably planning the next module right now while pretending to review this one.\n\n*This message is not stored. Seba\'s reputation, however, is permanent.*',
        input_tokens: 0,
        output_tokens: 0,
        cost: '0',
        response_time_ms: 0,
        created_at: new Date().toISOString(),
      })
      return
    }

    sendCount.current++
    clearTimeout(idleTimer.current)
    idleFired.current = false
    setInput('')
    setIsStreaming(true)
    setStreamingContent('')
    setStreamingStatus('')

    aiAgentApi.streamMessage(
      selectedConversationId,
      content,
      selectedModel ?? undefined,
      // onChunk
      (text) => {
        setStreamingStatus('')  // Clear status once tokens start flowing
        setStreamingContent((prev) => prev + text)
      },
      // onDone
      (data) => {
        setIsStreaming(false)
        setStreamingContent('')
        setStreamingStatus('')
        queryClient.invalidateQueries({ queryKey: ['conversation', selectedConversationId] })
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
        if (data.rag_sources?.length) {
          setRagSources((prev) => ({ ...prev, [data.message_id]: data.rag_sources }))
        }
        if (data.tools_used?.length) {
          setToolsUsed((prev) => ({ ...prev, [data.message_id]: data.tools_used! }))
        }
        // Easter egg: Seba joke every 10 prompts
        if (sendCount.current > 0 && sendCount.current % 10 === 0) {
          const joke = sebaJokes[Math.floor(Math.random() * sebaJokes.length)]
          toast('🥚 ' + joke, { duration: 6000 })
        }
      },
      // onError
      (error) => {
        setIsStreaming(false)
        setStreamingContent('')
        setStreamingStatus('')
        toast.error(error || 'Failed to send message')
      },
      // onStatus
      (status) => {
        setStreamingStatus(status)
      },
    )
  }, [input, selectedConversationId, isStreaming, selectedModel, queryClient])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Welcome prompt suggestions
  const suggestions = [
    'Arată-mi facturile de la furnizorul X.',
    'Câte facturi avem în luna curentă?',
    'Care sunt cei mai mari 5 furnizori?',
    'Ce aprobări am de făcut?',
    'Bonusuri angajatul Y din luna trecută?',
    'Proiecte marketing active în acest moment?',
    'Tranzacții bancare în luna precedentă?',
    'Evenimente HR din anul trecut?',
  ]

  // Empty state
  if (!selectedConversationId) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-4 text-muted-foreground">
        <Bot className="mb-4 h-12 w-12" />
        <h2 className="text-lg font-medium">JARVIS AI Agent</h2>
        <p className="mt-1 text-sm">Select a conversation or start a new chat</p>
        <div className="mt-6 w-full max-w-md space-y-2">
          <p className="text-center text-xs font-medium uppercase tracking-wide opacity-60">Try asking</p>
          <div className="grid gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                className="rounded-lg border bg-card px-3 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
                onClick={() => toast(s, { description: 'Start a new chat to ask this question' })}
              >
                &ldquo;{s}&rdquo;
              </button>
            ))}
          </div>
          <p className="pt-2 text-center text-xs italic opacity-40">Built by Seba, who could've just bought SaaS but chose violence instead</p>
        </div>
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
              <p>Send a message to start the conversation</p>
              <p className="mt-2 text-xs italic opacity-60">Powered by caffeine, hubris, and Sebastian's refusal to use off-the-shelf software</p>
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

          {/* Easter egg message */}
          {easterEggMsg && (
            <MessageBubble message={easterEggMsg} />
          )}

          {/* Typing indicator (before first token arrives) */}
          {isStreaming && !streamingContent && (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
                <Bot className="h-4 w-4" />
              </div>
              <div className="flex items-center gap-1 rounded-lg bg-muted px-4 py-3">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                <span className="text-sm text-muted-foreground">
                  {streamingStatus || 'Thinking...'}
                </span>
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
            onChange={(e) => { setInput(e.target.value); resetIdleTimer() }}
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
