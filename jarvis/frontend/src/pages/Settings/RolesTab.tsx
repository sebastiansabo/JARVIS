import { Fragment, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { rolesApi } from '@/api/roles'
import { toast } from 'sonner'
import type { Role, PermissionMatrix, RolePermission } from '@/types/roles'

type PermissionScope = 'deny' | 'own' | 'department' | 'all'

const SCOPE_OPTIONS: { value: PermissionScope; label: string; color: string }[] = [
  { value: 'deny', label: 'Deny', color: 'text-muted-foreground' },
  { value: 'own', label: 'Own', color: 'text-orange-500' },
  { value: 'department', label: 'Dept', color: 'text-blue-500' },
  { value: 'all', label: 'All', color: 'text-green-500' },
]

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
    mutationFn: ({ permId, roleId, scope }: { permId: number; roleId: number; scope: PermissionScope }) =>
      rolesApi.setSinglePermissionV2(permId, roleId, { scope, granted: scope !== 'deny' }),
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
      {matrix && <PermissionMatrixView matrix={matrix} roles={roles} onPermChange={permMutation.mutate} />}

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
  onPermChange,
}: {
  matrix: PermissionMatrix
  roles: Role[]
  onPermChange: (args: { permId: number; roleId: number; scope: PermissionScope }) => void
}) {
  const modules = matrix.modules || []
  const rolePerms = (matrix as unknown as Record<string, unknown>).role_permissions as Record<number, Record<number, RolePermission>> | undefined

  const getScope = (permId: number, roleId: number): PermissionScope => {
    if (!rolePerms) return 'deny'
    return (rolePerms[roleId]?.[permId]?.scope as PermissionScope) ?? 'deny'
  }

  const getModuleActions = (mod: typeof modules[0]) =>
    mod.entities.flatMap((e) => e.actions)

  const isModuleAllGranted = (mod: typeof modules[0], roleId: number) => {
    const actions = getModuleActions(mod)
    return actions.length > 0 && actions.every((a) => getScope(a.id, roleId) !== 'deny')
  }

  const isModuleSomeGranted = (mod: typeof modules[0], roleId: number) => {
    const actions = getModuleActions(mod)
    const grantedCount = actions.filter((a) => getScope(a.id, roleId) !== 'deny').length
    return grantedCount > 0 && grantedCount < actions.length
  }

  // Module toggle: grant all → 'all', revoke all → 'deny'
  const toggleModule = (mod: typeof modules[0], roleId: number) => {
    const targetScope: PermissionScope = isModuleAllGranted(mod, roleId) ? 'deny' : 'all'
    getModuleActions(mod).forEach((action) => {
      if (getScope(action.id, roleId) !== targetScope) {
        onPermChange({ permId: action.id, roleId, scope: targetScope })
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
                <TableHead className="sticky left-0 z-10 bg-card min-w-[220px]">Permission</TableHead>
                {roles.map((r) => (
                  <TableHead key={r.id} className="text-center min-w-[100px]">
                    {r.name}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {modules.map((mod) => (
                <Fragment key={mod.key}>
                  {/* Module header row */}
                  <TableRow>
                    <TableCell className="bg-muted/50 font-semibold sticky left-0 z-10">
                      {mod.label}
                    </TableCell>
                    {roles.map((role) => (
                      <TableCell key={role.id} className="bg-muted/50 text-center">
                        <ScopeToggle
                          allGranted={isModuleAllGranted(mod, role.id)}
                          someGranted={isModuleSomeGranted(mod, role.id)}
                          onToggle={() => toggleModule(mod, role.id)}
                        />
                      </TableCell>
                    ))}
                  </TableRow>
                  {/* Permission rows */}
                  {mod.entities.flatMap((entity) =>
                    entity.actions.map((action) => (
                      <TableRow key={action.id}>
                        <TableCell className="sticky left-0 z-10 bg-card text-sm pl-6">
                          {entity.label} &mdash; {action.label}
                        </TableCell>
                        {roles.map((role) => (
                          <TableCell key={role.id} className="text-center">
                            <ScopeSelect
                              value={getScope(action.id, role.id)}
                              onChange={(scope) => onPermChange({ permId: action.id, roleId: role.id, scope })}
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

/** Small clickable indicator for module-level toggle (all/some/none) */
function ScopeToggle({ allGranted, someGranted, onToggle }: { allGranted: boolean; someGranted: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={`inline-flex items-center justify-center h-5 w-5 rounded border text-[10px] font-bold transition-colors
        ${allGranted ? 'bg-green-500/20 border-green-500 text-green-500' : someGranted ? 'bg-orange-500/20 border-orange-500 text-orange-500' : 'bg-muted border-muted-foreground/30 text-muted-foreground'}`}
    >
      {allGranted ? 'A' : someGranted ? '~' : '-'}
    </button>
  )
}

function ScopeSelect({ value, onChange }: { value: PermissionScope; onChange: (scope: PermissionScope) => void }) {
  const current = SCOPE_OPTIONS.find((o) => o.value === value) ?? SCOPE_OPTIONS[0]

  return (
    <Select value={value} onValueChange={(v) => onChange(v as PermissionScope)}>
      <SelectTrigger className={`h-7 w-[80px] text-xs mx-auto ${current.color}`}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {SCOPE_OPTIONS.map((opt) => (
          <SelectItem key={opt.value} value={opt.value} className={`text-xs ${opt.color}`}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
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
