import { useCallback, useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Pencil } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageHeader } from '@/components/shared/PageHeader'
import { useAuthStore } from '@/stores/authStore'
import { organizationApi } from '@/api/organization'
import { suppliersApi, type MasterSupplier, type WorklistItem, type KontoConfig } from '@/api/suppliers'
import type { CompanyWithBrands } from '@/types/organization'

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

export default function Procesare() {
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [tab, setTab] = useState<'worklist' | 'master'>('worklist')
  const [search, setSearch] = useState('')

  // Company gating — a specific company is always required (persisted to URL as ?company=<id>)
  const [companyId, setCompanyIdState] = useState<number | null>(() => {
    const raw = new URLSearchParams(window.location.search).get('company')
    if (raw) {
      const n = Number(raw)
      if (!Number.isNaN(n)) return n
    }
    return null
  })

  const setCompanyId = useCallback((value: number) => {
    setCompanyIdState(value)
    const url = new URL(window.location.href)
    url.searchParams.set('company', String(value))
    window.history.replaceState({}, '', url.toString())
  }, [])

  const { data: companiesData } = useQuery({
    queryKey: ['companies-config'],
    queryFn: () => organizationApi.getCompaniesConfig(),
    staleTime: 10 * 60_000,
  })
  const companies = companiesData || []
  const selectedCompany = companies.find((c) => c.id === companyId) || null

  // Resolve the default company once the list loads: URL param → user's own company → first in list.
  useEffect(() => {
    if (companies.length === 0) return
    if (companyId !== null && companies.some((c) => c.id === companyId)) return
    if (user?.company_id && companies.some((c) => c.id === user.company_id)) {
      setCompanyId(user.company_id)
      return
    }
    setCompanyId(companies[0].id)
  }, [companies, companyId, user, setCompanyId])

  const { data: wl } = useQuery({
    queryKey: ['supplier-worklist', companyId],
    queryFn: () => suppliersApi.worklist(companyId as number),
    enabled: !!companyId,
  })
  const { data: masters, isLoading: mastersLoading } = useQuery({
    queryKey: ['supplier-master', companyId, search],
    queryFn: () => suppliersApi.list(companyId as number, search || undefined),
    enabled: !!companyId,
  })

  const resolveMut = useMutation({
    mutationFn: (i: WorklistItem) =>
      suppliersApi.resolve(i.candidate_id
        ? { action: 'link', partner_name: i.partner_name, partner_cif: i.partner_cif, supplier_id: i.candidate_id }
        : { action: 'create', partner_name: i.partner_name, partner_cif: i.partner_cif }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['supplier-worklist'] }); toast.success('Resolved') },
    onError: () => toast.error('Failed to resolve'),
  })

  // ── Add supplier dialog ──
  const [addOpen, setAddOpen] = useState(false)
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

  return (
    <div className="space-y-4">
      <PageHeader
        title="Procesare Furnizori"
        breadcrumbs={[{ label: 'Accounting' }, { label: 'Procesare' }]}
        actions={
          <>
            <Select
              value={companyId !== null ? String(companyId) : undefined}
              onValueChange={(v) => setCompanyId(Number(v))}
              disabled={companies.length === 0}
            >
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Se încarcă companiile…" />
              </SelectTrigger>
              <SelectContent>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{companyLabel(c)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              placeholder="Search suppliers…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-56"
            />
            <Button size="icon" onClick={() => setAddOpen(true)} title="Adaugă furnizor" disabled={companyId === null}>
              <Plus className="h-4 w-4" />
            </Button>
          </>
        }
      />
      {companyId === null ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Se încarcă companiile…</div>
      ) : (
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          <TabsTrigger value="worklist">Worklist ({wl?.items.length ?? 0})</TabsTrigger>
          <TabsTrigger value="master">Master</TabsTrigger>
        </TabsList>

        <TabsContent value="worklist">
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Source</TableHead><TableHead>Name</TableHead><TableHead>CUI</TableHead>
                <TableHead>Suggested</TableHead><TableHead>Confidence</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {(wl?.items ?? []).map((i, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{i.source}</TableCell>
                    <TableCell>{i.partner_name}</TableCell>
                    <TableCell>{i.partner_cif ?? '-'}</TableCell>
                    <TableCell>{i.candidate_id ? `#${i.candidate_id} (${i.method})` : '—'}</TableCell>
                    <TableCell>{i.confidence}</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" onClick={() => resolveMut.mutate(i)} disabled={resolveMut.isPending}>
                        {i.candidate_id ? 'Link' : 'Create'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {(wl?.items ?? []).length === 0 && (
                  <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-8">Nimic de rezolvat</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="master">
          <Card><CardContent className="p-0">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Name</TableHead><TableHead>CUI</TableHead>
                <TableHead>Konto (D/C)</TableHead><TableHead>Gegenkonto (D/C)</TableHead>
                <TableHead>Kostenstelle (D/C)</TableHead><TableHead>Extbeleg (D/C)</TableHead><TableHead>Klient</TableHead>
                <TableHead className="w-10" /></TableRow></TableHeader>
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
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        title="Editează konto"
                        onClick={(e) => { e.stopPropagation(); openEditor(s) }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {!mastersLoading && (masters?.suppliers ?? []).length === 0 && (
                  <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-8">Niciun furnizor găsit</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
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
                <div className="text-sm font-medium">Configurație EuroFib (Table 2)</div>
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

      {/* ═══ Per-company konto editor ═══ */}
      <KontoEditorDialog
        supplier={editorSupplier}
        company={selectedCompany}
        onOpenChange={(open) => { if (!open) setEditorSupplier(null) }}
      />
    </div>
  )
}

/* ═══════════════════════════════════════
   Konto editor — per (supplier, company)
   ═══════════════════════════════════════ */

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
  const [form, setForm] = useState<KontoConfig | null>(null)
  const [replicateAll, setReplicateAll] = useState(false)

  const open = !!supplier && !!company
  const supplierId = supplier?.id ?? null
  const companyId = company?.id ?? null

  const { data, isLoading } = useQuery({
    queryKey: ['supplier-konto', supplierId, companyId],
    queryFn: () => suppliersApi.getKonto(supplierId as number, companyId as number),
    enabled: open,
  })

  useEffect(() => {
    if (data?.konto) setForm(data.konto)
    else if (!open) setForm(null)
  }, [data, open])

  // Reset the "replicate to all" choice whenever a different supplier is opened for editing.
  useEffect(() => {
    setReplicateAll(false)
  }, [supplierId])

  const saveMut = useMutation({
    mutationFn: () => {
      if (!supplierId || companyId === null || !form) throw new Error('Missing data')
      return suppliersApi.updateKonto(supplierId, companyId, form, replicateAll)
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['supplier-master'] })
      qc.invalidateQueries({ queryKey: ['supplier-konto', supplierId, companyId] })
      toast.success(res.replicated ? `Configurație salvată pentru ${res.replicated} companii` : 'Configurație salvată')
      onOpenChange(false)
    },
    onError: () => toast.error('Nu s-a putut salva configurația'),
  })

  const setField = (key: keyof KontoConfig, value: string) =>
    setForm((prev) => (prev ? { ...prev, [key]: value || null } : prev))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{supplier?.name} — {company ? companyLabel(company) : ''}</DialogTitle>
          <DialogDescription>Configurație EuroFib pentru această companie (Table 2)</DialogDescription>
        </DialogHeader>
        {isLoading || !form ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Se încarcă...</div>
        ) : (
          <div className="space-y-4">
            <KontoFieldsGrid form={form} onChange={setField} />
            <ReplicateAllCheckbox id="edit-replicate-all" checked={replicateAll} onCheckedChange={setReplicateAll} />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Anulează</Button>
          <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !form}>
            {saveMut.isPending ? 'Se salvează...' : 'Salvează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
