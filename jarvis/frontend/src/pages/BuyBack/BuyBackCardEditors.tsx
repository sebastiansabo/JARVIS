import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import { buybackApi } from '@/api/buyback'
import type { BuybackRecord } from '@/types/buyback'
import { AUTOVIT_BRANDS, AUTOVIT_MODELS, AUTOVIT_EQUIPMENT } from '@/data/autovitData'
import { Autocomplete } from '@/components/shared/Autocomplete'
import { cn } from '@/lib/utils'
import { CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

// VIN validity — mirrors the intake form + backend VIN_RE (17 chars, no I/O/Q).
const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/
const EMPTY_STRINGS: string[] = []

type OptItem = { value: string; label: string }
export interface LookupOpts {
  fuel_types?: OptItem[]
  transmissions?: OptItem[]
  gearboxes?: OptItem[]
  client_types?: OptItem[]
  vat_statuses?: OptItem[]
}

// ── Payload coercion ──────────────────────────────────────────────────────
// Empties become null (not ''): the backend's validate_intake rejects '' for
// numeric/date fields, and null lets a field be cleared. Unchanged nulls stay
// null, so the server-side diff doesn't record a spurious change.
const strOrNull = (v: string | null | undefined): string | null => {
  const s = String(v ?? '').trim()
  return s ? s : null
}
const numOrNull = (v: string | number | null | undefined): number | null => {
  const s = String(v ?? '').trim()
  if (!s) return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

interface EditorProps {
  record: BuybackRecord
  opts?: LookupOpts
  onClose: () => void
}

// Shared save mutation: PUT the card's fields, then refetch the record (which
// also carries the updated events → the "Istoric" timeline). The backend logs
// a 'record_edited' event listing the fields that actually changed.
function useCardSave(recordId: number, onClose: () => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<BuybackRecord>) =>
      buybackApi.updateRecord(recordId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buyback-record', recordId] })
      qc.invalidateQueries({ queryKey: ['buyback-records'] })
      toast.success('Modificările au fost salvate')
      onClose()
    },
    onError: (e: unknown) =>
      toast.error(
        (e as { data?: { error?: string } })?.data?.error || 'Salvarea a eșuat',
      ),
  })
}

function SaveBar({ pending, disabled, onSave, onCancel }: { pending: boolean; disabled?: boolean; onSave: () => void; onCancel: () => void }) {
  return (
    <div className="flex justify-end gap-2 pt-1">
      <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={pending}>
        Anulează
      </Button>
      <Button type="button" size="sm" onClick={onSave} disabled={pending || disabled}>
        {pending && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />}
        Salvează
      </Button>
    </div>
  )
}

// ── Vehicul card editor ───────────────────────────────────────────────────
export function VehicleCardEditor({ record, opts, onClose }: EditorProps) {
  const [form, setForm] = useState({
    brand: record.brand ?? '',
    model: record.model ?? '',
    variant: record.variant ?? '',
    equipment: record.equipment ?? '',
    vin: record.vin ?? '',
    mileage_km: record.mileage_km ?? '',
    engine_capacity_cm3: record.engine_capacity_cm3 ?? '',
    fuel_type: record.fuel_type ?? '',
    transmission: record.transmission ?? '',
    gearbox: record.gearbox ?? '',
    manufacture_date: record.manufacture_date ?? '',
    first_registration_date: record.first_registration_date ?? '',
    service_history_uptodate: !!record.service_history_uptodate,
    extra_wheels: !!record.extra_wheels,
    keys_count: record.keys_count ?? '',
    general_condition: record.general_condition ?? '',
    has_damage: !!record.has_damage,
    damage_details: record.damage_details ?? '',
  })
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }))
  const save = useCardSave(record.id, onClose)

  const selectedEquipment = useMemo(
    () => new Set((form.equipment || '').split(',').map((s) => s.trim()).filter(Boolean)),
    [form.equipment],
  )
  const toggleEquipment = (value: string) => {
    const next = new Set(selectedEquipment)
    next.has(value) ? next.delete(value) : next.add(value)
    set('equipment', Array.from(next).join(', '))
  }

  const vinValue = form.vin.trim().toUpperCase()
  const vinValid = VIN_RE.test(vinValue)
  const canSave = form.brand.trim() !== '' && form.model.trim() !== '' && vinValid

  function submit() {
    if (save.isPending || !canSave) return
    save.mutate({
      brand: form.brand.trim(),
      model: form.model.trim(),
      variant: strOrNull(form.variant),
      equipment: strOrNull(form.equipment),
      vin: vinValue,
      mileage_km: numOrNull(form.mileage_km),
      engine_capacity_cm3: numOrNull(form.engine_capacity_cm3),
      fuel_type: strOrNull(form.fuel_type),
      transmission: strOrNull(form.transmission),
      gearbox: strOrNull(form.gearbox),
      manufacture_date: strOrNull(form.manufacture_date),
      first_registration_date: strOrNull(form.first_registration_date),
      service_history_uptodate: form.service_history_uptodate,
      extra_wheels: form.extra_wheels,
      keys_count: numOrNull(form.keys_count),
      general_condition: numOrNull(form.general_condition),
      has_damage: form.has_damage,
      damage_details: form.has_damage ? strOrNull(form.damage_details) : null,
    } as Partial<BuybackRecord>)
  }

  return (
    <CardContent className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Marca *</Label>
          <Autocomplete
            value={form.brand}
            onChange={(v) => set('brand', v)}
            onSelect={(v) => set('brand', v)}
            options={AUTOVIT_BRANDS as unknown as string[]}
            placeholder="BMW"
            allowCreate
            canonicalize
            invalid={!form.brand.trim()}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Model *</Label>
          <Autocomplete
            value={form.model}
            onChange={(v) => set('model', v)}
            onSelect={(v) => set('model', v)}
            options={AUTOVIT_MODELS[form.brand] ?? EMPTY_STRINGS}
            placeholder="320d"
            allowCreate
            canonicalize
            invalid={!form.model.trim()}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Varianta</Label>
          <Input value={form.variant} onChange={(e) => set('variant', e.target.value)} placeholder="Touring..." />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">VIN *</Label>
          <Input
            className={cn(!vinValid && 'border-destructive')}
            value={form.vin}
            onChange={(e) => set('vin', e.target.value.toUpperCase())}
            placeholder="17 caractere, fără I/O/Q"
            maxLength={17}
          />
          {!vinValid && <p className="text-xs text-destructive">VIN invalid — 17 caractere (fără I, O, Q).</p>}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">
          Echipare{selectedEquipment.size > 0 && <span className="text-muted-foreground"> · {selectedEquipment.size} selectate</span>}
        </Label>
        <div className="rounded-md border bg-muted/20 p-3 space-y-3 max-h-56 overflow-y-auto">
          {AUTOVIT_EQUIPMENT.map((group) => (
            <div key={group.category} className="space-y-2">
              <h4 className="text-[11px] font-semibold uppercase text-muted-foreground">{group.category}</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
                {group.options.map((opt) => (
                  <div key={opt.value} className="flex items-center gap-2">
                    <Checkbox
                      id={`eq-edit-${opt.value}`}
                      checked={selectedEquipment.has(opt.value)}
                      onCheckedChange={() => toggleEquipment(opt.value)}
                    />
                    <Label htmlFor={`eq-edit-${opt.value}`} className="text-sm font-normal cursor-pointer">{opt.label}</Label>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Rulaj (km)</Label>
          <Input type="number" inputMode="numeric" min={0} value={form.mileage_km} onChange={(e) => set('mileage_km', e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Capacitate cilindrică (cm³)</Label>
          <Input type="number" inputMode="numeric" min={0} value={form.engine_capacity_cm3} onChange={(e) => set('engine_capacity_cm3', e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Combustibil</Label>
          <Select value={form.fuel_type || undefined} onValueChange={(v) => set('fuel_type', v)}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Alege" /></SelectTrigger>
            <SelectContent>
              {(opts?.fuel_types ?? []).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Transmisie</Label>
          <Select value={form.transmission || undefined} onValueChange={(v) => set('transmission', v)}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Alege" /></SelectTrigger>
            <SelectContent>
              {(opts?.transmissions ?? []).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Cutie de viteze</Label>
          <Select value={form.gearbox || undefined} onValueChange={(v) => set('gearbox', v)}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Alege" /></SelectTrigger>
            <SelectContent>
              {(opts?.gearboxes ?? []).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Nr. chei</Label>
          <Input type="number" inputMode="numeric" min={0} value={form.keys_count} onChange={(e) => set('keys_count', e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Data fabricație</Label>
          <Input type="date" value={form.manufacture_date} onChange={(e) => set('manufacture_date', e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Data prima înmatriculare</Label>
          <Input type="date" value={form.first_registration_date} onChange={(e) => set('first_registration_date', e.target.value)} />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="flex items-center justify-between rounded-md border p-2.5">
          <Label className="text-xs">Istoric service la zi</Label>
          <Switch checked={form.service_history_uptodate} onCheckedChange={(v) => set('service_history_uptodate', v)} />
        </div>
        <div className="flex items-center justify-between rounded-md border p-2.5">
          <Label className="text-xs">Roți extra</Label>
          <Switch checked={form.extra_wheels} onCheckedChange={(v) => set('extra_wheels', v)} />
        </div>
        <div className="flex items-center justify-between rounded-md border p-2.5">
          <Label className="text-xs">Daune</Label>
          <Switch checked={form.has_damage} onCheckedChange={(v) => set('has_damage', v)} />
        </div>
      </div>

      {form.has_damage && (
        <div className="space-y-1.5">
          <Label className="text-xs">Detalii daune</Label>
          <Textarea value={form.damage_details} onChange={(e) => set('damage_details', e.target.value)} rows={2} />
        </div>
      )}

      <div className="space-y-1.5">
        <Label className="text-xs">Condiție generală (1-5)</Label>
        <div className="grid h-11 grid-cols-5 gap-1 rounded-lg bg-secondary p-1">
          {[1, 2, 3, 4, 5].map((n) => {
            const active = String(form.general_condition) === String(n)
            return (
              <button
                key={n}
                type="button"
                onClick={() => set('general_condition', n)}
                className={cn('rounded-md text-sm font-medium transition-colors', active ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground')}
              >
                {n}
              </button>
            )
          })}
        </div>
      </div>

      <SaveBar pending={save.isPending} disabled={!canSave} onSave={submit} onCancel={onClose} />
    </CardContent>
  )
}

// ── Vânzător & Trade-in card editor ───────────────────────────────────────
export function SellerCardEditor({ record, opts, onClose }: EditorProps) {
  const [form, setForm] = useState({
    client_type: record.client_type ?? '',
    vat_status: record.vat_status ?? '',
    seller_name: record.seller_name ?? '',
    seller_email: record.seller_email ?? '',
    seller_phone: record.seller_phone ?? '',
    seller_cui: record.seller_cui ?? '',
    is_trade_in: !!record.is_trade_in,
    target_vehicle_text: record.target_vehicle_text ?? '',
  })
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }))
  const save = useCardSave(record.id, onClose)

  function submit() {
    if (save.isPending) return
    save.mutate({
      client_type: strOrNull(form.client_type),
      vat_status: strOrNull(form.vat_status),
      seller_name: strOrNull(form.seller_name),
      seller_email: strOrNull(form.seller_email),
      seller_phone: strOrNull(form.seller_phone),
      seller_cui: strOrNull(form.seller_cui),
      is_trade_in: form.is_trade_in,
      target_vehicle_text: form.is_trade_in ? strOrNull(form.target_vehicle_text) : null,
    } as Partial<BuybackRecord>)
  }

  return (
    <CardContent className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">Tip client</Label>
          <Select value={form.client_type || undefined} onValueChange={(v) => set('client_type', v)}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Alege" /></SelectTrigger>
            <SelectContent>
              {(opts?.client_types ?? []).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Status TVA</Label>
          <Select value={form.vat_status || undefined} onValueChange={(v) => set('vat_status', v)}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Alege" /></SelectTrigger>
            <SelectContent>
              {(opts?.vat_statuses ?? []).map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Nume</Label>
          <Input value={form.seller_name} onChange={(e) => set('seller_name', e.target.value)} placeholder="Nume și prenume" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Telefon</Label>
          <Input value={form.seller_phone} onChange={(e) => set('seller_phone', e.target.value)} placeholder="0721 234 567" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Email</Label>
          <Input value={form.seller_email} onChange={(e) => set('seller_email', e.target.value)} placeholder="email@exemplu.ro" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">CUI</Label>
          <Input value={form.seller_cui} onChange={(e) => set('seller_cui', e.target.value)} placeholder="CUI (dacă firmă)" />
        </div>
      </div>

      <div className="flex items-center justify-between rounded-md border p-2.5">
        <Label className="text-xs">Trade-in</Label>
        <Switch checked={form.is_trade_in} onCheckedChange={(v) => set('is_trade_in', v)} />
      </div>
      {form.is_trade_in && (
        <div className="space-y-1.5">
          <Label className="text-xs">Vehicul dorit (text liber)</Label>
          <Input value={form.target_vehicle_text} onChange={(e) => set('target_vehicle_text', e.target.value)} placeholder="ex: Renault Clio 2022" />
        </div>
      )}

      <SaveBar pending={save.isPending} onSave={submit} onCancel={onClose} />
    </CardContent>
  )
}
