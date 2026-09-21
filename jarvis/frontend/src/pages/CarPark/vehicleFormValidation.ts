import { validateListPriceOnCreate } from './vehicleFormPricing'

// Required fields for saving a vehicle, so the editor can tell the user exactly
// what is missing (and which tab to fix) instead of firing a doomed request that
// comes back as a generic 500 (e.g. NOT NULL violation on `category`).

export type MissingField = { label: string; tab: string }

const filled = (v: unknown) => v != null && String(v).trim() !== ''

export function findMissingRequiredFields(
  form: Record<string, unknown>,
  isEdit: boolean,
): MissingField[] {
  const missing: MissingField[] = []
  if (!filled(form.vin) || String(form.vin).trim().length < 5) {
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
