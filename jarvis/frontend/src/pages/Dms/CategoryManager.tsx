import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Edit2, Trash2, GripVertical, Check, X, Shield } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import { rolesApi } from '@/api/roles'
import type { DmsCategory, DmsRelationshipTypeConfig } from '@/types/dms'

interface CategoryManagerProps {
  companyId?: number
}

export default function CategoryManager({ companyId }: CategoryManagerProps) {
  const queryClient = useQueryClient()
  const [editCat, setEditCat] = useState<DmsCategory | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteCatId, setDeleteCatId] = useState<number | null>(null)

  // Category form state
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [icon, setIcon] = useState('bi-folder')
  const [color, setColor] = useState('#6c757d')
  const [description, setDescription] = useState('')
  const [allowedRoleIds, setAllowedRoleIds] = useState<number[]>([])

  // Relationship types state
  const [rtCreateOpen, setRtCreateOpen] = useState(false)
  const [editRt, setEditRt] = useState<DmsRelationshipTypeConfig | null>(null)
  const [deleteRtId, setDeleteRtId] = useState<number | null>(null)
  const [rtLabel, setRtLabel] = useState('')
  const [rtSlug, setRtSlug] = useState('')
  const [rtIcon, setRtIcon] = useState('bi-file-earmark')
  const [rtColor, setRtColor] = useState('#6c757d')

  const { data, isLoading } = useQuery({
    queryKey: ['dms-categories-all', companyId],
    queryFn: () => dmsApi.listCategories(companyId, false),
    enabled: true,
  })

  const { data: rolesData } = useQuery({
    queryKey: ['roles-list'],
    queryFn: () => rolesApi.getRoles(),
  })

  const categories: DmsCategory[] = data?.categories || []
  const roles = rolesData || []

  const resetForm = () => {
    setName('')
    setSlug('')
    setIcon('bi-folder')
    setColor('#6c757d')
    setDescription('')
    setAllowedRoleIds([])
  }

  const createMutation = useMutation({
    mutationFn: (data: Partial<DmsCategory>) => dmsApi.createCategory(data),
    onSuccess: () => {
      toast.success('Category created')
      queryClient.invalidateQueries({ queryKey: ['dms-categories-all'] })
      queryClient.invalidateQueries({ queryKey: ['dms-categories'] })
      resetForm()
      setCreateOpen(false)
    },
    onError: () => toast.error('Failed to create category'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DmsCategory> }) =>
      dmsApi.updateCategory(id, data),
    onSuccess: () => {
      toast.success('Category updated')
      queryClient.invalidateQueries({ queryKey: ['dms-categories-all'] })
      queryClient.invalidateQueries({ queryKey: ['dms-categories'] })
      setEditCat(null)
      resetForm()
    },
    onError: () => toast.error('Failed to update category'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => dmsApi.deleteCategory(id),
    onSuccess: () => {
      toast.success('Category deactivated')
      queryClient.invalidateQueries({ queryKey: ['dms-categories-all'] })
      queryClient.invalidateQueries({ queryKey: ['dms-categories'] })
      setDeleteCatId(null)
    },
    onError: () => toast.error('Failed to delete category'),
  })

  // ── Relationship Types ──
  const { data: rtData, isLoading: rtLoading } = useQuery({
    queryKey: ['dms-rel-types-all'],
    queryFn: () => dmsApi.listRelationshipTypes(false),
  })
  const relTypes: DmsRelationshipTypeConfig[] = rtData?.types || []

  const resetRtForm = () => { setRtLabel(''); setRtSlug(''); setRtIcon('bi-file-earmark'); setRtColor('#6c757d') }

  const createRtMutation = useMutation({
    mutationFn: (data: Partial<DmsRelationshipTypeConfig>) => dmsApi.createRelationshipType(data),
    onSuccess: () => {
      toast.success('Type created')
      queryClient.invalidateQueries({ queryKey: ['dms-rel-types-all'] })
      queryClient.invalidateQueries({ queryKey: ['dms-rel-types'] })
      resetRtForm(); setRtCreateOpen(false)
    },
    onError: () => toast.error('Failed to create type'),
  })

  const updateRtMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DmsRelationshipTypeConfig> }) =>
      dmsApi.updateRelationshipType(id, data),
    onSuccess: () => {
      toast.success('Type updated')
      queryClient.invalidateQueries({ queryKey: ['dms-rel-types-all'] })
      queryClient.invalidateQueries({ queryKey: ['dms-rel-types'] })
      setEditRt(null); resetRtForm()
    },
    onError: () => toast.error('Failed to update type'),
  })

  const deleteRtMutation = useMutation({
    mutationFn: (id: number) => dmsApi.deleteRelationshipType(id),
    onSuccess: () => {
      toast.success('Type deactivated')
      queryClient.invalidateQueries({ queryKey: ['dms-rel-types-all'] })
      queryClient.invalidateQueries({ queryKey: ['dms-rel-types'] })
      setDeleteRtId(null)
    },
    onError: () => toast.error('Failed to delete type'),
  })

  const openRtEdit = (rt: DmsRelationshipTypeConfig) => {
    setEditRt(rt); setRtLabel(rt.label); setRtSlug(rt.slug); setRtIcon(rt.icon); setRtColor(rt.color)
  }

  const handleRtSave = () => {
    const payload = {
      label: rtLabel.trim(),
      slug: rtSlug.trim() || rtLabel.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''),
      icon: rtIcon, color: rtColor,
    }
    if (editRt) {
      updateRtMutation.mutate({ id: editRt.id, data: payload })
    } else {
      createRtMutation.mutate(payload)
    }
  }

  const openEdit = (cat: DmsCategory) => {
    setEditCat(cat)
    setName(cat.name)
    setSlug(cat.slug)
    setIcon(cat.icon)
    setColor(cat.color)
    setDescription(cat.description || '')
    setAllowedRoleIds(cat.allowed_role_ids || [])
  }

  const toggleRole = (roleId: number) => {
    setAllowedRoleIds((prev) =>
      prev.includes(roleId) ? prev.filter((r) => r !== roleId) : [...prev, roleId]
    )
  }

  const handleSave = () => {
    const payload: Record<string, unknown> = {
      name: name.trim(),
      slug: slug.trim() || name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''),
      icon,
      color,
      description: description.trim() || undefined,
      company_id: companyId,
      allowed_role_ids: allowedRoleIds.length > 0 ? allowedRoleIds : null,
    }

    if (editCat) {
      updateMutation.mutate({ id: editCat.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const formDialog = createOpen || editCat

  const roleNameById = (id: number) => roles.find((r) => r.id === id)?.name || `Role ${id}`

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Document Categories</h3>
        <Button size="sm" onClick={() => { resetForm(); setCreateOpen(true) }}>
          <Plus className="h-4 w-4 mr-1" />
          New Category
        </Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading categories...</p>
      ) : categories.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">No categories yet.</p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Name</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Color</TableHead>
                <TableHead>Access</TableHead>
                <TableHead className="text-center">Documents</TableHead>
                <TableHead className="text-center">Active</TableHead>
                <TableHead className="w-[80px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {categories.map((cat) => (
                <TableRow key={cat.id}>
                  <TableCell>
                    <GripVertical className="h-4 w-4 text-muted-foreground" />
                  </TableCell>
                  <TableCell className="font-medium">{cat.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{cat.slug}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div
                        className="h-4 w-4 rounded-full border"
                        style={{ backgroundColor: cat.color }}
                      />
                      <span className="text-xs text-muted-foreground">{cat.color}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    {cat.allowed_role_ids && cat.allowed_role_ids.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {cat.allowed_role_ids.map((rid) => (
                          <Badge key={rid} variant="outline" className="text-[10px] px-1.5 py-0">
                            {roleNameById(rid)}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">All roles</span>
                    )}
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant="secondary">{cat.document_count ?? 0}</Badge>
                  </TableCell>
                  <TableCell className="text-center">
                    {cat.is_active ? (
                      <Check className="h-4 w-4 text-green-600 mx-auto" />
                    ) : (
                      <X className="h-4 w-4 text-muted-foreground mx-auto" />
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(cat)}>
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => setDeleteCatId(cat.id)}
                      >
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
          if (!open) { setCreateOpen(false); setEditCat(null); resetForm() }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editCat ? 'Edit Category' : 'New Category'}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Name *</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Category name" />
            </div>
            <div className="space-y-1.5">
              <Label>Slug</Label>
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="Auto-generated from name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Icon</Label>
                <Input value={icon} onChange={(e) => setIcon(e.target.value)} placeholder="bi-folder" />
              </div>
              <div className="space-y-1.5">
                <Label>Color</Label>
                <div className="flex gap-2">
                  <Input value={color} onChange={(e) => setColor(e.target.value)} placeholder="#6c757d" />
                  <input
                    type="color"
                    value={color}
                    onChange={(e) => setColor(e.target.value)}
                    className="h-9 w-9 rounded border cursor-pointer"
                  />
                </div>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Description</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" />
            </div>

            {/* Role access */}
            <div className="space-y-1.5">
              <Label className="flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5" />
                Restrict to Roles
              </Label>
              <p className="text-xs text-muted-foreground">Leave unchecked for all roles to access</p>
              <div className="grid grid-cols-2 gap-2 mt-1">
                {roles.map((role) => (
                  <label key={role.id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <Checkbox
                      checked={allowedRoleIds.includes(role.id)}
                      onCheckedChange={() => toggleRole(role.id)}
                    />
                    {role.name}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => { setCreateOpen(false); setEditCat(null); resetForm() }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={!name.trim() || createMutation.isPending || updateMutation.isPending}
            >
              {editCat ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteCatId !== null}
        onOpenChange={(open) => !open && setDeleteCatId(null)}
        title="Deactivate Category"
        description="This will hide the category. Existing documents won't be affected."
        confirmLabel="Deactivate"
        variant="destructive"
        onConfirm={() => deleteCatId && deleteMutation.mutate(deleteCatId)}
      />

      {/* ── Relationship Types Section ── */}
      <div className="border-t pt-6 mt-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Relationship Types</h3>
          <Button size="sm" onClick={() => { resetRtForm(); setRtCreateOpen(true) }}>
            <Plus className="h-4 w-4 mr-1" />
            New Type
          </Button>
        </div>

        {rtLoading ? (
          <p className="text-sm text-muted-foreground">Loading types...</p>
        ) : relTypes.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">No relationship types yet.</p>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Label</TableHead>
                  <TableHead>Slug</TableHead>
                  <TableHead>Color</TableHead>
                  <TableHead className="text-center">Active</TableHead>
                  <TableHead className="w-[80px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {relTypes.map((rt) => (
                  <TableRow key={rt.id}>
                    <TableCell>
                      <GripVertical className="h-4 w-4 text-muted-foreground" />
                    </TableCell>
                    <TableCell className="font-medium">{rt.label}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{rt.slug}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="h-4 w-4 rounded-full border" style={{ backgroundColor: rt.color }} />
                        <span className="text-xs text-muted-foreground">{rt.color}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      {rt.is_active ? (
                        <Check className="h-4 w-4 text-green-600 mx-auto" />
                      ) : (
                        <X className="h-4 w-4 text-muted-foreground mx-auto" />
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openRtEdit(rt)}>
                          <Edit2 className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDeleteRtId(rt.id)}>
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
      </div>

      {/* Relationship Type Create/Edit Dialog */}
      <Dialog
        open={rtCreateOpen || !!editRt}
        onOpenChange={(open) => {
          if (!open) { setRtCreateOpen(false); setEditRt(null); resetRtForm() }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editRt ? 'Edit Type' : 'New Relationship Type'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Label *</Label>
              <Input value={rtLabel} onChange={(e) => setRtLabel(e.target.value)} placeholder="e.g. Invoices" />
            </div>
            <div className="space-y-1.5">
              <Label>Slug</Label>
              <Input value={rtSlug} onChange={(e) => setRtSlug(e.target.value)} placeholder="Auto-generated from label" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Icon</Label>
                <Input value={rtIcon} onChange={(e) => setRtIcon(e.target.value)} placeholder="bi-file-earmark" />
              </div>
              <div className="space-y-1.5">
                <Label>Color</Label>
                <div className="flex gap-2">
                  <Input value={rtColor} onChange={(e) => setRtColor(e.target.value)} placeholder="#6c757d" />
                  <input
                    type="color"
                    value={rtColor}
                    onChange={(e) => setRtColor(e.target.value)}
                    className="h-9 w-9 rounded border cursor-pointer"
                  />
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setRtCreateOpen(false); setEditRt(null); resetRtForm() }}>
              Cancel
            </Button>
            <Button
              onClick={handleRtSave}
              disabled={!rtLabel.trim() || createRtMutation.isPending || updateRtMutation.isPending}
            >
              {editRt ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete RT Confirmation */}
      <ConfirmDialog
        open={deleteRtId !== null}
        onOpenChange={(open) => !open && setDeleteRtId(null)}
        title="Deactivate Type"
        description="This will hide the relationship type. Existing child documents won't be affected."
        confirmLabel="Deactivate"
        variant="destructive"
        onConfirm={() => deleteRtId && deleteRtMutation.mutate(deleteRtId)}
      />
    </div>
  )
}
