import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Pencil,
  Trash2,
  Tags,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { SearchInput } from '@/components/shared/SearchInput'
import { EmptyState } from '@/components/shared/EmptyState'
import { efacturaApi } from '@/api/efactura'
import { organizationApi } from '@/api/organization'
import type { SupplierMapping, SupplierType } from '@/types/efactura'

type ViewMode = 'mappings' | 'types'

// ── Mapping Form ───────────────────────────────────────────
function MappingFormDialog({
  open,
  onOpenChange,
  mapping,
  supplierTypes,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  mapping: SupplierMapping | null
  supplierTypes: SupplierType[]
}) {
  const qc = useQueryClient()
  const [company, setCompany] = useState('')
  const [form, setForm] = useState({
    partner_name: mapping?.partner_name ?? '',
    partner_cif: mapping?.partner_cif ?? '',
    supplier_name: mapping?.supplier_name ?? '',
    supplier_vat: mapping?.supplier_vat ?? '',
    supplier_note: mapping?.supplier_note ?? '',
    kod_konto: mapping?.kod_konto ?? '',
    brand: mapping?.brand ?? '',
    department: mapping?.department ?? '',
    subdepartment: mapping?.subdepartment ?? '',
    type_ids: mapping?.type_ids ?? [],
  })

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }))

  const toggleType = (id: number) => {
    setForm((f) => ({
      ...f,
      type_ids: f.type_ids.includes(id) ? f.type_ids.filter((t) => t !== id) : [...f.type_ids, id],
    }))
  }

  // ── Company structure queries ──
  const { data: companies = [] } = useQuery({
    queryKey: ['companies'],
    queryFn: () => organizationApi.getCompanies(),
  })

  const { data: brands = [] } = useQuery({
    queryKey: ['brands', company],
    queryFn: () => organizationApi.getBrands(company),
    enabled: !!company,
  })

  const { data: departments = [] } = useQuery({
    queryKey: ['departments', company],
    queryFn: () => organizationApi.getDepartments(company),
    enabled: !!company,
  })

  const { data: subdepartments = [] } = useQuery({
    queryKey: ['subdepartments', company, form.department],
    queryFn: () => organizationApi.getSubdepartments(company, form.department),
    enabled: !!company && !!form.department,
  })

  const createMut = useMutation({
    mutationFn: () => efacturaApi.createMapping(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['efactura-mappings'] }); onOpenChange(false) },
  })

  const updateMut = useMutation({
    mutationFn: () => efacturaApi.updateMapping(mapping!.id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['efactura-mappings'] }); onOpenChange(false) },
  })

  const isEdit = !!mapping
  const isPending = createMut.isPending || updateMut.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Mapping' : 'Add Mapping'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Supplier Name (e-Factura) *</Label>
              <Input value={form.partner_name} onChange={(e) => set('partner_name', e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Supplier CIF</Label>
              <Input value={form.partner_cif} onChange={(e) => set('partner_cif', e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Mapped Name *</Label>
              <Input value={form.supplier_name} onChange={(e) => set('supplier_name', e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Supplier VAT</Label>
              <Input value={form.supplier_vat} onChange={(e) => set('supplier_vat', e.target.value)} />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Kod Konto</Label>
            <Input value={form.kod_konto} onChange={(e) => set('kod_konto', e.target.value)} />
          </div>

          {/* Supplier Types — prominent toggle buttons */}
          {supplierTypes.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs">Supplier Types *</Label>
              <div className="flex flex-wrap gap-2">
                {supplierTypes.map((pt) => {
                  const active = form.type_ids.includes(pt.id)
                  return (
                    <button
                      key={pt.id}
                      type="button"
                      onClick={() => toggleType(pt.id)}
                      className={`rounded-md border-2 px-4 py-2 text-sm font-semibold transition-all ${
                        active
                          ? 'border-primary bg-primary text-primary-foreground shadow-sm'
                          : 'border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground'
                      }`}
                    >
                      {pt.name}
                    </button>
                  )
                })}
              </div>
              {form.type_ids.length === 0 && (
                <p className="text-[11px] text-amber-600 dark:text-amber-400">Select at least one type</p>
              )}
            </div>
          )}

          {/* Company selector for structure lookups */}
          <div className="space-y-1">
            <Label className="text-xs">Company (for Brand/Dept lookups)</Label>
            <Select
              value={company || '__none__'}
              onValueChange={(v) => {
                setCompany(v === '__none__' ? '' : v)
                set('brand', '')
                set('department', '')
                set('subdepartment', '')
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">-- Select Company --</SelectItem>
                {companies.map((c) => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">Select a company to populate Brand, Department, Subdepartment dropdowns</p>
          </div>

          {/* Brand */}
          <div className="space-y-1">
            <Label className="text-xs">Brand</Label>
            {company && brands.length > 0 ? (
              <Select
                value={form.brand || '__none__'}
                onValueChange={(v) => set('brand', v === '__none__' ? '' : v)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">-- None --</SelectItem>
                  {brands.map((b) => (
                    <SelectItem key={b} value={b}>{b}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input value={form.brand} onChange={(e) => set('brand', e.target.value)} placeholder={company ? 'No brands found' : 'Select company first'} />
            )}
          </div>

          {/* Department */}
          <div className="space-y-1">
            <Label className="text-xs">Department</Label>
            {company && departments.length > 0 ? (
              <Select
                value={form.department || '__none__'}
                onValueChange={(v) => {
                  set('department', v === '__none__' ? '' : v)
                  set('subdepartment', '')
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">-- None --</SelectItem>
                  {departments.map((d) => (
                    <SelectItem key={d} value={d}>{d}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input value={form.department} onChange={(e) => set('department', e.target.value)} placeholder={company ? 'No departments found' : 'Select company first'} />
            )}
          </div>

          {/* Subdepartment */}
          <div className="space-y-1">
            <Label className="text-xs">Subdepartment</Label>
            {company && form.department ? (
              <Select
                value={form.subdepartment || '__none__'}
                onValueChange={(v) => set('subdepartment', v === '__none__' ? '' : v)}
                disabled={subdepartments.length === 0}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">-- None --</SelectItem>
                  {subdepartments.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input value={form.subdepartment} onChange={(e) => set('subdepartment', e.target.value)} placeholder={!form.department ? 'Select department first' : 'Select company first'} disabled={!company || !form.department} />
            )}
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Note</Label>
            <Input value={form.supplier_note} onChange={(e) => set('supplier_note', e.target.value)} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            onClick={() => (isEdit ? updateMut.mutate() : createMut.mutate())}
            disabled={!form.partner_name || !form.supplier_name || isPending}
          >
            {isPending ? 'Saving...' : isEdit ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Supplier Type Form ──────────────────────────────────────
function TypeFormDialog({
  open,
  onOpenChange,
  supplierType,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  supplierType: SupplierType | null
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name: supplierType?.name ?? '',
    description: supplierType?.description ?? '',
    hide_in_filter: supplierType?.hide_in_filter ?? true,
  })

  const createMut = useMutation({
    mutationFn: () => efacturaApi.createSupplierType(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['efactura-supplier-types'] }); onOpenChange(false) },
  })

  const updateMut = useMutation({
    mutationFn: () => efacturaApi.updateSupplierType(supplierType!.id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['efactura-supplier-types'] }); onOpenChange(false) },
  })

  const isEdit = !!supplierType
  const isPending = createMut.isPending || updateMut.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Supplier Type' : 'Add Supplier Type'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Name *</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Description</Label>
            <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="flex items-center gap-2">
            <Switch
              checked={form.hide_in_filter}
              onCheckedChange={(v) => setForm({ ...form, hide_in_filter: v })}
            />
            <Label className="text-sm">Hide typed invoices in "Hide Typed" filter</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            onClick={() => (isEdit ? updateMut.mutate() : createMut.mutate())}
            disabled={!form.name || isPending}
          >
            {isPending ? 'Saving...' : isEdit ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Main Component ─────────────────────────────────────────
export default function MappingsTab() {
  const qc = useQueryClient()
  const [viewMode, setViewMode] = useState<ViewMode>('mappings')
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [editMapping, setEditMapping] = useState<SupplierMapping | null | undefined>(undefined) // undefined = closed
  const [editType, setEditType] = useState<SupplierType | null | undefined>(undefined)
  const [deleteTarget, setDeleteTarget] = useState<{ type: 'mapping' | 'type'; id: number } | null>(null)

  const { data: mappings = [], isLoading: mappingsLoading } = useQuery({
    queryKey: ['efactura-mappings', showInactive],
    queryFn: () => efacturaApi.getMappings(!showInactive),
  })

  const { data: supplierTypes = [], isLoading: typesLoading } = useQuery({
    queryKey: ['efactura-supplier-types', showInactive],
    queryFn: () => efacturaApi.getSupplierTypes(!showInactive),
  })

  const deleteMappingMut = useMutation({
    mutationFn: (id: number) => efacturaApi.deleteMapping(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['efactura-mappings'] }); setDeleteTarget(null) },
  })

  const deleteTypeMut = useMutation({
    mutationFn: (id: number) => efacturaApi.deleteSupplierType(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['efactura-supplier-types'] }); setDeleteTarget(null) },
  })

  const filteredMappings = mappings.filter((m) => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      m.partner_name.toLowerCase().includes(q) ||
      m.supplier_name.toLowerCase().includes(q) ||
      (m.partner_cif && m.partner_cif.includes(q)) ||
      (m.supplier_vat && m.supplier_vat.includes(q))
    )
  })

  const filteredTypes = supplierTypes.filter((t) => {
    if (!search) return true
    return t.name.toLowerCase().includes(search.toLowerCase())
  })

  return (
    <div className="space-y-4">
      {/* View mode toggle */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <Button
            variant={viewMode === 'mappings' ? 'default' : 'outline'}
            size="sm"
            onClick={() => { setViewMode('mappings'); setSearch('') }}
          >
            <Tags className="mr-1.5 h-3.5 w-3.5" />
            Supplier Mappings ({mappings.length})
          </Button>
          <Button
            variant={viewMode === 'types' ? 'default' : 'outline'}
            size="sm"
            onClick={() => { setViewMode('types'); setSearch('') }}
          >
            Supplier Types ({supplierTypes.length})
          </Button>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch checked={showInactive} onCheckedChange={setShowInactive} />
            <span className="text-xs text-muted-foreground">Show inactive</span>
          </div>

          <SearchInput value={search} onChange={setSearch} placeholder="Search..." className="w-[180px]" />

          <Button
            size="sm"
            onClick={() => viewMode === 'mappings' ? setEditMapping(null) : setEditType(null)}
          >
            <Plus className="mr-1 h-3.5 w-3.5" />
            Add {viewMode === 'mappings' ? 'Mapping' : 'Type'}
          </Button>
        </div>
      </div>

      {/* Mappings view */}
      {viewMode === 'mappings' && (
        mappingsLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-12 animate-pulse rounded bg-muted/50" />)}
          </div>
        ) : filteredMappings.length === 0 ? (
          <EmptyState
            icon={<Tags className="h-10 w-10" />}
            title="No supplier mappings"
            description={search ? 'No mappings match your search' : 'Create your first mapping to auto-match suppliers'}
            action={
              !search ? (
                <Button onClick={() => setEditMapping(null)}>
                  <Plus className="mr-1 h-4 w-4" /> Add Mapping
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="rounded border overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="p-2 text-left">Supplier (e-Factura)</th>
                  <th className="p-2 text-left">CIF</th>
                  <th className="p-2 text-left">Mapped Name</th>
                  <th className="p-2 text-left">Types</th>
                  <th className="p-2 text-left">Kod Konto</th>
                  <th className="p-2 text-left">Dept</th>
                  <th className="p-2 text-center">Active</th>
                  <th className="p-2 text-left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredMappings.map((m) => (
                  <tr key={m.id} className="border-b hover:bg-muted/30">
                    <td className="p-2 font-medium">{m.partner_name}</td>
                    <td className="p-2 text-xs text-muted-foreground font-mono">{m.partner_cif || '—'}</td>
                    <td className="p-2">{m.supplier_name}</td>
                    <td className="p-2">
                      {m.type_names?.length ? (
                        <div className="flex flex-wrap gap-1">
                          {m.type_names.map((t, i) => (
                            <span key={i} className="rounded bg-primary/10 px-1.5 py-0.5 text-xs text-primary">
                              {t}
                            </span>
                          ))}
                        </div>
                      ) : '—'}
                    </td>
                    <td className="p-2 text-xs">{m.kod_konto || '—'}</td>
                    <td className="p-2 text-xs">{m.department || '—'}</td>
                    <td className="p-2 text-center">
                      {m.is_active ? (
                        <ToggleRight className="mx-auto h-4 w-4 text-green-600" />
                      ) : (
                        <ToggleLeft className="mx-auto h-4 w-4 text-muted-foreground" />
                      )}
                    </td>
                    <td className="p-2">
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setEditMapping(m)}>
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setDeleteTarget({ type: 'mapping', id: m.id })}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Types view */}
      {viewMode === 'types' && (
        typesLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-12 animate-pulse rounded bg-muted/50" />)}
          </div>
        ) : filteredTypes.length === 0 ? (
          <EmptyState
            icon={<Tags className="h-10 w-10" />}
            title="No supplier types"
            description="Create supplier types to categorize suppliers"
            action={
              <Button onClick={() => setEditType(null)}>
                <Plus className="mr-1 h-4 w-4" /> Add Type
              </Button>
            }
          />
        ) : (
          <div className="rounded border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="p-2 text-left">Name</th>
                  <th className="p-2 text-left">Description</th>
                  <th className="p-2 text-center">Hide in Filter</th>
                  <th className="p-2 text-center">Active</th>
                  <th className="p-2 text-center">Mappings</th>
                  <th className="p-2 text-left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredTypes.map((pt) => (
                  <tr key={pt.id} className="border-b hover:bg-muted/30">
                    <td className="p-2 font-medium">{pt.name}</td>
                    <td className="p-2 text-muted-foreground">{pt.description || '—'}</td>
                    <td className="p-2 text-center">
                      {pt.hide_in_filter ? (
                        <span className="text-xs text-green-600">Yes</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">No</span>
                      )}
                    </td>
                    <td className="p-2 text-center">
                      {pt.is_active ? (
                        <ToggleRight className="mx-auto h-4 w-4 text-green-600" />
                      ) : (
                        <ToggleLeft className="mx-auto h-4 w-4 text-muted-foreground" />
                      )}
                    </td>
                    <td className="p-2 text-center text-muted-foreground">{pt.mapping_count ?? '—'}</td>
                    <td className="p-2">
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setEditType(pt)}>
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setDeleteTarget({ type: 'type', id: pt.id })}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Mapping form dialog */}
      {editMapping !== undefined && (
        <MappingFormDialog
          open
          onOpenChange={() => setEditMapping(undefined)}
          mapping={editMapping}
          supplierTypes={supplierTypes}
        />
      )}

      {/* Type form dialog */}
      {editType !== undefined && (
        <TypeFormDialog
          open
          onOpenChange={() => setEditType(undefined)}
          supplierType={editType}
        />
      )}

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={() => setDeleteTarget(null)}
        title={deleteTarget?.type === 'mapping' ? 'Delete Mapping' : 'Delete Supplier Type'}
        description="Are you sure? This action cannot be undone."
        onConfirm={() => {
          if (!deleteTarget) return
          if (deleteTarget.type === 'mapping') deleteMappingMut.mutate(deleteTarget.id)
          else deleteTypeMut.mutate(deleteTarget.id)
        }}
        destructive
      />
    </div>
  )
}
