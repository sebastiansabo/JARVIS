import { validateListPriceOnCreate } from './vehicleFormPricing'
import { CATEGORY_LABELS } from '@/types/carpark'

// ── Stock-type (category) helpers ──────────────────────────────────────────

// Custody-type stock: the dealer holds the car but never bought it (Custodie,
// Consemnație), so the whole Achiziție (purchase cost) section is irrelevant —
// hidden in the form and nulled on save. TI (Trade-In) is a real purchase, so
// it is NOT custody.
const CUSTODY_CATEGORIES = new Set(['CUS', 'CON'])
export const isCustodyCategory = (category: unknown): boolean =>
  CUSTODY_CATEGORIES.has(String(category ?? '').trim().toUpperCase())

// Fold Romanian diacritics for tolerant label matching.
const _foldRo = (s: string) =>
  s.trim().toLowerCase().replace(/ă|â/g, 'a').replace(/î/g, 'i')
    .replace(/ș|ş/g, 's').replace(/ț|ţ/g, 't')

const _CATEGORY_CODES = new Set(Object.keys(CATEGORY_LABELS))
// Romanian label (folded) -> canonical code, built from CATEGORY_LABELS + a few
// common spelling variants seen in imported/legacy data.
const _CATEGORY_LABEL_TO_CODE: Record<string, string> = {
  ...Object.fromEntries(
    Object.entries(CATEGORY_LABELS).map(([code, label]) => [_foldRo(label), code]),
  ),
  consignatie: 'CON', consignative: 'CON',
  'trade in': 'TI', tradein: 'TI',
}

// Resolve a stored category into a canonical dropdown code. carpark_vehicles can
// hold a code ('CUS'), a Romanian label ('Custodie') or legacy text — pushing a
// label into the <Select> showed a blank "Tip stoc" on Edit (no matching option),
// forcing a manual re-pick every time. A code passes through; a known label maps
// to its code; anything else is kept verbatim (the Select shows it as a fallback
// option) so a value is never silently dropped. Blank stays blank.
export function normalizeCategory(stored: unknown): string {
  const raw = String(stored ?? '').trim()
  if (!raw) return ''
  const upper = raw.toUpperCase()
  if (_CATEGORY_CODES.has(upper)) return upper
  return _CATEGORY_LABEL_TO_CODE[_foldRo(raw)] ?? raw
}

// Purchase cost-basis fields nulled when the car is custody-type (Achiziție
// hidden) so no stale supplier/price/VAT lingers on a car that was never bought.
export const CUSTODY_CLEARED_FIELDS = [
  'supplier_name', 'supplier_cif', 'acquisition_document_number',
  'acquisition_price', 'purchase_price_net', 'acquisition_vat',
  'acquisition_value', 'acquisition_exchange_rate', 'cost_lines',
] as const

export function clearAcquisitionFields<T extends Record<string, unknown>>(payload: T): T {
  const out: Record<string, unknown> = { ...payload }
  for (const f of CUSTODY_CLEARED_FIELDS) out[f] = null
  return out as T
}

// Required fields for saving a vehicle, so the editor can tell the user exactly
// what is missing (and which tab to fix) instead of firing a doomed request that
// comes back as a generic 500 (e.g. NOT NULL violation on `category`).

export type MissingField = { label: string; tab: string }

const filled = (v: unknown) => v != null && String(v).trim() !== ''

// ISO-3779 VIN: 17 chars, excludes I/O/Q. Mirrors the backend create-time check
// in vehicle_repository (`^[A-HJ-NPR-Z0-9]{17}$`) so an invalid VIN is caught in
// the form with a clear message instead of firing a request that comes back as a
// generic 500. Validated case-insensitively (the VIN is upper-cased on save).
const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/
export const isValidVin = (v: unknown) => VIN_RE.test(String(v ?? '').trim().toUpperCase())

export function findMissingRequiredFields(
  form: Record<string, unknown>,
  isEdit: boolean,
): MissingField[] {
  const missing: MissingField[] = []
  // On create the backend enforces a full 17-char ISO VIN; on edit it does not
  // re-validate (and legacy/imported cars may have imperfect VINs), so stay
  // lenient there to avoid blocking edits of existing vehicles.
  if (!isEdit) {
    if (!isValidVin(form.vin)) {
      missing.push({ label: 'VIN (17 caractere, ISO 3779)', tab: 'vehicul' })
    }
  } else if (!filled(form.vin) || String(form.vin).trim().length < 5) {
    missing.push({ label: 'VIN (minim 5 caractere)', tab: 'vehicul' })
  }
  if (!filled(form.brand)) missing.push({ label: 'Marcă', tab: 'vehicul' })
  if (!filled(form.model)) missing.push({ label: 'Model', tab: 'vehicul' })
  if (!filled(form.category)) missing.push({ label: 'Tip stoc (categorie)', tab: 'vehicul' })
  // Preț listă is mandatory only when adding a car (reuses the shared rule).
  if (validateListPriceOnCreate(form as { list_price?: unknown }, isEdit)) {
    missing.push({ label: 'Preț listă', tab: 'comercial' })
  }
  return missing
}
