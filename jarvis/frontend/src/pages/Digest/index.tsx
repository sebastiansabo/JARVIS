import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Hash, Lock, Megaphone, Users, MessageCircle } from 'lucide-react'
import { digestApi } from '@/api/digest'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { DigestChannel } from '@/types/digest'
import ChannelView from './ChannelView'

export default function Digest() {
  const queryClient = useQueryClient()
  const [selectedChannel, setSelectedChannel] = useState<DigestChannel | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newChannel, setNewChannel] = useState({ name: '', description: '', type: 'general', is_private: false })

  const { data: channelsRes, isLoading } = useQuery({
    queryKey: ['digest-channels'],
    queryFn: digestApi.getChannels,
    refetchInterval: 30_000,
  })
  const channels = channelsRes?.data ?? []

  const createMutation = useMutation({
    mutationFn: () => digestApi.createChannel(newChannel),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['digest-channels'] })
      setShowCreate(false)
      setNewChannel({ name: '', description: '', type: 'general', is_private: false })
      if (res.data) setSelectedChannel(res.data)
    },
  })

  const channelIcon = (ch: DigestChannel) => {
    if (ch.is_private) return <Lock className="h-4 w-4 shrink-0 text-muted-foreground" />
    if (ch.type === 'announcement') return <Megaphone className="h-4 w-4 shrink-0 text-muted-foreground" />
    return <Hash className="h-4 w-4 shrink-0 text-muted-foreground" />
  }

  if (selectedChannel) {
    return <ChannelView channel={selectedChannel} onBack={() => setSelectedChannel(null)} />
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Digest</h1>
          <p className="text-sm text-muted-foreground">Communication channels for your organization</p>
        </div>
        <Button onClick={() => setShowCreate(true)} size="sm">
          <Plus className="mr-1.5 h-4 w-4" /> New Channel
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1,2,3].map(i => <div key={i} className="h-28 animate-pulse rounded-lg bg-muted" />)}
        </div>
      ) : channels.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <MessageCircle className="h-12 w-12 text-muted-foreground/40 mb-3" />
          <p className="text-lg font-medium">No channels yet</p>
          <p className="text-sm text-muted-foreground mt-1">Create the first channel to get started</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {channels.map((ch) => (
            <button
              key={ch.id}
              onClick={() => setSelectedChannel(ch)}
              className={cn(
                'flex flex-col gap-2 rounded-lg border p-4 text-left transition-colors hover:bg-accent',
                ch.unread_count > 0 && 'border-primary/30 bg-primary/5',
              )}
            >
              <div className="flex items-center gap-2">
                {channelIcon(ch)}
                <span className="font-medium truncate">{ch.name}</span>
                {ch.unread_count > 0 && (
                  <Badge variant="default" className="ml-auto text-xs">{ch.unread_count}</Badge>
                )}
              </div>
              {ch.description && (
                <p className="text-xs text-muted-foreground line-clamp-2">{ch.description}</p>
              )}
              <div className="flex items-center gap-3 text-xs text-muted-foreground mt-auto">
                <span className="flex items-center gap-1"><Users className="h-3 w-3" /> {ch.member_count}</span>
                <span className="flex items-center gap-1"><MessageCircle className="h-3 w-3" /> {ch.post_count}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Create Channel Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Channel</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Name</Label>
              <Input
                value={newChannel.name}
                onChange={(e) => setNewChannel({ ...newChannel, name: e.target.value })}
                placeholder="e.g. general, announcements"
              />
            </div>
            <div>
              <Label>Description</Label>
              <Textarea
                value={newChannel.description}
                onChange={(e) => setNewChannel({ ...newChannel, description: e.target.value })}
                placeholder="What's this channel about?"
                rows={2}
              />
            </div>
            <div>
              <Label>Type</Label>
              <Select value={newChannel.type} onValueChange={(v) => setNewChannel({ ...newChannel, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="general">General</SelectItem>
                  <SelectItem value="announcement">Announcement</SelectItem>
                  <SelectItem value="department">Department</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                checked={newChannel.is_private}
                onCheckedChange={(v) => setNewChannel({ ...newChannel, is_private: v })}
              />
              <Label>Private channel</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMutation.mutate()} disabled={!newChannel.name.trim() || createMutation.isPending}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
