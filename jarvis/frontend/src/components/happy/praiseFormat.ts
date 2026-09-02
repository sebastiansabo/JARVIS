/** Shared formatting for Praise (Aprecieri) lists. */

/**
 * A person's display name, falling back to `#<id>` when the name is missing
 * (e.g. the account was deleted, so the JOIN yields NULL).
 */
export function personLabel(name: string | null | undefined, id: string | number): string {
  const trimmed = (name ?? '').trim()
  return trimmed || `#${id}`
}

/** Short relative time in Romanian, e.g. "acum 3 zile". */
export function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(ms / 60_000)
  if (mins < 1) return 'acum'
  if (mins < 60) return `acum ${mins} min`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `acum ${hrs} h`
  const days = Math.floor(hrs / 24)
  return `acum ${days} ${days === 1 ? 'zi' : 'zile'}`
}
