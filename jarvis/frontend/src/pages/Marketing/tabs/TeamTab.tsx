import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Plus, Trash2 } from 'lucide-react'
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

  const addMut = useMutation({
    mutationFn: () => marketingApi.addMember(projectId, { user_id: Number(addUserId), role: addRole }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-members', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
      setShowAdd(false)
      setAddUserId('')
    },
  })

  const removeMut = useMutation({
    mutationFn: (memberId: number) => marketingApi.removeMember(projectId, memberId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mkt-members', projectId] })
      queryClient.invalidateQueries({ queryKey: ['mkt-project', projectId] })
    },
  })

  const updateRoleMut = useMutation({
    mutationFn: ({ memberId, role }: { memberId: number; role: string }) =>
      marketingApi.updateMember(projectId, memberId, { role }),
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
        <div className="text-center py-8 text-muted-foreground">No team members.</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
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
                      onValueChange={(v) => updateRoleMut.mutate({ memberId: m.id, role: v })}
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
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Add Team Member</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>User *</Label>
              <Select value={addUserId} onValueChange={setAddUserId}>
                <SelectTrigger><SelectValue placeholder="Select user" /></SelectTrigger>
                <SelectContent>
                  {users.filter((u) => u.is_active && !existingUserIds.has(u.id)).map((u) => (
                    <SelectItem key={u.id} value={String(u.id)}>{u.name} ({u.role_name})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
