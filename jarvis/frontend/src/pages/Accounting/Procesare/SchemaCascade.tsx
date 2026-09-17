import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { suppliersApi, type SchemaCascadeData, type SchemaCascadeLine } from '@/api/suppliers'
import { cascadeReconciles, lineReconciles, buildSavePayload } from './schemaCascade'

export function SchemaCascade({ invoiceId, company, supplierId, companyId, onSaved }: {
  invoiceId: number; company: string; supplierId: number; companyId: number; onSaved: () => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['schema-cascade', invoiceId, company],
    queryFn: () => suppliersApi.getSchemaCascade(invoiceId, company),
    staleTime: 60_000,
  })
  const [lines, setLines] = useState<SchemaCascadeLine[]>([])
  const [mode, setMode] = useState<'alloc' | 'line' | 'none'>('none')
  useEffect(() => { if (data) { setLines(data.lines); setMode(data.mode) } }, [data])

  const save = useMutation({
    mutationFn: () => suppliersApi.saveSchemaCascade(invoiceId, buildSavePayload(mode as 'alloc' | 'line', lines, supplierId, companyId)),
    onSuccess: () => { toast.success('Scheme salvate'); onSaved() },
    onError: () => toast.error('Nu s-au putut salva schemele'),
  })

  if (isLoading || !data) return <div className="px-8 py-3 text-xs text-muted-foreground">Se încarcă…</div>

  const presets = data.presets
  const Picker = ({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) => (
    <Select value={value != null ? String(value) : ''} onValueChange={(v) => onChange(v ? Number(v) : null)}>
      <SelectTrigger className="h-8 w-56 text-xs"><SelectValue placeholder="Schema activă (implicit)" /></SelectTrigger>
      <SelectContent>
        {presets.map((p) => (<SelectItem key={p.id} value={String(p.id)}>{p.name}{p.is_active ? ' · activă' : ''}</SelectItem>))}
      </SelectContent>
    </Select>
  )

  const setZone = (li: number, allocId: number, kc: number | null) =>
    setLines((prev) => prev.map((l) => l.index !== li ? l : {
      ...l, allocations: l.allocations.map((a) => a.id === allocId ? { ...a, konto_config_id: kc } : a) }))
  const setLineKonto = (li: number, kc: number | null) =>
    setLines((prev) => prev.map((l) => l.index !== li ? l : { ...l, line_konto_config_id: kc }))

  return (
    <div className="space-y-3 px-8 py-3">
      {lines.map((l) => (
        <div key={l.index} className="rounded-md border p-2.5">
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="font-medium">{l.name || `Linia ${l.index + 1}`}</span>
            <span className="font-mono text-[11px] text-muted-foreground">net {l.amount != null ? Number(l.amount).toFixed(2) : '—'}</span>
          </div>
          {mode === 'alloc' && l.allocations.length > 0 ? (
            <div className="space-y-1.5">
              {l.allocations.map((a) => (
                <div key={a.id} className="grid grid-cols-[1fr_auto] items-center gap-2">
                  <span className="truncate text-xs text-muted-foreground">
                    {a.department}{a.subdepartment ? ` · ${a.subdepartment}` : ''} · {a.value != null ? Number(a.value).toFixed(2) : '—'}
                  </span>
                  <Picker value={a.konto_config_id} onChange={(v) => setZone(l.index, a.id, v)} />
                </div>
              ))}
              {!lineReconciles(l) && (
                <p className="text-[11px] text-destructive">Suma zonelor nu corespunde valorii liniei — corectează în bugetare.</p>
              )}
            </div>
          ) : mode === 'alloc' ? (
            <p className="text-[11px] text-muted-foreground">Fără alocare — se exportă cu schema de bază.</p>
          ) : (
            <Picker value={l.line_konto_config_id} onChange={(v) => setLineKonto(l.index, v)} />
          )}
        </div>
      ))}
      <div className="flex justify-end">
        <Button size="sm" className="h-7 text-xs"
          disabled={save.isPending || mode === 'none' || !cascadeReconciles(lines)}
          onClick={() => save.mutate()}>
          {save.isPending ? 'Se salvează…' : 'Salvează scheme'}
        </Button>
      </div>
    </div>
  )
}
