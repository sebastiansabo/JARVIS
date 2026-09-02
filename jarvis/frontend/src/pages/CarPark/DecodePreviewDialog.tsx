import { Check, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { VINDecodeResult } from '@/types/carpark'
import {
  AUTOVIT_FUEL_TYPES,
  AUTOVIT_GEARBOX_TYPES,
  AUTOVIT_BODY_TYPES,
  AUTOVIT_DRIVE_TYPES,
  AUTOVIT_COLORS,
  AUTOVIT_EURO_STANDARDS,
  AUTOVIT_DOORS,
  AUTOVIT_SEATS,
} from '@/data/autovitData'

// Which VehicleForm tab each decoder-produced field lands on, plus the label
// the form shows for it. `other` covers keys that get merged into form state
// but have no visible input (e.g. engine_power_kw) — surfaced so nothing is
// applied silently.
type Options = readonly { value: string; label: string }[]
type TabKey = 'vehicul' | 'specificatii' | 'other'

interface FieldMeta {
  label: string
  tab: TabKey
  options?: Options
}

const TAB_LABELS: Record<TabKey, string> = {
  vehicul: 'Vehicul',
  specificatii: 'Specificații',
  other: 'Alte câmpuri (fără câmp vizibil)',
}
const TAB_ORDER: TabKey[] = ['vehicul', 'specificatii', 'other']

// Covers the union of both decoders' outputs — CIV (routes/vin.py::decode_civ)
// and VIN decode (connectors/vin_decoder .to_vehicle_fields()).
const FIELD_META: Record<string, FieldMeta> = {
  vin: { label: 'Serie șasiu (VIN)', tab: 'vehicul' },
  brand: { label: 'Marcă', tab: 'vehicul' },
  model: { label: 'Model', tab: 'vehicul' },
  variant: { label: 'Versiune', tab: 'vehicul' },
  generation: { label: 'Generație', tab: 'vehicul' },
  year_of_manufacture: { label: 'An fabricație', tab: 'vehicul' },
  first_registration_date: { label: 'Prima înmatriculare', tab: 'vehicul' },
  fuel_type: { label: 'Combustibil', tab: 'specificatii', options: AUTOVIT_FUEL_TYPES },
  transmission: { label: 'Cutie de viteze', tab: 'specificatii', options: AUTOVIT_GEARBOX_TYPES },
  body_type: { label: 'Caroserie', tab: 'specificatii', options: AUTOVIT_BODY_TYPES },
  drive_type: { label: 'Tracțiune', tab: 'specificatii', options: AUTOVIT_DRIVE_TYPES },
  engine_power_hp: { label: 'Putere (CP)', tab: 'specificatii' },
  engine_displacement_cc: { label: 'Capacitate cilindrică (cmc)', tab: 'specificatii' },
  color_exterior: { label: 'Culoare exterioară', tab: 'specificatii', options: AUTOVIT_COLORS },
  doors: { label: 'Nr. uși', tab: 'specificatii', options: AUTOVIT_DOORS },
  seats: { label: 'Nr. locuri', tab: 'specificatii', options: AUTOVIT_SEATS },
  euro_standard: { label: 'Normă de poluare', tab: 'specificatii', options: AUTOVIT_EURO_STANDARDS },
  co2_emissions: { label: 'Emisii CO₂ (g/km)', tab: 'specificatii' },
  max_weight_kg: { label: 'Masă maximă (kg)', tab: 'specificatii' },
  engine_power_kw: { label: 'Putere (kW)', tab: 'other' },
  is_electric_vehicle: { label: 'Vehicul electric', tab: 'other' },
}

const isEmpty = (v: unknown) => v === null || v === undefined || v === ''

function resolveLabel(meta: FieldMeta | undefined, value: unknown): string {
  if (isEmpty(value)) return '—'
  if (typeof value === 'boolean') return value ? 'Da' : 'Nu'
  if (meta?.options) {
    const hit = meta.options.find((o) => String(o.value) === String(value))
    if (hit) return hit.label
  }
  return String(value)
}

// Mirror applyDecodedFields: only scalar values (string | number | boolean |
// null) are merged into the form, so the preview shows exactly those.
const isApplied = (v: unknown) =>
  v === null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'

interface Row {
  key: string
  label: string
  tab: TabKey
  current: string
  next: string
  overwrite: boolean
  unchanged: boolean
}

interface DecodePreviewDialogProps {
  result: VINDecodeResult | null
  /** Current form values, to compare current → incoming per field. */
  form: Record<string, unknown>
  onApply: () => void
  onClose: () => void
}

export function DecodePreviewDialog({ result, form, onApply, onClose }: DecodePreviewDialogProps) {
  const fields = (result?.vehicle_fields ?? {}) as Record<string, unknown>
  const rows: Row[] = Object.entries(fields)
    .filter(([, v]) => isApplied(v))
    .map(([key, v]) => {
      const meta = FIELD_META[key]
      const currentRaw = form[key]
      const overwrite = !isEmpty(currentRaw) && String(currentRaw) !== String(v)
      const unchanged = !isEmpty(currentRaw) && String(currentRaw) === String(v)
      return {
        key,
        label: meta?.label ?? key,
        tab: meta?.tab ?? 'other',
        current: resolveLabel(meta, currentRaw),
        next: resolveLabel(meta, v),
        overwrite,
        unchanged,
      }
    })

  return (
    <Dialog open={!!result} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="sm:max-w-[1080px]">
        <DialogHeader>
          <DialogTitle>Verifică datele înainte de aplicare</DialogTitle>
        </DialogHeader>

        {result && (
          <p className="-mt-2 text-xs text-muted-foreground">
            Sursă: {result.provider} &middot; {Math.round(result.confidence * 100)}% &middot;{' '}
            {rows.length} {rows.length === 1 ? 'câmp' : 'câmpuri'}
          </p>
        )}

        <ScrollArea className="max-h-[60vh] pr-3">
          {rows.length === 0 && (
            <p className="text-sm text-muted-foreground">Nu s-au găsit date de aplicat.</p>
          )}
          {TAB_ORDER.map((tab) => {
            const tabRows = rows.filter((r) => r.tab === tab)
            if (tabRows.length === 0) return null
            return (
              <div key={tab} className="mb-4">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {TAB_LABELS[tab]}
                </div>
                <div className="space-y-1">
                  {tabRows.map((r) => (
                    <div
                      key={r.key}
                      className={cn(
                        'flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm',
                        r.overwrite
                          ? 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40'
                          : 'border-transparent',
                      )}
                    >
                      <span className="w-36 shrink-0 text-muted-foreground">{r.label}</span>
                      <span className="flex min-w-0 flex-1 items-center gap-1.5">
                        <span className="truncate text-muted-foreground">{r.current}</span>
                        <span className="shrink-0 text-muted-foreground">→</span>
                        <span className="truncate font-medium">{r.next}</span>
                      </span>
                      {r.overwrite && (
                        <Badge
                          variant="outline"
                          className="shrink-0 border-amber-400 text-amber-700 dark:text-amber-300"
                        >
                          suprascrie
                        </Badge>
                      )}
                      {r.unchanged && (
                        <span className="shrink-0 text-xs text-muted-foreground">fără schimbare</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </ScrollArea>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            <X className="mr-1 h-4 w-4" />
            Anulează
          </Button>
          <Button type="button" onClick={onApply} disabled={rows.length === 0}>
            <Check className="mr-1 h-4 w-4" />
            Aplică datele
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
