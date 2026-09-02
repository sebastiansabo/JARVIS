import type { FoiContract } from '@/types/foiParcurs'

/** Lower-cased user name → phone, for resolving an internal session's driving
 *  user (advisor_name) to their profile phone. Built from usersApi.getUsers();
 *  advisor_name === users.name is the same match the backend uses to map an
 *  advisor to a user. */
export function buildUserPhoneMap(users: { name: string; phone: string | null }[]): Map<string, string | null> {
  const m = new Map<string, string | null>()
  for (const u of users) {
    const key = (u.name || '').trim().toLowerCase()
    if (key) m.set(key, u.phone)
  }
  return m
}

export interface ClientCell {
  /** The person who drives — what the Client column leads with. */
  primary: string
  /** The company behind a company booking (kept as a secondary line); null when
   *  there's no distinct company (person client / internal / no driver). */
  secondary: string | null
}

/**
 * What the "Client" column shows: the person who drives is primary (Client =
 * Driver). For a company booking the driver is the contact person and the
 * company drops to a secondary line; a person booking shows the person; an
 * internal log shows the driving user (advisor).
 */
export function clientCell(c: FoiContract): ClientCell {
  if (c.is_internal) {
    return { primary: (c.advisor_name || '').trim() || '—', secondary: null }
  }
  const client = (c.client_name || '').trim() || (c.client_id != null ? `Client #${c.client_id}` : '')
  const driver = (c.driver_name || '').trim()
  if (driver && driver !== client) return { primary: driver, secondary: client || null }
  return { primary: client || '—', secondary: null }
}

export interface SessionParty {
  /** true when this is an internal (QuickSession) driving log — no customer. */
  isInternal: boolean
  /** Slot label: 'Client' for a Test Drive, 'Șofer' for an internal log. */
  label: string
  /** Party name: the client for a TD, the driving user for an internal log. */
  name: string
  /** Party phone: the client's phone for a TD, the driving user's profile phone
   *  (resolved from the Users directory) for an internal log; '—' if unknown. */
  phone: string
}

/**
 * Who a session's card shows as its "party" and phone. A normal Test Drive shows
 * the client (+ client_phone). An internal driving log has no client — the
 * driving user IS the party, so we show the advisor's name and resolve their
 * phone from the Users directory.
 */
export function sessionParty(c: FoiContract, usersByPhone?: Map<string, string | null>): SessionParty {
  if (c.is_internal) {
    const driver = (c.advisor_name || '').trim()
    const phone = usersByPhone?.get(driver.toLowerCase()) ?? null
    return { isInternal: true, label: 'Șofer', name: driver || '—', phone: phone || '—' }
  }
  const name = c.client_name || (c.client_id != null ? `Client #${c.client_id}` : '—')
  return { isInternal: false, label: 'Client', name, phone: c.client_phone || '—' }
}
