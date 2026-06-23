import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Pencil, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { vouchersApi } from '@/api/vouchers'
import type { ServiceCatalogItem } from '@/types/vouchers'

interface ServiceForm {
  service_code: string
  name: string
  price: string
  currency: string
  category: string
}

const emptyForm: ServiceForm = { service_code: '', name: '', price: '', currency: 'LEI', category: '' }

export default function ServiceCatalog() {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<ServiceCatalogItem | null>(null)
  const [form, setForm] = useState<ServiceForm>(emptyForm)
  const [deleteConfirm, setDeleteConfirm] = useState<ServiceCatalogItem | null>(null)

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['service-catalog'],
    queryFn: vouchersApi.getServiceCatalog,
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; price: number; currency: string; category?: string }) =>
      vouchersApi.createService(data),
    onSuccess: () => {
      toast.success('Service created')
      closeDialog()
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to create service')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name: string; price: number; currency: string; category?: string } }) =>
      vouchersApi.updateService(id, data),
    onSuccess: () => {
      toast.success('Service updated')
      closeDialog()
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to update service')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => vouchersApi.deleteService(id),
    onSuccess: () => {
      toast.success('Service deleted')
      setDeleteConfirm(null)
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to delete service')
    },
  })

  const openCreate = () => {
    setEditingItem(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  const openEdit = (item: ServiceCatalogItem) => {
    setEditingItem(item)
    setForm({
      service_code: item.service_code || '',
      name: item.name,
      price: String(item.price),
      currency: item.currency,
      category: item.category || '',
    })
    setDialogOpen(true)
  }

  const closeDialog = () => {
    setDialogOpen(false)
    setEditingItem(null)
    setForm(emptyForm)
  }

  const handleSubmit = () => {
    const price = parseFloat(form.price)
    if (!form.name.trim()) {
      toast.error('Name is required')
      return
    }
    if (isNaN(price) || price < 0) {
      toast.error('Price must be a valid positive number')
      return
    }

    const payload = {
      service_code: form.service_code.trim() || undefined,
      name: form.name.trim(),
      price,
      currency: form.currency || 'LEI',
      category: form.category.trim() || undefined,
    }

    if (editingItem) {
      updateMutation.mutate({ id: editingItem.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Service Catalog</h1>
        <Button size="sm" onClick={openCreate}>
          <Plus className="mr-1 h-4 w-4" />Add Service
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Code</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Price (LEI)</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-[120px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Loading...</TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No services found. Click "Add Service" to create one.</TableCell>
              </TableRow>
            ) : (
              items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-mono text-xs">{item.service_code || '—'}</TableCell>
                  <TableCell className="font-medium">{item.name}</TableCell>
                  <TableCell>{Number(item.price).toLocaleString()} {item.currency}</TableCell>
                  <TableCell>{item.category || '—'}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={item.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}>
                      {item.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(item)} title="Edit">
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => setDeleteConfirm(item)} title="Delete" className="text-destructive hover:text-destructive">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create / Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { if (!open) closeDialog() }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingItem ? 'Edit Service' : 'Add Service'}</DialogTitle>
            <DialogDescription>
              {editingItem ? 'Update the service details below.' : 'Fill in the details to add a new service.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid gap-1.5">
              <Label htmlFor="svc-code">Service Code</Label>
              <Input
                id="svc-code"
                value={form.service_code}
                onChange={(e) => setForm((f) => ({ ...f, service_code: e.target.value.toUpperCase() }))}
                placeholder="e.g. SVC-OIL"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="svc-name">Name *</Label>
              <Input
                id="svc-name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Service name"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="svc-price">Price *</Label>
              <Input
                id="svc-price"
                type="number"
                min="0"
                step="0.01"
                value={form.price}
                onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
                placeholder="0.00"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="svc-currency">Currency</Label>
              <Input
                id="svc-currency"
                value={form.currency}
                onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
                placeholder="LEI"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="svc-category">Category</Label>
              <Input
                id="svc-category"
                value={form.category}
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                placeholder="Optional category"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeDialog}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={isSaving}>
              {isSaving ? 'Saving...' : editingItem ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Service</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>{deleteConfirm?.name}</strong>? This action will deactivate the service.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
