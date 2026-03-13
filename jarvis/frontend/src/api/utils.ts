/**
 * Build a query string from a params object.
 * Skips undefined, null, and empty-string values.
 *
 * @example
 * buildQs({ page: 1, q: '', status: 'active' }) → '?page=1&status=active'
 */
export function buildQs(params: Record<string, unknown> | object): string {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  })
  const s = qs.toString()
  return s ? `?${s}` : ''
}
