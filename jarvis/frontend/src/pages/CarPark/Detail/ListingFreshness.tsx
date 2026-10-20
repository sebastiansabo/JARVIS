import { Badge } from '@/components/ui/badge'

export type Freshness = 'not_published' | 'up_to_date' | 'stale' | 'expired' | 'inactive' | 'error' | 'draft' | 'moderation'

const LABELS: Record<Freshness, { text: string; cls: string }> = {
  up_to_date:    { text: 'La zi',                cls: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  stale:         { text: 'Necesită actualizare', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200' },
  expired:       { text: 'Expirat',              cls: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
  inactive:      { text: 'Inactiv',              cls: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300' },
  error:         { text: 'Eroare',               cls: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
  not_published: { text: 'Nepublicat',           cls: '' },
  draft:         { text: 'Draft (neplătit)',     cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200' },
  moderation:    { text: 'În moderare',          cls: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300' },
}

export const formatListingTime = (iso?: string | null) => {
  if (!iso) return null
  const d = new Date(iso)
  return new Intl.DateTimeFormat('ro-RO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(d)
}

// Just the colored status pill. Rendered inline (alongside the "Auto" pill) in
// the publish row, so it must stay a single element — keep the sync/expiry meta
// out of here, or it breaks the one-line pill baseline.
export function FreshnessBadge({ freshness }: { freshness: Freshness }) {
  const l = LABELS[freshness]
  return <Badge variant="secondary" className={`font-normal ${l.cls}`}>{l.text}</Badge>
}

export function ListingFreshness({ freshness, lastSync, expiresAt }: {
  freshness: Freshness; lastSync?: string | null; expiresAt?: string | null
}) {
  return (
    <div className="flex flex-col items-end gap-0.5">
      <FreshnessBadge freshness={freshness} />
      {lastSync && <span className="text-[11px] text-muted-foreground">Ultima sincronizare: {formatListingTime(lastSync)}</span>}
      {expiresAt && freshness === 'expired' && <span className="text-[11px] text-muted-foreground">Expirat: {formatListingTime(expiresAt)}</span>}
    </div>
  )
}
