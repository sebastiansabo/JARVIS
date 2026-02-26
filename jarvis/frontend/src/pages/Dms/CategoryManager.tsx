import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Edit2, Trash2, GripVertical, Check, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import type { DmsCategory } from '@/types/dms'

interface CategoryManagerProps {
  companyId?: number
}

export default function CategoryManager({ companyId }: CategoryManagerProps) {
  const queryClient = useQueryClient()
  const [editCat, setEditCat] = useState<DmsCategory | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteCatId, setDeleteCatId] = useState<number | null>(null)

  // Form state
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [icon, setIcon] = useState('bi-folder')
  const [color, setColor] = useState('#6c757d')
  const [description, setDescription] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['dms-categories-all', companyId],
    queryFn: () => dmsApi.listCategories(companyId, false),
    enabled: true,
  })

  const categories: DmsCategory[] = data?.categories || []

  const resetForm = () => {
    setName('')
    setSlug('')
    setIcon('bi-folder')
    setColor('#6c757d')
    setDescription('')
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

  const openEdit = (cat: DmsCategory) => {
    setEditCat(cat)
    setName(cat.name)
    setSlug(cat.slug)
    setIcon(cat.icon)
    setColor(cat.color)
    setDescription(cat.description || '')
  }

  const handleSave = () => {
    const payload = {
      name: name.trim(),
      slug: slug.trim() || name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''),
      icon,
      color,
      description: description.trim() || undefined,
      company_id: companyId,
    }

    if (editCat) {
      updateMutation.mutate({ id: editCat.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const formDialog = createOpen || editCat

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
    </div>
  )
}
