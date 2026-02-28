import { useState, useMemo, Fragment } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { useDebounce } from '@/lib/utils'
import { useIsMobile } from '@/hooks/useMediaQuery'
import {
  Plus, Edit2, Trash2, Check, X, Search, Building2, User, FileText, CheckSquare,
  ChevronRight, ChevronDown, Tags, ArrowUpDown, ArrowUp, ArrowDown, ExternalLink, RefreshCw,
} from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/shared/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { MobileCardList, type MobileCardField } from '@/components/shared/MobileCardList'
import { dmsApi } from '@/api/dms'
import { tagsApi } from '@/api/tags'
import type { DmsSupplier, DmsSupplierType } from '@/types/dms'
import type { EntityTag, Tag } from '@/types/tags'

interface SupplierManagerProps {
  companyId?: number
}

const EMPTY: Partial<DmsSupplier> = {
  name: '', supplier_type: 'company', cui: '', j_number: '', nr_reg_com: '',
  address: '', city: '', county: '', bank_account: '', iban: '', bank_name: '',
  phone: '', email: '',
  contact_name: '', contact_function: '', contact_email: '', contact_phone: '',
  owner_name: '', owner_function: '', owner_email: '', owner_phone: '',
}

type SortKey = 'name' | 'cui' | 'total_ron' | 'document_count' | 'invoice_count'
type SortDir = 'asc' | 'desc'

function formatNum(n: number | undefined | null): string {
  if (!n) return '—'
  return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(n)
}

/* ── Tag cell per supplier ── */
function SupplierTagCell({ supId }: { supId: number }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState<number | null>(null)

  const { data: tags = [] } = useQuery({
    queryKey: ['entity-tags', 'supplier', supId],
    queryFn: () => tagsApi.getEntityTags('supplier', supId),
  })
  const { data: allTags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => tagsApi.getTags() })

  const filtered = (allTags as Tag[]).filter((t) =>
    t.name.toLowerCase().includes(search.toLowerCase()),
  )
  const tagIds = new Set((tags as EntityTag[]).map((t) => t.id))

  const toggle = async (tagId: number) => {
    setBusy(tagId)
    try {
      const action = tagIds.has(tagId) ? 'remove' : 'add'
      if (action === 'add') await tagsApi.addEntityTag('supplier', supId, tagId)
      else await tagsApi.removeEntityTag('supplier', supId, tagId)
      queryClient.invalidateQueries({ queryKey: ['entity-tags', 'supplier', supId] })
    } finally {
      setBusy(null)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="flex flex-wrap gap-0.5 items-center min-h-[1.5rem] cursor-pointer">
          {(tags as EntityTag[]).length === 0 && <span className="text-xs text-muted-foreground">—</span>}
          {(tags as EntityTag[]).map((t) => (
            <Badge key={t.id} variant="outline" className="text-[10px] px-1 py-0" style={{ borderColor: t.color ?? undefined, color: t.color ?? undefined }}>
              {t.name}
            </Badge>
          ))}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[200px] p-0" align="start">
        <div className="p-1.5 border-b">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tags..." className="h-7 text-xs" />
        </div>
        <div className="max-h-[180px] overflow-y-auto p-1">
          {filtered.map((t) => (
            <button
              key={t.id}
              className="w-full text-left text-xs px-2 py-1 rounded hover:bg-accent flex items-center gap-1.5 disabled:opacity-50"
              onClick={() => toggle(t.id)}
              disabled={busy === t.id}
            >
              <Checkbox checked={tagIds.has(t.id)} className="h-3 w-3" tabIndex={-1} />
              <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: t.color || '#6c757d' }} />
              {t.name}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

/* ── Expanded detail: documents + invoices ── */
function SupplierExpandedDetail({ supId }: { supId: number }) {
  const navigate = useNavigate()
  const [tab, setTab] = useState<'documents' | 'invoices'>('documents')

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ['supplier-documents', supId],
    queryFn: () => dmsApi.getSupplierDocuments(supId, 20),
  })
  const { data: invData, isLoading: invLoading } = useQuery({
    queryKey: ['supplier-invoices', supId],
    queryFn: () => dmsApi.getSupplierInvoices(supId, 10),
  })

  const docs = docsData?.documents || []
  const invoices = invData?.invoices || []

  return (
    <div className="border-t">
      {/* Tabs */}
      <div className="flex gap-0 border-b bg-muted/40">
        <button
          type="button"
          className={`px-4 py-1.5 text-xs font-medium transition-colors ${tab === 'documents' ? 'border-b-2 border-primary text-foreground bg-background' : 'text-muted-foreground hover:text-foreground'}`}
          onClick={() => setTab('documents')}
        >
          Documents {docs.length > 0 && <span className="ml-1 text-[10px] text-muted-foreground">({docs.length})</span>}
        </button>
        <button
          type="button"
          className={`px-4 py-1.5 text-xs font-medium transition-colors ${tab === 'invoices' ? 'border-b-2 border-primary text-foreground bg-background' : 'text-muted-foreground hover:text-foreground'}`}
          onClick={() => setTab('invoices')}
        >
          Invoices {invoices.length > 0 && <span className="ml-1 text-[10px] text-muted-foreground">({invoices.length})</span>}
        </button>
      </div>

      {/* Documents tab */}
      {tab === 'documents' && (
        <div className="max-h-[240px] overflow-y-auto">
          {docsLoading ? (
            <p className="text-xs text-muted-foreground px-4 py-3">Loading documents...</p>
          ) : docs.length === 0 ? (
            <p className="text-xs text-muted-foreground px-4 py-3">No documents linked.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-muted/60 backdrop-blur-sm">
                <tr className="border-b">
                  <th className="text-left font-medium px-3 py-1.5">Title</th>
                  <th className="text-left font-medium px-3 py-1.5 w-[100px]">Category</th>
                  <th className="text-left font-medium px-3 py-1.5 w-[80px]">Role</th>
                  <th className="text-left font-medium px-3 py-1.5 w-[80px]">Type</th>
                  <th className="text-left font-medium px-3 py-1.5 w-[90px]">Date</th>
                  <th className="text-center font-medium px-2 py-1.5 w-[70px]">Status</th>
                  <th className="w-[40px]" />
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-3 py-1.5">
                      <div className="flex items-center gap-1.5">
                        {doc.parent_id && <span className="text-muted-foreground">↳</span>}
                        <span className="font-medium">{doc.title}</span>
                      </div>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">{doc.category_name || '—'}</td>
                    <td className="px-3 py-1.5">
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">{doc.party_role}</Badge>
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {doc.parent_id ? (doc.relationship_type || 'annex') : 'main'}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">{doc.doc_date || '—'}</td>
                    <td className="px-2 py-1.5 text-center">
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">{doc.status}</Badge>
                    </td>
                    <td className="px-1 py-1.5">
                      <button
                        type="button"
                        className="inline-flex items-center justify-center h-6 w-6 rounded hover:bg-accent transition-colors"
                        title="Open document"
                        onClick={() => navigate(`/app/dms/documents/${doc.id}`)}
                      >
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Invoices tab */}
      {tab === 'invoices' && (
        <div className="max-h-[240px] overflow-y-auto">
          {invLoading ? (
            <p className="text-xs text-muted-foreground px-4 py-3">Loading invoices...</p>
          ) : invoices.length === 0 ? (
            <p className="text-xs text-muted-foreground px-4 py-3">No invoices found.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-muted/60 backdrop-blur-sm">
                <tr className="border-b">
                  <th className="text-left font-medium px-3 py-1.5">Invoice #</th>
                  <th className="text-left font-medium px-3 py-1.5 w-[90px]">Date</th>
                  <th className="text-right font-medium px-3 py-1.5 w-[90px]">Value</th>
                  <th className="text-left font-medium px-2 py-1.5 w-[50px]">Cur.</th>
                  <th className="text-right font-medium px-3 py-1.5 w-[80px]">RON</th>
                  <th className="text-center font-medium px-2 py-1.5 w-[80px]">Status</th>
                  <th className="text-center font-medium px-2 py-1.5 w-[80px]">Payment</th>
                  <th className="w-[40px]" />
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv) => (
                  <tr key={inv.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-3 py-1.5 font-medium">{inv.invoice_number || '—'}</td>
                    <td className="px-3 py-1.5 text-muted-foreground">{inv.invoice_date || '—'}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(inv.invoice_value)}
                    </td>
                    <td className="px-2 py-1.5 text-muted-foreground">{inv.currency}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{formatNum(inv.value_ron)}</td>
                    <td className="px-2 py-1.5 text-center">
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">{inv.status}</Badge>
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <Badge variant={inv.payment_status === 'paid' ? 'default' : 'outline'} className="text-[10px] px-1.5 py-0">
                        {inv.payment_status}
                      </Badge>
                    </td>
                    <td className="px-1 py-1.5">
                      {inv.drive_link ? (
                        <a
                          href={inv.drive_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center justify-center h-6 w-6 rounded hover:bg-accent transition-colors"
                          title="Download invoice"
                        >
                          <ExternalLink className="h-3 w-3" />
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
    </div>
  )
}

/* ── Invoices popup for mobile ── */
function SupplierInvoicesDialog({ supId, supName, open, onClose }: { supId: number; supName: string; open: boolean; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['supplier-invoices', supId],
    queryFn: () => dmsApi.getSupplierInvoices(supId, 50),
    enabled: open,
  })
  const invoices = data?.invoices || []

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base">Invoices — {supName}</DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto -mx-6 px-6">
          {isLoading ? (
            <p className="text-sm text-muted-foreground py-4">Loading...</p>
          ) : invoices.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">No invoices found.</p>
          ) : (
            <div className="space-y-2">
              {invoices.map((inv) => (
                <div key={inv.id} className="rounded-lg border px-3 py-2 text-sm space-y-0.5">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{inv.invoice_number || '—'}</span>
                    <span className="tabular-nums font-medium">
                      {new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(inv.invoice_value)} {inv.currency}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{inv.invoice_date || '—'}</span>
                    <div className="flex gap-1">
                      <StatusBadge status={inv.status} className="text-[10px] px-1.5 py-0" />
                      <StatusBadge status={inv.payment_status} className="text-[10px] px-1.5 py-0" />
                    </div>
                  </div>
                  {inv.value_ron && inv.currency !== 'RON' && (
                    <div className="text-xs text-muted-foreground text-right">{formatNum(inv.value_ron)} RON</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/* ── Documents popup for mobile ── */
function SupplierDocsDialog({ supId, supName, open, onClose }: { supId: number; supName: string; open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['supplier-documents', supId],
    queryFn: () => dmsApi.getSupplierDocuments(supId, 50),
    enabled: open,
  })
  const docs = data?.documents || []

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base">Documents — {supName}</DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto -mx-6 px-6">
          {isLoading ? (
            <p className="text-sm text-muted-foreground py-4">Loading...</p>
          ) : docs.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">No documents linked.</p>
          ) : (
            <div className="space-y-2">
              {docs.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  className="w-full text-left rounded-lg border px-3 py-2 text-sm space-y-0.5 active:bg-accent/50 transition-colors"
                  onClick={() => { onClose(); navigate(`/app/dms/documents/${doc.id}`) }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium truncate">
                      {doc.parent_id && <span className="text-muted-foreground mr-1">↳</span>}
                      {doc.title}
                    </span>
                    <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{doc.doc_date || '—'}</span>
                    <div className="flex gap-1">
                      {doc.category_name && <Badge variant="outline" className="text-[10px] px-1.5 py-0">{doc.category_name}</Badge>}
                      <StatusBadge status={doc.status} className="text-[10px] px-1.5 py-0" />
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/* ── Main component ── */
export default function SupplierManager({ companyId }: SupplierManagerProps) {
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
  const [search, setSearch] = useState('')
  const [editSup, setEditSup] = useState<DmsSupplier | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteSupId, setDeleteSupId] = useState<number | null>(null)
  const [form, setForm] = useState<Partial<DmsSupplier>>(EMPTY)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [selectMode, setSelectMode] = useState(false)
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [invoicesSup, setInvoicesSup] = useState<{ id: number; name: string } | null>(null)
  const [docsSup, setDocsSup] = useState<{ id: number; name: string } | null>(null)
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: 'name', dir: 'asc' })

  const debouncedSearch = useDebounce(search, 300)

  const { data, isLoading } = useQuery({
    queryKey: ['dms-suppliers', companyId, debouncedSearch],
    queryFn: () => dmsApi.listSuppliers({ search: debouncedSearch || undefined, active_only: false, limit: 200 }),
  })

  const { data: allTags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => tagsApi.getTags() })

  const suppliers: DmsSupplier[] = useMemo(() => {
    const list = data?.suppliers || []
    return [...list].sort((a, b) => {
      const dir = sort.dir === 'asc' ? 1 : -1
      if (sort.key === 'name') return dir * a.name.localeCompare(b.name)
      if (sort.key === 'cui') return dir * (a.cui || '').localeCompare(b.cui || '')
      const av = (a as unknown as Record<string, number>)[sort.key] || 0
      const bv = (b as unknown as Record<string, number>)[sort.key] || 0
      return dir * (av - bv)
    })
  }, [data?.suppliers, sort])

  const mobileFields: MobileCardField<DmsSupplier>[] = useMemo(() => [
    { key: 'name', label: 'Name', isPrimary: true, render: (s) => s.name },
    { key: 'total', label: 'Total', isPrimary: true, alignRight: true, render: (s) => (s.invoice_count ?? 0) > 0 ? formatNum(s.total_ron) + ' RON' : '' },
    { key: 'type', label: 'Type', isSecondary: true, render: (s) => (
      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
        {s.supplier_type === 'company' ? <><Building2 className="h-3 w-3 mr-0.5 inline" />Company</> : <><User className="h-3 w-3 mr-0.5 inline" />Person</>}
      </Badge>
    ) },
    { key: 'cui', label: 'CUI', isSecondary: true, render: (s) => s.cui || '' },
    { key: 'active', label: 'Active', isSecondary: true, render: (s) => s.is_active ? <Check className="h-3.5 w-3.5 text-green-600 inline" /> : <X className="h-3.5 w-3.5 text-muted-foreground inline" /> },
    { key: 'docs', label: 'Linked Docs', render: (s) => (s.document_count ?? 0) > 0 ? (
      <button
        type="button"
        className="text-primary underline underline-offset-2"
        onClick={(e) => { e.stopPropagation(); setDocsSup({ id: s.id, name: s.name }) }}
      >
        {s.document_count}
      </button>
    ) : '—' },
    { key: 'invoices', label: 'Invoices', render: (s) => (s.invoice_count ?? 0) > 0 ? (
      <button
        type="button"
        className="text-primary underline underline-offset-2"
        onClick={(e) => { e.stopPropagation(); setInvoicesSup({ id: s.id, name: s.name }) }}
      >
        {s.invoice_count}
      </button>
    ) : '—' },
    { key: 'city', label: 'City', expandOnly: true, render: (s) => s.city || '—' },
    { key: 'county', label: 'County', expandOnly: true, render: (s) => s.county || '—' },
    { key: 'email', label: 'Email', expandOnly: true, render: (s) => s.email || '—' },
    { key: 'phone', label: 'Phone', expandOnly: true, render: (s) => s.phone || '—' },
  ], [])

  const resetForm = () => setForm({ ...EMPTY })
  const setField = (key: keyof DmsSupplier, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const createMutation = useMutation({
    mutationFn: (d: Partial<DmsSupplier>) => dmsApi.createSupplier(d),
    onSuccess: () => { toast.success('Supplier created'); queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] }); resetForm(); setCreateOpen(false) },
    onError: () => toast.error('Failed to create supplier'),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, data: d }: { id: number; data: Partial<DmsSupplier> }) => dmsApi.updateSupplier(id, d),
    onSuccess: () => { toast.success('Supplier updated'); queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] }); setEditSup(null); resetForm() },
    onError: () => toast.error('Failed to update supplier'),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => dmsApi.deleteSupplier(id),
    onSuccess: () => { toast.success('Supplier deactivated'); queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] }); setDeleteSupId(null) },
    onError: () => toast.error('Failed to delete supplier'),
  })
  const batchDeactivateMutation = useMutation({
    mutationFn: (ids: number[]) => dmsApi.batchDeactivateSuppliers(ids),
    onSuccess: (_, ids) => { toast.success(`${ids.length} supplier(s) deactivated`); queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] }); setSelected(new Set()); setBatchDeleteOpen(false) },
    onError: () => toast.error('Batch deactivate failed'),
  })
  const anafBatchMutation = useMutation({
    mutationFn: () => dmsApi.syncAnafBatch(),
    onSuccess: (res) => {
      if (res.synced > 0) {
        toast.success(`ANAF sync: ${res.synced} of ${res.total} suppliers updated`)
      } else {
        toast.info(`All ${res.total} suppliers already up to date`)
      }
      queryClient.invalidateQueries({ queryKey: ['dms-suppliers'] })
    },
    onError: () => toast.error('ANAF batch sync failed'),
  })

  const openEdit = (sup: DmsSupplier) => {
    setEditSup(sup)
    setForm({ name: sup.name, supplier_type: sup.supplier_type, cui: sup.cui || '', j_number: sup.j_number || '', nr_reg_com: sup.nr_reg_com || '', address: sup.address || '', city: sup.city || '', county: sup.county || '', bank_account: sup.bank_account || '', iban: sup.iban || '', bank_name: sup.bank_name || '', phone: sup.phone || '', email: sup.email || '', contact_name: sup.contact_name || '', contact_function: sup.contact_function || '', contact_email: sup.contact_email || '', contact_phone: sup.contact_phone || '', owner_name: sup.owner_name || '', owner_function: sup.owner_function || '', owner_email: sup.owner_email || '', owner_phone: sup.owner_phone || '' })
  }

  const handleSave = () => {
    const payload: Record<string, unknown> = {
      name: (form.name || '').trim(), supplier_type: form.supplier_type || 'company',
      cui: (form.cui || '').trim() || null, j_number: (form.j_number || '').trim() || null,
      nr_reg_com: (form.nr_reg_com || '').trim() || null, address: (form.address || '').trim() || null,
      city: (form.city || '').trim() || null, county: (form.county || '').trim() || null,
      bank_account: (form.bank_account || '').trim() || null, iban: (form.iban || '').trim() || null,
      bank_name: (form.bank_name || '').trim() || null, phone: (form.phone || '').trim() || null,
      email: (form.email || '').trim() || null,
      contact_name: (form.contact_name || '').trim() || null, contact_function: (form.contact_function || '').trim() || null,
      contact_email: (form.contact_email || '').trim() || null, contact_phone: (form.contact_phone || '').trim() || null,
      owner_name: (form.owner_name || '').trim() || null, owner_function: (form.owner_function || '').trim() || null,
      owner_email: (form.owner_email || '').trim() || null, owner_phone: (form.owner_phone || '').trim() || null,
    }
    if (editSup) updateMutation.mutate({ id: editSup.id, data: payload })
    else createMutation.mutate(payload)
  }

  const toggleSelect = (id: number) => setSelected((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const toggleAll = () => setSelected(selected.size === suppliers.length ? new Set() : new Set(suppliers.map((s) => s.id)))

  const handleSort = (key: SortKey) => {
    setSort((prev) => prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' })
  }

  const handleBatchTag = (tagId: number, action: 'add' | 'remove') => {
    tagsApi.bulkEntityTags('supplier', [...selected], tagId, action).then((res) => {
      toast.success(`${action === 'add' ? 'Added' : 'Removed'} tag on ${res.count} supplier(s)`)
      queryClient.invalidateQueries({ queryKey: ['entity-tags'] })
    })
  }

  const SortIcon = ({ col }: { col: SortKey }) => sort.key === col
    ? sort.dir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
    : <ArrowUpDown className="h-3 w-3 opacity-30" />

  const formDialog = createOpen || editSup

  return (
    <div className="space-y-4 md:space-y-6">
      <PageHeader
        title="Suppliers"
        breadcrumbs={[
          { label: 'Documents', shortLabel: 'Docs.', href: '/app/dms' },
          { label: 'Suppliers' },
        ]}
        actions={
          <div className="flex items-center gap-1.5">
            {isMobile && (
              <Button
                variant={selectMode ? 'secondary' : 'outline'}
                size="icon"
                onClick={() => { setSelectMode((p) => !p); if (selectMode) setSelected(new Set()) }}
              >
                {selectMode ? <X className="h-4 w-4" /> : <CheckSquare className="h-4 w-4" />}
              </Button>
            )}
            <Button
              variant="outline"
              size="icon"
              className="md:size-auto md:px-3"
              onClick={() => anafBatchMutation.mutate()}
              disabled={anafBatchMutation.isPending}
              title="Sync all suppliers with CUI from ANAF"
            >
              <RefreshCw className={`h-4 w-4 md:mr-1 ${anafBatchMutation.isPending ? 'animate-spin' : ''}`} />
              <span className="hidden md:inline">Sync ANAF</span>
            </Button>
            <Button size="icon" className="md:size-auto md:px-3" onClick={() => { resetForm(); setCreateOpen(true) }}>
              <Plus className="h-4 w-4 md:mr-1" />
              <span className="hidden md:inline">New Supplier</span>
            </Button>
          </div>
        }
      />

      {/* Search + Batch actions */}
      <div className="flex items-center gap-2 flex-wrap">
        {selected.size > 0 && (
          <>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm"><Tags className="h-3.5 w-3.5 mr-1" />Tag ({selected.size})</Button>
              </PopoverTrigger>
              <PopoverContent className="w-[180px] p-1" align="end">
                {(allTags as Tag[]).map((t) => (
                  <button
                    key={t.id}
                    className="w-full text-left text-sm px-2 py-1 rounded hover:bg-accent flex items-center gap-1.5"
                    onClick={() => handleBatchTag(t.id, 'add')}
                  >
                    <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: t.color || '#6c757d' }} />
                    {t.name}
                  </button>
                ))}
              </PopoverContent>
            </Popover>
            <Button variant="destructive" size="sm" onClick={() => setBatchDeleteOpen(true)}>
              <Trash2 className="h-4 w-4 mr-1" />Deactivate ({selected.size})
            </Button>
          </>
        )}
        <div className="relative flex-1 md:flex-none">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search suppliers..." className="pl-8 md:w-[220px] h-9" />
        </div>
      </div>

      {/* List */}
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading suppliers...</p>
      ) : suppliers.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">
          {search ? 'No suppliers match your search.' : 'No suppliers yet. Add your first supplier.'}
        </p>
      ) : isMobile ? (
        <MobileCardList
          data={suppliers}
          fields={mobileFields}
          getRowId={(s) => s.id}
          selectable={selectMode}
          selectedIds={selected}
          onToggleSelect={toggleSelect}
          actions={(sup) => (
            <>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(sup)} title="Edit">
                <Edit2 className="h-3.5 w-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => setDeleteSupId(sup.id)} title="Delete">
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
        />
      ) : (
        <div className="rounded-md border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[36px]">
                  <Checkbox checked={selected.size === suppliers.length && suppliers.length > 0} onCheckedChange={toggleAll} />
                </TableHead>
                <TableHead className="w-[28px]" />
                <TableHead>
                  <span className="flex items-center gap-1 cursor-pointer select-none" onClick={() => handleSort('name')}>
                    Name <SortIcon col="name" />
                  </span>
                </TableHead>
                <TableHead>Type</TableHead>
                <TableHead>
                  <span className="flex items-center gap-1 cursor-pointer select-none" onClick={() => handleSort('cui')}>
                    CUI <SortIcon col="cui" />
                  </span>
                </TableHead>
                <TableHead>Tags</TableHead>
                <TableHead>
                  <span className="flex items-center gap-1 cursor-pointer select-none" onClick={() => handleSort('document_count')}>
                    Linked Docs <SortIcon col="document_count" />
                  </span>
                </TableHead>
                <TableHead className="text-right">
                  <span className="flex items-center gap-1 justify-end cursor-pointer select-none" onClick={() => handleSort('total_ron')}>
                    Invoiced (RON) <SortIcon col="total_ron" />
                  </span>
                </TableHead>
                <TableHead className="text-center">Active</TableHead>
                <TableHead className="w-[80px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppliers.map((sup) => {
                const docs = sup.linked_documents || []
                const isExpanded = expandedId === sup.id
                const toggleExpand = () => setExpandedId(isExpanded ? null : sup.id)
                return (
                  <Fragment key={sup.id}>
                    <TableRow
                      className={`cursor-pointer hover:bg-muted/40 ${selected.has(sup.id) ? 'bg-muted/50' : ''}`}
                      onClick={toggleExpand}
                      aria-expanded={isExpanded}
                    >
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Checkbox checked={selected.has(sup.id)} onCheckedChange={() => toggleSelect(sup.id)} />
                      </TableCell>
                      <TableCell className="px-0">
                        {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      </TableCell>
                      <TableCell className="font-medium">
                        <Link
                          to={`/app/dms/suppliers/${sup.id}`}
                          className="hover:underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {sup.name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          {sup.supplier_type === 'company' ? <><Building2 className="h-3 w-3 mr-1 inline" />Company</> : <><User className="h-3 w-3 mr-1 inline" />Person</>}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{sup.cui || '—'}</TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}><SupplierTagCell supId={sup.id} /></TableCell>
                      <TableCell>
                        {docs.length === 0 ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                            <FileText className="h-3 w-3 mr-0.5 inline" />{docs.length}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right text-sm tabular-nums">
                        {(sup.invoice_count ?? 0) > 0 ? (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span className="cursor-default">{formatNum(sup.total_ron)}</span>
                              </TooltipTrigger>
                              <TooltipContent>{sup.invoice_count} invoice(s) &middot; {formatNum(sup.total_eur)} EUR</TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {sup.is_active ? <Check className="h-4 w-4 text-green-600 mx-auto" /> : <X className="h-4 w-4 text-muted-foreground mx-auto" />}
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
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
                    {isExpanded && (
                      <TableRow className="bg-muted/30">
                        <TableCell colSpan={10} className="p-0">
                          <SupplierExpandedDetail supId={sup.id} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={!!formDialog} onOpenChange={(open) => { if (!open) { setCreateOpen(false); setEditSup(null); resetForm() } }}>
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
              <div className="space-y-1.5"><Label>CUI / CIF</Label><Input value={form.cui || ''} onChange={(e) => setField('cui', e.target.value)} placeholder="Tax ID" /></div>
              <div className="space-y-1.5"><Label>Nr. Reg. Com.</Label><Input value={form.nr_reg_com || ''} onChange={(e) => setField('nr_reg_com', e.target.value)} placeholder="J00/000/0000" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>J Number</Label><Input value={form.j_number || ''} onChange={(e) => setField('j_number', e.target.value)} placeholder="Trade registry" /></div>
              <div className="space-y-1.5"><Label>Phone</Label><Input value={form.phone || ''} onChange={(e) => setField('phone', e.target.value)} placeholder="Phone number" /></div>
            </div>
            <div className="space-y-1.5"><Label>Address</Label><Input value={form.address || ''} onChange={(e) => setField('address', e.target.value)} placeholder="Street address" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>City</Label><Input value={form.city || ''} onChange={(e) => setField('city', e.target.value)} placeholder="City" /></div>
              <div className="space-y-1.5"><Label>County</Label><Input value={form.county || ''} onChange={(e) => setField('county', e.target.value)} placeholder="County" /></div>
            </div>
            <div className="space-y-1.5"><Label>Email</Label><Input value={form.email || ''} onChange={(e) => setField('email', e.target.value)} placeholder="Email address" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Bank Name</Label><Input value={form.bank_name || ''} onChange={(e) => setField('bank_name', e.target.value)} placeholder="Bank name" /></div>
              <div className="space-y-1.5"><Label>IBAN</Label><Input value={form.iban || ''} onChange={(e) => setField('iban', e.target.value)} placeholder="IBAN" /></div>
            </div>
            <div className="pt-2 border-t">
              <p className="text-xs font-medium text-muted-foreground mb-2">Contact Person</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Name</Label><Input value={form.contact_name || ''} onChange={(e) => setField('contact_name', e.target.value)} placeholder="Contact name" /></div>
                <div className="space-y-1.5"><Label>Function</Label><Input value={form.contact_function || ''} onChange={(e) => setField('contact_function', e.target.value)} placeholder="Role / title" /></div>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-2">
                <div className="space-y-1.5"><Label>Email</Label><Input value={form.contact_email || ''} onChange={(e) => setField('contact_email', e.target.value)} placeholder="Contact email" /></div>
                <div className="space-y-1.5"><Label>Phone</Label><Input value={form.contact_phone || ''} onChange={(e) => setField('contact_phone', e.target.value)} placeholder="Contact phone" /></div>
              </div>
            </div>
            <div className="pt-2 border-t">
              <p className="text-xs font-medium text-muted-foreground mb-2">Owner</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Name</Label><Input value={form.owner_name || ''} onChange={(e) => setField('owner_name', e.target.value)} placeholder="Owner name" /></div>
                <div className="space-y-1.5"><Label>Function</Label><Input value={form.owner_function || ''} onChange={(e) => setField('owner_function', e.target.value)} placeholder="Role / title" /></div>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-2">
                <div className="space-y-1.5"><Label>Email</Label><Input value={form.owner_email || ''} onChange={(e) => setField('owner_email', e.target.value)} placeholder="Owner email" /></div>
                <div className="space-y-1.5"><Label>Phone</Label><Input value={form.owner_phone || ''} onChange={(e) => setField('owner_phone', e.target.value)} placeholder="Owner phone" /></div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreateOpen(false); setEditSup(null); resetForm() }}>Cancel</Button>
            <Button onClick={handleSave} disabled={!(form.name || '').trim() || createMutation.isPending || updateMutation.isPending}>
              {editSup ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={deleteSupId !== null} onOpenChange={(open) => !open && setDeleteSupId(null)}
        title="Deactivate Supplier" description="This will deactivate the supplier. They won't appear in search results anymore."
        confirmLabel="Deactivate" variant="destructive" onConfirm={() => deleteSupId && deleteMutation.mutate(deleteSupId)} />

      <ConfirmDialog open={batchDeleteOpen} onOpenChange={(open) => !open && setBatchDeleteOpen(false)}
        title={`Deactivate ${selected.size} Supplier(s)`}
        description={`This will deactivate ${selected.size} selected supplier(s). They won't appear in search results anymore.`}
        confirmLabel="Deactivate All" variant="destructive" onConfirm={() => batchDeactivateMutation.mutate([...selected])} />

      {invoicesSup && (
        <SupplierInvoicesDialog
          supId={invoicesSup.id}
          supName={invoicesSup.name}
          open
          onClose={() => setInvoicesSup(null)}
        />
      )}
      {docsSup && (
        <SupplierDocsDialog
          supId={docsSup.id}
          supName={docsSup.name}
          open
          onClose={() => setDocsSup(null)}
        />
      )}
    </div>
  )
}
