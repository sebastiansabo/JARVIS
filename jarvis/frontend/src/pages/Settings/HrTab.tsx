import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { hrApi } from '@/api/hr'
import { toast } from 'sonner'
import type { BonusType, HrSettings } from '@/types/hr'

export default function HrTab() {
  return (
    <div className="space-y-6">
      <BonusLockSection />
      <BonusTypesSection />
    </div>
  )
}

function BonusLockSection() {
  const queryClient = useQueryClient()

  const { data: settings } = useQuery({
    queryKey: ['settings', 'hrSettings'],
    queryFn: hrApi.getSettings,
    staleTime: 10 * 60_000,
  })

  const [lockDay, setLockDay] = useState(15)
  const [maxHoursPerDay, setMaxHoursPerDay] = useState(8)

  useEffect(() => {
    if (settings?.hr_bonus_lock_day) {
      setLockDay(settings.hr_bonus_lock_day)
    }
    if (settings?.hr_bonus_max_hours_per_day) {
      setMaxHoursPerDay(settings.hr_bonus_max_hours_per_day)
    }
  }, [settings])

  const saveMutation = useMutation({
    mutationFn: (data: HrSettings) => hrApi.updateSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'hrSettings'] })
      toast.success('Settings saved')
    },
    onError: () => toast.error('Failed to save settings'),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bonus Lock Deadline</CardTitle>
        <CardDescription>Bonuses become locked on this day of the following month.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-3">
          <div className="grid gap-2">
            <Label>Day of Month (1-28)</Label>
            <Input
              type="number"
              min={1}
              max={28}
              value={lockDay}
              onChange={(e) => setLockDay(Number(e.target.value))}
              className="w-24"
            />
          </div>
          <div className="grid gap-2">
            <Label>Max Free Hours / Day</Label>
            <Input
              type="number"
              min={1}
              max={24}
              value={maxHoursPerDay}
              onChange={(e) => setMaxHoursPerDay(Number(e.target.value))}
              className="w-24"
            />
          </div>
          <Button
            size="sm"
            disabled={saveMutation.isPending}
            onClick={() => saveMutation.mutate({ hr_bonus_lock_day: lockDay, hr_bonus_max_hours_per_day: maxHoursPerDay })}
          >
            <Save className="mr-1.5 h-4 w-4" />
            {saveMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function BonusTypesSection() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editType, setEditType] = useState<BonusType | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: bonusTypes = [], isLoading } = useQuery({
    queryKey: ['settings', 'bonusTypes'],
    queryFn: () => hrApi.getBonusTypes(),
    staleTime: 10 * 60_000,
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<BonusType>) => hrApi.createBonusType(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'bonusTypes'] })
      setShowAdd(false)
      toast.success('Bonus type created')
    },
    onError: () => toast.error('Failed to create bonus type'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<BonusType> }) => hrApi.updateBonusType(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'bonusTypes'] })
      setEditType(null)
      toast.success('Bonus type updated')
    },
    onError: () => toast.error('Failed to update bonus type'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => hrApi.deleteBonusType(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'bonusTypes'] })
      setDeleteId(null)
      toast.success('Bonus type deleted')
    },
    onError: () => toast.error('Failed to delete bonus type'),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Bonus Types</CardTitle>
            <CardDescription>Configure bonus types used for event bonuses.</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Type
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
        ) : bonusTypes.length === 0 ? (
          <EmptyState title="No bonus types" description="Add your first bonus type." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Amount (RON)</TableHead>
                <TableHead>Days/Amount</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {bonusTypes.map((bt) => (
                <TableRow key={bt.id}>
                  <TableCell className="font-medium">{bt.name}</TableCell>
                  <TableCell>{bt.amount}</TableCell>
                  <TableCell>{bt.days_per_amount || '-'}</TableCell>
                  <TableCell className="max-w-xs truncate text-muted-foreground text-sm">
                    {bt.description || '-'}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={bt.is_active ? 'active' : 'archived'} />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditType(bt)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(bt.id)}>
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

      <BonusTypeFormDialog
        open={showAdd || !!editType}
        bonusType={editType}
        onClose={() => { setShowAdd(false); setEditType(null) }}
        onSave={(data) => {
          if (editType) {
            updateMutation.mutate({ id: editType.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Bonus Type"
        description="This action cannot be undone."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

function BonusTypeFormDialog({ open, bonusType, onClose, onSave, isPending }: {
  open: boolean; bonusType: BonusType | null; onClose: () => void
  onSave: (data: Partial<BonusType>) => void; isPending: boolean
}) {
  const [form, setForm] = useState({ name: '', amount: '', days_per_amount: '', description: '' })

  const resetForm = () => {
    if (bonusType) {
      setForm({
        name: bonusType.name,
        amount: String(bonusType.amount),
        days_per_amount: bonusType.days_per_amount ? String(bonusType.days_per_amount) : '',
        description: bonusType.description || '',
      })
    } else {
      setForm({ name: '', amount: '', days_per_amount: '', description: '' })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-sm" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{bonusType ? 'Edit Bonus Type' : 'Add Bonus Type'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Amount (RON)</Label>
              <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            </div>
            <div className="grid gap-2">
              <Label>Days per Amount</Label>
              <Input
                type="number"
                value={form.days_per_amount}
                onChange={(e) => setForm({ ...form, days_per_amount: e.target.value })}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Description</Label>
            <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!form.name || !form.amount || isPending}
            onClick={() =>
              onSave({
                name: form.name,
                amount: Number(form.amount),
                days_per_amount: form.days_per_amount ? Number(form.days_per_amount) : undefined,
                description: form.description || undefined,
                is_active: bonusType?.is_active ?? true,
              })
            }
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
