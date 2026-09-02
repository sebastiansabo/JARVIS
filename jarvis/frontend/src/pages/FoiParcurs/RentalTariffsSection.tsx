import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Trash2, Plus } from 'lucide-react'
import { foiParcursApi } from '@/api/foiParcurs'

export default function RentalTariffsSection({ companyId }: { companyId?: number | null }) {
  const qc = useQueryClient()
  const cid = companyId ?? 0
  const [newIvLabel, setNewIvLabel] = useState('')
  const [newIvMin, setNewIvMin] = useState('')
  const [newIvMax, setNewIvMax] = useState('')
  const [newCatName, setNewCatName] = useState('')

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['fp-rental-intervals'] })
    qc.invalidateQueries({ queryKey: ['fp-rental-categories'] })
  }

  const { data: ivData } = useQuery({
    queryKey: ['fp-rental-intervals', cid],
    queryFn: () => foiParcursApi.getRentalIntervals(cid),
    enabled: cid > 0,
    staleTime: 30_000,
  })
  const { data: catData } = useQuery({
    queryKey: ['fp-rental-categories', cid, 'all'],
    queryFn: () => foiParcursApi.getRentalCategories(cid),
    enabled: cid > 0,
    staleTime: 30_000,
  })
  const intervals = ivData?.intervals ?? []
  const categories = catData?.categories ?? []

  const onErr = (e: unknown) =>
    toast.error((e as { data?: { error?: string } })?.data?.error ?? 'Eroare')

  const saveIv = useMutation({
    mutationFn: (p: { id?: number; label: string; min_days: number; max_days: number | null; sort_order?: number }) =>
      foiParcursApi.putRentalInterval({ company_id: cid, ...p }),
    onSuccess: () => { setNewIvLabel(''); setNewIvMin(''); setNewIvMax(''); invalidate() },
    onError: onErr,
  })
  const delIv = useMutation({
    mutationFn: (id: number) => foiParcursApi.deleteRentalInterval({ company_id: cid, id }),
    onSuccess: invalidate, onError: onErr,
  })
  const addCat = useMutation({
    mutationFn: (name: string) => foiParcursApi.addRentalCategory({ company_id: cid, name }),
    onSuccess: () => { setNewCatName(''); invalidate() }, onError: onErr,
  })
  const saveCat = useMutation({
    mutationFn: (p: { id: number; name: string; models_note: string | null; franchise_eur: number | null; extra_km_eur: number | null; sort_order?: number; is_active: boolean }) =>
      foiParcursApi.putRentalCategory({ company_id: cid, ...p }),
    onSuccess: invalidate, onError: onErr,
  })
  const delCat = useMutation({
    mutationFn: (id: number) => foiParcursApi.deleteRentalCategory({ company_id: cid, id }),
    onSuccess: invalidate, onError: onErr,
  })
  const setPrice = useMutation({
    mutationFn: (p: { category_id: number; interval_id: number; eur_per_day: number | null }) =>
      foiParcursApi.setRentalPrice({ company_id: cid, ...p }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fp-rental-categories'] }),
    onError: onErr,
  })

  if (!cid) return null

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Tarife închiriere (Mașini de curtoazie)</h3>
        <p className="text-sm text-muted-foreground">
          Intervale de durată + categorii cu preț €/zi. Fiecare mașină primește o categorie (în fișa mașinii).
        </p>
      </div>

      {/* Intervale */}
      <Card className="p-4 space-y-3">
        <p className="text-sm font-semibold">Intervale de durată (zile)</p>
        <div className="space-y-2">
          {intervals.map((iv) => (
            <div key={iv.id} className="flex items-center gap-2">
              <Input className="w-40" defaultValue={iv.label}
                     onBlur={(e) => saveIv.mutate({ id: iv.id, label: e.target.value, min_days: iv.min_days, max_days: iv.max_days, sort_order: iv.sort_order })} />
              <Input type="number" className="w-24" defaultValue={iv.min_days}
                     onBlur={(e) => saveIv.mutate({ id: iv.id, label: iv.label, min_days: Number(e.target.value), max_days: iv.max_days, sort_order: iv.sort_order })} />
              <span className="text-muted-foreground">–</span>
              <Input type="number" className="w-24" defaultValue={iv.max_days ?? ''} placeholder="∞"
                     onBlur={(e) => saveIv.mutate({ id: iv.id, label: iv.label, min_days: iv.min_days, max_days: e.target.value === '' ? null : Number(e.target.value), sort_order: iv.sort_order })} />
              <Button variant="ghost" size="icon" onClick={() => delIv.mutate(iv.id)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 border-t pt-3">
          <Input className="w-40" placeholder="ex: 1-8 zile" value={newIvLabel} onChange={(e) => setNewIvLabel(e.target.value)} />
          <Input type="number" className="w-24" placeholder="min" value={newIvMin} onChange={(e) => setNewIvMin(e.target.value)} />
          <span className="text-muted-foreground">–</span>
          <Input type="number" className="w-24" placeholder="max (∞)" value={newIvMax} onChange={(e) => setNewIvMax(e.target.value)} />
          <Button variant="outline" size="sm"
                  disabled={!newIvLabel.trim() || newIvMin === ''}
                  onClick={() => saveIv.mutate({ label: newIvLabel.trim(), min_days: Number(newIvMin), max_days: newIvMax === '' ? null : Number(newIvMax) })}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă interval
          </Button>
        </div>
      </Card>

      {/* Categorii price grid */}
      <Card className="p-4 space-y-3 overflow-x-auto">
        <p className="text-sm font-semibold">Categorii &amp; prețuri (€/zi)</p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="p-2">Categorie</th>
              {intervals.map((iv) => <th key={iv.id} className="p-2 text-center">{iv.label}</th>)}
              <th className="p-2 text-center">Franșiză €</th>
              <th className="p-2 text-center">Extra km €</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.id} className="border-b">
                <td className="p-2">
                  <Label htmlFor={`cat-name-${c.id}`} className="sr-only">{c.name}</Label>
                  <Input id={`cat-name-${c.id}`} className="w-40" defaultValue={c.name}
                         onBlur={(e) => saveCat.mutate({ id: c.id, name: e.target.value, models_note: c.models_note, franchise_eur: c.franchise_eur, extra_km_eur: c.extra_km_eur, sort_order: c.sort_order, is_active: c.is_active })} />
                </td>
                {intervals.map((iv) => (
                  <td key={iv.id} className="p-2">
                    <Input type="number" step="0.01" className="w-20 text-center"
                           defaultValue={c.prices[iv.id] ?? ''}
                           onBlur={(e) => setPrice.mutate({ category_id: c.id, interval_id: iv.id, eur_per_day: e.target.value === '' ? null : Number(e.target.value) })} />
                  </td>
                ))}
                <td className="p-2">
                  <Input type="number" step="0.01" className="w-20 text-center" defaultValue={c.franchise_eur ?? ''}
                         onBlur={(e) => saveCat.mutate({ id: c.id, name: c.name, models_note: c.models_note, franchise_eur: e.target.value === '' ? null : Number(e.target.value), extra_km_eur: c.extra_km_eur, sort_order: c.sort_order, is_active: c.is_active })} />
                </td>
                <td className="p-2">
                  <Input type="number" step="0.01" className="w-20 text-center" defaultValue={c.extra_km_eur ?? ''}
                         onBlur={(e) => saveCat.mutate({ id: c.id, name: c.name, models_note: c.models_note, franchise_eur: c.franchise_eur, extra_km_eur: e.target.value === '' ? null : Number(e.target.value), sort_order: c.sort_order, is_active: c.is_active })} />
                </td>
                <td className="p-2">
                  <Button variant="ghost" size="icon" onClick={() => delCat.mutate(c.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex items-center gap-2 border-t pt-3">
          <Input className="w-56" placeholder="Categorie nouă (ex: SUV+)" value={newCatName} onChange={(e) => setNewCatName(e.target.value)} />
          <Button variant="outline" size="sm" disabled={!newCatName.trim()} onClick={() => addCat.mutate(newCatName.trim())}>
            <Plus className="h-4 w-4 mr-1" /> Adaugă categorie
          </Button>
        </div>
      </Card>
    </div>
  )
}
