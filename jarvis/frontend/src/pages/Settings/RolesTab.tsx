import { Fragment, useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, Save, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
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

// key = `${permId}:${roleId}`
type PendingMap = Map<string, { permId: number; roleId: number; scope: PermissionScope }>

export default function RolesTab() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editRole, setEditRole] = useState<Role | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  // Pending changes not yet saved
  const [pending, setPending] = useState<PendingMap>(new Map())

  const { data: roles = [], isLoading: rolesLoading } = useQuery({
    queryKey: ['settings', 'roles'],
    queryFn: rolesApi.getRoles,
    staleTime: 10 * 60_000,
  })

  const { data: matrix } = useQuery({
    queryKey: ['settings', 'permissionMatrix'],
    queryFn: rolesApi.getPermissionMatrix,
    staleTime: 10 * 60_000,
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

  const [isSaving, setIsSaving] = useState(false)

  const handlePermChange = useCallback((args: { permId: number; roleId: number; scope: PermissionScope }) => {
    setPending((prev) => {
      const next = new Map(prev)
      next.set(`${args.permId}:${args.roleId}`, args)
      return next
    })
  }, [])

  const handleSave = async () => {
    if (pending.size === 0) return
    setIsSaving(true)
    try {
      await Promise.all(
        Array.from(pending.values()).map(({ permId, roleId, scope }) =>
          rolesApi.setSinglePermissionV2(permId, roleId, { scope, granted: scope !== 'deny' })
        )
      )
      setPending(new Map())
      queryClient.invalidateQueries({ queryKey: ['settings', 'permissionMatrix'] })
      toast.success(`${pending.size} permission${pending.size > 1 ? 's' : ''} saved`)
    } catch {
      toast.error('Failed to save permissions')
    } finally {
      setIsSaving(false)
    }
  }

  const handleDiscard = () => {
    setPending(new Map())
  }

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
      {matrix && (
        <PermissionMatrixView
          matrix={matrix}
          roles={roles}
          pending={pending}
          onPermChange={handlePermChange}
          onSave={handleSave}
          onDiscard={handleDiscard}
          isSaving={isSaving}
        />
      )}

      {/* Role Form Dialog */}
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
  pending,
  onPermChange,
  onSave,
  onDiscard,
  isSaving,
}: {
  matrix: PermissionMatrix
  roles: Role[]
  pending: PendingMap
  onPermChange: (args: { permId: number; roleId: number; scope: PermissionScope }) => void
  onSave: () => void
  onDiscard: () => void
  isSaving: boolean
}) {
  const modules = matrix.modules || []
  const rolePerms = (matrix as unknown as Record<string, unknown>).role_permissions as Record<number, Record<number, RolePermission>> | undefined

  const getScope = (permId: number, roleId: number): PermissionScope => {
    // Pending changes take priority
    const pendingKey = `${permId}:${roleId}`
    const pendingEntry = pending.get(pendingKey)
    if (pendingEntry) return pendingEntry.scope
    if (!rolePerms) return 'deny'
    return (rolePerms[roleId]?.[permId]?.scope as PermissionScope) ?? 'deny'
  }

  const isPending = (permId: number, roleId: number) =>
    pending.has(`${permId}:${roleId}`)

  const getModuleActions = (mod: typeof modules[0]) =>
    mod.entities.flatMap((e) => e.actions)

  const getModuleScope = (mod: typeof modules[0], roleId: number): PermissionScope | 'mixed' => {
    const actions = getModuleActions(mod)
    if (actions.length === 0) return 'deny'
    const scopes = actions.map((a) => getScope(a.id, roleId))
    const unique = [...new Set(scopes)]
    return unique.length === 1 ? unique[0] : 'mixed'
  }

  // Bulk set all actions in a module to the chosen scope
  const handleModuleBulk = (mod: typeof modules[0], roleId: number, scope: PermissionScope) => {
    getModuleActions(mod).forEach((action) => {
      onPermChange({ permId: action.id, roleId, scope })
    })
  }

  const pendingCount = pending.size

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle>Permission Matrix</CardTitle>
            {pendingCount > 0 && (
              <Badge variant="secondary" className="text-xs">
                {pendingCount} unsaved change{pendingCount > 1 ? 's' : ''}
              </Badge>
            )}
          </div>
          {pendingCount > 0 && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={onDiscard} disabled={isSaving}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                Discard
              </Button>
              <Button size="sm" onClick={onSave} disabled={isSaving}>
                <Save className="mr-1.5 h-3.5 w-3.5" />
                {isSaving ? 'Saving…' : `Save Changes (${pendingCount})`}
              </Button>
            </div>
          )}
        </div>
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
                  {/* Module header row — bulk scope selector */}
                  <TableRow>
                    <TableCell className="bg-muted/50 font-semibold sticky left-0 z-10">
                      {mod.label}
                    </TableCell>
                    {roles.map((role) => {
                      const modScope = getModuleScope(mod, role.id)
                      return (
                        <TableCell key={role.id} className="bg-muted/50 text-center">
                          <ModuleScopeSelect
                            value={modScope === 'mixed' ? 'deny' : modScope}
                            isMixed={modScope === 'mixed'}
                            onChange={(scope) => handleModuleBulk(mod, role.id, scope)}
                          />
                        </TableCell>
                      )
                    })}
                  </TableRow>
                  {/* Permission rows */}
                  {mod.entities.flatMap((entity) =>
                    entity.actions.map((action) => (
                      <TableRow key={action.id}>
                        <TableCell className="sticky left-0 z-10 bg-card text-sm pl-6">
                          {entity.label} &mdash; {action.label}
                        </TableCell>
                        {roles.map((role) => {
                          const hasPending = isPending(action.id, role.id)
                          return (
                            <TableCell key={role.id} className="text-center">
                              <ScopeSelect
                                value={getScope(action.id, role.id)}
                                onChange={(scope) => onPermChange({ permId: action.id, roleId: role.id, scope })}
                                dirty={hasPending}
                              />
                            </TableCell>
                          )
                        })}
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

/** Module-level bulk scope dropdown — shows current scope or Mixed indicator */
function ModuleScopeSelect({
  value,
  isMixed,
  onChange,
}: {
  value: PermissionScope
  isMixed: boolean
  onChange: (scope: PermissionScope) => void
}) {
  const current = SCOPE_OPTIONS.find((o) => o.value === value) ?? SCOPE_OPTIONS[0]
  return (
    <Select value={value} onValueChange={(v) => onChange(v as PermissionScope)}>
      <SelectTrigger className={`h-6 w-[80px] text-[11px] font-semibold mx-auto border-dashed ${isMixed ? 'text-muted-foreground' : current.color}`}>
        <SelectValue>{isMixed ? '~mixed' : current.label}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {SCOPE_OPTIONS.map((opt) => (
          <SelectItem key={opt.value} value={opt.value} className={`text-xs font-medium ${opt.color}`}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function ScopeSelect({
  value,
  onChange,
  dirty,
}: {
  value: PermissionScope
  onChange: (scope: PermissionScope) => void
  dirty?: boolean
}) {
  const current = SCOPE_OPTIONS.find((o) => o.value === value) ?? SCOPE_OPTIONS[0]
  return (
    <Select value={value} onValueChange={(v) => onChange(v as PermissionScope)}>
      <SelectTrigger className={`h-7 w-[80px] text-xs mx-auto transition-all ${current.color} ${dirty ? 'ring-2 ring-orange-400 ring-offset-1' : ''}`}>
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
