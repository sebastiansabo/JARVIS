import { Badge } from '@/components/ui/badge'
import type { FoiContract } from '@/types/foiParcurs'

// "Replanificat" marker for a session whose time was moved (a late/missed drive
// revived to PLANNED, or any planned drive rescheduled). Tooltip carries when
// (rescheduled_at). Renders nothing for a session that was never rescheduled.
export default function RescheduledBadge({ session, className = '' }: { session: FoiContract; className?: string }) {
  if (!session.rescheduled_at) return null
  const when = new Date(session.rescheduled_at).toLocaleString('ro-RO')
  return (
    <Badge
      variant="outline"
      title={`Replanificat la ${when}`}
      className={`text-[10px] border-sky-400 text-sky-700 dark:text-sky-400 ${className}`}
    >
      Replanificat
    </Badge>
  )
}
