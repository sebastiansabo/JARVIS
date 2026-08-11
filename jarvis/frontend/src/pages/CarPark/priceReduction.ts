// Reduction-percentage helper for a struck-through original price shown next
// to a lower current/promotional price. Shared by the Kanban card (CardPrice
// in Dispo/KanbanBoard.tsx) and the Vehicle Detail price panel (Detail.tsx)
// so both compute and format the "−X%" indicator identically.

/**
 * Returns the price cut as a positive percentage rounded to one decimal
 * (e.g. 4.2 for original=23900 / current=22900), or null when there's no
 * real reduction to show: a missing/non-numeric price, original <= 0,
 * current <= 0, or current >= original (current === original is "no
 * reduction", not a 0% badge).
 */
export function reductionPct(
  original: number | null | undefined,
  current: number | null | undefined,
): number | null {
  if (original == null || current == null) return null
  if (!Number.isFinite(original) || !Number.isFinite(current)) return null
  if (!(original > 0) || !(current > 0) || !(current < original)) return null
  const pctRaw = ((original - current) / original) * 100
  return Math.round(pctRaw * 10) / 10
}

/**
 * Formats a reductionPct() result as a Romanian-locale "−X,Y%" label
 * (comma decimal separator, real minus sign) — or null when there's
 * nothing to render.
 */
export function formatReductionPct(pct: number | null): string | null {
  if (pct == null) return null
  return `−${pct.toLocaleString('ro-RO', { maximumFractionDigits: 1 })}%`
}
