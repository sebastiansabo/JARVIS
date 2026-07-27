import type { FoiContract, ReturnFuelLevel, ReturnTestDrivePayload } from '@/types/foiParcurs'
import { type DamageState, fromDamagePayload, toDamagePayload, makeEmptyDamageState } from './testDriveDamage'

export interface ReturnFormState {
  kmEnd: string
  fuel: ReturnFuelLevel | null
  damage: DamageState
  notes: string
  advisorSignature: string
  clientSignature: string
}

/** Seed the return damage from what was recorded at handover so the advisor
 *  confirms + adds, instead of starting blank (which hides departure damage). */
export function seedReturnDamage(contract: Pick<FoiContract, 'departure_damage'>): { damage: DamageState; seeded: boolean } {
  const items = contract.departure_damage
  if (Array.isArray(items) && items.length > 0) {
    return { damage: fromDamagePayload(items), seeded: true }
  }
  return { damage: makeEmptyDamageState(), seeded: false }
}

/** Inline error for the km_end field — null while untouched or valid. */
export function kmEndError(kmEnd: string, kmStart?: number | null): string | null {
  if (kmEnd.trim() === '') return null
  const n = Number(kmEnd)
  if (Number.isNaN(n)) return 'Km retur invalid.'
  const start = kmStart == null ? NaN : Number(kmStart)
  if (!Number.isNaN(start) && n < start) return `Km retur trebuie să fie ≥ km plecare (${kmStart}).`
  return null
}

export function returnMissing(s: ReturnFormState, kmStart?: number | null) {
  const n = Number(s.kmEnd)
  const start = kmStart == null ? NaN : Number(kmStart)
  const kmValid = s.kmEnd.trim() !== '' && !Number.isNaN(n) && (Number.isNaN(start) || n >= start)
  return { km: !kmValid, fuel: !s.fuel, advisorSig: !s.advisorSignature, clientSig: !s.clientSignature }
}

export function isReturnValid(s: ReturnFormState, kmStart?: number | null): boolean {
  return !Object.values(returnMissing(s, kmStart)).some(Boolean)
}

export function buildReturnPayload(s: ReturnFormState): ReturnTestDrivePayload {
  const notes = s.notes.trim()
  return {
    km_end: Number(s.kmEnd),
    fuel_gauge_end_level: s.fuel!,
    return_damage: toDamagePayload(s.damage),
    ...(notes ? { return_notes: notes } : {}),
    advisor_signature: s.advisorSignature,
    client_signature: s.clientSignature,
  }
}
