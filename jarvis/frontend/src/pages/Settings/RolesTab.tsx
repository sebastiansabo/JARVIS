import { Fragment, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { rolesApi } from '@/api/roles'
import { toast } from 'sonner'
import type { Role, PermissionMatrix, RolePermission } from '@/types/roles'

export default function RolesTab() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editRole, setEditRole] = useState<Role | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: roles = [], isLoading: rolesLoading } = useQuery({
    queryKey: ['settings', 'roles'],
    queryFn: rolesApi.getRoles,
  })

  const { data: matrix } = useQuery({
    queryKey: ['settings', 'permissionMatrix'],
    queryFn: rolesApi.getPermissionMatrix,
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<Role>) => rolesApi.createRole(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'roles'] })
      queryClient.invalidateQueries({ queryKey: ['settings', 'permissionMatrix'] })
      setShowAdd(false)
      toast.success('Role created')
    },
    onError: () => toast.error('Failed to create role'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Role> }) => rolesApi.updateRole(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'roles'] })
      queryClient.invalidateQueries({ queryKey: ['settings', 'permissionMatrix'] })
      setEditRole(null)
      toast.success('Role updated')
    },
    onError: () => toast.error('Failed to update role'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => rolesApi.deleteRole(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'roles'] })
      queryClient.invalidateQueries({ queryKey: ['settings', 'permissionMatrix'] })
      setDeleteId(null)
      toast.success('Role deleted')
    },
    onError: () => toast.error('Failed to delete role'),
  })

  const permMutation = useMutation({
    mutationFn: ({ permId, roleId, granted }: { permId: number; roleId: number; granted: boolean }) =>
      rolesApi.setSinglePermissionV2(permId, roleId, { scope: 'all', granted }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'permissionMatrix'] })
    },
    onError: () => toast.error('Failed to update permission'),
  })

  return (
    <div className="space-y-6">
      {/* Roles List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Roles</CardTitle>
            <Button size="sm" onClick={() => setShowAdd(true)}>
              <Plus className="mr-1.5 h-4 w-4" />
              Add Role
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {rolesLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-10 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : roles.length === 0 ? (
            <EmptyState title="No roles" description="Add your first role." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="w-24">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {roles.map((role) => (
                  <TableRow key={role.id}>
                    <TableCell className="font-medium">{role.name}</TableCell>
                    <TableCell className="text-muted-foreground">{role.description || '-'}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" onClick={() => setEditRole(role)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => setDeleteId(role.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Permission Matrix */}
      {matrix && <PermissionMatrixView matrix={matrix} roles={roles} onToggle={permMutation.mutate} />}

      {/* Role Form Dialog (create + edit) */}
      <RoleFormDialog
        open={showAdd || !!editRole}
        role={editRole}
        onClose={() => { setShowAdd(false); setEditRole(null) }}
        onSave={(data) => {
          if (editRole) {
            updateMutation.mutate({ id: editRole.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Role"
        description="This will remove the role and its permissions."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </div>
  )
}

function PermissionMatrixView({
  matrix,
  roles,
  onToggle,
}: {
  matrix: PermissionMatrix
  roles: Role[]
  onToggle: (args: { permId: number; roleId: number; granted: boolean }) => void
}) {
  const modules = matrix.modules || []
  // role_permissions may come from matrix response as a separate field
  const rolePerms = (matrix as unknown as Record<string, unknown>).role_permissions as Record<number, Record<number, RolePermission>> | undefined

  const isGranted = (permId: number, roleId: number): boolean => {
    if (!rolePerms) return false
    const rp = rolePerms[roleId]
    if (!rp) return false
    const perm = rp[permId]
    return perm?.granted ?? false
  }

  // Get all permission IDs for a module
  const getModulePermIds = (mod: typeof modules[0]) =>
    mod.entities.flatMap((e) => e.actions.map((a) => a.id))

  // Check if all perms in a module are granted for a role
  const isModuleAllGranted = (mod: typeof modules[0], roleId: number) => {
    const ids = getModulePermIds(mod)
    return ids.length > 0 && ids.every((id) => isGranted(id, roleId))
  }

  // Check if some (but not all) perms in a module are granted for a role
  const isModuleSomeGranted = (mod: typeof modules[0], roleId: number) => {
    const ids = getModulePermIds(mod)
    const grantedCount = ids.filter((id) => isGranted(id, roleId)).length
    return grantedCount > 0 && grantedCount < ids.length
  }

  // Toggle all perms in a module for a role
  const toggleModule = (mod: typeof modules[0], roleId: number) => {
    const grant = !isModuleAllGranted(mod, roleId)
    const ids = getModulePermIds(mod)
    ids.forEach((permId) => {
      if (isGranted(permId, roleId) !== grant) {
        onToggle({ permId, roleId, granted: grant })
      }
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Permission Matrix</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 z-10 bg-card">Permission</TableHead>
                {roles.map((r) => (
                  <TableHead key={r.id} className="text-center">
                    {r.name}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {modules.map((mod) => (
                <Fragment key={mod.key}>
                  <TableRow>
                    <TableCell className="bg-muted/50 font-semibold">
                      {mod.label}
                    </TableCell>
                    {roles.map((role) => (
                      <TableCell key={role.id} className="bg-muted/50 text-center">
                        <Checkbox
                          checked={isModuleAllGranted(mod, role.id) ? true : isModuleSomeGranted(mod, role.id) ? 'indeterminate' : false}
                          onCheckedChange={() => toggleModule(mod, role.id)}
                        />
                      </TableCell>
                    ))}
                  </TableRow>
                  {mod.entities.flatMap((entity) =>
                    entity.actions.map((action) => (
                      <TableRow key={action.id}>
                        <TableCell className="sticky left-0 z-10 bg-card text-sm">
                          {entity.label} &mdash; {action.label}
                        </TableCell>
                        {roles.map((role) => (
                          <TableCell key={role.id} className="text-center">
                            <Checkbox
                              checked={isGranted(action.id, role.id)}
                              onCheckedChange={(checked) =>
                                onToggle({ permId: action.id, roleId: role.id, granted: !!checked })
                              }
                            />
                          </TableCell>
                        ))}
                      </TableRow>
                    )),
                  )}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}

function RoleFormDialog({ open, role, onClose, onSave, isPending }: {
  open: boolean; role: Role | null; onClose: () => void
  onSave: (data: Partial<Role>) => void; isPending: boolean
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const resetForm = () => {
    if (role) {
      setName(role.name); setDescription(role.description || '')
    } else {
      setName(''); setDescription('')
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-sm" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{role ? 'Edit Role' : 'Add Role'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Description</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={isPending || !name} onClick={() => onSave({ name, description })}>
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
