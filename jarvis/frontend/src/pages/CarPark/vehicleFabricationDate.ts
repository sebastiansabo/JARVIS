// "Data fabricației" is entered as Month + Year dropdowns but stored as
// manufacture_date = YYYY-MM-01. These helpers convert between the two, extracted
// from VehicleForm so the round-trip is unit-testable.
//
// Hydration guard: Autovit/VIN-imported cars have no manufacture_date but DO have
// year_of_manufacture, so the year selector must fall back to it. Without this,
// the year rendered blank and picking a month would rewrite year_of_manufacture
// to the current year (silent corruption).

export type FabParts = { month: string; year: string }

/** Month ('MM' or '') + year ('YYYY' or '') to show in the fab-date selectors. */
export function deriveFabParts(
  manufactureDate?: string | null,
  yearOfManufacture?: number | null,
): FabParts {
  const md = manufactureDate ?? ''
  const month = md.slice(5, 7)
  const year = md.slice(0, 4) || (yearOfManufacture != null ? String(yearOfManufacture) : '')
  return { month, year }
}

/**
 * Build the stored pair from the selected month + year. Month defaults to January
 * when unset; the year is used verbatim (the caller resolves any fallback), so a
 * known year is never silently reset.
 */
export function fabToManufactureDate(
  month: string,
  year: string,
): { manufacture_date: string; year_of_manufacture: number } {
  const m = month || '01'
  return { manufacture_date: `${year}-${m}-01`, year_of_manufacture: Number(year) }
}
