// Romanian civilian plate helpers.
// Canonical form: "<COUNTY> <digits> <letters>", single-space separated.
// County is either "B" (Bucharest: 2–3 digits) or two letters (2 digits).
// Provisional/temporary/special-series plates are out of scope for the mask.

function splitCounty(s: string): { county: string; rest: string } {
  // Bucharest only when the string is exactly "B" or "B" followed by a digit.
  if (s === 'B' || (s[0] === 'B' && /\d/.test(s[1] ?? ''))) {
    return { county: 'B', rest: s.slice(1) }
  }
  return { county: s.slice(0, 2), rest: s.slice(2) }
}

export function formatRoPlate(raw: string): string {
  const s = raw.toUpperCase().replace(/[^A-Z0-9]/g, '')
  if (!s) return ''
  const { county, rest } = splitCounty(s)
  const maxDigits = county === 'B' ? 3 : 2
  const digits = (rest.match(/^\d+/)?.[0] ?? '').slice(0, maxDigits)
  const afterDigits = rest.slice((rest.match(/^\d+/)?.[0] ?? '').length)
  const letters = (afterDigits.match(/^[A-Z]+/)?.[0] ?? '').slice(0, 3)
  return [county, digits, letters].filter(Boolean).join(' ')
}

export function isValidRoPlate(v: string): boolean {
  return /^(B \d{2,3}|[A-Z]{2} \d{2}) [A-Z]{3}$/.test(v.trim().toUpperCase())
}
