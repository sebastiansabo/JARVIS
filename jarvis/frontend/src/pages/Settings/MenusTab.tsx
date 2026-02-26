import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, GripVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { settingsApi } from '@/api/settings'
import { toast } from 'sonner'
import type { MenuItem } from '@/types/settings'

export default function MenusTab() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editItem, setEditItem] = useState<MenuItem | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['settings', 'moduleMenu'],
    queryFn: async () => {
      const res = await settingsApi.getAllModuleMenu()
      return res.items ?? (res as unknown as MenuItem[])
    },
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<MenuItem>) => settingsApi.createMenuItem(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'moduleMenu'] })
      setShowAdd(false)
      toast.success('Menu item created')
    },
    onError: () => toast.error('Failed to create menu item'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<MenuItem> }) => settingsApi.updateMenuItem(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'moduleMenu'] })
      setEditItem(null)
      toast.success('Menu item updated')
    },
    onError: () => toast.error('Failed to update menu item'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => settingsApi.deleteMenuItem(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'moduleMenu'] })
      setDeleteId(null)
      toast.success('Menu item deleted')
    },
    onError: () => toast.error('Failed to delete menu item'),
  })

  // Build hierarchical list: parents first (sorted), then children indented under each parent
  const structured = (() => {
    const parents = items.filter((i) => !i.parent_id).sort((a, b) => a.sort_order - b.sort_order)
    const childMap = new Map<number, MenuItem[]>()
    for (const item of items) {
      if (item.parent_id) {
        const list = childMap.get(item.parent_id) ?? []
        list.push(item)
        childMap.set(item.parent_id, list)
      }
    }
    const result: { item: MenuItem; isChild: boolean }[] = []
    for (const parent of parents) {
      result.push({ item: parent, isChild: false })
      const children = (childMap.get(parent.id) ?? []).sort((a, b) => a.sort_order - b.sort_order)
      for (const child of children) {
        result.push({ item: child, isChild: true })
      }
    }
    return result
  })()

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Module Menu</CardTitle>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Item
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : structured.length === 0 ? (
          <EmptyState title="No menu items" description="Add your first module menu item." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10" />
                <TableHead>Label</TableHead>
                <TableHead>Module Key</TableHead>
                <TableHead>URL</TableHead>
                <TableHead>Order</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {structured.map(({ item, isChild }) => (
                <TableRow key={item.id} className={isChild ? 'bg-muted/30' : ''}>
                  <TableCell>
                    <GripVertical className="h-4 w-4 text-muted-foreground" />
                  </TableCell>
                  <TableCell className="font-medium">
                    {isChild && <span className="mr-2 text-muted-foreground">└</span>}
                    {item.icon && <span className="mr-2">{item.icon}</span>}
                    {item.name}
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">{item.module_key}</TableCell>
                  <TableCell className="text-muted-foreground text-xs">{item.url}</TableCell>
                  <TableCell>{item.sort_order}</TableCell>
                  <TableCell>
                    <StatusBadge status={item.status === 'active' ? 'active' : item.status === 'coming_soon' ? 'coming_soon' : 'archived'} />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditItem(item)}>
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => setDeleteId(item.id)}
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

      <MenuFormDialog
        open={showAdd || !!editItem}
        item={editItem}
        parentModules={items.filter((i) => !i.parent_id)}
        onClose={() => {
          setShowAdd(false)
          setEditItem(null)
        }}
        onSave={(data) => {
          if (editItem) {
            updateMutation.mutate({ id: editItem.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Menu Item"
        description="This action cannot be undone."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

function MenuFormDialog({
  open,
  item,
  parentModules,
  onClose,
  onSave,
  isPending,
}: {
  open: boolean
  item: MenuItem | null
  parentModules: MenuItem[]
  onClose: () => void
  onSave: (data: Partial<MenuItem>) => void
  isPending: boolean
}) {
  const [form, setForm] = useState({
    name: '',
    module_key: '',
    icon: '',
    url: '',
    sort_order: 0,
    status: 'active',
    parent_id: null as number | null,
  })

  const resetForm = () =>
    setForm(
      item
        ? {
            name: item.name,
            module_key: item.module_key,
            icon: item.icon || '',
            url: item.url,
            sort_order: item.sort_order,
            status: item.status || 'active',
            parent_id: item.parent_id,
          }
        : { name: '', module_key: '', icon: '', url: '', sort_order: 0, status: 'active', parent_id: null },
    )

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose()
        else resetForm()
      }}
    >
      <DialogContent className="sm:max-w-md" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{item ? 'Edit Menu Item' : 'Add Menu Item'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="grid gap-2">
              <Label>Module Key</Label>
              <Input value={form.module_key} onChange={(e) => setForm({ ...form, module_key: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Icon</Label>
              <Input value={form.icon} onChange={(e) => setForm({ ...form, icon: e.target.value })} placeholder="e.g. bi-house" />
            </div>
            <div className="grid gap-2">
              <Label>URL</Label>
              <Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Parent</Label>
              <Select
                value={form.parent_id?.toString() ?? '_none'}
                onValueChange={(v) => setForm({ ...form, parent_id: v === '_none' ? null : Number(v) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">— Top level —</SelectItem>
                  {parentModules
                    .filter((p) => p.id !== item?.id)
                    .map((p) => (
                      <SelectItem key={p.id} value={p.id.toString()}>
                        {p.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Sort Order</Label>
              <Input
                type="number"
                value={form.sort_order}
                onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Switch
              checked={form.status === 'active'}
              onCheckedChange={(v) => setForm({ ...form, status: v ? 'active' : 'archived' })}
            />
            <Label>Active</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={isPending || !form.name || !form.module_key}
            onClick={() => onSave(form)}
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
