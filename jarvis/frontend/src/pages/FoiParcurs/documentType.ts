// A document-type key: 'sales' (fixed default), 'service', or any user-defined
// type slug. Widened from the old fixed union so types are data-driven.
export type DocType = string

export interface DocumentType {
  key: string
  label: string
  is_rental: boolean
  has_template?: boolean
  is_default?: boolean
  is_active?: boolean
  sort_order?: number
}

// Fallback labels for the built-in keys — live labels come from the API
// (getDocumentTypes). Used when the type list isn't loaded yet.
export const DOC_TYPE_LABELS: Record<string, string> = {
  sales: 'Vânzări',
  service: 'Mașini de curtoazie',
}

/** Resolve a display label for a key, preferring the loaded type list. */
export function docTypeLabel(key: string, types?: { key: string; label: string }[]): string {
  return types?.find((t) => t.key === key)?.label || DOC_TYPE_LABELS[key] || key
}

/** Read the `context` query param (a document-type key); blank → 'sales'. */
export function contextFromSearch(search: string): DocType {
  return new URLSearchParams(search).get('context') || 'sales'
}
