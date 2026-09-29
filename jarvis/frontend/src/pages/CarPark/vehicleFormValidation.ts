import { validateListPriceOnCreate } from './vehicleFormPricing'

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
