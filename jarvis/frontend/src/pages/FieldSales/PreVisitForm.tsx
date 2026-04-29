import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { ClipboardList } from 'lucide-react'
import type { PreVisitData } from '@/api/fieldSales'

interface Props {
  data: PreVisitData
  onChange: (data: PreVisitData) => void
  readOnly?: boolean
}

const ACQUISITION_OPTIONS = [
  { value: 'cash', label: 'Cash' },
  { value: 'leasing', label: 'Leasing' },
  { value: 'credit', label: 'Credit' },
]

export function PreVisitForm({ data, onChange, readOnly }: Props) {
  const update = (patch: Partial<PreVisitData>) => onChange({ ...data, ...patch })

  if (readOnly) {
    const hasData = data.confirmed_contact_person || data.confirmed_address ||
      data.known_fleet_count || data.shareholders_info ||
      (data.acquisition_methods && data.acquisition_methods.length > 0) ||
      (data.visit_objectives && data.visit_objectives.length > 0)

    if (!hasData) return null

    return (
      <div className="rounded-lg border p-3 space-y-2">
        <h3 className="text-sm font-semibold flex items-center gap-1.5">
          <ClipboardList className="h-4 w-4" />
          Pre-Vizita
        </h3>
        <div className="grid grid-cols-2 gap-2 text-sm">
          {data.confirmed_contact_person && (
            <div><span className="text-muted-foreground">Persoana contact: </span><span className="font-medium">{data.confirmed_contact_person}</span></div>
          )}
          {data.confirmed_address && (
            <div><span className="text-muted-foreground">Adresa: </span><span className="font-medium">{data.confirmed_address}</span></div>
          )}
          {data.known_fleet_count != null && data.known_fleet_count > 0 && (
            <div><span className="text-muted-foreground">Flota cunoscuta: </span><span className="font-medium">{data.known_fleet_count} vehicule</span></div>
          )}
          {data.acquisition_methods && data.acquisition_methods.length > 0 && (
            <div><span className="text-muted-foreground">Mod achizitie: </span><span className="font-medium">{data.acquisition_methods.join(', ')}</span></div>
          )}
          {data.shareholders_info && (
            <div className="col-span-2"><span className="text-muted-foreground">Actionari: </span><span className="font-medium">{data.shareholders_info}</span></div>
          )}
          {data.work_points_count != null && data.work_points_count > 0 && (
            <div><span className="text-muted-foreground">Puncte de lucru: </span><span className="font-medium">{data.work_points_count}</span></div>
          )}
          {data.annual_revenue_estimate != null && data.annual_revenue_estimate > 0 && (
            <div><span className="text-muted-foreground">Venit anual estimat: </span><span className="font-medium">{data.annual_revenue_estimate.toLocaleString('ro-RO')} EUR</span></div>
          )}
        </div>
        {data.visit_objectives && data.visit_objectives.length > 0 && (
          <div className="text-sm">
            <span className="text-muted-foreground">Obiective: </span>
            <ul className="list-disc list-inside mt-1">
              {data.visit_objectives.map((o, i) => <li key={i} className="font-medium">{o}</li>)}
            </ul>
          </div>
        )}
        {data.materials_prepared && data.materials_prepared.length > 0 && (
          <div className="text-sm">
            <span className="text-muted-foreground">Materiale pregatite: </span>
            <span className="font-medium">{data.materials_prepared.join(', ')}</span>
          </div>
        )}
        {data.notes && (
          <div className="text-sm"><span className="text-muted-foreground">Note: </span><span className="font-medium">{data.notes}</span></div>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-lg border p-3 space-y-3">
      <h3 className="text-sm font-semibold flex items-center gap-1.5">
        <ClipboardList className="h-4 w-4" />
        Pre-Vizita
      </h3>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Persoana contact *</Label>
          <Input
            value={data.confirmed_contact_person || ''}
            onChange={e => update({ confirmed_contact_person: e.target.value })}
            placeholder="Nume persoana"
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Adresa / Sediu</Label>
          <Input
            value={data.confirmed_address || ''}
            onChange={e => update({ confirmed_address: e.target.value })}
            placeholder="Adresa vizita"
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Flota cunoscuta (nr. vehicule)</Label>
          <Input
            type="number"
            min={0}
            value={data.known_fleet_count ?? ''}
            onChange={e => update({ known_fleet_count: e.target.value ? Number(e.target.value) : undefined })}
            className="h-9"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Puncte de lucru</Label>
          <Input
            type="number"
            min={0}
            value={data.work_points_count ?? ''}
            onChange={e => update({ work_points_count: e.target.value ? Number(e.target.value) : undefined })}
            className="h-9"
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Mod de achizitie</Label>
        <div className="flex gap-4">
          {ACQUISITION_OPTIONS.map(opt => {
            const checked = (data.acquisition_methods || []).includes(opt.value)
            return (
              <label key={opt.value} className="flex items-center gap-1.5 text-sm cursor-pointer">
                <Checkbox
                  checked={checked}
                  onCheckedChange={v => {
                    const current = data.acquisition_methods || []
                    update({
                      acquisition_methods: v
                        ? [...current, opt.value]
                        : current.filter(m => m !== opt.value),
                    })
                  }}
                />
                {opt.label}
              </label>
            )
          })}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Actionari</Label>
        <Input
          value={data.shareholders_info || ''}
          onChange={e => update({ shareholders_info: e.target.value })}
          placeholder="Informatii despre actionari"
          className="h-9"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Venit anual estimat (EUR)</Label>
        <Input
          type="number"
          min={0}
          value={data.annual_revenue_estimate ?? ''}
          onChange={e => update({ annual_revenue_estimate: e.target.value ? Number(e.target.value) : undefined })}
          className="h-9"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Obiective vizita</Label>
        <Textarea
          value={(data.visit_objectives || []).join('\n')}
          onChange={e => update({ visit_objectives: e.target.value.split('\n').filter(Boolean) })}
          placeholder="Un obiectiv pe linie"
          rows={3}
          className="text-sm"
        />
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Note pre-vizita</Label>
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
