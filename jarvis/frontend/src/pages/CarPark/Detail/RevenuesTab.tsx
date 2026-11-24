// CarPark vehicle Detail — "Financiar" Venituri table. Flat, spreadsheet-style
// list of revenue entries, mirroring CostsTab: the original invoice amount (its
// currency) is the primary figure, the EUR equivalent is shown beneath each
// money column, and the BNR curs under the date. Subtotal/summary are EUR.
import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Pencil, Trash2, TrendingUp } from 'lucide-react'
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
import { REVENUE_TYPE_LABELS, type RevenueType, type VehicleRevenue } from '@/types/carpark'

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

const eurNet = (r: VehicleRevenue) => Number(r.amount_eur ?? r.amount ?? 0)
const eurVat = (r: VehicleRevenue) => Number(r.vat_amount_eur ?? r.vat_amount ?? 0)

export function RevenuesTab({
  vehicleId, revenues, canEdit,
}: {
  vehicleId: number; revenues: VehicleRevenue[]; canEdit: boolean
}) {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
  const [form, setForm] = useState({
    revenue_type: 'sale' as RevenueType,
    amount: '', description: '', client_name: '', invoice_number: '',
    date: new Date().toISOString().slice(0, 10), vat_amount: '',
  })

  const resetForm = () => {
    setForm({
      revenue_type: 'sale', amount: '', description: '', client_name: '',
      invoice_number: '', date: new Date().toISOString().slice(0, 10), vat_amount: '',
    })
    setEditingId(null)
    setDialogOpen(false)
  }

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['carpark', 'revenues', vehicleId] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'profitability', vehicleId] })
    queryClient.invalidateQueries({ queryKey: ['carpark', 'documents', vehicleId] })
  }

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => carparkApi.createRevenue(vehicleId, data),
    onSuccess: () => { invalidate(); toast.success('Venit adăugat'); resetForm() },
    onError: () => toast.error('Adăugarea venitului a eșuat'),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => carparkApi.updateRevenue(id, data),
    onSuccess: () => { invalidate(); toast.success('Venit actualizat'); resetForm() },
    onError: () => toast.error('Actualizarea venitului a eșuat'),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => carparkApi.deleteRevenue(id),
    onSuccess: () => { invalidate(); toast.success('Venit șters'); setDeleteConfirmId(null) },
    onError: () => toast.error('Ștergerea venitului a eșuat'),
  })

  const handleSubmit = () => {
    const payload = {
      revenue_type: form.revenue_type,
      amount: Number(form.amount),
      description: form.description || null,
      client_name: form.client_name || null,
      invoice_number: form.invoice_number || null,
      date: form.date,
      vat_amount: form.vat_amount ? Number(form.vat_amount) : 0,
    }
    if (editingId) updateMutation.mutate({ id: editingId, data: payload })
    else createMutation.mutate(payload)
  }

  const startEdit = (r: VehicleRevenue) => {
    setForm({
      revenue_type: r.revenue_type, amount: String(r.amount), description: r.description ?? '',
      client_name: r.client_name ?? '', invoice_number: r.invoice_number ?? '',
      date: r.date, vat_amount: String(r.vat_amount ?? 0),
    })
    setEditingId(r.id)
    setDialogOpen(true)
  }

  const totalNet = revenues.reduce((s, r) => s + eurNet(r), 0)
  const totalVat = revenues.reduce((s, r) => s + eurVat(r), 0)
  const totalGross = totalNet + totalVat

  const byType = useMemo(() => {
    const map: Record<string, number> = {}
    revenues.forEach((r) => { map[r.revenue_type] = (map[r.revenue_type] ?? 0) + eurNet(r) })
    return Object.entries(map).sort(([, a], [, b]) => b - a)
  }, [revenues])

  return (
    <div className="space-y-4">
      {/* Summary bar (EUR) */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="text-muted-foreground">Net: <span className="font-semibold text-emerald-600 tabular-nums">{fmt(totalNet)} EUR</span></span>
          {totalVat > 0 && <span className="text-muted-foreground">TVA: <span className="font-medium tabular-nums">{fmt(totalVat)} EUR</span></span>}
          <span className="text-muted-foreground">Total: <span className="font-bold text-emerald-600 tabular-nums">{fmt(totalGross)} EUR</span></span>
        </div>
        {canEdit && (
          <Button size="sm" onClick={() => { resetForm(); setDialogOpen(true) }}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă venit
          </Button>
        )}
      </div>

      {byType.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {byType.map(([type, amount]) => {
            const pct = totalNet > 0 ? Math.round((amount / totalNet) * 100) : 0
            return (
              <div key={type} className="flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs">
                <span className="font-medium">{REVENUE_TYPE_LABELS[type as RevenueType] ?? type}</span>
                <span className="tabular-nums text-muted-foreground">{fmt(amount)} €</span>
                <span className="text-[10px] text-muted-foreground">({pct}%)</span>
              </div>
            )
          })}
        </div>
      )}

      {revenues.length === 0 ? (
        <EmptyState title="Niciun venit înregistrat" icon={<TrendingUp className="h-8 w-8" />} />
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-xs text-muted-foreground">
                <th className="text-left px-3 py-2 font-medium">Dată</th>
                <th className="text-left px-3 py-2 font-medium">Tip</th>
                <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">Client</th>
                <th className="text-left px-3 py-2 font-medium hidden lg:table-cell">Nr. factură</th>
                <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Descriere</th>
                <th className="text-right px-3 py-2 font-medium">Net</th>
                <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">TVA</th>
                <th className="text-right px-3 py-2 font-medium">Total</th>
                {canEdit && <th className="px-2 py-2 w-20"></th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {revenues.map((r) => {
                const netEurV = eurNet(r)
                const vatEurV = eurVat(r)
                const isForeign = !!r.currency && r.currency !== 'EUR'
                const origNet = Number(r.amount)
                const origVat = Number(r.vat_amount ?? 0)
                return (
                  <tr key={r.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-3 py-2 tabular-nums text-xs align-top">
                      <div>{formatDate(r.date)}</div>
                      {isForeign && r.exchange_rate_eur ? (
                        <div className="text-[10px] text-muted-foreground">curs {fmtRate(Number(r.exchange_rate_eur))}</div>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant="outline" className="text-[11px]">{REVENUE_TYPE_LABELS[r.revenue_type] ?? r.revenue_type}</Badge>
                    </td>
                    <td className="px-3 py-2 hidden sm:table-cell text-muted-foreground truncate max-w-[140px]">{r.client_name || '-'}</td>
                    <td className="px-3 py-2 hidden lg:table-cell font-mono text-xs text-muted-foreground">{r.invoice_number || '-'}</td>
                    <td className="px-3 py-2 hidden md:table-cell text-muted-foreground truncate max-w-[180px]">{r.description || '-'}</td>
                    <td className="px-3 py-2 text-right tabular-nums align-top">
                      <div>{fmt(origNet)}{isForeign ? ` ${r.currency}` : ''}</div>
                      {isForeign && <div className="text-[10px] text-muted-foreground tabular-nums">≈ {fmt(netEurV)} €</div>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell align-top">
                      <div>{origVat > 0 ? `${fmt(origVat)}${isForeign ? ` ${r.currency}` : ''}` : '-'}</div>
                      {isForeign && origVat > 0 && <div className="text-[10px] tabular-nums">≈ {fmt(vatEurV)} €</div>}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium align-top">
                      <div>{fmt(origNet + origVat)}{isForeign ? ` ${r.currency}` : ''}</div>
                      {isForeign && <div className="text-[10px] font-normal text-muted-foreground tabular-nums">≈ {fmt(netEurV + vatEurV)} €</div>}
                    </td>
                    {canEdit && (
                      <td className="px-2 py-2 text-right whitespace-nowrap">
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" aria-label="Editează venit" onClick={() => startEdit(r)}>
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500 hover:text-red-600" aria-label="Șterge venit" onClick={() => setDeleteConfirmId(r.id)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
            {revenues.length > 1 && (
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

      {/* Add/Edit Revenue Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { if (!open) resetForm() }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Editează venit' : 'Adaugă venit'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Tip</Label>
                <Select value={form.revenue_type} onValueChange={(v) => setForm((p) => ({ ...p, revenue_type: v as RevenueType }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(REVENUE_TYPE_LABELS).map(([k, label]) => (
                      <SelectItem key={k} value={k}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Dată</Label>
                <Input type="date" value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Sumă (net)</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={form.amount} onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))} />
              </div>
              <div>
                <Label>Valoare TVA</Label>
                <Input type="number" step="0.01" placeholder="0.00" value={form.vat_amount} onChange={(e) => setForm((p) => ({ ...p, vat_amount: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Client</Label>
                <Input placeholder="Nume client" value={form.client_name} onChange={(e) => setForm((p) => ({ ...p, client_name: e.target.value }))} />
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
            <Button variant="outline" onClick={resetForm}>Anulează</Button>
            <Button onClick={handleSubmit} disabled={!form.amount || Number(form.amount) <= 0 || createMutation.isPending || updateMutation.isPending}>
              {createMutation.isPending || updateMutation.isPending ? 'Se salvează...' : editingId ? 'Actualizează' : 'Adaugă'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={deleteConfirmId !== null} onOpenChange={(open) => { if (!open) setDeleteConfirmId(null) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Șterge venit</DialogTitle>
            <DialogDescription>Ești sigur? Această acțiune nu poate fi anulată.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>Anulează</Button>
            <Button variant="destructive" disabled={deleteMutation.isPending} onClick={() => deleteConfirmId && deleteMutation.mutate(deleteConfirmId)}>
              {deleteMutation.isPending ? 'Se șterge...' : 'Șterge'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
