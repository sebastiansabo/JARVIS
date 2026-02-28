import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { Bot } from 'lucide-react'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { EphemeralChatPopup } from './EphemeralChatPopup'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'

export function AiAgentWidget() {
  const isWidgetOpen = useAiAgentStore((s) => s.isWidgetOpen)
  const setWidgetOpen = useAiAgentStore((s) => s.setWidgetOpen)
  const { pathname } = useLocation()
  const isMobile = useIsMobile()

  // Hide on the full AI Agent page — the full chat is already there
  const onAiAgentPage = pathname.startsWith('/app/ai-agent')

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isWidgetOpen) setWidgetOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isWidgetOpen, setWidgetOpen])

  if (onAiAgentPage) return null

  return (
    <>
      {/* Floating trigger button — above bottom nav on mobile */}
      {!isWidgetOpen && (
        <Button
          onClick={() => setWidgetOpen(true)}
          size="icon"
          aria-label="Open AI Agent"
          className={cn(
            'fixed right-5 z-50 h-12 w-12 rounded-full shadow-lg transition-transform hover:scale-105',
            isMobile ? 'bottom-20' : 'bottom-5',
          )}
        >
          <Bot className="h-5 w-5" />
        </Button>
      )}

      {/* Mobile: bottom sheet for AI chat */}
      {isMobile && (
        <Sheet open={isWidgetOpen} onOpenChange={setWidgetOpen}>
          <SheetContent side="bottom" className="flex h-[85vh] flex-col p-0" showCloseButton={false}>
            <SheetTitle className="sr-only">AI Agent</SheetTitle>
            <EphemeralChatPopup onClose={() => setWidgetOpen(false)} pageContext={pathname} />
          </SheetContent>
        </Sheet>
      )}
    </>
  )
}

/** Inline chat panel rendered inside the layout flex container (pushes content). Desktop only — mobile uses Sheet. */
export function AiAgentPanel() {
  const isWidgetOpen = useAiAgentStore((s) => s.isWidgetOpen)
  const setWidgetOpen = useAiAgentStore((s) => s.setWidgetOpen)
  const { pathname } = useLocation()
  const isMobile = useIsMobile()

  // On mobile, the Sheet in AiAgentWidget handles rendering
  if (!isWidgetOpen || isMobile) return null

  return (
    <aside
      className={cn(
        'hidden md:flex flex-col border-l bg-background h-full overflow-hidden',
        'w-[420px] lg:w-[480px] xl:w-[540px]',
        'animate-in slide-in-from-right duration-200',
      )}
    >
      <EphemeralChatPopup onClose={() => setWidgetOpen(false)} pageContext={pathname} />
    </aside>
  )
}
