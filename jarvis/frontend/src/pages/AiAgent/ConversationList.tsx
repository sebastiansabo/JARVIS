import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Archive, Trash2, MoreVertical, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import { aiAgentApi } from '@/api/aiAgent'
import { useAiAgentStore } from '@/stores/aiAgentStore'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { toast } from 'sonner'
import type { Conversation } from '@/types/aiAgent'

export function ConversationList() {
  const queryClient = useQueryClient()
  const selectedConversationId = useAiAgentStore((s) => s.selectedConversationId)
  const setConversation = useAiAgentStore((s) => s.setConversation)

  const { data: conversations, isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: aiAgentApi.getConversations,
  })

  const createMutation = useMutation({
    mutationFn: () => aiAgentApi.createConversation(),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setConversation(data.id)
    },
    onError: () => toast.error('Failed to create conversation'),
  })

  const archiveMutation = useMutation({
    mutationFn: (id: number) => aiAgentApi.archiveConversation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      toast.success('Conversation archived')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => aiAgentApi.deleteConversation(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (selectedConversationId === id) setConversation(null)
      toast.success('Conversation deleted')
    },
  })

  const activeConversations = (conversations ?? []).filter((c: Conversation) => c.status === 'active')

  return (
    <div className="flex h-full flex-col">
      <div className="border-b p-3">
        <Button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="w-full"
          size="sm"
        >
          <Plus className="mr-2 h-4 w-4" />
          New Chat
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-1 p-2">
          {isLoading &&
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="space-y-1 rounded-md p-3">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ))}

          {!isLoading && activeConversations.length === 0 && (
            <div className="p-4 text-center text-sm text-muted-foreground">
              No conversations yet. Start a new chat.
            </div>
          )}

          {activeConversations.map((conv: Conversation) => (
            <div
              key={conv.id}
              onClick={() => setConversation(conv.id)}
              className={cn(
                'group flex cursor-pointer items-center justify-between rounded-md px-3 py-2 transition-colors',
                selectedConversationId === conv.id
                  ? 'bg-primary/10 text-primary'
                  : 'hover:bg-accent'
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-3 w-3 shrink-0" />
                  <span className="truncate text-sm font-medium">
                    {conv.title || 'New conversation'}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {conv.message_count} msgs
                  {conv.total_cost && Number(conv.total_cost) > 0 && ` · $${conv.total_cost}`}
                </div>
              </div>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 group-hover:opacity-100"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MoreVertical className="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      archiveMutation.mutate(conv.id)
                    }}
                  >
                    <Archive className="mr-2 h-4 w-4" />
                    Archive
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="text-destructive"
                    onClick={(e) => {
                      e.stopPropagation()
                      deleteMutation.mutate(conv.id)
                    }}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
