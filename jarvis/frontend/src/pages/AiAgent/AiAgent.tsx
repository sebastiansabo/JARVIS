import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { ConversationList } from './ConversationList'
import { ChatWindow } from './ChatWindow'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'

export default function AiAgent() {
  const isSidebarOpen = useAiAgentStore((s) => s.isSidebarOpen)
  const setSidebarOpen = useAiAgentStore((s) => s.setSidebarOpen)
  const toggleSidebar = useAiAgentStore((s) => s.toggleSidebar)

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] md:h-[calc(100vh)]">
      {/* Desktop conversation sidebar */}
      <div className="hidden w-72 border-r md:block">
        <ConversationList />
      </div>

      {/* Mobile conversation sidebar */}
      <Sheet open={isSidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetTitle className="sr-only">Conversations</SheetTitle>
          <ConversationList />
        </SheetContent>
      </Sheet>

      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Mobile toggle button */}
        <div className="flex items-center border-b px-2 py-1 md:hidden">
          <Button variant="ghost" size="icon" onClick={toggleSidebar}>
            {isSidebarOpen ? (
              <PanelLeftClose className="h-4 w-4" />
            ) : (
              <PanelLeftOpen className="h-4 w-4" />
            )}
          </Button>
        </div>

        <ChatWindow />
      </div>
    </div>
  )
}
