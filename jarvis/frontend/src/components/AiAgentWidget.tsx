import { useEffect } from 'react'
import { Bot, X } from 'lucide-react'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { EphemeralChatPopup } from './EphemeralChatPopup'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
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
      <Button
        onClick={() => setWidgetOpen(!isWidgetOpen)}
        size="icon"
        aria-label={isWidgetOpen ? 'Close AI Agent' : 'Open AI Agent'}
        className={cn(
          'fixed bottom-5 right-5 z-50 h-12 w-12 rounded-full shadow-lg transition-transform hover:scale-105',
          isWidgetOpen && 'bg-muted text-muted-foreground hover:bg-muted/80',
        )}
      >
        {isWidgetOpen ? <X className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
      </Button>

      {/* Chat panel — right-side Sheet */}
      <Sheet open={isWidgetOpen} onOpenChange={setWidgetOpen}>
        <SheetContent
          side="right"
          className="flex w-full flex-col gap-0 p-0 sm:max-w-lg md:max-w-xl lg:max-w-2xl"
          aria-describedby={undefined}
        >
          <SheetTitle className="sr-only">AI Agent</SheetTitle>
          {isWidgetOpen && <EphemeralChatPopup />}
        </SheetContent>
      </Sheet>
    </>
  )
}
