import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Shield, Trash2, User, Users } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { dmsApi } from '@/api/dms'
import { usersApi } from '@/api/users'
import { rolesApi } from '@/api/roles'
import type { DmsFolderAclEntry, DmsFolder } from '@/types/dms'

interface FolderACLDialogProps {
  folder: DmsFolder | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const PERMS = ['can_view', 'can_add', 'can_edit', 'can_delete', 'can_manage'] as const
const PERM_LABELS: Record<string, string> = {
  can_view: 'View',
  can_add: 'Add',
  can_edit: 'Edit',
  can_delete: 'Delete',
  can_manage: 'Manage',
}

export default function FolderACLDialog({ folder, open, onOpenChange }: FolderACLDialogProps) {
  const queryClient = useQueryClient()
  const [addMode, setAddMode] = useState<'user' | 'role' | null>(null)
  const [selectedUserId, setSelectedUserId] = useState<string>('')
  const [selectedRoleId, setSelectedRoleId] = useState<string>('')
  const [newPerms, setNewPerms] = useState<Record<string, boolean>>({
    can_view: true, can_add: false, can_edit: false, can_delete: false, can_manage: false,
  })

  const { data: aclData, isLoading } = useQuery({
    queryKey: ['dms-folder-acl', folder?.id],
    queryFn: () => dmsApi.getFolderAcl(folder!.id),
    enabled: !!folder && open,
  })

  const { data: usersData } = useQuery({
    queryKey: ['users-list'],
    queryFn: () => usersApi.getUsers(),
    enabled: open && addMode === 'user',
  })

  const { data: rolesData } = useQuery({
    queryKey: ['roles-list'],
    queryFn: () => rolesApi.getRoles(),
    enabled: open && addMode === 'role',
  })

  const setAclMutation = useMutation({
    mutationFn: (data: { user_id?: number; role_id?: number } & Record<string, boolean>) =>
      dmsApi.setFolderAcl(folder!.id, data),
    onSuccess: () => {
      toast.success('Permission updated')
      queryClient.invalidateQueries({ queryKey: ['dms-folder-acl', folder?.id] })
      setAddMode(null)
      setSelectedUserId('')
      setSelectedRoleId('')
    },
    onError: () => toast.error('Failed to update permission'),
  })

  const removeMutation = useMutation({
    mutationFn: (aclId: number) => dmsApi.removeFolderAcl(folder!.id, aclId),
    onSuccess: () => {
      toast.success('Permission removed')
      queryClient.invalidateQueries({ queryKey: ['dms-folder-acl', folder?.id] })
    },
    onError: () => toast.error('Failed to remove permission'),
  })

  const togglePerm = (entry: DmsFolderAclEntry, perm: string) => {
    const data: Record<string, unknown> = {}
    if (entry.user_id) data.user_id = entry.user_id
    if (entry.role_id) data.role_id = entry.role_id
    for (const p of PERMS) data[p] = p === perm ? !entry[p] : entry[p]
    setAclMutation.mutate(data as Parameters<typeof setAclMutation.mutate>[0])
  }

  const entries: DmsFolderAclEntry[] = aclData?.acl || []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Permissions — {folder?.name}
          </DialogTitle>
        </DialogHeader>

        {folder?.inherit_permissions && (
          <div className="text-xs text-muted-foreground bg-muted/50 rounded px-3 py-2">
            This folder inherits permissions from its parent. Explicit entries below override inherited ones.
          </div>
        )}

        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : entries.length === 0 && !addMode ? (
          <div className="text-center py-6 text-sm text-muted-foreground">
            No explicit permissions set. {folder?.inherit_permissions ? 'Using inherited permissions.' : 'No one has access.'}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User / Role</TableHead>
                {PERMS.map((p) => (
                  <TableHead key={p} className="text-center w-16">{PERM_LABELS[p]}</TableHead>
                ))}
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {entry.user_id ? (
                        <>
                          <User className="h-3 w-3 text-muted-foreground" />
                          <span className="text-sm">{entry.user_name}</span>
                          <span className="text-xs text-muted-foreground">{entry.user_email}</span>
                        </>
                      ) : (
                        <>
                          <Users className="h-3 w-3 text-muted-foreground" />
                          <Badge variant="outline">{entry.role_name}</Badge>
                        </>
                      )}
                    </div>
                  </TableCell>
                  {PERMS.map((p) => (
                    <TableCell key={p} className="text-center">
                      <Checkbox
                        checked={entry[p]}
                        onCheckedChange={() => togglePerm(entry, p)}
                      />
                    </TableCell>
                  ))}
                  <TableCell>
                    <Button
                      variant="ghost" size="icon" className="h-6 w-6"
                      onClick={() => removeMutation.mutate(entry.id)}
                    >
                      <Trash2 className="h-3 w-3 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {/* Add new entry */}
        {addMode ? (
          <div className="border rounded-md p-3 space-y-3">
            <div className="flex gap-2">
              {addMode === 'user' && (
                <Select value={selectedUserId} onValueChange={setSelectedUserId}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select user..." />
                  </SelectTrigger>
                  <SelectContent>
                    {(usersData || []).map((u: { id: number; name: string; email: string }) => (
                      <SelectItem key={u.id} value={u.id.toString()}>
                        {u.name} ({u.email})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              {addMode === 'role' && (
                <Select value={selectedRoleId} onValueChange={setSelectedRoleId}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select role..." />
                  </SelectTrigger>
                  <SelectContent>
                    {(rolesData || []).map((r: { id: number; name: string }) => (
                      <SelectItem key={r.id} value={r.id.toString()}>
                        {r.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            <div className="flex items-center gap-4">
              {PERMS.map((p) => (
                <label key={p} className="flex items-center gap-1 text-sm">
                  <Checkbox
                    checked={newPerms[p] || false}
                    onCheckedChange={(v) => setNewPerms((prev) => ({ ...prev, [p]: v === true }))}
                  />
                  {PERM_LABELS[p]}
                </label>
              ))}
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={(!selectedUserId && !selectedRoleId)}
                onClick={() => {
                  const data: Record<string, unknown> = { ...newPerms }
                  if (addMode === 'user') data.user_id = Number(selectedUserId)
                  if (addMode === 'role') data.role_id = Number(selectedRoleId)
                  setAclMutation.mutate(data as Parameters<typeof setAclMutation.mutate>[0])
                }}
              >
                Grant
              </Button>
              <Button size="sm" variant="outline" onClick={() => setAddMode(null)}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setAddMode('user')}>
              <User className="h-3 w-3 mr-1" /> Add User
            </Button>
            <Button size="sm" variant="outline" onClick={() => setAddMode('role')}>
              <Users className="h-3 w-3 mr-1" /> Add Role
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
