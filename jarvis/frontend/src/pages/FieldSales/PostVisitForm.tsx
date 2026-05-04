import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ClipboardCheck, Star } from 'lucide-react'
import type { PostVisitData } from '@/api/fieldSales'

interface Props {
  data: PostVisitData
  onChange: (data: PostVisitData) => void
  readOnly?: boolean
}

const PURCHASE_INTENT_LABELS: Record<string, string> = {
  none: 'Fara interes',
  exploring: 'Exploreaza',
  interested: 'Interesat',
  ready_to_buy: 'Gata de achizitie',
  negotiating: 'In negociere',
}

const BRAND_OPTIONS = ['BMW', 'Mercedes', 'Audi', 'Volkswagen', 'Volvo', 'Toyota', 'Hyundai', 'Skoda', 'Ford', 'Renault', 'Dacia', 'Peugeot', 'Citroen', 'Opel', 'Kia', 'Mazda', 'Nissan', 'Honda', 'Suzuki', 'Altele']

const FINANCING_OPTIONS = ['Cash', 'Leasing operational', 'Leasing financiar', 'Credit auto', 'Renting']

function SatisfactionStars({ value, onChange, readOnly }: { value?: number; onChange: (v: number) => void; readOnly?: boolean }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map(i => (
        <button
          key={i}
          type="button"
          disabled={readOnly}
          onClick={() => !readOnly && onChange(i)}
          className={`p-0.5 ${readOnly ? 'cursor-default' : 'cursor-pointer hover:scale-110'} transition-transform`}
        >
          <Star
            className={`h-5 w-5 ${i <= (value || 0) ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}`}
          />
        </button>
      ))}
    </div>
  )
}

export function PostVisitForm({ data, onChange, readOnly }: Props) {
  const update = (patch: Partial<PostVisitData>) => onChange({ ...data, ...patch })

  if (readOnly) {
    const hasData = data.satisfaction_level || data.purchase_intent ||
      (data.cross_brand_interest && data.cross_brand_interest.length > 0) ||
      data.decision_maker_met || data.budget_range || data.next_steps

    if (!hasData) return null

    return (
      <div className="rounded-lg border border-green-200 bg-green-50/30 p-3 space-y-2">
        <h3 className="text-sm font-semibold flex items-center gap-1.5 text-green-700">
          <ClipboardCheck className="h-4 w-4" />
          Post-Vizita
        </h3>
        <div className="grid grid-cols-2 gap-2 text-sm">
          {data.satisfaction_level != null && (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Satisfactie: </span>
              <SatisfactionStars value={data.satisfaction_level} onChange={() => {}} readOnly />
            </div>
          )}
          {data.purchase_intent && (
            <div><span className="text-muted-foreground">Intentie achizitie: </span><span className="font-medium">{PURCHASE_INTENT_LABELS[data.purchase_intent] || data.purchase_intent}</span></div>
          )}
          {data.cross_brand_interest && data.cross_brand_interest.length > 0 && (
            <div className="col-span-2"><span className="text-muted-foreground">Interes cross-brand: </span><span className="font-medium">{data.cross_brand_interest.join(', ')}</span></div>
          )}
          {data.competitor_vehicles_seen && data.competitor_vehicles_seen.length > 0 && (
            <div className="col-span-2"><span className="text-muted-foreground">Vehicule concurenta: </span><span className="font-medium">{data.competitor_vehicles_seen.join(', ')}</span></div>
          )}
          {data.decision_maker_met && (
            <div><span className="text-muted-foreground">Decision maker: </span><span className="font-medium">{data.decision_maker_name || 'Da'}</span></div>
          )}
          {data.budget_range && (
            <div><span className="text-muted-foreground">Buget: </span><span className="font-medium">{data.budget_range}</span></div>
          )}
          {data.preferred_financing && (
            <div><span className="text-muted-foreground">Finantare preferata: </span><span className="font-medium">{data.preferred_financing}</span></div>
          )}
          {data.timeline_to_purchase && (
            <div><span className="text-muted-foreground">Termen achizitie: </span><span className="font-medium">{data.timeline_to_purchase}</span></div>
          )}
        </div>
        {data.next_steps && (
          <div className="text-sm"><span className="text-muted-foreground">Pasi urmatori: </span><span className="font-medium">{data.next_steps}</span></div>
        )}
        {data.notes && (
          <div className="text-sm"><span className="text-muted-foreground">Note: </span><span className="font-medium">{data.notes}</span></div>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-green-200 bg-green-50/30 p-3 space-y-3">
      <h3 className="text-sm font-semibold flex items-center gap-1.5 text-green-700">
        <ClipboardCheck className="h-4 w-4" />
        Post-Vizita
      </h3>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Nivel satisfactie client *</Label>
          <SatisfactionStars value={data.satisfaction_level} onChange={v => update({ satisfaction_level: v })} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Intentie achizitie *</Label>
          <Select value={data.purchase_intent || '_none'} onValueChange={v => update({ purchase_intent: v === '_none' ? undefined : v })}>
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Selecteaza..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_none">— Selecteaza —</SelectItem>
              {Object.entries(PURCHASE_INTENT_LABELS).map(([k, v]) => (
                <SelectItem key={k} value={k}>{v}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Interes cross-brand</Label>
        <div className="flex flex-wrap gap-2">
          {BRAND_OPTIONS.map(brand => {
            const checked = (data.cross_brand_interest || []).includes(brand)
            return (
              <label key={brand} className="flex items-center gap-1 text-xs cursor-pointer">
                <Checkbox
                  checked={checked}
                  onCheckedChange={v => {
                    const current = data.cross_brand_interest || []
                    update({
                      cross_brand_interest: v
                        ? [...current, brand]
                        : current.filter(b => b !== brand),
                    })
                  }}
                />
                {brand}
              </label>
            )
          })}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Vehicule concurenta observate</Label>
        <Input
          value={(data.competitor_vehicles_seen || []).join(', ')}
          onChange={e => update({ competitor_vehicles_seen: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
          placeholder="ex: VW Tiguan, Mercedes GLC"
          className="h-9"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Decision maker intalnit?</Label>
          <div className="flex items-center gap-2">
            <Checkbox
              checked={!!data.decision_maker_met}
              onCheckedChange={v => update({ decision_maker_met: !!v })}
            />
            <span className="text-sm">Da</span>
          </div>
        </div>
        {data.decision_maker_met && (
          <div className="space-y-1.5">
            <Label className="text-xs">Nume decision maker</Label>
            <Input
              value={data.decision_maker_name || ''}
              onChange={e => update({ decision_maker_name: e.target.value })}
              className="h-9"
            />
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Buget estimat</Label>
          <Input
            value={data.budget_range || ''}
            onChange={e => update({ budget_range: e.target.value })}
            placeholder="ex: 30.000-50.000 EUR"
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Finantare preferata</Label>
          <Select value={data.preferred_financing || '_none'} onValueChange={v => update({ preferred_financing: v === '_none' ? undefined : v })}>
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Selecteaza..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="_none">— Selecteaza —</SelectItem>
              {FINANCING_OPTIONS.map(f => (
                <SelectItem key={f} value={f}>{f}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Termen estimat achizitie</Label>
        <Input
          value={data.timeline_to_purchase || ''}
          onChange={e => update({ timeline_to_purchase: e.target.value })}
          placeholder="ex: 3 luni, Q3 2026"
          className="h-9"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Pasi urmatori</Label>
        <Textarea
          value={data.next_steps || ''}
          onChange={e => update({ next_steps: e.target.value })}
          rows={2}
          className="text-sm"
          placeholder="Ce urmeaza dupa vizita..."
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Note post-vizita</Label>
        <Textarea
          value={data.notes || ''}
          onChange={e => update({ notes: e.target.value })}
          rows={2}
          className="text-sm"
          placeholder="Observatii suplimentare..."
        />
      </div>
    </div>
  )
}
