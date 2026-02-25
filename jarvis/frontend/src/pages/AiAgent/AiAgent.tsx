import { useCallback, useState } from 'react'
import { useQueryClient, useMutation } from '@tanstack/react-query'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { ConversationList } from './ConversationList'
import { ChatWindow } from './ChatWindow'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { aiAgentApi } from '@/api/aiAgent'
import { toast } from 'sonner'

export default function AiAgent() {
  const queryClient = useQueryClient()
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [pendingMessage, setPendingMessage] = useState<string | null>(null)

  const createAndSend = useMutation({
    mutationFn: (message: string) => aiAgentApi.createConversation(message),
    onSuccess: (data, message) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setSelectedConversationId(data.id)
      setPendingMessage(message)
    },
    onError: () => toast.error('Failed to create conversation'),
  })

  const handleSuggestionClick = useCallback((text: string) => {
    createAndSend.mutate(text)
  }, [createAndSend])

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] md:h-[calc(100vh)]">
      {/* Desktop conversation sidebar */}
      <div className="hidden w-72 border-r md:block">
        <ConversationList
          selectedConversationId={selectedConversationId}
          onSelect={setSelectedConversationId}
        />
      </div>

      {/* Mobile conversation sidebar */}
      <Sheet open={isSidebarOpen} onOpenChange={setIsSidebarOpen}>
        <SheetContent side="left" className="w-72 p-0" aria-describedby={undefined}>
          <SheetTitle className="sr-only">Conversations</SheetTitle>
          <ConversationList
            selectedConversationId={selectedConversationId}
            onSelect={(id) => { setSelectedConversationId(id); setIsSidebarOpen(false) }}
          />
        </SheetContent>
      </Sheet>

      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Mobile toggle button */}
        <div className="flex items-center border-b px-2 py-1 md:hidden">
          <Button variant="ghost" size="icon" onClick={() => setIsSidebarOpen(!isSidebarOpen)}>
            {isSidebarOpen ? (
              <PanelLeftClose className="h-4 w-4" />
            ) : (
              <PanelLeftOpen className="h-4 w-4" />
            )}
          </Button>
        </div>

        <ChatWindow
          conversationId={selectedConversationId}
          pendingMessage={pendingMessage}
          onPendingConsumed={() => setPendingMessage(null)}
          onSuggestionClick={handleSuggestionClick}
        />
      </div>
    </div>
  )
}
