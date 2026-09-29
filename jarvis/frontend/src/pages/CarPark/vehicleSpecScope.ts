// Which technical-spec fields apply to a given fuel_type / body_type, and which
// should be nulled on save. Extracted from VehicleForm's submit handler so the
// clearing rules are unit-testable and can't silently wipe data.
//
// Data-loss guard: a spec group is cleared ONLY when the fuel_type / body_type is
// a RECOGNIZED taxonomy value that legitimately excludes it. An empty or unmapped
// value clears nothing — so an Autovit/VIN-imported car with a blank/unknown
// fuel_type never has its consumption/tank/battery specs erased when re-saved.
import { AUTOVIT_FUEL_TYPES, AUTOVIT_BODY_TYPES } from '../../data/autovitData'

// Combustion fuels have a fuel tank + consumption/emission norms. Only a pure EV
// has none — ethanol, CNG, LPG, hydrogen and every (mild-)hybrid keep the tank.
const FUEL_USES_TANK = new Set<string>([
  'petrol', 'diesel', 'hybrid', 'plugin-hybrid',
  'mild-hybrid-petrol', 'mild-hybrid-diesel',
  'petrol-lpg', 'petrol-cng', 'hydrogen', 'ethanol',
])
// Traction battery + kWh norms. Mild hybrids deliberately excluded.
const FUEL_USES_BATTERY = new Set<string>(['electric', 'hybrid', 'plugin-hybrid'])
// Body types that legitimately carry cargo/payload specs (kept broad on purpose
// so people-carriers/utilities aren't stripped — only clear for plain cars).
const BODY_USES_CARGO = new Set<string>(['van', 'pickup', 'minibus', 'minivan'])

const KNOWN_FUEL_TYPES = new Set<string>(AUTOVIT_FUEL_TYPES.map((f) => f.value))
const KNOWN_BODY_TYPES = new Set<string>(AUTOVIT_BODY_TYPES.map((b) => b.value))

export const usesFuelTank = (ft?: string | null) => FUEL_USES_TANK.has(ft ?? '')
export const usesBattery = (ft?: string | null) => FUEL_USES_BATTERY.has(ft ?? '')
export const usesCargo = (bt?: string | null) => BODY_USES_CARGO.has(bt ?? '')
export const isKnownFuelType = (ft?: string | null) => KNOWN_FUEL_TYPES.has(ft ?? '')
export const isKnownBodyType = (bt?: string | null) => KNOWN_BODY_TYPES.has(bt ?? '')

export const TANK_FIELDS = [
  'fuel_tank_capacity_liters', 'norma_combustibil',
  'consum_urban', 'consum_extraurban', 'consum_mixt',
] as const
export const BATTERY_FIELDS = [
  'battery_capacity_kwh', 'norma_energie', 'electric_range_km',
] as const
export const CARGO_FIELDS = [
  'payload_kg', 'cargo_volume_m3',
  'cargo_length_mm', 'cargo_width_mm', 'cargo_height_mm', 'euro_pallets',
] as const

/**
 * Spec-field keys that should be set to null for the given fuel_type / body_type
 * on save — but only when that value is a recognized value that legitimately
 * excludes the group. Unknown/blank fuel_type or body_type clears nothing.
 */
export function specFieldsToClear(
  fuelType?: string | null,
  bodyType?: string | null,
): string[] {
  const out: string[] = []
  if (isKnownFuelType(fuelType) && !usesFuelTank(fuelType)) out.push(...TANK_FIELDS)
  if (isKnownFuelType(fuelType) && !usesBattery(fuelType)) out.push(...BATTERY_FIELDS)
  if (isKnownBodyType(bodyType) && !usesCargo(bodyType)) out.push(...CARGO_FIELDS)
  return out
}
