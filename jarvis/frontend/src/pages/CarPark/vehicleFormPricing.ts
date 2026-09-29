// Selling-price rules for the vehicle editor's "Preț" tab. A first selling
// (list) price is mandatory when a car is *added*; editing an existing car is
// never blocked. On create the active price (current_price) is seeded from the
// selling price so the new car shows a price everywhere immediately, and the
// profile "Fișă de preț" keeps current_price in sync on publish.

/** True when v is a usable positive price (accepts number or numeric string). */
function positivePrice(v: unknown): number | null {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isNaN(n) || n <= 0 ? null : n
}

/** RO error message when a new car is saved without a valid list price. */
export function validateListPriceOnCreate(
  form: { list_price?: unknown },
  isEdit: boolean,
): string | null {
  if (isEdit) return null
  return positivePrice(form.list_price) == null ? 'Prețul de listă este obligatoriu' : null
}

/** The active selling price shown in listings: the promo when set, else the list. */
export function activeSellingPrice(fields: {
  list_price?: unknown
  promotional_price?: unknown
}): number | null {
  return positivePrice(fields.promotional_price) ?? positivePrice(fields.list_price)
}

/**
 * Keep current_price — the active price the catalog list/sort/filter reads — in
 * step with the selling price. On create, seed it from the active selling price
 * when unset. On edit, re-sync it to the active selling price so the catalog
 * doesn't show a stale price after a list/promo edit; but never wipe it when the
 * form currently has no positive selling price.
 */
export function syncCurrentPrice<T extends Record<string, unknown>>(
  payload: T,
  isEdit: boolean,
): T {
  const active = activeSellingPrice(payload)
  if (!isEdit) {
    if (positivePrice(payload.current_price) != null) return payload
    return { ...payload, current_price: active }
  }
  if (active == null) return payload
  return { ...payload, current_price: active }
}
