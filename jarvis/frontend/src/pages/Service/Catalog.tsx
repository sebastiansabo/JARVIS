import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Pencil, Trash2, ChevronRight, ChevronDown, DollarSign } from 'lucide-react'

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { vouchersApi } from '@/api/vouchers'
import { organizationApi } from '@/api/organization'
import type { ServiceCatalogItem, ServicePricing } from '@/types/vouchers'
import type { CompanyWithBrands } from '@/types/organization'

// ── Service form (create/edit master service) ──────
interface ServiceForm {
  name: string
  category: string
}

const emptyServiceForm: ServiceForm = { name: '', category: '' }

// ── Pricing form (create/edit pricing) ─────────────
interface PricingForm {
  company_id: string
  department: string
  service_code: string
  price: string
  currency: string
}

const emptyPricingForm: PricingForm = { company_id: '', department: '', service_code: '', price: '', currency: 'LEI' }

export default function ServiceCatalog() {
  const queryClient = useQueryClient()

  // Expand state
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  // Service dialog
  const [serviceDialogOpen, setServiceDialogOpen] = useState(false)
  const [editingService, setEditingService] = useState<ServiceCatalogItem | null>(null)
  const [serviceForm, setServiceForm] = useState<ServiceForm>(emptyServiceForm)

  // Pricing dialog
  const [pricingDialogOpen, setPricingDialogOpen] = useState(false)
  const [pricingServiceId, setPricingServiceId] = useState<number | null>(null)
  const [editingPricing, setEditingPricing] = useState<ServicePricing | null>(null)
  const [pricingForm, setPricingForm] = useState<PricingForm>(emptyPricingForm)

  // Delete confirmation
  const [deleteConfirm, setDeleteConfirm] = useState<{ type: 'service'; item: ServiceCatalogItem } | { type: 'pricing'; item: ServicePricing } | null>(null)

  // ── Queries ──────────────────────────────────────────
  const { data: items = [], isLoading } = useQuery({
    queryKey: ['service-catalog'],
    queryFn: vouchersApi.getServiceCatalog,
  })

  const { data: companies = [] } = useQuery({
    queryKey: ['companies-config'],
    queryFn: organizationApi.getCompaniesConfig,
  })

  // ── Toggle expand ────────────────────────────────────
  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // ── Service mutations ────────────────────────────────
  const createServiceMutation = useMutation({
    mutationFn: (data: { name: string; category?: string }) =>
      vouchersApi.createService(data),
    onSuccess: () => {
      toast.success('Service created')
      closeServiceDialog()
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      const msg = err && typeof err === 'object' && 'data' in err
        ? String((err as { data: { error?: string } }).data?.error || 'Failed')
        : err instanceof Error ? err.message : 'Failed to create service'
      toast.error(msg)
    },
  })

  const updateServiceMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name?: string; category?: string } }) =>
      vouchersApi.updateService(id, data),
    onSuccess: () => {
      toast.success('Service updated')
      closeServiceDialog()
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      const msg = err && typeof err === 'object' && 'data' in err
        ? String((err as { data: { error?: string } }).data?.error || 'Failed')
        : err instanceof Error ? err.message : 'Failed to update service'
      toast.error(msg)
    },
  })

  const deleteServiceMutation = useMutation({
    mutationFn: (id: number) => vouchersApi.deleteService(id),
    onSuccess: () => {
      toast.success('Service deactivated')
      setDeleteConfirm(null)
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to delete service')
    },
  })

  // ── Pricing mutations ────────────────────────────────
  const createPricingMutation = useMutation({
    mutationFn: ({ serviceId, data }: { serviceId: number; data: { company_id: number; department?: string; service_code?: string; price: number; currency?: string } }) =>
      vouchersApi.createPricing(serviceId, data),
    onSuccess: () => {
      toast.success('Pricing added')
      closePricingDialog()
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      const msg = err && typeof err === 'object' && 'data' in err
        ? String((err as { data: { error?: string } }).data?.error || 'Failed')
        : err instanceof Error ? err.message : 'Failed to add pricing'
      toast.error(msg)
    },
  })

  const updatePricingMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { department?: string; service_code?: string; price?: number; currency?: string } }) =>
      vouchersApi.updatePricing(id, data),
    onSuccess: () => {
      toast.success('Pricing updated')
      closePricingDialog()
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to update pricing')
    },
  })

  const deletePricingMutation = useMutation({
    mutationFn: (id: number) => vouchersApi.deletePricing(id),
    onSuccess: () => {
      toast.success('Pricing deleted')
      setDeleteConfirm(null)
      queryClient.invalidateQueries({ queryKey: ['service-catalog'] })
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Failed to delete pricing')
    },
  })

  // ── Service dialog helpers ───────────────────────────
  const openCreateService = () => {
    setEditingService(null)
    setServiceForm(emptyServiceForm)
    setServiceDialogOpen(true)
  }

  const openEditService = (item: ServiceCatalogItem) => {
    setEditingService(item)
    setServiceForm({
      name: item.name,
      category: item.category || '',
    })
    setServiceDialogOpen(true)
  }

  const closeServiceDialog = () => {
    setServiceDialogOpen(false)
    setEditingService(null)
    setServiceForm(emptyServiceForm)
  }

  const handleServiceSubmit = () => {
    if (!serviceForm.name.trim()) {
      toast.error('Name is required')
      return
    }
    const payload = {
      name: serviceForm.name.trim(),
      category: serviceForm.category.trim() || undefined,
    }
    if (editingService) {
      updateServiceMutation.mutate({ id: editingService.id, data: payload })
    } else {
      createServiceMutation.mutate(payload)
    }
  }

  // ── Pricing dialog helpers ───────────────────────────
  const openAddPricing = (serviceId: number) => {
    setPricingServiceId(serviceId)
    setEditingPricing(null)
    setPricingForm(emptyPricingForm)
    setPricingDialogOpen(true)
  }

  const openEditPricing = (pricing: ServicePricing) => {
    setPricingServiceId(pricing.service_id)
    setEditingPricing(pricing)
    setPricingForm({
      company_id: String(pricing.company_id),
      department: pricing.department || '',
      service_code: pricing.service_code || '',
      price: String(pricing.price),
      currency: pricing.currency || 'LEI',
    })
    setPricingDialogOpen(true)
  }

  const closePricingDialog = () => {
    setPricingDialogOpen(false)
    setPricingServiceId(null)
    setEditingPricing(null)
    setPricingForm(emptyPricingForm)
  }

  const handlePricingSubmit = () => {
    const price = parseFloat(pricingForm.price)
    if (!editingPricing && !pricingForm.company_id) {
      toast.error('Company is required')
      return
    }
    if (isNaN(price) || price < 0) {
      toast.error('Price must be a valid positive number')
      return
    }
    if (editingPricing) {
      updatePricingMutation.mutate({
        id: editingPricing.id,
        data: {
          department: pricingForm.department.trim() || undefined,
          service_code: pricingForm.service_code.trim() || undefined,
          price,
          currency: pricingForm.currency || 'LEI',
        },
      })
    } else if (pricingServiceId) {
      createPricingMutation.mutate({
        serviceId: pricingServiceId,
        data: {
          company_id: parseInt(pricingForm.company_id),
          department: pricingForm.department.trim() || undefined,
          service_code: pricingForm.service_code.trim() || undefined,
          price,
          currency: pricingForm.currency || 'LEI',
        },
      })
    }
  }

  // ── Helper: get companies not yet priced for a service ──
  const getAvailableCompanies = (svc: ServiceCatalogItem): CompanyWithBrands[] => {
    const pricedIds = new Set(svc.pricing.map((p) => p.company_id))
    return companies.filter((c) => !pricedIds.has(c.id))
  }

  const isSavingService = createServiceMutation.isPending || updateServiceMutation.isPending
  const isSavingPricing = createPricingMutation.isPending || updatePricingMutation.isPending

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Service Catalog</h1>
        <Button size="sm" onClick={openCreateService}>
          <Plus className="mr-1 h-4 w-4" />Add Service
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[40px]"></TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Companies</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-[140px]">Actions</TableHead>
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
              items.map((item) => {
                const isExpanded = expandedIds.has(item.id)
                return (
                  <ServiceRow
                    key={item.id}
                    item={item}
                    isExpanded={isExpanded}
                    onToggle={() => toggleExpand(item.id)}
                    onEditService={() => openEditService(item)}
                    onDeleteService={() => setDeleteConfirm({ type: 'service', item })}
                    onAddPricing={() => openAddPricing(item.id)}
                    onEditPricing={openEditPricing}
                    onDeletePricing={(p) => setDeleteConfirm({ type: 'pricing', item: p })}
                  />
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create / Edit Service Dialog */}
      <Dialog open={serviceDialogOpen} onOpenChange={(open) => { if (!open) closeServiceDialog() }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingService ? 'Edit Service' : 'Add Service'}</DialogTitle>
            <DialogDescription>
              {editingService ? 'Update the master service details.' : 'Create a new master service. Add company pricing after creation.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid gap-1.5">
              <Label htmlFor="svc-name">Name *</Label>
              <Input
                id="svc-name"
                value={serviceForm.name}
                onChange={(e) => setServiceForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Service name"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="svc-category">Category</Label>
              <Input
                id="svc-category"
                value={serviceForm.category}
                onChange={(e) => setServiceForm((f) => ({ ...f, category: e.target.value }))}
                placeholder="Optional category"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeServiceDialog}>Cancel</Button>
            <Button onClick={handleServiceSubmit} disabled={isSavingService}>
              {isSavingService ? 'Saving...' : editingService ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add / Edit Pricing Dialog */}
      <Dialog open={pricingDialogOpen} onOpenChange={(open) => { if (!open) closePricingDialog() }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingPricing ? 'Edit Pricing' : 'Add Company Pricing'}</DialogTitle>
            <DialogDescription>
              {editingPricing
                ? `Update pricing for ${editingPricing.company_name}.`
                : 'Set price for a specific company.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {!editingPricing && (
              <div className="grid gap-1.5">
                <Label>Company *</Label>
                <Select value={pricingForm.company_id} onValueChange={(v) => setPricingForm((f) => ({ ...f, company_id: v }))}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select company..." />
                  </SelectTrigger>
                  <SelectContent>
                    {(pricingServiceId
                      ? getAvailableCompanies(items.find((i) => i.id === pricingServiceId)!)
                      : companies
                    ).map((c) => (
                      <SelectItem key={c.id} value={String(c.id)}>{c.company}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <DepartmentPicker
              companyId={editingPricing ? String(editingPricing.company_id) : pricingForm.company_id}
              companies={companies}
              value={pricingForm.department}
              onChange={(v) => setPricingForm((f) => ({ ...f, department: v }))}
            />
            <div className="grid gap-1.5">
              <Label htmlFor="p-code">Service Code</Label>
              <Input
                id="p-code"
                value={pricingForm.service_code}
                onChange={(e) => setPricingForm((f) => ({ ...f, service_code: e.target.value.toUpperCase() }))}
                placeholder="e.g. SVC-OIL"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="p-price">Price *</Label>
              <Input
                id="p-price"
                type="number"
                min="0"
                step="0.01"
                value={pricingForm.price}
                onChange={(e) => setPricingForm((f) => ({ ...f, price: e.target.value }))}
                placeholder="0.00"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="p-currency">Currency</Label>
              <Input
                id="p-currency"
                value={pricingForm.currency}
                onChange={(e) => setPricingForm((f) => ({ ...f, currency: e.target.value }))}
                placeholder="LEI"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closePricingDialog}>Cancel</Button>
            <Button onClick={handlePricingSubmit} disabled={isSavingPricing}>
              {isSavingPricing ? 'Saving...' : editingPricing ? 'Update' : 'Add'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirm} onOpenChange={() => setDeleteConfirm(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {deleteConfirm?.type === 'service' ? 'Delete Service' : 'Delete Pricing'}
            </DialogTitle>
            <DialogDescription>
              {deleteConfirm?.type === 'service'
                ? <>Are you sure you want to deactivate <strong>{(deleteConfirm.item as ServiceCatalogItem).name}</strong>? This will hide the service from forms.</>
                : <>Are you sure you want to remove pricing for <strong>{(deleteConfirm?.item as ServicePricing)?.company_name}</strong>?</>
              }
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (!deleteConfirm) return
                if (deleteConfirm.type === 'service') {
                  deleteServiceMutation.mutate((deleteConfirm.item as ServiceCatalogItem).id)
                } else {
                  deletePricingMutation.mutate((deleteConfirm.item as ServicePricing).id)
                }
              }}
              disabled={deleteServiceMutation.isPending || deletePricingMutation.isPending}
            >
              {(deleteServiceMutation.isPending || deletePricingMutation.isPending) ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Service Row Component ──────────────────────────────

interface ServiceRowProps {
  item: ServiceCatalogItem
  isExpanded: boolean
  onToggle: () => void
  onEditService: () => void
  onDeleteService: () => void
  onAddPricing: () => void
  onEditPricing: (p: ServicePricing) => void
  onDeletePricing: (p: ServicePricing) => void
}

function ServiceRow({
  item,
  isExpanded,
  onToggle,
  onEditService,
  onDeleteService,
  onAddPricing,
  onEditPricing,
  onDeletePricing,
}: ServiceRowProps) {
  return (
    <>
      {/* Parent row */}
      <TableRow
        className="cursor-pointer hover:bg-muted/50"
        onClick={onToggle}
      >
        <TableCell className="pl-3">
          {item.pricing.length > 0 ? (
            isExpanded
              ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
              : <ChevronRight className="h-4 w-4 text-muted-foreground" />
          ) : (
            <span className="inline-block w-4" />
          )}
        </TableCell>
        <TableCell className="font-medium">{item.name}</TableCell>
        <TableCell>{item.category || '\u2014'}</TableCell>
        <TableCell>
          <Badge variant="secondary">{item.pricing.length}</Badge>
        </TableCell>
        <TableCell>
          <Badge variant="outline" className={item.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}>
            {item.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </TableCell>
        <TableCell>
          <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
            <Button variant="ghost" size="icon" onClick={onEditService} title="Edit service">
              <Pencil className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={onAddPricing} title="Add pricing">
              <DollarSign className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" onClick={onDeleteService} title="Delete service" className="text-destructive hover:text-destructive">
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </TableCell>
      </TableRow>

      {/* Expanded child rows (pricing) */}
      {isExpanded && item.pricing.length > 0 && (
        <TableRow className="bg-muted/20">
          <TableCell />
          <TableCell colSpan={2} className="pl-8 text-xs font-medium text-muted-foreground">Company / Department</TableCell>
          <TableCell className="text-xs font-medium text-muted-foreground">Code</TableCell>
          <TableCell className="text-xs font-medium text-muted-foreground">Price</TableCell>
          <TableCell />
        </TableRow>
      )}
      {isExpanded && item.pricing.map((p) => (
        <TableRow key={`p-${p.id}`} className="bg-muted/30">
          <TableCell />
          <TableCell className="pl-8 text-sm" colSpan={2}>
            <span className="text-muted-foreground">{p.company_name}</span>
            {p.department && <span className="text-xs text-muted-foreground ml-2">/ {p.department}</span>}
          </TableCell>
          <TableCell className="font-mono text-xs">{p.service_code || '\u2014'}</TableCell>
          <TableCell className="text-sm font-medium">{Number(p.price).toLocaleString()} {p.currency}</TableCell>
          <TableCell>
            <div className="flex gap-1">
              <Button variant="ghost" size="icon" onClick={() => onEditPricing(p)} title="Edit pricing">
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" onClick={() => onDeletePricing(p)} title="Delete pricing" className="text-destructive hover:text-destructive">
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

// ── Department Picker (fetches from org structure) ──

function DepartmentPicker({ companyId, companies, value, onChange }: {
  companyId: string
  companies: { id: number; company: string }[]
  value: string
  onChange: (v: string) => void
}) {
  const companyName = companies.find((c) => String(c.id) === companyId)?.company || ''
  const { data: departments = [] } = useQuery({
    queryKey: ['departments', companyName],
    queryFn: () => organizationApi.getDepartments(companyName),
    enabled: !!companyName,
    staleTime: 5 * 60_000,
  })

  return (
    <div className="grid gap-1.5">
      <Label>Department</Label>
      <Select value={value || '__none__'} onValueChange={(v) => onChange(v === '__none__' ? '' : v)}>
        <SelectTrigger>
          <SelectValue placeholder="All departments" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">All departments</SelectItem>
          {departments.map((dept: string) => (
            <SelectItem key={dept} value={dept}>{dept}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
