import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Edit2, Trash2, Check, X, ChevronUp, ChevronDown } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import type { DmsPartyRoleConfig } from '@/types/dms'

const EMPTY: Partial<DmsPartyRoleConfig> = { label: '', slug: '' }

export default function PartyRoleManager() {
  const queryClient = useQueryClient()
  const [editRole, setEditRole] = useState<DmsPartyRoleConfig | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteRoleId, setDeleteRoleId] = useState<number | null>(null)
  const [form, setForm] = useState<Partial<DmsPartyRoleConfig>>(EMPTY)

  const { data, isLoading } = useQuery({
    queryKey: ['dms-party-roles-all'],
    queryFn: () => dmsApi.listPartyRoles(false),
  })
  const roles: DmsPartyRoleConfig[] = data?.roles || []

  const resetForm = () => setForm({ ...EMPTY })

  const createMutation = useMutation({
    mutationFn: (data: Partial<DmsPartyRoleConfig>) => dmsApi.createPartyRole(data),
    onSuccess: () => {
      toast.success('Party role created')
      queryClient.invalidateQueries({ queryKey: ['dms-party-roles'] })
      queryClient.invalidateQueries({ queryKey: ['dms-party-roles-all'] })
      resetForm()
      setCreateOpen(false)
    },
    onError: () => toast.error('Failed to create party role'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DmsPartyRoleConfig> }) =>
      dmsApi.updatePartyRole(id, data),
    onSuccess: () => {
      toast.success('Party role updated')
      queryClient.invalidateQueries({ queryKey: ['dms-party-roles'] })
      queryClient.invalidateQueries({ queryKey: ['dms-party-roles-all'] })
      setEditRole(null)
      resetForm()
    },
    onError: () => toast.error('Failed to update party role'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => dmsApi.deletePartyRole(id),
    onSuccess: () => {
      toast.success('Party role deactivated')
      queryClient.invalidateQueries({ queryKey: ['dms-party-roles'] })
      queryClient.invalidateQueries({ queryKey: ['dms-party-roles-all'] })
      setDeleteRoleId(null)
    },
    onError: () => toast.error('Failed to deactivate party role'),
  })

  const reorderMutation = useMutation({
    mutationFn: (ids: number[]) => dmsApi.reorderPartyRoles(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dms-party-roles'] })
      queryClient.invalidateQueries({ queryKey: ['dms-party-roles-all'] })
    },
  })

  const openEdit = (role: DmsPartyRoleConfig) => {
    setEditRole(role)
    setForm({ label: role.label, slug: role.slug })
  }

  const handleSave = () => {
    const label = (form.label || '').trim()
    if (!label) return
    const slug = (form.slug || '').trim() || label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    if (editRole) {
      updateMutation.mutate({ id: editRole.id, data: { label, slug } })
    } else {
      createMutation.mutate({ label, slug })
    }
  }

  const moveUp = (idx: number) => {
    if (idx <= 0) return
    const ids = roles.map((r) => r.id)
    ;[ids[idx - 1], ids[idx]] = [ids[idx], ids[idx - 1]]
    reorderMutation.mutate(ids)
  }

  const moveDown = (idx: number) => {
    if (idx >= roles.length - 1) return
    const ids = roles.map((r) => r.id)
    ;[ids[idx], ids[idx + 1]] = [ids[idx + 1], ids[idx]]
    reorderMutation.mutate(ids)
  }

  const formDialog = createOpen || editRole

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Party Roles</h3>
        <Button size="sm" onClick={() => { resetForm(); setCreateOpen(true) }}>
          <Plus className="h-4 w-4 mr-1" />
          New Role
        </Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading roles...</p>
      ) : roles.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">
          No party roles yet. Add your first role.
        </p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[40px]" />
                <TableHead>Label</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead className="text-center">Active</TableHead>
                <TableHead className="w-[80px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {roles.map((role, idx) => (
                <TableRow key={role.id}>
                  <TableCell className="px-1">
                    <div className="flex flex-col">
                      <button
                        onClick={() => moveUp(idx)}
                        disabled={idx === 0}
                        className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-25"
                      >
                        <ChevronUp className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => moveDown(idx)}
                        disabled={idx === roles.length - 1}
                        className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-25"
                      >
                        <ChevronDown className="h-3 w-3" />
                      </button>
                    </div>
                  </TableCell>
                  <TableCell className="font-medium">{role.label}</TableCell>
                  <TableCell className="text-sm text-muted-foreground font-mono">{role.slug}</TableCell>
                  <TableCell className="text-center">
                    {role.is_active ? (
                      <Check className="h-4 w-4 text-green-600 mx-auto" />
                    ) : (
                      <X className="h-4 w-4 text-muted-foreground mx-auto" />
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(role)}>
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDeleteRoleId(role.id)}>
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog
        open={!!formDialog}
        onOpenChange={(open) => {
          if (!open) { setCreateOpen(false); setEditRole(null); resetForm() }
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{editRole ? 'Edit Party Role' : 'New Party Role'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Label *</Label>
              <Input
                value={form.label || ''}
                onChange={(e) => setForm((prev) => ({ ...prev, label: e.target.value }))}
                placeholder="e.g. Emitent, Beneficiar"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Slug</Label>
              <Input
                value={form.slug || ''}
                onChange={(e) => setForm((prev) => ({ ...prev, slug: e.target.value }))}
                placeholder="Auto-generated from label"
                className="font-mono text-sm"
              />
              <p className="text-[11px] text-muted-foreground">Lowercase, used internally. Leave blank to auto-generate.</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreateOpen(false); setEditRole(null); resetForm() }}>
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={!(form.label || '').trim() || createMutation.isPending || updateMutation.isPending}
            >
              {editRole ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteRoleId !== null}
        onOpenChange={(open) => !open && setDeleteRoleId(null)}
        title="Deactivate Party Role"
        description="This will deactivate the party role. Existing parties with this role will still display correctly."
        confirmLabel="Deactivate"
        variant="destructive"
        onConfirm={() => deleteRoleId && deleteMutation.mutate(deleteRoleId)}
      />
    </div>
  )
}
