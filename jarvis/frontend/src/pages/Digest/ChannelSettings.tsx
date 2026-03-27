import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Search, Shield, ShieldCheck, Crown, UserMinus, Trash2 } from 'lucide-react'
import { digestApi } from '@/api/digest'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import type { DigestChannel } from '@/types/digest'

interface Props {
  channel: DigestChannel
  onBack: () => void
}

export default function ChannelSettings({ channel, onBack }: Props) {
  const queryClient = useQueryClient()
  const [inviteSearch, setInviteSearch] = useState('')
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const { data: membersRes } = useQuery({
    queryKey: ['digest-members', channel.id],
    queryFn: () => digestApi.getMembers(channel.id),
  })
  const members = membersRes?.data ?? []

  const { data: searchRes } = useQuery({
    queryKey: ['digest-user-search', inviteSearch],
    queryFn: () => digestApi.searchUsers(inviteSearch),
    enabled: inviteSearch.length >= 2,
  })
  const searchResults = (searchRes?.data ?? []).filter(u => !members.some(m => m.user_id === u.id))

  const updateSettings = useMutation({
    mutationFn: (settings: Parameters<typeof digestApi.updateChannelSettings>[1]) =>
      digestApi.updateChannelSettings(channel.id, settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-channels'] })
    },
  })

  const addMember = useMutation({
    mutationFn: (userId: number) => digestApi.addMember(channel.id, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-members', channel.id] })
      queryClient.invalidateQueries({ queryKey: ['digest-channels'] })
      setInviteSearch('')
    },
  })

  const removeMember = useMutation({
    mutationFn: (userId: number) => digestApi.removeMember(channel.id, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-members', channel.id] })
      queryClient.invalidateQueries({ queryKey: ['digest-channels'] })
    },
  })

  const setRole = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) =>
      digestApi.setMemberRole(channel.id, userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-members', channel.id] })
    },
  })

  const clearHistory = useMutation({
    mutationFn: () => digestApi.clearChannelHistory(channel.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-posts', channel.id] })
      setShowClearConfirm(false)
    },
  })

  const deleteChannel = useMutation({
    mutationFn: () => digestApi.deleteChannel(channel.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-channels'] })
      onBack()
    },
  })

  const roleIcon = (role: string) => {
    if (role === 'admin') return <Crown className="h-3.5 w-3.5 text-yellow-500" />
    if (role === 'moderator') return <ShieldCheck className="h-3.5 w-3.5 text-blue-500" />
    return <Shield className="h-3.5 w-3.5 text-muted-foreground" />
  }

  const admins = members.filter(m => m.role === 'admin')
  const moderators = members.filter(m => m.role === 'moderator')
  const regularMembers = members.filter(m => m.role === 'member')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h2 className="text-lg font-semibold">Channel Settings</h2>
      </div>

      {/* Permissions */}
      <div className="rounded-lg border p-4 space-y-4">
        <h3 className="text-sm font-semibold">Permissions</h3>
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-sm">Allow member posts</Label>
            <p className="text-xs text-muted-foreground">If off, only admins/moderators can post</p>
          </div>
          <Switch
            checked={channel.allow_member_posts ?? true}
            onCheckedChange={(v) => updateSettings.mutate({ allow_member_posts: v })}
          />
        </div>
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-sm">Allow reactions</Label>
            <p className="text-xs text-muted-foreground">Members can react to posts with emoji</p>
          </div>
          <Switch
            checked={channel.allow_reactions ?? true}
            onCheckedChange={(v) => updateSettings.mutate({ allow_reactions: v })}
          />
        </div>
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-sm">Allow images</Label>
            <p className="text-xs text-muted-foreground">Members can attach images to posts</p>
          </div>
          <Switch
            checked={channel.allow_images ?? true}
            onCheckedChange={(v) => updateSettings.mutate({ allow_images: v })}
          />
        </div>
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-sm">Auto-delete messages</Label>
            <p className="text-xs text-muted-foreground">Automatically delete messages after N days</p>
          </div>
          <Select
            value={String(channel.auto_delete_days ?? 'never')}
            onValueChange={(v) => updateSettings.mutate({ auto_delete_days: v === 'never' ? null : Number(v) })}
          >
            <SelectTrigger className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="never">Never</SelectItem>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
              <SelectItem value="365">1 year</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Members */}
      <div className="rounded-lg border p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Members ({members.length})</h3>
        </div>

        {/* Invite */}
        <div className="space-y-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={inviteSearch}
              onChange={(e) => setInviteSearch(e.target.value)}
              placeholder="Invite user by name or email..."
              className="pl-9"
            />
          </div>
          {searchResults.length > 0 && (
            <div className="max-h-32 overflow-y-auto rounded-lg border divide-y">
              {searchResults.map(u => (
                <button
                  key={u.id}
                  onClick={() => addMember.mutate(u.id)}
                  className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-accent text-sm"
                >
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary shrink-0">
                    {u.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium truncate">{u.name}</div>
                    <div className="text-[10px] text-muted-foreground truncate">{u.email}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Member list by role */}
        {[
          { label: 'Admins', items: admins },
          { label: 'Moderators', items: moderators },
          { label: 'Members', items: regularMembers },
        ].map(group => group.items.length > 0 && (
          <div key={group.label} className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{group.label}</p>
            {group.items.map(m => (
              <div key={m.user_id} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent/40 group/member">
                {roleIcon(m.role)}
                <div className="flex-1 min-w-0">
                  <span className="text-sm truncate block">{m.user_name}</span>
                  <span className="text-[10px] text-muted-foreground truncate block">{m.user_email}</span>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover/member:opacity-100 transition-opacity">
                  <Select
                    value={m.role}
                    onValueChange={(v) => setRole.mutate({ userId: m.user_id, role: v })}
                  >
                    <SelectTrigger className="h-7 w-24 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admin">Admin</SelectItem>
                      <SelectItem value="moderator">Moderator</SelectItem>
                      <SelectItem value="member">Member</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive"
                    onClick={() => removeMember.mutate(m.user_id)}
                  >
                    <UserMinus className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Danger Zone */}
      <div className="rounded-lg border border-destructive/30 p-4 space-y-3">
        <h3 className="text-sm font-semibold text-destructive">Danger Zone</h3>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm">Clear message history</p>
            <p className="text-xs text-muted-foreground">Delete all messages in this channel</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => setShowClearConfirm(true)}>
            <Trash2 className="h-3.5 w-3.5 mr-1" /> Clear
          </Button>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm">Delete channel</p>
            <p className="text-xs text-muted-foreground">Permanently delete this channel and all data</p>
          </div>
          <Button variant="destructive" size="sm" onClick={() => setShowDeleteConfirm(true)}>
            <Trash2 className="h-3.5 w-3.5 mr-1" /> Delete
          </Button>
        </div>
      </div>

      {/* Clear Confirm */}
      <Dialog open={showClearConfirm} onOpenChange={setShowClearConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Clear Message History</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will delete all messages in <strong>{channel.name}</strong>. This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowClearConfirm(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => clearHistory.mutate()} disabled={clearHistory.isPending}>
              Clear All Messages
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Channel</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will permanently delete <strong>{channel.name}</strong> and all its messages, polls, and reactions.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteConfirm(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteChannel.mutate()} disabled={deleteChannel.isPending}>
              Delete Channel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
