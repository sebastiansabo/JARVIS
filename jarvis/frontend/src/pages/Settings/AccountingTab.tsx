import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { settingsApi } from '@/api/settings'
import { toast } from 'sonner'
import type { VatRate, DropdownOption } from '@/types/settings'

export default function AccountingTab() {
  return (
    <div className="space-y-6">
      <VatRatesSection />
      <DropdownSection type="invoice_status" title="Invoice Status Options" />
      <DropdownSection type="payment_status" title="Payment Status Options" />
    </div>
  )
}

function VatRatesSection() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editRate, setEditRate] = useState<VatRate | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: vatRates = [], isLoading } = useQuery({
    queryKey: ['settings', 'vatRates'],
    queryFn: () => settingsApi.getVatRates(),
    staleTime: 10 * 60_000,
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<VatRate>) => settingsApi.createVatRate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'vatRates'] })
      setShowAdd(false)
      toast.success('VAT rate added')
    },
    onError: () => toast.error('Failed to add VAT rate'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<VatRate> }) => settingsApi.updateVatRate(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'vatRates'] })
      setEditRate(null)
      toast.success('VAT rate updated')
    },
    onError: () => toast.error('Failed to update VAT rate'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => settingsApi.deleteVatRate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'vatRates'] })
      setDeleteId(null)
      toast.success('VAT rate deleted')
    },
    onError: () => toast.error('Failed to delete VAT rate'),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>VAT Rates</CardTitle>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Rate
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
        ) : vatRates.length === 0 ? (
          <EmptyState title="No VAT rates" description="Add your first VAT rate." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Rate (%)</TableHead>
                <TableHead>Default</TableHead>
                <TableHead>Active</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {vatRates.map((vr) => (
                <TableRow key={vr.id}>
                  <TableCell className="font-medium">{vr.name}</TableCell>
                  <TableCell>{vr.rate}%</TableCell>
                  <TableCell>{vr.is_default ? 'Yes' : '-'}</TableCell>
                  <TableCell>{vr.is_active ? 'Yes' : 'No'}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditRate(vr)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(vr.id)}>
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

      <VatRateFormDialog
        open={showAdd || !!editRate}
        rate={editRate}
        onClose={() => { setShowAdd(false); setEditRate(null) }}
        onSave={(data) => {
          if (editRate) {
            updateMutation.mutate({ id: editRate.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete VAT Rate"
        description="This action cannot be undone."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

function VatRateFormDialog({ open, rate, onClose, onSave, isPending }: {
  open: boolean; rate: VatRate | null; onClose: () => void
  onSave: (data: Partial<VatRate>) => void; isPending: boolean
}) {
  const [name, setName] = useState('')
  const [rateVal, setRateVal] = useState('')
  const [isDefault, setIsDefault] = useState(false)

  const resetForm = () => {
    if (rate) {
      setName(rate.name); setRateVal(String(rate.rate)); setIsDefault(rate.is_default)
    } else {
      setName(''); setRateVal(''); setIsDefault(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-sm" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{rate ? 'Edit VAT Rate' : 'Add VAT Rate'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Rate (%)</Label>
            <Input type="number" value={rateVal} onChange={(e) => setRateVal(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={isDefault} onCheckedChange={setIsDefault} />
            <Label>Default</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!name || !rateVal || isPending}
            onClick={() => onSave({ name, rate: Number(rateVal), is_default: isDefault, is_active: rate?.is_active ?? true })}
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DropdownSection({ type, title }: { type: string; title: string }) {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editOption, setEditOption] = useState<DropdownOption | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: options = [], isLoading } = useQuery({
    queryKey: ['settings', 'dropdownOptions', type],
    queryFn: () => settingsApi.getDropdownOptions(type),
    staleTime: 5 * 60_000,
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<DropdownOption>) => settingsApi.addDropdownOption(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'dropdownOptions', type] })
      setShowAdd(false)
      toast.success('Option added')
    },
    onError: () => toast.error('Failed to add option'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DropdownOption> }) => settingsApi.updateDropdownOption(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'dropdownOptions', type] })
      setEditOption(null)
      toast.success('Option updated')
    },
    onError: () => toast.error('Failed to update option'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => settingsApi.deleteDropdownOption(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'dropdownOptions', type] })
      setDeleteId(null)
      toast.success('Option deleted')
    },
    onError: () => toast.error('Failed to delete option'),
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>Manage {type.replace('_', ' ')} options for invoices.</CardDescription>
          </div>
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Option
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
        ) : options.length === 0 ? (
          <EmptyState title="No options" description="Add your first option." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Color</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Order</TableHead>
                <TableHead>Notify</TableHead>
                <TableHead>Active</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {options.map((opt) => (
                <TableRow key={opt.id}>
                  <TableCell>
                    {opt.color && (
                      <div
                        className="h-5 w-5 rounded border"
                        style={{ backgroundColor: opt.color, opacity: opt.opacity ?? 1 }}
                      />
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{opt.value}</TableCell>
                  <TableCell className="font-medium">{opt.label}</TableCell>
                  <TableCell>{opt.sort_order}</TableCell>
                  <TableCell>{opt.notify_on_status ? 'Yes' : '-'}</TableCell>
                  <TableCell>{opt.is_active ? 'Yes' : 'No'}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => setEditOption(opt)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setDeleteId(opt.id)}>
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

      <DropdownFormDialog
        open={showAdd || !!editOption}
        option={editOption}
        dropdownType={type}
        optionCount={options.length}
        onClose={() => { setShowAdd(false); setEditOption(null) }}
        onSave={(data) => {
          if (editOption) {
            updateMutation.mutate({ id: editOption.id, data })
          } else {
            createMutation.mutate(data)
          }
        }}
        isPending={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmDialog
        open={!!deleteId}
        onOpenChange={() => setDeleteId(null)}
        title="Delete Option"
        description="This action cannot be undone."
        onConfirm={() => deleteId && deleteMutation.mutate(deleteId)}
        destructive
      />
    </Card>
  )
}

function DropdownFormDialog({ open, option, dropdownType, optionCount, onClose, onSave, isPending }: {
  open: boolean; option: DropdownOption | null; dropdownType: string; optionCount: number
  onClose: () => void; onSave: (data: Partial<DropdownOption>) => void; isPending: boolean
}) {
  const [value, setValue] = useState('')
  const [label, setLabel] = useState('')
  const [color, setColor] = useState('#3b82f6')

  const resetForm = () => {
    if (option) {
      setValue(option.value); setLabel(option.label); setColor(option.color || '#3b82f6')
    } else {
      setValue(''); setLabel(''); setColor('#3b82f6')
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-sm" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>{option ? 'Edit Option' : 'Add Option'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Value</Label>
            <Input value={value} onChange={(e) => setValue(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label>Label</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} />
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
          <Button
            disabled={!value || !label || isPending}
            onClick={() => onSave({
              dropdown_type: dropdownType,
              value,
              label,
              color,
              is_active: option?.is_active ?? true,
              sort_order: option?.sort_order ?? optionCount,
            })}
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
