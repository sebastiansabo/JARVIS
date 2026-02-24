import { useEffect } from 'react'
import { Bot } from 'lucide-react'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { EphemeralChatPopup } from './EphemeralChatPopup'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function AiAgentWidget() {
  const isWidgetOpen = useAiAgentStore((s) => s.isWidgetOpen)
  const setWidgetOpen = useAiAgentStore((s) => s.setWidgetOpen)

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isWidgetOpen) setWidgetOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isWidgetOpen, setWidgetOpen])

  return (
    <>
      {/* Floating trigger button — bottom-right corner */}
      {!isWidgetOpen && (
        <Button
          onClick={() => setWidgetOpen(true)}
          size="icon"
          aria-label="Open AI Agent"
          className="fixed bottom-5 right-5 z-50 h-12 w-12 rounded-full shadow-lg transition-transform hover:scale-105"
        >
          <Bot className="h-5 w-5" />
        </Button>
      )}
    </>
  )
}

/** Inline chat panel rendered inside the layout flex container (pushes content). */
export function AiAgentPanel() {
  const isWidgetOpen = useAiAgentStore((s) => s.isWidgetOpen)
  const setWidgetOpen = useAiAgentStore((s) => s.setWidgetOpen)

  if (!isWidgetOpen) return null

  return (
    <aside
      className={cn(
        'hidden md:flex flex-col border-l bg-background',
        'w-[420px] lg:w-[480px] xl:w-[540px]',
        'animate-in slide-in-from-right duration-200',
      )}
    >
      <EphemeralChatPopup onClose={() => setWidgetOpen(false)} />
    </aside>
  )
}
