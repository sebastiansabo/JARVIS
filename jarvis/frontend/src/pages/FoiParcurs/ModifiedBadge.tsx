import { Badge } from '@/components/ui/badge'
import type { FoiContract } from '@/types/foiParcurs'

// "Modificat" marker for a session an admin corrected or an advisor extended.
// Tooltip carries who + when (corrected_by / corrected_at). Renders nothing for
// an untouched session.
export default function ModifiedBadge({ session, className = '' }: { session: FoiContract; className?: string }) {
  if (!session.corrected_at) return null
  const when = new Date(session.corrected_at).toLocaleString('ro-RO')
  const who = session.corrected_by ? ` de ${session.corrected_by}` : ''
  return (
    <Badge
      variant="outline"
      title={`Modificat${who} la ${when}`}
      className={`text-[10px] border-amber-400 text-amber-700 dark:text-amber-400 ${className}`}
    >
      Modificat
    </Badge>
  )
}
