// Romanian civilian plate helpers.
// Canonical form: "<COUNTY> <digits> <letters>", single-space separated.
// County is either "B" (Bucharest: 2–3 digits) or two letters (2 digits).
// Provisional plates (numere provizorii) are county + 6–8 digits and NO
// letters (e.g. "CJ 123456" / "CJ 0231879") — accepted alongside the mask.

// Max digits kept in a provisional plate's number group (min enforced by the
// validator).
const MAX_PROVISIONAL_DIGITS = 8

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
  const allDigits = rest.match(/^\d+/)?.[0] ?? ''
  const afterDigits = rest.slice(allDigits.length)
  const letters = (afterDigits.match(/^[A-Z]+/)?.[0] ?? '').slice(0, 3)
  // Standard plates carry trailing letters and cap the digit group at 2 (3 for
  // Bucharest). A provisional plate is county + digits with no letters — allow
  // its longer, fixed-length number group.
  const maxDigits = county === 'B' ? 3 : 2
  const digits = letters
    ? allDigits.slice(0, maxDigits)
    : allDigits.slice(0, MAX_PROVISIONAL_DIGITS)
  return [county, digits, letters].filter(Boolean).join(' ')
}

export function isValidRoPlate(v: string): boolean {
  const s = v.trim().toUpperCase()
  // Standard civilian: county + 2 digits (3 for Bucharest) + 3 letters.
  const standard = /^(B \d{2,3}|[A-Z]{2} \d{2}) [A-Z]{3}$/.test(s)
  // Provisional (numere provizorii): county + 6–8 digits, no letters.
  const provisional = /^(B|[A-Z]{2}) \d{6,8}$/.test(s)
  return standard || provisional
}
