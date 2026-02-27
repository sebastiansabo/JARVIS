import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useDebounce } from '@/lib/utils'
import { Plus, Edit2, Trash2, Check, X, Search, Building2, User } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { dmsApi } from '@/api/dms'
import type { DmsSupplier, DmsSupplierType } from '@/types/dms'

interface SupplierManagerProps {
  companyId?: number
}

const EMPTY: Partial<DmsSupplier> = {
  name: '',
  supplier_type: 'company',
  cui: '',
  j_number: '',
  nr_reg_com: '',
  address: '',
  city: '',
  county: '',
  bank_account: '',
  iban: '',
  bank_name: '',
  phone: '',
  email: '',
}

export default function SupplierManager({ companyId }: SupplierManagerProps) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [editSup, setEditSup] = useState<DmsSupplier | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteSupId, setDeleteSupId] = useState<number | null>(null)
  const [form, setForm] = useState<Partial<DmsSupplier>>(EMPTY)

  const debouncedSearch = useDebounce(search, 300)

  const { data, isLoading } = useQuery({
    queryKey: ['dms-suppliers', companyId, debouncedSearch],
    queryFn: () => dmsApi.listSuppliers({ search: debouncedSearch || undefined, active_only: false, limit: 200 }),
  })
  const suppliers: DmsSupplier[] = data?.suppliers || []

  const resetForm = () => setForm({ ...EMPTY })

  const setField = (key: keyof DmsSupplier, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const createMutation = useMutation({
    mutationFn: (data: Partial<DmsSupplier>) => dmsApi.createSupplier(data),
    onSuccess: () => {
      toast.success('Supplier created')
      queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] })
      resetForm()
      setCreateOpen(false)
    },
    onError: () => toast.error('Failed to create supplier'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DmsSupplier> }) =>
      dmsApi.updateSupplier(id, data),
    onSuccess: () => {
      toast.success('Supplier updated')
      queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] })
      setEditSup(null)
      resetForm()
    },
    onError: () => toast.error('Failed to update supplier'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => dmsApi.deleteSupplier(id),
    onSuccess: () => {
      toast.success('Supplier deactivated')
      queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] })
      setDeleteSupId(null)
    },
    onError: () => toast.error('Failed to delete supplier'),
  })

  const openEdit = (sup: DmsSupplier) => {
    setEditSup(sup)
    setForm({
      name: sup.name,
      supplier_type: sup.supplier_type,
      cui: sup.cui || '',
      j_number: sup.j_number || '',
      nr_reg_com: sup.nr_reg_com || '',
      address: sup.address || '',
      city: sup.city || '',
      county: sup.county || '',
      bank_account: sup.bank_account || '',
      iban: sup.iban || '',
      bank_name: sup.bank_name || '',
      phone: sup.phone || '',
      email: sup.email || '',
    })
  }

  const handleSave = () => {
    const payload: Record<string, unknown> = {
      name: (form.name || '').trim(),
      supplier_type: form.supplier_type || 'company',
      cui: (form.cui || '').trim() || null,
      j_number: (form.j_number || '').trim() || null,
      nr_reg_com: (form.nr_reg_com || '').trim() || null,
      address: (form.address || '').trim() || null,
      city: (form.city || '').trim() || null,
      county: (form.county || '').trim() || null,
      bank_account: (form.bank_account || '').trim() || null,
      iban: (form.iban || '').trim() || null,
      bank_name: (form.bank_name || '').trim() || null,
      phone: (form.phone || '').trim() || null,
      email: (form.email || '').trim() || null,
    }
    if (editSup) {
      updateMutation.mutate({ id: editSup.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const formDialog = createOpen || editSup

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Supplier List</h3>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search suppliers..."
              className="pl-8 w-[220px] h-9"
            />
          </div>
          <Button size="sm" onClick={() => { resetForm(); setCreateOpen(true) }}>
            <Plus className="h-4 w-4 mr-1" />
            New Supplier
          </Button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading suppliers...</p>
      ) : suppliers.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">
          {search ? 'No suppliers match your search.' : 'No suppliers yet. Add your first supplier.'}
        </p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>CUI</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Email</TableHead>
                <TableHead className="text-center">Active</TableHead>
                <TableHead className="w-[80px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppliers.map((sup) => (
                <TableRow key={sup.id}>
                  <TableCell className="font-medium">{sup.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {sup.supplier_type === 'company' ? (
                        <><Building2 className="h-3 w-3 mr-1 inline" />Company</>
                      ) : (
                        <><User className="h-3 w-3 mr-1 inline" />Person</>
                      )}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{sup.cui || '—'}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{sup.phone || '—'}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{sup.email || '—'}</TableCell>
                  <TableCell className="text-center">
                    {sup.is_active ? (
                      <Check className="h-4 w-4 text-green-600 mx-auto" />
                    ) : (
                      <X className="h-4 w-4 text-muted-foreground mx-auto" />
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(sup)}>
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDeleteSupId(sup.id)}>
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
          if (!open) { setCreateOpen(false); setEditSup(null); resetForm() }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editSup ? 'Edit Supplier' : 'New Supplier'}</DialogTitle>
          </DialogHeader>

          <div className="space-y-3">
            <div className="grid grid-cols-[1fr_140px] gap-3">
              <div className="space-y-1.5">
                <Label>Name *</Label>
                <Input value={form.name || ''} onChange={(e) => setField('name', e.target.value)} placeholder="Supplier name" />
              </div>
              <div className="space-y-1.5">
                <Label>Type</Label>
                <Select value={form.supplier_type || 'company'} onValueChange={(v) => setField('supplier_type', v as DmsSupplierType)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="company">Company</SelectItem>
                    <SelectItem value="person">Person</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>CUI / CIF</Label>
                <Input value={form.cui || ''} onChange={(e) => setField('cui', e.target.value)} placeholder="Tax ID" />
              </div>
              <div className="space-y-1.5">
                <Label>Nr. Reg. Com.</Label>
                <Input value={form.nr_reg_com || ''} onChange={(e) => setField('nr_reg_com', e.target.value)} placeholder="J00/000/0000" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>J Number</Label>
                <Input value={form.j_number || ''} onChange={(e) => setField('j_number', e.target.value)} placeholder="Trade registry" />
              </div>
              <div className="space-y-1.5">
                <Label>Phone</Label>
                <Input value={form.phone || ''} onChange={(e) => setField('phone', e.target.value)} placeholder="Phone number" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Address</Label>
              <Input value={form.address || ''} onChange={(e) => setField('address', e.target.value)} placeholder="Street address" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>City</Label>
                <Input value={form.city || ''} onChange={(e) => setField('city', e.target.value)} placeholder="City" />
              </div>
              <div className="space-y-1.5">
                <Label>County</Label>
                <Input value={form.county || ''} onChange={(e) => setField('county', e.target.value)} placeholder="County" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Email</Label>
              <Input value={form.email || ''} onChange={(e) => setField('email', e.target.value)} placeholder="Email address" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Bank Name</Label>
                <Input value={form.bank_name || ''} onChange={(e) => setField('bank_name', e.target.value)} placeholder="Bank name" />
              </div>
              <div className="space-y-1.5">
                <Label>IBAN</Label>
                <Input value={form.iban || ''} onChange={(e) => setField('iban', e.target.value)} placeholder="IBAN" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Bank Account</Label>
              <Input value={form.bank_account || ''} onChange={(e) => setField('bank_account', e.target.value)} placeholder="Account number" />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreateOpen(false); setEditSup(null); resetForm() }}>
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={!(form.name || '').trim() || createMutation.isPending || updateMutation.isPending}
            >
              {editSup ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={deleteSupId !== null}
        onOpenChange={(open) => !open && setDeleteSupId(null)}
        title="Deactivate Supplier"
        description="This will deactivate the supplier. They won't appear in search results anymore."
        confirmLabel="Deactivate"
        variant="destructive"
        onConfirm={() => deleteSupId && deleteMutation.mutate(deleteSupId)}
      />
    </div>
  )
}
