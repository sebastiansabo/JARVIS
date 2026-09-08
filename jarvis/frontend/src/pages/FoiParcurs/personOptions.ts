export type PersonKind = 'client' | 'user'
export type PersonSource = 'clients' | 'users'

export interface PersonOption {
  key: string        // stable React key
  name: string       // display name — what the field stores
  detail?: string    // phone / sublabel
  kind: PersonKind
}

export interface PersonSourceClient { id: number; name: string; phone?: string | null }
export interface PersonSourceUser { id?: number; name: string; phone?: string | null }

/** Merge CRM clients + internal users into a deduped, query-filtered suggestion
 *  list for the person picker. CRM clients arrive already server-filtered (the
 *  /clients/search endpoint), so they pass through as-is; users come from the
 *  full directory and are filtered client-side by name/phone. Dedupes by
 *  case-insensitive name (client wins — it carries a phone and is the driving
 *  party). Caps to `limit`. */
export function mergePersonOptions(
  query: string,
  clients: PersonSourceClient[],
  users: PersonSourceUser[],
  opts: { limit?: number; sources?: PersonSource[] } = {},
): PersonOption[] {
  const limit = opts.limit ?? 8
  const sources = opts.sources ?? ['clients', 'users']
  const q = query.trim().toLowerCase()
  const out: PersonOption[] = []
  const seen = new Set<string>()

  const push = (name: string, detail: string | null | undefined, kind: PersonKind) => {
    const key = (name || '').trim().toLowerCase()
    if (!key || seen.has(key)) return
    seen.add(key)
    out.push({ key: `${kind}:${key}`, name: name.trim(), detail: detail || undefined, kind })
  }

  if (sources.includes('clients')) {
    for (const c of clients) push(c.name, c.phone, 'client')
  }
  if (sources.includes('users') && q.length >= 1) {
    for (const u of users) {
      const hay = `${u.name} ${u.phone || ''}`.toLowerCase()
      if (hay.includes(q)) push(u.name, u.phone, 'user')
    }
  }
  return out.slice(0, limit)
}
