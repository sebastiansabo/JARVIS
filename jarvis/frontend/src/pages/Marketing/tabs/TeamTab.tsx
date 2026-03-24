import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Plus, Trash2, Users, Search, Check, ChevronsUpDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { marketingApi } from '@/api/marketing'
import { usersApi } from '@/api/users'
import type { UserDetail } from '@/types/users'
import { fmtDate } from './utils'

const PROJECT_ROLES = [
  { value: 'stakeholder', label: 'Stakeholder' },
  { value: 'observer', label: 'Observer' },
  { value: 'owner', label: 'Owner' },
  { value: 'manager', label: 'Manager' },
  { value: 'specialist', label: 'Specialist' },
  { value: 'viewer', label: 'Viewer' },
  { value: 'agency', label: 'Agency' },
]

export function TeamTab({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [addUserId, setAddUserId] = useState('')
  const [addRole, setAddRole] = useState('')
  const [addResponsibility, setAddResponsibility] = useState('')
  const [userSearch, setUserSearch] = useState('')
  const [userPopoverOpen, setUserPopoverOpen] = useState(false)

  const { data } = useQuery({
    queryKey: ['mkt-members', projectId],
    queryFn: () => marketingApi.getMembers(projectId),
  })
  const members = data?.members ?? []

  const { data: usersData } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    enabled: showAdd,
  })
  const users: UserDetail[] = (usersData as UserDetail[] | undefined) ?? []
  const existingUserIds = new Set(members.map((m) => m.user_id))

  const availableUsers = useMemo(() =>
    users.filter((u) => u.is_active && !existingUserIds.has(u.id)),
    [users, existingUserIds]
  )

  const filteredUsers = useMemo(() => {
    if (!userSearch.trim()) return availableUsers
    const q = userSearch.toLowerCase()
    return availableUsers.filter((u) =>
      u.name.toLowerCase().includes(q) || (u.email ?? '').toLowerCase().includes(q)
    )
  }, [availableUsers, userSearch])

  const selectedUser = users.find((u) => String(u.id) === addUserId)

  const addMut = useMutation({
    mutationFn: () => marketingApi.addMember(projectId, {
      user_id: Number(addUserId), role: addRole,
      responsibility: addResponsibility.trim() || undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-members', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      setShowAdd(false)
      setAddUserId('')
      setAddRole('')
      setAddResponsibility('')
      setUserSearch('')
    },
  })

  const removeMut = useMutation({
    mutationFn: (memberId: number) => marketingApi.removeMember(projectId, memberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-members', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
    },
  })

  const updateMemberMut = useMutation({
    mutationFn: ({ memberId, updates }: { memberId: number; updates: { role?: string; responsibility?: string } }) =>
      marketingApi.updateMember(projectId, memberId, updates),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mkt-members', projectId] }),
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Member
        </Button>
      </div>

      {members.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Users className="mx-auto h-8 w-8 mb-2 opacity-40" />
          <div>No team members yet</div>
          <div className="text-xs mt-1">Add stakeholders and observers to this project.</div>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Responsibility</TableHead>
                <TableHead>Added</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="font-medium">{m.user_name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{m.user_email}</TableCell>
                  <TableCell>
                    <Select
                      value={m.role}
                      onValueChange={(v) => updateMemberMut.mutate({ memberId: m.id, updates: { role: v } })}
                    >
                      <SelectTrigger className="w-[120px] h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PROJECT_ROLES.map((r) => (
                          <SelectItem key={r.value} value={r.value} className="text-xs">{r.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell>
                    <Input
                      className="h-8 text-xs min-w-[160px]"
                      placeholder="What will they do?"
                      defaultValue={m.responsibility ?? ''}
                      onBlur={(e) => {
                        const val = e.target.value.trim()
                        if (val !== (m.responsibility ?? ''))
                          updateMemberMut.mutate({ memberId: m.id, updates: { responsibility: val } })
                      }}
                    />
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{fmtDate(m.created_at)}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => removeMut.mutate(m.id)}>
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Add Member Dialog */}
      <Dialog open={showAdd} onOpenChange={(open) => { setShowAdd(open); if (!open) { setAddUserId(''); setAddRole(''); setAddResponsibility(''); setUserSearch('') } }}>
        <DialogContent className="max-w-sm" aria-describedby={undefined}>
          <DialogHeader><DialogTitle>Add Team Member</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>User *</Label>
              <Popover open={userPopoverOpen} onOpenChange={setUserPopoverOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={userPopoverOpen}
                    className="w-full justify-between font-normal"
                  >
                    {selectedUser ? (
                      <span className="truncate">{selectedUser.name}</span>
                    ) : (
                      <span className="text-muted-foreground">Select user...</span>
                    )}
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[320px] p-0" align="start">
                  <div className="flex items-center border-b px-3 py-2">
                    <Search className="h-4 w-4 shrink-0 opacity-50 mr-2" />
                    <Input
                      placeholder="Search by name or email..."
                      value={userSearch}
                      onChange={(e) => setUserSearch(e.target.value)}
                      className="h-8 border-0 p-0 shadow-none focus-visible:ring-0"
                    />
                  </div>
                  <div className="max-h-64 overflow-y-auto p-1">
                    {filteredUsers.length === 0 ? (
                      <div className="py-6 text-center text-sm text-muted-foreground">No users found</div>
                    ) : (
                      filteredUsers.map((u) => (
                        <button
                          key={u.id}
                          className={cn(
                            'flex items-center w-full rounded-sm px-2 py-1.5 text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground',
                            addUserId === String(u.id) && 'bg-accent'
                          )}
                          onClick={() => {
                            setAddUserId(String(u.id))
                            setUserPopoverOpen(false)
                            setUserSearch('')
                          }}
                        >
                          <Check className={cn('mr-2 h-4 w-4', addUserId === String(u.id) ? 'opacity-100' : 'opacity-0')} />
                          <div className="flex flex-col items-start">
                            <span>{u.name}</span>
                            <span className="text-xs text-muted-foreground">{u.email} · {u.role_name}</span>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
            <div className="space-y-1.5">
              <Label>Role</Label>
              <Select value={addRole} onValueChange={setAddRole}>
                <SelectTrigger><SelectValue placeholder="Select role" /></SelectTrigger>
                <SelectContent>
                  {PROJECT_ROLES.map((r) => (
                    <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Responsibility</Label>
              <Input
                value={addResponsibility}
                onChange={(e) => setAddResponsibility(e.target.value)}
                placeholder="e.g. Manages social media campaigns"
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowAdd(false)}>Cancel</Button>
              <Button disabled={!addUserId || !addRole || addMut.isPending} onClick={() => addMut.mutate()}>
                {addMut.isPending ? 'Adding...' : 'Add'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
