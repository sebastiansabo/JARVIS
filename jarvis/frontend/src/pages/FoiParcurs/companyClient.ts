import type { CrmClient } from '@/types/foiParcurs'

// Romanian legal-form tokens. CRM data often stores companies as client_type
// 'person' with the legal form only in the display name (e.g. "NELAURA COMIMPEX
// SRL"), so the company→contact gate must recognise those too — otherwise a
// company session slips through without a driver contact.
export const COMPANY_NAME_RE = /\b(s\.?r\.?l\.?(-d)?|s\.?a\.?|s\.?n\.?c\.?|s\.?c\.?[as]\.?|p\.?f\.?a\.?)\b/i

/** A CRM client is treated as a company (needs a gate-valid driver contact) when
 *  it is typed 'company' OR its name carries a RO legal form. Kept in sync with
 *  the backend `_is_company_client` in foi_parcurs/routes/test_drive.py. */
export function isCompanyClientLike(client?: CrmClient | null): boolean {
  if (!client) return false
  if (client.client_type === 'company') return true
  return COMPANY_NAME_RE.test(client.display_name || client.name || '')
}
