import { Badge } from '@/components/ui/badge'
import type { FoiContract } from '@/types/foiParcurs'

/** "Eveniment" marker for a session tied to an HR event (Task 15) — mirrors
 *  ModifiedBadge's shape. Renders only when the row carries an event_id;
 *  prefers the joined event_name (get_contracts/get_contract_by_id LEFT JOIN
 *  hr.events), falling back to mkt_project_name (older rows whose event
 *  linkage predates the dedicated hr.events join) then a numeric placeholder.
 *  Renders nothing for a plain campaign (mkt_project_id, no event_id) or a
 *  session with neither. */
export default function EventBadge({ session, className = '' }: { session: FoiContract; className?: string }) {
  if (!session.event_id) return null
  const label = session.event_name || session.mkt_project_name || `Eveniment #${session.event_id}`
  return (
    <Badge
      variant="outline"
      title={`Eveniment: ${label}`}
      className={`text-[10px] border-violet-400 text-violet-700 dark:text-violet-400 ${className}`}
    >
      {label}
    </Badge>
  )
}
