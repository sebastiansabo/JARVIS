import { Fragment, useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Pencil, ChevronDown, ChevronRight, Download, RotateCcw, RefreshCw, Trash2, Check } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { AccountingTenantSelector } from '@/components/shared/AccountingTenantSelector'
import { useAccountingStore } from '@/stores/accountingStore'
import { DateField } from '@/components/ui/date-field'
import { PageHeader } from '@/components/shared/PageHeader'
import { CurrencyDisplay } from '@/components/shared/CurrencyDisplay'
import { organizationApi } from '@/api/organization'
import { suppliersApi, type MasterSupplier, type BudgetedInvoice, type KontoConfig, type KontoPreset, type EfacturaPartner } from '@/api/suppliers'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import type { CompanyWithBrands } from '@/types/organization'

/* ── worklist grouped by supplier ── */
interface SupplierGroup {
  supplierId: number
  supplierName: string
  invoices: BudgetedInvoice[]
}

/* ── period preset control (mirrors FoiParcurs/ReportsTab's Seg + rangeForPreset) ── */
type PeriodPreset = 'month' | '30d' | 'year' | 'custom'

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function rangeForPreset(preset: PeriodPreset, from: string, to: string): { from: string; to: string } {
  const now = new Date()
  if (preset === 'month') return { from: ymd(new Date(now.getFullYear(), now.getMonth(), 1)), to: ymd(now) }
  if (preset === 'year') return { from: ymd(new Date(now.getFullYear(), 0, 1)), to: ymd(now) }
  if (preset === 'custom') return { from, to }
  return { from: ymd(new Date(now.getTime() - 29 * 864e5)), to: ymd(now) } // 30d default
}

function Seg<T extends string>({ value, onChange, options }: {
  value: T; onChange: (v: T) => void; options: readonly (readonly [T, string])[]
}) {
  return (
    <div className="inline-flex gap-0.5 rounded-lg border bg-muted/50 p-0.5">
      {options.map(([v, label]) => (
        <button key={v} type="button" onClick={() => onChange(v)}
          className={cn('rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
            value === v ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}>
          {label}
        </button>
      ))}
    </div>
  )
}

// EuroFib konto editor — Debit/Credit column layout (pattern: MEDLINE EuroFib file)
const DEBIT_FIELDS: { key: keyof KontoConfig; label: string }[] = [
  { key: 'konto_debit', label: 'Konto Debit' },
  { key: 'gegenkonto_debit', label: 'Gegenkonto Debit' },
  { key: 'kostenstelle_debit', label: 'Kostenstelle Debit' },
  { key: 'extbeleg_debit', label: 'Extbeleg Debit' },
]
const CREDIT_FIELDS: { key: keyof KontoConfig; label: string }[] = [
  { key: 'konto_credit', label: 'Konto Credit' },
  { key: 'gegenkonto_credit', label: 'Gegenkonto Credit' },
  { key: 'kostenstelle_credit', label: 'Kostenstelle Credit' },
  { key: 'extbeleg_credit', label: 'Extbeleg Credit' },
]
const GENERAL_FIELDS: { key: keyof KontoConfig; label: string }[] = [
  { key: 'klient', label: 'Klient' },
  { key: 'steuercode', label: 'Steuercode' },
  { key: 'text_template', label: 'Text Template' },
  { key: 'belegart', label: 'Belegart' },
]
const EMPTY_KONTO: KontoConfig = {
  konto_debit: null, konto_credit: null, klient: null,
  gegenkonto_debit: null, gegenkonto_credit: null,
  kostenstelle_debit: null, kostenstelle_credit: null,
  extbeleg_debit: null, extbeleg_credit: null,
  steuercode: null, text_template: null, belegart: null,
}

/** Debit/Credit + General EuroFib field grid, shared by the konto editor and the Add-supplier dialog. */
function KontoFieldsGrid({
  form,
  onChange,
  disabled,
}: {
  form: KontoConfig
  onChange: (key: keyof KontoConfig, value: string) => void
  disabled?: boolean
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Debit (Soll)</div>
          {DEBIT_FIELDS.map((f) => (
            <div key={f.key}>
              <Label className="text-xs">{f.label}</Label>
              <Input
                className="h-8 text-sm font-mono"
                disabled={disabled}
                value={form[f.key] ?? ''}
                onChange={(e) => onChange(f.key, e.target.value)}
              />
            </div>
          ))}
        </div>
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Credit (Haben)</div>
          {CREDIT_FIELDS.map((f) => (
            <div key={f.key}>
              <Label className="text-xs">{f.label}</Label>
              <Input
                className="h-8 text-sm font-mono"
                disabled={disabled}
                value={form[f.key] ?? ''}
                onChange={(e) => onChange(f.key, e.target.value)}
              />
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">General</div>
        <div className="grid grid-cols-2 gap-3">
          {GENERAL_FIELDS.map((f) => (
            <div key={f.key}>
              <Label className="text-xs">{f.label}</Label>
              <Input
                className="h-8 text-sm font-mono"
                disabled={disabled}
                value={form[f.key] ?? ''}
                onChange={(e) => onChange(f.key, e.target.value)}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/** "Replicate to all group companies" checkbox row, shared by the Add dialog and the konto editor. */
function ReplicateAllCheckbox({
  checked,
  onCheckedChange,
  id,
}: {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  id: string
}) {
  return (
    <div className="flex items-start gap-2 border-t pt-3">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(v) => onCheckedChange(v === true)}
        className="mt-0.5"
      />
      <div className="grid gap-0.5 leading-none">
        <Label htmlFor={id} className="cursor-pointer text-sm font-normal">
          Aplică pentru toate companiile din grup
        </Label>
        <p className="text-xs text-muted-foreground">
          Salvează aceeași configurație EuroFib pentru toate companiile
        </p>
      </div>
    </div>
  )
}

function companyLabel(c: CompanyWithBrands): string {
  return `${c.company} · ${c.vat || '—'}`
}

/** Per-invoice EuroFib schema picker in the worklist: shows the effective preset (active or a
 * pinned override) and lets the user pin a different one, or revert to the supplier's active
 * preset. Presets are fetched per (supplier, company) and cached, so all rows of one supplier
 * share a single query. Read-only in the processed view. */
function InvoicePresetPicker({
  inv, companyId, disabled,
}: {
  inv: BudgetedInvoice
  companyId: number
  disabled?: boolean
}) {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ['supplier-presets', inv.supplier_id, companyId],
    queryFn: () => suppliersApi.listPresets(inv.supplier_id, companyId),
    enabled: !disabled,
  })
  const presets = data?.presets ?? []
  const setMut = useMutation({
    mutationFn: (kontoConfigId: number | null) =>
      suppliersApi.setInvoicePreset(inv.id, { konto_config_id: kontoConfigId, supplier_id: inv.supplier_id, company_id: companyId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['supplier-worklist-invoices'] }),
    onError: () => toast.error('Nu s-a putut seta schema'),
  })

  const label = inv.konto_name ?? 'Implicit'
  if (disabled) return <span className="text-xs text-muted-foreground">{label}</span>

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1 text-xs font-normal" disabled={setMut.isPending}>
          {inv.konto_overridden && <span className="h-1.5 w-1.5 rounded-full bg-primary" title="Schemă suprascrisă" />}
          <span className="max-w-[120px] truncate">{label}</span>
          <ChevronDown className="h-3 w-3 opacity-60" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {presets.map((p) => (
          <DropdownMenuItem key={p.id} onClick={() => setMut.mutate(p.id)}>
            <Check className={cn('mr-1.5 h-3.5 w-3.5', p.id === inv.konto_config_id ? 'opacity-100' : 'opacity-0')} />
            {p.name}{p.is_active ? ' · activă' : ''}
          </DropdownMenuItem>
        ))}
        {inv.konto_overridden && (
          <DropdownMenuItem onClick={() => setMut.mutate(null)} className="text-muted-foreground">
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Revino la schema activă
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default function Procesare() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<'worklist' | 'master'>('worklist')
  const [search, setSearch] = useState('')

  // Company gating — the acting company comes from the shared accounting tenant switcher
  // (accountingStore, persisted across accounting pages). null = "Toate companiile"; Procesare
  // is per-company (konto + export), so it prompts to pick one when none is selected.
  const companyId = useAccountingStore((s) => s.selectedCompanyId)

  const { data: companiesData } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
    staleTime: 10 * 60_000,
  })
  const companies = companiesData || []
  const selectedCompany = companies.find((c) => c.id === companyId) || null

  // Worklist period filter — presets mirror FoiParcurs/ReportsTab; 'custom' uses DateField range.
  const [preset, setPreset] = useState<PeriodPreset>('30d')
  const [customFrom, setCustomFrom] = useState<string>(ymd(new Date(Date.now() - 29 * 864e5)))
  const [customTo, setCustomTo] = useState<string>(ymd(new Date()))
  const { from: startDate, to: endDate } = rangeForPreset(preset, customFrom, customTo)

  // Worklist "Importate" toggle — 'bugetata' (default) shows the actionable worklist,
  // 'procesate' shows a read-only history of EuroFib-exported invoices (status='Importat').
  const [worklistView, setWorklistView] = useState<'bugetata' | 'procesate'>('bugetata')
  const isProcessedView = worklistView === 'procesate'

  const bugetataQ = useQuery({
    queryKey: ['supplier-worklist-invoices', companyId, startDate, endDate, 'bugetata'],
    queryFn: () => suppliersApi.fetchInvoices(companyId as number, startDate, endDate, undefined),
    enabled: !!companyId,
  })
  const procesateQ = useQuery({
    queryKey: ['supplier-worklist-invoices', companyId, startDate, endDate, 'procesate'],
    queryFn: () => suppliersApi.fetchInvoices(companyId as number, startDate, endDate, 'Importat'),
    enabled: !!companyId,
  })
  const invoicesData = isProcessedView ? procesateQ.data : bugetataQ.data
  const invoicesLoading = isProcessedView ? procesateQ.isLoading : bugetataQ.isLoading
  const bugetataCount = bugetataQ.data?.invoices.length ?? 0
  const procesateCount = procesateQ.data?.invoices.length ?? 0
  // Furnizori tab shows active suppliers by default, or the soft-deleted ones ('Șterse').
  const [masterView, setMasterView] = useState<'active' | 'deleted'>('active')
  const { data: masters, isLoading: mastersLoading } = useQuery({
    queryKey: ['supplier-master', companyId, search, masterView],
    queryFn: () => suppliersApi.list(companyId as number, search || undefined, { deleted: masterView === 'deleted' }),
    enabled: !!companyId,
  })

  // ── Worklist grouped by supplier ──
  const supplierGroups = useMemo<SupplierGroup[]>(() => {
    const byId = new Map<number, SupplierGroup>()
    for (const inv of invoicesData?.invoices ?? []) {
      let group = byId.get(inv.supplier_id)
      if (!group) {
        group = { supplierId: inv.supplier_id, supplierName: inv.supplier, invoices: [] }
        byId.set(inv.supplier_id, group)
      }
      group.invoices.push(inv)
    }
    return Array.from(byId.values()).sort((a, b) => a.supplierName.localeCompare(b.supplierName))
  }, [invoicesData])

  const [expandedSuppliers, setExpandedSuppliers] = useState<Set<number>>(new Set())
  const toggleSupplier = (supplierId: number) =>
    setExpandedSuppliers((prev) => {
      const next = new Set(prev)
      if (next.has(supplierId)) next.delete(supplierId)
      else next.add(supplierId)
      return next
    })

  const [selectedInvoiceIds, setSelectedInvoiceIds] = useState<Set<number>>(new Set())
  // Selection is period/company/view scoped — drop stale picks when any changes.
  useEffect(() => { setSelectedInvoiceIds(new Set()) }, [companyId, startDate, endDate, worklistView])

  const toggleInvoiceSelected = (invoiceId: number) =>
    setSelectedInvoiceIds((prev) => {
      const next = new Set(prev)
      if (next.has(invoiceId)) next.delete(invoiceId)
      else next.add(invoiceId)
      return next
    })

  const groupSelectionState = (group: SupplierGroup): boolean | 'indeterminate' => {
    const selectedCount = group.invoices.filter((inv) => selectedInvoiceIds.has(inv.id)).length
    if (selectedCount === 0) return false
    return selectedCount === group.invoices.length ? true : 'indeterminate'
  }

  const toggleGroupSelected = (group: SupplierGroup) => {
    const allSelected = group.invoices.every((inv) => selectedInvoiceIds.has(inv.id))
    setSelectedInvoiceIds((prev) => {
      const next = new Set(prev)
      for (const inv of group.invoices) {
        if (allSelected) next.delete(inv.id)
        else next.add(inv.id)
      }
      return next
    })
  }

  // General export scope: checked rows across all suppliers, or everything shown if none checked.
  const shownInvoiceIds = useMemo(
    () => supplierGroups.flatMap((g) => g.invoices.map((inv) => inv.id)),
    [supplierGroups],
  )
  const selectedShownCount = shownInvoiceIds.filter((id) => selectedInvoiceIds.has(id)).length
  const exportCount = selectedShownCount > 0 ? selectedShownCount : shownInvoiceIds.length

  const exportSupplierMut = useMutation({
    mutationFn: async (group: SupplierGroup) => {
      if (companyId === null) throw new Error('Nicio companie selectată')
      const selectedInGroup = group.invoices.filter((inv) => selectedInvoiceIds.has(inv.id)).map((inv) => inv.id)
      const invoiceIds = selectedInGroup.length > 0 ? selectedInGroup : group.invoices.map((inv) => inv.id)
      await suppliersApi.exportCsv(companyId, startDate, endDate, invoiceIds)
    },
    onSuccess: (_res, group) => {
      // Exported invoices flip Bugetata → Importat server-side — refresh the worklist so they drop off.
      qc.invalidateQueries({ queryKey: ['supplier-worklist-invoices'] })
      setWorklistView('procesate')
      toast.success(`Exportat — facturile au fost marcate procesate (${group.supplierName})`)
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'Exportul a eșuat'),
  })

  const unprocessMut = useMutation({
    mutationFn: async (group: SupplierGroup) => {
      await suppliersApi.unprocess(group.invoices.map((inv) => inv.id))
    },
    onSuccess: (_res, group) => {
      qc.invalidateQueries({ queryKey: ['supplier-worklist-invoices'] })
      setWorklistView('bugetata')
      toast.success(`Readuse în lucru (${group.supplierName})`)
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'Acțiunea a eșuat'),
  })

  // General export: a single CSV/XLSX of the checked invoices across all suppliers, or all shown
  // invoices when none are checked.
  const exportGeneralMut = useMutation({
    mutationFn: async (format: 'csv' | 'xlsx') => {
      if (companyId === null) throw new Error('Nicio companie selectată')
      const selected = shownInvoiceIds.filter((id) => selectedInvoiceIds.has(id))
      const invoiceIds = selected.length > 0 ? selected : shownInvoiceIds
      await suppliersApi.exportCsv(companyId, startDate, endDate, invoiceIds, format)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['supplier-worklist-invoices'] })
      setWorklistView('procesate')
      toast.success('Exportat — facturile au fost marcate procesate')
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : 'Exportul a eșuat'),
  })

  // ── Add supplier dialog ──
  const [addOpen, setAddOpen] = useState(false)
  const [syncOpen, setSyncOpen] = useState(false)
  const [addForm, setAddForm] = useState({ name: '', cui: '', nr_reg_com: '', ref_no: '' })
  const [addKonto, setAddKonto] = useState<KontoConfig>(EMPTY_KONTO)
  const [addReplicateAll, setAddReplicateAll] = useState(false)
  const setAddKontoField = (key: keyof KontoConfig, value: string) =>
    setAddKonto((prev) => ({ ...prev, [key]: value || null }))

  const createMut = useMutation({
    mutationFn: async () => {
      if (companyId === null) throw new Error('No company selected')
      const res = await suppliersApi.create({
        name: addForm.name.trim(),
        cui: addForm.cui.trim() || null,
        nr_reg_com: addForm.nr_reg_com.trim() || null,
        ref_no: addForm.ref_no.trim() || null,
      })
      let replicated: number | undefined
      if (res.id) {
        const kontoRes = await suppliersApi.updateKonto(res.id, companyId, addKonto, addReplicateAll)
        replicated = kontoRes.replicated
      }
      return { ...res, replicated }
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['supplier-master'] })
      toast.success(
        res.replicated
          ? `Furnizor adăugat — configurație salvată pentru ${res.replicated} companii`
          : 'Furnizor adăugat')
      setAddOpen(false)
      setAddForm({ name: '', cui: '', nr_reg_com: '', ref_no: '' })
      setAddKonto(EMPTY_KONTO)
      setAddReplicateAll(false)
    },
    onError: () => toast.error('Nu s-a putut adăuga furnizorul'),
  })

  // ── Per-company konto editor ──
  const [editorSupplier, setEditorSupplier] = useState<MasterSupplier | null>(null)
  const openEditor = (s: MasterSupplier) => setEditorSupplier(s)

  // ── Delete / restore Furnizori (soft delete, gated on backend, recorded in audit log) ──
  const [deleteSup, setDeleteSup] = useState<MasterSupplier | null>(null)
  const deleteSupMut = useMutation({
    mutationFn: (id: number) => suppliersApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['supplier-master'] })
      qc.invalidateQueries({ queryKey: ['supplier-worklist-invoices'] })
      setDeleteSup(null)
      toast.success('Furnizor șters')
    },
    onError: () => toast.error('Nu s-a putut șterge furnizorul'),
  })
  const restoreSupMut = useMutation({
    mutationFn: (id: number) => suppliersApi.restore(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['supplier-master'] })
      qc.invalidateQueries({ queryKey: ['supplier-worklist-invoices'] })
      toast.success('Furnizor restaurat')
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : 'Nu s-a putut restaura furnizorul'),
  })

  return (
    <div className="space-y-4">
      <PageHeader
        title="Procesare Furnizori"
        breadcrumbs={[{ label: 'Accounting' }, { label: 'Procesare' }]}
        actions={
          <>
            <AccountingTenantSelector className="w-64" />
            <Input
              placeholder="Search suppliers…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-56"
            />
            <Button
              variant="outline"
              onClick={() => setSyncOpen(true)}
              title="Importă furnizori din e-Factura"
              disabled={companyId === null}
            >
              <RefreshCw className="mr-2 h-4 w-4" /> Sync e-Factura
            </Button>
            <Button size="icon" onClick={() => setAddOpen(true)} title="Adaugă furnizor" disabled={companyId === null}>
              <Plus className="h-4 w-4" />
            </Button>
          </>
        }
      />
      {companyId === null ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Selectează o companie pentru a vedea furnizorii și worklist-ul.</div>
      ) : (
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TabsList>
            <TabsTrigger value="worklist">Worklist ({invoicesData?.invoices.length ?? 0})</TabsTrigger>
            <TabsTrigger value="master">Furnizori</TabsTrigger>
          </TabsList>
          {tab === 'worklist' && (
            <div className="flex flex-wrap items-center gap-2">
              <Seg value={worklistView} onChange={setWorklistView} options={[['bugetata', `In lucru (${bugetataCount})`], ['procesate', `Importate (${procesateCount})`]] as const} />
              <Seg value={preset} onChange={setPreset} options={[['month', 'Luna curentă'], ['30d', 'Ultimele 30 zile'], ['year', 'Anul curent'], ['custom', 'Interval']] as const} />
              {preset === 'custom' && (
                <DateField
                  mode="range"
                  startDate={customFrom}
                  endDate={customTo}
                  onRangeChange={(start, end) => { setCustomFrom(start); setCustomTo(end) }}
                />
              )}
              {!isProcessedView && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      size="sm"
                      variant="outline"
                      className="ml-auto h-8 gap-1"
                      title={selectedShownCount > 0 ? `Export selecție (${exportCount})` : 'Export toate'}
                      disabled={exportGeneralMut.isPending || shownInvoiceIds.length === 0}
                    >
                      <Download className="h-4 w-4" />
                      <span className="text-xs">
                        {selectedShownCount > 0 ? `Export selecție (${exportCount})` : 'Export toate'}
                      </span>
                      <ChevronDown className="h-3 w-3 opacity-60" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => exportGeneralMut.mutate('csv')}>CSV</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => exportGeneralMut.mutate('xlsx')}>Excel (XLSX)</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          )}
          {tab === 'master' && (
            <Seg value={masterView} onChange={setMasterView} options={[['active', 'Active'], ['deleted', 'Șterse']] as const} />
          )}
        </div>

        <TabsContent value="worklist" className="mt-3">
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow>
                <TableHead className="w-8" />
                <TableHead>Furnizor / Nr. factură</TableHead><TableHead>Data</TableHead>
                <TableHead className="text-right">Net</TableHead><TableHead className="text-right">Total</TableHead>
                <TableHead>Monedă</TableHead><TableHead>Schemă</TableHead><TableHead className="text-right">Acțiuni</TableHead></TableRow></TableHeader>
              <TableBody>
                {supplierGroups.map((group) => {
                  const isExpanded = expandedSuppliers.has(group.supplierId)
                  return (
                    <Fragment key={group.supplierId}>
                      <TableRow
                        className="cursor-pointer bg-muted/30 hover:bg-muted/50"
                        onClick={() => toggleSupplier(group.supplierId)}
                      >
                        <TableCell>
                          {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                        </TableCell>
                        <TableCell colSpan={4}>
                          <div className="flex items-center gap-2">
                            {!isProcessedView && (
                              <Checkbox
                                checked={groupSelectionState(group)}
                                onCheckedChange={() => toggleGroupSelected(group)}
                                onClick={(e) => e.stopPropagation()}
                              />
                            )}
                            <span className="font-medium">{group.supplierName}</span>
                            <Badge variant="secondary" className="font-normal">{group.invoices.length} facturi</Badge>
                          </div>
                        </TableCell>
                        <TableCell colSpan={2} />
                        <TableCell className="text-right">
                          {!isProcessedView && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={(e) => { e.stopPropagation(); exportSupplierMut.mutate(group) }}
                              disabled={exportSupplierMut.isPending}
                            >
                              <Download className="mr-1.5 h-3.5 w-3.5" />
                              Export CSV
                            </Button>
                          )}
                          {isProcessedView && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={(e) => { e.stopPropagation(); unprocessMut.mutate(group) }}
                              disabled={unprocessMut.isPending}
                            >
                              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                              Înapoi în lucru
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                      {isExpanded && group.invoices.map((inv) => (
                        <TableRow key={inv.id}>
                          <TableCell />
                          <TableCell className="pl-8">
                            <div className="flex items-center gap-2">
                              {!isProcessedView && (
                                <Checkbox
                                  checked={selectedInvoiceIds.has(inv.id)}
                                  onCheckedChange={() => toggleInvoiceSelected(inv.id)}
                                />
                              )}
                              {inv.invoice_number}
                            </div>
                          </TableCell>
                          <TableCell className="whitespace-nowrap">{new Date(inv.invoice_date).toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })}</TableCell>
                          <TableCell className="text-right">
                            {inv.net_value != null ? <CurrencyDisplay value={Number(inv.net_value)} currency={inv.currency} /> : '—'}
                          </TableCell>
                          <TableCell className="text-right"><CurrencyDisplay value={Number(inv.invoice_value)} currency={inv.currency} /></TableCell>
                          <TableCell>{inv.currency}</TableCell>
                          <TableCell>
                            {companyId != null && (
                              <InvoicePresetPicker inv={inv} companyId={companyId} disabled={isProcessedView} />
                            )}
                          </TableCell>
                          <TableCell />
                        </TableRow>
                      ))}
                    </Fragment>
                  )
                })}
                {!invoicesLoading && supplierGroups.length === 0 && (
                  <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-8">
                    {isProcessedView ? 'Nicio factură procesată în interval' : 'Nicio factură bugetată în interval'}
                  </TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="master">
          <Card><CardContent className="p-0">
            {masterView === 'deleted' ? (
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Name</TableHead><TableHead>CUI</TableHead>
                  <TableHead>Șters de</TableHead><TableHead>Data ștergerii</TableHead>
                  <TableHead className="w-28" /></TableRow></TableHeader>
                <TableBody>
                  {(masters?.suppliers ?? []).map((s: MasterSupplier) => (
                    <TableRow key={s.id}>
                      <TableCell className="font-medium">{s.name}</TableCell>
                      <TableCell>{s.cui ?? '-'}</TableCell>
                      <TableCell>{s.deleted_by_name ?? '-'}</TableCell>
                      <TableCell className="whitespace-nowrap">{s.deleted_at ? new Date(s.deleted_at).toLocaleString('ro-RO') : '-'}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost" size="sm" className="h-7 gap-1.5"
                          title="Restaurează furnizorul"
                          onClick={() => restoreSupMut.mutate(s.id)}
                          disabled={restoreSupMut.isPending}
                        >
                          <RotateCcw className="h-3.5 w-3.5" /> Restaurează
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!mastersLoading && (masters?.suppliers ?? []).length === 0 && (
                    <TableRow><TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-8">Niciun furnizor șters</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            ) : (
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Name</TableHead><TableHead>CUI</TableHead>
                  <TableHead>Konto (D/C)</TableHead><TableHead>Gegenkonto (D/C)</TableHead>
                  <TableHead>Kostenstelle (D/C)</TableHead><TableHead>Extbeleg (D/C)</TableHead><TableHead>Klient</TableHead>
                  <TableHead className="w-20" /></TableRow></TableHeader>
                <TableBody>
                  {(masters?.suppliers ?? []).map((s: MasterSupplier) => (
                    <TableRow
                      key={s.id}
                      className="cursor-pointer hover:bg-muted/40"
                      onClick={() => openEditor(s)}
                    >
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          {s.name}
                          {s.has_company_config === false && (
                            <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground" title="Folosește configurația implicită a furnizorului">implicit</Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>{s.cui ?? '-'}</TableCell>
                      <TableCell>{`${s.konto_debit ?? '-'} / ${s.konto_credit ?? '-'}`}</TableCell>
                      <TableCell>{`${s.gegenkonto_debit ?? '-'} / ${s.gegenkonto_credit ?? '-'}`}</TableCell>
                      <TableCell>{`${s.kostenstelle_debit ?? '-'} / ${s.kostenstelle_credit ?? '-'}`}</TableCell>
                      <TableCell>{`${s.extbeleg_debit ?? '-'} / ${s.extbeleg_credit ?? '-'}`}</TableCell>
                      <TableCell>{s.klient ?? '-'}</TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-0.5">
                          <Button
                            variant="ghost" size="icon" className="h-7 w-7"
                            title="Editează konto"
                            onClick={(e) => { e.stopPropagation(); openEditor(s) }}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive"
                            title="Șterge furnizorul"
                            onClick={(e) => { e.stopPropagation(); setDeleteSup(s) }}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!mastersLoading && (masters?.suppliers ?? []).length === 0 && (
                    <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-8">Niciun furnizor găsit</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent></Card>
        </TabsContent>
      </Tabs>
      )}

      {/* ═══ Add supplier ═══ */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Adaugă furnizor</DialogTitle>
            <DialogDescription>Creează o identitate nouă de furnizor în master.</DialogDescription>
          </DialogHeader>
          <div className="max-h-[70vh] space-y-5 overflow-y-auto pr-1">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Nume *</Label>
                <Input className="h-8 text-sm" value={addForm.name} onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">CUI</Label>
                <Input className="h-8 text-sm" value={addForm.cui} onChange={(e) => setAddForm((f) => ({ ...f, cui: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Nr. Reg. Com.</Label>
                <Input className="h-8 text-sm" value={addForm.nr_reg_com} onChange={(e) => setAddForm((f) => ({ ...f, nr_reg_com: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Ref. No.</Label>
                <Input className="h-8 text-sm" value={addForm.ref_no} onChange={(e) => setAddForm((f) => ({ ...f, ref_no: e.target.value }))} />
              </div>
            </div>

            <div className="space-y-2 border-t pt-4">
              <div>
                <div className="text-sm font-medium">Eurofib Company Data</div>
                <p className="text-xs text-muted-foreground">Se va salva pentru {selectedCompany ? companyLabel(selectedCompany) : ''}.</p>
              </div>
              <KontoFieldsGrid form={addKonto} onChange={setAddKontoField} />
            </div>
            <ReplicateAllCheckbox id="add-replicate-all" checked={addReplicateAll} onCheckedChange={setAddReplicateAll} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Anulează</Button>
            <Button onClick={() => createMut.mutate()} disabled={!addForm.name.trim() || createMut.isPending}>
              {createMut.isPending ? 'Se salvează...' : 'Salvează'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══ Sync furnizori din e-Factura ═══ */}
      <SyncEfacturaDialog
        open={syncOpen}
        company={selectedCompany}
        onOpenChange={setSyncOpen}
      />

      {/* ═══ Per-company konto editor ═══ */}
      <KontoEditorDialog
        supplier={editorSupplier}
        company={selectedCompany}
        onOpenChange={(open) => { if (!open) setEditorSupplier(null) }}
      />

      {/* ═══ Delete Furnizor (soft delete) confirmation ═══ */}
      <ConfirmDialog
        open={deleteSup !== null}
        onOpenChange={(open) => { if (!open) setDeleteSup(null) }}
        title="Șterge furnizorul"
        description={`Furnizorul „${deleteSup?.name ?? ''}” va fi șters și nu va mai apărea în liste sau la rezolvarea facturilor. Îl poți restaura din „Șterse”. Acțiunea este înregistrată în jurnal.`}
        confirmLabel="Șterge"
        variant="destructive"
        onConfirm={() => { if (deleteSup) deleteSupMut.mutate(deleteSup.id) }}
      />
    </div>
  )
}

/* ═══════════════════════════════════════
   Konto editor — per (supplier, company)
   ═══════════════════════════════════════ */

/** A local editable draft: an existing preset (id set) or a brand-new one (id null). */
type PresetDraft = { id: number | null; name: string; is_active: boolean; konto: KontoConfig }

function draftFromPreset(p: KontoPreset): PresetDraft {
  const { id, name, is_active, ...konto } = p
  return { id, name, is_active, konto: konto as KontoConfig }
}

function KontoEditorDialog({
  supplier,
  company,
  onOpenChange,
}: {
  supplier: MasterSupplier | null
  company: CompanyWithBrands | null
  onOpenChange: (open: boolean) => void
}) {
  const qc = useQueryClient()
  const [draft, setDraft] = useState<PresetDraft | null>(null)
  const [replicateAll, setReplicateAll] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<KontoPreset | null>(null)

  const open = !!supplier && !!company
  const supplierId = supplier?.id ?? null
  const companyId = company?.id ?? null

  const { data, isLoading } = useQuery({
    queryKey: ['supplier-presets', supplierId, companyId],
    queryFn: () => suppliersApi.listPresets(supplierId as number, companyId as number),
    enabled: open,
  })
  const presets = data?.presets ?? []
  const maxPresets = data?.max ?? 5
  const atLimit = presets.length >= maxPresets

  // On (re)load, keep the current selection if it still exists, else select the active preset
  // (or the first). When the supplier has no presets yet, start a fresh draft.
  useEffect(() => {
    if (!open) { setDraft(null); return }
    if (!data) return
    setDraft((prev) => {
      if (prev && prev.id !== null) {
        const still = presets.find((p) => p.id === prev.id)
        if (still) return draftFromPreset(still)
      } else if (prev && prev.id === null) {
        return prev  // keep an in-progress new draft
      }
      const active = presets.find((p) => p.is_active) ?? presets[0]
      return active ? draftFromPreset(active) : { id: null, name: 'Implicit', is_active: true, konto: { ...EMPTY_KONTO } }
    })
  }, [data, open]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setReplicateAll(false) }, [supplierId])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['supplier-master'] })
    qc.invalidateQueries({ queryKey: ['supplier-presets', supplierId, companyId] })
    qc.invalidateQueries({ queryKey: ['supplier-worklist-invoices'] })
  }

  const saveMut = useMutation({
    mutationFn: async () => {
      if (!supplierId || companyId === null || !draft) throw new Error('Missing data')
      const name = (draft.name || '').trim() || 'Implicit'
      const body = { ...draft.konto, name, is_active: draft.is_active, replicate_all: replicateAll }
      if (draft.id === null) {
        const res = await suppliersApi.createPreset(supplierId, companyId, body)
        return { newId: res.id as number }
      }
      await suppliersApi.updatePreset(supplierId, companyId, draft.id, body)
      return { newId: draft.id }
    },
    onSuccess: ({ newId }) => {
      invalidate()
      setDraft((prev) => (prev ? { ...prev, id: newId } : prev))
      toast.success(replicateAll ? 'Schemă salvată pentru toate companiile' : 'Schemă salvată')
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : 'Nu s-a putut salva schema'),
  })

  const activateMut = useMutation({
    mutationFn: (presetId: number) => suppliersApi.activatePreset(supplierId as number, companyId as number, presetId),
    onSuccess: () => { invalidate(); toast.success('Schemă activă actualizată') },
    onError: () => toast.error('Nu s-a putut schimba schema activă'),
  })

  const deleteMut = useMutation({
    mutationFn: (presetId: number) => suppliersApi.deletePreset(supplierId as number, companyId as number, presetId),
    onSuccess: (_res, presetId) => {
      invalidate()
      setDraft((prev) => (prev && prev.id === presetId ? null : prev))
      toast.success('Schemă ștearsă')
    },
    onError: () => toast.error('Nu s-a putut șterge schema'),
  })

  const startNewDraft = () => {
    const n = presets.length + 1
    setDraft({ id: null, name: `Schemă ${n}`, is_active: presets.length === 0, konto: { ...EMPTY_KONTO } })
  }

  const setField = (key: keyof KontoConfig, value: string) =>
    setDraft((prev) => (prev ? { ...prev, konto: { ...prev.konto, [key]: value || null } } : prev))

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{supplier?.name} — {company ? companyLabel(company) : ''}</DialogTitle>
          <DialogDescription>Scheme EuroFib — pentru această companie (max. {maxPresets})</DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Se încarcă...</div>
        ) : (
          <div className="grid grid-cols-[220px_1fr] gap-4">
            {/* Preset list */}
            <div className="space-y-1.5 border-r pr-3">
              {presets.map((p) => {
                const isSelected = draft?.id === p.id
                return (
                  <div
                    key={p.id}
                    className={cn(
                      'group flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm cursor-pointer',
                      isSelected ? 'bg-accent' : 'hover:bg-accent/50')}
                    onClick={() => setDraft(draftFromPreset(p))}
                  >
                    <button
                      type="button"
                      title={p.is_active ? 'Schema activă' : 'Setează ca activă'}
                      onClick={(e) => { e.stopPropagation(); if (!p.is_active) activateMut.mutate(p.id) }}
                      className={cn(
                        'flex h-4 w-4 shrink-0 items-center justify-center rounded-full border',
                        p.is_active ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40')}
                    >
                      {p.is_active && <Check className="h-3 w-3" />}
                    </button>
                    <span className="flex-1 truncate">{p.name}</span>
                    <button
                      type="button"
                      title="Șterge schema"
                      onClick={(e) => { e.stopPropagation(); setPendingDelete(p) }}
                      className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )
              })}
              {draft?.id === null && (
                <div className="flex items-center gap-1.5 rounded-md bg-accent px-2 py-1.5 text-sm">
                  <span className="h-4 w-4 shrink-0 rounded-full border border-dashed border-muted-foreground/40" />
                  <span className="flex-1 truncate italic text-muted-foreground">{draft.name} (nouă)</span>
                </div>
              )}
              <Button
                variant="ghost" size="sm"
                className="w-full justify-start gap-1.5 text-muted-foreground"
                disabled={atLimit || draft?.id === null}
                onClick={startNewDraft}
              >
                <Plus className="h-3.5 w-3.5" /> Adaugă schemă
              </Button>
              {atLimit && <p className="px-2 text-[11px] text-muted-foreground">Limită de {maxPresets} scheme atinsă.</p>}
            </div>

            {/* Editor for the selected/new preset */}
            {draft ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <Label className="text-xs">Nume schemă</Label>
                    <Input
                      className="h-8 text-sm"
                      value={draft.name}
                      onChange={(e) => setDraft((prev) => (prev ? { ...prev, name: e.target.value } : prev))}
                    />
                  </div>
                  <label className="mt-4 flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm">
                    <Checkbox
                      checked={draft.is_active}
                      disabled={draft.id !== null && draft.is_active}
                      onCheckedChange={(v) => setDraft((prev) => (prev ? { ...prev, is_active: v === true } : prev))}
                    />
                    Schemă activă
                  </label>
                </div>
                <KontoFieldsGrid form={draft.konto} onChange={setField} />
                <ReplicateAllCheckbox id="edit-replicate-all" checked={replicateAll} onCheckedChange={setReplicateAll} />
              </div>
            ) : (
              <div className="flex items-center justify-center text-sm text-muted-foreground">
                Selectează o schemă sau adaugă una nouă.
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Închide</Button>
          <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !draft}>
            {saveMut.isPending ? 'Se salvează...' : 'Salvează schema'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    <ConfirmDialog
      open={pendingDelete !== null}
      onOpenChange={(o) => { if (!o) setPendingDelete(null) }}
      title="Șterge schema"
      description={`Schema „${pendingDelete?.name ?? ''}” va fi ștearsă definitiv. Acțiunea este înregistrată în jurnal.`}
      confirmLabel="Șterge"
      variant="destructive"
      onConfirm={() => { if (pendingDelete) { deleteMut.mutate(pendingDelete.id); setPendingDelete(null) } }}
    />
    </>
  )
}

/* ═══════════════════════════════════════
   Sync furnizori din e-Factura
   ═══════════════════════════════════════ */

const partnerKey = (p: Pick<EfacturaPartner, 'partner_name' | 'partner_cif'>) =>
  `${p.partner_name}||${p.partner_cif ?? ''}`

function SyncEfacturaDialog({
  open,
  company,
  onOpenChange,
}: {
  open: boolean
  company: CompanyWithBrands | null
  onOpenChange: (open: boolean) => void
}) {
  const qc = useQueryClient()
  const companyId = company?.id ?? null
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['efactura-partners', companyId],
    queryFn: () => suppliersApi.efacturaPartners(companyId as number),
    enabled: open && companyId !== null,
  })

  const partners = data?.partners ?? []

  // Default selection: genuinely-new partners checked, already-existing ones unchecked
  // (so we don't create duplicates — the user can still tick them to link).
  useEffect(() => {
    if (data) setSelected(new Set(data.partners.filter((p) => !p.existing).map(partnerKey)))
  }, [data])

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const allKeys = partners.map(partnerKey)
  const allChecked = allKeys.length > 0 && allKeys.every((k) => selected.has(k))
  const toggleAll = () => setSelected(allChecked ? new Set() : new Set(allKeys))

  const importMut = useMutation({
    mutationFn: () =>
      suppliersApi.importEfactura(
        partners
          .filter((p) => selected.has(partnerKey(p)))
          .map((p) => ({ partner_name: p.partner_name, partner_cif: p.partner_cif })),
      ),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['supplier-master'] })
      qc.invalidateQueries({ queryKey: ['efactura-partners'] })
      const parts: string[] = []
      if (res.created) parts.push(`${res.created} creați`)
      if (res.linked) parts.push(`${res.linked} legați`)
      toast.success(parts.length ? `Import e-Factura: ${parts.join(', ')}` : 'Nimic de importat')
      onOpenChange(false)
    },
    onError: () => toast.error('Importul din e-Factura a eșuat'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Importă furnizori din e-Factura</DialogTitle>
          <DialogDescription>
            Furnizori din facturile primite{company ? ` — ${companyLabel(company)}` : ''}, care nu sunt încă în master.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Se încarcă…</div>
        ) : partners.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Niciun furnizor nou în e-Factura.</div>
        ) : (
          <div className="max-h-[60vh] overflow-y-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead className="w-8">
                  <Checkbox checked={allChecked} onCheckedChange={toggleAll} aria-label="Selectează tot" />
                </TableHead>
                <TableHead>Furnizor</TableHead>
                <TableHead>CUI</TableHead>
                <TableHead className="text-right">Facturi</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {partners.map((p) => {
                  const key = partnerKey(p)
                  return (
                    <TableRow key={key} className="cursor-pointer hover:bg-muted/40" onClick={() => toggle(key)}>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Checkbox checked={selected.has(key)} onCheckedChange={() => toggle(key)} />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          {p.partner_name}
                          {p.existing && (
                            <Badge
                              variant="outline"
                              className="text-[10px] font-normal text-muted-foreground"
                              title={p.candidate_name ? `Se leagă de: ${p.candidate_name}` : 'Există deja în master'}
                            >
                              există deja
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>{p.partner_cif ?? '-'}</TableCell>
                      <TableCell className="text-right">{p.count}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Anulează</Button>
          <Button onClick={() => importMut.mutate()} disabled={selected.size === 0 || importMut.isPending}>
            {importMut.isPending ? 'Se importă…' : `Importă ${selected.size} furnizori`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
