import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Hash, Lock, Megaphone, Users, MessageCircle, Search, X, Building2, GitBranch } from 'lucide-react'
import { digestApi } from '@/api/digest'
import { organizationApi } from '@/api/organization'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { DigestChannel } from '@/types/digest'
import ChannelView from './ChannelView'

type AudienceMode = 'everyone' | 'levels' | 'manual'

interface TargetItem {
  target_type: 'all' | 'company' | 'node'
  company_id?: number
  node_id?: number
  label: string
}

export default function Digest() {
  const queryClient = useQueryClient()
  const [selectedChannel, setSelectedChannel] = useState<DigestChannel | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [newChannel, setNewChannel] = useState({ name: '', description: '', type: 'general', is_private: false })
  const [audienceMode, setAudienceMode] = useState<AudienceMode>('everyone')
  const [targets, setTargets] = useState<TargetItem[]>([])
  const [inviteSearch, setInviteSearch] = useState('')
  const [invitedUsers, setInvitedUsers] = useState<{ id: number; name: string; email: string }[]>([])

  const { data: channelsRes, isLoading } = useQuery({
    queryKey: ['digest-channels'],
    queryFn: digestApi.getChannels,
    refetchInterval: 30_000,
  })
  const channels = channelsRes?.data ?? []

  // Org data for level picker
  const { data: companiesRes } = useQuery({
    queryKey: ['companies-config'],
    queryFn: organizationApi.getCompaniesConfig,
    enabled: showCreate,
  })
  const companies = companiesRes ?? []

  const { data: nodesRes } = useQuery({
    queryKey: ['structure-nodes'],
    queryFn: organizationApi.getStructureNodes,
    enabled: showCreate,
  })
  const nodes = nodesRes ?? []

  // User search for manual invite
  const { data: searchRes } = useQuery({
    queryKey: ['digest-user-search', inviteSearch],
    queryFn: () => digestApi.searchUsers(inviteSearch),
    enabled: inviteSearch.length >= 2,
  })
  const searchResults = (searchRes?.data ?? []).filter(u => !invitedUsers.some(iu => iu.id === u.id))

  // Build tree structure for level picker
  const companyTree = useMemo(() => {
    return companies.map(c => ({
      ...c,
      nodes: nodes.filter(n => n.company_id === c.id && n.level === 1).map(l1 => ({
        ...l1,
        children: nodes.filter(n => n.parent_id === l1.id).map(l2 => ({
          ...l2,
          children: nodes.filter(n => n.parent_id === l2.id),
        })),
      })),
    }))
  }, [companies, nodes])

  const createMutation = useMutation({
    mutationFn: () => {
      const finalTargets = audienceMode === 'everyone'
        ? [{ target_type: 'all' as const }]
        : audienceMode === 'levels'
          ? targets.map(t => ({ target_type: t.target_type, company_id: t.company_id, node_id: t.node_id }))
          : undefined

      return digestApi.createChannel({
        ...newChannel,
        is_private: audienceMode === 'manual' || newChannel.is_private,
        targets: finalTargets,
      }).then(async (res) => {
        // If manual mode, add invited users
        if (audienceMode === 'manual' && res.data) {
          for (const u of invitedUsers) {
            await digestApi.addMember(res.data.id, u.id)
          }
        }
        return res
      })
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['digest-channels'] })
      setShowCreate(false)
      resetForm()
      if (res.data) setSelectedChannel(res.data)
    },
  })

  const resetForm = () => {
    setNewChannel({ name: '', description: '', type: 'general', is_private: false })
    setAudienceMode('everyone')
    setTargets([])
    setInviteSearch('')
    setInvitedUsers([])
  }

  const toggleTarget = (item: TargetItem) => {
    const key = item.node_id ? `node-${item.node_id}` : `company-${item.company_id}`
    const exists = targets.some(t =>
      t.node_id ? `node-${t.node_id}` === key : `company-${t.company_id}` === key
    )
    if (exists) {
      setTargets(targets.filter(t =>
        !(t.node_id ? `node-${t.node_id}` === key : `company-${t.company_id}` === key)
      ))
    } else {
      setTargets([...targets, item])
    }
  }

  const isTargetSelected = (item: { node_id?: number; company_id?: number }) => {
    if (item.node_id) return targets.some(t => t.node_id === item.node_id)
    if (item.company_id) return targets.some(t => t.company_id === item.company_id && !t.node_id)
    return false
  }

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
      <Dialog open={showCreate} onOpenChange={(v) => { setShowCreate(v); if (!v) resetForm() }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
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

            {/* Audience Selection */}
            <div>
              <Label className="mb-2 block">Audience</Label>
              <div className="grid grid-cols-3 gap-2">
                {([
                  { value: 'everyone', label: 'Everyone', icon: Users, desc: 'All users' },
                  { value: 'levels', label: 'By Level', icon: GitBranch, desc: 'Structure nodes' },
                  { value: 'manual', label: 'Manual', icon: Search, desc: 'Invite users' },
                ] as const).map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => setAudienceMode(opt.value)}
                    className={cn(
                      'flex flex-col items-center gap-1 rounded-lg border p-3 text-xs transition-colors',
                      audienceMode === opt.value ? 'border-primary bg-primary/5' : 'hover:bg-accent',
                    )}
                  >
                    <opt.icon className="h-4 w-4" />
                    <span className="font-medium">{opt.label}</span>
                    <span className="text-[10px] text-muted-foreground">{opt.desc}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Level Picker */}
            {audienceMode === 'levels' && (
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Select structure nodes (users in selected nodes + descendants will be added)</Label>
                {targets.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {targets.map((t, i) => (
                      <Badge key={i} variant="secondary" className="gap-1 pr-1">
                        {t.label}
                        <button onClick={() => toggleTarget(t)} className="ml-0.5 hover:text-destructive">
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
                <div className="max-h-48 overflow-y-auto rounded-lg border p-2 space-y-1 text-sm">
                  {companyTree.map(company => (
                    <div key={company.id}>
                      <button
                        onClick={() => toggleTarget({ target_type: 'company', company_id: company.id, label: `${company.company} (All)` })}
                        className={cn(
                          'flex items-center gap-2 w-full rounded px-2 py-1 hover:bg-accent text-left',
                          isTargetSelected({ company_id: company.id }) && 'bg-primary/10 font-medium',
                        )}
                      >
                        <Building2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="truncate">{company.company}</span>
                        <span className="text-[10px] text-muted-foreground ml-auto">L0</span>
                      </button>
                      {company.nodes.map(l1 => (
                        <div key={l1.id} className="ml-4">
                          <button
                            onClick={() => toggleTarget({ target_type: 'node', node_id: l1.id, label: `${l1.name}` })}
                            className={cn(
                              'flex items-center gap-2 w-full rounded px-2 py-1 hover:bg-accent text-left',
                              isTargetSelected({ node_id: l1.id }) && 'bg-primary/10 font-medium',
                            )}
                          >
                            <GitBranch className="h-3 w-3 text-muted-foreground shrink-0" />
                            <span className="truncate">{l1.name}</span>
                            <span className="text-[10px] text-muted-foreground ml-auto">L1</span>
                          </button>
                          {l1.children.map(l2 => (
                            <div key={l2.id} className="ml-4">
                              <button
                                onClick={() => toggleTarget({ target_type: 'node', node_id: l2.id, label: `${l2.name}` })}
                                className={cn(
                                  'flex items-center gap-2 w-full rounded px-2 py-1 hover:bg-accent text-left',
                                  isTargetSelected({ node_id: l2.id }) && 'bg-primary/10 font-medium',
                                )}
                              >
                                <span className="truncate text-xs">{l2.name}</span>
                                <span className="text-[10px] text-muted-foreground ml-auto">L2</span>
                              </button>
                              {l2.children.map(l3 => (
                                <button
                                  key={l3.id}
                                  onClick={() => toggleTarget({ target_type: 'node', node_id: l3.id, label: `${l3.name}` })}
                                  className={cn(
                                    'flex items-center gap-2 w-full rounded px-2 py-0.5 hover:bg-accent text-left ml-4',
                                    isTargetSelected({ node_id: l3.id }) && 'bg-primary/10 font-medium',
                                  )}
                                >
                                  <span className="truncate text-xs">{l3.name}</span>
                                  <span className="text-[10px] text-muted-foreground ml-auto">L3</span>
                                </button>
                              ))}
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  ))}
                  {companyTree.length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-4">No structure nodes configured</p>
                  )}
                </div>
              </div>
            )}

            {/* Manual Invite */}
            {audienceMode === 'manual' && (
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Search and invite individual users</Label>
                {invitedUsers.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {invitedUsers.map(u => (
                      <Badge key={u.id} variant="secondary" className="gap-1 pr-1">
                        {u.name}
                        <button onClick={() => setInvitedUsers(invitedUsers.filter(x => x.id !== u.id))} className="ml-0.5 hover:text-destructive">
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    value={inviteSearch}
                    onChange={(e) => setInviteSearch(e.target.value)}
                    placeholder="Search by name or email..."
                    className="pl-9"
                  />
                </div>
                {searchResults.length > 0 && (
                  <div className="max-h-36 overflow-y-auto rounded-lg border divide-y">
                    {searchResults.map(u => (
                      <button
                        key={u.id}
                        onClick={() => { setInvitedUsers([...invitedUsers, { id: u.id, name: u.name, email: u.email }]); setInviteSearch('') }}
                        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-accent text-sm"
                      >
                        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary shrink-0">
                          {u.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <div className="font-medium truncate">{u.name}</div>
                          <div className="text-[10px] text-muted-foreground truncate">{u.email}{u.department ? ` · ${u.department}` : ''}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreate(false); resetForm() }}>Cancel</Button>
            <Button
              onClick={() => createMutation.mutate()}
              disabled={!newChannel.name.trim() || createMutation.isPending || (audienceMode === 'levels' && targets.length === 0)}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
