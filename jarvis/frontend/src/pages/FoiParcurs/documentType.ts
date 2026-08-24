export type DocType = 'sales' | 'service'

export const DOC_TYPE_LABELS: Record<DocType, string> = {
  sales: 'Vânzări',
  service: 'Mașini de curtoazie',
}

/** Read the `context` query param; anything but 'service' → 'sales'. */
export function contextFromSearch(search: string): DocType {
  return new URLSearchParams(search).get('context') === 'service' ? 'service' : 'sales'
}
