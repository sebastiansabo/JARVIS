import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { toast } from 'sonner'
import { tagsApi } from '@/api/tags'
import type { TagGroup, Tag } from '@/types/tags'

export default function TagsTab() {
  return (
    <div className="space-y-6">
      <TagGroupsSection />
      <TagsSection />
    </div>
  )
}

function TagGroupsSection() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editGroup, setEditGroup] = useState<TagGroup | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: groups = [], isLoading } = useQuery({
    queryKey: ['settings', 'tagGroups'],
    queryFn: () => tagsApi.getGroups(),
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<TagGroup>) => tagsApi.createGroup(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'tagGroups'] })
      setShowAdd(false)
      toast.success('Tag group created')
    },
    onError: () => toast.error('Failed to create tag group'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<TagGroup> }) => tagsApi.updateGroup(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'tagGroups'] })
      setEditGroup(null)
      toast.success('Tag group updated')
    },
    onError: () => toast.error('Failed to update tag group'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => tagsApi.deleteGroup(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'tagGroups'] })
      setDeleteId(null)
      toast.success('Tag group deleted')
    },
    onError: () => toast.error('Failed to delete tag group'),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Tag Groups</CardTitle>
            <CardDescription>Organize tags into groups.</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Group
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : groups.length === 0 ? (
          <EmptyState title="No tag groups" description="Add your first group." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Color</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Order</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.map((g) => (
                <TableRow key={g.id}>
                  <TableCell>
                    {g.color && <div className="h-5 w-5 rounded border" style={{ backgroundColor: g.color }} />}
                  </TableCell>
                  <TableCell className="font-medium">{g.name}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{g.description || '-'}</TableCell>
                  <TableCell>{g.sort_order}</TableCell>
                  <TableCell>
                    <StatusBadge status={g.is_active ? 'active' : 'archived'} />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditGroup(g)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(g.id)}>
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

      <TagGroupFormDialog
        open={showAdd || !!editGroup}
        group={editGroup}
        onClose={() => { setShowAdd(false); setEditGroup(null) }}
        onSave={(data) => {
          if (editGroup) {
            updateMutation.mutate({ id: editGroup.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Tag Group"
        description="Tags in this group will become ungrouped."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

function TagGroupFormDialog({ open, group, onClose, onSave, isPending }: {
  open: boolean; group: TagGroup | null; onClose: () => void
  onSave: (data: Partial<TagGroup>) => void; isPending: boolean
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState('#3b82f6')

  const resetForm = () => {
    if (group) {
      setName(group.name); setDescription(group.description || ''); setColor(group.color || '#3b82f6')
    } else {
      setName(''); setDescription(''); setColor('#3b82f6')
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-sm" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{group ? 'Edit Tag Group' : 'Add Tag Group'}</DialogTitle>
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
          <div className="grid gap-2">
            <Label>Color</Label>
            <div className="flex gap-2">
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-8 w-8 cursor-pointer rounded border" />
              <Input value={color} onChange={(e) => setColor(e.target.value)} className="h-8" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={!name || isPending} onClick={() => onSave({ name, description, color, is_active: group?.is_active ?? true })}>
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TagsSection() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editTag, setEditTag] = useState<Tag | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: tags = [], isLoading } = useQuery({
    queryKey: ['settings', 'tags'],
    queryFn: () => tagsApi.getTags(),
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<Tag>) => tagsApi.createTag(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'tags'] })
      setShowAdd(false)
      toast.success('Tag created')
    },
    onError: () => toast.error('Failed to create tag'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Tag> }) => tagsApi.updateTag(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'tags'] })
      setEditTag(null)
      toast.success('Tag updated')
    },
    onError: () => toast.error('Failed to update tag'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => tagsApi.deleteTag(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'tags'] })
      setDeleteId(null)
      toast.success('Tag deleted')
    },
    onError: () => toast.error('Failed to delete tag'),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Tags</CardTitle>
            <CardDescription>Tags can be attached to invoices, transactions, and more.</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Tag
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : tags.length === 0 ? (
          <EmptyState title="No tags" description="Add your first tag." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Color</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Group</TableHead>
                <TableHead>Scope</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tags.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    {t.color && <div className="h-5 w-5 rounded border" style={{ backgroundColor: t.color }} />}
                  </TableCell>
                  <TableCell className="font-medium">{t.name}</TableCell>
                  <TableCell className="text-muted-foreground">{t.group_name || '-'}</TableCell>
                  <TableCell>{t.is_global ? 'Global' : 'Personal'}</TableCell>
                  <TableCell>
                    <StatusBadge status={t.is_active ? 'active' : 'archived'} />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditTag(t)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(t.id)}>
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

      <TagFormDialog
        open={showAdd || !!editTag}
        tag={editTag}
        onClose={() => { setShowAdd(false); setEditTag(null) }}
        onSave={(data) => {
          if (editTag) {
            updateMutation.mutate({ id: editTag.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Tag"
        description="This will remove the tag from all entities."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

function TagFormDialog({ open, tag, onClose, onSave, isPending }: {
  open: boolean; tag: Tag | null; onClose: () => void
  onSave: (data: Partial<Tag>) => void; isPending: boolean
}) {
  const [name, setName] = useState('')
  const [color, setColor] = useState('#3b82f6')

  const resetForm = () => {
    if (tag) {
      setName(tag.name); setColor(tag.color || '#3b82f6')
    } else {
      setName(''); setColor('#3b82f6')
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-sm" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{tag ? 'Edit Tag' : 'Add Tag'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Color</Label>
            <div className="flex gap-2">
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-8 w-8 cursor-pointer rounded border" />
              <Input value={color} onChange={(e) => setColor(e.target.value)} className="h-8" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={!name || isPending} onClick={() => onSave({ name, color, is_global: tag?.is_global ?? true })}>
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
