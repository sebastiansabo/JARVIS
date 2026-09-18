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

/** On create, default current_price to the active selling price when it is unset. */
export function seedCurrentPriceOnCreate<T extends Record<string, unknown>>(
  payload: T,
  isEdit: boolean,
): T {
  if (isEdit) return payload
  if (positivePrice(payload.current_price) != null) return payload
  return { ...payload, current_price: activeSellingPrice(payload) }
}
