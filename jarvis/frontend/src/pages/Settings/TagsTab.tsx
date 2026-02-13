import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, Play, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { toast } from 'sonner'
import { tagsApi } from '@/api/tags'
import type { TagGroup, Tag, AutoTagRule, RuleCondition } from '@/types/tags'

const ENTITY_TYPE_LABELS: Record<string, string> = {
  invoice: 'Invoice',
  efactura_invoice: 'e-Factura',
  transaction: 'Transaction',
  event: 'HR Event',
}

const OPERATOR_LABELS: Record<string, string> = {
  eq: 'equals',
  neq: 'not equals',
  contains: 'contains',
  not_contains: 'not contains',
  starts_with: 'starts with',
  ends_with: 'ends with',
  gt: '>',
  gte: '>=',
  lt: '<',
  lte: '<=',
  regex: 'regex',
}

export default function TagsTab() {
  return (
    <div className="space-y-6">
      <TagGroupsSection />
      <TagsSection />
      <AutoTagRulesSection />
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

/* ──── Auto-Tag Rules ──── */

function AutoTagRulesSection() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editRule, setEditRule] = useState<AutoTagRule | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['settings', 'autoTagRules'],
    queryFn: () => tagsApi.getAutoTagRules(),
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<AutoTagRule>) => tagsApi.createAutoTagRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'autoTagRules'] })
      setShowForm(false)
      toast.success('Rule created')
    },
    onError: () => toast.error('Failed to create rule'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<AutoTagRule> }) => tagsApi.updateAutoTagRule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'autoTagRules'] })
      setEditRule(null)
      toast.success('Rule updated')
    },
    onError: () => toast.error('Failed to update rule'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => tagsApi.deleteAutoTagRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'autoTagRules'] })
      setDeleteId(null)
      toast.success('Rule deleted')
    },
    onError: () => toast.error('Failed to delete rule'),
  })

  const runMutation = useMutation({
    mutationFn: (id: number) => tagsApi.runAutoTagRule(id),
    onSuccess: (result) => {
      toast.success(`Rule applied: ${result.matched} matched, ${result.tagged} newly tagged`)
      queryClient.invalidateQueries({ queryKey: ['entity-tags'] })
    },
    onError: () => toast.error('Failed to run rule'),
  })

  const toggleActive = (rule: AutoTagRule) => {
    updateMutation.mutate({ id: rule.id, data: { is_active: !rule.is_active } })
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Auto-Tag Rules</CardTitle>
            <CardDescription>Automatically apply tags based on conditions.</CardDescription>
          </div>
          <Button size="sm" onClick={() => { setEditRule(null); setShowForm(true) }}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Rule
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
        ) : rules.length === 0 ? (
          <EmptyState title="No auto-tag rules" description="Create rules to automatically tag entities." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Entity Type</TableHead>
                <TableHead>Tag</TableHead>
                <TableHead>Conditions</TableHead>
                <TableHead>On Create</TableHead>
                <TableHead>Active</TableHead>
                <TableHead className="w-32">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell className="font-medium">{rule.name}</TableCell>
                  <TableCell className="text-sm">{ENTITY_TYPE_LABELS[rule.entity_type] ?? rule.entity_type}</TableCell>
                  <TableCell>
                    <span
                      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
                      style={{ backgroundColor: rule.tag_color ?? '#6c757d' }}
                    >
                      {rule.tag_name}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-[200px]">
                    {(rule.conditions || []).map((c, i) => (
                      <span key={i}>
                        {i > 0 && ' AND '}
                        {c.field} {OPERATOR_LABELS[c.operator] ?? c.operator} "{c.value}"
                      </span>
                    ))}
                    {(!rule.conditions || rule.conditions.length === 0) && <span className="italic">No conditions (matches all)</span>}
                  </TableCell>
                  <TableCell>{rule.run_on_create ? 'Yes' : 'No'}</TableCell>
                  <TableCell>
                    <Switch checked={rule.is_active} onCheckedChange={() => toggleActive(rule)} />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost" size="sm" title="Run now"
                        disabled={runMutation.isPending}
                        onClick={() => runMutation.mutate(rule.id)}
                      >
                        <Play className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => { setEditRule(rule); setShowForm(true) }}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(rule.id)}>
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

      <AutoTagRuleFormDialog
        open={showForm}
        rule={editRule}
        onClose={() => { setShowForm(false); setEditRule(null) }}
        onSave={(data) => {
          if (editRule) {
            updateMutation.mutate({ id: editRule.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Auto-Tag Rule"
        description="This will not remove already applied tags."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

function AutoTagRuleFormDialog({ open, rule, onClose, onSave, isPending }: {
  open: boolean; rule: AutoTagRule | null; onClose: () => void
  onSave: (data: Partial<AutoTagRule>) => void; isPending: boolean
}) {
  const [name, setName] = useState('')
  const [entityType, setEntityType] = useState('invoice')
  const [tagId, setTagId] = useState<number | null>(null)
  const [conditions, setConditions] = useState<RuleCondition[]>([])
  const [runOnCreate, setRunOnCreate] = useState(true)

  const { data: allTags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: () => tagsApi.getTags(),
    enabled: open,
  })

  const { data: entityFields = {} } = useQuery({
    queryKey: ['auto-tag-entity-fields'],
    queryFn: () => tagsApi.getEntityFields(),
    enabled: open,
    staleTime: 60_000,
  })

  const fieldsForType = entityFields[entityType] ?? []

  const resetForm = () => {
    if (rule) {
      setName(rule.name)
      setEntityType(rule.entity_type)
      setTagId(rule.tag_id)
      setConditions(rule.conditions || [])
      setRunOnCreate(rule.run_on_create)
    } else {
      setName('')
      setEntityType('invoice')
      setTagId(null)
      setConditions([])
      setRunOnCreate(true)
    }
  }

  const addCondition = () => {
    setConditions([...conditions, { field: fieldsForType[0] ?? '', operator: 'contains', value: '' }])
  }

  const updateCondition = (idx: number, patch: Partial<RuleCondition>) => {
    setConditions(conditions.map((c, i) => i === idx ? { ...c, ...patch } : c))
  }

  const removeCondition = (idx: number) => {
    setConditions(conditions.filter((_, i) => i !== idx))
  }

  const handleSave = () => {
    if (!name.trim()) return toast.error('Name is required')
    if (!tagId) return toast.error('Tag is required')
    onSave({
      name: name.trim(),
      entity_type: entityType,
      tag_id: tagId,
      conditions,
      run_on_create: runOnCreate,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-lg" onOpenAutoFocus={(e) => { e.preventDefault(); resetForm() }}>
        <DialogHeader>
          <DialogTitle>{rule ? 'Edit Auto-Tag Rule' : 'Add Auto-Tag Rule'}</DialogTitle>
          <DialogDescription>Define conditions to automatically apply tags.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Rule Name *</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g., Tag high-value invoices" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Entity Type *</Label>
              <Select value={entityType} onValueChange={(v) => { setEntityType(v); setConditions([]) }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(ENTITY_TYPE_LABELS).map(([val, label]) => (
                    <SelectItem key={val} value={val}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Apply Tag *</Label>
              <Select value={tagId ? String(tagId) : '__none__'} onValueChange={(v) => setTagId(v === '__none__' ? null : Number(v))}>
                <SelectTrigger><SelectValue placeholder="Select tag" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Select tag...</SelectItem>
                  {allTags.map((t) => (
                    <SelectItem key={t.id} value={String(t.id)}>
                      <span className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: t.color ?? '#6c757d' }} />
                        {t.name}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs">Conditions (all must match)</Label>
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={addCondition}>
                <Plus className="mr-1 h-3 w-3" /> Add
              </Button>
            </div>
            {conditions.length === 0 && (
              <p className="text-xs text-muted-foreground italic">No conditions — rule matches all entities.</p>
            )}
            {conditions.map((cond, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <Select value={cond.field} onValueChange={(v) => updateCondition(idx, { field: v })}>
                  <SelectTrigger className="w-[140px] h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {fieldsForType.map((f) => (
                      <SelectItem key={f} value={f}>{f}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={cond.operator} onValueChange={(v) => updateCondition(idx, { operator: v })}>
                  <SelectTrigger className="w-[110px] h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(OPERATOR_LABELS).map(([val, label]) => (
                      <SelectItem key={val} value={val}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={cond.value}
                  onChange={(e) => updateCondition(idx, { value: e.target.value })}
                  placeholder="value"
                  className="h-8 flex-1 text-xs"
                />
                <Button variant="ghost" size="sm" className="h-8 w-8 p-0 shrink-0" onClick={() => removeCondition(idx)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <Switch checked={runOnCreate} onCheckedChange={setRunOnCreate} />
            <Label className="text-xs">Auto-apply when entity is created</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={isPending} onClick={handleSave}>
            {isPending ? 'Saving...' : rule ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
