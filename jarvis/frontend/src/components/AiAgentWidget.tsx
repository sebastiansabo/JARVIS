import { useEffect } from 'react'
import { Bot, PanelLeftClose, PanelLeftOpen, X } from 'lucide-react'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { ChatWindow } from '@/pages/AiAgent/ChatWindow'
import { ConversationList } from '@/pages/AiAgent/ConversationList'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'

export function AiAgentWidget() {
  const isWidgetOpen = useAiAgentStore((s) => s.isWidgetOpen)
  const setWidgetOpen = useAiAgentStore((s) => s.setWidgetOpen)
  const isSidebarOpen = useAiAgentStore((s) => s.isSidebarOpen)
  const toggleSidebar = useAiAgentStore((s) => s.toggleSidebar)
  const selectedConversationId = useAiAgentStore((s) => s.selectedConversationId)

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
        >
          <SheetTitle className="sr-only">AI Agent</SheetTitle>

          <div className="flex h-full">
            {/* Conversation sidebar inside widget */}
            <div
              className={cn(
                'border-r transition-all duration-200',
                isSidebarOpen ? 'w-56' : 'w-0 overflow-hidden border-r-0',
              )}
            >
              {isSidebarOpen && <ConversationList />}
            </div>

            {/* Main chat */}
            <div className="flex flex-1 flex-col">
              {/* Widget header */}
              <div className="flex items-center gap-2 border-b px-3 py-2">
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={toggleSidebar}>
                  {isSidebarOpen ? (
                    <PanelLeftClose className="h-4 w-4" />
                  ) : (
                    <PanelLeftOpen className="h-4 w-4" />
                  )}
                </Button>
                <Bot className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">JARVIS AI</span>
              </div>

              {/* Chat content */}
              {selectedConversationId ? (
                <ChatWindow />
              ) : (
                <div className="flex flex-1 flex-col items-center justify-center text-muted-foreground">
                  <Bot className="mb-3 h-10 w-10" />
                  <p className="text-sm font-medium">JARVIS AI Agent</p>
                  <p className="mt-1 text-xs">Open the sidebar to pick or start a chat</p>
                </div>
              )}
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}
