import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Building2, User, Pencil, Save, X, ExternalLink, UserCircle, Briefcase,
  FileText, Receipt, Mail, Phone, MapPin, Landmark, Hash, Shield, RefreshCw,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { StatCard } from '@/components/shared/StatCard'
import { TagBadgeList } from '@/components/shared/TagBadge'
import { TagPickerButton } from '@/components/shared/TagPicker'
import { dmsApi } from '@/api/dms'
import { tagsApi } from '@/api/tags'
import type { DmsSupplier, DmsSupplierType } from '@/types/dms'

function formatNum(n: number | undefined | null): string {
  if (!n) return '—'
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(n)
}

function formatDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ro-RO')
}

function InfoRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-start gap-3 py-2">
      <Icon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="text-sm font-medium truncate">{value || '—'}</div>
      </div>
    </div>
  )
}

export default function SupplierProfile() {
  const { supplierId } = useParams<{ supplierId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const id = Number(supplierId)

  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<DmsSupplier>>({})
  const [tab, setTab] = useState<'documents' | 'invoices'>('documents')

  const { data: supData, isLoading } = useQuery({
    queryKey: ['dms-supplier', id],
    queryFn: () => dmsApi.getSupplier(id),
    enabled: !!id,
  })
  const supplier = supData?.supplier

  const { data: docsData } = useQuery({
    queryKey: ['supplier-documents', id],
    queryFn: () => dmsApi.getSupplierDocuments(id, 50),
    enabled: !!id,
  })

  const { data: invData } = useQuery({
    queryKey: ['supplier-invoices', id],
    queryFn: () => dmsApi.getSupplierInvoices(id, 50),
    enabled: !!id,
  })

  const { data: tags = [] } = useQuery({
    queryKey: ['entity-tags', 'supplier', id],
    queryFn: () => tagsApi.getEntityTags('supplier', id),
    enabled: !!id,
  })

  const docs = docsData?.documents || []
  const invoices = invData?.invoices || []

  const totalRon = invoices.reduce((s, inv) => s + (inv.value_ron || 0), 0)
  const totalEur = invoices.reduce((s, inv) => s + (inv.value_eur || 0), 0)

  const updateMutation = useMutation({
    mutationFn: (data: Partial<DmsSupplier>) => dmsApi.updateSupplier(id, data),
    onSuccess: () => {
      toast.success('Supplier updated')
      queryClient.invalidateQueries({ queryKey: ['dms-supplier', id] })
      queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] })
      setEditing(false)
    },
    onError: () => toast.error('Failed to update supplier'),
  })

  const anafMutation = useMutation({
    mutationFn: () => dmsApi.syncAnaf(id),
    onSuccess: (res) => {
      const fields = res.updated_fields || []
      if (fields.length > 0) {
        toast.success(`Synced from ANAF: ${fields.join(', ')}`)
      } else {
        toast.info('All fields already up to date')
      }
      if (res.anaf_name) {
        toast.info(`ANAF name: ${res.anaf_name}`, { duration: 5000 })
      }
      queryClient.invalidateQueries({ queryKey: ['dms-supplier', id] })
      queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] })
    },
    onError: (err: Error & { response?: { data?: { error?: string } } }) => {
      const msg = err?.response?.data?.error || 'ANAF sync failed'
      toast.error(msg)
    },
  })

  const startEdit = () => {
    if (!supplier) return
    setForm({
      name: supplier.name,
      supplier_type: supplier.supplier_type,
      cui: supplier.cui || '',
      j_number: supplier.j_number || '',
      nr_reg_com: supplier.nr_reg_com || '',
      address: supplier.address || '',
      city: supplier.city || '',
      county: supplier.county || '',
      bank_account: supplier.bank_account || '',
      iban: supplier.iban || '',
      bank_name: supplier.bank_name || '',
      phone: supplier.phone || '',
      email: supplier.email || '',
      contact_name: supplier.contact_name || '',
      contact_function: supplier.contact_function || '',
      contact_email: supplier.contact_email || '',
      contact_phone: supplier.contact_phone || '',
      owner_name: supplier.owner_name || '',
      owner_function: supplier.owner_function || '',
      owner_email: supplier.owner_email || '',
      owner_phone: supplier.owner_phone || '',
    })
    setEditing(true)
  }

  const handleSave = () => {
    const payload: Partial<DmsSupplier> = {
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
      contact_name: (form.contact_name || '').trim() || null,
      contact_function: (form.contact_function || '').trim() || null,
      contact_email: (form.contact_email || '').trim() || null,
      contact_phone: (form.contact_phone || '').trim() || null,
      owner_name: (form.owner_name || '').trim() || null,
      owner_function: (form.owner_function || '').trim() || null,
      owner_email: (form.owner_email || '').trim() || null,
      owner_phone: (form.owner_phone || '').trim() || null,
    }
    updateMutation.mutate(payload)
  }

  const setField = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }))

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-4 gap-3">
          <Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" />
        </div>
        <Skeleton className="h-48" />
      </div>
    )
  }

  if (!supplier) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/app/dms')}>
          <ArrowLeft className="mr-1.5 h-4 w-4" /> Back to Documents
        </Button>
        <p className="text-muted-foreground">Supplier not found.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <Button variant="ghost" size="sm" className="mb-1 -ml-2" onClick={() => navigate('/app/dms')}>
            <ArrowLeft className="mr-1.5 h-4 w-4" /> Suppliers
          </Button>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{supplier.name}</h1>
            <Badge variant="outline" className="gap-1">
              {supplier.supplier_type === 'company' ? <Building2 className="h-3 w-3" /> : <User className="h-3 w-3" />}
              {supplier.supplier_type}
            </Badge>
            {supplier.is_active ? (
              <Badge variant="default" className="bg-green-600">Active</Badge>
            ) : (
              <Badge variant="secondary">Inactive</Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          <TagBadgeList tags={tags} />
          <TagPickerButton
            entityType="supplier"
            entityIds={[id]}
            onTagsChanged={() => queryClient.invalidateQueries({ queryKey: ['entity-tags', 'supplier', id] })}
          />
          {editing ? (
            <>
              <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
                <X className="mr-1.5 h-3.5 w-3.5" /> Cancel
              </Button>
              <Button size="sm" onClick={handleSave} disabled={!(form.name || '').trim() || updateMutation.isPending}>
                <Save className="mr-1.5 h-3.5 w-3.5" /> Save
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => anafMutation.mutate()}
                disabled={anafMutation.isPending || !supplier.cui}
                title={!supplier.cui ? 'No CUI — add a CUI first to sync' : 'Fetch company data from ANAF'}
              >
                <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${anafMutation.isPending ? 'animate-spin' : ''}`} />
                Sync ANAF
              </Button>
              <Button variant="outline" size="sm" onClick={startEdit}>
                <Pencil className="mr-1.5 h-3.5 w-3.5" /> Edit
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard title="Documents" value={docs.length} icon={<FileText className="h-4 w-4" />} />
        <StatCard title="Invoices" value={invoices.length} icon={<Receipt className="h-4 w-4" />} />
        <StatCard title="Total RON" value={formatNum(totalRon)} icon={<Landmark className="h-4 w-4" />} />
        <StatCard title="Total EUR" value={formatNum(totalEur)} icon={<Landmark className="h-4 w-4" />} />
      </div>

      {/* Supplier details */}
      {editing ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Supplier Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-[1fr_140px] gap-3">
              <div className="space-y-1.5">
                <Label>Name *</Label>
                <Input value={form.name || ''} onChange={(e) => setField('name', e.target.value)} />
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
              <div className="space-y-1.5"><Label>CUI / CIF</Label><Input value={form.cui || ''} onChange={(e) => setField('cui', e.target.value)} /></div>
              <div className="space-y-1.5"><Label>Nr. Reg. Com.</Label><Input value={form.nr_reg_com || ''} onChange={(e) => setField('nr_reg_com', e.target.value)} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>J Number</Label><Input value={form.j_number || ''} onChange={(e) => setField('j_number', e.target.value)} /></div>
              <div className="space-y-1.5"><Label>Phone</Label><Input value={form.phone || ''} onChange={(e) => setField('phone', e.target.value)} /></div>
            </div>
            <div className="space-y-1.5"><Label>Address</Label><Input value={form.address || ''} onChange={(e) => setField('address', e.target.value)} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>City</Label><Input value={form.city || ''} onChange={(e) => setField('city', e.target.value)} /></div>
              <div className="space-y-1.5"><Label>County</Label><Input value={form.county || ''} onChange={(e) => setField('county', e.target.value)} /></div>
            </div>
            <div className="space-y-1.5"><Label>Email</Label><Input value={form.email || ''} onChange={(e) => setField('email', e.target.value)} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Bank Name</Label><Input value={form.bank_name || ''} onChange={(e) => setField('bank_name', e.target.value)} /></div>
              <div className="space-y-1.5"><Label>IBAN</Label><Input value={form.iban || ''} onChange={(e) => setField('iban', e.target.value)} /></div>
            </div>
            <div className="pt-3 border-t">
              <p className="text-sm font-medium mb-2">Contact Person</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Name</Label><Input value={form.contact_name || ''} onChange={(e) => setField('contact_name', e.target.value)} /></div>
                <div className="space-y-1.5"><Label>Function</Label><Input value={form.contact_function || ''} onChange={(e) => setField('contact_function', e.target.value)} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <div className="space-y-1.5"><Label>Email</Label><Input value={form.contact_email || ''} onChange={(e) => setField('contact_email', e.target.value)} /></div>
                <div className="space-y-1.5"><Label>Phone</Label><Input value={form.contact_phone || ''} onChange={(e) => setField('contact_phone', e.target.value)} /></div>
              </div>
            </div>
            <div className="pt-3 border-t">
              <p className="text-sm font-medium mb-2">Owner</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Name</Label><Input value={form.owner_name || ''} onChange={(e) => setField('owner_name', e.target.value)} /></div>
                <div className="space-y-1.5"><Label>Function</Label><Input value={form.owner_function || ''} onChange={(e) => setField('owner_function', e.target.value)} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <div className="space-y-1.5"><Label>Email</Label><Input value={form.owner_email || ''} onChange={(e) => setField('owner_email', e.target.value)} /></div>
                <div className="space-y-1.5"><Label>Phone</Label><Input value={form.owner_phone || ''} onChange={(e) => setField('owner_phone', e.target.value)} /></div>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Company Info</CardTitle>
            </CardHeader>
            <CardContent className="space-y-0 divide-y">
              <InfoRow icon={Hash} label="CUI / CIF" value={supplier.cui} />
              <InfoRow icon={Shield} label="Nr. Reg. Com." value={supplier.nr_reg_com} />
              <InfoRow icon={Hash} label="J Number" value={supplier.j_number} />
              <InfoRow icon={Phone} label="Phone" value={supplier.phone} />
              <InfoRow icon={Mail} label="Email" value={supplier.email} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Address & Banking</CardTitle>
            </CardHeader>
            <CardContent className="space-y-0 divide-y">
              <InfoRow icon={MapPin} label="Address" value={supplier.address} />
              <InfoRow icon={MapPin} label="City / County" value={[supplier.city, supplier.county].filter(Boolean).join(', ') || null} />
              <InfoRow icon={Landmark} label="Bank" value={supplier.bank_name} />
              <InfoRow icon={Landmark} label="IBAN" value={supplier.iban} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Contact Person</CardTitle>
            </CardHeader>
            <CardContent className="space-y-0 divide-y">
              <InfoRow icon={UserCircle} label="Name" value={supplier.contact_name} />
              <InfoRow icon={Briefcase} label="Function" value={supplier.contact_function} />
              <InfoRow icon={Mail} label="Email" value={supplier.contact_email} />
              <InfoRow icon={Phone} label="Phone" value={supplier.contact_phone} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Owner</CardTitle>
            </CardHeader>
            <CardContent className="space-y-0 divide-y">
              <InfoRow icon={UserCircle} label="Name" value={supplier.owner_name} />
              <InfoRow icon={Briefcase} label="Function" value={supplier.owner_function} />
              <InfoRow icon={Mail} label="Email" value={supplier.owner_email} />
              <InfoRow icon={Phone} label="Phone" value={supplier.owner_phone} />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Documents & Invoices tabs */}
      <Card>
        <div className="flex gap-0 border-b">
          <button
            type="button"
            className={`px-5 py-2.5 text-sm font-medium transition-colors ${tab === 'documents' ? 'border-b-2 border-primary text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            onClick={() => setTab('documents')}
          >
            Documents {docs.length > 0 && <span className="ml-1 text-xs text-muted-foreground">({docs.length})</span>}
          </button>
          <button
            type="button"
            className={`px-5 py-2.5 text-sm font-medium transition-colors ${tab === 'invoices' ? 'border-b-2 border-primary text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            onClick={() => setTab('invoices')}
          >
            Invoices {invoices.length > 0 && <span className="ml-1 text-xs text-muted-foreground">({invoices.length})</span>}
          </button>
        </div>

        {/* Documents */}
        {tab === 'documents' && (
          <div className="max-h-[400px] overflow-y-auto">
            {docs.length === 0 ? (
              <p className="text-sm text-muted-foreground px-5 py-6 text-center">No documents linked to this supplier.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card backdrop-blur-sm">
                  <tr className="border-b">
                    <th className="text-left font-medium px-4 py-2.5">Title</th>
                    <th className="text-left font-medium px-3 py-2.5 w-[120px]">Category</th>
                    <th className="text-left font-medium px-3 py-2.5 w-[90px]">Role</th>
                    <th className="text-left font-medium px-3 py-2.5 w-[80px]">Type</th>
                    <th className="text-left font-medium px-3 py-2.5 w-[100px]">Date</th>
                    <th className="text-center font-medium px-3 py-2.5 w-[80px]">Status</th>
                    <th className="w-[50px]" />
                  </tr>
                </thead>
                <tbody>
                  {docs.map((doc) => (
                    <tr key={doc.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1.5">
                          {doc.parent_id && <span className="text-muted-foreground">↳</span>}
                          <span className="font-medium">{doc.title}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{doc.category_name || '—'}</td>
                      <td className="px-3 py-2">
                        <Badge variant="outline" className="text-[11px] px-1.5 py-0">{doc.party_role}</Badge>
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">
                        {doc.parent_id ? (doc.relationship_type || 'annex') : 'main'}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{formatDate(doc.doc_date)}</td>
                      <td className="px-3 py-2 text-center">
                        <Badge variant="outline" className="text-[11px] px-1.5 py-0">{doc.status}</Badge>
                      </td>
                      <td className="px-2 py-2">
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => navigate(`/app/dms/documents/${doc.id}`)}>
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Invoices */}
        {tab === 'invoices' && (
          <div className="max-h-[400px] overflow-y-auto">
            {invoices.length === 0 ? (
              <p className="text-sm text-muted-foreground px-5 py-6 text-center">No invoices found for this supplier.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card backdrop-blur-sm">
                  <tr className="border-b">
                    <th className="text-left font-medium px-4 py-2.5">Invoice #</th>
                    <th className="text-left font-medium px-3 py-2.5 w-[100px]">Date</th>
                    <th className="text-right font-medium px-3 py-2.5 w-[100px]">Value</th>
                    <th className="text-left font-medium px-2 py-2.5 w-[50px]">Cur.</th>
                    <th className="text-right font-medium px-3 py-2.5 w-[90px]">RON</th>
                    <th className="text-center font-medium px-3 py-2.5 w-[90px]">Status</th>
                    <th className="text-center font-medium px-3 py-2.5 w-[90px]">Payment</th>
                    <th className="w-[50px]" />
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr key={inv.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-2 font-medium">{inv.invoice_number || '—'}</td>
                      <td className="px-3 py-2 text-muted-foreground">{formatDate(inv.invoice_date)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(inv.invoice_value)}
                      </td>
                      <td className="px-2 py-2 text-muted-foreground">{inv.currency}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatNum(inv.value_ron)}</td>
                      <td className="px-3 py-2 text-center">
                        <Badge variant="outline" className="text-[11px] px-1.5 py-0">{inv.status}</Badge>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Badge variant={inv.payment_status === 'paid' ? 'default' : 'outline'} className="text-[11px] px-1.5 py-0">
                          {inv.payment_status}
                        </Badge>
                      </td>
                      <td className="px-2 py-2">
                        {inv.drive_link ? (
                          <a
                            href={inv.drive_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center justify-center h-7 w-7 rounded hover:bg-accent transition-colors"
                            title="Download invoice"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}
