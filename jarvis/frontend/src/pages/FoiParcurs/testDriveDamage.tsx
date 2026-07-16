import { useState } from 'react'
import { ImagePlus, X, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { fileToCompressedDataUrl } from '@/lib/imageCompress'
import type { TdDamageItem } from '@/types/foiParcurs'

// Shared structured-damage model for the Test Drive flow — the departure form
// (New/TestDriveForm → departure_damage) captures the same 7 fixed zones ×
// severity + optional per-zone photos as the return form. Ported from the
// mobile app's TestDrive/damage.tsx so both platforms stay in sync.

export const DAMAGE_ZONES = [
  'Față',
  'Spate',
  'Lateral stânga',
  'Lateral dreapta',
  'Plafon',
  'Roți / Jante',
  'Interior',
] as const
export type DamageZone = (typeof DAMAGE_ZONES)[number]

export const SEVERITY_LABELS = ['Fără', 'Minor', 'Mediu', 'Grav'] as const
export type SeverityLabel = (typeof SEVERITY_LABELS)[number]

/** Romanian UI labels → the API severity enum stored in the JSONB column. */
export const SEVERITY_API: Record<Exclude<SeverityLabel, 'Fără'>, TdDamageItem['severity']> = {
  Minor: 'minor',
  Mediu: 'moderate',
  Grav: 'severe',
}

/** Max photos kept per zone — keeps the embedded-base64 payload bounded. */
export const MAX_PHOTOS_PER_ZONE = 6

export type DamageState = Record<DamageZone, { severity: SeverityLabel; note: string; photos: string[] }>

/** Fresh, all-"Fără" damage state. A factory so each caller gets its own object. */
export function makeEmptyDamageState(): DamageState {
  return Object.fromEntries(
    DAMAGE_ZONES.map((zone) => [zone, { severity: 'Fără' as SeverityLabel, note: '', photos: [] as string[] }]),
  ) as DamageState
}

const API_SEVERITY_TO_LABEL: Record<TdDamageItem['severity'], SeverityLabel> = {
  minor: 'Minor',
  moderate: 'Mediu',
  severe: 'Grav',
}

/** Rebuilds a DamageState from a stored API damage list (e.g. to pre-fill a new
 *  drive from the same car's last one). Photos are dropped — the new drive
 *  documents its own. */
export function fromDamagePayload(items?: TdDamageItem[] | null): DamageState {
  const state = makeEmptyDamageState()
  if (!Array.isArray(items)) return state
  for (const it of items) {
    const zone = it?.zone as DamageZone
    const label = it && API_SEVERITY_TO_LABEL[it.severity]
    if ((DAMAGE_ZONES as readonly string[]).includes(zone) && label) {
      state[zone] = { severity: label, note: it.note ?? '', photos: [] }
    }
  }
  return state
}

/** Collapses the per-zone state into the compact API list (only zones with an
 *  actual severity; notes/photos trimmed or omitted when empty). */
export function toDamagePayload(damage: DamageState): TdDamageItem[] {
  return DAMAGE_ZONES.filter((zone) => damage[zone].severity !== 'Fără').map((zone) => {
    const { severity, note, photos } = damage[zone]
    const item: TdDamageItem = {
      zone,
      severity: SEVERITY_API[severity as Exclude<SeverityLabel, 'Fără'>],
    }
    if (note.trim()) item.note = note.trim()
    if (photos.length) item.photos = photos
    return item
  })
}

/** Active-pill colour per severity — green (none) → amber → orange → red. */
const SEVERITY_ACTIVE_CLASS: Record<SeverityLabel, string> = {
  Fără: 'bg-emerald-500 text-white shadow-sm',
  Minor: 'bg-amber-500 text-white shadow-sm',
  Mediu: 'bg-orange-500 text-white shadow-sm',
  Grav: 'bg-red-500 text-white shadow-sm',
}

function SeveritySegmentedControl({
  value,
  onChange,
}: {
  value: SeverityLabel
  onChange: (v: SeverityLabel) => void
}) {
  return (
    <div className="grid grid-cols-4 gap-1 h-10 rounded-lg bg-secondary p-1">
      {SEVERITY_LABELS.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={cn(
            'flex items-center justify-center rounded-md text-[13px] font-semibold transition-colors',
            value === opt ? SEVERITY_ACTIVE_CLASS[opt] : 'text-muted-foreground',
          )}
        >
          {opt}
        </button>
      ))}
    </div>
  )
}

/** File-upload photo strip for one damaged zone (desktop-friendly: choose image
 *  files). Selected images are downscaled/compressed to base64 JPEG. */
function ZonePhotos({
  photos,
  onChange,
}: {
  photos: string[]
  onChange: (next: string[]) => void
}) {
  const [busy, setBusy] = useState(false)

  const handleFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (!files.length) return
    setBusy(true)
    const room = MAX_PHOTOS_PER_ZONE - photos.length
    const compressed = (
      await Promise.all(files.slice(0, room).map((f) => fileToCompressedDataUrl(f)))
    ).filter((p): p is string => !!p)
    setBusy(false)
    if (compressed.length) onChange([...photos, ...compressed])
  }

  const removeAt = (idx: number) => onChange(photos.filter((_, i) => i !== idx))

  return (
    <div className="flex flex-wrap gap-2">
      {photos.map((src, i) => (
        <div key={i} className="relative h-16 w-16">
          <img src={src} alt={`Avarie ${i + 1}`} className="h-16 w-16 rounded-md object-cover border" />
          <button
            type="button"
            onClick={() => removeAt(i)}
            aria-label="Șterge poza"
            className="absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-white shadow"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}
      {photos.length < MAX_PHOTOS_PER_ZONE && (
        <label className="flex h-16 w-16 cursor-pointer flex-col items-center justify-center gap-0.5 rounded-md border-2 border-dashed text-muted-foreground hover:bg-accent transition-colors">
          {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <ImagePlus className="h-5 w-5" />}
          <span className="text-[10px] font-medium">Poză</span>
          <input type="file" accept="image/*" multiple className="hidden" onChange={handleFiles} />
        </label>
      )}
    </div>
  )
}

/** Per-zone damage capture UI (severity segmented control + optional note and
 *  photos once a severity is set). Controlled via a DamageState. */
export function DamageReport({
  value,
  onChange,
}: {
  value: DamageState
  onChange: (next: DamageState) => void
}) {
  const setSeverity = (zone: DamageZone, severity: SeverityLabel) =>
    onChange({ ...value, [zone]: { ...value[zone], severity } })
  const setNote = (zone: DamageZone, note: string) =>
    onChange({ ...value, [zone]: { ...value[zone], note } })
  const setPhotos = (zone: DamageZone, photos: string[]) =>
    onChange({ ...value, [zone]: { ...value[zone], photos } })

  return (
    <div className="space-y-2.5">
      {DAMAGE_ZONES.map((zone) => (
        <div key={zone} className="space-y-2 rounded-lg border bg-card p-3">
          <span className="text-sm font-semibold">{zone}</span>
          <SeveritySegmentedControl value={value[zone].severity} onChange={(sev) => setSeverity(zone, sev)} />
          {value[zone].severity !== 'Fără' && (
            <>
              <Input
                type="text"
                value={value[zone].note}
                onChange={(e) => setNote(zone, e.target.value)}
                placeholder="Notă (opțional)"
              />
              <ZonePhotos photos={value[zone].photos} onChange={(next) => setPhotos(zone, next)} />
            </>
          )}
        </div>
      ))}
    </div>
  )
}
