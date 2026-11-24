// CarPark vehicle Detail — "Financiar" Costuri table. A flat, spreadsheet-style
// list of cost ENTRIES (one row each), mirroring the sibling RevenuesTab, so
// accounting can scan it at a glance. The old cost-line/budget grouping
// (Planificat/Execuție, expand/collapse, Adaugă linie) is gone: adding a cost is
// a single "Adaugă cost" step, and the backend files it under a line by type
// (VehicleService.create_cost → get_or_create_for_type), so no orphan costs.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { DollarSign, Plus, Pencil, Trash2, Link2, Unlink, Search } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { carparkApi } from '@/api/carpark'
import { COST_TYPE_LABELS, type CostType, type VehicleCost } from '@/types/carpark'

function formatDate(d: string | null): string {
  if (!d) return '-'
  const date = new Date(d)
  if (isNaN(date.getTime())) return d
  return date.toLocaleDateString('ro-RO')
}

const fmt = (v: number) =>
  new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)

// BNR rates carry 4 decimals (RON per 1 EUR).
const fmtRate = (v: number) =>
  new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 4, maximumFractionDigits: 4 }).format(v)

const todayStr = () => new Date().toISOString().slice(0, 10)

type CostForm = {
  cost_type: CostType
  amount: string
  description: string
  supplier_name: string
  invoice_number: string
  date: string
  vat_rate: string
  vat_amount: string
}

const emptyForm = (): CostForm => ({
  cost_type: 'achizitie', amount: '', description: '', supplier_name: '',
  invoice_number: '', date: todayStr(), vat_rate: '19', vat_amount: '',
})

export function CostsTab({
  vehicleId, canEdit, currency,
}: {
  vehicleId: number; canEdit: boolean; currency: string
}) {
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: ['carpark', 'costs', vehicleId],
    queryFn: () => carparkApi.getCosts(vehicleId),
  })
  const costs = data?.costs ?? []

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [form, setForm] = useState<CostForm>(emptyForm())
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [editTipId, setEditTipId] = useState<number | null>(null)
  const [linkCostId, setLinkCostId] = useState<number | null>(null)
  const [invoiceSearch, setInvoiceSearch] = useState('')

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['carpark', 'costs', vehicleId] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
    // A transfer-created cost that's deleted/changed frees its source document —
    // refresh the Documente tab so its Transferă / "În costuri" badge is current.
    queryClient.invalidateQueries({ queryKey: ['carpark', 'documents', vehicleId] })
  }

  const resetDialog = () => { setForm(emptyForm()); setEditId(null); setDialogOpen(false) }

  const createMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => carparkApi.createCost(vehicleId, payload),
    onSuccess: () => { invalidate(); toast.success('Cost adăugat'); resetDialog() },
    onError: () => toast.error('Adăugarea costului a eșuat'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) => carparkApi.updateCost(id, payload),
    onSuccess: () => { invalidate(); toast.success('Cost actualizat'); resetDialog() },
    onError: () => toast.error('Actualizarea costului a eșuat'),
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => carparkApi.deleteCost(id),
    onSuccess: () => { invalidate(); toast.success('Cost șters'); setDeleteId(null) },
    onError: () => toast.error('Ștergerea costului a eșuat'),
  })
  const linkMut = useMutation({
    mutationFn: ({ costId, invoiceId }: { costId: number; invoiceId: number | null }) =>
      carparkApi.linkCostInvoice(costId, invoiceId),
    onSuccess: () => { invalidate(); toast.success('Factură actualizată'); setLinkCostId(null); setInvoiceSearch('') },
    onError: () => toast.error('Operațiunea a eșuat'),
  })

  const { data: invoiceSearchData } = useQuery({
    queryKey: ['carpark', 'invoice-search', invoiceSearch],
    queryFn: () => carparkApi.searchLinkableEntities('invoice', invoiceSearch),
    enabled: linkCostId !== null && invoiceSearch.length >= 1,
  })
  const invoiceResults = invoiceSearchData?.results ?? []

  const openAdd = () => { setForm(emptyForm()); setEditId(null); setDialogOpen(true) }
  const openEdit = (c: VehicleCost) => {
    setForm({
      cost_type: c.cost_type, amount: String(c.amount), description: c.description ?? '',
      supplier_name: c.supplier_name ?? '', invoice_number: c.invoice_number ?? '',
      date: c.date, vat_rate: String(c.vat_rate ?? 19), vat_amount: String(c.vat_amount ?? 0),
    })
    setEditId(c.id); setDialogOpen(true)
  }
  const handleSubmit = () => {
    const payload = {
      cost_type: form.cost_type,
      amount: Number(form.amount),
      description: form.description || null,
      supplier_name: form.supplier_name || null,
      invoice_number: form.invoice_number || null,
      date: form.date,
      vat_rate: form.vat_rate ? Number(form.vat_rate) : 19,
      vat_amount: form.vat_amount ? Number(form.vat_amount) : 0,
    }
    // currency is a create-time attribute (it seeds the cost line); never send
    // it on edit, or it would clobber the cost's stored currency with the
    // vehicle's price_currency.
    if (editId) updateMut.mutate({ id: editId, payload })
    else createMut.mutate({ ...payload, currency })
  }

  // EUR equivalents (server-computed amount_eur/vat_amount_eur; fall back to the
  // raw amount when absent, e.g. an EUR cost). Totals/subtotal are EUR so a
  // mixed-currency sum is coherent.
  const eurNet = (c: VehicleCost) => Number(c.amount_eur ?? c.amount ?? 0)
  const eurVat = (c: VehicleCost) => Number(c.vat_amount_eur ?? c.vat_amount ?? 0)
  const totalNet = costs.reduce((s, c) => s + eurNet(c), 0)
  const totalVat = costs.reduce((s, c) => s + eurVat(c), 0)
  const totalGross = totalNet + totalVat

  return (
    <div className="space-y-4">
      {/* Summary bar — mirrors RevenuesTab */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="text-muted-foreground">Net: <span className="font-semibold tabular-nums">{fmt(totalNet)} EUR</span></span>
          {totalVat > 0 && <span className="text-muted-foreground">TVA: <span className="font-medium tabular-nums">{fmt(totalVat)} EUR</span></span>}
          <span className="text-muted-foreground">Total: <span className="font-bold tabular-nums">{fmt(totalGross)} EUR</span></span>
        </div>
        {canEdit && (
          <Button size="sm" onClick={openAdd}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă cost
          </Button>
        )}
      </div>

      {costs.length === 0 ? (
        <EmptyState title="Niciun cost înregistrat" icon={<DollarSign className="h-8 w-8" />} />
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-xs text-muted-foreground">
                <th className="text-left px-3 py-2 font-medium">Dată</th>
                <th className="text-left px-3 py-2 font-medium">Tip</th>
                <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">Furnizor</th>
                <th className="text-left px-3 py-2 font-medium hidden lg:table-cell">Factură</th>
                <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Descriere</th>
                <th className="text-right px-3 py-2 font-medium">Net</th>
                <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">TVA</th>
                <th className="text-right px-3 py-2 font-medium">Total</th>
                {canEdit && <th className="px-2 py-2 w-24"></th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {costs.map((c) => {
                const netEurV = eurNet(c)
                const vatEurV = eurVat(c)
                const isForeign = !!c.currency && c.currency !== 'EUR'
                const origNet = Number(c.amount)
                const origVat = Number(c.vat_amount ?? 0)
                return (
                  <tr key={c.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-3 py-2 tabular-nums text-xs align-top">
                      <div>{formatDate(c.date)}</div>
                      {isForeign && c.exchange_rate_eur ? (
                        <div className="text-[10px] text-muted-foreground">curs {fmtRate(Number(c.exchange_rate_eur))}</div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      {canEdit && editTipId === c.id ? (
                        <select
                          aria-label="Tip cost"
                          autoFocus
                          className="text-[11px] border rounded px-1 py-0.5 bg-background"
                          defaultValue={c.cost_type}
                          onChange={(e) => { updateMut.mutate({ id: c.id, payload: { cost_type: e.target.value } }); setEditTipId(null) }}
                          onBlur={() => setEditTipId(null)}
                        >
                          {Object.entries(COST_TYPE_LABELS).map(([k, label]) => (
                            <option key={k} value={k}>{label}</option>
                          ))}
                        </select>
                      ) : (
                        <Badge
                          variant="outline"
                          className={`text-[11px] ${canEdit ? 'cursor-pointer hover:bg-muted' : ''}`}
                          title={canEdit ? 'Schimbă tipul' : undefined}
                          onClick={canEdit ? () => setEditTipId(c.id) : undefined}
                        >
                          {COST_TYPE_LABELS[c.cost_type] ?? c.cost_type}
                        </Badge>
                      )}
                    </td>
                    <td className="px-3 py-2 hidden sm:table-cell text-muted-foreground truncate max-w-[140px]">{c.supplier_name || '-'}</td>
                    <td className="px-3 py-2 hidden lg:table-cell">
                      {c.invoice_id ? (
                        <div className="flex items-center gap-1">
                          <Badge variant="secondary" className="text-[10px] font-mono">
                            {c.invoice_number_ref || c.invoice_number || `#${c.invoice_id}`}
                          </Badge>
                          {canEdit && (
                            <Button variant="ghost" size="sm" className="h-5 w-5 p-0 text-muted-foreground hover:text-red-500"
                              onClick={() => linkMut.mutate({ costId: c.id, invoiceId: null })}>
                              <Unlink className="h-3 w-3" />
                            </Button>
                          )}
                        </div>
                      ) : c.invoice_number ? (
                        <span className="font-mono text-xs text-muted-foreground">{c.invoice_number}</span>
                      ) : canEdit ? (
                        <Button variant="ghost" size="sm" className="h-6 text-[10px] px-2 text-muted-foreground"
                          onClick={() => { setLinkCostId(c.id); setInvoiceSearch('') }}>
                          <Link2 className="h-3 w-3 mr-1" /> Asociază
                        </Button>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-3 py-2 hidden md:table-cell text-muted-foreground truncate max-w-[180px]">{c.description || '-'}</td>
                    <td className="px-3 py-2 text-right tabular-nums align-top">
                      <div>{fmt(origNet)}{isForeign ? ` ${c.currency}` : ''}</div>
                      {isForeign && <div className="text-[10px] text-muted-foreground tabular-nums">≈ {fmt(netEurV)} €</div>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell align-top">
                      <div>{origVat > 0 ? `${fmt(origVat)}${isForeign ? ` ${c.currency}` : ''}` : '-'}</div>
                      {isForeign && origVat > 0 && <div className="text-[10px] tabular-nums">≈ {fmt(vatEurV)} €</div>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium align-top">
                      <div>{fmt(origNet + origVat)}{isForeign ? ` ${c.currency}` : ''}</div>
                      {isForeign && <div className="text-[10px] font-normal text-muted-foreground tabular-nums">≈ {fmt(netEurV + vatEurV)} €</div>}
                    </td>
                    {canEdit && (
                      <td className="px-2 py-2 text-right whitespace-nowrap">
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" aria-label="Editează cost" onClick={() => openEdit(c)}>
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500 hover:text-red-600" aria-label="Șterge cost" onClick={() => setDeleteId(c.id)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
            {costs.length > 1 && (
              <tfoot>
                <tr className="border-t bg-muted/30 font-medium text-xs">
                  <td className="px-3 py-2 text-muted-foreground text-[11px]" colSpan={5}>Total (EUR)</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmt(totalNet)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell">{totalVat > 0 ? fmt(totalVat) : '-'}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-bold">{fmt(totalGross)}</td>
                  {canEdit && <td></td>}
                </tr>
              </tfoot>
            )}
          </table>
        </Card>
      )}

      {/* Add / Edit cost dialog (with Tip selector) */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { if (!open) resetDialog() }}>
        <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>{editId ? 'Editează cost' : 'Adaugă cost'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Tip *</Label>
                <Select value={form.cost_type} onValueChange={(v) => setForm((p) => ({ ...p, cost_type: v as CostType }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(COST_TYPE_LABELS).map(([k, label]) => (
                      <SelectItem key={k} value={k}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Dată *</Label>
                <Input type="date" value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label>Sumă (net) *</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={form.amount} autoFocus
                  onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))} />
              </div>
              <div>
                <Label>TVA %</Label>
                <Input type="number" step="0.01" value={form.vat_rate} onChange={(e) => setForm((p) => ({ ...p, vat_rate: e.target.value }))} />
              </div>
              <div>
                <Label>Valoare TVA</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={form.vat_amount} onChange={(e) => setForm((p) => ({ ...p, vat_amount: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Furnizor</Label>
                <Input placeholder="Nume furnizor" value={form.supplier_name} onChange={(e) => setForm((p) => ({ ...p, supplier_name: e.target.value }))} />
              </div>
              <div>
                <Label>Nr. factură</Label>
                <Input placeholder="Număr factură" value={form.invoice_number} onChange={(e) => setForm((p) => ({ ...p, invoice_number: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Descriere</Label>
              <Input placeholder="Descriere opțională" value={form.description} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={resetDialog}>Anulează</Button>
            <Button disabled={!form.amount || Number(form.amount) <= 0 || createMut.isPending || updateMut.isPending} onClick={handleSubmit}>
              {createMut.isPending || updateMut.isPending ? 'Se salvează...' : editId ? 'Actualizează' : 'Înregistrează'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Link invoice dialog */}
      <Dialog open={linkCostId !== null} onOpenChange={(open) => { if (!open) { setLinkCostId(null); setInvoiceSearch('') } }}>
        <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Asociază factură</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input placeholder="Caută facturi..." className="pl-9" value={invoiceSearch} onChange={(e) => setInvoiceSearch(e.target.value)} autoFocus />
            </div>
            {invoiceResults.length > 0 ? (
              <div className="max-h-60 overflow-y-auto rounded-md border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted/30">
                      <th className="text-left px-3 py-1.5 font-medium">Nr. factură</th>
                      <th className="text-left px-3 py-1.5 font-medium">Furnizor</th>
                      <th className="px-2 py-1.5 w-16"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {invoiceResults.map((inv) => (
                      <tr key={inv.id} className="hover:bg-muted/20">
                        <td className="px-3 py-1.5 font-mono">{inv.label}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{inv.sublabel || '-'}</td>
                        <td className="px-2 py-1.5 text-right">
                          <Button size="sm" className="h-6 text-[10px] px-2" disabled={linkMut.isPending}
                            onClick={() => linkCostId && linkMut.mutate({ costId: linkCostId, invoiceId: inv.id })}>
                            Asociază
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : invoiceSearch.length >= 1 ? (
              <div className="text-xs text-center text-muted-foreground py-4">Nicio factură găsită</div>
            ) : (
              <div className="text-xs text-center text-muted-foreground py-4">Scrie pentru a căuta facturi</div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={deleteId !== null} onOpenChange={(open) => { if (!open) setDeleteId(null) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Șterge cost</DialogTitle>
            <DialogDescription>Ești sigur? Această acțiune nu poate fi anulată.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteId(null)}>Anulează</Button>
            <Button variant="destructive" disabled={deleteMut.isPending} onClick={() => deleteId && deleteMut.mutate(deleteId)}>
              {deleteMut.isPending ? 'Se șterge...' : 'Șterge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
