import type { VinHistoryEntry } from '@/types/buyback'

/** A number as ro-RO grouped euros ("8.500 €"), or "—" when absent. */
export function fmtEur(v: number | null | undefined): string {
  return v != null ? `${v.toLocaleString('ro-RO')} €` : '—'
}

/** An ISO date as ro-RO dd.mm.yyyy, or "—" when empty/invalid. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('ro-RO', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

/**
 * One-line "this car was evaluated before" banner from a VIN's prior buyback
 * history (newest first), or null when there is none. Leads with the most
 * recent evaluation — where, when, and its last offer — then notes how many
 * earlier ones exist, matching what the sales team wants at a glance.
 */
export function vinHistoryWarning(entries: VinHistoryEntry[]): string | null {
  if (!entries || entries.length === 0) return null
  const [latest] = entries
  const where = latest.company_name || 'altă locație'
  const offer = latest.last_offer_eur != null
    ? `ultima ofertă ${fmtEur(latest.last_offer_eur)}`
    : 'fără ofertă'
  let msg = `Evaluat anterior la ${where} · ${fmtDate(latest.created_at)} · ${offer}`
  if (entries.length > 1) msg += ` (+${entries.length - 1} evaluări anterioare)`
  return msg
}
