import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCircle2, XCircle, RotateCcw, ClipboardCheck, FileText, Info, Check } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { notificationsApi } from '@/api/notifications'
import type { InAppNotification } from '@/types/notifications'

const typeIcons: Record<string, React.ElementType> = {
  approval: ClipboardCheck,
  info: FileText,
  warning: Info,
}

const titleIcons: Record<string, React.ElementType> = {
  approved: CheckCircle2,
  rejected: XCircle,
  returned: RotateCcw,
}

function getIcon(notification: InAppNotification) {
  // Check title for specific status keywords
  const lower = notification.title.toLowerCase()
  for (const [keyword, Icon] of Object.entries(titleIcons)) {
    if (lower.includes(keyword)) return Icon
  }
  return typeIcons[notification.type] || Info
}

function timeAgo(dateStr: string): string {
  const now = new Date()
  const date = new Date(dateStr)
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString('ro-RO')
}

export function NotificationBell() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  // Poll unread count every 30s
  const { data: countData } = useQuery({
    queryKey: ['notification-unread-count'],
    queryFn: () => notificationsApi.getUnreadCount(),
    refetchInterval: 30000,
  })

  // Fetch notifications when popover opens
  const { data: listData, isLoading } = useQuery({
    queryKey: ['notifications-list'],
    queryFn: () => notificationsApi.getNotifications({ limit: 20 }),
    enabled: open,
    refetchOnMount: 'always',
  })

  const markReadMutation = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-unread-count'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-list'] })
    },
  })

  const markAllReadMutation = useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-unread-count'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-list'] })
    },
  })

  const unreadCount = countData?.count ?? 0
  const notifications = listData?.notifications ?? []

  const handleClick = (n: InAppNotification) => {
    if (!n.is_read) {
      markReadMutation.mutate(n.id)
    }
    if (n.link) {
      setOpen(false)
      navigate(n.link)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className="relative flex items-center justify-center rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-white">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0" sideOffset={8}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3">
          <h4 className="text-sm font-semibold">Notifications</h4>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-auto px-2 py-1 text-xs"
              onClick={() => markAllReadMutation.mutate()}
              disabled={markAllReadMutation.isPending}
            >
              <Check className="mr-1 h-3 w-3" />
              Mark all read
            </Button>
          )}
        </div>
        <Separator />

        {/* List */}
        <ScrollArea className="max-h-80">
          {isLoading ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              Loading...
            </div>
          ) : notifications.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              No notifications
            </div>
          ) : (
            <div className="divide-y">
              {notifications.map((n) => {
                const Icon = getIcon(n)
                return (
                  <button
                    key={n.id}
                    onClick={() => handleClick(n)}
                    className={cn(
                      'flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-accent',
                      !n.is_read && 'bg-accent/50',
                    )}
                  >
                    <Icon className={cn(
                      'mt-0.5 h-4 w-4 shrink-0',
                      !n.is_read ? 'text-primary' : 'text-muted-foreground',
                    )} />
                    <div className="min-w-0 flex-1">
                      <p className={cn(
                        'truncate text-sm',
                        !n.is_read && 'font-medium',
                      )}>
                        {n.title}
                      </p>
                      {n.message && (
                        <p className="mt-0.5 truncate text-xs text-muted-foreground">
                          {n.message}
                        </p>
                      )}
                      <p className="mt-1 text-xs text-muted-foreground">
                        {timeAgo(n.created_at)}
                      </p>
                    </div>
                    {!n.is_read && (
                      <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
